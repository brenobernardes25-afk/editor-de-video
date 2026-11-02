"""Linha do tempo principal: blocos (trechos de vídeo, imagens, cartões), reenquadramento, zoom, transições
e conversão de tempos (bruto -> saída, palavra -> saída)."""
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import grafico as G
from .tempo import clamp, easing, expo_io, lerp, suave
from .util import ErroPlano, aviso, num

TRANSICOES = {"corte", "fade", "preto", "branco", "flash", "deslizar", "deslizar_esq", "deslizar_dir",
              "deslizar_cima", "deslizar_baixo", "zoom", "zoom_in", "zoom_out", "chicote", "desfoque",
              "glitch", "cortina", "circulo", "girar"}
ALIAS_TRANS = {"none": "corte", "cut": "corte", "nenhuma": "corte", "dissolve": "fade", "crossfade": "fade",
               "dissolver": "fade", "fade_preto": "preto", "black": "preto", "white": "branco", "slide": "deslizar",
               "push": "deslizar", "empurrar": "deslizar", "whip": "chicote", "blur": "desfoque", "wipe": "cortina",
               "iris": "circulo", "spin": "girar", "zoom_entrada": "zoom_in", "zoom_saida": "zoom_out"}


class Bloco:
    def __init__(self, spec, ctx, idx):
        self.idx = idx
        self.spec = spec
        self.ctx = ctx
        self.tipo = "video"
        self.midia = None
        self.cartao = None
        self.cor_fundo = None
        self.de = num(spec.get("de"), 0.0)
        self.vel = max(0.05, num(spec.get("velocidade"), 1.0))
        self.congelar = bool(spec.get("congelar", False))
        self.espelhar = bool(spec.get("espelhar", False))
        self.enquadrar = spec.get("enquadrar", spec.get("enquadramento", "auto"))
        self.zoom = spec.get("zoom", 1.0)
        self.foco = spec.get("foco")
        self.grade = spec.get("cor") or spec.get("color_grade")
        self.mudo = bool(spec.get("mudo", False))
        self.volume = num(spec.get("volume"), 1.0)
        self.movimento = spec.get("movimento", "kenburns")
        tr = spec.get("transicao")
        if isinstance(tr, str):
            tr = {"tipo": tr}
        self.transicao = tr or None
        if "cartao" in spec or "tela" in spec:
            self.tipo = "cartao"
            self.cartao = spec.get("cartao") or spec.get("tela")
            self.duracao = num(spec.get("duracao"), 2.5)
            self.cor_fundo = spec.get("fundo")
            return
        if "cor_solida" in spec or ("fundo" in spec and "midia" not in spec and "imagem" not in spec):
            self.tipo = "cor"
            self.cor_fundo = spec.get("cor_solida", spec.get("fundo"))
            self.duracao = num(spec.get("duracao"), 1.0)
            return
        ref = spec.get("midia", spec.get("imagem", "principal"))
        self.midia = ref
        info = ctx.bib.info(ref)
        if info.get("imagem"):
            self.tipo = "imagem"
            self.duracao = num(spec.get("duracao"), 3.0)
            return
        self.info = info
        dur_m = info["duracao"]
        self.ate = num(spec.get("ate"), dur_m) if spec.get("ate") is not None else dur_m
        if self.ate > dur_m > 0:
            self.ate = dur_m
        if self.congelar:
            self.duracao = num(spec.get("duracao"), 1.0)
            self.ate = self.de
        else:
            if self.ate <= self.de:
                raise ErroPlano("Bloco %d: 'ate' (%.2f) precisa ser maior que 'de' (%.2f)." % (idx, self.ate, self.de))
            self.duracao = (self.ate - self.de) / self.vel

    def tempo_fonte(self, u):
        """Tempo na mídia de origem para o instante local u (pode passar das bordas: 'alças' das transições)."""
        if self.congelar:
            return self.de
        return self.de + u * self.vel


class Linha:
    def __init__(self, specs, ctx):
        self.ctx = ctx
        self.blocos = []
        if not specs:
            raise ErroPlano("A linha do tempo está vazia.")
        for i, s in enumerate(specs):
            self.blocos.append(Bloco(s, ctx, i))
        # zoom alternado entre cortes (estilo jump cut)
        za = ctx.plano.get("zoom_alternado")
        if za:
            z = 1.12 if za is True else num(za, 1.12)
            k = 0
            for b in self.blocos:
                if b.tipo == "video" and b.midia == self.blocos[0].midia and b.zoom in (1, 1.0, None):
                    if k % 2 == 1:
                        b.zoom = z
                    k += 1
        self.inicios = []
        t = 0.0
        for b in self.blocos:
            self.inicios.append(t)
            t += b.duracao
        self.duracao = t
        self._trans = []  # (t_corte, dur, tipo, i_antes, i_depois, params)
        for i in range(1, len(self.blocos)):
            tr = self.blocos[i].transicao
            if tr is None and ctx.estilo.get("transicao_padrao") not in (None, "corte"):
                tr = {"tipo": ctx.estilo["transicao_padrao"]}
            if not tr:
                continue
            tipo = ALIAS_TRANS.get(str(tr.get("tipo", "fade")), str(tr.get("tipo", "fade")))
            if tipo == "corte":
                continue
            if tipo not in TRANSICOES:
                aviso("transição desconhecida '%s' — usando fade" % tipo)
                tipo = "fade"
            d = num(tr.get("duracao"), 0.45 if tipo not in ("flash", "glitch", "chicote") else 0.3)
            d = min(d, self.blocos[i - 1].duracao * 0.9, self.blocos[i].duracao * 0.9)
            self._trans.append((self.inicios[i], d, tipo, i - 1, i, tr))
        self._camera = []  # efeitos de câmera (zoom/tremor) registrados pelos efeitos

    # ---------------------------------------------------------------- busca
    def bloco_em(self, t):
        if t <= 0:
            return 0
        lo, hi = 0, len(self.inicios) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.inicios[mid] <= t + 1e-9:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def mapear_bruto(self, s, ref=None):
        """Tempo de saída correspondente ao tempo s da mídia ref (padrão: mídia do 1º bloco)."""
        ref = ref if ref is not None else self.midia_principal()
        melhor = None
        for i, b in enumerate(self.blocos):
            if b.tipo != "video" or b.midia != ref:
                continue
            if b.congelar:
                continue
            if b.de - 1e-6 <= s <= b.ate + 1e-6:
                return self.inicios[i] + (s - b.de) / b.vel
            # guarda o próximo trecho após s (caso s caia num pedaço cortado)
            if b.de > s and (melhor is None or b.de < melhor[0]):
                melhor = (b.de, self.inicios[i])
        return None if melhor is None else melhor[1]

    def midia_principal(self):
        for b in self.blocos:
            if b.tipo == "video":
                return b.midia
        return None

    # ---------------------------------------------------------------- câmera
    def registrar_camera(self, efeito):
        self._camera.append(efeito)

    def _camera_em(self, t):
        z, dx, dy, rot = 1.0, 0.0, 0.0, 0.0
        foco = None
        for e in self._camera:
            if e.ativo(t):
                r = e.camera(t)
                z *= r.get("zoom", 1.0)
                dx += r.get("dx", 0.0)
                dy += r.get("dy", 0.0)
                rot += r.get("rot", 0.0)
                if r.get("foco") is not None:
                    foco = r["foco"]
        return z, dx, dy, rot, foco

    # ---------------------------------------------------------------- renderização
    def quadro(self, t):
        """Quadro da faixa principal (PIL RGB do tamanho da saída) no instante t."""
        for (tc, d, tipo, ia, ib, params) in self._trans:
            if tc - d / 2 <= t < tc + d / 2:
                p = clamp((t - (tc - d / 2)) / max(1e-6, d))
                A = self._render_bloco(ia, t)
                B = self._render_bloco(ib, t)
                return misturar(A, B, p, tipo, params, self.ctx)
        return self._render_bloco(self.bloco_em(t), t)

    def _zoom_bloco(self, b, u):
        z = b.zoom
        if isinstance(z, dict):
            z0, z1 = num(z.get("de"), 1.0), num(z.get("para", z.get("ate")), 1.15)
            return lerp(z0, z1, easing(z.get("curva", "suave"))(clamp(u / max(1e-6, b.duracao))))
        return max(0.2, num(z, 1.0))

    def _render_bloco(self, i, t):
        ctx = self.ctx
        W, H = ctx.W, ctx.H
        b = self.blocos[i]
        u = t - self.inicios[i]
        if b.tipo == "cor":
            return Image.new("RGB", (W, H), G.cor(b.cor_fundo or ctx.estilo["fundo"], ctx.estilo)[:3])
        if b.tipo == "cartao":
            return ctx.render_cartao(b, u)
        cz, cdx, cdy, crot, cfoco = self._camera_em(t)
        if b.tipo == "imagem":
            img = ctx.bib.imagem(b.midia).convert("RGB")
            p = clamp(u / max(1e-6, b.duracao))
            mov = str(b.movimento or "kenburns")
            z0, z1, f0, f1 = 1.0, 1.0, (0.5, 0.5), (0.5, 0.5)
            if mov in ("kenburns", "ken_burns", "zoom_in", "aproximar"):
                z0, z1 = 1.0, 1.12
            elif mov in ("zoom_out", "afastar"):
                z0, z1 = 1.12, 1.0
            elif mov in ("pan", "pan_dir", "panoramica"):
                z0 = z1 = 1.1
                f0, f1 = (0.35, 0.5), (0.65, 0.5)
            elif mov == "pan_esq":
                z0 = z1 = 1.1
                f0, f1 = (0.65, 0.5), (0.35, 0.5)
            q = suave(p)
            z = lerp(z0, z1, q) * cz
            foco = (lerp(f0[0], f1[0], q), lerp(f0[1], f1[1], q))
            ajustar = (img.width / img.height) / (W / H)
            if b.enquadrar in ("ajustar", "conter", "fit") or (b.enquadrar == "auto" and not 0.6 < ajustar < 1.6):
                return enquadrar_ajustado(img, W, H, z, ctx)
            return G.cobrir(img, W, H, foco, z)
        # vídeo
        s = b.tempo_fonte(u)
        ref = b.midia
        tam = None
        if ctx.rascunho:
            inf = b.info
            tam = (max(2, int(inf["largura"] * ctx.escala_rascunho) // 2 * 2),
                   max(2, int(inf["altura"] * ctx.escala_rascunho) // 2 * 2))
        arr = ctx.bib.leitor(ref, "principal", tam).quadro(s)
        img = Image.fromarray(arr, "RGB")
        if b.espelhar:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        z = self._zoom_bloco(b, u) * cz
        modo = b.enquadrar
        sw, sh = img.size
        asp_s, asp_o = sw / sh, W / H
        if isinstance(modo, dict):
            foco = (num(modo.get("x"), 0.5), num(modo.get("y"), 0.5))
            modo = "foco"
        else:
            foco = None
            modo = str(modo or "auto")
            if modo == "auto":
                if abs(asp_s - asp_o) / asp_o < 0.03:
                    modo = "centro"
                elif asp_s > asp_o:
                    modo = "rosto"
                else:
                    modo = "ajustar" if asp_s / asp_o < 0.8 else "centro"
        if cfoco is not None:
            foco = cfoco
        if modo in ("ajustar", "conter", "fit", "desfoque"):
            out = enquadrar_ajustado(img, W, H, z, ctx)
        else:
            if foco is None:
                if modo == "rosto":
                    foco = ctx.foco_rosto(ref, s, asp_o, asp_s)
                elif b.foco:
                    foco = (num(b.foco.get("x"), 0.5), num(b.foco.get("y"), 0.5))
                else:
                    foco = (0.5, 0.5)
            out = recorte_cobrir(img, W, H, foco, z, cdx, cdy)
        if crot:
            out = out.rotate(crot, Image.BICUBIC, expand=False, fillcolor=None)
            out = G.cobrir(out, W, H, (0.5, 0.5), 1.0 + abs(math.sin(math.radians(crot))) * 0.6)
        if b.grade:
            out = ctx.aplicar_grade(out, b.grade)
        return out


def recorte_cobrir(img, W, H, foco, zoom=1.0, dx=0.0, dy=0.0):
    """Janela de recorte com o aspecto da saída, centrada no foco, com zoom e deslocamento (px de saída)."""
    sw, sh = img.size
    esc = max(W / sw, H / sh) * max(1.0, zoom)
    cw, ch = W / esc, H / esc
    cx = foco[0] * sw - dx / esc
    cy = foco[1] * sh - dy / esc
    x0 = min(max(cx - cw / 2, 0), sw - cw)
    y0 = min(max(cy - ch / 2, 0), sh - ch)
    if zoom < 1.0:
        # zoom < 1: encolhe o quadro dentro da tela com fundo desfocado
        base = recorte_cobrir(img, W, H, foco, 1.0)
        return enquadrar_ajustado(base, W, H, zoom, None)
    return img.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))


def enquadrar_ajustado(img, W, H, zoom=1.0, ctx=None):
    """Imagem inteira dentro da tela sobre uma versão desfocada e escurecida dela mesma."""
    fundo = G.cobrir(img, max(2, W // 6), max(2, H // 6), (0.5, 0.5))
    fundo = fundo.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
    fundo = Image.blend(fundo, Image.new("RGB", (W, H), (0, 0, 0)), 0.35)
    iw, ih = img.size
    esc = min(W / iw, H / ih) * zoom
    nw, nh = max(1, int(iw * esc)), max(1, int(ih * esc))
    fg = img.resize((nw, nh), Image.BICUBIC)
    fundo.paste(fg, ((W - nw) // 2, (H - nh) // 2))
    return fundo


def _deslocar(img, dx, dy, W, H):
    out = Image.new("RGB", (W, H), (0, 0, 0))
    out.paste(img, (int(round(dx)), int(round(dy))))
    return out


def _escalar_centro(img, s, W, H):
    if abs(s - 1) < 1e-3:
        return img
    nw, nh = max(1, int(W * s)), max(1, int(H * s))
    r = img.resize((nw, nh), Image.BICUBIC)
    out = Image.new("RGB", (W, H), (0, 0, 0))
    out.paste(r, ((W - nw) // 2, (H - nh) // 2))
    return out


def _borrao_horizontal(img, k):
    if k <= 1:
        return img
    W, H = img.size
    return img.resize((max(1, int(W / k)), H), Image.BILINEAR).resize((W, H), Image.BILINEAR)


def misturar(A, B, p, tipo, params, ctx):
    W, H = A.size
    if tipo == "fade":
        return Image.blend(A, B, suave(p))
    if tipo in ("preto", "branco", "flash"):
        c = (0, 0, 0) if tipo == "preto" else (255, 255, 255)
        meio = Image.new("RGB", (W, H), c)
        if tipo == "flash":
            # flash: pico branco rápido no meio
            k = 1 - abs(p - 0.5) * 2
            base = A if p < 0.5 else B
            return Image.blend(base, meio, clamp(k ** 1.5))
        if p < 0.5:
            return Image.blend(A, meio, suave(p * 2))
        return Image.blend(meio, B, suave((p - 0.5) * 2))
    if tipo.startswith("deslizar") or tipo == "chicote":
        direcao = tipo.split("_")[-1] if "_" in tipo else str(params.get("direcao", "esq"))
        q = expo_io(p)
        if direcao in ("dir", "direita"):
            sx, sy = 1, 0
        elif direcao in ("cima", "topo"):
            sx, sy = 0, -1
        elif direcao in ("baixo",):
            sx, sy = 0, 1
        else:
            sx, sy = -1, 0
        out = Image.new("RGB", (W, H))
        out.paste(A, (int(sx * q * W), int(sy * q * H)))
        out.paste(B, (int(sx * (q - 1) * W), int(sy * (q - 1) * H)))
        if tipo == "chicote":
            k = 1 + 26 * math.sin(math.pi * p) ** 2
            if sy == 0:
                out = _borrao_horizontal(out, k)
            else:
                out = out.transpose(Image.TRANSPOSE)
                out = _borrao_horizontal(out, k).transpose(Image.TRANSPOSE)
        return out
    if tipo in ("zoom", "zoom_in"):
        if p < 0.5:
            q = suave(p * 2)
            img = _escalar_centro(A, 1 + 0.9 * q, W, H)
            img = G.desfocar(img, 18 * q)
        else:
            q = suave((p - 0.5) * 2)
            img = _escalar_centro(B, 1.9 - 0.9 * q, W, H)
            img = G.desfocar(img, 18 * (1 - q))
        return img
    if tipo == "zoom_out":
        if p < 0.5:
            q = suave(p * 2)
            out = Image.new("RGB", (W, H), (0, 0, 0))
            sa = 1 - 0.35 * q
            r = A.resize((int(W * sa), int(H * sa)), Image.BICUBIC)
            out.paste(r, ((W - r.width) // 2, (H - r.height) // 2))
            return Image.blend(out, Image.new("RGB", (W, H)), 0.0)
        q = suave((p - 0.5) * 2)
        sb = 1.35 - 0.35 * q
        return _escalar_centro(B, sb, W, H)
    if tipo == "desfoque":
        q = suave(p)
        r = 22 * math.sin(math.pi * p)
        return Image.blend(G.desfocar(A, r), G.desfocar(B, r), q)
    if tipo == "glitch":
        base = A if p < 0.5 else B
        arr = np.asarray(base).copy()
        k = math.sin(math.pi * p)
        sh = int(28 * k)
        rng = np.random.default_rng(int(p * 1000))
        arr[..., 0] = np.roll(arr[..., 0], sh, axis=1)
        arr[..., 2] = np.roll(arr[..., 2], -sh, axis=1)
        for _ in range(int(8 * k)):
            y0 = int(rng.integers(0, H - 10))
            hh = int(rng.integers(8, max(9, H // 12)))
            arr[y0:y0 + hh] = np.roll(arr[y0:y0 + hh], int(rng.integers(-W // 8, W // 8)), axis=1)
        return Image.fromarray(arr, "RGB")
    if tipo == "cortina":
        q = suave(p)
        m = np.clip((np.arange(W, dtype=np.float32) - (q * (W + 120) - 60)) / 60.0, 0, 1)
        m = (1 - m) * 255
        mask = Image.fromarray(np.repeat(m[None, :], H, axis=0).astype(np.uint8), "L")
        return Image.composite(B, A, mask)
    if tipo == "circulo":
        q = suave(p)
        r = q * math.hypot(W, H) / 2 * 1.02
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(3))
        return Image.composite(B, A, mask)
    if tipo == "girar":
        q = suave(p)
        base = A if p < 0.5 else B
        ang = 25 * math.sin(math.pi * p) * (1 if p < 0.5 else -1)
        s = 1 + 0.4 * math.sin(math.pi * p)
        img = base.rotate(ang, Image.BICUBIC)
        img = _escalar_centro(img, s, W, H)
        return G.desfocar(img, 10 * math.sin(math.pi * p))
    return B if p >= 0.5 else A
