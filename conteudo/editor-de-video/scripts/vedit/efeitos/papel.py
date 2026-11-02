"""Motion de papel: um print/documento/notícia entra em 3D, flutua, recebe marca-texto e zoom no trecho."""
import math

import numpy as np
from PIL import Image, ImageDraw

from .. import grafico as G
from ..tempo import clamp, easing, entrada, expo_io, lerp, mola, suave
from ..util import num
from .base import Efeito, registrar


@registrar("papel", "motion_de_papel", "documento", "noticia", "manchete_jornal", "print_noticia", "artigo",
           "folha", "paper")
class Papel(Efeito):
    """Folha/print que entra girando em 3D e flutua. imagem (print de notícia, documento, post) OU gere um:
    titulo (manchete), texto (corpo), fonte_noticia (nome do veículo — use o nome real só se for um print real),
    data, subtitulo. destaque: {x, y, w, h} (0..1 dentro do papel) recebe marca-texto; zoom_destaque (ex. 1.5)
    aproxima nele; tempo_destaque (s após o início, padrão 1.2); largura (0.86), fundo ('escurecer' padrão |
    'desfoque' | 'nenhum'), inclinacao (graus finais, padrão 6)."""
    entrada_padrao = "nenhuma"
    duracao_padrao = 4.5
    som_entrada = "papel"
    vol_som = 0.35

    def preparar(self):
        W, H = self.W, self.H
        self.w = W * num(self.param("largura"), 0.86)
        ref = self.param("imagem", self.param("midia"))
        if ref:
            im = self.ctx.bib.imagem(ref)
            esc = self.w / im.width
            h = im.height * esc
            if h > H * 0.78:
                esc = H * 0.78 / im.height
            im = im.resize((max(1, int(im.width * esc)), max(1, int(im.height * esc))), Image.LANCZOS)
            borda = int(self.px(22))
            papel = Image.new("RGBA", (im.width + 2 * borda, im.height + 2 * borda), (252, 251, 248, 255))
            papel.paste(im, (borda, borda), im)
            self.papel = G.cantos(papel, self.px(12))
        else:
            self.papel = self._gerar()
        self.pw, self.ph = self.papel.size
        self.x, self.y = self.pos(None, "centro")
        self.incl = num(self.param("inclinacao"), 6)
        dst = self.param("destaque")
        self.dst = None
        if dst:
            self.dst = (num(dst.get("x"), 0.5), num(dst.get("y"), 0.4), num(dst.get("w"), 0.7), num(dst.get("h"), 0.06))
        self.t_dst = self.t0 + num(self.param("tempo_destaque"), 1.2)
        self.z_dst = num(self.param("zoom_destaque"), 1.0)
        self.cor_marca = self.cor(self.param("cor_marca", "#FFE14D"))

    def area(self, t):
        return self.caixa(self.x, self.y, self.pw * 1.04, self.ph * 1.04)

    def _gerar(self):
        e = self.e
        w = int(self.w)
        pad = int(self.px(56))
        tinta = (24, 24, 26, 255)
        cinza = (110, 108, 104, 255)
        blocos = []
        fonte_n = self.param("fonte_noticia", self.param("veiculo"))
        data = self.param("data")
        if fonte_n or data:
            cab = Image.new("RGBA", (w - 2 * pad, int(self.px(56))), (0, 0, 0, 0))
            if fonte_n:
                r = G.render_texto(str(fonte_n), e["fonte_forte"], self.px(30), self.cor(self.param("cor_veiculo", "perigo")),
                                   maiusculas=True, rastreio=self.px(3))
                cab.paste(r.img, (0, int(cab.height / 2 - r.img.height / 2)), r.img)
            if data:
                r = G.render_texto(str(data), e["fonte_texto"], self.px(26), cinza)
                cab.paste(r.img, (cab.width - r.img.width, int(cab.height / 2 - r.img.height / 2)), r.img)
            blocos.append(("img", cab, self.px(18)))
            blocos.append(("linha", None, self.px(26)))
        tit = self.param("titulo", self.param("manchete", ""))
        if tit:
            r = G.render_texto(str(tit), e["fonte_serif"], self.px(num(self.param("tamanho"), 62)), tinta,
                               largura_max=w - 2 * pad, alinhamento="esquerda", entrelinha=1.08,
                               cor_destaque=self.cor("destaque"), fonte_destaque=e["fonte_destaque"])
            blocos.append(("txt", r, self.px(18)))
        sub = self.param("subtitulo")
        if sub:
            r = G.render_texto(str(sub), e["fonte_texto"], self.px(34), cinza, largura_max=w - 2 * pad, alinhamento="esquerda")
            blocos.append(("txt", r, self.px(26)))
        capa = self.param("imagem_capa")
        if capa:
            im = self.ctx.bib.imagem(capa)
            cw = w - 2 * pad
            ch = int(cw * 0.56)
            blocos.append(("img", G.cantos(G.cobrir(im.convert("RGB"), cw, ch).convert("RGBA"), self.px(10)), self.px(26)))
        corpo = self.param("texto")
        if corpo:
            r = G.render_texto(str(corpo), e["fonte_texto"], self.px(32), (52, 52, 54, 255),
                               largura_max=w - 2 * pad, alinhamento="esquerda", entrelinha=1.35)
            blocos.append(("txt", r, 0))
        else:
            blocos.append(("linhas", 7, 0))
        alt = pad
        for tipo, obj, gap in blocos:
            if tipo == "txt":
                alt += obj.img.height - 2 * obj.pad + gap
            elif tipo == "img":
                alt += obj.height + gap
            elif tipo == "linha":
                alt += gap
            elif tipo == "linhas":
                alt += obj * self.px(44)
        alt += pad
        papel = G.textura_papel(w, int(alt), (251, 249, 244))
        papel = G.cantos(papel, self.px(14))
        d = ImageDraw.Draw(papel)
        y = pad
        for tipo, obj, gap in blocos:
            if tipo == "txt":
                papel.paste(obj.img, (pad - obj.pad, int(y - obj.pad)), obj.img)
                y += obj.img.height - 2 * obj.pad + gap
            elif tipo == "img":
                papel.paste(obj, (pad, int(y)), obj)
                y += obj.height + gap
            elif tipo == "linha":
                d.line([pad, y - gap / 2, w - pad, y - gap / 2], fill=(220, 216, 208), width=max(1, int(self.px(2))))
            elif tipo == "linhas":
                rng = np.random.default_rng(5)
                for k in range(obj):
                    lw = (w - 2 * pad) * (0.55 + 0.45 * rng.random() if k % 3 == 2 else 0.92 + 0.08 * rng.random())
                    d.rounded_rectangle([pad, y + self.px(12), pad + lw, y + self.px(26)], radius=self.px(7),
                                        fill=(214, 210, 202))
                    y += self.px(44)
        return papel

    def _com_marca(self, t):
        if not self.dst:
            return self.papel
        p = easing("entrada")(clamp((t - self.t_dst) / 0.5))
        if p <= 0:
            return self.papel
        x, y, w, h = self.dst
        X0 = (x - w / 2) * self.pw
        Y0 = (y - h / 2) * self.ph
        X1 = X0 + w * self.pw * p
        camada = Image.new("RGBA", self.papel.size, (0, 0, 0, 0))
        ImageDraw.Draw(camada).rounded_rectangle([X0, Y0, X1, Y0 + h * self.ph], radius=self.px(6),
                                                 fill=self.cor_marca[:3] + (125,))
        return Image.alpha_composite(self.papel, camada)

    def aplicar(self, img, t):
        u = t - self.t0
        pi = clamp(u / 0.9)
        po = easing("saida")(self.p_saida(t, max(0.4, self.d_out)))
        q = easing("expo_io")(pi)
        fundo = str(self.param("fundo", "escurecer"))
        k_f = (q * (1 - po))
        if fundo == "escurecer":
            img = Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), 0.45 * k_f)
        elif fundo == "desfoque":
            img = Image.blend(img, G.desfocar(img, self.px(28)), k_f)
        wob = math.sin(u * 1.4) * 2.0 * q
        rx = lerp(38, self.incl * 0.6, q) + wob * 0.6 + 30 * po
        ry = lerp(-26, -self.incl, q) + math.sin(u * 1.1 + 1) * 2.2 * q
        rz = lerp(-12, -2, q) + math.sin(u * 0.9) * 0.8 * q - 6 * po
        esc = lerp(0.72, 1.0, mola(pi, 0.6, 1.2)) * (1 - 0.1 * po)
        cx, cy = self.x, self.y + lerp(self.H * 0.35, 0, q) + self.H * 0.6 * po
        if self.dst and self.z_dst > 1.01:
            pz = suave(clamp((t - self.t_dst - 0.15) / 0.7)) * (1 - po)
            z = lerp(1.0, self.z_dst, pz)
            # desloca para levar o destaque ao centro
            dx = (0.5 - self.dst[0]) * self.pw * esc * (z - 1) * 1.0
            dy = (0.5 - self.dst[1]) * self.ph * esc * (z - 1) * 1.0
            esc *= z
            cx += dx
            cy += dy
        sp = self._com_marca(t)
        cantos = G.projetar_cartao(self.pw, self.ph, cx, cy, rx, ry, rz, esc, focal=self.px(2200))
        out_sp, (x0, y0) = G.perspectiva(sp, cantos)
        sombra = G.com_sombra(out_sp, self.px(42), self.px(8), self.px(28), 0.45)
        pad = (sombra.width - out_sp.width) / 2
        op = clamp(pi * 4) * (1 - clamp((po - 0.7) / 0.3))
        return G.colar(img, sombra, x0 - pad, y0 - pad, (0, 0), 1, 0, op)

    def sons_extra(self):
        out = []
        if self.dst:
            out.append((self.t_dst, "risco", 0.3))
        return out
