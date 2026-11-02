"""Cor e câmera: color grade (looks), zoom/punch-in, tremor, flash, glitch, vinheta, vazamento de luz, desfoque."""
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

from .. import grafico as G
from ..tempo import clamp, easing, lerp, ruido1d, suave
from ..util import num
from .base import Efeito, registrar

# contraste, saturacao, brilho, temperatura, matiz, lift(r,g,b), ganho(r,g,b), desbotar, vinheta, grao
LOOKS = {
    "natural": dict(contraste=0.12, saturacao=1.08, temperatura=0.03),
    "cinema": dict(contraste=0.26, saturacao=1.02, lift=(-0.035, 0.012, 0.065), ganho=(0.055, 0.0, -0.06),
                   vinheta=0.28),
    "teal_orange": "cinema",
    "quente": dict(contraste=0.14, saturacao=1.1, temperatura=0.32),
    "frio": dict(contraste=0.12, saturacao=0.95, temperatura=-0.32),
    "pb": dict(contraste=0.24, saturacao=0.0),
    "preto_e_branco": "pb",
    "noir": dict(contraste=0.55, saturacao=0.0, brilho=-0.03, vinheta=0.45, grao=0.05),
    "vintage": dict(contraste=0.08, saturacao=0.78, desbotar=0.09, lift=(0.02, 0.0, 0.05), ganho=(0.06, 0.02, -0.06),
                    vinheta=0.32, grao=0.045),
    "retro": "vintage",
    "vibrante": dict(contraste=0.2, saturacao=1.38, brilho=0.01),
    "moody": dict(contraste=0.32, saturacao=0.72, brilho=-0.05, lift=(0.0, 0.01, 0.035), vinheta=0.38),
    "sombrio": "moody",
    "pastel": dict(contraste=-0.16, saturacao=0.82, brilho=0.05, desbotar=0.06),
    "dourado": dict(contraste=0.16, saturacao=1.15, temperatura=0.42, ganho=(0.04, 0.02, -0.03), vinheta=0.2),
    "golden_hour": "dourado",
    "neon": dict(contraste=0.26, saturacao=1.25, lift=(0.03, -0.02, 0.08), ganho=(0.06, -0.05, 0.05)),
    "cyberpunk": "neon",
    "matrix": dict(contraste=0.22, saturacao=0.85, lift=(-0.02, 0.03, -0.02), ganho=(-0.06, 0.07, -0.05)),
    "lavado": dict(contraste=-0.1, saturacao=0.7, desbotar=0.12),
    "dramatico": dict(contraste=0.42, saturacao=0.9, brilho=-0.02, vinheta=0.4),
}


def _params_look(preset, extra=None):
    p = LOOKS.get(str(preset).lower(), None)
    while isinstance(p, str):
        p = LOOKS.get(p)
    p = dict(p or LOOKS["natural"])
    for k in ("contraste", "saturacao", "brilho", "temperatura", "matiz", "desbotar", "vinheta", "grao", "exposicao"):
        if extra and extra.get(k) is not None:
            p[k] = num(extra[k])
    return p


@lru_cache(64)
def _luts(preset_chave, k):
    import json
    preset, extra = json.loads(preset_chave)
    p = _params_look(preset, extra)
    x = np.linspace(0, 1, 256)
    c = p.get("contraste", 0.0) * k
    s = x * x * (3 - 2 * x)
    base = x + c * (s - x) if c >= 0 else x + c * (s - x) * 0.8
    br = p.get("brilho", 0.0) * k + p.get("exposicao", 0.0) * k
    base = base + br
    temp = p.get("temperatura", 0.0) * k
    mat = p.get("matiz", 0.0) * k
    lift = p.get("lift", (0, 0, 0))
    ganho = p.get("ganho", (0, 0, 0))
    temp_g = (0.09 * temp, 0.015 * temp - 0.05 * mat, -0.09 * temp)
    luts = []
    for ch in range(3):
        y = base.copy()
        y = y + lift[ch] * k * (1 - y) ** 2 + ganho[ch] * k * y ** 2 + temp_g[ch] * y
        d = p.get("desbotar", 0.0) * k
        y = d + (1 - d * 0.6) * y
        luts.append(np.clip(y * 255, 0, 255).astype(np.uint8).tolist())
    return luts[0] + luts[1] + luts[2]


@lru_cache(16)
def _vinheta(w, h, forca):
    xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    ys = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    r = np.sqrt((xs * 0.9) ** 2 + (ys * (h / w) * 0.62) ** 2) if h > w else np.sqrt(xs ** 2 * 0.8 + ys ** 2)
    m = 1 - forca * np.clip((r - 0.45) / 0.85, 0, 1) ** 1.6
    m8 = (m * 255).astype(np.uint8)
    return Image.merge("RGB", [Image.fromarray(m8, "L")] * 3)


@lru_cache(8)
def _graos(w, h, forca):
    out = []
    rng = np.random.default_rng(11)
    for _ in range(4):
        n = rng.normal(0, 255 * forca, (h // 2 + 1, w // 2 + 1)).astype(np.float32)
        img = Image.fromarray(np.clip(n + 128, 0, 255).astype(np.uint8), "L").resize((w, h), Image.BILINEAR)
        out.append(Image.merge("RGB", [img] * 3))
    return out


def aplicar_look(img, preset, intensidade=1.0, extra=None, quadro=0):
    import json
    k = clamp(float(intensidade), 0, 1.5)
    if k <= 0.001:
        return img
    ex = {kk: extra.get(kk) for kk in ("contraste", "saturacao", "brilho", "temperatura", "matiz", "desbotar",
                                         "vinheta", "grao", "exposicao") if extra and extra.get(kk) is not None}
    p = _params_look(preset, ex)
    chave = json.dumps([str(preset).lower(), ex], sort_keys=True)
    out = img.point(_luts(chave, round(k, 3)))
    sat = 1 + (p.get("saturacao", 1.0) - 1) * k
    if abs(sat - 1) > 0.01:
        out = ImageEnhance.Color(out).enhance(sat)
    v = p.get("vinheta", 0.0) * k
    if v > 0.01:
        out = ImageChops.multiply(out, _vinheta(out.width, out.height, round(v, 2)))
    g = p.get("grao", 0.0) * min(1.0, k)
    if g > 0.005:
        gr = _graos(out.width, out.height, round(g, 3))[quadro % 4]
        out = Image.blend(out, ImageChops.overlay(out, gr), 0.9)
    return out


@registrar("color_grade", "colorgrade", "grade_de_cor", "correcao_de_cor", "filtro", "look", "lut", "cor",
           "colorir", "filtro_de_cor")
class ColorGrade(Efeito):
    """Look de cor no vídeo. preset: natural, cinema, quente, frio, pb, noir, vintage, vibrante, moody, pastel,
    dourado, neon, matrix, lavado, dramatico. intensidade 0..1 (padrão 1). Ajustes finos opcionais: contraste,
    saturacao, brilho, temperatura, matiz, desbotar, vinheta, grao. modo: 'aplicar' (padrão, entra suave) ou
    'revelar' (uma linha passa revelando o look — ótimo para 'antes e depois' de cor). Use 'tudo': true para o
    vídeo inteiro."""
    fase = "base"
    duracao_padrao = 1e6
    entrada_padrao = "fade"

    def preparar(self):
        self.preset = self.param("preset", self.param("look", "cinema"))
        self.k = num(self.param("intensidade"), 1.0)
        self.modo = self.param("modo", "aplicar")
        if self.spec.get("camada") in ("tudo", "final"):
            self.fase = "final"
        self.t1 = min(self.t1, self.ctx.duracao + 1)
        self.d_in = num(self.spec.get("duracao_entrada"), 0.0 if self.t0 <= 0.01 else 0.5)
        self.d_out = num(self.spec.get("duracao_saida"), 0.0 if self.t1 >= self.ctx.duracao else 0.4)

    def aplicar(self, img, t):
        q = int(t * self.ctx.fps)
        if self.modo == "revelar":
            d = max(0.3, num(self.spec.get("duracao_revelar"), 1.2))
            p = suave(clamp((t - self.t0) / d))
            g = aplicar_look(img, self.preset, self.k, self.spec, q)
            if p >= 1:
                return g
            W, H = img.size
            x = int(W * p)
            out = img.copy()
            out.paste(g.crop((0, 0, x, H)), (0, 0))
            ImageDraw.Draw(out).rectangle([x - max(2, int(3 * self.s)), 0, x + max(2, int(3 * self.s)), H],
                                          fill=(255, 255, 255))
            return out
        k = self.k
        if self.d_in > 0:
            k *= suave(clamp((t - self.t0) / self.d_in))
        if self.d_out > 0:
            k *= 1 - suave(clamp((t - (self.t1 - self.d_out)) / self.d_out))
        return aplicar_look(img, self.preset, k, self.spec, q)


@registrar("zoom", "punch_in", "zoom_in", "aproximar", "zoom_rapido", "zoom_lento", "push_in")
class Zoom(Efeito):
    """Zoom de câmera no vídeo principal (qualidade máxima, recorta da fonte). intensidade (1.15), tipo: 'suave'
    (entra e sai suave), 'seco' (corte direto, estilo jump cut), 'pulso' (batida rápida 1→i→1), 'lento' (aproxima
    devagar durante todo o efeito). foco: 'rosto' (padrão) ou {x, y} em 0..1."""
    fase = "camera"
    duracao_padrao = 2.0

    def preparar(self):
        self.i = num(self.param("intensidade", self.param("zoom")), 1.15)
        tipo = str(self.param("tipo_zoom", self.param("modo", self.param("estilo", "suave"))))
        nome = str(self.spec.get("tipo", ""))
        if "rapido" in nome:
            tipo = "pulso"
        if "lento" in nome or "push" in nome:
            tipo = "lento"
        self.modo = tipo
        f = self.param("foco")
        self.foco = (num(f.get("x"), 0.5), num(f.get("y"), 0.45)) if isinstance(f, dict) else None

    def camera(self, t):
        u = t - self.t0
        i = self.i
        if self.modo == "seco":
            z = i
        elif self.modo == "pulso":
            d = min(0.45, self.dur)
            p = clamp(u / d)
            z = 1 + (i - 1) * math.sin(math.pi * p) ** 2 if p < 1 else 1.0
        elif self.modo == "lento":
            z = lerp(1.0, i, clamp(u / max(1e-6, self.dur)))
        else:
            d = min(0.4, self.dur / 3)
            z = 1 + (i - 1) * suave(clamp(u / d)) * (1 - suave(clamp((u - (self.dur - d)) / d)))
            if self.param("manter"):
                z = 1 + (i - 1) * suave(clamp(u / d))
        r = {"zoom": z}
        if self.foco:
            r["foco"] = self.foco
        return r


@registrar("tremor", "shake", "tremer", "terremoto", "impacto_camera")
class Tremor(Efeito):
    """Tremor de câmera (ênfase/impacto). intensidade em px (padrão 16), frequencia (Hz, padrão 9). Curto: 0.3–0.8s."""
    fase = "camera"
    duracao_padrao = 0.5
    som_entrada = None

    def preparar(self):
        self.i = num(self.param("intensidade"), 16)
        self.f = num(self.param("frequencia"), 9)

    def camera(self, t):
        u = t - self.t0
        dec = 1 - clamp(u / self.dur) ** 1.5
        a = self.px(self.i) * dec
        return {"dx": a * ruido1d(u * self.f, 1), "dy": a * ruido1d(u * self.f, 2), "zoom": 1 + 0.05 * dec,
                "rot": 0.8 * dec * ruido1d(u * self.f * 0.7, 3)}


@registrar("flash", "clarao", "piscar")
class Flash(Efeito):
    """Clarão branco (ou cor) que some rápido — marca batidas/cortes. duracao padrão 0.3s, cor, intensidade."""
    fase = "final"
    duracao_padrao = 0.3
    som_entrada = None

    def aplicar(self, img, t):
        p = clamp((t - self.t0) / self.dur)
        k = num(self.param("intensidade"), 0.85) * (1 - p) ** 2
        c = self.cor(self.param("cor", "#FFFFFF"))
        return Image.blend(img, Image.new("RGB", img.size, c[:3]), clamp(k))


@registrar("glitch", "falha", "distorcao_digital")
class Glitch(Efeito):
    """Falha digital (separação RGB + fatias deslocadas). Curto (0.2–0.6s). intensidade 0..1."""
    fase = "final"
    duracao_padrao = 0.35
    som_entrada = "glitch"

    def aplicar(self, img, t):
        k = num(self.param("intensidade"), 1.0)
        u = (t - self.t0) / self.dur
        env = math.sin(math.pi * clamp(u))
        arr = np.asarray(img).copy()
        H, W = arr.shape[:2]
        rng = np.random.default_rng(int(t * 1000) % 100000)
        sh = int(self.px(26) * k * env * (0.5 + rng.random()))
        arr[..., 0] = np.roll(arr[..., 0], sh, axis=1)
        arr[..., 2] = np.roll(arr[..., 2], -sh, axis=1)
        for _ in range(int(10 * k * env)):
            y0 = int(rng.integers(0, max(1, H - 10)))
            hh = int(rng.integers(6, max(7, H // 14)))
            arr[y0:y0 + hh] = np.roll(arr[y0:y0 + hh], int(rng.integers(-W // 7, W // 7)), axis=1)
        return Image.fromarray(arr, "RGB")


@registrar("vinheta", "vignette")
class Vinheta(Efeito):
    """Escurece as bordas. intensidade 0..1 (padrão 0.4). Use 'tudo': true para o vídeo todo."""
    fase = "final"
    duracao_padrao = 1e6

    def aplicar(self, img, t):
        v = clamp(num(self.param("intensidade"), 0.4), 0, 1)
        return ImageChops.multiply(img, _vinheta(img.width, img.height, round(v, 2)))


@registrar("vazamento_luz", "light_leak", "luz", "brilho_cinematico")
class VazamentoLuz(Efeito):
    """Mancha de luz quente que atravessa a tela (transições cinematográficas). cor (padrão laranja), duracao 1.2s."""
    fase = "final"
    duracao_padrao = 1.2
    som_entrada = "whoosh"
    vol_som = 0.2

    def preparar(self):
        W, H = self.W, self.H
        c1 = self.cor(self.param("cor", "#FF9A3D"))
        c2 = self.cor(self.param("cor2", "#FF3D7F"))
        self.k = 4  # desenha em 1/4 da resolução (é tudo desfocado mesmo)
        w = int(W * 0.6 / self.k)
        self.mancha = []
        for c in (c1, c2):
            g = G.gradiente_radial(w * 2, w * 2, c[:3] + (255,), c[:3] + (0,), 0.5, 0.5, 0.5)
            self.mancha.append(g)

    def aplicar(self, img, t):
        p = clamp((t - self.t0) / self.dur)
        env = math.sin(math.pi * p) ** 1.2
        W, H = img.size
        w4, h4 = max(1, W // self.k), max(1, H // self.k)
        camada = Image.new("RGB", (w4, h4), (0, 0, 0))
        for k, m in enumerate(self.mancha):
            x = (lerp(-0.4, 1.4, p) + (k * 0.25 - 0.1)) * w4
            y = (0.3 + 0.35 * k) * h4
            mm = G.opacidade_img(m, env * (0.9 - 0.3 * k))
            camada.paste(mm, (int(x - m.width / 2), int(y - m.height / 2)), mm)
        return ImageChops.screen(img, camada.resize((W, H), Image.BILINEAR))


@registrar("desfocar", "desfoque", "blur", "desfoque_fundo")
class Desfocar(Efeito):
    """Desfoca (e opcionalmente escurece) o vídeo por um período — útil atrás de textos grandes.
    raio (padrão 18), escurecer 0..1 (padrão 0.25)."""
    fase = "base"
    duracao_padrao = 2.5
    entrada_padrao = "fade"

    def aplicar(self, img, t):
        k = self.anim(t)["op"]
        r = self.px(num(self.param("raio"), 18)) * k
        out = G.desfocar(img, r)
        esc = num(self.param("escurecer"), 0.25) * k
        if esc > 0:
            out = Image.blend(out, Image.new("RGB", img.size, (0, 0, 0)), esc)
        return out
