"""Primitivas gráficas (Pillow + numpy): cores, fontes, texto com marcação, formas com antisserrilhado,
sombras, colagem com transformação, perspectiva, desfoque e ícones vetoriais."""
import math
import os
import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .util import ASSETS, aviso

DIR_FONTES = os.path.join(ASSETS, "fontes")

NOMES_CORES = {
    "branco": "#FFFFFF", "white": "#FFFFFF", "preto": "#000000", "black": "#000000",
    "vermelho": "#E53935", "red": "#E53935", "verde": "#2ECC71", "green": "#2ECC71",
    "azul": "#2F6BFF", "blue": "#2F6BFF", "amarelo": "#FFD60A", "yellow": "#FFD60A",
    "laranja": "#FF8A3D", "orange": "#FF8A3D", "roxo": "#9B5CFF", "purple": "#9B5CFF",
    "rosa": "#FF5CA8", "pink": "#FF5CA8", "cinza": "#8E8E93", "gray": "#8E8E93", "grey": "#8E8E93",
    "ciano": "#2EE6D6", "cyan": "#2EE6D6", "dourado": "#E8B04B", "gold": "#E8B04B",
    "transparente": "#00000000", "transparent": "#00000000", "nenhum": "#00000000", "none": "#00000000",
}


def cor(c, estilo=None, alpha=None):
    """Converte '#RGB', '#RRGGBB', '#RRGGBBAA', nome, chave do estilo ('destaque', 'texto'...) ou tupla em RGBA."""
    if c is None:
        c = "#FFFFFF"
    if isinstance(c, (tuple, list)):
        t = tuple(int(round(x)) for x in c)
        if len(t) == 3:
            t = t + (255,)
    else:
        s = str(c).strip()
        if estilo is not None and s in estilo and isinstance(estilo[s], str) and estilo[s].startswith("#"):
            s = estilo[s]
        s = NOMES_CORES.get(s.lower(), s)
        if not s.startswith("#"):
            s = "#" + s
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        try:
            v = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
        except ValueError:
            aviso("cor inválida '%s' — usando branco" % c)
            v = [255, 255, 255]
        if len(v) == 3:
            v.append(255)
        t = tuple(v[:4])
    if alpha is not None:
        t = t[:3] + (int(round(max(0, min(1, alpha)) * 255)),)
    return t


def misturar_cor(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def luminancia(c):
    r, g, b = c[:3]
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def contraste_para(c):
    """Cor de texto legível sobre a cor c."""
    return (18, 18, 20, 255) if luminancia(c) > 0.6 else (255, 255, 255, 255)


# ------------------------------------------------------------------ fontes
_SISTEMA = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _chave(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# nomes antigos ou genéricos -> fontes incluídas (planos antigos continuam funcionando)
ALIAS_FONTES = {_chave(k): v for k, v in {
    "Inter-ExtraBold": "InterDisplay-ExtraBold", "Inter-Black": "InterDisplay-Black",
    "Inter-Regular": "Inter-Medium", "InterDisplay-Regular": "InterDisplay-Medium",
    "Poppins-Bold": "MonaSansSemiExpanded-Bold", "Poppins-SemiBold": "MonaSansSemiExpanded-Bold",
    "Poppins-ExtraBold": "MonaSansSemiExpanded-ExtraBold", "Poppins-Black": "MonaSansSemiExpanded-Black",
    "Poppins-Medium": "Inter-Medium", "Poppins-Regular": "Inter-Medium",
    "LiberationMono-Bold": "JetBrainsMono-Bold", "LiberationMono-Regular": "JetBrainsMono-Medium",
    "Montserrat-Black": "MonaSansSemiExpanded-Black", "Montserrat-ExtraBold": "MonaSansSemiExpanded-ExtraBold",
    "Montserrat-Bold": "MonaSansSemiExpanded-Bold", "Montserrat": "MonaSansSemiExpanded-ExtraBold",
    "TheBoldFont": "MonaSansExpanded-Black", "Bebas": "MonaSansCondensed-Black", "BebasNeue": "MonaSansCondensed-Black",
    "Anton": "MonaSansCondensed-Black", "Oswald": "MonaSansCondensed-ExtraBold", "Impact": "MonaSansCondensed-Black",
    "SFPro": "InterDisplay-Bold", "Helvetica": "InterDisplay-Bold", "Arial": "Inter-SemiBold",
    "MonaSans-Black": "MonaSansSemiExpanded-Black", "MonaSans-ExtraBold": "MonaSansSemiExpanded-ExtraBold",
    "MonaSans-Bold": "MonaSansSemiExpanded-Bold", "Mono": "JetBrainsMono-Bold",
    "Playfair": "Lora-Bold", "Serif": "Lora-Bold", "Lora": "Lora-Bold",
}.items()}

# fontes variáveis originais (sem modificação): nome -> (arquivo, instância)
VARIAVEIS = {_chave(k): v for k, v in {
    "Lora-Regular": ("Lora-Variable.ttf", "Regular"), "Lora-Medium": ("Lora-Variable.ttf", "Medium"),
    "Lora-SemiBold": ("Lora-Variable.ttf", "SemiBold"), "Lora-Bold": ("Lora-Variable.ttf", "Bold"),
    "Lora-Italic": ("Lora-Italic-Variable.ttf", "Italic"), "Lora-MediumItalic": ("Lora-Italic-Variable.ttf", "Medium Italic"),
    "Lora-SemiBoldItalic": ("Lora-Italic-Variable.ttf", "SemiBold Italic"),
    "Lora-BoldItalic": ("Lora-Italic-Variable.ttf", "Bold Italic"),
}.items()}


@lru_cache(None)
def _resolver_fonte(nome):
    """(caminho, instância variável ou None) para um nome de fonte."""
    nome = str(nome)
    if os.path.isabs(nome) and os.path.exists(nome):
        return nome, None
    for ext in (".otf", ".ttf", ""):
        p = os.path.join(DIR_FONTES, nome + ext)
        if os.path.exists(p) and not os.path.isdir(p):
            return p, None
    alvo = _chave(nome)
    if alvo in VARIAVEIS:
        arq, inst = VARIAVEIS[alvo]
        p = os.path.join(DIR_FONTES, arq)
        if os.path.exists(p):
            return p, inst
    if alvo in ALIAS_FONTES and _chave(ALIAS_FONTES[alvo]) != alvo:
        return _resolver_fonte(ALIAS_FONTES[alvo])
    # busca aproximada (ex.: "inter display black" -> InterDisplay-Black)
    if os.path.isdir(DIR_FONTES):
        for f in sorted(os.listdir(DIR_FONTES)):
            if _chave(os.path.splitext(f)[0]) == alvo:
                return os.path.join(DIR_FONTES, f), None
    for p in _SISTEMA:
        if os.path.exists(p):
            aviso("fonte '%s' não encontrada — usando %s" % (nome, os.path.basename(p)))
            return p, None
    return None, None


def _arquivo_fonte(nome):
    return _resolver_fonte(nome)[0]


_RAQM = [None]


def tem_raqm():
    if _RAQM[0] is None:
        try:
            from PIL import features
            _RAQM[0] = bool(features.check("raqm"))
        except Exception:
            _RAQM[0] = False
    return _RAQM[0]


@lru_cache(512)
def fonte(nome, tamanho):
    tamanho = max(4, int(round(tamanho)))
    p, inst = _resolver_fonte(nome)
    if p is None:
        return ImageFont.load_default()
    try:
        f = ImageFont.truetype(p, tamanho, layout_engine=ImageFont.Layout.RAQM if tem_raqm() else ImageFont.Layout.BASIC)
    except Exception:
        f = ImageFont.truetype(p, tamanho)
    if inst:
        try:
            f.set_variation_by_name(inst)
        except Exception:
            pass  # FreeType sem suporte a fontes variáveis: fica o peso padrão
    return f


def _kw_recursos(recursos):
    return {"features": list(recursos)} if recursos and tem_raqm() else {}


# ------------------------------------------------------------------ texto com marcação
_RE_MARCA = re.compile(r"(\*\*.+?\*\*|\*.+?\*|(?<![\w@])_.+?_(?!\w)|==.+?==)", re.S)


def _runs(texto):
    """Divide o texto em trechos com estilo: 'n' normal, 'c' cor de destaque, 'f' fonte de destaque, 'm' marca-texto."""
    out = []
    pos = 0
    for m in _RE_MARCA.finditer(texto):
        if m.start() > pos:
            out.append((texto[pos:m.start()], "n"))
        s = m.group(0)
        if s.startswith("**"):
            out.append((s[2:-2], "c"))
        elif s.startswith("*"):
            out.append((s[1:-1], "c"))
        elif s.startswith("=="):
            out.append((s[2:-2], "m"))
        else:
            out.append((s[1:-1], "f"))
        pos = m.end()
    if pos < len(texto):
        out.append((texto[pos:], "n"))
    return out


def tirar_marcas(texto):
    return "".join(t for t, _ in _runs(str(texto)))


# ------------------------------------------------------------------ emoji
_FAIXAS_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\uFE0F\u200D\U000E0020-\U000E007F]")
_EMOJI_FONTES = [
    os.path.join(DIR_FONTES, "NotoColorEmoji.ttf"),
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto-color-emoji/NotoColorEmoji.ttf",
]
_aviso_emoji = [False]


@lru_cache(None)
def _cmap(caminho):
    try:
        from fontTools.ttLib import TTFont

        f = TTFont(caminho, lazy=True, fontNumber=0)
        return frozenset(f.getBestCmap().keys())
    except Exception:
        return None


def _tem_glifo(nome_fonte, ch):
    p = _arquivo_fonte(nome_fonte)
    cm = _cmap(p) if p else None
    if cm is None:
        return ord(ch) < 0x2600
    return ord(ch) in cm


@lru_cache(None)
def _fonte_emoji():
    for p in _EMOJI_FONTES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, 109)
            except Exception:
                continue
    return None


@lru_cache(256)
def emoji_img(seq, tamanho):
    """Imagem RGBA de um emoji (sequência de codepoints) no tamanho pedido, ou None se não houver fonte."""
    f = _fonte_emoji()
    if f is None:
        return None
    im = Image.new("RGBA", (160 * max(1, len(seq)), 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    try:
        d.text((0, 0), seq, font=f, embedded_color=True)
    except Exception:
        return None
    bb = im.getbbox()
    if not bb:
        return None
    im = im.crop(bb)
    k = tamanho / max(1, im.height)
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)


def _separar_emoji(palavra, nome_fonte):
    """Divide uma palavra em trechos [(texto, é_emoji)]. Emojis sem fonte disponível são descartados."""
    if not _FAIXAS_EMOJI.search(palavra):
        return [(palavra, False)]
    out = []
    buf = ""
    emo = ""
    for ch in palavra:
        e = bool(_FAIXAS_EMOJI.match(ch)) and not _tem_glifo(nome_fonte, ch)
        if e:
            if buf:
                out.append((buf, False))
                buf = ""
            emo += ch
        else:
            if emo:
                out.append((emo, True))
                emo = ""
            buf += ch
    if buf:
        out.append((buf, False))
    if emo:
        out.append((emo, True))
    if _fonte_emoji() is None:
        if any(e for _, e in out) and not _aviso_emoji[0]:
            aviso("sem fonte de emoji neste ambiente — emojis removidos do texto")
            _aviso_emoji[0] = True
        out = [(t, e) for t, e in out if not e]
    return out


class TextoRender:
    def __init__(self, img, palavras, linhas, pad):
        self.img = img            # RGBA
        self.palavras = palavras  # [(x0, y0, x1, y1, texto, estilo)] em coordenadas da imagem
        self.linhas = linhas      # [(x0, y0, x1, y1)]
        self.pad = pad


def _sombras(camada, sombras):
    """Sombras em camadas (lista de dicts raio/dx/dy/opacidade/cor) calculadas a partir do alfa do texto."""
    alfa = camada.getchannel("A")
    W, H = camada.size
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for sh in sombras:
        op = float(sh.get("opacidade", 0.5))
        if op <= 0:
            continue
        a = Image.new("L", (W, H), 0)
        a.paste(alfa, (int(round(sh.get("dx", 0))), int(round(sh.get("dy", 0)))))
        a = desfocar(a, float(sh.get("raio", 10)))
        if op != 1:
            a = a.point(lambda v, k=op: int(v * k))
        c = Image.new("RGBA", (W, H), tuple(cor(sh.get("cor", (0, 0, 0))))[:3] + (0,))
        c.putalpha(a)
        out = Image.alpha_composite(out, c)
    return Image.alpha_composite(out, camada)


# padrões de marcação vindos do estilo do plano (o contexto ajusta ao montar o estilo)
PADROES_TEXTO = {"marca_solida": False, "destaque_fonte": False}


def render_texto(texto, nome_fonte, tamanho, cor_txt=(255, 255, 255, 255), largura_max=None,
                 alinhamento="centro", entrelinha=1.12, contorno=0, cor_contorno=(0, 0, 0, 255),
                 sombra=None, cor_destaque=(255, 214, 10, 255), fonte_destaque=None, escala_destaque=1.0,
                 maiusculas=False, caixa=None, caixa_pad=(26, 14), caixa_raio=18, marca_cor=None,
                 rastreio=0, cor_por_palavra=None, ocultar_apos=None, caixa_palavras=None, marca_solida=None,
                 ocultar_indices=None, recursos=None, destaque_fonte=None):
    """Renderiza texto com quebra de linha e marcação (*cor*, _fonte_, ==marca-texto==).

    sombra: None, dict(raio, dx, dy, opacidade, cor) ou lista desses dicts (camadas).  caixa: cor de uma caixa
    atrás de cada linha. cor_por_palavra: dict índice->cor (karaokê). marca_solida: ==marca== vira etiqueta
    sólida com texto contrastante. ocultar_indices: palavras (índices) que não são desenhadas, mas ocupam lugar.
    recursos: recursos OpenType (ex. ['tnum'] para números de largura fixa). destaque_fonte: *cor* também usa a
    fonte de destaque. marca_solida/destaque_fonte = None seguem o estilo do plano (PADROES_TEXTO)."""
    if marca_solida is None:
        marca_solida = PADROES_TEXTO.get("marca_solida", False)
    if destaque_fonte is None:
        destaque_fonte = PADROES_TEXTO.get("destaque_fonte", False)
    texto = str(texto if texto is not None else "").replace("\\n", "\n")  # '\\n' digitado vira quebra de linha
    if maiusculas:
        texto = texto.upper()
    f_n = fonte(nome_fonte, tamanho)
    f_d = fonte(fonte_destaque or nome_fonte, tamanho * escala_destaque)
    marca_cor = marca_cor or (cor_destaque[:3] + ((255,) if marca_solida else (110,)))
    kwr = _kw_recursos(recursos)
    ocultar_indices = set(ocultar_indices or ())

    # tokens: (palavra, estilo) e quebras explícitas
    tokens = []
    for trecho, est in _runs(texto):
        partes = re.split(r"(\n)", trecho)
        for p in partes:
            if p == "\n":
                tokens.append(("\n", est))
                continue
            for i, w in enumerate(re.split(r"( +)", p)):
                if not w:
                    continue
                if w.strip() == "":
                    tokens.append((" ", est))
                else:
                    for parte, e_emoji in _separar_emoji(w, nome_fonte):
                        if not e_emoji:
                            tokens.append((parte, est))
                        else:
                            seq = parte.replace("\uFE0F", "")
                            if seq:
                                tokens.append((seq, "e"))

    def fnt(est):
        return f_d if (est == "f" or (est == "c" and destaque_fonte)) else f_n

    def larg(w, est):
        if est == "e":
            n_e = max(1, len([c for c in w if c != "\u200D"]) - w.count("\u200D") * 1)
            return tamanho * 1.12 * max(1, n_e if "\u200D" not in w else 1)
        f = fnt(est)
        try:
            v = f.getlength(w, **kwr)
        except Exception:
            v = f.getbbox(w)[2]
        if rastreio:
            v = sum(f.getlength(ch) for ch in w)
        return v + rastreio * max(0, len(w) - 1)

    esp = larg(" ", "n") + (rastreio * 2.5 if rastreio else 0)
    # montar linhas
    linhas = [[]]
    largura_atual = 0.0
    lm = largura_max if largura_max else 1e9
    pendente_espaco = False
    for w, est in tokens:
        if w == "\n":
            linhas.append([])
            largura_atual = 0.0
            pendente_espaco = False
            continue
        if w == " ":
            pendente_espaco = True
            continue
        lw = larg(w, est)
        extra = esp if (linhas[-1] and pendente_espaco) else 0
        if linhas[-1] and largura_atual + extra + lw > lm:
            linhas.append([])
            largura_atual = 0.0
            extra = 0
        juntar = bool(linhas[-1]) and not pendente_espaco
        linhas[-1].append([w, est, lw, extra, juntar])
        largura_atual += extra + lw
        pendente_espaco = False
    linhas = [ln for ln in linhas] or [[]]

    asc_n, desc_n = f_n.getmetrics()
    asc_d, desc_d = f_d.getmetrics()
    tem_d = any(est == "f" or (est == "c" and destaque_fonte) for ln in linhas for (_, est, _, _, _) in ln)
    asc = max(asc_n, asc_d if tem_d else 0)
    desc = max(desc_n, desc_d if tem_d else 0)
    alt_linha = (asc + desc) * entrelinha
    larguras = [sum(e + lw for (_, _, lw, e, _) in ln) for ln in linhas]
    W = max([1.0] + larguras)
    H = alt_linha * len(linhas) - (alt_linha - (asc + desc))

    pad = int(math.ceil(contorno + 4 + (tamanho * 0.12 if any(est == "m" for ln in linhas for (_, est, _, _, _) in ln) else 0)))
    bx, by = caixa_pad if caixa is not None else (0, 0)
    sombras = [sombra] if isinstance(sombra, dict) else list(sombra or [])
    pad_sh = max([int(s_.get("raio", 0) * 2 + max(abs(s_.get("dx", 0)), abs(s_.get("dy", 0)))) for s_ in sombras] or [0])
    pad_total = pad + pad_sh + int(bx)
    iw = int(math.ceil(W + 2 * pad_total))
    ih = int(math.ceil(H + 2 * pad_total + 2 * by))
    camada = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    palavras_out = []
    linhas_out = []
    y = pad_total + by
    idx = 0
    for li, ln in enumerate(linhas):
        lw = larguras[li]
        if alinhamento in ("esquerda", "left", "esq"):
            x = pad_total
        elif alinhamento in ("direita", "right", "dir"):
            x = pad_total + (W - lw)
        else:
            x = pad_total + (W - lw) / 2.0
        base_y = y + asc
        linhas_out.append((x, y, x + lw, y + asc + desc))
        if caixa is not None and ln:
            d.rounded_rectangle([x - bx, y - by * 0.55, x + lw + bx, y + asc + desc + by * 0.55],
                                radius=caixa_raio, fill=tuple(cor(caixa)))
        for (w, est, wl, extra, juntar) in ln:
            x += extra
            f = fnt(est)
            if (ocultar_apos is not None and idx > ocultar_apos) or idx in ocultar_indices:
                palavras_out.append((x, y, x + wl, y + asc + desc, w, est))
                x += wl
                idx += 1
                continue
            if caixa_palavras and idx in caixa_palavras:
                px_, py_ = tamanho * 0.12, tamanho * 0.06
                d.rounded_rectangle([x - px_, base_y - asc * 0.86 - py_, x + wl + px_, base_y + desc * 0.7 + py_],
                                    radius=tamanho * 0.18, fill=tuple(cor(caixa_palavras[idx])))
            if cor_por_palavra is not None and idx in cor_por_palavra:
                c = cor_por_palavra[idx]
            elif est in ("c", "f"):
                c = cor_destaque
            else:
                c = cor_txt
            if est == "m":
                if marca_solida:
                    px_, py_ = tamanho * 0.14, tamanho * 0.05
                    d.rounded_rectangle([x - px_, base_y - asc * 0.84 - py_, x + wl + px_, base_y + desc * 0.62 + py_],
                                        radius=tamanho * 0.14, fill=tuple(marca_cor[:3]) + (255,))
                    c = contraste_para(marca_cor)
                else:
                    d.rounded_rectangle([x - 6, base_y - asc * 0.78, x + wl + 6, base_y + desc * 0.55],
                                        radius=8, fill=marca_cor)
            if est == "e":
                ei = emoji_img(w, tamanho * 1.02)
                if ei is not None:
                    camada.paste(ei, (int(x + (wl - ei.width) / 2), int(base_y - asc * 0.86)), ei)
                palavras_out.append((x, y, x + wl, y + asc + desc, w, est))
                x += wl
                idx += 1
                continue
            if rastreio:
                xx = x
                for ch in w:
                    d.text((xx, base_y), ch, font=f, fill=tuple(c), anchor="ls",
                           stroke_width=int(contorno), stroke_fill=tuple(cor_contorno))
                    xx += f.getlength(ch) + rastreio
            else:
                d.text((x, base_y), w, font=f, fill=tuple(c), anchor="ls",
                       stroke_width=int(contorno), stroke_fill=tuple(cor_contorno), **kwr)
            palavras_out.append((x, y, x + wl, y + asc + desc, w, est))
            x += wl
            idx += 1
        y += alt_linha
    if sombras:
        camada = _sombras(camada, sombras)
    return TextoRender(camada, palavras_out, linhas_out, pad_total)


def medir_texto(texto, nome_fonte, tamanho):
    f = fonte(nome_fonte, tamanho)
    try:
        return f.getlength(texto)
    except Exception:
        return f.getbbox(texto)[2]


def ajustar_tamanho(texto, nome_fonte, tamanho, largura_max, minimo=18, linhas_max=None, **kw):
    """Reduz o tamanho da fonte até o texto caber em largura_max (e em linhas_max, se dado)."""
    t = tamanho
    while t > minimo:
        r = render_texto(texto, nome_fonte, t, largura_max=largura_max, **kw)
        if linhas_max is None or len(r.linhas) <= linhas_max:
            maior = max((p[2] - p[0] for p in r.palavras), default=0)
            if maior <= largura_max:
                return t
        t *= 0.92
    return minimo


# ------------------------------------------------------------------ formas (SDF com antisserrilhado exato)
@lru_cache(256)
def _mascara_ret(w, h, r, esp=0.0):
    """Máscara L de retângulo arredondado (ou anel de borda se esp>0)."""
    w, h = int(w), int(h)
    r = max(0.0, min(float(r), w / 2.0, h / 2.0))
    ys = np.arange(h, dtype=np.float32) + 0.5
    xs = np.arange(w, dtype=np.float32) + 0.5
    qx = np.abs(xs - w / 2.0) - (w / 2.0 - r)
    qy = np.abs(ys - h / 2.0) - (h / 2.0 - r)
    qx = qx[None, :]
    qy = qy[:, None]
    mx = np.maximum(qx, 0)
    my = np.maximum(qy, 0)
    dist = np.sqrt(mx * mx + my * my) + np.minimum(np.maximum(qx, qy), 0) - r
    a = np.clip(0.5 - dist, 0, 1)
    if esp > 0:
        a = a * np.clip(dist + esp + 0.5, 0, 1)
    return Image.fromarray((a * 255).astype(np.uint8), "L")


def mascara_ret(w, h, r, esp=0.0):
    return _mascara_ret(int(round(w)), int(round(h)), round(float(r), 1), round(float(esp), 1))


def ret_arred(w, h, r, preench=(30, 30, 34, 255), borda=None, esp_borda=0, gradiente=None):
    """Retângulo arredondado RGBA. gradiente: (cor1, cor2, angulo_graus) substitui o preenchimento."""
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    if gradiente is not None:
        base = gradiente_linear(w, h, gradiente[0], gradiente[1], gradiente[2] if len(gradiente) > 2 else 90)
    else:
        base = Image.new("RGBA", (w, h), tuple(preench))
    a = mascara_ret(w, h, r)
    if base.mode == "RGBA":
        al = np.asarray(base.getchannel("A"), dtype=np.uint16) * np.asarray(a, dtype=np.uint16) // 255
        base.putalpha(Image.fromarray(al.astype(np.uint8), "L"))
    else:
        base.putalpha(a)
    if borda is not None and esp_borda > 0:
        anel = mascara_ret(w, h, r, esp_borda)
        camada = Image.new("RGBA", (w, h), tuple(borda))
        camada.putalpha(anel)
        base = Image.alpha_composite(base, camada)
    return base


def circulo(d, preench=(255, 255, 255, 255), borda=None, esp_borda=0):
    return ret_arred(d, d, d / 2.0, preench, borda, esp_borda)


def gradiente_linear(w, h, c1, c2, angulo=90):
    """Gradiente linear RGBA. angulo 90 = de cima (c1) para baixo (c2)."""
    c1, c2 = np.array(cor(c1), np.float32), np.array(cor(c2), np.float32)
    a = math.radians(angulo)
    dx, dy = math.cos(a), math.sin(a)
    xs = np.linspace(-0.5, 0.5, w, dtype=np.float32)[None, :]
    ys = np.linspace(-0.5, 0.5, h, dtype=np.float32)[:, None]
    proj = xs * dx * (w / max(w, h)) + ys * dy * (h / max(w, h))
    pmin, pmax = proj.min(), proj.max()
    t = (proj - pmin) / max(1e-6, pmax - pmin)
    arr = c1[None, None, :] * (1 - t[..., None]) + c2[None, None, :] * t[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def gradiente_radial(w, h, c_centro, c_borda, cx=0.5, cy=0.5, raio=0.75):
    c1, c2 = np.array(cor(c_centro), np.float32), np.array(cor(c_borda), np.float32)
    xs = (np.arange(w, dtype=np.float32) / max(1, w - 1) - cx)[None, :] * (w / max(w, h))
    ys = (np.arange(h, dtype=np.float32) / max(1, h - 1) - cy)[:, None] * (h / max(w, h))
    t = np.clip(np.sqrt(xs * xs + ys * ys) / raio, 0, 1)
    arr = c1 * (1 - t[..., None]) + c2 * t[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


@lru_cache(8)
def _fundo_cena(w, h, c1, c2, grao):
    g = gradiente_radial(w, h, c1, c2, 0.5, 0.32, 1.05)
    arr = np.asarray(g.convert("RGB"), np.float32)
    if grao > 0:  # grão fino evita "degraus" no gradiente e dá textura de filme
        arr += np.random.default_rng(7).normal(0, 255 * grao, (h, w, 1)).astype(np.float32)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def fundo_cena(w, h, estilo, tipo="gradiente"):
    """Fundo padrão de cenas geradas (gradiente sutil com luz no alto e grão fino)."""
    if tipo == "liso":
        return Image.new("RGB", (w, h), cor(estilo["fundo"])[:3])
    c1 = tuple(cor(estilo.get("fundo2", estilo["fundo"])))
    c2 = tuple(cor(estilo["fundo"]))
    return _fundo_cena(int(w), int(h), c1, c2, float(estilo.get("grao_fundo", 0.012))).copy()


# ------------------------------------------------------------------ materiais de cartão (vidro fosco, sólido, claro)
MATERIAIS = {
    # vidro escuro: desfoca o vídeo atrás, escurece e dá borda clara (padrão dos estilos modernos)
    "vidro": dict(tipo="vidro", tinta="#121214", opacidade=0.50, desfoque=34, saturacao=1.35, borda=0.20, brilho=0.07,
                  texto="claro"),
    # vidro claro (estilo iOS claro)
    "vidro_claro": dict(tipo="vidro", tinta="#F7F7F9", opacidade=0.80, desfoque=34, saturacao=1.6, borda=0.6,
                        brilho=0.0, texto="escuro"),
    # cartão sólido na cor 'cartao' do estilo
    "solido": dict(tipo="solido", tinta=None, opacidade=0.97, desfoque=0, saturacao=1.0, borda=0.10, brilho=0.04,
                   texto="claro"),
    # branco sólido (interfaces claras)
    "claro": dict(tipo="solido", tinta="#FFFFFF", opacidade=1.0, desfoque=0, saturacao=1.0, borda=0.0, brilho=0.0,
                  texto="escuro"),
    # preto translúcido sem desfoque (rótulos, chips)
    "preto": dict(tipo="solido", tinta="#000000", opacidade=0.58, desfoque=0, saturacao=1.0, borda=0.14, brilho=0.0,
                  texto="claro"),
}
ALIAS_MATERIAL = {"glass": "vidro", "fosco": "vidro", "vidro_escuro": "vidro", "light": "vidro_claro",
                  "solid": "solido", "escuro": "solido", "branco": "claro", "white": "claro", "black": "preto"}


def material(estilo=None, nome=None):
    """Resolve o material de um cartão: nome ('vidro', 'solido', 'claro', 'vidro_claro', 'preto') ou dict com
    ajustes. Sem nome, usa estilo['material'] (e os ajustes de estilo['vidro'] para os de vidro)."""
    estilo = estilo or {}
    extra = {}
    if isinstance(nome, dict):
        extra = dict(nome)
        nome = extra.pop("base", extra.pop("tipo_material", None))
    nome = nome or estilo.get("material", "vidro")
    nome = ALIAS_MATERIAL.get(str(nome).lower(), str(nome).lower())
    m = dict(MATERIAIS.get(nome, MATERIAIS["vidro"]))
    if m["tipo"] == "vidro" and nome == "vidro" and isinstance(estilo.get("vidro"), dict):
        m.update(estilo["vidro"])
    m.update(extra)
    if m.get("tinta") is None:
        m["tinta"] = estilo.get("cartao", "#151517")
    m["nome"] = nome
    return m


def cores_material(m, estilo):
    """(texto, texto_suave) legíveis sobre o material."""
    if m.get("texto") == "escuro":
        return cor(estilo.get("texto_cartao_escuro", "#0B0B0C"), estilo), cor(estilo.get("texto_cartao_escuro_suave", "#6B6B72"), estilo)
    return cor(estilo.get("texto_cartao", estilo.get("texto", "#FFFFFF")), estilo), \
        cor(estilo.get("texto_cartao_suave", estilo.get("texto_suave", "#B5B5BC")), estilo)


class Cartao:
    """Cartão pronto: sprite (sombra + tinta + borda + conteúdo) e a forma do vidro, com margem pad."""

    def __init__(self, sprite, forma, pad, mat, w, h, desfoque):
        self.sprite = sprite
        self.forma = forma
        self.pad = pad
        self.mat = mat
        self.w, self.h = w, h
        self.desfoque = desfoque
        self._forma_rgba = None

    def colar(self, img, x, y, ancora=(0, 0)):
        """Cola conteúdo RGBA no cartão; (x, y) relativo ao canto do cartão (sem a margem da sombra)."""
        if img is None:
            return self
        X = int(round(self.pad + x - ancora[0] * img.width))
        Y = int(round(self.pad + y - ancora[1] * img.height))
        compor(self.sprite, img, X, Y)
        return self

    def forma_rgba(self):
        if self._forma_rgba is None:
            f = Image.new("RGBA", self.forma.size, (255, 255, 255, 0))
            f.putalpha(self.forma)
            self._forma_rgba = f
        return self._forma_rgba

    def copia(self):
        c = Cartao(self.sprite.copy(), self.forma, self.pad, self.mat, self.w, self.h, self.desfoque)
        c._forma_rgba = self._forma_rgba
        return c


def compor(dst, src, x, y):
    """alpha_composite de src em dst (RGBA) na posição (x, y), aceitando posições fora da imagem."""
    x, y = int(round(x)), int(round(y))
    sx, sy = max(0, -x), max(0, -y)
    if sx >= src.width or sy >= src.height or x >= dst.width or y >= dst.height:
        return dst
    if sx or sy:
        src = src.crop((sx, sy, src.width, src.height))
    w = min(src.width, dst.width - max(0, x))
    h = min(src.height, dst.height - max(0, y))
    if w <= 0 or h <= 0:
        return dst
    if (w, h) != src.size:
        src = src.crop((0, 0, w, h))
    dst.alpha_composite(src, (max(0, x), max(0, y)))
    return dst


@lru_cache(64)
def _grad_vertical(h, a0, a1, ate=1.0):
    """Coluna L (1×h) com alfa indo de a0 (topo) a a1 (em 'ate' da altura) e mantendo a1 depois."""
    t = np.clip(np.arange(h, dtype=np.float32) / max(1.0, (h - 1) * ate), 0, 1)
    v = (a0 + (a1 - a0) * t) * 255
    return Image.fromarray(np.clip(v, 0, 255).astype(np.uint8)[:, None], "L")


def cartao(w, h, raio, estilo=None, mat=None, s=1.0, sombra=True, borda=True, forma=None):
    """Cria um Cartao w×h com o material pedido (ver material()). s = escala da resolução (W/1080).
    Para colar no quadro use colar_cartao (o vidro desfoca o que está atrás)."""
    m = material(estilo, mat)
    w, h = max(2, int(round(w))), max(2, int(round(h)))
    fm = forma if forma is not None else mascara_ret(w, h, raio)
    tinta = cor(m["tinta"], estilo)
    camada = Image.new("RGBA", (w, h), tinta[:3] + (int(255 * clamp01(m["opacidade"] * tinta[3] / 255.0)),))
    if m.get("brilho", 0) > 0:
        luz = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        luz.putalpha(_grad_vertical(h, m["brilho"], 0.0, 0.6).resize((w, h)))
        camada = Image.alpha_composite(camada, luz)
    a = np.asarray(camada.getchannel("A"), np.uint16) * np.asarray(fm, np.uint16) // 255
    camada.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    if borda and m.get("borda", 0) > 0:
        esp = max(1.0, 1.6 * s)
        anel = np.asarray(mascara_ret(w, h, raio, esp), np.float32)
        grad = np.asarray(_grad_vertical(h, 1.0, 0.42, 1.0), np.float32)[:, :1] / 255.0
        cb = (255, 255, 255) if m.get("texto") != "escuro" else (0, 0, 0)
        k = m["borda"] if m.get("texto") != "escuro" else m["borda"] * 0.12
        al = np.clip(anel * grad * k, 0, 255).astype(np.uint8)
        lb = Image.new("RGBA", (w, h), cb + (0,))
        lb.putalpha(Image.fromarray(al, "L"))
        camada = Image.alpha_composite(camada, lb)
    pad = 0
    sprite = camada
    if sombra:
        op = float(estilo.get("sombra", 0.32) if estilo else 0.32)
        if isinstance(sombra, dict):
            op = sombra.get("opacidade", op)
        rs = (sombra.get("raio", 42) if isinstance(sombra, dict) else 42) * s
        dy = (sombra.get("dy", 20) if isinstance(sombra, dict) else 20) * s
        sh, pad = so_sombra(fm, rs, 0, dy, op)
        if m["tipo"] == "vidro":  # sombra só por fora: o vidro não fica sujo
            fora = Image.new("L", sh.size, 0)
            fora.paste(fm, (pad, pad))
            al = np.asarray(sh.getchannel("A"), np.uint16) * (255 - np.asarray(fora, np.uint16)) // 255
            sh.putalpha(Image.fromarray(al.astype(np.uint8), "L"))
        sh.alpha_composite(camada, (pad, pad))
        sprite = sh
    fsp = Image.new("L", sprite.size, 0)
    fsp.paste(fm, (pad, pad))
    des = float(m.get("desfoque", 0)) * s if m["tipo"] == "vidro" else 0.0
    return Cartao(sprite, fsp, pad, m, w, h, des)


def clamp01(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def colar_cartao(base, c, x, y, ancora=(0.5, 0.5), escala=1.0, rot=0.0, opacidade=1.0):
    """Cola um Cartao: desfoca o quadro atrás da forma (vidro) e cola o sprite por cima.
    A âncora se refere ao cartão sem a margem da sombra."""
    if c is None or opacidade <= 0.003 or escala <= 0.003:
        return base
    sp = transformar(c.sprite, escala, rot)
    # posição: âncora relativa ao cartão (sem pad); o pad cresce junto com a escala
    cx = x - (ancora[0] - 0.5) * c.w * escala
    cy = y - (ancora[1] - 0.5) * c.h * escala
    px = int(round(cx - sp.width / 2))
    py = int(round(cy - sp.height / 2))
    if px >= base.width or py >= base.height or px + sp.width <= 0 or py + sp.height <= 0:
        return base
    if c.desfoque > 0.5 and base.mode == "RGB":
        forma = c.forma if (abs(escala - 1) < 1e-3 and abs(rot) < 0.05) else \
            transformar(c.forma_rgba(), escala, rot).getchannel("A")
        x0, y0 = max(0, px), max(0, py)
        x1, y1 = min(base.width, px + forma.width), min(base.height, py + forma.height)
        if x1 > x0 and y1 > y0:
            r = c.desfoque
            mg = int(r * 1.5) + 2
            X0, Y0, X1, Y1 = max(0, x0 - mg), max(0, y0 - mg), min(base.width, x1 + mg), min(base.height, y1 + mg)
            reg = desfocar(base.crop((X0, Y0, X1, Y1)), r)
            sat = float(c.mat.get("saturacao", 1.0))
            if abs(sat - 1) > 0.02:
                from PIL import ImageEnhance
                reg = ImageEnhance.Color(reg).enhance(sat)
            reg = reg.crop((x0 - X0, y0 - Y0, x1 - X0, y1 - Y0))
            mk = forma.crop((x0 - px, y0 - py, x1 - px, y1 - py))
            if opacidade < 0.999:
                mk = mk.point(lambda v, k=opacidade: int(v * k))
            base.paste(reg, (x0, y0), mk)
    if opacidade < 0.999:
        sp = opacidade_img(sp, opacidade)
    if base.mode == "RGBA":
        compor(base, sp, px, py)
        return base
    base.paste(sp, (px, py), sp)
    return base


def pilula(texto, estilo, s=1.0, mat="preto", cor_txt=None, tam=26, fonte_nome=None, cor_fundo=None, maiusculas=True,
           rastreio=2.4, pad_x=22, pad_y=10, icone_img=None):
    """Rótulo em pílula (ex. 'ANTES', 'EU', 'NOVO'). cor_fundo: cor sólida (texto contrastante automático)."""
    fn = fonte_nome or estilo.get("fonte_rotulo", "Inter-Bold")
    if cor_fundo is not None:
        cf = cor(cor_fundo, estilo)
        m = {"tinta": cf, "opacidade": cf[3] / 255.0, "borda": 0.0, "brilho": 0.0, "desfoque": 0, "tipo": "solido",
             "texto": "escuro" if luminancia(cf) > 0.6 else "claro"}
        ct = cor_txt or contraste_para(cf)
    else:
        m = mat
        ct = cor_txt or cores_material(material(estilo, mat), estilo)[0]
    r = render_texto(str(texto), fn, tam * s, ct, maiusculas=maiusculas, rastreio=rastreio * s)
    tw, th = r.img.width - 2 * r.pad, r.img.height - 2 * r.pad
    iw = (icone_img.width + 10 * s) if icone_img is not None else 0
    w, h = tw + iw + 2 * pad_x * s, th + 2 * pad_y * s
    c = cartao(w, h, h / 2, estilo, m, s=s, sombra=False)
    if icone_img is not None:
        c.colar(icone_img, pad_x * s, h / 2, (0, 0.5))
    c.colar(r.img, pad_x * s + iw - r.pad, (h - th) / 2 - r.pad)
    return c


# ------------------------------------------------------------------ sombra, desfoque, cantos
def desfocar(img, raio):
    if raio <= 0.5:
        return img
    w, h = img.size
    f = max(1.0, raio / 5.0)
    if f > 1.01:
        pw, ph = max(1, int(w / f)), max(1, int(h / f))
        small = img.resize((pw, ph), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(raio / f))
        return small.resize((w, h), Image.BILINEAR)
    return img.filter(ImageFilter.GaussianBlur(raio))


def com_sombra(img, raio=26, dx=0, dy=14, opacidade=0.5, cor_s=(0, 0, 0), expandir=True):
    """Retorna RGBA com sombra suave sob img. Se expandir, aumenta a tela (pad = raio*2 + deslocamento)."""
    if opacidade <= 0:
        return img
    pad = int(raio * 2 + max(abs(dx), abs(dy))) if expandir else 0
    w, h = img.size
    W, H = w + 2 * pad, h + 2 * pad
    alfa = img.getchannel("A")
    camada_a = Image.new("L", (W, H), 0)
    camada_a.paste(alfa, (pad + int(dx), pad + int(dy)))
    camada_a = desfocar(camada_a, raio)
    if opacidade != 1:
        camada_a = camada_a.point(lambda v: int(v * opacidade))
    sombra = Image.new("RGBA", (W, H), tuple(cor(cor_s))[:3] + (0,))
    sombra.putalpha(camada_a)
    out = sombra
    topo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    topo.paste(img, (pad, pad))
    out = Image.alpha_composite(out, topo)
    return out


def so_sombra(alfa, raio=26, dx=0, dy=14, opacidade=0.5, cor_s=(0, 0, 0)):
    """Somente a sombra (RGBA) de uma máscara L, com margem pad = raio*2 + deslocamento."""
    pad = int(raio * 2 + max(abs(dx), abs(dy)))
    w, h = alfa.size
    W, H = w + 2 * pad, h + 2 * pad
    camada_a = Image.new("L", (W, H), 0)
    camada_a.paste(alfa, (pad + int(dx), pad + int(dy)))
    camada_a = desfocar(camada_a, raio)
    if opacidade != 1:
        camada_a = camada_a.point(lambda v: int(v * opacidade))
    sombra = Image.new("RGBA", (W, H), tuple(cor(cor_s))[:3] + (0,))
    sombra.putalpha(camada_a)
    return sombra, pad


@lru_cache(48)
def _sombra_ret(w, h, r, raio, dx, dy, op):
    return so_sombra(mascara_ret(w, h, r), raio, dx, dy, op)


def com_sombra_ret(img, r, raio=26, dx=0, dy=14, opacidade=0.5):
    """Como com_sombra, mas para cartões retangulares/arredondados: a sombra é calculada uma vez e reaproveitada."""
    w, h = img.size
    sh, pad = _sombra_ret(w, h, round(float(r), 1), round(float(raio), 1), int(dx), int(dy), round(float(opacidade), 2))
    out = sh.copy()
    out.alpha_composite(img, (pad, pad))
    return out


def brilho_externo(img, raio=18, cor_b=(255, 255, 255), intensidade=0.8):
    """Halo (glow) ao redor do alfa da imagem."""
    return com_sombra(img, raio=raio, dx=0, dy=0, opacidade=intensidade, cor_s=cor_b)


def cantos(img, r):
    """Aplica cantos arredondados (retorna RGBA)."""
    img = img.convert("RGBA") if img.mode != "RGBA" else img.copy()
    if r <= 0:
        return img
    m = mascara_ret(img.width, img.height, r)
    a = np.asarray(img.getchannel("A"), dtype=np.uint16) * np.asarray(m, dtype=np.uint16) // 255
    img.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    return img


def borda_em(img, r, cor_b, esp):
    """Desenha borda (anel) sobre img RGBA com cantos r."""
    if esp <= 0:
        return img
    anel = mascara_ret(img.width, img.height, r, esp)
    camada = Image.new("RGBA", img.size, tuple(cor(cor_b)))
    camada.putalpha(anel)
    return Image.alpha_composite(img, camada)


def opacidade_img(img, op):
    if op >= 0.999:
        return img
    img = img.copy()
    a = img.getchannel("A").point(lambda v: int(v * max(0.0, op)))
    img.putalpha(a)
    return img


# ------------------------------------------------------------------ enquadramento de imagens
def cobrir(img, w, h, foco=(0.5, 0.5), zoom=1.0):
    """Recorta e redimensiona img para cobrir (w, h) sem distorcer, centrado em foco (0..1)."""
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    iw, ih = img.size
    esc = max(w / iw, h / ih) * max(1.0, zoom)
    cw, ch = w / esc, h / esc
    fx = min(max(foco[0] * iw - cw / 2, 0), iw - cw)
    fy = min(max(foco[1] * ih - ch / 2, 0), ih - ch)
    return img.resize((w, h), Image.BICUBIC, box=(fx, fy, fx + cw, fy + ch))


def conter(img, w, h):
    iw, ih = img.size
    esc = min(w / iw, h / ih)
    return img.resize((max(1, int(iw * esc)), max(1, int(ih * esc))), Image.BICUBIC)


# ------------------------------------------------------------------ colagem com transformação
try:
    import cv2 as _cv2  # opcional: rotação/escala bem mais rápidas
except Exception:  # pragma: no cover
    _cv2 = None


def _transformar_cv2(sprite, escala, rot):
    w, h = sprite.size
    a = math.radians(rot)
    c, s_ = abs(math.cos(a)) * escala, abs(math.sin(a)) * escala
    nw, nh = int(math.ceil(w * c + h * s_)), int(math.ceil(w * s_ + h * c))
    M = _cv2.getRotationMatrix2D((w / 2.0, h / 2.0), rot, escala)
    M[0, 2] += nw / 2.0 - w / 2.0
    M[1, 2] += nh / 2.0 - h / 2.0
    arr = np.asarray(sprite.convert("RGBa"))
    interp = _cv2.INTER_LINEAR if escala >= 0.6 else _cv2.INTER_AREA
    out = _cv2.warpAffine(arr, M, (max(1, nw), max(1, nh)), flags=interp, borderMode=_cv2.BORDER_CONSTANT,
                          borderValue=(0, 0, 0, 0))
    return Image.fromarray(out, "RGBa").convert("RGBA")


def transformar(sprite, escala=1.0, rot=0.0):
    """Escala e gira (graus, anti-horário) com alfa pré-multiplicado (sem halo escuro)."""
    if abs(escala - 1) < 1e-3 and abs(rot) < 0.05:
        return sprite
    w, h = sprite.size
    if _cv2 is not None and abs(rot) >= 0.05 and w * h > 40000:
        try:
            return _transformar_cv2(sprite, escala, rot)
        except Exception:
            pass
    pm = sprite.convert("RGBa")
    if abs(rot) < 0.05:
        nw, nh = max(1, int(round(w * escala))), max(1, int(round(h * escala)))
        return pm.resize((nw, nh), Image.BICUBIC).convert("RGBA")
    if abs(escala - 1) >= 1e-3:
        nw, nh = max(1, int(round(w * escala))), max(1, int(round(h * escala)))
        pm = pm.resize((nw, nh), Image.BICUBIC)
    pm = pm.rotate(rot, Image.BICUBIC, expand=True)
    return pm.convert("RGBA")


def colar(base, sprite, x, y, ancora=(0.5, 0.5), escala=1.0, rot=0.0, opacidade=1.0):
    """Cola sprite RGBA em base (RGB) de modo que o ponto 'ancora' do sprite fique em (x, y)."""
    if sprite is None or opacidade <= 0.003 or escala <= 0.003:
        return base
    sp = transformar(sprite, escala, rot)
    if opacidade < 0.999:
        sp = opacidade_img(sp, opacidade)
    px = int(round(x - ancora[0] * sp.width))
    py = int(round(y - ancora[1] * sp.height))
    if px >= base.width or py >= base.height or px + sp.width <= 0 or py + sp.height <= 0:
        return base
    if base.mode == "RGBA":
        camada = Image.new("RGBA", base.size, (0, 0, 0, 0))
        camada.paste(sp, (px, py))
        return Image.alpha_composite(base, camada)
    base.paste(sp, (px, py), sp)
    return base


def _coef_perspectiva(src, dst):
    """Coeficientes para Image.transform(PERSPECTIVE) que mapeiam dst (saída) -> src (entrada)."""
    A, B = [], []
    for (xs, ys), (xd, yd) in zip(src, dst):
        A.append([xd, yd, 1, 0, 0, 0, -xs * xd, -xs * yd])
        A.append([0, 0, 0, xd, yd, 1, -ys * xd, -ys * yd])
        B.extend([xs, ys])
    return np.linalg.solve(np.array(A, np.float64), np.array(B, np.float64)).tolist()


def perspectiva(sprite, cantos_dst):
    """Deforma sprite para os 4 cantos de destino [(tl),(tr),(br),(bl)] (coords absolutas).
    Retorna (imagem, (x0, y0)) — posição do canto superior esquerdo do resultado."""
    xs = [p[0] for p in cantos_dst]
    ys = [p[1] for p in cantos_dst]
    x0, y0 = int(math.floor(min(xs))), int(math.floor(min(ys)))
    x1, y1 = int(math.ceil(max(xs))), int(math.ceil(max(ys)))
    W, H = max(1, x1 - x0), max(1, y1 - y0)
    w, h = sprite.size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(p[0] - x0, p[1] - y0) for p in cantos_dst]
    try:
        coef = _coef_perspectiva(src, dst)
    except np.linalg.LinAlgError:
        return sprite, (x0, y0)
    pm = sprite.convert("RGBa")
    out = pm.transform((W, H), Image.PERSPECTIVE, coef, Image.BICUBIC).convert("RGBA")
    return out, (x0, y0)


def projetar_cartao(w, h, cx, cy, rx=0.0, ry=0.0, rz=0.0, escala=1.0, focal=1800.0):
    """Cantos 2D de um cartão w×h girado em 3D (graus) com centro em (cx, cy)."""
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    out = []
    for x, y in pts:
        x, y, z = x * escala, y * escala, 0.0
        # rotação z
        x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
        # rotação x (inclina para trás)
        y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
        # rotação y
        x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
        f = focal / (focal + z)
        out.append((cx + x * f, cy + y * f))
    return out


# ------------------------------------------------------------------ texturas
def ruido_img(w, h, intensidade=0.06, semente=0, mono=True):
    rng = np.random.default_rng(semente)
    if mono:
        n = rng.normal(0, 255 * intensidade, (h, w)).astype(np.float32)
        return n[..., None]
    return rng.normal(0, 255 * intensidade, (h, w, 3)).astype(np.float32)


def textura_papel(w, h, base=(250, 247, 241), semente=3):
    rng = np.random.default_rng(semente)
    arr = np.ones((h, w, 3), np.float32) * np.array(base[:3], np.float32)
    fino = rng.normal(0, 3.2, (h, w, 1)).astype(np.float32)
    grosso = rng.normal(0, 1, (max(2, h // 24), max(2, w // 24))).astype(np.float32)
    grosso = np.asarray(Image.fromarray(((grosso * 18) + 128).clip(0, 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
                        np.float32)[..., None] - 128
    arr += fino + grosso * 0.12
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB").convert("RGBA")


# ------------------------------------------------------------------ ícones vetoriais (desenhados em 4x)
def _tela(s, ss=4):
    S = int(s * ss)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im), S


def _reduzir(im, s):
    return im.resize((int(s), int(s)), Image.LANCZOS)


def _linha_grossa(d, pts, larg, c):
    d.line(pts, fill=c, width=int(larg), joint="curve")
    r = larg / 2.0
    for (x, y) in (pts[0], pts[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=c)


def icone(nome, s=96, c=(255, 255, 255, 255), progresso=1.0, preenchido=True):
    """Ícones: coracao, balao, aviao, marcador, check, xis, seta_baixo, seta_cima, seta_dir, seta_esq, cursor,
    play, sino, estrela, faisca, raio, link, carrinho, presente, cadeado, lupa, mais, enviar, usuario, chip,
    olho, relogio, fogo, dinheiro."""
    c = tuple(cor(c))
    im, d, S = _tela(s)
    u = S / 100.0
    nome = str(nome).lower()
    lw = 9 * u
    if nome in ("coracao", "heart", "curtir"):
        pts = []
        for i in range(181):
            t = math.pi * 2 * i / 180
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts.append((50 * u + x * 2.85 * u, 46 * u - y * 2.85 * u))
        if preenchido:
            d.polygon(pts, fill=c)
        else:
            d.line(pts + [pts[0]], fill=c, width=int(lw), joint="curve")
    elif nome in ("balao", "comentario", "comment", "comentar"):
        if preenchido:
            d.ellipse([8 * u, 12 * u, 92 * u, 80 * u], fill=c)
            d.polygon([(22 * u, 66 * u), (14 * u, 92 * u), (42 * u, 76 * u)], fill=c)
        else:
            d.ellipse([10 * u, 12 * u, 90 * u, 78 * u], outline=c, width=int(lw))
            d.polygon([(22 * u, 66 * u), (14 * u, 92 * u), (40 * u, 76 * u)], fill=c)
    elif nome in ("aviao", "compartilhar", "share", "enviar_aviao"):
        d.polygon([(8 * u, 46 * u), (92 * u, 10 * u), (60 * u, 92 * u), (46 * u, 56 * u)], fill=c)
        d.polygon([(46 * u, 56 * u), (92 * u, 10 * u), (40 * u, 50 * u)], fill=(0, 0, 0, 0))
        d.line([(46 * u, 56 * u), (92 * u, 10 * u)], fill=(0, 0, 0, 0), width=int(4 * u))
    elif nome in ("marcador", "salvar", "save", "bookmark"):
        poly = [(22 * u, 8 * u), (78 * u, 8 * u), (78 * u, 92 * u), (50 * u, 70 * u), (22 * u, 92 * u)]
        if preenchido:
            d.polygon(poly, fill=c)
        else:
            d.line(poly + [poly[0]], fill=c, width=int(lw), joint="curve")
    elif nome in ("check", "ok", "visto"):
        p = max(0.0, min(1.0, progresso))
        a, b, e = (20 * u, 52 * u), (42 * u, 74 * u), (82 * u, 28 * u)
        l1 = math.dist(a, b)
        l2 = math.dist(b, e)
        L = (l1 + l2) * p
        if L > 0:
            if L <= l1:
                fpt = (a[0] + (b[0] - a[0]) * L / l1, a[1] + (b[1] - a[1]) * L / l1)
                _linha_grossa(d, [a, fpt], 13 * u, c)
            else:
                q = (L - l1) / l2
                fpt = (b[0] + (e[0] - b[0]) * q, b[1] + (e[1] - b[1]) * q)
                _linha_grossa(d, [a, b, fpt], 13 * u, c)
    elif nome in ("xis", "x", "fechar", "errado"):
        _linha_grossa(d, [(24 * u, 24 * u), (76 * u, 76 * u)], 13 * u, c)
        _linha_grossa(d, [(76 * u, 24 * u), (24 * u, 76 * u)], 13 * u, c)
    elif nome.startswith("seta"):
        ang = {"seta_baixo": 90, "seta_cima": -90, "seta_dir": 0, "seta_esq": 180, "seta": 0}.get(nome, 0)
        tmp, td, _ = _tela(s)
        _linha_grossa(td, [(14 * u, 50 * u), (80 * u, 50 * u)], 12 * u, c)
        _linha_grossa(td, [(56 * u, 24 * u), (84 * u, 50 * u), (56 * u, 76 * u)], 12 * u, c)
        im = tmp.rotate(-ang, Image.BICUBIC)
    elif nome in ("cursor", "mouse", "ponteiro"):
        poly = [(22 * u, 6 * u), (22 * u, 82 * u), (40 * u, 66 * u), (54 * u, 94 * u), (66 * u, 88 * u),
                (52 * u, 60 * u), (76 * u, 58 * u)]
        d.polygon(poly, fill=(20, 20, 22, 255))
        inner = [(28 * u, 20 * u), (28 * u, 68 * u), (41 * u, 56 * u), (56 * u, 86 * u), (58 * u, 85 * u),
                 (44 * u, 54 * u), (62 * u, 53 * u)]
        d.polygon(inner, fill=c)
    elif nome in ("play", "reproduzir"):
        d.polygon([(30 * u, 18 * u), (30 * u, 82 * u), (82 * u, 50 * u)], fill=c)
    elif nome in ("sino", "notificacao", "bell"):
        d.pieslice([20 * u, 12 * u, 80 * u, 72 * u], 180, 360, fill=c)
        d.rectangle([20 * u, 42 * u, 80 * u, 70 * u], fill=c)
        d.polygon([(12 * u, 76 * u), (88 * u, 76 * u), (80 * u, 66 * u), (20 * u, 66 * u)], fill=c)
        d.ellipse([40 * u, 76 * u, 60 * u, 94 * u], fill=c)
    elif nome in ("estrela", "star"):
        pts = []
        for i in range(10):
            r = 44 * u if i % 2 == 0 else 19 * u
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((50 * u + r * math.cos(a), 52 * u + r * math.sin(a)))
        d.polygon(pts, fill=c)
    elif nome in ("faisca", "brilho", "sparkle", "ia"):
        pts = []
        for i in range(8):
            r = 46 * u if i % 2 == 0 else 11 * u
            a = -math.pi / 2 + i * math.pi / 4
            pts.append((50 * u + r * math.cos(a), 50 * u + r * math.sin(a)))
        d.polygon(pts, fill=c)
    elif nome in ("raio", "energia", "rapido"):
        d.polygon([(58 * u, 4 * u), (18 * u, 56 * u), (46 * u, 56 * u), (38 * u, 96 * u), (82 * u, 40 * u),
                   (54 * u, 40 * u)], fill=c)
    elif nome in ("link", "corrente"):
        tmp, td, _ = _tela(s)
        td.rounded_rectangle([8 * u, 36 * u, 58 * u, 64 * u], radius=14 * u, outline=c, width=int(9 * u))
        td.rounded_rectangle([42 * u, 36 * u, 92 * u, 64 * u], radius=14 * u, outline=c, width=int(9 * u))
        im = tmp.rotate(40, Image.BICUBIC)
    elif nome in ("carrinho", "comprar", "cart"):
        d.line([(6 * u, 16 * u), (20 * u, 16 * u), (30 * u, 62 * u), (80 * u, 62 * u), (90 * u, 30 * u),
                (24 * u, 30 * u)], fill=c, width=int(lw), joint="curve")
        d.ellipse([30 * u, 72 * u, 44 * u, 86 * u], fill=c)
        d.ellipse([66 * u, 72 * u, 80 * u, 86 * u], fill=c)
    elif nome in ("presente", "gift"):
        d.rectangle([14 * u, 36 * u, 86 * u, 52 * u], fill=c)
        d.rectangle([20 * u, 54 * u, 80 * u, 92 * u], fill=c)
        d.rectangle([45 * u, 36 * u, 55 * u, 92 * u], fill=(0, 0, 0, 0))
        d.ellipse([26 * u, 14 * u, 50 * u, 36 * u], outline=c, width=int(7 * u))
        d.ellipse([50 * u, 14 * u, 74 * u, 36 * u], outline=c, width=int(7 * u))
    elif nome in ("cadeado", "seguro", "lock"):
        d.rounded_rectangle([18 * u, 44 * u, 82 * u, 92 * u], radius=10 * u, fill=c)
        d.arc([30 * u, 12 * u, 70 * u, 60 * u], 180, 360, fill=c, width=int(9 * u))
        d.line([(30 * u, 36 * u), (30 * u, 46 * u)], fill=c, width=int(9 * u))
        d.line([(70 * u, 36 * u), (70 * u, 46 * u)], fill=c, width=int(9 * u))
    elif nome in ("lupa", "buscar", "search"):
        d.ellipse([10 * u, 10 * u, 66 * u, 66 * u], outline=c, width=int(10 * u))
        _linha_grossa(d, [(58 * u, 58 * u), (88 * u, 88 * u)], 13 * u, c)
    elif nome in ("mais", "plus", "+"):
        _linha_grossa(d, [(50 * u, 18 * u), (50 * u, 82 * u)], 11 * u, c)
        _linha_grossa(d, [(18 * u, 50 * u), (82 * u, 50 * u)], 11 * u, c)
    elif nome in ("enviar", "send", "seta_enviar"):
        _linha_grossa(d, [(50 * u, 82 * u), (50 * u, 20 * u)], 11 * u, c)
        _linha_grossa(d, [(24 * u, 44 * u), (50 * u, 18 * u), (76 * u, 44 * u)], 11 * u, c)
    elif nome in ("usuario", "pessoa", "perfil", "user"):
        d.ellipse([30 * u, 8 * u, 70 * u, 48 * u], fill=c)
        d.pieslice([12 * u, 54 * u, 88 * u, 130 * u], 180, 360, fill=c)
    elif nome in ("chip", "processador", "cpu"):
        d.rounded_rectangle([24 * u, 24 * u, 76 * u, 76 * u], radius=8 * u, outline=c, width=int(7 * u))
        d.rounded_rectangle([38 * u, 38 * u, 62 * u, 62 * u], radius=4 * u, fill=c)
        for k in (36, 50, 64):
            for (a1, b1, a2, b2) in ((k, 8, k, 24), (k, 76, k, 92), (8, k, 24, k), (76, k, 92, k)):
                d.line([(a1 * u, b1 * u), (a2 * u, b2 * u)], fill=c, width=int(6 * u))
    elif nome in ("olho", "ver", "eye"):
        d.chord([6 * u, 24 * u, 94 * u, 76 * u], 0, 360, outline=c, width=int(8 * u))
        d.ellipse([36 * u, 36 * u, 64 * u, 64 * u], fill=c)
    elif nome in ("relogio", "tempo", "clock"):
        d.ellipse([8 * u, 8 * u, 92 * u, 92 * u], outline=c, width=int(9 * u))
        _linha_grossa(d, [(50 * u, 50 * u), (50 * u, 24 * u)], 9 * u, c)
        _linha_grossa(d, [(50 * u, 50 * u), (68 * u, 60 * u)], 9 * u, c)
    elif nome in ("fogo", "fire", "quente"):
        pts = []
        for i in range(121):
            t = i / 120 * 2 * math.pi
            r = 1 - 0.25 * math.sin(t) ** 2
            x = 50 + 36 * math.sin(t) * r
            y = 60 - 40 * math.cos(t) * (1.0 if math.cos(t) < 0 else 0.85) - (22 * max(0, -math.cos(t)) ** 3)
            pts.append((x * u, y * u))
        d.polygon(pts, fill=c)
    elif nome in ("dinheiro", "cifrao", "money"):
        f = fonte("Inter-Black", 90 * u)
        d.text((50 * u, 52 * u), "$", font=f, fill=c, anchor="mm")
    else:
        d.ellipse([20 * u, 20 * u, 80 * u, 80 * u], fill=c)
    return _reduzir(im, s)
