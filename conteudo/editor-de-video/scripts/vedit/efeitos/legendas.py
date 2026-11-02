"""Legendas automáticas sincronizadas por palavra (a partir da transcrição) em vários estilos."""
import bisect
import re

import numpy as np
from PIL import Image

from .. import grafico as G
from ..tempo import clamp, easing, volta
from ..util import aviso, num, sem_acento
from .base import Efeito, registrar

PONT_FIM = re.compile(r"[\.!\?…]$")
PONT_PAUSA = re.compile(r"[,;:]$")


@registrar("legendas", "legenda", "captions", "subtitles", "legendas_animadas", "legenda_automatica")
class Legendas(Efeito):
    """Legendas sincronizadas com a fala (usa a transcrição da análise).
    estilo: 'destaque' (palavra falada muda de cor e dá um pulinho — karaokê), 'caixa_palavra' (caixa colorida
    atrás da palavra falada), 'pop' (palavras surgem uma a uma), 'impacto' (CAIXA ALTA, 1–3 palavras, contorno),
    'caixa' (bloco com fundo), 'palavra' (uma palavra por vez, grande), 'minimal' (discreta).
    max_palavras (padrão 4; impacto 3), linhas (padrão 2), posicao (padrão: 70% da altura no vertical), tamanho
    (64), fonte, cor, cor_destaque, contorno (0; impacto 9), maiusculas, pulo (true: a palavra falada cresce um
    pouco), desviar (true: sobe/desce para não bater em cartões, CTAs e prints), fundo_auto (true: caixa escura
    quando o fundo atrás é claro), destacar: ['IA', 'Claude'] (sempre na cor de destaque), pontuacao (false =
    remove . e ,),
    ocultar: [[ini, fim], ...] (esconde nesses intervalos), texto: [{texto, inicio, fim}] (legenda manual quando
    não há transcrição). Por padrão cobre o vídeo todo."""
    fase = "legenda"
    duracao_padrao = 1e6
    som_entrada = None

    def preparar(self):
        ctx = self.ctx
        base = dict(self.e.get("legenda", {}))
        self.estilo = str(self.param("estilo", base.get("estilo", "destaque")))
        if self.spec.get("inicio") is None:
            self.t0 = 0.0
        if self.spec.get("fim") is None and self.spec.get("duracao") is None:
            self.t1 = ctx.duracao + 1
        mp_pad = 3 if self.estilo == "impacto" else 1 if self.estilo == "palavra" else 4
        self.max_p = int(num(self.param("max_palavras"), mp_pad))
        self.linhas = int(num(self.param("linhas"), 1 if self.estilo in ("impacto", "palavra") else 2))
        tam_pad = base.get("tamanho", 64)
        if self.estilo == "palavra":
            tam_pad = 112
        elif self.estilo == "minimal":
            tam_pad = min(tam_pad, 48)
        self.tam = self.px(num(self.param("tamanho"), tam_pad))
        self.fonte = self.e.get(self.param("fonte", "fonte_legenda"), self.param("fonte", "fonte_legenda"))
        if self.estilo == "minimal" and self.param("fonte") is None:
            self.fonte = self.e.get("fonte_titulo")
        # a configuração de legenda do estilo vale para o estilo de legenda dele; outro estilo pedido usa o natural
        natural = self.estilo in ("impacto", "palavra")
        self.maius = bool(self.param("maiusculas", base.get("maiusculas", natural) if base.get("estilo") == self.estilo else natural))
        self.cor_t = self.cor(self.param("cor", base.get("cor", "#FFFFFF")))
        cd = self.param("cor_destaque", base.get("cor_destaque") or "destaque")
        self.cor_d = self.cor(cd)
        cont_pad = base.get("contorno", 0)
        if self.estilo == "impacto":
            cont_pad = max(cont_pad, 9)
        if self.estilo in ("caixa", "minimal", "caixa_palavra"):
            cont_pad = 0
        self.contorno = self.px(num(self.param("contorno"), cont_pad))
        self.caixa = self.param("cor_caixa", base.get("caixa", "#000000C2"))
        self.destacar = {self._n(x) for x in (self.param("destacar") or [])}
        self.pont = bool(self.param("pontuacao", False))
        self.pulo = bool(self.param("pulo", base.get("pulo", True))) and self.estilo in ("destaque", "caixa_palavra", "pop")
        self.brilho = bool(self.param("brilho", base.get("brilho", False)))
        self.desviar = bool(self.param("desviar", True))        # foge de cartões/CTAs/prints na mesma altura
        self.fundo_auto = bool(self.param("fundo_auto", True))  # caixa escura quando o fundo atrás é claro
        self.ocultar = [(ctx.resolver_tempo(a), ctx.resolver_tempo(b)) for a, b in (self.param("ocultar") or [])]
        for i, b in enumerate(ctx.linha.blocos):
            if b.tipo == "cartao":
                self.ocultar.append((ctx.linha.inicios[i], ctx.linha.inicios[i] + b.duracao))
        self._auto_ocultar = False
        if self.spec.get("posicao") is None:
            self.x = self.W / 2
            self.y = self.H * num(base.get("altura"), 0.70) if self.H > self.W else self.H * 0.84
        else:
            self.x, self.y = self.pos(None, "baixo")
        self.larg_max = self.W * num(self.param("largura"), 0.86)
        # sombra: contato + difusa (mais forte que a dos títulos: legenda precisa ler em qualquer fundo)
        k = 1.0 if self.estilo != "minimal" else 0.8
        self.sombras = [{"raio": self.px(2.5), "dy": self.px(1.5), "opacidade": 0.55 * k},
                        {"raio": self.px(16), "dy": self.px(5), "opacidade": 0.5 * k}]
        if self.contorno > 0:
            self.sombras = [{"raio": self.px(12), "dy": self.px(5), "opacidade": 0.5}]
        if self.brilho:
            self.sombras.append({"raio": self.px(22), "dy": 0, "opacidade": 0.55, "cor": self.cor_d})
        palavras = self._palavras()
        self.chunks = self._agrupar(palavras)
        self.inicios = [c["i"] for c in self.chunks]
        self._cache = {}
        if not self.chunks:
            aviso("legendas: nenhuma palavra disponível (rode 'analisar' com transcrição ou passe 'texto')")

    @staticmethod
    def _n(s):
        return re.sub(r"[^\w]", "", sem_acento(str(s)).lower())

    def _palavras(self):
        manual = self.param("texto")
        if manual:
            out = []
            for sg in manual:
                a = self.ctx.resolver_tempo(sg.get("inicio", 0))
                b = self.ctx.resolver_tempo(sg.get("fim", a + 2))
                ws = str(sg.get("texto", "")).split()
                tot = sum(len(w) for w in ws) or 1
                acc = a
                for w in ws:
                    d = (b - a) * len(w) / tot
                    out.append({"p": w, "i": acc, "f": acc + d})
                    acc += d
            return out
        return [w for w in self.ctx.palavras if self.t0 - 0.05 <= w["i"] < self.t1]

    def _agrupar(self, ws):
        chunks = []
        atual = []
        max_c = 16 if self.estilo == "impacto" else 24
        for k, w in enumerate(ws):
            txt = w["p"].strip()
            if not txt:
                continue
            if atual:
                ant = atual[-1]
                gap = w["i"] - ant["f"]
                comp = sum(len(x["p"]) + 1 for x in atual) + len(txt)
                quebra = (len(atual) >= self.max_p or gap > 0.45 or PONT_FIM.search(ant["p"]) is not None
                          or (PONT_PAUSA.search(ant["p"]) is not None and len(atual) >= 2)
                          or comp > max_c * self.linhas)
                if quebra:
                    chunks.append(atual)
                    atual = []
            atual.append(dict(w, p=txt))
        if atual:
            chunks.append(atual)
        out = []
        for i, c in enumerate(chunks):
            ini = c[0]["i"] - 0.04
            fim = c[-1]["f"] + 0.18
            if i + 1 < len(chunks):
                fim = min(fim, chunks[i + 1][0]["i"] - 0.03)
                if fim - ini < 0.45:
                    fim = min(chunks[i + 1][0]["i"] - 0.03, ini + 0.45)
            out.append({"i": ini, "f": max(ini + 0.12, fim), "ws": c})
        return out

    def _texto(self, w):
        s = w["p"]
        if not self.pont:
            s = re.sub(r"[\.,;:]+$", "", s)
        return s

    def _kw(self):
        return dict(largura_max=self.larg_max, alinhamento="centro", maiusculas=self.maius, contorno=self.contorno,
                    cor_contorno=(0, 0, 0, 255), entrelinha=1.04)

    def _render(self, ci, atual, visiveis, esconder_atual=False):
        """Bloco de legenda. Retorna o TextoRender (com caixas das palavras)."""
        k = (ci, atual, visiveis, esconder_atual)
        if k in self._cache:
            return self._cache[k]
        if len(self._cache) > 96:
            self._cache = {}
        c = self.chunks[ci]
        textos = [self._texto(w) for w in c["ws"]]
        cores = {}
        caixas = None
        for j, w in enumerate(c["ws"]):
            if self._n(w["p"]) in self.destacar:
                cores[j] = self.cor_d
        est = self.estilo
        if est in ("destaque", "impacto", "pop", "palavra") and atual is not None and atual >= 0:
            cores[atual] = self.cor_d
        if est == "caixa_palavra" and atual is not None and atual >= 0 and not esconder_atual:
            caixas = {atual: self.cor_d}
            cores[atual] = G.contraste_para(self.cor_d)
        kw = self._kw()
        kw.update(cor_por_palavra=cores, caixa_palavras=caixas)
        if est != "caixa":
            kw["sombra"] = self.sombras
        else:
            kw["caixa"] = self.caixa
            kw["caixa_pad"] = (self.px(24), self.px(12))
            kw["caixa_raio"] = self.px(16)
        if est == "pop":
            kw["ocultar_apos"] = visiveis
        if esconder_atual and atual is not None and atual >= 0:
            kw["ocultar_indices"] = {atual}
        r = G.render_texto(" ".join(textos), self.fonte, self.tam, self.cor_t, **kw)
        self._cache[k] = r
        return r

    def _palavra_ativa(self, ci, j):
        """Sprite só da palavra ativa (mesma fonte/cor/sombra), para o 'pulo'."""
        k = ("ativa", ci, j)
        if k in self._cache:
            return self._cache[k]
        w = self.chunks[ci]["ws"][j]
        caixas = None
        cor = self.cor_d
        if self.estilo == "caixa_palavra":
            caixas = {0: self.cor_d}
            cor = G.contraste_para(self.cor_d)
        r = G.render_texto(self._texto(w), self.fonte, self.tam, cor, maiusculas=self.maius, contorno=self.contorno,
                           cor_contorno=(0, 0, 0, 255), sombra=self.sombras, caixa_palavras=caixas)
        self._cache[k] = r
        return r

    # ---------------------------------------------------------------- posição e legibilidade
    def _melhor_y(self, areas, w, h):
        y0 = self.y
        x0, x1 = self.x - w / 2, self.x + w / 2

        def colide(yc):
            a0, a1 = yc - h / 2, yc + h / 2
            return any(not (x1 < a[0] or x0 > a[2] or a1 < a[1] or a0 > a[3]) for a in areas)
        if not areas or not colide(y0):
            return y0, False
        m = self.px(22)
        lim0, lim1 = self.H * 0.1 + h / 2, self.H * (0.9 if self.H > self.W else 0.95) - h / 2
        cands = []
        for a in areas:
            cands += [a[3] + m + h / 2, a[1] - m - h / 2]
        cands = sorted((c for c in cands if lim0 <= c <= lim1), key=lambda c: abs(c - y0))
        for c in cands:
            if not colide(c):
                return c, False
        return y0, True

    def _y_livre(self, t, w, h):
        """Centro vertical da legenda desviando de cartões/CTAs/prints ativos; muda suave (média de instantes
        recentes, determinística). Retorna (y, sem_saida)."""
        if not self.desviar:
            return self.y, False
        ys, sem = [], False
        for k in range(4):
            y, s_ = self._melhor_y(self.ctx.areas_ocupadas(t - k * 0.07, exceto=self), w, h)
            ys.append(y)
            if k == 0:
                sem = s_
        return sum(ys) / len(ys), sem

    def _fundo_auto(self, img, r, x, y, esc, op, forcar=False):
        """Caixa escura atrás da legenda quando o que está atrás é claro (ou sem lugar livre)."""
        if not self.fundo_auto or self.estilo == "caixa" or not r.linhas:
            return img
        lx0 = min(l[0] for l in r.linhas)
        ly0 = min(l[1] for l in r.linhas)
        lx1 = max(l[2] for l in r.linhas)
        ly1 = max(l[3] for l in r.linhas)
        cx = x + ((lx0 + lx1) / 2 - r.img.width / 2) * esc
        cy = y + ((ly0 + ly1) / 2 - r.img.height / 2) * esc
        w, h = (lx1 - lx0) * esc + self.px(44), (ly1 - ly0) * esc + self.px(18)
        k = 1.0 if forcar else 0.0
        if not forcar:
            bx0, by0 = int(max(0, cx - w / 2)), int(max(0, cy - h / 2))
            bx1, by1 = int(min(img.width, cx + w / 2)), int(min(img.height, cy + h / 2))
            if bx1 - bx0 < 4 or by1 - by0 < 4:
                return img
            reg = np.asarray(img.crop((bx0, by0, bx1, by1)).convert("L").resize((24, 6), Image.BILINEAR), np.float32) / 255
            lum = max(float(reg.mean()), float(np.percentile(reg, 75)) - 0.08)
            k = clamp((lum - 0.5) / 0.16)
        if k <= 0.01:
            return img
        chave = ("caixa", int(w), int(h))
        if chave not in self._cache:
            self._cache[chave] = G.ret_arred(w, h, min(h / 2, self.px(20)), (0, 0, 0, 255))
        cx_ = self._cache[chave]
        return G.colar(img, cx_, cx, cy, (0.5, 0.5), 1, 0, op * k * 0.72)

    def aplicar(self, img, t):
        if not self.chunks:
            return img
        if not self._auto_ocultar:
            self._auto_ocultar = True
            for e in getattr(self.ctx, "efeitos", []):
                if e is not self and (getattr(e, "oculta_legendas", False) or e.spec.get("ocultar_legendas")):
                    self.ocultar.append((e.t0, e.t1))
        for a, b in self.ocultar:
            if a <= t < b:
                return img
        ci = bisect.bisect_right(self.inicios, t) - 1
        if ci < 0:
            return img
        c = self.chunks[ci]
        if t >= c["f"]:
            return img
        atual = -1
        for j, w in enumerate(c["ws"]):
            if w["i"] <= t + 0.02:
                atual = j
        p_bloco = clamp((t - c["i"]) / 0.18)
        if self.estilo == "palavra":
            w = c["ws"][max(0, atual)]
            k = ("p", ci, atual)
            if k not in self._cache:
                cor = self.cor_d if self._n(w["p"]) in self.destacar else self.cor_t
                self._cache[k] = G.render_texto(self._texto(w), self.fonte, self.tam, cor, maiusculas=self.maius,
                                                contorno=self.contorno, sombra=self.sombras)
            r = self._cache[k]
            y, sem = self._y_livre(t, r.img.width - 2 * r.pad, r.img.height - 2 * r.pad)
            p = clamp((t - min(w["i"], c["i"] + 0.04) + 0.04) / 0.16)
            esc = 0.84 + 0.16 * volta(p, 2.2)
            op = clamp(p * 3 + 0.35)
            img = self._fundo_auto(img, r, self.x, y, esc, op, sem)
            return G.colar(img, r.img, self.x, y, (0.5, 0.5), esc, 0, op)
        if self.estilo == "caixa" or self.estilo == "minimal":
            r = self._render(ci, -1, None)
            y, sem = self._y_livre(t, r.img.width - 2 * r.pad, r.img.height - 2 * r.pad)
            op = clamp(p_bloco * 2)
            if self.estilo == "minimal":
                op *= 1 - clamp((t - c["f"] + 0.12) / 0.12)
            dy = self.px(10) * (1 - easing("expo")(p_bloco))
            img = self._fundo_auto(img, r, self.x, y + dy, 1.0, op, sem)
            return G.colar(img, r.img, self.x, y + dy, (0.5, 0.5), 1, 0, op)
        vis = atual if self.estilo == "pop" else None
        pulo = self.pulo and atual >= 0
        r = self._render(ci, atual, vis, esconder_atual=pulo)
        y, sem = self._y_livre(t, r.img.width - 2 * r.pad, r.img.height - 2 * r.pad)
        if self.estilo == "impacto":
            esc = 0.8 + 0.2 * volta(p_bloco, 2.2)
            img = self._fundo_auto(img, r, self.x, y, esc, clamp(p_bloco * 3), sem)
            return G.colar(img, r.img, self.x, y, (0.5, 0.5), esc, 0, clamp(p_bloco * 3))
        q = easing("expo")(p_bloco)
        esc_b = 0.96 + 0.04 * q
        dy = self.px(12) * (1 - q)
        op = clamp(p_bloco * 2.5)
        img = self._fundo_auto(img, r, self.x, y + dy, esc_b, op, sem)
        img = G.colar(img, r.img, self.x, y + dy, (0.5, 0.5), esc_b, 0, op)
        if pulo:
            w = c["ws"][atual]
            ra = self._palavra_ativa(ci, atual)
            x0, y0, x1, y1 = r.palavras[atual][:4]
            # centro da palavra no quadro (o bloco foi colado centralizado em (x, y + dy) com escala esc_b)
            cxp = self.x + ((x0 + x1) / 2 - r.img.width / 2) * esc_b
            cyp = y + dy + ((y0 + y1) / 2 - r.img.height / 2) * esc_b
            pp = clamp((t - w["i"]) / 0.2)
            # cresce pouco (no máximo ~1/5 do espaço entre palavras de cada lado): palavra longa cresce menos
            larg_w = max(1.0, (x1 - x0))
            esp = G.medir_texto(" ", self.fonte, self.tam)
            k = min(0.07, 2 * esp * 0.22 / larg_w) if self.estilo != "caixa_palavra" else min(0.03, esp * 0.3 / larg_w)
            if self.estilo == "pop":
                esc_w = 0.55 + (0.45 + k) * volta(pp, 2.0)
                op_w = op * clamp(pp * 4 + 0.5)
            else:
                esc_w = 1.0 + k * volta(pp, 2.4)
                op_w = op  # a troca de cor é imediata; só o tamanho anima
            wx0, wy0, wx1, wy1 = ra.palavras[0][:4]
            ocx = (wx0 + wx1) / 2 / ra.img.width
            ocy = (wy0 + wy1) / 2 / ra.img.height
            img = G.colar(img, ra.img, cxp, cyp, (ocx, ocy), esc_w * esc_b, 0, op_w)
        return img
