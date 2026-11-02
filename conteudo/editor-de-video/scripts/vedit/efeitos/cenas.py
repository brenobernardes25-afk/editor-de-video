"""Cenas compostas com vídeo: tela dividida, antes e depois, galeria, deck de cenas, órbita, carrossel,
afasta e revela, diminui e explica, b-roll (cobertura) e picture-in-picture."""
import math

import numpy as np
from PIL import Image, ImageDraw

from .. import grafico as G
from ..tempo import clamp, easing, entrada, expo, expo_io, kf, lerp, mola, suave, volta
from ..util import num, sondar
from .base import Efeito, registrar


def _rotulo(txt, s, estilo, cor_fundo=None, cor_txt=None, tam=26):
    """Rótulo em pílula (preto translúcido com borda fina, ou sólido em cor_fundo)."""
    return G.pilula(str(txt), estilo, s, mat="preto", tam=tam, cor_fundo=cor_fundo, cor_txt=cor_txt).sprite


def _moldura_celular(w, h, s, cor_c=(18, 18, 20, 255)):
    """Moldura genérica de celular (sem marca) para um conteúdo w×h."""
    b = 22 * s
    W, H = int(w + 2 * b), int(h + 2 * b)
    m = G.ret_arred(W, H, 64 * s, cor_c, (70, 70, 76, 255), max(2, 3 * s))
    furo = Image.new("L", (W, H), 255)
    ImageDraw.Draw(furo).rounded_rectangle([b, b, b + w, b + h], radius=46 * s, fill=0)
    a = np.minimum(np.asarray(m.getchannel("A")), np.asarray(furo))
    m.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([W / 2 - 70 * s, b + 14 * s, W / 2 + 70 * s, b + 44 * s], radius=15 * s, fill=cor_c)
    return m, b


class _Cena(Efeito):
    fase = "cena"
    entrada_padrao = "fade"
    som_entrada = "whoosh"
    vol_som = 0.22

    def fundo(self, base, q=1.0):
        f = self.param("fundo", "estilo")
        W, H = self.W, self.H
        if f in ("desfoque", "blur", "video"):
            bg = G.desfocar(base, self.px(40))
            bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
        elif isinstance(f, str) and (f.startswith("#") or f in G.NOMES_CORES):
            bg = Image.new("RGB", (W, H), self.cor(f)[:3])
        elif isinstance(f, str) and f in self.ctx.bib.mapa:
            bg = G.cobrir(self.ctx.bib.quadro_pil(f, 0), W, H)
        else:
            if not hasattr(self, "_bg_estilo"):
                self._bg_estilo = G.fundo_cena(W, H, self.e)
            bg = self._bg_estilo.copy()
        if q < 1:
            bg = Image.blend(base, bg, clamp(q))
        return bg

    def painel(self, fonte, t, base, w, h, raio=0, foco=(0.5, 0.5), grade=None):
        fr = self.quadro_de(fonte, t, base, (int(w), int(h)))
        if grade:
            fr = self.ctx.aplicar_grade(fr, grade)
        im = G.cobrir(fr, w, h, foco).convert("RGBA")
        if raio > 0:
            im = G.cantos(im, raio)
        return im

    def progresso(self, t):
        """q: 0→1 na entrada, 1→0 na saída (com easing)."""
        pi = easing("expo_io")(self.p_entrada(t, max(0.3, self.d_in)))
        po = easing("expo_io")(self.p_saida(t, max(0.25, self.d_out)))
        return pi * (1 - po), pi, po


@registrar("tela_dividida", "split", "split_screen", "dividir_tela", "tela_dupla", "comparacao", "comparar",
           "lado_a_lado", "duas_telas")
class TelaDividida(_Cena):
    """Tela dividida com 2 a 4 painéis. paineis: [fonte, ...] onde fonte = 'principal' | nome de mídia |
    {midia, de, velocidade} | {imagem} | {texto, fundo} | {bruto: segundos} (outro momento do vídeo principal);
    cada painel aceita 'rotulo' e 'cor' (look). direcao: 'vertical' (empilhado, padrão em 9:16) | 'horizontal'
    (lado a lado) | 'grade' (2×2), espaco (px, padrão 14), raio (padrão 28), margem (padrão 28),
    rotulos_posicao ('topo' | 'baixo'), entrada ('deslizar' | 'fade' | 'expandir')."""

    def preparar(self):
        ps = self.param("paineis") or ["principal", "principal"]
        self.paineis = [p if isinstance(p, dict) else {"midia": p} if p != "principal" else {"principal": True} for p in ps]
        n = len(self.paineis)
        padrao = "vertical" if self.H > self.W else "horizontal"
        if n == 4 and not self.param("direcao"):
            padrao = "grade"
        self.dir = str(self.param("direcao", padrao))
        self.gap = self.px(num(self.param("espaco"), 12))
        self.raio = self.px(num(self.param("raio"), 32))
        self.marg = self.px(num(self.param("margem"), 24 if self.raio > 0 else 0))
        self.entrada_tipo = str(self.param("entrada", "deslizar"))
        W, H, g, m = self.W, self.H, self.gap, self.marg
        rects = []
        if self.dir == "grade":
            cols = 2
            rows = int(math.ceil(n / 2))
            cw = (W - 2 * m - g) / 2
            ch = (H - 2 * m - g * (rows - 1)) / rows
            for i in range(n):
                r, c = divmod(i, 2)
                rects.append((m + c * (cw + g), m + r * (ch + g), cw, ch))
        elif self.dir == "horizontal":
            cw = (W - 2 * m - g * (n - 1)) / n
            for i in range(n):
                rects.append((m + i * (cw + g), m, cw, H - 2 * m))
        else:
            ch = (H - 2 * m - g * (n - 1)) / n
            for i in range(n):
                rects.append((m, m + i * (ch + g), W - 2 * m, ch))
        self.rects = rects
        self.rotulos = []
        for p in self.paineis:
            if p.get("rotulo"):
                self.rotulos.append(_rotulo(p["rotulo"], self.s, self.e))
            else:
                self.rotulos.append(None)
        self.rot_pos = str(self.param("rotulos_posicao", "topo"))

    def aplicar(self, img, t):
        q, pi, po = self.progresso(t)
        out = self.fundo(img, q)
        for i, (p, (x, y, w, h)) in enumerate(zip(self.paineis, self.rects)):
            foco = (num(p.get("foco_x"), 0.5), num(p.get("foco_y"), 0.45))
            pan = self.painel(p, t, img, w, h, self.raio, foco, p.get("cor"))
            dx = dy = 0
            esc = 1.0
            if self.entrada_tipo == "deslizar":
                sinal = -1 if i % 2 == 0 else 1
                if self.dir == "vertical":
                    dx = sinal * (1 - q) * (self.W + 40)
                else:
                    dy = sinal * (1 - q) * (self.H + 40)
            elif self.entrada_tipo == "expandir":
                esc = 0.6 + 0.4 * q
            op = 1.0 if self.entrada_tipo == "deslizar" else q
            out = G.colar(out, pan, x + w / 2 + dx, y + h / 2 + dy, (0.5, 0.5), esc, 0, op)
            rt = self.rotulos[i]
            if rt is not None:
                ry = y + self.px(28) if self.rot_pos == "topo" else y + h - self.px(28) - rt.height
                out = G.colar(out, rt, x + self.px(28) + dx, ry + dy, (0, 0), 1, 0, clamp(q * 1.5))
        return out


@registrar("antes_depois", "antes_e_depois", "before_after", "comparativo", "original_editado")
class AntesDepois(_Cena):
    """Comparação antes/depois com cortina deslizante (linha com alça) ou lado a lado. antes / depois: fontes
    (padrão as duas = 'principal'), cor_antes / cor_depois: look aplicado a cada lado (ex. depois: 'cinema'),
    modo: 'cortina' (padrão) | 'lado_a_lado' | 'alternar', rotulos: ['ANTES', 'DEPOIS'] (ex. ['ORIGINAL',
    'EDITADO']), posicao_final (0..1 onde a cortina para, padrão 0.5), vertical (true = cortina de cima p/ baixo)."""

    def preparar(self):
        self.antes = self.param("antes", "principal")
        self.depois = self.param("depois", "principal")
        self.ca = self.param("cor_antes")
        self.cd = self.param("cor_depois", "cinema" if self.antes == self.depois else None)
        self.modo = str(self.param("modo", "cortina"))
        rot = self.param("rotulos", ["ANTES", "DEPOIS"])
        self.ra = _rotulo(rot[0], self.s, self.e) if rot and rot[0] else None
        self.rd = _rotulo(rot[1], self.s, self.e, cor_fundo="destaque") if rot and len(rot) > 1 and rot[1] else None
        self.pf = num(self.param("posicao_final"), 0.5)
        self.vertical = bool(self.param("vertical", False))
        d = self.px(84)
        S = 4
        al = Image.new("RGBA", (int(d * S), int(d * S)), (0, 0, 0, 0))
        dd = ImageDraw.Draw(al)
        dd.ellipse([0, 0, d * S - 1, d * S - 1], fill=(255, 255, 255, 255))
        c = (18, 18, 20, 255)
        u = d * S / 100
        lw = int(7 * u)
        dd.line([(40 * u, 34 * u), (26 * u, 50 * u), (40 * u, 66 * u)], fill=c, width=lw, joint="curve")
        dd.line([(60 * u, 34 * u), (74 * u, 50 * u), (60 * u, 66 * u)], fill=c, width=lw, joint="curve")
        al = al.resize((int(d), int(d)), Image.LANCZOS)
        if self.vertical:
            al = al.rotate(90)
        self.alca = G.com_sombra(al, self.px(16), 0, self.px(6), 0.4)
        self.esp_linha = max(2, int(self.px(4)))

    def _quadro(self, fonte, t, base, grade):
        fr = self.quadro_de(fonte, t, base, (self.W, self.H))
        fr = G.cobrir(fr, self.W, self.H) if fr.size != (self.W, self.H) else fr
        if grade:
            fr = self.ctx.aplicar_grade(fr, grade)
        return fr

    def aplicar(self, img, t):
        W, H = self.W, self.H
        q, pi, po = self.progresso(t)
        A = self._quadro(self.antes, t, img, self.ca)
        B = self._quadro(self.depois, t, img, self.cd)
        u = t - self.t0
        if self.modo == "lado_a_lado":
            out = Image.new("RGB", (W, H), (0, 0, 0))
            if H > W:
                h2 = H // 2
                out.paste(G.cobrir(A, W, h2), (0, 0))
                out.paste(G.cobrir(B, W, H - h2), (0, h2))
                ImageDraw.Draw(out).rectangle([0, h2 - 3, W, h2 + 3], fill=(255, 255, 255))
                pos = [(self.px(28), self.px(40)), (self.px(28), h2 + self.px(28))]
            else:
                w2 = W // 2
                out.paste(G.cobrir(A, w2, H), (0, 0))
                out.paste(G.cobrir(B, W - w2, H), (w2, 0))
                ImageDraw.Draw(out).rectangle([w2 - 3, 0, w2 + 3, H], fill=(255, 255, 255))
                pos = [(self.px(28), self.px(28)), (w2 + self.px(28), self.px(28))]
            for r, p in zip((self.ra, self.rd), pos):
                if r is not None:
                    out = G.colar(out, r, p[0], p[1], (0, 0))
            return Image.blend(img, out, q) if q < 1 else out
        if self.modo == "alternar":
            per = num(self.param("intervalo"), 1.0)
            k = int(u / per) % 2
            out = (A if k == 0 else B).copy()
            r = self.ra if k == 0 else self.rd
            if r is not None:
                out = G.colar(out, r, W / 2, self.px(150), (0.5, 0))
            return Image.blend(img, out, q) if q < 1 else out
        # cortina
        x = kf(u, [(0.0, 0.94), (0.55, 0.94), (1.35, 0.06, "suave"), (2.2, 0.8, "suave"), (2.8, self.pf, "suave")])
        if self.param("posicao_slider") is not None:
            x = num(self.param("posicao_slider"))
        out = A.copy()
        if self.vertical:
            yy = int(H * x)
            out.paste(B.crop((0, yy, W, H)), (0, yy))
            ImageDraw.Draw(out).rectangle([0, yy - self.esp_linha // 2, W, yy + self.esp_linha // 2], fill=(255, 255, 255))
            out = G.colar(out, self.alca, W / 2, yy, (0.5, 0.5))
        else:
            xx = int(W * x)
            out.paste(B.crop((xx, 0, W, H)), (xx, 0))
            ImageDraw.Draw(out).rectangle([xx - self.esp_linha // 2, 0, xx + self.esp_linha // 2, H], fill=(255, 255, 255))
            out = G.colar(out, self.alca, xx, H * 0.5, (0.5, 0.5))
        if self.ra is not None:
            out = G.colar(out, self.ra, self.px(30), self.px(150), (0, 0), 1, 0, clamp((x - 0.12) * 6))
        if self.rd is not None:
            out = G.colar(out, self.rd, W - self.px(30), self.px(150), (1, 0), 1, 0, clamp((0.88 - x) * 6))
        return Image.blend(img, out, q) if q < 1 else out


@registrar("galeria", "galeria_de_videos", "grade", "grid", "mosaico", "colagem", "grade_de_videos")
class Galeria(_Cena):
    """Grade de vídeos/imagens tocando juntos, entrando em cascata. itens: [fontes] (2–9; 'principal' vale),
    colunas (auto), espaco (16), raio (24), margem (40), titulo (texto no topo), destaque: índice que cresce até
    tela cheia no fim (opcional), rotulos: ['A', 'B', ...] (opcional), fundo ('estilo' | 'desfoque' | cor)."""

    def preparar(self):
        itens = self.param("itens") or ["principal"] * 4
        self.itens = [i if isinstance(i, dict) else {"midia": i} if i != "principal" else {"principal": True} for i in itens]
        n = len(self.itens)
        cols = int(num(self.param("colunas"), 1 if n <= 1 else 2 if n <= 4 else 3))
        rows = int(math.ceil(n / cols))
        m = self.px(num(self.param("margem"), 40))
        g = self.px(num(self.param("espaco"), 16))
        topo = 0
        self.tit = None
        if self.param("titulo"):
            self.tit = G.render_texto(str(self.param("titulo")), self.e["fonte_titulo"], self.px(72), self.cor("texto"),
                                      largura_max=self.W * 0.86, cor_destaque=self.cor("destaque"),
                                      fonte_destaque=self.e["fonte_destaque"], marca_solida=bool(self.e.get("marca_solida", True)),
                                      sombra=self.sombra_texto())
            topo = self.tit.img.height + self.px(40)
        cw = (self.W - 2 * m - g * (cols - 1)) / cols
        ch_max = (self.H - 2 * m - topo - g * (rows - 1)) / rows
        ch = min(ch_max, cw * num(self.param("proporcao"), 16 / 9 if self.H > self.W else 9 / 16))
        tot_h = rows * ch + (rows - 1) * g
        y0 = topo + (self.H - topo - tot_h) / 2
        self.rects = []
        for i in range(n):
            r, c = divmod(i, cols)
            nlin = min(cols, n - r * cols)
            x0 = (self.W - (nlin * cw + (nlin - 1) * g)) / 2
            self.rects.append((x0 + c * (cw + g), y0 + r * (ch + g), cw, ch))
        self.raio = self.px(num(self.param("raio"), 24))
        self.y_tit = y0 - self.px(30)
        self.destaque = self.param("destaque")
        rots = self.param("rotulos") or []
        self.rots = [_rotulo(r, self.s, self.e, tam=22) if r else None for r in rots] + [None] * n

    def aplicar(self, img, t):
        q, pi, po = self.progresso(t)
        out = self.fundo(img, q)
        if self.tit is not None:
            out = G.colar(out, self.tit.img, self.W / 2, self.y_tit, (0.5, 1), 1, 0, q)
        u = t - self.t0
        zd = None
        if self.destaque is not None:
            d0 = self.dur - num(self.param("duracao_destaque"), 1.2)
            zd = easing("expo_io")(clamp((u - d0) / 0.6))
        for i, (it, (x, y, w, h)) in enumerate(zip(self.itens, self.rects)):
            p = clamp((u - 0.08 * i) / 0.45)
            esc = 0.82 + 0.18 * volta(p, 1.6)
            op = clamp(p * 2) * (1 - po)
            if zd is not None and i == int(self.destaque) and zd > 0:
                X, Y = lerp(x, 0, zd), lerp(y, 0, zd)
                ww, hh = lerp(w, self.W, zd), lerp(h, self.H, zd)
                pan = self.painel(it, t, img, ww, hh, self.raio * (1 - zd))
                out = G.colar(out, pan, X + ww / 2, Y + hh / 2, (0.5, 0.5), 1, 0, 1)
                continue
            pan = self.painel(it, t, img, w, h, self.raio)
            out = G.colar(out, G.com_sombra_ret(pan, self.raio, self.px(16), 0, self.px(8), 0.4), x + w / 2, y + h / 2,
                          (0.5, 0.5), esc, 0, op)
            if self.rots[i] is not None:
                out = G.colar(out, self.rots[i], x + self.px(16), y + self.px(16), (0, 0), 1, 0, op)
        if zd is not None and zd > 0:
            i = int(self.destaque)
            if 0 <= i < len(self.itens):
                x, y, w, h = self.rects[i]
                X, Y = lerp(x, 0, zd), lerp(y, 0, zd)
                ww, hh = lerp(w, self.W, zd), lerp(h, self.H, zd)
                pan = self.painel(self.itens[i], t, img, ww, hh, self.raio * (1 - zd))
                out = G.colar(out, pan, X + ww / 2, Y + hh / 2, (0.5, 0.5))
        return out

    def sons_extra(self):
        return [(self.t0 + 0.08 * i, "pop", 0.12) for i in range(len(self.itens))]


@registrar("deck_cenas", "deck", "deck_de_cenas", "baralho", "pilha", "pilha_de_cartoes", "cartas")
class DeckCenas(_Cena):
    """Cenas empilhadas como cartas: a de cima sai voando e revela a próxima. itens: [fontes] (vídeos, imagens,
    {texto}), intervalo (s por carta; padrão divide a duração), largura (0.76), proporcao (altura/largura, padrão
    1.3), direcao_saida ('esquerda' | 'direita' | 'cima' | 'alternar'), rotulos (opcional), fundo."""

    def preparar(self):
        itens = self.param("itens") or ["principal"]
        self.itens = [i if isinstance(i, dict) else {"midia": i} if i != "principal" else {"principal": True} for i in itens]
        n = len(self.itens)
        self.intervalo = num(self.param("intervalo"), max(0.6, (self.dur - 0.4) / max(1, n)))
        self.w = self.W * num(self.param("largura"), 0.76)
        self.h = min(self.H * 0.8, self.w * num(self.param("proporcao"), 1.3))
        self.raio = self.px(num(self.param("raio"), 36))
        self.x, self.y = self.pos(None, "centro")
        self.dir = str(self.param("direcao_saida", "alternar"))
        rots = self.param("rotulos") or []
        self.rots = [_rotulo(r, self.s, self.e) if r else None for r in rots] + [None] * n

    def aplicar(self, img, t):
        q, pi, po = self.progresso(t)
        out = self.fundo(img, q)
        u = t - self.t0 - 0.2
        n = len(self.itens)
        k_f = max(0.0, u / self.intervalo)
        k = int(k_f)
        frac = k_f - k
        voo = easing("saida")(clamp((frac - (1 - 0.42 / self.intervalo)) / (0.42 / self.intervalo))) if k < n - 1 else 0.0
        # desenha de trás para frente: k+3 .. k
        for j in range(min(n - 1, k + 3), k - 1, -1):
            if j < 0:
                continue
            nivel = j - k - voo
            if nivel < -0.001 and j != k:
                continue
            esc = 1 - 0.07 * max(0, nivel)
            dy = -self.px(46) * max(0, nivel)
            rot = (3.5 if j % 2 else -3.5) * min(1, max(0, nivel))
            pan = self.painel(self.itens[j], t, img, self.w, self.h, self.raio)
            if nivel > 0.01:
                esc_k = clamp(0.22 * nivel)
                a_ = pan.getchannel("A")
                rgb = Image.blend(pan.convert("RGB"), Image.new("RGB", pan.size, (0, 0, 0)), esc_k)
                pan = rgb.convert("RGBA")
                pan.putalpha(a_)
            if self.rots[j] is not None:
                pan.paste(self.rots[j], (int(self.px(24)), int(self.px(24))), self.rots[j])
            pan = G.com_sombra_ret(pan, self.raio, self.px(26), 0, self.px(14), 0.5)
            x, y = self.x, self.y + dy
            op = 1.0
            if j == k and voo > 0:
                d = self.dir
                if d == "alternar":
                    d = "esquerda" if k % 2 == 0 else "direita"
                sx = -1 if d == "esquerda" else 1 if d == "direita" else 0
                sy = -1 if d == "cima" else 0
                x += sx * voo * self.W * 1.1
                y += sy * voo * self.H * 0.9 + (self.px(80) * voo if sy == 0 else 0)
                rot = -sx * 22 * voo
            entrada_k = volta(clamp((t - self.t0) / 0.5), 1.4)
            out = G.colar(out, pan, x, y + (1 - entrada_k) * self.px(200), (0.5, 0.5), esc * (0.9 + 0.1 * entrada_k), rot,
                          op * clamp(q * 1.6))
        return out

    def sons_extra(self):
        n = len(self.itens)
        return [(self.t0 + 0.2 + (k + 1) * self.intervalo - 0.42, "whoosh", 0.22) for k in range(n - 1)]


def _cartao_item(item, efeito, w, h, t, base, como_cartao=False, sombra=False):
    """Desenha um item genérico (vídeo/imagem/texto/ícone). Mídias viram painel RGBA w×h; texto/ícone viram
    cartão no material do estilo (RGBA, ou Cartao se como_cartao=True para colar com desfoque de vidro)."""
    e = efeito.e
    s = efeito.s
    if isinstance(item, str):
        item = {"texto": item}
    if item.get("midia") or item.get("imagem") or item.get("principal") or item.get("bruto") is not None:
        pan = efeito.painel(item, t, base, w, h, efeito.px(28))
        if item.get("rotulo"):
            rt = _rotulo(item["rotulo"], s, e, tam=22)
            pan.alpha_composite(rt, (int(efeito.px(18)), int(h - rt.height - efeito.px(18))))
        return pan
    mat = item.get("material")
    if item.get("cor"):
        cc = efeito.cor(item["cor"])
        mat = {"tipo": "solido", "tinta": cc, "opacidade": cc[3] / 255.0, "borda": 0.1, "brilho": 0.05,
               "texto": "escuro" if G.luminancia(cc) > 0.6 else "claro"}
    c = G.cartao(w, h, efeito.px(32), e, mat, s=s, sombra=sombra)
    ct, cs = G.cores_material(G.material(e, mat), e)
    y = h * 0.5
    if item.get("icone"):
        tam_ic = min(w, h) * (0.3 if item.get("texto") else 0.42)
        ic = G.icone(item["icone"], tam_ic, efeito.cor(item.get("cor_icone", "destaque")))
        c.colar(ic, w / 2, h * (0.38 if item.get("texto") else 0.5), (0.5, 0.5))
        y = h * 0.72
    if item.get("texto"):
        tam = efeito.px(num(item.get("tamanho"), 42))
        r = G.render_texto(str(item["texto"]), e["fonte_titulo"], tam, ct, largura_max=w * 0.84,
                           cor_destaque=efeito.cor("destaque"), fonte_destaque=e["fonte_destaque"])
        if r.img.height - 2 * r.pad > h * 0.5:
            r = G.render_texto(str(item["texto"]), e["fonte_titulo"], efeito.px(30), ct, largura_max=w * 0.86)
        c.colar(r.img, w / 2, y, (0.5, 0.5))
    if como_cartao:
        return c
    return c.sprite


@registrar("orbita", "orbita_de_videos", "orbit", "orbitar", "sistema_solar", "girando_em_volta")
class Orbita(_Cena):
    """Itens orbitando em elipse (com profundidade) ao redor de um centro. centro: fonte (padrão 'principal',
    em círculo) ou {texto}/{icone}; itens: [fontes ou {texto}/{icone}/{imagem}] (3–8); raio_x (0.4), raio_y (0.14),
    velocidade (voltas/s, padrão 0.12), tamanho_itens (0.24), tamanho_centro (0.5), fundo."""

    def preparar(self):
        self.centro = self.param("centro", "principal")
        if self.centro == "principal":
            self.centro = {"principal": True}
        elif isinstance(self.centro, str):
            self.centro = {"midia": self.centro}
        itens = self.param("itens") or [{"icone": "raio"}, {"icone": "estrela"}, {"icone": "coracao"}, {"icone": "play"}]
        self.itens = [i if isinstance(i, dict) else ({"midia": i} if i in self.ctx.bib.mapa else {"texto": i}) for i in itens]
        self.rx = self.W * num(self.param("raio_x"), 0.4)
        self.ry = self.H * num(self.param("raio_y"), 0.14 if self.H > self.W else 0.22)
        self.vel = num(self.param("velocidade"), 0.12)
        self.ti = self.W * num(self.param("tamanho_itens"), 0.24)
        self.tc = self.W * num(self.param("tamanho_centro"), 0.5) if self.H > self.W else self.H * 0.5
        self.x, self.y = self.pos(None, "centro")
        ca = self.cor(self.param("cor_anel", "#FFFFFF"))
        self.anel = G.circulo(self.tc + self.px(18), (0, 0, 0, 0), ca[:3] + (200,), max(3, self.px(4)))
        self.brilho = G.gradiente_radial(int(self.tc * 2.2), int(self.tc * 2.2), self.cor("destaque", 0.22),
                                         self.cor("destaque", 0.0), 0.5, 0.5, 0.5)

    def _item_cache(self, it, w, h, t, base):
        if it.get("midia") or it.get("principal"):
            return _cartao_item(it, self, w, h, t, base)
        k = id(it)
        if not hasattr(self, "_cache_itens"):
            self._cache_itens = {}
        if k not in self._cache_itens:
            self._cache_itens[k] = _cartao_item(it, self, w, h, t, base)
        return self._cache_itens[k]

    def aplicar(self, img, t):
        q, pi, po = self.progresso(t)
        out = self.fundo(img, q)
        u = t - self.t0
        abrir = easing("expo")(clamp(u / 0.9)) * (1 - easing("saida")(po))
        n = len(self.itens)
        itens_desenho = []
        for i, it in enumerate(self.itens):
            ang = 2 * math.pi * (i / n + u * self.vel)
            z = math.sin(ang)
            x = self.x + self.rx * abrir * math.cos(ang)
            y = self.y + self.ry * abrir * z
            esc = 0.72 + 0.36 * (z + 1) / 2
            itens_desenho.append((z, i, it, x, y, esc))
        ordem = sorted(itens_desenho, key=lambda v: v[0])

        def desenhar(o, z, i, it, x, y, esc):
            w = h = self.ti
            if it.get("midia") or it.get("imagem") or it.get("principal"):
                h = self.ti * num(it.get("proporcao"), 1.25)
            card = self._item_cache(it, w, h, t, img)
            if z < 0:
                a_ = card.getchannel("A")
                rgb = Image.blend(card.convert("RGB"), Image.new("RGB", card.size, (0, 0, 0)), 0.45 * -z)
                card = rgb.convert("RGBA")
                card.putalpha(a_)
            card = G.com_sombra_ret(card, self.px(30), self.px(16), 0, self.px(8), 0.45)
            return G.colar(o, card, x, y, (0.5, 0.5), esc * (0.5 + 0.5 * abrir), 0, clamp(q * 1.5))

        for v in ordem:
            if v[0] < 0:
                out = desenhar(out, *v)
        # centro
        out = G.colar(out, self.brilho, self.x, self.y, (0.5, 0.5), 1, 0, q * (0.7 + 0.3 * math.sin(u * 2)))
        if self.centro.get("principal") or self.centro.get("midia") or self.centro.get("imagem"):
            c = self.painel(self.centro, t, img, self.tc, self.tc, self.tc / 2, (0.5, 0.42))
        else:
            c = _cartao_item(self.centro, self, self.tc, self.tc, t, img)
            c = G.cantos(c, self.tc / 2)
        pc = volta(clamp(u / 0.6), 1.5)
        out = G.colar(out, G.com_sombra_ret(c, self.tc / 2, self.px(26), 0, self.px(12), 0.5), self.x, self.y, (0.5, 0.5),
                      0.4 + 0.6 * pc, 0, clamp(q * 2))
        out = G.colar(out, self.anel, self.x, self.y, (0.5, 0.5), 0.4 + 0.6 * pc, 0, clamp(q * 2))
        for v in ordem:
            if v[0] >= 0:
                out = desenhar(out, *v)
        return out


@registrar("carrossel", "carrossel_de_elementos", "carousel", "esteira", "vitrine", "slider", "marquee")
class Carrossel(Efeito):
    """Carrossel de elementos sobre o vídeo. itens: [textos | {texto, icone, imagem, midia, rotulo}],
    modo: 'passo' (um item central em destaque, avança a cada 'intervalo') | 'esteira' (rolagem contínua infinita),
    largura_item (0.5), proporcao (altura/largura do cartão, padrão 1.0 para texto e 1.25 para mídia),
    posicao (padrão 'centro'), titulo (opcional acima), fundo ('gradiente' escurece atrás), velocidade (esteira, px/s)."""
    entrada_padrao = "subir"
    duracao_padrao = 5.0
    som_entrada = "swish"
    vol_som = 0.18

    def preparar(self):
        itens = self.param("itens") or ["Item 1", "Item 2", "Item 3"]
        self.itens = [i if isinstance(i, dict) else ({"midia": i} if i in self.ctx.bib.mapa else {"texto": i}) for i in itens]
        self.modo = str(self.param("modo", "passo"))
        self.wi = self.W * num(self.param("largura_item"), 0.5 if self.modo == "passo" else 0.36)
        tem_midia = any(i.get("midia") or i.get("imagem") for i in self.itens)
        self.hi = self.wi * num(self.param("proporcao"), 1.25 if tem_midia else 0.9)
        self.gap = self.px(num(self.param("espaco"), 34))
        n = len(self.itens)
        self.intervalo = num(self.param("intervalo"), max(0.7, (self.dur - 0.8) / max(1, n)))
        self.x, self.y = self.pos(None, "centro")
        self.vel = self.px(num(self.param("velocidade"), 260))
        self.tit = G.render_texto(str(self.param("titulo")), self.e["fonte_titulo"], self.px(66), self.cor("texto"),
                                  largura_max=self.W * 0.86, cor_destaque=self.cor("destaque"),
                                  fonte_destaque=self.e["fonte_destaque"], marca_solida=bool(self.e.get("marca_solida", True)),
                                  sombra=self.sombra_texto()) if self.param("titulo") else None
        self._cache = {}

    def area(self, t):
        ht = (self.tit.img.height - self.tit.pad + self.px(40)) if self.tit else 0
        return (0, self.y - self.hi / 2 - ht, self.W, self.y + self.hi / 2 + self.px(30))

    def _card(self, i, t, base):
        it = self.itens[i]
        dinamico = bool(it.get("midia") or it.get("principal"))
        if not dinamico and i in self._cache:
            return self._cache[i]
        if dinamico or it.get("imagem"):
            c = _cartao_item(it, self, self.wi, self.hi, t, base)
            c = G.com_sombra_ret(c, self.px(28), self.px(36), 0, self.px(18), 0.38)
        else:
            c = _cartao_item(it, self, self.wi, self.hi, t, base, como_cartao=True, sombra=True)
        if not dinamico:
            self._cache[i] = c
        return c

    def _colar_item(self, img, c, x, y, esc, rot, op):
        if isinstance(c, G.Cartao):
            return G.colar_cartao(img, c, x, y, (0.5, 0.5), esc, rot, op)
        return G.colar(img, c, x, y, (0.5, 0.5), esc, rot, op)

    def aplicar(self, img, t):
        a = self.anim(t)
        if self.param("fundo") == "gradiente":
            from .texto import _fundo_legivel
            g = _fundo_legivel(self.W, self.H, 0, self.H, 0.6)
            img = G.colar(img, g, 0, 0, (0, 0), 1, 0, a["op"] * 0.9)
        u = t - self.t0
        n = len(self.itens)
        passo = self.wi + self.gap
        if self.modo == "esteira":
            total = n * passo
            off = (u * self.vel) % total
            k0 = int(math.floor((-self.W / 2 - self.wi + off) / passo)) - 1
            for k in range(k0, k0 + int(self.W / passo) + 4):
                x = self.x + k * passo - off
                if x < -self.wi or x > self.W + self.wi:
                    continue
                img = self._colar_item(img, self._card(k % n, t, img), x + a["dx"], self.y + a["dy"], 1, 0, a["op"])
        else:
            kf_ = u / self.intervalo
            k = int(kf_)
            fr = kf_ - k
            mov = 0.45 / self.intervalo
            frac = suave(clamp((fr - (1 - mov)) / mov)) if k < n - 1 else 0.0
            pos = min(n - 1, k + frac)
            ordem = sorted(range(n), key=lambda i: -abs(i - pos))
            for i in ordem:
                d = i - pos
                if abs(d) > 2.6:
                    continue
                esc = 1 - 0.2 * min(1.0, abs(d))
                op = (1 - 0.5 * min(1.0, abs(d))) * a["op"]
                x = self.x + d * (self.wi * 0.86 + self.gap)
                img = self._colar_item(img, self._card(i, t, img), x + a["dx"], self.y + a["dy"] + abs(d) * self.px(20),
                                       esc * a["esc"], -d * 3, op)
        if self.tit:
            img = G.colar(img, self.tit.img, self.W / 2 + a["dx"], self.y - self.hi / 2 - self.px(40) + a["dy"], (0.5, 1),
                          1, 0, a["op"])
        return img

    def sons_extra(self):
        if self.modo == "esteira":
            return []
        n = len(self.itens)
        return [(self.t0 + (k + 1) * self.intervalo - 0.45, "swish", 0.15) for k in range(n - 1)]


@registrar("afasta_revela", "afastar_e_revelar", "afastar", "zoom_out", "zoom_out_revela", "revelar", "encolher_tela",
           "por_dentro", "tela_no_celular")
class AfastaRevela(_Cena):
    """O vídeo encolhe (câmera 'se afasta') e revela o que está em volta: títulos acima/abaixo, fundo e, se quiser,
    uma moldura de celular. escala (padrão 0.62), raio (40), titulo / subtitulo (textos revelados acima/abaixo),
    moldura ('nenhuma' | 'celular'), volta (true: volta à tela cheia no fim), posicao_y (centro do vídeo, 0..1),
    fundo ('desfoque' padrão | 'estilo' | cor | mídia)."""
    som_entrada = "whoosh"

    def preparar(self):
        self.esc = num(self.param("escala"), 0.62)
        self.raio = self.px(num(self.param("raio"), 40))
        self.volta = bool(self.param("volta", True))
        self.py = num(self.param("posicao_y"), 0.54 if self.param("titulo") and not self.param("subtitulo") else 0.5)
        self.moldura = str(self.param("moldura", "nenhuma"))
        if "celular" in str(self.spec.get("tipo", "")):
            self.moldura = "celular"
        self.d_ida = num(self.param("duracao_ida"), 0.7)
        self.d_volta = num(self.param("duracao_volta"), 0.6) if self.volta else 0
        e = self.e
        self.tit = G.render_texto(str(self.param("titulo")), e["fonte_titulo"], self.px(num(self.param("tamanho"), 84)),
                                  self.cor("texto"), largura_max=self.W * 0.86, cor_destaque=self.cor("destaque"),
                                  fonte_destaque=e["fonte_destaque"], entrelinha=1.02,
                                  marca_solida=bool(e.get("marca_solida", True)), sombra=self.sombra_texto()) if self.param("titulo") else None
        self.sub = G.render_texto(str(self.param("subtitulo")), e["fonte_texto"], self.px(42), self.cor("texto_suave"),
                                  largura_max=self.W * 0.86, cor_destaque=self.cor("destaque"),
                                  fonte_destaque=e["fonte_destaque"], sombra=self.sombra_texto(0.8)) if self.param("subtitulo") else None
        if self.param("fundo") is None:
            self.spec["fundo"] = "desfoque"
        self._mold = None

    def aplicar(self, img, t):
        W, H = self.W, self.H
        u = t - self.t0
        p_ida = easing("expo_io")(clamp(u / self.d_ida))
        p_volta = easing("expo_io")(clamp((t - (self.t1 - self.d_volta)) / max(1e-6, self.d_volta))) if self.volta else 0
        q = p_ida * (1 - p_volta)
        if q <= 0.001:
            return img
        bg = self.fundo(img, 1.0)
        esc = lerp(1.0, self.esc, q)
        w, h = W * esc, H * esc
        cy = lerp(H / 2, H * self.py, q)
        card = img.resize((max(2, int(w)), max(2, int(h))), Image.BICUBIC).convert("RGBA")
        card = G.cantos(card, self.raio * q)
        out = bg
        if self.moldura == "celular":
            if self._mold is None or self._mold[0].size[0] < 2:
                self._mold = _moldura_celular(W * self.esc, H * self.esc, self.s)
            mold, b = self._mold
            k = esc / self.esc
            out = G.colar(out, G.com_sombra_ret(card, self.raio * q, self.px(40), 0, self.px(24), 0.6 * q), W / 2, cy, (0.5, 0.5))
            out = G.colar(out, mold, W / 2, cy, (0.5, 0.5), k, 0, q)
        else:
            out = G.colar(out, G.com_sombra_ret(card, self.raio * q, self.px(40), 0, self.px(20), 0.6 * q), W / 2, cy, (0.5, 0.5))
        pt = clamp((u - self.d_ida * 0.6) / 0.45) * (1 - p_volta)
        if self.tit is not None:
            y = cy - h / 2 - self.px(40)
            out = G.colar(out, self.tit.img, W / 2, y + self.px(30) * (1 - entrada(pt)), (0.5, 1), 1, 0, pt)
        if self.sub is not None:
            y = cy + h / 2 + self.px(34)
            out = G.colar(out, self.sub.img, W / 2, y - self.px(30) * (1 - entrada(pt)), (0.5, 0), 1, 0, pt)
        return out

    def sons_extra(self):
        return [(self.t1 - self.d_volta, "swish", 0.2)] if self.volta else []


@registrar("diminui_explica", "diminuir_e_explicar", "diminui", "pip_explica", "explicar", "explicacao",
           "apresentador_no_canto", "voce_no_canto")
class DiminuiExplica(_Cena):
    """Você encolhe para um canto (círculo) e o conteúdo da explicação ocupa a tela. conteudo: fonte (imagem/print,
    vídeo, ou {texto}); pontos: ['tópico 1', 'tópico 2'] (lista que aparece item a item, opcional); titulo (opcional);
    pip: posicao 'inf_dir' | 'inf_esq' | 'sup_dir' | 'sup_esq' (padrão inf_dir); forma 'circulo' | 'arredondado';
    tamanho (0.36); borda (cor, padrão destaque); fundo ('estilo' | cor | 'desfoque')."""
    som_entrada = "whoosh"

    def preparar(self):
        self.conteudo = self.param("conteudo")
        if isinstance(self.conteudo, str):
            self.conteudo = {"midia": self.conteudo} if self.conteudo in self.ctx.bib.mapa else {"texto": self.conteudo}
        self.forma = str(self.param("forma", "circulo"))
        self.tam = self.W * num(self.param("tamanho"), 0.36)
        pp = str(self.param("pip", self.param("posicao_pip", "inf_dir")))
        m = self.px(46)
        hpip = self.tam if self.forma == "circulo" else self.tam * 1.3
        xs = {"esq": m + self.tam / 2, "dir": self.W - m - self.tam / 2}
        ys = {"sup": self.px(170) + hpip / 2, "inf": self.H - self.px(260) - hpip / 2}
        lado = "esq" if "esq" in pp else "dir"
        alt = "sup" if "sup" in pp else "inf"
        self.pip_c = (xs[lado], ys[alt])
        self.pip_wh = (self.tam, hpip)
        self.borda = self.param("borda", "#FFFFFF")
        e = self.e
        self.tit = G.render_texto(str(self.param("titulo")), e["fonte_titulo"], self.px(70), self.cor("texto"),
                                  largura_max=self.W * 0.86, alinhamento="esquerda", cor_destaque=self.cor("destaque"),
                                  fonte_destaque=e["fonte_destaque"], marca_solida=bool(e.get("marca_solida", True)),
                                  sombra=self.sombra_texto()) if self.param("titulo") else None
        self.pontos = []
        pts = self.param("pontos") or []
        n = max(1, len(pts))
        for i, ptx in enumerate(pts):
            txt = str(ptx).lstrip("•- ").strip()
            r = G.render_texto(txt, e["fonte_forte"], self.px(46), self.cor("texto"), largura_max=self.W * 0.78,
                               alinhamento="esquerda", cor_destaque=self.cor("destaque"), fonte_destaque=e["fonte_destaque"],
                               sombra=self.sombra_texto(0.8))
            dot = G.circulo(int(self.px(16)), self.cor("destaque"))
            lin = Image.new("RGBA", (int(r.img.width + self.px(40)), r.img.height), (0, 0, 0, 0))
            asc = G.fonte(e["fonte_forte"], self.px(46)).getmetrics()[0]
            lin.alpha_composite(dot, (int(r.pad), int(r.pad + asc * 0.62 - dot.height / 2)))
            lin.alpha_composite(r.img, (int(self.px(40)), 0))
            r.img = lin
            self.pontos.append((r, self.t0 + 0.7 + i * max(0.5, (self.dur - 1.5) / n)))
        # área do conteúdo
        topo = self.px(140)
        if self.tit:
            topo += self.tit.img.height + self.px(20)
        base_area = (self.pip_c[1] - hpip / 2 - self.px(40)) if alt == "inf" else self.H - self.px(240)
        if self.pontos:
            base_area -= sum(r.img.height for r, _ in self.pontos) + self.px(30)
        if alt == "sup":
            topo = max(topo, self.pip_c[1] + hpip / 2 + self.px(40))
        self.area = (self.px(46), topo, self.W - 2 * self.px(46), max(self.px(200), base_area - topo))

    def aplicar(self, img, t):
        W, H = self.W, self.H
        q, pi, po = self.progresso(t)
        bg = self.fundo(img, 1.0)
        out = bg
        # conteúdo
        if self.conteudo:
            x, y, w, h = self.area
            so_texto = self.conteudo.get("texto") and not (self.conteudo.get("midia") or self.conteudo.get("imagem"))
            estatico = so_texto or bool(self.conteudo.get("imagem")) or self.ctx.bib.e_imagem(self.conteudo.get("midia", "")) \
                if not so_texto and self.conteudo.get("midia") else True
            c = getattr(self, "_c_cache", None) if estatico else None
            if c is None:
                if so_texto:
                    c = G.com_sombra_ret(_cartao_item(self.conteudo, self, w, h, t, img), self.px(32), self.px(36), 0,
                                         self.px(18), 0.35)
                elif self.param("ajustar_conteudo", True):
                    fr = self.quadro_de(self.conteudo, t, img, (int(w), int(h)))
                    fit = G.cantos(G.conter(fr, w, h).convert("RGBA"), self.px(26))
                    c = G.com_sombra_ret(fit, self.px(26), self.px(26), 0, self.px(14), 0.45)
                else:
                    c = G.com_sombra_ret(self.painel(self.conteudo, t, img, w, h, self.px(30)), self.px(30), self.px(26), 0,
                                         self.px(14), 0.45)
                if estatico:
                    self._c_cache = c
            out = G.colar(out, c, x + w / 2, y + h / 2 + self.px(60) * (1 - q), (0.5, 0.5), 0.94 + 0.06 * q, 0, q)
        if self.tit:
            out = G.colar(out, self.tit.img, self.px(46) - self.tit.pad, self.px(120), (0, 0), 1, 0, q)
        if self.pontos:
            y = self.area[1] + self.area[3] + self.px(30)
            for r, tt in self.pontos:
                p = clamp((t - tt) / 0.35) * (1 - po)
                out = G.colar(out, r.img, self.px(46) - r.pad - self.px(30) * (1 - entrada(p)), y, (0, 0), 1, 0, p)
                y += r.img.height
        # vídeo principal encolhendo até o PiP
        cx = lerp(W / 2, self.pip_c[0], q)
        cy = lerp(H / 2, self.pip_c[1], q)
        w = lerp(W, self.pip_wh[0], q)
        h = lerp(H, self.pip_wh[1], q)
        raio = lerp(0, (min(w, h) / 2) if self.forma == "circulo" else self.px(30), q)
        # janela de recorte da base com o aspecto atual, centrada no rosto (região superior)
        asp = w / max(1, h)
        bw = min(W, H * asp)
        bh = bw / asp
        foco_y = lerp(0.5, 0.42, q)
        x0 = (W - bw) / 2
        y0 = min(max(H * foco_y - bh / 2, 0), H - bh)
        rec = img.resize((max(2, int(w)), max(2, int(h))), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh)).convert("RGBA")
        rec = G.cantos(rec, raio)
        if q > 0.02 and self.borda:
            rec = G.borda_em(rec, raio, self.cor(self.borda), max(2, self.px(5)) * q)
        rec = G.com_sombra_ret(rec, raio, self.px(26) * q + 1, 0, self.px(12) * q, 0.5 * q)
        out = G.colar(out, rec, cx, cy, (0.5, 0.5))
        return out

    def sons_extra(self):
        return [(tt, "pop", 0.2) for _, tt in self.pontos] + [(self.t1 - self.d_out, "swish", 0.18)]


@registrar("broll", "b_roll", "cobertura", "inserir_video", "inserir_imagem", "mostrar", "corte_para", "cutaway",
           "tela_cheia")
class BRoll(_Cena):
    """Cobertura em tela cheia (b-roll): mostra outra mídia por cima do vídeo principal, mantendo a voz.
    midia (vídeo ou imagem), de (início na mídia), velocidade, enquadrar ('cobrir' | 'ajustar'), movimento (imagens:
    'kenburns' | 'zoom_out' | 'pan' | 'nenhum'), transicao ('corte' | 'fade' | 'zoom' | 'deslizar' | 'desfoque'),
    audio (volume do som do b-roll, padrão 0), abafar_voz (0..1, reduz a voz durante o b-roll), cor (look)."""
    som_entrada = None

    def preparar(self):
        self.ref = self.param("midia", self.param("imagem"))
        self.fonte = {"midia": self.ref, "de": num(self.param("de"), 0.0), "velocidade": num(self.param("velocidade"), 1.0)}
        self.modo = str(self.param("enquadrar", "cobrir"))
        self.mov = str(self.param("movimento", "kenburns"))
        tr = self.param("transicao", "corte")
        self.tr = tr.get("tipo", "fade") if isinstance(tr, dict) else str(tr)
        self.d_tr = num(tr.get("duracao"), 0.3) if isinstance(tr, dict) else 0.3
        if self.tr in ("deslizar", "zoom", "fade", "desfoque") and self.spec.get("som") is None:
            self.som_entrada = "whoosh" if self.tr != "fade" else None
        self.img_fixa = self.ctx.bib.e_imagem(self.ref)

    def _quadro(self, t, base):
        W, H = self.W, self.H
        if self.img_fixa:
            im = self.ctx.bib.imagem(self.ref).convert("RGB")
            p = clamp((t - self.t0) / self.dur)
            z, f = 1.0, (0.5, 0.5)
            if self.mov in ("kenburns", "zoom_in"):
                z = 1.0 + 0.12 * suave(p)
            elif self.mov == "zoom_out":
                z = 1.12 - 0.12 * suave(p)
            elif self.mov in ("pan", "pan_dir"):
                z, f = 1.12, (0.35 + 0.3 * suave(p), 0.5)
            if self.modo == "ajustar" or (self.modo == "auto" and not 0.6 < (im.width / im.height) / (W / H) < 1.6):
                from ..linha import enquadrar_ajustado
                return enquadrar_ajustado(im, W, H, z)
            return G.cobrir(im, W, H, f, z)
        fr = self.quadro_de(self.fonte, t, base, (W, H))
        if self.modo == "ajustar":
            from ..linha import enquadrar_ajustado
            return enquadrar_ajustado(fr, W, H)
        return G.cobrir(fr, W, H)

    def aplicar(self, img, t):
        fr = self._quadro(t, img)
        if self.param("cor"):
            fr = self.ctx.aplicar_grade(fr, self.param("cor"))
        W, H = self.W, self.H
        pi = clamp((t - self.t0) / self.d_tr)
        po = clamp((t - (self.t1 - self.d_tr)) / self.d_tr)
        if self.tr == "corte" or (pi >= 1 and po <= 0):
            return fr
        k = pi if pi < 1 else 1 - po
        q = easing("expo_io")(k)
        if self.tr == "fade":
            return Image.blend(img, fr, q)
        if self.tr == "zoom":
            s = 1.25 - 0.25 * q
            z = fr.resize((int(W * s), int(H * s)), Image.BICUBIC)
            z = z.crop(((z.width - W) // 2, (z.height - H) // 2, (z.width - W) // 2 + W, (z.height - H) // 2 + H))
            return Image.blend(img, z, q)
        if self.tr == "desfoque":
            r = self.px(30) * (1 - q)
            return Image.blend(G.desfocar(img, self.px(30) * q), G.desfocar(fr, r), q)
        if self.tr == "deslizar":
            out = img.copy()
            out.paste(fr, (int(W * (1 - q)), 0))
            return out
        return fr

    def faixas_audio(self):
        v = num(self.param("audio"), 0.0)
        if v <= 0 or self.img_fixa:
            return []
        de = self.fonte["de"]
        vel = self.fonte["velocidade"]
        return [(self.t0, self.ref, de, de + self.dur * vel, vel, v)]

    def abafar_voz(self):
        g = num(self.param("abafar_voz"), 0.0)
        return [(self.t0, self.t1, 1 - clamp(g))] if g > 0 else []


@registrar("pip", "picture_in_picture", "janela", "video_no_canto", "sobrepor_video", "overlay_video")
class PiP(Efeito):
    """Janela com outra mídia sobre o vídeo (picture-in-picture). midia, de, velocidade, posicao (padrão sup_dir),
    largura (0.4), proporcao (altura/largura; padrão a da mídia), forma ('arredondado' | 'circulo'), raio, borda
    (cor), audio (volume, padrão 0), rotulo (opcional)."""
    entrada_padrao = "pop"
    duracao_padrao = 4.0
    som_entrada = "pop"
    vol_som = 0.2

    def preparar(self):
        self.ref = self.param("midia", self.param("imagem"))
        self.fonte = {"midia": self.ref, "de": num(self.param("de"), 0.0), "velocidade": num(self.param("velocidade"), 1.0)}
        inf = self.ctx.bib.info(self.ref)
        self.w = self.W * num(self.param("largura"), 0.4)
        self.forma = str(self.param("forma", "arredondado"))
        prop = num(self.param("proporcao"), (inf["altura"] / max(1, inf["largura"])) if inf.get("largura") else 1.0)
        self.h = self.w if self.forma == "circulo" else self.w * prop
        self.raio = self.w / 2 if self.forma == "circulo" else self.px(num(self.param("raio"), 26))
        self.x, self.y = self.pos(None, "sup_dir")
        if self.spec.get("posicao") in (None, "sup_dir"):
            self.x = self.W - self.px(40) - self.w / 2
            self.y = self.px(170) + self.h / 2
        self.rot = _rotulo(self.param("rotulo"), self.s, self.e, tam=22) if self.param("rotulo") else None

    def area(self, t):
        return self.caixa(self.x, self.y, self.w, self.h, self.px(10))

    def aplicar(self, img, t):
        fr = self.quadro_de(self.fonte, t, img, (int(self.w), int(self.h)))
        pan = G.cobrir(fr, self.w, self.h).convert("RGBA")
        pan = G.cantos(pan, self.raio)
        if self.param("borda"):
            pan = G.borda_em(pan, self.raio, self.cor(self.param("borda")), max(2, self.px(6)))
        if self.rot is not None:
            pan.paste(self.rot, (int(self.px(14)), int(self.px(14))), self.rot)
        pan = G.com_sombra_ret(pan, self.raio, self.px(30), 0, self.px(16), 0.42)
        return self.colar_anim(img, pan, self.x, self.y, t)

    def faixas_audio(self):
        v = num(self.param("audio"), 0.0)
        if v <= 0 or self.ctx.bib.e_imagem(self.ref):
            return []
        de, vel = self.fonte["de"], self.fonte["velocidade"]
        return [(self.t0, self.ref, de, de + self.dur * vel, vel, v)]
