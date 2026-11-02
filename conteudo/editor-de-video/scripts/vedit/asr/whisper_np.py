"""Whisper (OpenAI, licença MIT) em numpy puro: log-mel, encoder, decoder com cache, decodificação gulosa com
regras de timestamp, janelas longas e tempo por palavra via DTW na atenção cruzada. Sem torch/onnx/internet."""
import base64
import json
import math
import re
import time
import zlib

import numpy as np

SR = 16000
N_FFT = 400
HOP = 160
N_FRAMES = 3000
TOK_POR_SEG = 50  # posições de áudio por segundo no encoder

IDIOMAS = ("en zh de es ru ko fr ja pt tr pl ca nl ar sv it id hi fi vi he uk el ms cs ro da hu ta no th ur hr bg lt "
           "la mi ml cy sk te fa lv bn sr az sl kn et mk br eu is hy ne mn bs kk sq sw gl mr pa si km sn yo so af oc ka "
           "be tg sd gu am yi lo uz fo ht ps tk nn mt sa lb my bo tl mg as tt haw ln ha ba jw su").split()

ALUCINACOES = ["amara.org", "legendas pela comunidade", "obrigado por assistir", "inscreva-se no canal",
               "legenda adriana", "transcrição e legendas", "subtitles by", "thanks for watching",
               "e aí pessoal, tudo bem", "tchau, tchau"]


# ------------------------------------------------------------------ áudio -> log-mel
def _hz_mel(f):
    f = np.asarray(f, np.float64)
    f_sp = 200.0 / 3
    mels = f / f_sp
    min_log_hz, min_log_mel, logstep = 1000.0, 1000.0 / f_sp, math.log(6.4) / 27.0
    return np.where(f >= min_log_hz, min_log_mel + np.log(np.maximum(f, 1e-10) / min_log_hz) / logstep, mels)


def _mel_hz(m):
    m = np.asarray(m, np.float64)
    f_sp = 200.0 / 3
    freqs = f_sp * m
    min_log_hz, min_log_mel, logstep = 1000.0, 1000.0 / f_sp, math.log(6.4) / 27.0
    return np.where(m >= min_log_mel, min_log_hz * np.exp(logstep * (m - min_log_mel)), freqs)


def filtros_mel(n_mels=80, sr=SR, n_fft=N_FFT):
    """Igual a librosa.filters.mel(sr, n_fft, n_mels) (escala e normalização 'slaney')."""
    fft_f = np.linspace(0, sr / 2, 1 + n_fft // 2)
    mel_f = _mel_hz(np.linspace(_hz_mel(0.0), _hz_mel(sr / 2.0), n_mels + 2))
    fdiff = np.diff(mel_f)
    ramps = np.subtract.outer(mel_f, fft_f)
    w = np.zeros((n_mels, len(fft_f)))
    for i in range(n_mels):
        lower = -ramps[i] / fdiff[i]
        upper = ramps[i + 2] / fdiff[i + 1]
        w[i] = np.maximum(0, np.minimum(lower, upper))
    w *= (2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels]))[:, None]
    return w.astype(np.float32)


def log_mel(audio, filtros, pad_segundos=30):
    """log-mel como no Whisper (torch.stft center=True, Hann periódica, descarta o último quadro)."""
    a = np.concatenate([np.asarray(audio, np.float32), np.zeros(int(pad_segundos * SR), np.float32)])
    a = np.pad(a, (N_FFT // 2, N_FFT // 2), mode="reflect")
    n = 1 + (len(a) - N_FFT) // HOP
    jan = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)
    out = np.empty((filtros.shape[0], n - 1), np.float32)
    bloco = 4000
    for i0 in range(0, n - 1, bloco):
        i1 = min(n - 1, i0 + bloco)
        idx = np.arange(i0, i1)[:, None] * HOP + np.arange(N_FFT)[None, :]
        spec = np.fft.rfft(a[idx] * jan, n=N_FFT, axis=1)
        mag = (spec.real ** 2 + spec.imag ** 2).astype(np.float32)
        out[:, i0:i1] = filtros @ mag.T
    lg = np.log10(np.maximum(out, 1e-10))
    lg = np.maximum(lg, lg.max() - 8.0)
    return (lg + 4.0) / 4.0


# ------------------------------------------------------------------ utilidades numéricas
def _erf(x):
    s = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * a)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-a * a)
    return s * y


def _gelu(x):
    return 0.5 * x * (1.0 + _erf(x * 0.7071067811865476))


def _ln(x, w, b, eps=1e-5):
    m = x.mean(-1, keepdims=True)
    v = ((x - m) ** 2).mean(-1, keepdims=True)
    return (x - m) / np.sqrt(v + eps) * w + b


def _softmax(x, eixo=-1):
    x = x - x.max(axis=eixo, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=eixo, keepdims=True)


def _log_softmax(x):
    m = x.max()
    return x - m - math.log(np.exp(x - m).sum())


def _razao_compressao(txt):
    b = txt.encode("utf-8")
    return len(b) / max(1, len(zlib.compress(b)))


# ------------------------------------------------------------------ tokenizador (BPE em bytes, formato tiktoken)
class Tokenizador:
    def __init__(self, tokens_txt, n_vocab):
        self.bytes = {}
        self.rank = {}
        for ln in tokens_txt.splitlines():
            p = ln.split()
            if len(p) != 2:
                continue
            try:
                b = base64.b64decode(p[0])
            except Exception:
                b = b""
            i = int(p[1])
            self.bytes[i] = b
            if b:
                self.rank.setdefault(b, i)
        self.n_vocab = n_vocab
        self.eot = 50257
        self.sot = 50258
        self.traduzir = 50358
        self.transcrever = 50359
        self.sot_lm = 50360
        self.sot_prev = 50361
        self.sem_fala = 50362
        self.sem_ts = 50363
        self.ts0 = 50364
        self._re = re.compile(r"""'s|'t|'re|'ve|'m|'ll|'d| ?[^\W\d_]+| ?\d+| ?[^\s\w]+| ?_+|\s+(?!\S)|\s+""")

    def idioma(self, cod):
        cod = (cod or "pt").lower()[:3].strip()
        if cod not in IDIOMAS:
            cod = "pt"
        return self.sot + 1 + IDIOMAS.index(cod)

    def decodificar_bytes(self, toks):
        return b"".join(self.bytes.get(t, b"") for t in toks if t < self.eot)

    def texto(self, toks):
        return self.decodificar_bytes(toks).decode("utf-8", "replace")

    def codificar(self, txt):
        out = []
        for m in self._re.finditer(txt):
            peca = m.group(0).encode("utf-8")
            if peca in self.rank:
                out.append(self.rank[peca])
                continue
            partes = [bytes([c]) for c in peca]
            while len(partes) > 1:
                melhor = None
                for i in range(len(partes) - 1):
                    r = self.rank.get(partes[i] + partes[i + 1])
                    if r is not None and (melhor is None or r < melhor[0]):
                        melhor = (r, i)
                if melhor is None:
                    break
                i = melhor[1]
                partes = partes[:i] + [partes[i] + partes[i + 1]] + partes[i + 2:]
            out.extend(self.rank[p] for p in partes if p in self.rank)
        return out

    def suprimidos(self):
        simbolos = set('"#()*+/:;<=>@[\\]^_`{|}~「」『』♩♪♫♬♭♮♯')
        extra = {"<<", ">>", "<<<", ">>>", "--", "---", "-(", "-[", "('", '("', "((", "))", "(((", ")))", "[[", "]]",
                 "{{", "}}", "♪♪", "♪♪♪"}
        s = []
        for i, b in self.bytes.items():
            try:
                t = b.decode("utf-8").strip()
            except Exception:
                continue
            if t and (all(c in simbolos for c in t) or t in extra):
                s.append(i)
        s += list(range(self.sot, self.sem_ts + 1))
        return np.array(sorted(set(s)), np.int64)


# ------------------------------------------------------------------ modelo
class Whisper:
    def __init__(self, caminho):
        t = time.time()
        z = np.load(caminho)
        self.meta = json.loads(bytes(z["__meta__"]).decode())
        W = {}
        for k in z.files:
            if k.startswith("__") or k.endswith("@s") or k.endswith("@eixo"):
                continue
            if k.endswith("@q"):
                b = k[:-2]
                q = z[k].astype(np.float32)
                s = z[b + "@s"].astype(np.float32)
                W[b] = q * (s[None, :] if int(z[b + "@eixo"][0]) == 1 else s[:, None])
            else:
                W[k] = z[k].astype(np.float32)
        self.W = W
        m = self.meta
        self.d, self.H = m["d"], m["n_head"]
        self.n_enc, self.n_dec = m["n_enc"], m["n_dec"]
        self.dh = self.d // self.H
        self.esc = self.dh ** -0.25
        nm = m["n_mels"]
        self.c1 = np.ascontiguousarray(W["enc.conv1.weight"].transpose(2, 1, 0).reshape(3 * nm, self.d))
        self.c2 = np.ascontiguousarray(W["enc.conv2.weight"].transpose(2, 1, 0).reshape(3 * self.d, self.d))
        self.emb = W["dec.token_embedding.weight"]
        self.tok = Tokenizador(bytes(z["__tokens__"]).decode("utf-8"), m["n_vocab"])
        self.supr = self.tok.suprimidos()
        self.fm = filtros_mel(nm)
        self.nome = m.get("nome", "whisper")
        self.t_carga = time.time() - t

    # -------------------------------------------------------------- encoder
    def _conv(self, x, Wr, b, passo):
        T = x.shape[0]
        xp = np.pad(x, ((1, 1), (0, 0)))
        if passo == 1:
            col = np.concatenate([xp[0:T], xp[1:T + 1], xp[2:T + 2]], axis=1)
        else:
            To = (T - 1) // 2 + 1
            idx = np.arange(To) * 2
            col = np.concatenate([xp[idx], xp[idx + 1], xp[idx + 2]], axis=1)
        return col @ Wr + b

    def codificar(self, mel):
        W = self.W
        x = _gelu(self._conv(mel.T, self.c1, W["enc.conv1.bias"], 1))
        x = _gelu(self._conv(x, self.c2, W["enc.conv2.bias"], 2))
        x = x + W["enc.positional_embedding"][: x.shape[0]]
        H, dh, d = self.H, self.dh, self.d
        T = x.shape[0]
        for i in range(self.n_enc):
            p = "enc.blocks.%d." % i
            h = _ln(x, W[p + "attn_ln.weight"], W[p + "attn_ln.bias"])
            q = ((h @ W[p + "attn.q.w"] + W[p + "attn.q.b"]) * self.esc).reshape(T, H, dh).transpose(1, 0, 2)
            k = ((h @ W[p + "attn.k.w"]) * self.esc).reshape(T, H, dh).transpose(1, 2, 0)
            v = (h @ W[p + "attn.v.w"] + W[p + "attn.v.b"]).reshape(T, H, dh).transpose(1, 0, 2)
            a = _softmax(q @ k) @ v
            x = x + a.transpose(1, 0, 2).reshape(T, d) @ W[p + "attn.o.w"] + W[p + "attn.o.b"]
            h = _ln(x, W[p + "mlp_ln.weight"], W[p + "mlp_ln.bias"])
            x = x + _gelu(h @ W[p + "mlp.0.w"] + W[p + "mlp.0.b"]) @ W[p + "mlp.2.w"] + W[p + "mlp.2.b"]
        return _ln(x, W["enc.ln_post.weight"], W["enc.ln_post.bias"])

    # -------------------------------------------------------------- decoder
    def preparar_cruzada(self, xa):
        W = self.W
        T = xa.shape[0]
        H, dh = self.H, self.dh
        self.kc, self.vc = [], []
        for i in range(self.n_dec):
            p = "dec.blocks.%d." % i
            k = (xa @ W[p + "cross.k.w"]) * self.esc
            v = xa @ W[p + "cross.v.w"] + W[p + "cross.v.b"]
            self.kc.append(np.ascontiguousarray(k.reshape(T, H, dh).transpose(1, 2, 0)))
            self.vc.append(np.ascontiguousarray(v.reshape(T, H, dh).transpose(1, 0, 2)))

    def novo_cache(self):
        return {"n": 0, "K": [np.zeros((self.H, self.dh, 448), np.float32) for _ in range(self.n_dec)],
                "V": [np.zeros((self.H, 448, self.dh), np.float32) for _ in range(self.n_dec)]}

    def passo(self, toks, cache, capturar=None):
        """Roda o decoder para os novos tokens. capturar: conjunto de camadas cujo QK cruzado deve ser guardado."""
        W = self.W
        n = len(toks)
        off = cache["n"]
        H, dh, d = self.H, self.dh, self.d
        x = self.emb[np.array(toks)] + W["dec.positional_embedding"][off:off + n]
        qks = {}
        tot = off + n
        mask = None
        if n > 1:
            mask = np.triu(np.full((n, tot), -np.inf, np.float32), k=off + 1)
        for i in range(self.n_dec):
            p = "dec.blocks.%d." % i
            h = _ln(x, W[p + "attn_ln.weight"], W[p + "attn_ln.bias"])
            q = ((h @ W[p + "attn.q.w"] + W[p + "attn.q.b"]) * self.esc).reshape(n, H, dh).transpose(1, 0, 2)
            k = ((h @ W[p + "attn.k.w"]) * self.esc).reshape(n, H, dh).transpose(1, 2, 0)
            v = (h @ W[p + "attn.v.w"] + W[p + "attn.v.b"]).reshape(n, H, dh).transpose(1, 0, 2)
            cache["K"][i][:, :, off:tot] = k
            cache["V"][i][:, off:tot, :] = v
            qk = q @ cache["K"][i][:, :, :tot]
            if mask is not None:
                qk = qk + mask
            a = _softmax(qk) @ cache["V"][i][:, :tot, :]
            x = x + a.transpose(1, 0, 2).reshape(n, d) @ W[p + "attn.o.w"] + W[p + "attn.o.b"]
            h = _ln(x, W[p + "cross_attn_ln.weight"], W[p + "cross_attn_ln.bias"])
            q = ((h @ W[p + "cross.q.w"] + W[p + "cross.q.b"]) * self.esc).reshape(n, H, dh).transpose(1, 0, 2)
            qk = q @ self.kc[i]
            if capturar is not None and i in capturar:
                qks[i] = qk
            a = _softmax(qk) @ self.vc[i]
            x = x + a.transpose(1, 0, 2).reshape(n, d) @ W[p + "cross.o.w"] + W[p + "cross.o.b"]
            h = _ln(x, W[p + "mlp_ln.weight"], W[p + "mlp_ln.bias"])
            x = x + _gelu(h @ W[p + "mlp.0.w"] + W[p + "mlp.0.b"]) @ W[p + "mlp.2.w"] + W[p + "mlp.2.b"]
        cache["n"] = tot
        x = _ln(x, W["dec.ln.weight"], W["dec.ln.bias"])
        return x @ self.emb.T, qks

    # -------------------------------------------------------------- decodificação de uma janela
    def _decodificar(self, lang, prompt, temperatura, rng):
        tk = self.tok
        ini = []
        if prompt:
            ini = [tk.sot_prev] + prompt[-223:]
        ini += [tk.sot, lang, tk.transcrever]
        cache = self.novo_cache()
        lg, _ = self.passo(ini, cache)
        p_sot = _softmax(lg[len(ini) - 3].astype(np.float64))
        sem_fala = float(p_sot[tk.sem_fala])
        ultimo = lg[-1].astype(np.float64)
        seq = []
        soma = 0.0
        ts0 = tk.ts0
        for passo in range(224 - 0):
            l = ultimo.copy()
            l[self.supr] = -np.inf
            if passo == 0:
                l[220] = -np.inf
                l[tk.eot] = -np.inf
            ult_ts = len(seq) >= 1 and seq[-1] >= ts0
            penult_ts = len(seq) < 2 or seq[-2] >= ts0
            if ult_ts:
                if penult_ts:
                    l[ts0:] = -np.inf
                else:
                    l[:tk.eot] = -np.inf
            tss = [s for s in seq if s >= ts0]
            if tss:
                lim = tss[-1] if (ult_ts and not penult_ts) else tss[-1] + 1
                l[ts0:lim] = -np.inf
            if not seq:
                l[:ts0] = -np.inf
                l[ts0 + 50 + 1:] = -np.inf
            lp = _log_softmax(l)
            lts = lp[ts0:]
            lts = lts[np.isfinite(lts)]
            if len(lts):
                m = lts.max()
                ts_lp = m + math.log(np.exp(lts - m).sum())
                txt_max = lp[:ts0].max()
                if ts_lp > txt_max:
                    l[:ts0] = -np.inf
                    lp = _log_softmax(l)
            if temperatura <= 0:
                t = int(np.argmax(l))
            else:
                pr = np.exp(_log_softmax(l / temperatura))
                t = int(rng.choice(len(pr), p=pr / pr.sum()))
            soma += float(lp[t]) if np.isfinite(lp[t]) else -10.0
            if t == tk.eot:
                break
            seq.append(t)
            if cache["n"] >= 447:
                break
            lg, _ = self.passo([t], cache)
            ultimo = lg[-1].astype(np.float64)
        return seq, soma / (len(seq) + 1), sem_fala

    # -------------------------------------------------------------- alinhamento por palavra (DTW)
    def _alinhar(self, lang, toks_texto, n_quadros):
        tk = self.tok
        if not toks_texto:
            return []
        seq = [tk.sot, lang, tk.transcrever, tk.sem_ts] + toks_texto + [tk.eot]
        camadas = set(range(self.n_dec // 2, self.n_dec))
        cache = self.novo_cache()
        _, qks = self.passo(seq, cache, capturar=camadas)
        M = max(1, n_quadros // 2)
        pesos = []
        for i in sorted(qks):
            for h in range(self.H):
                w = qks[i][h][:, :M]
                w = _softmax(w.astype(np.float64))
                pesos.append(w)
        P = np.stack(pesos)  # (heads, N, M)
        P = P[:, 3:-1]  # linhas que preveem texto + eot
        # escolhe as cabeças mais "diagonais" (monotônicas), mais robusto que usar todas
        N = P.shape[1]
        if N >= 4:
            idx = np.arange(N)
            notas = []
            for h in range(P.shape[0]):
                am = P[h].argmax(1)
                c = np.corrcoef(idx, am)[0, 1] if np.std(am) > 0 else 0.0
                mono = np.mean(np.diff(am) >= -1)
                notas.append((0 if np.isnan(c) else c) + mono)
            ordem = np.argsort(notas)[::-1]
            P = P[ordem[:max(6, len(ordem) // 4)]]
        std = P.std(axis=1, keepdims=True) + 1e-9
        P = (P - P.mean(axis=1, keepdims=True)) / std
        # filtro de mediana (largura 7) no eixo do tempo
        if P.shape[2] >= 7:
            pp = np.pad(P, ((0, 0), (0, 0), (3, 3)), mode="reflect")
            vis = np.stack([pp[:, :, k:k + P.shape[2]] for k in range(7)], -1)
            P = np.median(vis, -1)
        matriz = P.mean(0)
        ti, tt = _dtw(-matriz)
        # palavras (tokens que começam com espaço iniciam palavra; pontuação gruda na anterior)
        palavras, grupos = [], []
        for t in toks_texto + [tk.eot]:
            if t >= tk.eot:
                palavras.append("")
                grupos.append([t])
                continue
            b = tk.bytes.get(t, b"")
            s = b.decode("utf-8", "ignore")
            nova = (not palavras) or b.startswith(b" ") or (grupos and grupos[-1][0] >= tk.eot)
            if nova:
                palavras.append(s)
                grupos.append([t])
            else:
                palavras[-1] += s
                grupos[-1].append(t)
        # junta bytes quebrados (utf-8) por grupo
        palavras = [tk.decodificar_bytes(g).decode("utf-8", "replace") if g[0] < tk.eot else "" for g in grupos]
        saltos = np.pad(np.diff(ti), (1, 0), constant_values=1).astype(bool)
        tempos_salto = tt[saltos] / TOK_POR_SEG
        fronteiras = np.pad(np.cumsum([len(g) for g in grupos[:-1]]), (1, 0))
        out = []
        for k in range(len(grupos) - 1):
            a = fronteiras[k]
            b = fronteiras[k + 1]
            if a >= len(tempos_salto):
                break
            ini = float(tempos_salto[a])
            fim = float(tempos_salto[min(b, len(tempos_salto) - 1)])
            out.append({"p": palavras[k].strip(), "i": ini, "f": max(ini, fim), "toks": grupos[k]})
        return [w for w in out if w["p"]]

    # -------------------------------------------------------------- transcrição completa
    def transcrever(self, audio, idioma="pt", prompt=None, log_fn=print, fala=None, estado=None, orcamento=None):
        """estado: caminho de um .json para salvar/retomar o progresso; orcamento: segundos máximos nesta chamada.
        Retorna o resultado completo ou {'parcial': True, 'progresso': 0..1} se o orçamento acabar."""
        t_ini = time.time()
        tk = self.tok
        lang = tk.idioma(idioma)
        mel = log_mel(audio, self.fm)
        n_cont = max(0, len(audio) // HOP)
        voc = tk.codificar(" " + prompt.strip()) if prompt else []
        seek = 0
        anteriores = []
        segmentos, palavras = [], []
        if estado:
            try:
                st = json.load(open(estado, encoding="utf-8"))
                if st.get("modelo") == self.nome and st.get("n") == n_cont:
                    seek, anteriores = st["seek"], st["anteriores"]
                    segmentos, palavras = st["segmentos"], st["palavras"]
                    log_fn("retomando transcrição em %.1fs" % (seek * HOP / SR))
            except Exception:
                pass
        rng = np.random.default_rng(0)
        t_janela = None
        while seek < n_cont:
            if orcamento and t_janela and (time.time() - t_ini) + t_janela * 1.15 > orcamento:
                if estado:
                    json.dump({"modelo": self.nome, "n": n_cont, "seek": seek, "anteriores": anteriores,
                               "segmentos": segmentos, "palavras": palavras}, open(estado, "w", encoding="utf-8"))
                return {"parcial": True, "progresso": seek / max(1, n_cont)}
            t_j0 = time.time()
            tam = min(N_FRAMES, n_cont - seek)
            if tam < 10:
                break
            seg = mel[:, seek:seek + tam]
            if tam < N_FRAMES:
                seg = np.pad(seg, ((0, 0), (0, N_FRAMES - tam)))
            off_t = seek * HOP / SR
            # pula janelas sem fala (evita alucinações)
            if fala is not None and not any(b > off_t and a < off_t + tam * HOP / SR for a, b in fala):
                seek += tam
                continue
            xa = self.codificar(seg)
            self.preparar_cruzada(xa)
            res = None
            for T in (0.0, 0.2, 0.4, 0.6, 0.8):
                pr = (voc + anteriores[-(223 - len(voc)):]) if T < 0.5 else voc
                toks, lp, ns = self._decodificar(lang, pr, T, rng)
                txt = tk.texto(toks)
                res = (toks, lp, ns)
                if ns > 0.6 and lp < -1.0:
                    break
                if _razao_compressao(txt) <= 2.4 and lp >= -1.0:
                    break
            toks, lp, ns = res
            if ns > 0.6 and lp < -1.0:
                seek += tam
                continue
            ts = [t >= tk.ts0 for t in toks]
            cons = [i + 1 for i in range(len(toks) - 1) if ts[i] and ts[i + 1]]
            final_unico = len(toks) >= 2 and (not ts[-2]) and ts[-1]
            segs_j = []
            if cons:
                fatias = cons + ([len(toks)] if final_unico else [])
                ult = 0
                for f in fatias:
                    pedaco = toks[ult:f]
                    if pedaco and pedaco[0] >= tk.ts0 and pedaco[-1] >= tk.ts0:
                        a = off_t + (pedaco[0] - tk.ts0) * 0.02
                        b = off_t + (pedaco[-1] - tk.ts0) * 0.02
                        segs_j.append((a, b, [t for t in pedaco if t < tk.eot]))
                    ult = f
                if final_unico:
                    avanco = tam
                else:
                    avanco = (toks[ult - 1] - tk.ts0) * 2 if ult > 0 else tam
            else:
                tts = [t for t in toks if t >= tk.ts0]
                dur = tam * HOP / SR
                if tts and tts[-1] != tk.ts0:
                    dur = (tts[-1] - tk.ts0) * 0.02
                segs_j.append((off_t, off_t + dur, [t for t in toks if t < tk.eot]))
                avanco = tam
            avanco = max(1, min(avanco, tam)) if avanco > 0 else tam
            # limita os segmentos ao fim real do áudio desta janela
            fim_j = off_t + tam * HOP / SR
            segs_j = [(min(a, fim_j), min(max(b, a + 0.1), fim_j), tt) for (a, b, tt) in segs_j]
            # palavras com DTW na janela
            texto_j = [t for (_, _, tt) in segs_j for t in tt]
            try:
                ws = self._alinhar(lang, texto_j, tam)
            except Exception as ex:  # nunca derruba a transcrição por causa do alinhamento
                log_fn("alinhamento falhou (%s) — usando tempos proporcionais" % ex)
                ws = []
            ws_abs = [dict(w, i=w["i"] + off_t, f=w["f"] + off_t) for w in ws]
            # distribui palavras pelos segmentos e limita aos seus tempos
            k = 0
            for (a, b, tt) in segs_j:
                txt = tk.texto(tt).strip()
                n_pal_seg = len([x for x in re.split(r"\s+", txt) if x])
                if not txt:
                    continue
                if fala is not None and b > a:
                    sobre = sum(max(0.0, min(b, y) - max(a, x)) for x, y in fala)
                    if sobre / (b - a) < 0.2:
                        k += n_pal_seg
                        continue
                if any(h in txt.lower() for h in ALUCINACOES) and (lp < -0.6 or fala is not None):
                    k += n_pal_seg
                    continue
                n_pal = len([x for x in re.split(r"\s+", txt) if x])
                mine = ws_abs[k:k + n_pal]
                k += n_pal
                if len(mine) != n_pal or not mine:
                    mine = _proporcional(txt, a, b)
                for w in mine:
                    w["i"] = min(max(w["i"], a - 0.1), b)
                    w["f"] = min(max(w["f"], w["i"] + 0.04), b + 0.2)
                    w.pop("toks", None)
                segmentos.append({"i": round(a, 2), "f": round(b, 2), "texto": txt})
                palavras.extend({"p": w["p"], "i": round(w["i"], 3), "f": round(w["f"], 3),
                                 "seg": len(segmentos) - 1} for w in mine)
            anteriores += toks
            seek += avanco
            dt = time.time() - t_j0
            t_janela = dt if t_janela is None else max(t_janela, dt)
            log_fn("  transcrito até %s (%.0f%%)" % ("%d:%04.1f" % divmod(min(seek, n_cont) * HOP / SR, 60),
                                                    100.0 * min(seek, n_cont) / max(1, n_cont)))
        palavras = _ajustar_duracoes(palavras)
        if estado:
            try:
                import os as _os
                _os.remove(estado)
            except Exception:
                pass
        log_fn("transcrição: %d segmentos, %d palavras em %.1fs" % (len(segmentos), len(palavras), time.time() - t_ini))
        return {"palavras": palavras, "segmentos": segmentos, "modelo": "whisper-" + self.nome}


def _proporcional(txt, a, b):
    ws = [x for x in re.split(r"\s+", txt) if x]
    tot = sum(len(w) for w in ws) or 1
    out = []
    acc = a
    for w in ws:
        d = (b - a) * len(w) / tot
        out.append({"p": w, "i": acc, "f": acc + d})
        acc += d
    return out


def _ajustar_duracoes(ws):
    if not ws:
        return ws
    dur = np.array([w["f"] - w["i"] for w in ws])
    nz = dur[dur > 0]
    med = min(0.7, float(np.median(nz))) if len(nz) else 0.3
    mx = med * 2.2
    for k, w in enumerate(ws):
        if w["f"] - w["i"] > mx:
            if re.search(r"[\.!\?…,]$", w["p"]) or k == len(ws) - 1:
                w["f"] = w["i"] + mx
            elif k + 1 < len(ws):
                w["i"] = max(w["i"], w["f"] - mx)
        if k + 1 < len(ws) and w["f"] > ws[k + 1]["i"]:
            w["f"] = max(w["i"] + 0.02, ws[k + 1]["i"])
    return ws


def _dtw(x):
    """DTW (igual ao do Whisper): retorna (índices de texto, índices de tempo)."""
    N, M = x.shape
    custo = np.full((N + 1, M + 1), np.inf)
    rastro = -np.ones((N + 1, M + 1), np.int8)
    custo[0, 0] = 0
    x = x.astype(np.float64)
    for j in range(1, M + 1):
        c_ant = custo[:, j - 1]
        col = custo[:, j]
        xj = x[:, j - 1]
        for i in range(1, N + 1):
            c0 = c_ant[i - 1]
            c1 = col[i - 1]
            c2 = c_ant[i]
            if c0 < c1 and c0 < c2:
                c, t = c0, 0
            elif c1 < c0 and c1 < c2:
                c, t = c1, 1
            else:
                c, t = c2, 2
            col[i] = xj[i - 1] + c
            rastro[i, j] = t
    i, j = N, M
    rastro[0, :] = 2
    rastro[:, 0] = 1
    res = []
    while i > 0 or j > 0:
        res.append((i - 1, j - 1))
        t = rastro[i, j]
        if t == 0:
            i -= 1
            j -= 1
        elif t == 1:
            i -= 1
        else:
            j -= 1
    r = np.array(res[::-1])
    return r[:, 0], r[:, 1]
