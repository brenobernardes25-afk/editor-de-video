"""Efeitos de texto: título, textos com recorte, elemento riscado, lista numerada, passos, contador, rodapé
(lower third), destaque de área (círculo/seta/sublinhado) e imagem/adesivo/marca d'água."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import grafico as G
from ..tempo import clamp, easing, entrada, expo, lerp, mola, suave, volta
from ..util import aviso, num
from .base import Efeito, registrar


def _fundo_legivel(W, H, y0, y1, forca=0.75, topo=False):
    """Gradiente escuro atrás de uma área de texto."""
    h = int(max(2, y1 - y0))
    a = np.linspace(0, 1, h, dtype=np.float32)
    if topo:
        a = a[::-1]
    a = (np.clip(a * 1.25, 0, 1) ** 1.2) * 255 * forca
    m = Image.fromarray(np.repeat(a[:, None], W, axis=1).astype(np.uint8), "L")
    g = Image.new("RGBA", (W, h), (0, 0, 0, 255))
    g.putalpha(m)
    return g


def _ponto(d, c):
    return G.circulo(d, c)


def _caixa_palavra(r, i, pad_y=0.35, pad_b=0.7):
    """Recorte (caixa) da palavra i de um TextoRender, com margem para acentos e descendentes."""
    x0, y0, x1, y1 = r.palavras[i][:4]
    p = r.pad
    return (int(max(0, x0 - p * 0.5)), int(max(0, y0 - p * pad_y)), int(min(r.img.width, x1 + p * 0.5)),
            int(min(r.img.height, y1 + p * pad_b)))


@registrar("titulo", "texto", "title", "texto_animado", "headline", "chamada_texto", "manchete", "frase")
class Titulo(Efeito):
    """Texto animado. texto (aceita *cor de destaque*, _ênfase_ na fonte de destaque do estilo, ==etiqueta==
    e \\n), sobretitulo (rótulo pequeno acima, ex. 'EDIÇÃO AUTOMÁTICA'; sobretitulo_estilo 'pilula' | 'texto'),
    subtitulo, icone (opcional no rótulo, ex. 'raio', 'chip'), posicao (sem posição, no vídeo vertical o título
    desvia sozinho do rosto e de cartões ativos), tamanho (px em 1080, padrão 96),
    fonte ('fonte_titulo' | 'fonte_pesada' | 'fonte_impacto' | nome), cor, alinhamento, largura (0..1),
    maiusculas, rastreio (espaço extra entre letras, fração do tamanho), fundo: None | 'cartao' (vidro fosco) |
    'faixa' | 'caixa' | 'gradiente' | cor, animacao: 'mascara' (padrão: as palavras sobem de dentro de uma
    máscara) | 'desfoque' (palavras surgem do desfoque) | 'palavra' (pop palavra a palavra) | 'revelar' (linha a
    linha) | 'digitar' | 'letra' | 'subir' | 'pop' | 'mola' | 'zoom' | 'fade', saida: 'fade' | 'subir' |
    'encolher' | 'nenhuma'."""
    entrada_padrao = "subir"
    som_entrada = "swish"
    vol_som = 0.18

    POR_PALAVRA = ("mascara", "palavra", "palavras", "word", "desfoque", "blur")

    def preparar(self):
        e = self.e
        self.animacao = str(self.param("animacao", self.param("animação", "mascara")))
        if self.animacao in ("subir", "pop", "mola", "zoom", "fade", "girar", "esquerda", "direita", "descer"):
            self.anim_in = self.animacao
        elif self.animacao in self.POR_PALAVRA + ("revelar", "recorte", "digitar", "letra", "maquina", "typewriter"):
            self.anim_in = "nenhuma"  # a entrada é feita palavra a palavra / letra a letra
        tam = num(self.param("tamanho"), 96)
        nf = self.param("fonte", "fonte_titulo")
        nf = e.get(nf, nf)
        larg = num(self.param("largura"), 0.86) * self.W
        self.alinh = self.param("alinhamento", "centro")
        fundo = self.param("fundo")
        self.fundo = fundo
        sombra = self.param("sombra", fundo in (None, "gradiente", False))
        cor_txt = self.param("cor", "texto")
        if fundo == "faixa":
            cor_txt = self.param("cor", "texto_escuro" if G.luminancia(self.cor(self.param("cor_faixa", "destaque"))) > 0.55 else "texto")
        elif fundo == "cartao":
            cor_txt = self.param("cor", self.cores_cartao()[0])
        maius = bool(self.param("maiusculas", e.get("titulo_maiusculas", False)))
        rast = num(self.param("rastreio"), e.get("titulo_rastreio", 0.0)) * self.px(tam)
        kw = dict(largura_max=larg, alinhamento=self.alinh, maiusculas=maius,
                  contorno=self.px(num(self.param("contorno"), 0)), cor_contorno=self.cor(self.param("cor_contorno", "#000000")),
                  cor_destaque=self.cor(self.param("cor_destaque", "destaque")), fonte_destaque=e["fonte_destaque"],
                  escala_destaque=num(self.param("escala_destaque"), e.get("escala_destaque", 1.0)),
                  entrelinha=num(self.param("entrelinha"), 1.04), marca_solida=bool(e.get("marca_solida", True)),
                  rastreio=rast)
        self.sombras = self.sombra_texto() if sombra else None
        if fundo == "caixa":
            cc = self.cor(self.param("cor_caixa", "destaque"))
            kw["caixa"] = cc
            kw["caixa_pad"] = (self.px(26), self.px(12))
            kw["caixa_raio"] = self.px(14)
            if self.param("cor") is None:
                cor_txt = G.contraste_para(cc)
            self.sombras = None
        if self.animacao in ("digitar", "letra", "maquina", "typewriter"):
            kw["alinhamento"] = "esquerda"  # cresce da esquerda sem 'dançar'
        self.kw = kw
        self.nf, self.tam = nf, tam
        self.txt = str(self.param("texto", ""))
        self.cor_txt = cor_txt
        # versão sem sombra (animação palavra a palavra) e versão final com sombra
        self.r0 = G.render_texto(self.txt, nf, self.px(tam), self.cor(cor_txt), **kw)
        self.r = G.render_texto(self.txt, nf, self.px(tam), self.cor(cor_txt), sombra=self.sombras, **kw) \
            if self.sombras else self.r0
        partes = []
        st = self.param("sobretitulo")
        ic = self.param("icone")
        if st or ic:
            partes.append(("sobre", self._rotulo(st, ic)))
        partes.append(("principal", None))
        sub = self.param("subtitulo")
        if sub:
            cs = self.cores_cartao()[1] if fundo == "cartao" else self.cor(self.param("cor_subtitulo", "texto_suave"))
            rsub = G.render_texto(str(sub), e["fonte_texto"], self.px(num(self.param("tamanho_subtitulo"), 40)),
                                  cs if fundo != "cartao" else cs, largura_max=larg, alinhamento=self.alinh,
                                  cor_destaque=self.cor("destaque"), fonte_destaque=e["fonte_destaque"],
                                  entrelinha=1.2, sombra=self.sombra_texto(0.8) if sombra else None)
            partes.append(("sub", rsub.img))
        self.partes = partes
        self.gap = self.px(num(self.param("espaco"), 22))
        self._layout()
        self._cache_n = {}
        self.stag = num(self.param("intervalo_palavras"), 0.065)
        self.d_pal = num(self.param("duracao_palavra"), 0.6)
        n = max(1, len(self.r0.palavras))
        self.t_fim_anim = self.t0 + (n - 1) * self.stag + self.d_pal
        # sem posição pedida (vídeo vertical): desvia do rosto e de outros elementos na primeira vez que aparece
        self._auto = self.spec.get("posicao") is None and self.H > self.W and not self.spec.get("_cartao_tela")
        self._posicionado = False

    def area(self, t):
        x0, y0, x1, y1 = self.caixa_total
        m = self.px(54) if self.fundo == "cartao" else self.px(12)
        if self.fundo == "faixa":
            return (0, y0 - self.px(30), self.W, y1 + self.px(30))
        return (x0 - m, y0 - m, x1 + m, y1 + m)

    def _posicionar(self):
        self._posicionado = True
        H, W = self.H, self.W
        x0, y0, x1, y1 = self.area(self.t0)
        bh, bw = y1 - y0, x1 - x0
        tm = self.t0 + min(0.6, self.dur / 2)
        obst = []
        rosto = self.ctx.rosto_saida(tm)
        if rosto:
            cx, cy, tam = rosto
            fh = tam * H * 1.45  # cabeça inteira, com cabelo e queixo
            obst.append(self.caixa(cx * W, cy * H, fh * 0.9, fh))
        obst += self.ctx.areas_ocupadas(tm, exceto=self, tipos_ignorar=("legendas", "titulo"))
        if not obst:
            return
        y_def = (y0 + y1) / 2

        def colide(yc):
            b = (W / 2 - bw / 2, yc - bh / 2, W / 2 + bw / 2, yc + bh / 2)
            return any(not (b[2] < a[0] or b[0] > a[2] or b[3] < a[1] or b[1] > a[3]) for a in obst)
        if not colide(y_def):
            return
        lo, hi = H * 0.09 + bh / 2, H * 0.64 - bh / 2
        cands = []
        for a in obst:
            cands += [a[1] - self.px(24) - bh / 2, a[3] + self.px(24) + bh / 2]
        cands += [H * f for f in (0.14, 0.2, 0.34, 0.42, 0.5, 0.56)]
        cands = sorted((c for c in cands if lo <= c <= hi), key=lambda c: (abs(c - y_def) > H * 0.2, c > y_def, abs(c - y_def)))
        for c in cands:
            if not colide(c):
                self.spec["posicao"] = [self.cx / W, (c - y_def + self.cy) / H]
                self._layout()
                return

    def _rotulo(self, st, ic):
        e = self.e
        estilo_r = str(self.param("sobretitulo_estilo", "pilula"))
        cd = self.cor(self.param("cor_sobretitulo", "destaque"))
        icone = None
        if ic:
            icone = G.icone(ic, self.px(num(self.param("tamanho_icone"), 30 if st else 64)), self.cor(self.param("cor_icone", "destaque")))
        if not st:
            return icone
        if estilo_r == "pilula":
            ponto = icone if icone is not None else _ponto(int(self.px(13)), cd)
            c = G.pilula(str(st), e, self.s, mat="preto", tam=num(self.param("tamanho_sobretitulo"), 28),
                         icone_img=ponto, pad_x=24, pad_y=13)
            return c.sprite
        rs = G.render_texto(str(st), e["fonte_rotulo"], self.px(num(self.param("tamanho_sobretitulo"), 26)), cd,
                            maiusculas=True, rastreio=self.px(4), sombra=self.sombra_texto(0.7))
        if icone is None:
            return rs.img
        gap = int(self.px(12))
        w = icone.width + gap + rs.img.width
        h = max(icone.height, rs.img.height)
        lin = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        lin.paste(icone, (0, (h - icone.height) // 2), icone)
        lin.paste(rs.img, (icone.width + gap, (h - rs.img.height) // 2), rs.img)
        return lin

    def _layout(self):
        ws = [self.r.img.width if p[0] == "principal" else p[1].width for p in self.partes]
        hs = [self.r.img.height if p[0] == "principal" else p[1].height for p in self.partes]
        # as partes encostam pelo texto, não pela margem de sombra
        self.bw = max(ws)
        self.bh = sum(hs) + self.gap * (len(hs) - 1)
        x, y = self.pos(None, "terco_superior")
        self.cx, self.cy = x, y
        topo = y - self.bh / 2
        self.offs = []
        for (nome, im), w, h in zip(self.partes, ws, hs):
            if self.alinh in ("esquerda", "esq", "left"):
                ox = x - self.bw / 2
            elif self.alinh in ("direita", "dir", "right"):
                ox = x + self.bw / 2 - w
            else:
                ox = x - w / 2
            self.offs.append((nome, im, ox, topo))
            topo += h + self.gap
        # caixa do texto visível (sem as margens de sombra) para cartões e faixas
        m = self.r.pad
        self.caixa_total = (x - self.bw / 2 + m * 0.6, y - self.bh / 2 + m * 0.6, x + self.bw / 2 - m * 0.6,
                            y + self.bh / 2 - m * 0.6)

    def _fundo(self, img, t):
        f = self.fundo
        if not f or f in ("caixa",):
            return img
        a = self.anim(t)
        if self.anim_in == "nenhuma":
            a = dict(a, op=a["op"] * clamp(self.p_entrada(t, 0.35) * 1.0), dy=a["dy"] + self.px(30) * (1 - expo(self.p_entrada(t, 0.6))))
        x0, y0, x1, y1 = self.caixa_total
        if f == "gradiente":
            W, H = self.W, self.H
            em_cima = self.cy < H * 0.45
            if em_cima:
                g = _fundo_legivel(W, H, 0, y1 + self.px(180), 0.82, topo=True)
                return G.colar(img, g, 0, 0, (0, 0), 1, 0, a["op"])
            g = _fundo_legivel(W, H, y0 - self.px(180), H, 0.82)
            return G.colar(img, g, 0, y0 - self.px(180), (0, 0), 1, 0, a["op"])
        pad_x, pad_y = self.px(54), self.px(44)
        if f == "faixa":
            w, h = self.W * 1.1, (y1 - y0) + pad_y * 1.1
            card = Image.new("RGBA", (int(w), int(h)), self.cor(self.param("cor_faixa", "destaque")))
            prog = easing("expo")(self.p_entrada(t, max(0.3, self.d_in * 0.9)))
            prog *= 1 - easing("saida")(self.p_saida(t))
            card = card.crop((0, 0, max(1, int(w * prog)), int(h)))
            return G.colar(img, card, -self.W * 0.05, (y0 + y1) / 2, (0, 0.5), 1, -2.0, 1.0)
        w, h = (x1 - x0) + 2 * pad_x, (y1 - y0) + 2 * pad_y
        if f == "cartao":
            if not hasattr(self, "_card"):
                self._card = self.cartao(w, h)
            return self.colar_cartao(img, self._card, (x0 + x1) / 2, (y0 + y1) / 2, a=a)
        cc = self.cor(f)
        if not hasattr(self, "_card_cor"):
            self._card_cor = G.cartao(w, h, self.px(self.e["raio"]), self.e,
                                      {"tipo": "solido", "tinta": cc, "opacidade": cc[3] / 255.0, "borda": 0, "brilho": 0,
                                       "texto": "escuro" if G.luminancia(cc) > 0.6 else "claro"}, s=self.s)
        return self.colar_cartao(img, self._card_cor, (x0 + x1) / 2, (y0 + y1) / 2, a=a)

    def _principal_em(self, t):
        """Sprite do texto principal conforme a animação de digitação/letra."""
        if self.animacao not in ("digitar", "letra", "maquina", "typewriter"):
            return self.r.img
        limpo = G.tirar_marcas(self.txt)
        vel = num(self.param("velocidade"), 22)  # caracteres por segundo
        n = int(clamp((t - self.t0) * vel / max(1, len(limpo))) * len(limpo))
        if n >= len(limpo):
            return self.r.img
        cont = 0
        bruto = []
        for ch in self.txt:
            if ch in "*_=":
                bruto.append(ch)
                continue
            if cont >= n:
                break
            bruto.append(ch)
            cont += 1
        s = "".join(bruto)
        for m in ("**", "*", "==", "_"):
            if s.count(m) % 2 == 1:
                s += m
        cursor = "|" if (int(t * 2.4) % 2 == 0 and self.animacao != "letra") else ""
        k = (n, cursor)
        if k not in self._cache_n:
            r = G.render_texto(s + cursor, self.nf, self.px(self.tam), self.cor(self.cor_txt), sombra=self.sombras,
                               **self.kw)
            base = Image.new("RGBA", self.r.img.size, (0, 0, 0, 0))
            base.paste(r.img, (0, 0), r.img)
            self._cache_n = {k: base}
        return self._cache_n[k]

    def aplicar(self, img, t):
        if self._auto and not self._posicionado:
            self._posicionar()
        img = self._fundo(img, t)
        a = self.anim(t)
        por_palavra = self.animacao in self.POR_PALAVRA
        for (nome, im, ox, oy) in self.offs:
            if nome != "principal":
                if por_palavra or self.animacao in ("revelar", "recorte"):
                    # rótulo e subtítulo entram suaves junto com as palavras
                    p = clamp((t - self.t0 - (0.0 if nome == "sobre" else 0.18)) / 0.45)
                    q = easing("expo")(p)
                    ps = easing("saida")(self.p_saida(t))
                    img = G.colar(img, im, ox, oy + self.px(18) * (1 - q), (0, 0), 1, 0, clamp(p * 2) * (1 - ps))
                else:
                    img = G.colar(img, im, ox + a["dx"], oy + a["dy"], (0, 0), 1, 0, a["op"])
                continue
            if por_palavra:
                img = self._por_palavra(img, t, ox, oy)
            elif self.animacao in ("revelar", "recorte"):
                img = self._revelar(img, t, ox, oy)
            else:
                sp = self._principal_em(t)
                if a["esc"] != 1 or a["rot"] != 0:
                    img = G.colar(img, sp, ox + sp.width / 2 + a["dx"], oy + sp.height / 2 + a["dy"], (0.5, 0.5),
                                  a["esc"], a["rot"], a["op"])
                else:
                    img = G.colar(img, sp, ox + a["dx"], oy + a["dy"], (0, 0), 1, 0, a["op"])
        return img

    def _por_palavra(self, img, t, ox, oy):
        ps = easing("saida")(self.p_saida(t))
        if t >= self.t_fim_anim and ps <= 0:
            return G.colar(img, self.r.img, ox, oy, (0, 0))
        r = self.r0
        anim = self.animacao
        # compõe as palavras (sem sombra) num quadro do tamanho do render final e aplica a sombra no conjunto
        off = self.r.pad - r.pad
        quadro = Image.new("RGBA", self.r.img.size, (0, 0, 0, 0))
        for i in range(len(r.palavras)):
            p = clamp((t - self.t0 - i * self.stag) / self.d_pal)
            if p <= 0:
                continue
            box = _caixa_palavra(r, i)
            sp = r.img.crop(box)
            if anim == "mascara":
                q = easing("expo")(p)
                hh = sp.height
                dy = int(round(hh * 0.92 * (1 - q) - hh * 0.55 * ps))
                jan = Image.new("RGBA", sp.size, (0, 0, 0, 0))
                G.compor(jan, sp, 0, dy)
                if ps > 0:
                    jan = G.opacidade_img(jan, 1 - ps)
                G.compor(quadro, jan, box[0] + off, box[1] + off)
            elif anim in ("desfoque", "blur"):
                q = easing("entrada")(p)
                raio = self.px(16) * (1 - q)
                if raio > 0.6:
                    m = int(raio * 2)
                    sp2 = Image.new("RGBA", (sp.width + 2 * m, sp.height + 2 * m), (0, 0, 0, 0))
                    sp2.paste(sp, (m, m))
                    sp2 = sp2.filter(ImageFilter.GaussianBlur(raio))
                else:
                    m, sp2 = 0, sp
                esc = 1.08 - 0.08 * q
                sp2 = G.opacidade_img(sp2, clamp(p * 1.6) * (1 - ps))
                if abs(esc - 1) > 1e-3:
                    sp2 = G.transformar(sp2, esc, 0)
                cx = box[0] + off + sp.width / 2
                cy = box[1] + off + sp.height / 2
                G.compor(quadro, sp2, cx - sp2.width / 2, cy - sp2.height / 2)
            else:  # 'palavra': pop com leve subida
                q = volta(p, 1.5)
                esc = 0.86 + 0.14 * q
                sp2 = G.transformar(sp, esc, 0) if abs(esc - 1) > 1e-3 else sp
                sp2 = G.opacidade_img(sp2, clamp(p * 2.2) * (1 - ps))
                cx = box[0] + off + sp.width / 2
                cy = box[1] + off + sp.height / 2 + self.px(28) * (1 - easing("expo")(p))
                G.compor(quadro, sp2, cx - sp2.width / 2, cy - sp2.height / 2)
        if self.sombras:
            quadro = G._sombras(quadro, self.sombras if ps <= 0 else
                                [dict(s_, opacidade=s_["opacidade"] * (1 - ps)) for s_ in self.sombras])
        return G.colar(img, quadro, ox, oy, (0, 0))

    def _revelar(self, img, t, ox, oy):
        r = self.r
        stag = num(self.param("intervalo_linhas"), 0.12)
        ps = easing("saida")(self.p_saida(t))
        for i, (x0, y0, x1, y1) in enumerate(r.linhas):
            pad = r.pad
            box = (int(max(0, x0 - pad)), int(max(0, y0 - pad * 0.3)), int(min(r.img.width, x1 + pad)),
                   int(min(r.img.height, y1 + pad * 0.6)))
            sp = r.img.crop(box)
            p = easing("expo")(clamp((t - self.t0 - i * stag) / 0.6))
            janela = Image.new("RGBA", sp.size, (0, 0, 0, 0))
            dy = int(sp.height * (1 - p)) - int(sp.height * ps * 0.6)
            G.compor(janela, sp, 0, dy)
            img = G.colar(img, janela, ox + box[0], oy + box[1], (0, 0), 1, 0, 1 - ps)
        return img

    def sons_extra(self):
        if self.animacao in ("digitar", "maquina", "typewriter"):
            limpo = G.tirar_marcas(self.txt)
            vel = num(self.param("velocidade"), 22)
            return [(self.t0 + k / vel, "tecla", 0.12) for k in range(0, len(limpo), 2) if self.t0 + k / vel < self.t1]
        return []


@registrar("texto_recorte", "textos_com_recorte", "recorte", "texto_mascara", "texto_vazado", "knockout",
           "texto_adesivo", "adesivo_texto")
class TextoRecorte(Efeito):
    """Texto com recorte. modo: 'revelar' (linhas surgem de uma máscara; 'faixas': true põe faixas de cor atrás
    de cada linha), 'vazado' (tela escura com o vídeo aparecendo DENTRO das letras; 'atravessar': true faz a
    câmera passar pelas letras no fim), 'adesivo' (texto recortado como adesivo, contorno branco grosso e sombra).
    texto, tamanho (automático no vazado; 150 revelar; 96 adesivo), fonte (padrão 'fonte_impacto', letras altas),
    cor, cores_faixas, posicao, maiusculas (padrão true)."""
    entrada_padrao = "fade"
    som_entrada = "whoosh"
    vol_som = 0.22

    def preparar(self):
        nome = str(self.spec.get("tipo", ""))
        modo = self.param("modo")
        if not modo:
            modo = "vazado" if ("vazado" in nome or "knockout" in nome) else "adesivo" if "adesivo" in nome else "revelar"
        if modo in ("atras", "atras_da_pessoa", "behind"):
            aviso("texto_recorte modo 'atras' precisa de segmentação de pessoa (não disponível) — usando 'adesivo'")
            modo = "adesivo"
        self.modo = modo
        e = self.e
        maius = bool(self.param("maiusculas", True))
        txt = str(self.param("texto", ""))
        fpad = "fonte_pesada" if modo == "adesivo" else "fonte_impacto"
        nf = e.get(self.param("fonte", fpad), self.param("fonte", fpad))
        W, H = self.W, self.H
        if modo == "vazado":
            self.oculta_legendas = True
            kw = dict(maiusculas=maius, entrelinha=0.9, cor_destaque=(255, 255, 255, 255))
            if self.param("tamanho") is None:
                # tamanho automático: as letras ocupam ~90% da largura (ou 46% da altura)
                r0 = G.render_texto(txt, nf, 200, (255, 255, 255, 255), **kw)
                k = min(W * 0.9 / max(1, r0.img.width - 2 * r0.pad), H * 0.46 / max(1, r0.img.height - 2 * r0.pad))
                tam = 200 * k
            else:
                tam = self.px(num(self.param("tamanho"), 150))
                tam = G.ajustar_tamanho(txt.upper() if maius else txt, nf, tam, W * 0.92, minimo=self.px(40))
            r = G.render_texto(txt, nf, tam, (255, 255, 255, 255), largura_max=W * 0.96, **kw)
            self.mask_txt = r.img.getchannel("A")
            self.cor_tela = self.cor(self.param("cor_fundo", "fundo"))
            self.op_tela = num(self.param("opacidade"), 0.96)
        elif modo == "adesivo":
            tam = self.px(num(self.param("tamanho"), 96))
            cor_t = self.cor(self.param("cor", "destaque"))
            r = G.render_texto(txt, nf, tam, cor_t, largura_max=W * 0.84, maiusculas=maius, entrelinha=0.98,
                               contorno=self.px(num(self.param("contorno"), 16)),
                               cor_contorno=self.cor(self.param("cor_contorno", "#FFFFFF")),
                               cor_destaque=self.cor(self.param("cor_destaque", "texto_escuro")))
            self.sprite = G.com_sombra(r.img, self.px(22), 0, self.px(14), 0.42)
            self.rot = num(self.param("rotacao"), -4)
        else:
            tam = self.px(num(self.param("tamanho"), 150))
            self.faixas = bool(self.param("faixas", False))
            cor_t = self.param("cor", "texto")
            larg = W * 0.9
            tam = G.ajustar_tamanho(txt.upper() if maius else txt, nf, tam, larg, minimo=self.px(40))
            self.r = G.render_texto(txt, nf, tam, self.cor(cor_t), largura_max=larg, maiusculas=maius,
                                    entrelinha=1.0 if self.faixas else 0.96, alinhamento=self.param("alinhamento", "centro"),
                                    cor_destaque=self.cor(self.param("cor_destaque", "destaque")),
                                    fonte_destaque=e["fonte_destaque"],
                                    sombra=None if self.faixas else self.sombra_texto())
            f = G.fonte(nf, tam)
            self.asc = f.getmetrics()[0]
            try:
                self.cap = -f.getbbox("H", anchor="ls")[1]
            except Exception:
                self.cap = self.asc * 0.72
            self.maius = maius
        self.x, self.y = self.pos(None, "centro")

    def area(self, t):
        if self.modo == "vazado":
            return None
        if self.modo == "adesivo":
            return self.caixa(self.x, self.y, self.sprite.width * 0.8, self.sprite.height * 0.8)
        r = self.r
        return self.caixa(self.x, self.y, r.img.width - 2 * r.pad + self.px(44), r.img.height - 2 * r.pad)

    def aplicar(self, img, t):
        if self.modo == "vazado":
            return self._vazado(img, t)
        if self.modo == "adesivo":
            p = self.p_entrada(t, 0.5)
            esc = 0.3 + 0.7 * mola(p, 0.5, 2.2) if p < 1 else 1.0
            po = self.p_saida(t)
            esc *= 1 - 0.25 * easing("saida")(po)
            op = clamp(p * 5) * (1 - easing("saida")(po))
            bob = math.sin((t - self.t0) * 2.2) * self.px(3)
            return G.colar(img, self.sprite, self.x, self.y + bob, (0.5, 0.5), esc, self.rot + 3 * (1 - clamp(p * 1.5)), op)
        r = self.r
        ox = self.x - r.img.width / 2
        oy = self.y - r.img.height / 2
        stag = num(self.param("intervalo_linhas"), 0.12)
        ps = easing("saida")(self.p_saida(t))
        cores = self.param("cores_faixas", ["destaque", "#FFFFFF", "#0B0B0C"])
        for i, (x0, y0, x1, y1) in enumerate(r.linhas):
            t_l = self.t0 + i * stag
            pad = r.pad
            box = (int(max(0, x0 - pad)), int(max(0, y0 - pad * 0.2)), int(min(r.img.width, x1 + pad)),
                   int(min(r.img.height, y1 + pad * 0.5)))
            sp = r.img.crop(box)
            if self.faixas:
                pf = easing("expo")(clamp((t - t_l) / 0.42))
                fw = int((x1 - x0 + self.px(44)) * pf * (1 - ps))
                c = self.cor(cores[i % len(cores)])
                if self.maius:  # faixa centrada nas maiúsculas (do topo da letra à linha de base)
                    base = y0 + self.asc
                    m_ = self.cap * 0.2
                    fy0, fh = base - self.cap - m_, self.cap + 2 * m_
                else:
                    fy0, fh = y0 + (y1 - y0) * 0.04, (y1 - y0) * 0.98
                if fw > 2:
                    faixa = Image.new("RGBA", (fw, int(fh)), c)
                    img = G.colar(img, faixa, ox + x0 - self.px(22), oy + fy0, (0, 0))
                colorido = Image.new("RGBA", sp.size, G.contraste_para(c))
                colorido.putalpha(sp.getchannel("A"))
                sp = colorido
                t_l += 0.16
            p = easing("expo")(clamp((t - t_l) / 0.55))
            janela = Image.new("RGBA", sp.size, (0, 0, 0, 0))
            G.compor(janela, sp, 0, int(sp.height * (1 - p)) - int(sp.height * ps))
            img = G.colar(img, janela, ox + box[0], oy + box[1], (0, 0))
        return img

    def _vazado(self, img, t):
        W, H = img.size
        p = self.p_entrada(t, max(0.35, self.d_in))
        po = self.p_saida(t, max(0.3, self.d_out))
        esc = 1.22 - 0.22 * easing("expo")(p)
        atravessar = bool(self.param("atravessar", False))
        op_tela = self.op_tela * easing("entrada")(p)
        if atravessar:
            d_at = min(0.8, self.dur * 0.4)
            pa = clamp((t - (self.t1 - d_at)) / d_at)
            esc *= 1 + 14 * easing("saida")(pa)
            op_tela *= 1 - clamp((pa - 0.6) / 0.4)
        else:
            op_tela *= 1 - easing("saida")(po)
        m = self.mask_txt
        if abs(esc - 1) > 1e-3:
            nw, nh = int(m.width * esc), int(m.height * esc)
            m = m.resize((max(1, nw), max(1, nh)), Image.BICUBIC)
        full = Image.new("L", (W, H), 0)
        full.paste(m, (int(self.x - m.width / 2), int(self.y - m.height / 2)))
        arr = (255 - np.asarray(full, np.float32)) * op_tela
        alfa = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "L")
        tela = Image.new("RGB", (W, H), self.cor_tela[:3])
        out = img.copy()
        out.paste(tela, (0, 0), alfa)
        return out


@registrar("riscado", "elemento_riscado", "risco", "strike", "tachado", "riscar")
class Riscado(Efeito):
    """Texto que é riscado (e opcionalmente substituído). texto ou itens: ['Premiere', 'After Effects'] (riscados
    em sequência), novo: texto que aparece depois (ex. 'Só com IA'), cor_risco (padrão 'perigo'), estilo_risco:
    'mao' (traço à mão, padrão) | 'reto' | 'x' (dois traços), tempo_risco (s após o início, padrão 0.6),
    intervalo (entre itens, padrão 0.45), tamanho (padrão 76), cartao (padrão true: vidro fosco), posicao."""
    entrada_padrao = "subir"
    duracao_padrao = 3.5
    som_entrada = "pop"
    vol_som = 0.2

    def preparar(self):
        e = self.e
        itens = self.param("itens")
        if not itens:
            itens = [str(self.param("texto", ""))]
        self.itens = [str(x) for x in itens]
        tam = self.px(num(self.param("tamanho"), 76))
        self.usa_cartao = bool(self.param("cartao", True))
        ct = self.cores_cartao()[0] if self.usa_cartao else self.cor("texto")
        sh = None if self.usa_cartao else self.sombra_texto()
        self.renders = [G.render_texto(x, e["fonte_titulo"], tam, self.cor(self.param("cor", ct)),
                                       largura_max=self.W * 0.78, cor_destaque=self.cor("destaque"),
                                       fonte_destaque=e["fonte_destaque"], sombra=sh) for x in self.itens]
        novo = self.param("novo", self.param("substituto"))
        self.novo = G.render_texto(str(novo), e["fonte_titulo"], tam * num(self.param("escala_novo"), 1.18),
                                   self.cor(self.param("cor_novo", "destaque")), largura_max=self.W * 0.82,
                                   cor_destaque=self.cor("destaque2"), fonte_destaque=e["fonte_destaque"],
                                   sombra=sh) if novo else None
        self.t_risco = self.t0 + num(self.param("tempo_risco"), 0.6)
        self.intervalo = num(self.param("intervalo"), 0.45)
        self.d_risco = num(self.param("duracao_risco"), 0.32)
        gap = self.px(18)
        hs = [r.img.height - 2 * r.pad for r in self.renders]
        self.alt = sum(hs) + gap * (len(hs) - 1) + ((self.novo.img.height - 2 * self.novo.pad + gap * 2.2) if self.novo else 0)
        self.larg = max([r.img.width - 2 * r.pad for r in self.renders] + ([self.novo.img.width - 2 * self.novo.pad] if self.novo else []))
        self.x, self.y = self.pos(None, "centro")
        self.gap = gap
        self.t_novo = self.t_risco + self.intervalo * (len(self.itens) - 1) + self.d_risco + 0.15
        self.cor_risco = self.cor(self.param("cor_risco", "perigo"))
        self.estilo_risco = self.param("estilo_risco", "mao")
        self.card = None
        if self.usa_cartao:
            pad = self.px(60)
            self.card = self.cartao(self.larg + 2 * pad, self.alt + 2 * pad)

    def area(self, t):
        pad = self.px(60) if self.card is not None else 0
        return self.caixa(self.x, self.y, self.larg + 2 * pad, self.alt + 2 * pad)

    def _traco(self, w, h, p, semente):
        """Sprite RGBA de um risco (p = progresso 0..1)."""
        esp = max(3, self.px(num(self.param("espessura"), 10)))
        S = 3
        pad = int(esp * 2)
        im = Image.new("RGBA", (int((w + 2 * pad) * S), int((h + 2 * pad) * S)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rng = np.random.default_rng(semente)
        cy = (h / 2 + pad) * S
        x0, x1 = pad * S, (w + pad) * S
        tracos = 2 if self.estilo_risco == "x" else 1
        for k in range(tracos):
            pts = []
            n = 24
            for i in range(n + 1):
                u = i / n
                if u > p:
                    break
                x = x0 + (x1 - x0) * u
                if self.estilo_risco == "reto":
                    y = cy
                elif self.estilo_risco == "x":
                    y = (pad + h * (0.15 + 0.7 * u if k == 0 else 0.85 - 0.7 * u)) * S
                else:
                    y = cy + (math.sin(u * 5.0 + semente) * 0.05 * h + (u - 0.5) * 0.14 * h) * S + rng.normal(0, 0.3) * S
                pts.append((x, y))
            if len(pts) >= 2:
                d.line(pts, fill=self.cor_risco, width=int(esp * S), joint="curve")
                r = esp * S / 2
                for (x, y) in (pts[0], pts[-1]):
                    d.ellipse([x - r, y - r, x + r, y + r], fill=self.cor_risco)
        return im.resize((int(w + 2 * pad), int(h + 2 * pad)), Image.LANCZOS), pad

    def aplicar(self, img, t):
        a = self.anim(t)
        if self.card is not None:
            img = self.colar_cartao(img, self.card, self.x, self.y, a=a)
        y = self.y - self.alt / 2
        for i, r in enumerate(self.renders):
            t_i = self.t_risco + i * self.intervalo
            p = clamp((t - t_i) / self.d_risco)
            op = a["op"] * (1 - 0.55 * clamp((t - t_i - self.d_risco) / 0.3))
            x = self.x - r.img.width / 2
            yy = y - r.pad
            img = G.colar(img, r.img, x + a["dx"], yy + a["dy"], (0, 0), 1, 0, op)
            if p > 0:
                for li, (lx0, ly0, lx1, ly1) in enumerate(r.linhas):
                    w, h = lx1 - lx0, ly1 - ly0
                    pl = clamp(p * len(r.linhas) - li)
                    if pl <= 0:
                        continue
                    tr, pad = self._traco(w + self.px(24), h, easing("entrada")(pl), i * 7 + li)
                    img = G.colar(img, tr, x + lx0 - self.px(12) - pad + a["dx"], yy + ly0 - pad + a["dy"], (0, 0), 1, 0,
                                  a["op"])
            y += r.img.height - 2 * r.pad + self.gap
        if self.novo is not None and t >= self.t_novo:
            p = clamp((t - self.t_novo) / 0.45)
            esc = 0.6 + 0.4 * volta(p, 1.8)
            hn = self.novo.img.height - 2 * self.novo.pad
            img = G.colar(img, self.novo.img, self.x + a["dx"], y + self.gap * 1.2 + hn / 2 + a["dy"],
                          (0.5, 0.5), esc, 0, clamp(p * 3) * a["op"])
        return img

    def sons_extra(self):
        s = [(self.t_risco + i * self.intervalo, "risco", 0.35) for i in range(len(self.itens))]
        if self.novo is not None:
            s.append((self.t_novo, "pop", 0.4))
        return s


@registrar("lista", "lista_numerada", "topicos", "itens", "ranking", "top")
class Lista(Efeito):
    """Lista numerada que aparece item a item (como '01 Carrossel de elementos ...'). itens (textos ou
    {texto, em: tempo}), titulo (opcional), numeros (true), destaque_atual (true: o item mais recente fica em
    destaque e os anteriores esmaecem), intervalo (padrão: distribui no tempo), tamanho (46), cartao (true: vidro
    fosco), posicao."""
    entrada_padrao = "subir"
    duracao_padrao = 5.0
    som_entrada = None

    def preparar(self):
        e = self.e
        itens = self.param("itens") or []
        self.itens = []
        n = max(1, len(itens))
        intervalo = num(self.param("intervalo"), max(0.25, min(1.2, (self.dur - 0.8) / n)))
        for i, it in enumerate(itens):
            if isinstance(it, dict):
                txt = str(it.get("texto", ""))
                em = self.ctx.resolver_tempo(it["em"]) if it.get("em") is not None else self.t0 + 0.3 + i * intervalo
            else:
                txt, em = str(it), self.t0 + 0.3 + i * intervalo
            self.itens.append((txt, em))
        tam = self.px(num(self.param("tamanho"), 46))
        self.tam = tam
        self.num = bool(self.param("numeros", True))
        self.destaque_atual = bool(self.param("destaque_atual", True))
        self.usa_cartao = bool(self.param("cartao", True))
        ct, cs = self.cores_cartao() if self.usa_cartao else (self.cor("texto"), self.cor("texto_suave"))
        sh = None if self.usa_cartao else self.sombra_texto()
        larg = self.W * num(self.param("largura"), 0.8)
        self.col_num = tam * 1.9 if self.num else 0
        self.rs = []
        for i, (txt, em) in enumerate(self.itens):
            r = G.render_texto(txt, e["fonte_forte"], tam, ct, largura_max=larg - self.col_num, alinhamento="esquerda",
                               cor_destaque=self.cor("destaque"), fonte_destaque=e["fonte_destaque"], sombra=sh)
            rn = G.render_texto("%02d" % (i + 1), e["fonte_forte"], tam, self.cor("destaque"), alinhamento="esquerda",
                                recursos=["tnum"], sombra=sh)
            self.rs.append((r, rn))
        self.titulo = None
        if self.param("titulo"):
            self.titulo = G.render_texto(str(self.param("titulo")), e["fonte_titulo"], tam * 1.36, ct,
                                         largura_max=larg, alinhamento="esquerda", cor_destaque=self.cor("destaque"),
                                         fonte_destaque=e["fonte_destaque"], sombra=sh)
        self.gap = tam * 0.62
        hs = [r.img.height - 2 * r.pad for r, rn in self.rs]
        alt_tit = (self.titulo.img.height - 2 * self.titulo.pad + self.gap * 1.3) if self.titulo else 0
        self.alt = sum(hs) + self.gap * max(0, len(hs) - 1) + alt_tit
        self.larg = larg
        self.x, self.y = self.pos(None, "centro")
        self.hs = hs
        self.card = None
        self.cs = cs
        if self.usa_cartao:
            pad = self.px(56)
            self.card = self.cartao(larg + 2 * pad, self.alt + 2 * pad)

    def area(self, t):
        pad = self.px(56) if self.card is not None else 0
        return self.caixa(self.x, self.y, self.larg + 2 * pad, self.alt + 2 * pad)

    def aplicar(self, img, t):
        a = self.anim(t)
        if self.card is not None:
            img = self.colar_cartao(img, self.card, self.x, self.y, a=a)
        x0 = self.x - self.larg / 2 + a["dx"]
        y = self.y - self.alt / 2 + a["dy"]
        if self.titulo:
            img = G.colar(img, self.titulo.img, x0 - self.titulo.pad, y - self.titulo.pad, (0, 0), 1, 0, a["op"])
            y += self.titulo.img.height - 2 * self.titulo.pad + self.gap * 1.3
        atual = max([i for i, (_, em) in enumerate(self.itens) if em <= t] or [-1])
        d = None
        for i, ((r, rn), (txt, em), h) in enumerate(zip(self.rs, self.itens, self.hs)):
            p = clamp((t - em) / 0.45)
            if p > 0:
                q = easing("expo")(p)
                op = clamp(p * 2) * a["op"]
                if self.destaque_atual and i < atual:
                    op *= 0.42
                dx = -self.px(36) * (1 - q)
                if self.num:
                    img = G.colar(img, rn.img, x0 + dx - rn.pad, y - rn.pad, (0, 0), 1, 0, op)
                img = G.colar(img, r.img, x0 + self.col_num + dx - r.pad, y - r.pad, (0, 0), 1, 0, op)
            y += h + self.gap
        return img

    def sons_extra(self):
        return [(em, "pop", 0.22) for (_, em) in self.itens]


@registrar("passos", "etapas", "steps", "progresso_etapas", "numeros_etapas")
class Passos(Efeito):
    """Indicador de etapas (círculos 1-2-3 que acendem em sequência) com rótulo da etapa atual.
    itens: ['rápido', 'fácil', 'barato'] (ou total: 3), tempos opcionais 'em': [...], posicao (padrão topo),
    tamanho (diâmetro, padrão 92), cor_ativa (padrão destaque)."""
    entrada_padrao = "descer"
    duracao_padrao = 4.0
    som_entrada = None

    def preparar(self):
        itens = self.param("itens")
        if not itens:
            itens = [""] * int(num(self.param("total"), 3))
        self.rotulos = [str(x) for x in itens]
        n = len(self.rotulos)
        ems = self.param("em")
        if ems:
            self.tempos = [self.ctx.resolver_tempo(x) for x in ems]
        else:
            passo = (self.dur - 0.5) / max(1, n)
            self.tempos = [self.t0 + 0.3 + i * passo for i in range(n)]
        self.d = self.px(num(self.param("tamanho"), 92))
        self.cor_a = self.cor(self.param("cor_ativa", "destaque"))
        self.x, self.y = self.pos(None, "topo")
        self.esp = self.d * 0.62
        e = self.e
        ca = G.contraste_para(self.cor_a)
        self.nums = [G.render_texto(str(i + 1), e["fonte_titulo"], self.d * 0.44, ca, recursos=["tnum"]).img for i in range(n)]
        self.nums_off = [G.render_texto(str(i + 1), e["fonte_titulo"], self.d * 0.44, (255, 255, 255, 200),
                                        recursos=["tnum"]).img for i in range(n)]
        self.rots = [G.render_texto(r, e["fonte_titulo"], self.px(44), self.cor("texto"), sombra=self.sombra_texto(),
                                    cor_destaque=self.cor("destaque"), fonte_destaque=e["fonte_destaque"]).img if r else None
                     for r in self.rotulos]
        self.c_on = G.com_sombra(G.circulo(self.d, self.cor_a), self.px(16), 0, self.px(6), 0.3)
        self.c_off = G.cartao(self.d, self.d, self.d / 2, e, "preto", s=self.s, sombra=False)

    def area(self, t):
        n = len(self.rotulos)
        total = n * self.d + (n - 1) * self.esp
        hr = max([r.height for r in self.rots if r is not None] or [0])
        return (self.x - total / 2, self.y - self.d / 2, self.x + total / 2, self.y + self.d * 0.78 + hr)

    def aplicar(self, img, t):
        a = self.anim(t)
        n = len(self.rotulos)
        total = n * self.d + (n - 1) * self.esp
        x = self.x - total / 2 + self.d / 2
        atual = max([i for i, tt in enumerate(self.tempos) if tt <= t] or [-1])
        yy = self.y + a["dy"]
        for i in range(n):
            cx = x + i * (self.d + self.esp)
            if i < n - 1:
                p = clamp((t - self.tempos[i + 1] + 0.3) / 0.3) if i + 1 <= atual + 1 else 0
                x0, x1 = cx + self.d / 2 + self.px(10), cx + self.d / 2 + self.esp - self.px(10)
                lw = max(2, int(self.px(4)))
                trilho = G.ret_arred(x1 - x0, lw, lw / 2, (255, 255, 255, int(70 * a["op"])))
                img = G.colar(img, trilho, x0, yy, (0, 0.5))
                if p > 0:
                    ativo = G.ret_arred(max(2, (x1 - x0) * p), lw, lw / 2, self.cor_a)
                    img = G.colar(img, ativo, x0, yy, (0, 0.5), 1, 0, a["op"])
            if i <= atual:
                p = clamp((t - self.tempos[i]) / 0.4)
                esc = 0.7 + 0.3 * volta(p, 2.0)
                img = G.colar_cartao(img, self.c_off, cx, yy, (0.5, 0.5), 1, 0, a["op"] * (1 - p))
                img = G.colar(img, self.c_on, cx, yy, (0.5, 0.5), esc, 0, a["op"])
                img = G.colar(img, self.nums[i], cx, yy, (0.5, 0.5), esc, 0, a["op"])
            else:
                img = G.colar_cartao(img, self.c_off, cx, yy, (0.5, 0.5), 1, 0, a["op"])
                img = G.colar(img, self.nums_off[i], cx, yy, (0.5, 0.5), 1, 0, a["op"])
        if atual >= 0 and self.rots[atual] is not None:
            p = clamp((t - self.tempos[atual]) / 0.4)
            img = G.colar(img, self.rots[atual], self.x, yy + self.d * 0.78 + self.px(18) * (1 - expo(p)),
                          (0.5, 0), 1, 0, clamp(p * 2) * a["op"])
        return img

    def sons_extra(self):
        return [(tt, "pop", 0.3) for tt in self.tempos]


def formatar_numero(v, casas=0, sep_milhar=".", sep_decimal=","):
    s = ("%." + str(int(casas)) + "f") % v
    inteiro, _, dec = s.partition(".")
    neg = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    r = sep_milhar.join(grupos)
    if dec:
        r += sep_decimal + dec
    return ("-" if neg else "") + r


@registrar("contador", "numero", "count_up", "contagem", "numero_animado", "estatistica")
class Contador(Efeito):
    """Número que conta até o valor (ex. 0 → 100.000). ate (valor final), de (0), prefixo ('R$ ', '+'), sufixo
    ('%', ' mil'), casas (decimais), rotulo (texto abaixo, em caixa alta espaçada), tamanho (padrão 180), cor
    (padrão texto; prefixo/sufixo em letras/%/R$ ficam menores e na cor de destaque), duracao_contagem (1.4s),
    posicao."""
    entrada_padrao = "subir"
    duracao_padrao = 3.0
    som_entrada = None

    def preparar(self):
        self.v0 = num(self.param("de"), 0.0)
        self.v1 = num(self.param("ate", self.param("valor")), 100.0)
        self.casas = int(num(self.param("casas"), 0 if float(self.v1).is_integer() else 1))
        self.pre = str(self.param("prefixo", ""))
        self.suf = str(self.param("sufixo", ""))
        self.dc = num(self.param("duracao_contagem"), min(1.4, self.dur * 0.6))
        self.tam = self.px(num(self.param("tamanho"), 180))
        e = self.e
        self.nf = e["fonte_pesada"]
        self.x, self.y = self.pos(None, "centro")
        rot = self.param("rotulo")
        self.rot = None
        if rot:
            self.rot = G.render_texto(str(rot), e["fonte_rotulo"], self.px(34), self.cor(self.param("cor_rotulo", "texto")),
                                      largura_max=self.W * 0.84, maiusculas=bool(self.param("maiusculas_rotulo", True)),
                                      rastreio=self.px(5), sombra=self.sombra_texto(0.8))
        larg_max = G.medir_texto(self.pre + formatar_numero(max(abs(self.v0), abs(self.v1)), self.casas) + self.suf,
                                 self.nf, self.tam)
        if larg_max > self.W * 0.9:
            self.tam *= self.W * 0.9 / larg_max
        self.c_num = self.cor(self.param("cor", "texto"))
        self._pre = self._parte(self.pre)
        self._suf = self._parte(self.suf)
        self._cache = {}

    def area(self, t):
        hr = (self.rot.img.height - self.rot.pad) if self.rot else 0
        return self.caixa(self.x, self.y, self.W * 0.8, self.tam * 1.25 + hr)

    def _pequeno(self, s):
        return any(ch.isalpha() or ch in "$%€£¥" for ch in s)

    def _parte(self, s):
        if not s:
            return None
        k = 0.56 if self._pequeno(s) else 1.0
        c = self.cor(self.param("cor_extra", "destaque")) if k < 1 else self.c_num
        return G.render_texto(s.strip() if k < 1 else s, self.nf, self.tam * k, c, sombra=self.sombra_texto())

    def _k(self, s):
        return 0.56 if self._pequeno(s) else 1.0

    def _cap(self, tam):
        f = G.fonte(self.nf, tam)
        try:
            return -f.getbbox("H", anchor="ls")[1]
        except Exception:
            return f.getmetrics()[0] * 0.72

    def _numero(self, s):
        """Compõe prefixo + número + sufixo pela linha de base; prefixo pequeno (R$) fica alinhado no topo."""
        rn = G.render_texto(s, self.nf, self.tam, self.c_num, sombra=self.sombra_texto(), recursos=["tnum"])
        pecas = []
        if self._pre is not None:
            pecas.append((self._pre, self._k(self.pre), "pre"))
        pecas.append((rn, 1.0, "num"))
        if self._suf is not None:
            pecas.append((self._suf, self._k(self.suf), "suf"))
        asc_b = G.fonte(self.nf, self.tam).getmetrics()[0]
        cap_b = self._cap(self.tam)
        gap = self.px(8)
        W = sum(p.img.width - 2 * p.pad for p, _, _ in pecas) + gap * (len(pecas) - 1) + 2 * rn.pad
        out = Image.new("RGBA", (int(W) + 2, int(rn.img.height)), (0, 0, 0, 0))
        x = rn.pad
        yb_num = rn.pad + asc_b
        for p, k, tipo in pecas:
            asc = G.fonte(self.nf, self.tam * k).getmetrics()[0]
            yb = yb_num
            if tipo == "pre" and k < 1:
                yb = yb_num - cap_b + self._cap(self.tam * k)  # topo das letras pequenas = topo do número
            G.compor(out, p.img, x - p.pad, yb - asc - p.pad)
            x += p.img.width - 2 * p.pad + gap
        return out

    def aplicar(self, img, t):
        a = self.anim(t)
        p = easing("expo")(clamp((t - self.t0 - 0.1) / self.dc))
        v = self.v0 + (self.v1 - self.v0) * p
        s = formatar_numero(v, self.casas)
        if s not in self._cache:
            self._cache = {s: self._numero(s)}
        sp = self._cache[s]
        hr = (self.rot.img.height - self.rot.pad) if self.rot else 0
        y = self.y - hr / 2
        img = G.colar(img, sp, self.x + a["dx"], y + a["dy"], (0.5, 0.5), a["esc"], 0, a["op"])
        if self.rot:
            pr = clamp((t - self.t0 - 0.25) / 0.4)
            img = G.colar(img, self.rot.img, self.x + a["dx"], y + sp.height / 2 - self.px(24) + a["dy"] + self.px(14) * (1 - expo(pr)),
                          (0.5, 0), 1, 0, a["op"] * pr)
        return img

    def sons_extra(self):
        n = 9
        out = [(self.t0 + 0.1 + self.dc * (1 - (1 - k / n) ** 2), "tecla", 0.14) for k in range(n)]
        out.append((self.t0 + 0.1 + self.dc, "ding", 0.3))
        return out


@registrar("rodape", "lower_third", "nome", "identificacao", "terco_inferior", "legenda_nome")
class Rodape(Efeito):
    """Identificação estilo 'lower third': nome (forte) + descricao (cargo/@perfil) num cartão de vidro com barra
    de cor. posicao (padrão inf_esq), cor_barra (destaque), material ('vidro' | 'solido' | 'claro')."""
    entrada_padrao = "esquerda"
    duracao_padrao = 4.0
    som_entrada = "swish"
    vol_som = 0.2

    def preparar(self):
        e = self.e
        ct, cs = self.cores_cartao()
        self.rn = G.render_texto(str(self.param("nome", self.param("texto", ""))), e["fonte_titulo"], self.px(54),
                                 ct, alinhamento="esquerda", cor_destaque=self.cor("destaque"),
                                 fonte_destaque=e["fonte_destaque"])
        d = self.param("descricao", self.param("cargo", self.param("subtitulo")))
        self.rd = G.render_texto(str(d), e["fonte_texto"], self.px(34), cs, alinhamento="esquerda") if d else None
        padx, pady = self.px(34), self.px(26)
        self.bar_w = self.px(8)
        tw = max(self.rn.img.width - 2 * self.rn.pad, (self.rd.img.width - 2 * self.rd.pad) if self.rd else 0)
        th = (self.rn.img.height - 2 * self.rn.pad) + ((self.rd.img.height - 2 * self.rd.pad + self.px(6)) if self.rd else 0)
        w = tw + padx * 2 + self.bar_w + self.px(22)
        h = th + pady * 2
        self.w, self.h = w, h
        self.padx, self.pady = padx, pady
        self.card = self.cartao(w, h, self.px(24))
        x, y = self.pos(None, "inf_esq")
        if self.spec.get("posicao") in (None, "inf_esq"):
            x = self.px(56) + w / 2
            y = self.H * (0.6 if self.H > self.W else 0.78)
        self.x, self.y = x, y

    def area(self, t):
        return self.caixa(self.x, self.y, self.w, self.h, self.px(8))

    def aplicar(self, img, t):
        a = self.anim(t)
        img = self.colar_cartao(img, self.card, self.x, self.y, a=a)
        x0 = self.x - self.w / 2 + a["dx"]
        y0 = self.y - self.h / 2 + a["dy"]
        pb = easing("expo")(self.p_entrada(t, 0.55))
        bh = int((self.h - 2 * self.pady) * pb)
        if bh > 2:
            barra = G.ret_arred(self.bar_w, bh, self.bar_w / 2, self.cor(self.param("cor_barra", "destaque")))
            img = G.colar(img, barra, x0 + self.padx, self.y + a["dy"], (0, 0.5), 1, 0, a["op"])
        xt = x0 + self.padx + self.bar_w + self.px(22)
        # nome e descrição sobem de dentro do cartão (máscara)
        for k, (r, yy, atraso) in enumerate(((self.rn, y0 + self.pady, 0.12),
                                             (self.rd, y0 + self.pady + self.rn.img.height - 2 * self.rn.pad + self.px(6), 0.26))):
            if r is None:
                continue
            p = easing("expo")(clamp((t - self.t0 - atraso) / 0.5))
            if p <= 0:
                continue
            sp = r.img
            jan = Image.new("RGBA", sp.size, (0, 0, 0, 0))
            G.compor(jan, sp, 0, int(sp.height * 0.7 * (1 - p)))
            img = G.colar(img, jan, xt - r.pad, yy - r.pad, (0, 0), 1, 0, a["op"] * clamp(p * 1.6))
        return img


@registrar("destaque_area", "circular", "circulo", "seta", "apontar", "sublinhado", "sublinhar", "marcar",
           "realce", "highlight", "marca_texto")
class DestaqueArea(Efeito):
    """Desenha (animado, traço à mão) um círculo, retângulo, sublinhado, marca-texto ou seta apontando para uma área.
    forma: 'circulo' | 'retangulo' | 'sublinhado' | 'marca_texto' | 'seta', alvo: {x, y, w, h} (0..1, centro e
    tamanho), cor (padrão destaque), espessura (9), texto (rótulo opcional junto da seta), de: 'esquerda'|'direita'|
    'cima'|'baixo' (de onde vem a seta)."""
    entrada_padrao = "nenhuma"
    duracao_padrao = 2.5
    som_entrada = "risco"
    vol_som = 0.25

    def preparar(self):
        nome = str(self.spec.get("tipo", ""))
        forma = self.param("forma")
        if not forma:
            forma = "seta" if "seta" in nome or "apontar" in nome else "sublinhado" if "sublinh" in nome else \
                "marca_texto" if "marca" in nome else "circulo"
        self.forma = forma
        al = self.param("alvo", {"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.12})
        self.ax, self.ay = num(al.get("x"), 0.5) * self.W, num(al.get("y"), 0.5) * self.H
        self.aw, self.ah = num(al.get("w"), 0.4) * self.W, num(al.get("h"), 0.12) * self.H
        self.c = self.cor(self.param("cor", "destaque"))
        self.esp = max(3, self.px(num(self.param("espessura"), 9)))
        self.rot = None
        if self.param("texto"):
            self.rot = G.render_texto(str(self.param("texto")), self.e["fonte_titulo"], self.px(52), self.c,
                                      sombra=self.sombra_texto(), largura_max=self.W * 0.6)
        self.d_desenho = num(self.param("duracao_desenho"), 0.55)

    def area(self, t):
        return self.caixa(self.ax, self.ay, self.aw, self.ah, self.esp * 2)

    def _caminho(self):
        cx, cy, w, h = self.ax, self.ay, self.aw, self.ah
        pts = []
        if self.forma == "circulo":
            n = 80
            for i in range(n + 1):
                u = i / n * 1.1
                ang = -math.pi * 0.6 + u * 2 * math.pi
                rr = 1 + 0.04 * math.sin(u * 7) + 0.035 * u
                pts.append((cx + (w / 2 + self.esp) * rr * math.cos(ang), cy + (h / 2 + self.esp) * rr * math.sin(ang)))
        elif self.forma == "retangulo":
            x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 + self.esp)]
        elif self.forma in ("sublinhado", "marca_texto"):
            y = cy + (h / 2 if self.forma == "sublinhado" else 0)
            n = 30
            for i in range(n + 1):
                u = i / n
                pts.append((cx - w / 2 + w * u, y + math.sin(u * 6) * self.esp * 0.2 - u * self.esp * 0.35))
        else:  # seta
            de = self.param("de", "baixo")
            L = max(self.px(220), min(w, h) * 1.2)
            dirs = {"esquerda": (-1, 0), "direita": (1, 0), "cima": (0, -1), "baixo": (0, 1)}
            dx, dy = dirs.get(de, (0, 1))
            tipx, tipy = cx + dx * (w / 2 + self.px(10)) if dx else cx, cy + dy * (h / 2 + self.px(10)) if dy else cy
            sx, sy = tipx + dx * L, tipy + dy * L
            n = 30
            for i in range(n + 1):
                u = i / n
                curva = math.sin(u * math.pi) * L * 0.18
                pts.append((sx + (tipx - sx) * u + (-dy) * curva, sy + (tipy - sy) * u + dx * curva))
            self._ponta = (tipx, tipy, math.atan2(tipy - pts[-2][1], tipx - pts[-2][0]))
            self._origem = (sx, sy)
        return pts

    def aplicar(self, img, t):
        p = easing("entrada")(clamp((t - self.t0) / self.d_desenho))
        op = 1 - easing("saida")(self.p_saida(t))
        pts = self._caminho()
        k = max(2, int(len(pts) * p))
        pts = pts[:k]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        m = self.esp * 4 + self.px(60)
        x0, y0 = int(min(xs) - m), int(min(ys) - m)
        x1, y1 = int(max(xs) + m), int(max(ys) + m)
        S = 2
        camada = Image.new("RGBA", ((x1 - x0) * S, (y1 - y0) * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(camada)
        P = [((x - x0) * S, (y - y0) * S) for x, y in pts]
        if self.forma == "marca_texto":
            d.line(P, fill=self.c[:3] + (110,), width=int(self.ah * S * 0.9), joint="curve")
        else:
            d.line(P, fill=self.c, width=int(self.esp * S), joint="curve")
            r = self.esp * S / 2
            for (x, y) in (P[0], P[-1]):
                d.ellipse([x - r, y - r, x + r, y + r], fill=self.c)
        if self.forma == "seta" and p >= 0.98:
            tx, ty, ang = self._ponta
            L = self.esp * 3.2
            for s_ in (-1, 1):
                a2 = ang + math.pi + s_ * 0.55
                d.line([((tx - x0) * S, (ty - y0) * S), ((tx + L * math.cos(a2) - x0) * S, (ty + L * math.sin(a2) - y0) * S)],
                       fill=self.c, width=int(self.esp * S))
                rr = self.esp * S / 2
                ex, ey = (tx + L * math.cos(a2) - x0) * S, (ty + L * math.sin(a2) - y0) * S
                d.ellipse([ex - rr, ey - rr, ex + rr, ey + rr], fill=self.c)
        camada = camada.resize((x1 - x0, y1 - y0), Image.LANCZOS)
        if self.forma != "marca_texto":
            camada = G.com_sombra(camada, self.px(10), 0, self.px(3), 0.35, expandir=False)
        img = G.colar(img, camada, x0, y0, (0, 0), 1, 0, op)
        if self.rot is not None and self.forma == "seta":
            sx, sy = self._origem
            pr = clamp((t - self.t0 - self.d_desenho * 0.6) / 0.3)
            img = G.colar(img, self.rot.img, sx, sy + (self.px(30) if sy >= self.ay else -self.px(30)),
                          (0.5, 0 if sy >= self.ay else 1), 1, 0, op * pr)
        elif self.rot is not None:
            pr = clamp((t - self.t0 - self.d_desenho * 0.6) / 0.3)
            img = G.colar(img, self.rot.img, self.ax, self.ay + self.ah / 2 + self.px(40), (0.5, 0), 1, 0, op * pr)
        return img


@registrar("imagem", "sticker", "adesivo", "logo", "marca_dagua", "marca_d_agua", "watermark", "foto", "print",
           "sobrepor_imagem", "overlay_imagem")
class ImagemSobreposta(Efeito):
    """Imagem/print/logo/adesivo sobre o vídeo. imagem (nome em midias ou caminho), posicao, largura (0..1 da tela,
    padrão 0.6; logos 0.16), raio (cantos, padrão do estilo), sombra (true), borda (cor), rotacao (graus), flutuar
    (true = balanço suave), opacidade. 'marca_dagua': logo pequeno no canto o vídeo todo."""
    entrada_padrao = "pop"
    duracao_padrao = 3.0
    som_entrada = "pop"
    vol_som = 0.25

    def preparar(self):
        nome = str(self.spec.get("tipo", ""))
        self.marca = "marca" in nome or "water" in nome
        if self.marca:
            if self.spec.get("inicio") is None and self.spec.get("fim") is None and self.spec.get("duracao") is None:
                self.t0, self.t1 = 0.0, self.ctx.duracao + 1
                self.dur = self.t1 - self.t0
            self.anim_in = str(self.spec.get("entrada", "fade"))
            self.som_entrada = None
        ref = self.param("imagem", self.param("midia"))
        im = self.ctx.bib.imagem(ref)
        larg = num(self.param("largura"), 0.16 if self.marca else 0.6) * self.W
        if self.param("altura"):
            esc = num(self.param("altura")) * self.H / im.height
        else:
            esc = larg / im.width
        im = im.resize((max(1, int(im.width * esc)), max(1, int(im.height * esc))), Image.LANCZOS)
        r = self.px(num(self.param("raio"), 0 if self.marca else self.e["raio"] * 0.8))
        if r > 0:
            im = G.cantos(im, r)
        if self.param("borda"):
            im = G.borda_em(im, r, self.cor(self.param("borda")), max(2, self.px(num(self.param("espessura_borda"), 6))))
        if self.param("sombra", not self.marca):
            im = G.com_sombra(im, self.px(36), 0, self.px(18), self.e["sombra"] + 0.05)
        self.sp = im
        self.rot = num(self.param("rotacao"), 0)
        self.flutuar = bool(self.param("flutuar", False))
        self.op = num(self.param("opacidade"), 0.75 if self.marca else 1.0)
        padrao = "sup_dir" if self.marca else "centro"
        self.x, self.y = self.pos(None, padrao)
        if self.marca and self.spec.get("posicao") in (None, "sup_dir"):
            self.x = self.W - self.px(40) - im.width / 2
            self.y = self.px(150) + im.height / 2

    def area(self, t):
        return self.caixa(self.x, self.y, self.sp.width * 0.82, self.sp.height * 0.82)

    def aplicar(self, img, t):
        bob = math.sin((t - self.t0) * 2.0) * self.px(8) if self.flutuar else 0
        rot = self.rot + (math.sin((t - self.t0) * 1.3) * 1.2 if self.flutuar else 0)
        return self.colar_anim(img, self.sp, self.x, self.y + bob, t, extra_rot=rot, extra_op=self.op)
