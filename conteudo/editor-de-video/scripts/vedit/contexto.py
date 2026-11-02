"""Contexto de renderização: lê o plano, monta estilo, mídias, linha do tempo, transcrição e efeitos,
e compõe cada quadro."""
import json
import math
import os
import re

from PIL import Image

from . import grafico as G
from .estilos import montar_estilo
from .linha import Linha
from .tempo import clamp
from .util import ErroPlano, aviso, ler_json, log, normalizar_chaves, num, sem_acento, sondar

FORMATOS = {"9:16": (1080, 1920), "vertical": (1080, 1920), "reels": (1080, 1920), "tiktok": (1080, 1920),
            "shorts": (1080, 1920), "stories": (1080, 1920), "16:9": (1920, 1080), "horizontal": (1920, 1080),
            "youtube": (1920, 1080), "1:1": (1080, 1080), "quadrado": (1080, 1080), "4:5": (1080, 1350),
            "feed": (1080, 1350), "4:3": (1440, 1080), "3:4": (1080, 1440)}


def carregar_plano(caminho_ou_dict, base_dir=None):
    if isinstance(caminho_ou_dict, dict):
        bruto = caminho_ou_dict
        base_dir = base_dir or os.getcwd()
    else:
        bruto = ler_json(caminho_ou_dict)
        base_dir = base_dir or os.path.dirname(os.path.abspath(caminho_ou_dict))
    plano = normalizar_chaves(bruto, raiz=True)
    return plano, base_dir


class Contexto:
    def __init__(self, plano, base_dir, rascunho=False, escala_rascunho=0.5):
        from .efeitos import criar_efeito, FASES  # registra todos os efeitos
        from .midia import Biblioteca

        self.plano = plano
        self.base_dir = base_dir
        self.rascunho = rascunho
        self.escala_rascunho = escala_rascunho
        saida = plano.get("saida") or {}
        if isinstance(saida, str):
            saida = {"arquivo": saida}
        self.saida = saida
        self.estilo = montar_estilo(plano.get("estilo"))
        G.PADROES_TEXTO.update(marca_solida=bool(self.estilo.get("marca_solida", True)),
                               destaque_fonte=bool(self.estilo.get("destaque_fonte", False)))
        midias = dict(plano.get("midias") or {})
        # atalhos comuns
        for k in ("video", "principal", "bruto", "midia", "arquivo_video"):
            if k in plano and isinstance(plano[k], str) and "principal" not in midias:
                midias["principal"] = plano[k]
        fps_pedido = saida.get("fps", 30)
        self.bib = Biblioteca(midias, base_dir, 30)
        principal = None
        if "principal" in self.bib.mapa:
            principal = self.bib.mapa["principal"]
        elif midias:
            principal = list(self.bib.mapa.values())[0]
            self.bib.mapa.setdefault("principal", principal)
        self.info_principal = sondar(principal) if principal and os.path.exists(principal) else None

        # formato de saída
        fmt = str(saida.get("formato", "9:16")).lower()
        if fmt in ("original", "mesmo", "auto") and self.info_principal and self.info_principal.get("largura"):
            iw, ih = self.info_principal["largura"], self.info_principal["altura"]
            k = 1920.0 / max(iw, ih) if max(iw, ih) > 1920 else 1.0
            W, H = int(iw * k) // 2 * 2, int(ih * k) // 2 * 2
        elif re.match(r"^\d+x\d+$", fmt):
            W, H = map(int, fmt.split("x"))
        else:
            W, H = FORMATOS.get(fmt, (1080, 1920))
        W = int(num(saida.get("largura"), W))
        H = int(num(saida.get("altura"), H))
        if rascunho:
            W, H = int(W * escala_rascunho) // 2 * 2, int(H * escala_rascunho) // 2 * 2
        self.W, self.H = W - W % 2, H - H % 2
        self.s = min(self.W, self.H) / 1080.0
        if str(fps_pedido).lower() in ("original", "auto") and self.info_principal:
            f = self.info_principal.get("fps") or 30
            fps = 30 if 29 < f < 31 else 25 if 24.5 < f < 25.5 else 24 if 23 < f < 24.5 else 60 if 59 < f < 61 else 30
        else:
            fps = num(fps_pedido, 30)
        self.fps = max(10, min(60, fps))
        self.bib.fps = self.fps
        audio = plano.get("audio") or {}
        self.audio_cfg = audio
        self.sons_auto = bool(audio.get("sons_auto", audio.get("efeitos_sonoros", plano.get("sons_auto", True))))

        # linha do tempo
        specs = plano.get("linha_do_tempo")
        cs = plano.get("cortar_silencios") or (plano.get("cortes_automaticos"))
        if (specs in (None, "auto", "") or specs == []) and cs:
            from .analise import cortes_por_silencio

            cfg = cs if isinstance(cs, dict) else {}
            ref = cfg.get("midia", "principal")
            cam = self.bib.caminho(ref)
            pals = None
            arq_t = cam + ".transcricao.json"
            if os.path.exists(arq_t):
                try:
                    pals = json.load(open(arq_t, encoding="utf-8")).get("palavras") or None
                except Exception:
                    pals = None
            segs = cortes_por_silencio(cam, silencio_min=num(cfg.get("silencio_min"), 0.45),
                                       margem=num(cfg.get("margem"), 0.12), palavras=pals)
            remover = cfg.get("remover") or []  # trechos [ini, fim] (tempo bruto) para tirar (erros, repetições)
            for a_, b_ in remover:
                a_, b_ = num(a_), num(b_)
                novo = []
                for x, y in segs:
                    if b_ <= x or a_ >= y:
                        novo.append((x, y))
                    else:
                        if a_ > x:
                            novo.append((x, a_))
                        if b_ < y:
                            novo.append((b_, y))
                segs = [(x, y) for x, y in novo if y - x > 0.12]
            specs = [{"midia": ref, "de": a, "ate": b} for a, b in segs]
            log("cortes automáticos: %d trechos" % len(specs))
        elif specs in (None, "auto", ""):
            specs = [{"midia": "principal"}]
        if isinstance(specs, dict):
            specs = [specs]
        self._cache_rostos = {}
        self._cartoes = {}
        self.linha = Linha(specs, self)
        self.duracao = self.linha.duracao
        dmax = saida.get("duracao_max")
        if dmax:
            self.duracao = min(self.duracao, num(dmax, self.duracao))

        # transcrição (palavras em tempo de saída)
        self.palavras = []
        self._carregar_transcricao()

        # efeitos
        self.efeitos = []
        for i, sp in enumerate(plano.get("efeitos") or []):
            if not isinstance(sp, dict):
                continue
            if sp.get("desativado") or sp.get("ativo") is False:
                continue
            try:
                ef = criar_efeito(sp, self)
            except ErroPlano as ex:
                raise ErroPlano("efeitos[%d] (%s): %s" % (i, sp.get("tipo"), ex))
            ef.ordem = i
            self.efeitos.append(ef)
            if ef.fase == "camera":
                self.linha.registrar_camera(ef)
        self.efeitos.sort(key=lambda e: (FASES.get(e.fase, 3), e.ordem))
        self.efeitos_quadro = [e for e in self.efeitos if e.fase != "camera"]

    # ---------------------------------------------------------------- transcrição
    def _carregar_transcricao(self):
        p = self.plano.get("transcricao")
        cand = []
        if isinstance(p, str):
            cand.append(p if os.path.isabs(p) else os.path.join(self.base_dir, p))
        prin = self.bib.mapa.get("principal")
        if prin:
            cand.append(prin + ".transcricao.json")
            cand.append(os.path.join(os.path.dirname(prin), "transcricao.json"))
        cand.append(os.path.join(self.base_dir, "transcricao.json"))
        arq = next((c for c in cand if c and os.path.exists(c)), None)
        if not arq:
            return
        try:
            d = json.load(open(arq, encoding="utf-8"))
        except Exception as ex:
            aviso("transcrição ilegível (%s): %s" % (arq, ex))
            return
        ref = "principal"
        brutas = d.get("palavras") or []
        corr = self.plano.get("correcoes") or {}
        brutas = aplicar_correcoes(brutas, corr)
        out = []
        for w in brutas:
            a = self.linha.mapear_bruto(num(w.get("i")), ref)
            b = self.linha.mapear_bruto(num(w.get("f")), ref)
            if a is None:
                continue
            ia = self.linha.mapear_bruto(num(w.get("i")) + 0.0001, ref)
            # palavra precisa começar dentro de um trecho mantido
            bloco = self.linha.bloco_em(a + 1e-4)
            bl = self.linha.blocos[bloco]
            if not (bl.tipo == "video" and bl.de - 0.05 <= num(w.get("i")) <= bl.ate + 0.05):
                continue
            if b is None or b < a:
                b = a + max(0.08, num(w.get("f")) - num(w.get("i")))
            fim_bloco = self.linha.inicios[bloco] + bl.duracao
            b = min(b, fim_bloco)
            out.append({"p": w.get("p", ""), "i": a, "f": max(a + 0.05, b), "seg": w.get("seg", 0)})
        self.palavras = out
        self.arquivo_transcricao = arq

    def buscar_palavra(self, alvo, n=1, apos=0.0):
        """Tempo (início, fim) da n-ésima ocorrência da palavra/frase alvo no tempo de saída."""
        def norm(s):
            return re.sub(r"[^\w]", "", sem_acento(s).lower())
        seq = [norm(x) for x in str(alvo).split() if norm(x)]
        if not seq:
            return None
        ws = [norm(w["p"]) for w in self.palavras]
        achados = []
        for i in range(len(ws) - len(seq) + 1):
            if all(ws[i + k] == seq[k] or (len(seq[k]) > 3 and ws[i + k].startswith(seq[k])) for k in range(len(seq))):
                if self.palavras[i]["i"] >= apos:
                    achados.append((self.palavras[i]["i"], self.palavras[i + len(seq) - 1]["f"]))
        if len(achados) >= n:
            return achados[n - 1]
        return None

    def resolver_tempo(self, v, fim=False):
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("inicio", "comeco", "start"):
                return 0.0
            if s in ("fim", "final", "end"):
                return self.duracao
            if re.match(r"^-?[\d:\.,]+s?$", s):
                return num(s)
            # texto livre = palavra
            v = {"palavra": v}
        if isinstance(v, dict):
            aj = num(v.get("ajuste", v.get("deslocamento", 0.0)), 0.0)
            if "palavra" in v or "frase" in v:
                if not self.palavras:
                    raise ErroPlano("tempo por palavra ('%s') exige transcrição — rode 'editor.py analisar' antes."
                                    % (v.get("palavra") or v.get("frase")))
                r = self.buscar_palavra(v.get("palavra") or v.get("frase"), int(num(v.get("n", v.get("ocorrencia", 1)), 1)),
                                        num(v.get("apos"), 0.0))
                if r is None:
                    import difflib
                    cands = difflib.get_close_matches(str(v.get("palavra") or v.get("frase")).lower(),
                                                      list({w["p"].lower().strip(".,!?") for w in self.palavras}), n=5)
                    raise ErroPlano("palavra '%s' não encontrada na transcrição (parecidas: %s)"
                                    % (v.get("palavra") or v.get("frase"), ", ".join(cands) or "—"))
                usar_fim = bool(v.get("fim_palavra")) if "fim_palavra" in v else fim
                return (r[1] if usar_fim else r[0]) + aj
            if "bruto" in v:
                t = self.linha.mapear_bruto(num(v["bruto"]), v.get("midia"))
                if t is None:
                    raise ErroPlano("tempo bruto %.2fs não está em nenhum trecho mantido" % num(v["bruto"]))
                return t + aj
            if "bloco" in v:
                i = int(num(v["bloco"]))
                i = max(0, min(i, len(self.linha.blocos) - 1))
                if v.get("fim_bloco"):
                    return self.linha.inicios[i] + self.linha.blocos[i].duracao + aj
                return self.linha.inicios[i] + num(v.get("t"), 0.0) + aj
            if "t" in v:
                return num(v["t"]) + aj
        raise ErroPlano("tempo inválido: %r" % (v,))

    # ---------------------------------------------------------------- rostos / enquadramento
    def foco_rosto(self, ref, s, asp_o, asp_s):
        caminho = self.bib.caminho(ref)
        if caminho not in self._cache_rostos:
            from .analise import trilha_rostos

            self._cache_rostos[caminho] = trilha_rostos(caminho)
        tr = self._cache_rostos[caminho]
        if not tr:
            return (0.5, 0.45)
        # interpolação linear na trilha suavizada [(t, x, y, tam)]
        if s <= tr[0][0]:
            p = tr[0]
        elif s >= tr[-1][0]:
            p = tr[-1]
        else:
            lo, hi = 0, len(tr) - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if tr[mid][0] <= s:
                    lo = mid
                else:
                    hi = mid
            a, b = tr[lo], tr[hi]
            k = (s - a[0]) / max(1e-6, b[0] - a[0])
            p = tuple(a[j] + (b[j] - a[j]) * k for j in range(4))
        return (p[1], min(0.75, p[2] + 0.06))

    def rosto_saida(self, t):
        """Rosto no quadro de saída em t: (cx, cy, altura) normalizados (aproximado, sem zoom), ou None."""
        try:
            i = self.linha.bloco_em(t)
            b = self.linha.blocos[i]
            if b.tipo != "video" or not b.midia or self.bib.e_imagem(b.midia):
                return None
            s = b.tempo_fonte(t - self.linha.inicios[i])
            caminho = self.bib.caminho(b.midia)
            if caminho not in self._cache_rostos:
                from .analise import trilha_rostos
                self._cache_rostos[caminho] = trilha_rostos(caminho)
            tr = self._cache_rostos[caminho]
            if not tr:
                return None
            p = min(tr, key=lambda a: abs(a[0] - s))
            if abs(p[0] - s) > 1.5:
                return None
            cx, cy, tam = p[1], p[2], p[3]
            inf = sondar(caminho)
            asp_s = inf["largura"] / max(1, inf["altura"])
            asp_o = self.W / self.H
            if asp_s > asp_o * 1.03:  # laterais cortadas, enquadramento segue o rosto
                cw = asp_o / asp_s
                x0 = min(max(cx - cw / 2, 0.0), 1.0 - cw)
                return ((cx - x0) / cw, cy, tam)
            if asp_s < asp_o * 0.97:
                return None
            return (cx, cy, tam)
        except Exception:
            return None

    def areas_ocupadas(self, t, exceto=None, tipos_ignorar=("legendas",)):
        """Caixas ocupadas por efeitos ativos em t (para desviar legendas/títulos)."""
        out = []
        for e in getattr(self, "efeitos", []):
            if e is exceto or getattr(e, "nome", "") in tipos_ignorar or not e.ativo(t):
                continue
            try:
                a = e.area(t)
            except Exception:
                a = None
            if a:
                out.append(a)
        return out

    # ---------------------------------------------------------------- cor
    def aplicar_grade(self, img, spec, intensidade=None):
        from .efeitos.cor import aplicar_look

        if isinstance(spec, dict):
            return aplicar_look(img, spec.get("preset", "natural"), num(spec.get("intensidade"), 1.0) if intensidade is None else intensidade, spec)
        return aplicar_look(img, str(spec), 1.0 if intensidade is None else intensidade, {})

    # ---------------------------------------------------------------- cartões de tela cheia
    def render_cartao(self, bloco, u):
        from .efeitos import criar_efeito

        k = bloco.idx
        if k not in self._cartoes:
            sp = dict(bloco.cartao) if isinstance(bloco.cartao, dict) else {"texto": str(bloco.cartao)}
            sp.setdefault("tipo", "titulo")
            sp["inicio"] = 0.0
            sp["fim"] = bloco.duracao
            sp.setdefault("posicao", "centro")
            sp.setdefault("tamanho", 96)
            sp.setdefault("saida_anim", "nenhuma")
            sp["som"] = False
            fundo = bloco.cor_fundo or sp.get("fundo_cena")
            self._cartoes[k] = (criar_efeito(sp, self), fundo)
        ef, fundo = self._cartoes[k]
        if fundo and isinstance(fundo, str) and (fundo.startswith("#") or fundo in G.NOMES_CORES):
            base = Image.new("RGB", (self.W, self.H), G.cor(fundo, self.estilo)[:3])
        elif fundo and isinstance(fundo, str) and fundo in self.bib.mapa:
            base = G.cobrir(self.bib.quadro_pil(fundo, u), self.W, self.H)
        else:
            if "_fundo_cena" not in self.__dict__:
                self._fundo_cena = G.fundo_cena(self.W, self.H, self.estilo)
            base = self._fundo_cena.copy()
        return ef.aplicar(base, u)

    # ---------------------------------------------------------------- fontes de quadro para efeitos
    def quadro_fonte(self, fonte, t, t0, base, tamanho=None):
        """fonte: 'principal' | nome de mídia | {'midia','de','velocidade','ate','loop'} | {'imagem'} |
        {'texto', 'fundo'} | {'cor'} | {'bruto': s}."""
        if fonte is None or fonte == "principal" or (isinstance(fonte, dict) and fonte.get("principal")):
            return base
        if isinstance(fonte, str):
            fonte = {"midia": fonte}
        if "cor" in fonte and len(fonte) <= 2 and "midia" not in fonte:
            return Image.new("RGB", (self.W, self.H), G.cor(fonte["cor"], self.estilo)[:3])
        if "texto" in fonte and "midia" not in fonte and "imagem" not in fonte:
            return self._cartao_texto(fonte)
        if "bruto" in fonte:
            fonte = dict(fonte, midia=fonte.get("midia", "principal"), de=fonte["bruto"])
        ref = fonte.get("midia") or fonte.get("imagem")
        if self.bib.e_imagem(ref):
            return self.bib.imagem(ref).convert("RGB")
        de = num(fonte.get("de"), 0.0)
        vel = num(fonte.get("velocidade"), 1.0)
        dur = sondar(self.bib.caminho(ref))["duracao"]
        ate = num(fonte.get("ate"), dur) if fonte.get("ate") is not None else dur
        s = de + max(0.0, t - t0) * vel
        if s > ate:
            if fonte.get("loop", True) and ate - de > 0.3:
                s = de + (s - de) % (ate - de)
            else:
                s = ate
        tam = None
        if tamanho:
            inf = sondar(self.bib.caminho(ref))
            k = max(tamanho[0] / max(1, inf["largura"]), tamanho[1] / max(1, inf["altura"]))
            if k < 0.7:
                tam = (max(2, int(inf["largura"] * k * 1.15) // 2 * 2), max(2, int(inf["altura"] * k * 1.15) // 2 * 2))
        return self.bib.quadro_pil(ref, s, chave="ef%d" % id(fonte), tamanho=tam)

    def _cartao_texto(self, fonte):
        chave = json.dumps(fonte, sort_keys=True, ensure_ascii=False)
        if chave not in self._cartoes:
            e = self.estilo
            W, H = self.W, self.H
            fundo = fonte.get("fundo")
            if fundo:
                base = Image.new("RGB", (W, H), G.cor(fundo, e)[:3])
            else:
                base = G.fundo_cena(W, H, e)
            cor_t = fonte.get("cor_texto") or ("texto_escuro" if fundo and G.luminancia(G.cor(fundo, e)) > 0.6 else "texto")
            r = G.render_texto(fonte["texto"], e.get(fonte.get("fonte", "fonte_titulo"), e["fonte_titulo"]),
                               num(fonte.get("tamanho"), 84) * self.s, G.cor(cor_t, e), largura_max=W * 0.84,
                               cor_destaque=G.cor("destaque", e), fonte_destaque=e["fonte_destaque"],
                               marca_solida=bool(e.get("marca_solida", True)), entrelinha=1.04)
            G.colar(base, r.img, W / 2, H / 2)
            self._cartoes[chave] = base
        return self._cartoes[chave]

    # ---------------------------------------------------------------- quadro final
    def quadro(self, t):
        img = self.linha.quadro(t)
        for e in self.efeitos_quadro:
            if e.ativo(t):
                try:
                    img = e.aplicar(img, t)
                except Exception as ex:  # um efeito com problema não derruba o render
                    if not getattr(e, "_avisado", False):
                        aviso("efeito '%s' falhou em t=%.2f: %s" % (e.nome, t, ex))
                        import traceback
                        traceback.print_exc()
                        e._avisado = True
                if img.mode != "RGB":
                    img = img.convert("RGB")
        return img

    def todos_sons(self):
        out = []
        for e in self.efeitos:
            try:
                out.extend(e.sons())
            except Exception as ex:
                aviso("sons de '%s': %s" % (e.nome, ex))
        for s in self.plano.get("sons") or []:
            try:
                out.append((self.resolver_tempo(s.get("t", s.get("inicio", 0))), s.get("tipo", "pop"),
                            num(s.get("volume"), 0.5)))
            except Exception as ex:
                aviso("som inválido %r: %s" % (s, ex))
        return out


def aplicar_correcoes(palavras, corr):
    """Substitui palavras/frases erradas da transcrição. corr: {"errado": "certo", "duas palavras": "uma"}."""
    if not corr:
        return palavras
    import copy

    def norm(s):
        return re.sub(r"[^\w]", "", sem_acento(s).lower())

    ws = copy.deepcopy(palavras)
    for errado, certo in corr.items():
        seq = [norm(x) for x in str(errado).split() if norm(x)]
        if not seq:
            continue
        i = 0
        while i <= len(ws) - len(seq):
            if all(norm(ws[i + k]["p"]) == seq[k] for k in range(len(seq))):
                pont = re.sub(r"^.*?([\.,!?;:…]*)$", r"\1", ws[i + len(seq) - 1]["p"])
                novo = {"p": str(certo) + pont, "i": ws[i]["i"], "f": ws[i + len(seq) - 1]["f"],
                        "seg": ws[i].get("seg", 0)}
                partes = str(certo).split()
                if len(partes) > 1:
                    # distribui o tempo entre as palavras novas
                    a, b = novo["i"], novo["f"]
                    tot = sum(len(p) for p in partes)
                    acc = a
                    rep = []
                    for j, ptx in enumerate(partes):
                        d = (b - a) * len(ptx) / max(1, tot)
                        rep.append({"p": ptx + (pont if j == len(partes) - 1 else ""), "i": acc, "f": acc + d,
                                    "seg": novo["seg"]})
                        acc += d
                    ws[i:i + len(seq)] = rep
                    i += len(rep)
                else:
                    ws[i:i + len(seq)] = [novo]
                    i += 1
            else:
                i += 1
    return ws
