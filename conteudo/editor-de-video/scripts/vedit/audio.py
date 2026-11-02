"""Mixagem: voz dos trechos (com microfades nos cortes), áudio de b-rolls, música com ducking e efeitos sonoros
sintetizados (sem arquivos externos)."""
import os
import subprocess
import wave

import numpy as np

from .midia import extrair_audio
from .util import aviso, ffmpeg_bin, filtros, log, num, sondar

SR = 48000


# ------------------------------------------------------------------ síntese de efeitos sonoros
def _env(n, ataque, decaimento):
    t = np.arange(n) / SR
    a = np.clip(t / max(1e-4, ataque), 0, 1)
    return a * np.exp(-np.maximum(0, t - ataque) / max(1e-4, decaimento))


def _ruido_filtrado(d, f_ini, f_fim, largura=0.6, semente=1, env=None):
    """Ruído com banda passante móvel (síntese no domínio da frequência, quadro a quadro)."""
    n = int(d * SR)
    rng = np.random.default_rng(semente)
    N, hop = 1024, 256
    nfr = max(1, (n - N) // hop + 2)
    freqs = np.fft.rfftfreq(N, 1 / SR)
    out = np.zeros(n + N, np.float32)
    win = np.hanning(N).astype(np.float32)
    for k in range(nfr):
        p = k / max(1, nfr - 1)
        fc = f_ini * (f_fim / f_ini) ** p
        mag = np.exp(-0.5 * (np.log(np.maximum(freqs, 1) / fc) / largura) ** 2)
        fase = rng.uniform(0, 2 * np.pi, len(freqs))
        quadro = np.fft.irfft(mag * np.exp(1j * fase), N).astype(np.float32) * win
        out[k * hop:k * hop + N] += quadro
    out = out[:n]
    if env is not None:
        out *= env[:n]
    m = np.max(np.abs(out)) or 1
    return out / m


def _seno(freqs, d, amps=None, decs=None):
    n = int(d * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    amps = amps or [1.0] * len(freqs)
    decs = decs or [d] * len(freqs)
    for f, a, dc in zip(freqs, amps, decs):
        s += a * np.sin(2 * np.pi * f * t) * np.exp(-t / dc)
    return s


def _varredura(f0, f1, d, dec):
    n = int(d * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / max(1e-4, d / 4))
    fase = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(fase) * np.exp(-t / dec) * np.clip(t / 0.002, 0, 1)


def sintetizar(tipo, semente=0):
    tipo = str(tipo).lower()
    rng = np.random.default_rng(semente + 7)
    if tipo in ("whoosh", "woosh", "swoosh", "transicao", "passar"):
        d = 0.55
        n = int(d * SR)
        t = np.arange(n) / SR
        env = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2 * np.exp(-np.maximum(0, t - 0.3) / 0.15)
        s = _ruido_filtrado(d, 350, 2600, 0.55, semente, env) * 0.9
    elif tipo in ("swish", "rapido", "chicote"):
        d = 0.28
        n = int(d * SR)
        t = np.arange(n) / SR
        env = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 1.5
        s = _ruido_filtrado(d, 900, 5200, 0.5, semente, env) * 0.8
    elif tipo in ("pop", "bolha", "aparecer"):
        s = _varredura(950, 260, 0.14, 0.04) * 0.9
        clk = rng.normal(0, 1, int(0.004 * SR)) * np.linspace(1, 0, int(0.004 * SR))
        s[:len(clk)] += clk * 0.15
    elif tipo in ("gota", "bolha2"):
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        f = 400 + 1400 * np.clip(t / 0.05, 0, 1)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.035) * 0.8
    elif tipo in ("click", "clique", "toque"):
        n = int(0.03 * SR)
        s = rng.normal(0, 1, n) * np.exp(-np.arange(n) / (0.0025 * SR))
        s += 0.5 * np.sin(2 * np.pi * 2300 * np.arange(n) / SR) * np.exp(-np.arange(n) / (0.006 * SR))
        s *= 0.6
    elif tipo in ("tecla", "teclado", "digitar"):
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        s = rng.normal(0, 1, n) * np.exp(-t / 0.003) * 0.5
        s += 0.6 * np.sin(2 * np.pi * rng.uniform(160, 240) * t) * np.exp(-t / 0.012)
        s *= rng.uniform(0.6, 1.0)
    elif tipo in ("ding", "sino", "check", "certo"):
        s = _seno([1568, 3136, 4704, 6585], 1.0, [1, 0.35, 0.15, 0.06], [0.55, 0.3, 0.18, 0.1]) * 0.6
        s *= np.clip(np.arange(len(s)) / (0.002 * SR), 0, 1)
    elif tipo in ("sucesso", "conquista", "chime"):
        a = _seno([1318.5, 2637], 0.7, [1, 0.3], [0.35, 0.2])
        b = _seno([1975.5, 3951], 0.9, [1, 0.3], [0.45, 0.25])
        s = np.zeros(int(1.05 * SR))
        s[:len(a)] += a
        o = int(0.12 * SR)
        s[o:o + len(b)] += b
        s *= 0.5
    elif tipo in ("caixa", "dinheiro", "venda", "ka_ching", "moeda"):
        s = np.zeros(int(0.9 * SR))
        m = _seno([2637, 3520, 5274], 0.6, [1, 0.6, 0.3], [0.25, 0.18, 0.12])
        nz = rng.normal(0, 1, int(0.05 * SR)) * np.exp(-np.arange(int(0.05 * SR)) / (0.01 * SR)) * 0.4
        s[:len(m)] += m
        s[:len(nz)] += nz
        o = int(0.14 * SR)
        s[o:o + len(m)] += m * 0.9
        s *= 0.45
    elif tipo in ("impacto", "boom", "batida", "grave"):
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        f = 32 + 40 * np.exp(-t / 0.06)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35)
        nz = _ruido_filtrado(0.15, 180, 120, 0.8, semente) * np.exp(-np.arange(int(0.15 * SR)) / (0.03 * SR))
        s[:len(nz)] += nz * 0.5
        s = np.tanh(s * 1.6) * 0.8
    elif tipo in ("riser", "subida", "tensao"):
        d = 1.2
        n = int(d * SR)
        t = np.arange(n) / SR
        env = (t / d) ** 2
        s = _ruido_filtrado(d, 300, 6000, 0.45, semente, env) * 0.6
        f = 200 * (6 ** (t / d))
        s += 0.25 * np.sin(2 * np.pi * np.cumsum(f) / SR) * env
    elif tipo in ("glitch", "erro", "falha"):
        n = int(0.22 * SR)
        s = np.zeros(n)
        pos = 0
        while pos < n:
            L = int(rng.integers(200, 1600))
            f = rng.uniform(80, 1200)
            seg = np.sign(np.sin(2 * np.pi * f * np.arange(L) / SR)) * rng.uniform(0.2, 0.7)
            s[pos:pos + L] = seg[: max(0, min(L, n - pos))]
            pos += L + int(rng.integers(0, 600))
        s *= 0.45
    elif tipo in ("notificacao", "notif", "alerta"):
        a = _seno([880, 1760], 0.25, [1, 0.25], [0.12, 0.08])
        b = _seno([1318.5, 2637], 0.45, [1, 0.25], [0.2, 0.1])
        s = np.zeros(int(0.6 * SR))
        s[:len(a)] += a
        o = int(0.11 * SR)
        s[o:o + len(b)] += b
        s *= 0.5
    elif tipo in ("risco", "riscar", "caneta", "marcador"):
        d = 0.35
        n = int(d * SR)
        t = np.arange(n) / SR
        env = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 0.7
        s = _ruido_filtrado(d, 2500, 3500, 0.35, semente, env) * 0.35
    elif tipo in ("papel", "folha"):
        d = 0.45
        n = int(d * SR)
        t = np.arange(n) / SR
        env = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2 * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 9 * t)))
        s = _ruido_filtrado(d, 1800, 5000, 0.9, semente, env) * 0.45
    else:
        return sintetizar("pop", semente)
    s = np.asarray(s, np.float32)
    fade = min(len(s), int(0.004 * SR))
    if fade > 1:
        s[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return s


# ------------------------------------------------------------------ utilitários
def _colocar(dest, sinal, t, ganho=1.0):
    i = int(round(t * SR))
    if i >= len(dest) or len(sinal) == 0:
        return
    if i < 0:
        sinal = sinal[-i:]
        i = 0
    n = min(len(sinal), len(dest) - i)
    if sinal.ndim == 1:
        dest[i:i + n] += sinal[:n, None] * ganho
    else:
        dest[i:i + n] += sinal[:n] * ganho


def _microfade(a, ms=8):
    n = min(len(a) // 2, int(SR * ms / 1000))
    if n > 1:
        r = np.linspace(0, 1, n, dtype=np.float32)[:, None]
        a[:n] *= r
        a[-n:] *= r[::-1]
    return a


_CACHE_COMPLETO = {}


def _audio_completo(caminho):
    if caminho not in _CACHE_COMPLETO:
        _CACHE_COMPLETO[caminho] = extrair_audio(caminho, 0.0, None, SR, 2)
    return _CACHE_COMPLETO[caminho]


def _trecho(caminho, de, ate, vel):
    info = sondar(caminho)
    if not info.get("tem_audio"):
        return np.zeros((int(max(0, ate - de) / vel * SR), 2), np.float32)
    if abs(vel - 1.0) < 1e-3 and info["duracao"] < 1800:
        a = _audio_completo(caminho)
        return a[int(de * SR):int(ate * SR)].copy()
    return extrair_audio(caminho, de, ate, SR, 2, vel)


def _limpar_voz(a, reduzir_ruido=True):
    fl = filtros()
    chain = []
    if "highpass" in fl:
        chain.append("highpass=f=75")
    if reduzir_ruido and "afftdn" in fl:
        chain.append("afftdn=nf=-28")
    if "acompressor" in fl:
        chain.append("acompressor=threshold=0.09:ratio=2.5:attack=12:release=180:makeup=1.6")
    if not chain:
        return a
    cmd = [ffmpeg_bin(), "-v", "error", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-i", "-", "-af", ",".join(chain),
           "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    r = subprocess.run(cmd, input=np.ascontiguousarray(a, np.float32).tobytes(), capture_output=True)
    if r.returncode != 0:
        aviso("limpeza de voz falhou; seguindo sem ela")
        return a
    b = np.frombuffer(r.stdout, np.float32).reshape(-1, 2)
    out = np.zeros_like(a)
    out[:min(len(a), len(b))] = b[:len(a)]
    return out


def _envelope(a, janela=0.02):
    m = a.mean(axis=1) if a.ndim == 2 else a
    k = int(janela * SR)
    n = len(m) // k
    if n == 0:
        return np.zeros(1), k
    r = np.sqrt(np.mean(m[: n * k].reshape(n, k) ** 2, axis=1) + 1e-12)
    return r, k


def _ganho_ducking(voz, nivel=0.3, ataque=0.06, soltura=0.4):
    env, k = _envelope(voz)
    db = 20 * np.log10(env + 1e-9)
    piso = np.percentile(db, 20) if len(db) > 10 else -60
    ativo = db > max(-42, piso + 9)
    g = np.ones(len(env))
    atual = 1.0
    ka = np.exp(-0.02 / ataque)
    ks = np.exp(-0.02 / soltura)
    for i in range(len(env)):
        alvo = nivel if ativo[i] else 1.0
        coef = ka if alvo < atual else ks
        atual = alvo + (atual - alvo) * coef
        g[i] = atual
    xs = (np.arange(len(g)) + 0.5) * k
    return np.interp(np.arange(len(voz)), xs, g).astype(np.float32)


def _carregar_musica(caminho, dur, inicio=0.0):
    info = sondar(caminho)
    total = info["duracao"] or dur
    a = extrair_audio(caminho, inicio, None, SR, 2)
    n = int(dur * SR)
    if len(a) == 0:
        return np.zeros((n, 2), np.float32)
    if len(a) >= n:
        return a[:n]
    # repete com crossfade de 1s
    out = np.zeros((n, 2), np.float32)
    cf = min(int(1.0 * SR), len(a) // 3)
    pos = 0
    while pos < n:
        seg = a.copy()
        if pos > 0 and cf > 0:
            seg[:cf] *= np.linspace(0, 1, cf, dtype=np.float32)[:, None]
        if cf > 0:
            seg[-cf:] *= np.linspace(1, 0, cf, dtype=np.float32)[:, None]
        m = min(len(seg), n - pos)
        out[pos:pos + m] += seg[:m]
        pos += len(seg) - cf
    return out


def salvar_wav(caminho, a):
    a = np.clip(a, -1, 1)
    pcm = (a * 32767).astype("<i2")
    with wave.open(caminho, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ mixagem principal
def mixar(ctx, destino, de=None, ate=None):
    cfg = ctx.audio_cfg
    dur = ctx.duracao
    n = int(np.ceil(dur * SR)) + 1
    voz = np.zeros((n, 2), np.float32)
    lin = ctx.linha
    vol_voz = num(cfg.get("volume_voz", cfg.get("volume_principal")), 1.0)
    for i, b in enumerate(lin.blocos):
        if b.tipo != "video" or b.mudo or b.congelar:
            continue
        caminho = ctx.bib.caminho(b.midia)
        a = _trecho(caminho, b.de, b.ate, b.vel)
        alvo = int(round(b.duracao * SR))
        if len(a) > alvo:
            a = a[:alvo]
        a = _microfade(a, 6)
        _colocar(voz, a, lin.inicios[i], b.volume * vol_voz)
    if cfg.get("limpar_voz") or cfg.get("melhorar_voz"):
        voz = _limpar_voz(voz, reduzir_ruido=cfg.get("reduzir_ruido", True))
    # áudio próprio de efeitos (b-roll com som, etc.)
    extra = np.zeros_like(voz)
    for e in ctx.efeitos:
        for (t_out, ref, a0, a1, vel, vol) in (e.faixas_audio() if hasattr(e, "faixas_audio") else []):
            try:
                a = _trecho(ctx.bib.caminho(ref), a0, a1, vel)
                _colocar(extra, _microfade(a, 15), t_out, vol)
            except Exception as ex:
                aviso("áudio de efeito: %s" % ex)
        # efeitos que abafam a voz (ex.: b-roll com 'abafar_voz')
        for (ta, tb, g) in (e.abafar_voz() if hasattr(e, "abafar_voz") else []):
            i0, i1 = max(0, int(ta * SR)), min(n, int(tb * SR))
            if i1 <= i0:
                continue
            r = int(0.08 * SR)
            env = np.ones(n, np.float32)
            env[i0:i1] = g
            a0 = max(0, i0 - r)
            env[a0:i0] = np.linspace(1, g, i0 - a0)
            b1 = min(n, i1 + r)
            env[i1:b1] = np.linspace(g, 1, b1 - i1)
            voz *= env[:, None]
    mix = voz + extra
    # música
    mus = cfg.get("musica") or ctx.plano.get("musica")
    if mus:
        try:
            cam = ctx.bib.caminho(mus)
            m = _carregar_musica(cam, dur, num(cfg.get("musica_inicio"), 0.0))
            tem_voz = np.max(np.abs(voz)) > 0.01
            vol_m = num(cfg.get("volume_musica"), 0.16 if tem_voz else 0.75)
            fi, fo = num(cfg.get("fade_entrada_musica"), 0.8), num(cfg.get("fade_saida_musica"), 2.0)
            env = np.ones(len(m), np.float32)
            nfi, nfo = int(fi * SR), int(fo * SR)
            if nfi > 1:
                env[:nfi] = np.linspace(0, 1, nfi)
            if nfo > 1 and nfo < len(env):
                env[-nfo:] = np.linspace(1, 0, nfo)
            m *= env[:, None]
            if cfg.get("ducking", True) and tem_voz:
                g = _ganho_ducking(voz, num(cfg.get("nivel_ducking"), 0.35))
                m *= g[:len(m), None]
            mix[:len(m)] += m * vol_m
        except Exception as ex:
            aviso("música não aplicada: %s" % ex)
    # há conteúdo de verdade (voz/música)? Se só houver efeitos sonoros, não normalizar (senão eles estouram)
    rms = float(np.sqrt(np.mean(mix ** 2))) if len(mix) else 0.0
    ctx.audio_so_efeitos = rms < 10 ** (-48 / 20)
    # efeitos sonoros
    vol_sfx = num(cfg.get("volume_sons", cfg.get("volume_efeitos")), 1.0)
    if vol_sfx > 0:
        cache = {}
        for k, (t, tipo, vol) in enumerate(ctx.todos_sons()):
            if t is None or t < 0 or t > dur:
                continue
            chave = (tipo, k % 3)
            if chave not in cache:
                cache[chave] = sintetizar(tipo, k % 3)
            _colocar(mix, cache[chave], t, vol * vol_sfx)
    pico = float(np.max(np.abs(mix))) if len(mix) else 0
    if pico > 0.97:
        mix *= 0.97 / pico
    if de is not None:
        mix = mix[int(de * SR):int((ate if ate is not None else dur) * SR)]
    salvar_wav(destino, mix)
    return destino
