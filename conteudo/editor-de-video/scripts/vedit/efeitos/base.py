"""Classe base dos efeitos, registro por nome/alias e utilitários de animação/posição."""
import difflib

from PIL import Image

from .. import grafico as G
from ..tempo import clamp, easing, lerp, mola, volta
from ..util import ErroPlano, aviso, num, sem_acento

REGISTRO = {}
ALIASES = {}
FASES = {"camera": 0, "base": 1, "cena": 2, "sobre": 3, "legenda": 4, "final": 5}


def registrar(nome, *aliases):
    def deco(cls):
        cls.nome = nome
        REGISTRO[nome] = cls
        for a in aliases:
            ALIASES[a] = nome
        return cls
    return deco


def normalizar_tipo(t):
    t = sem_acento(str(t)).strip().lower().replace(" ", "_").replace("-", "_")
    if t.startswith("efeito_"):
        t = t[7:]
    return ALIASES.get(t, t)


def criar_efeito(spec, ctx):
    tipo = normalizar_tipo(spec.get("tipo", ""))
    if tipo not in REGISTRO:
        sug = difflib.get_close_matches(tipo, list(REGISTRO) + list(ALIASES), n=3, cutoff=0.5)
        raise ErroPlano("Efeito desconhecido '%s'. Parecidos: %s. Rode 'editor.py efeitos' para a lista."
                        % (spec.get("tipo"), ", ".join(sug) or "—"))
    return REGISTRO[tipo](spec, ctx)


POSICOES = {
    "centro": (0.5, 0.5), "meio": (0.5, 0.5), "center": (0.5, 0.5),
    "topo": (0.5, 0.15), "top": (0.5, 0.15), "cima": (0.5, 0.15),
    "terco_superior": (0.5, 0.28), "superior": (0.5, 0.28), "alto": (0.5, 0.28),
    "terco_inferior": (0.5, 0.66), "inferior": (0.5, 0.66),
    "baixo": (0.5, 0.75), "bottom": (0.5, 0.75), "embaixo": (0.5, 0.75),
    "rodape": (0.5, 0.82),
    "sup_esq": (0.25, 0.14), "sup_dir": (0.75, 0.14), "inf_esq": (0.25, 0.78), "inf_dir": (0.75, 0.78),
    "esquerda": (0.27, 0.5), "direita": (0.73, 0.5),
}


class Efeito:
    nome = "base"
    fase = "sobre"
    duracao_padrao = 3.0
    entrada_padrao = "subir"
    saida_padrao = "fade"
    som_entrada = None
    vol_som = 0.35

    def __init__(self, spec, ctx):
        self.spec = spec
        self.ctx = ctx
        self.e = ctx.estilo
        self.s = ctx.s
        self.W, self.H = ctx.W, ctx.H
        ini = spec.get("inicio", 0.0)
        self.t0 = ctx.resolver_tempo(ini)
        if spec.get("fim") is not None:
            self.t1 = ctx.resolver_tempo(spec.get("fim"), fim=True)
        elif spec.get("duracao") is not None:
            self.t1 = self.t0 + num(spec.get("duracao"), self.duracao_padrao)
        else:
            self.t1 = self.t0 + self.duracao_padrao
        if spec.get("tudo") or spec.get("video_inteiro"):
            self.t0, self.t1 = 0.0, ctx.duracao + 1
        self.t0 = max(0.0, self.t0)
        if self.t1 <= self.t0:
            aviso("efeito '%s' com fim <= início (%.2f) — usando duração padrão" % (self.nome, self.t0))
            self.t1 = self.t0 + self.duracao_padrao
        self.dur = self.t1 - self.t0
        self.d_in = num(spec.get("duracao_entrada"), 0.5)
        self.d_out = num(spec.get("duracao_saida"), 0.28)
        sa = spec.get("saida_anim", spec.get("saida"))
        if isinstance(sa, dict):
            self.d_out = num(sa.get("duracao"), self.d_out)
            sa = sa.get("tipo")
        en = spec.get("entrada")
        if isinstance(en, dict):
            self.d_in = num(en.get("duracao"), self.d_in)
            en = en.get("tipo")
        self.anim_in = str(en or self.entrada_padrao)
        self.anim_out = str(sa or self.saida_padrao)
        if self.d_in + self.d_out > self.dur:
            k = self.dur / max(1e-6, self.d_in + self.d_out)
            self.d_in *= k
            self.d_out *= k
        self.preparar()

    # ---------------------------------------------------------------- ganchos
    def preparar(self):
        pass

    def ativo(self, t):
        return self.t0 <= t < self.t1

    def aplicar(self, img, t):
        return img

    def area(self, t):
        """Caixa (x0, y0, x1, y1) em px que o efeito ocupa na tela em t, ou None. Legendas e títulos usam isso
        para desviar (não colidir com cartões, CTAs, prints...)."""
        return None

    @staticmethod
    def caixa(cx, cy, w, h, m=0.0):
        return (cx - w / 2 - m, cy - h / 2 - m, cx + w / 2 + m, cy + h / 2 + m)

    def sons(self):
        som = self.spec.get("som", self.som_entrada)
        if som in (None, False, "nenhum", "") or not self.ctx.sons_auto:
            return self.sons_extra() if self.ctx.sons_auto else []
        return [(self.t0, str(som), num(self.spec.get("volume_som"), self.vol_som))] + self.sons_extra()

    def sons_extra(self):
        return []

    # ---------------------------------------------------------------- utilitários
    def px(self, v):
        return float(v) * self.s

    def cor(self, c, alpha=None):
        return G.cor(c, self.e, alpha)

    def param(self, nome, padrao=None):
        v = self.spec.get(nome)
        return padrao if v is None else v

    def pos(self, p=None, padrao="centro"):
        p = self.spec.get("posicao", padrao) if p is None else p
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            x, y = num(p[0], 0.5), num(p[1], 0.5)
        elif isinstance(p, dict):
            x, y = num(p.get("x"), 0.5), num(p.get("y"), 0.5)
        else:
            x, y = POSICOES.get(sem_acento(str(p)).lower(), POSICOES.get(padrao, (0.5, 0.5)))
        # valores > 1.5 são pixels na referência 1080
        X = x * self.s if x > 1.5 else x * self.W
        Y = y * self.s if y > 1.5 else y * self.H
        return X, Y

    def local(self, t):
        return t - self.t0

    def p_entrada(self, t, d=None):
        return clamp((t - self.t0) / max(1e-6, d if d is not None else self.d_in))

    def p_saida(self, t, d=None):
        d = d if d is not None else self.d_out
        return clamp((t - (self.t1 - d)) / max(1e-6, d))

    def anim(self, t, dist=60):
        """Transformação de entrada+saída: dict(op, dx, dy, esc, rot). Movimento de editor: ease-out expo
        (arranca rápido e assenta devagar), leve escala junto e saída curta."""
        r = {"op": 1.0, "dx": 0.0, "dy": 0.0, "esc": 1.0, "rot": 0.0}
        D = self.px(dist)
        pi = self.p_entrada(t)
        a = self.anim_in
        if pi < 1 and a not in ("nenhuma", "none", "corte"):
            q = easing("expo")(pi)
            r["op"] *= clamp(pi * 2.6)
            if a in ("subir", "up", "baixo"):
                r["dy"] += D * (1 - q)
                r["esc"] *= 0.965 + 0.035 * q
            elif a in ("descer", "down", "cima"):
                r["dy"] -= D * (1 - q)
                r["esc"] *= 0.965 + 0.035 * q
            elif a in ("esquerda", "da_esquerda", "left"):
                r["dx"] -= D * 2.2 * (1 - q)
            elif a in ("direita", "da_direita", "right"):
                r["dx"] += D * 2.2 * (1 - q)
            elif a in ("pop", "estourar"):
                r["esc"] *= 0.55 + 0.45 * volta(pi, 1.9)
                r["op"] = clamp(pi * 4)
            elif a in ("mola", "spring"):
                r["esc"] *= 0.3 + 0.7 * mola(pi)
                r["op"] = clamp(pi * 4)
            elif a in ("zoom", "aproximar"):
                r["esc"] *= 1.18 - 0.18 * q
            elif a in ("girar", "rodar"):
                r["rot"] += -10 * (1 - q)
                r["esc"] *= 0.75 + 0.25 * volta(pi)
            elif a in ("fade", "aparecer"):
                r["op"] = easing("entrada")(pi)
                r["esc"] *= 0.985 + 0.015 * q
        po = self.p_saida(t)
        a = self.anim_out
        if po > 0 and a not in ("nenhuma", "none", "corte"):
            q = easing("saida")(po)
            r["op"] *= 1 - easing("entrada")(po)
            if a in ("subir", "up"):
                r["dy"] -= D * q
            elif a in ("descer", "down"):
                r["dy"] += D * q
            elif a in ("esquerda", "left"):
                r["dx"] -= D * 2 * q
            elif a in ("direita", "right"):
                r["dx"] += D * 2 * q
            elif a in ("encolher", "pop", "diminuir"):
                r["esc"] *= 1 - 0.3 * q
            elif a in ("zoom", "aumentar"):
                r["esc"] *= 1 + 0.2 * q
            else:
                r["esc"] *= 1 - 0.025 * q
        return r

    def colar_anim(self, img, sprite, x, y, t, ancora=(0.5, 0.5), dist=60, extra_esc=1.0, extra_rot=0.0,
                   extra_op=1.0):
        a = self.anim(t, dist)
        return G.colar(img, sprite, x + a["dx"], y + a["dy"], ancora, a["esc"] * extra_esc,
                       a["rot"] + extra_rot, a["op"] * extra_op)

    # ---------------------------------------------------------------- cartões e sombras do estilo
    def material(self, nome=None):
        return G.material(self.e, nome if nome is not None else self.param("material"))

    def cartao(self, w, h, raio=None, mat=None, sombra=True, borda=True):
        """Cartão no material do estilo (vidro fosco por padrão). Cole com self.colar_cartao."""
        r = self.px(self.e["raio"]) if raio is None else raio
        return G.cartao(w, h, r, self.e, mat if mat is not None else self.param("material"), s=self.s,
                        sombra=sombra, borda=borda)

    def cores_cartao(self, mat=None):
        """(texto, texto_suave) para usar dentro do cartão do material."""
        return G.cores_material(self.material(mat), self.e)

    def colar_cartao(self, img, c, x, y, t=None, ancora=(0.5, 0.5), escala=1.0, rot=0.0, opacidade=1.0, a=None):
        """Cola um Cartao com a animação de entrada/saída do efeito (se t for dado)."""
        if a is None and t is not None:
            a = self.anim(t)
        if a is None:
            a = {"op": 1.0, "dx": 0.0, "dy": 0.0, "esc": 1.0, "rot": 0.0}
        return G.colar_cartao(img, c, x + a["dx"], y + a["dy"], ancora, a["esc"] * escala, a["rot"] + rot,
                              a["op"] * opacidade)

    def sombra_texto(self, k=1.0, cor="#000000"):
        """Sombra suave em duas camadas (contato + difusa) do estilo, para texto sobre vídeo."""
        camadas = self.e.get("sombra_texto") or [[3, 1, 0.32], [18, 6, 0.42]]
        return [{"raio": self.px(c[0]) * k, "dy": self.px(c[1]) * k, "opacidade": min(1.0, c[2] * (k if k < 1 else 1.0)),
                 "cor": cor} for c in camadas]

    def pilula(self, texto, destaque=False, tam=26, mat="preto", cor_fundo=None, **kw):
        cf = cor_fundo if cor_fundo is not None else ("destaque" if destaque else None)
        return G.pilula(texto, self.e, self.s, mat=mat, tam=tam, cor_fundo=cf, **kw)

    # fontes de quadro (vídeo/imagem/texto) usadas em painéis, cartões, galerias...
    def quadro_de(self, fonte, t, base, tamanho=None):
        return self.ctx.quadro_fonte(fonte, t, self.t0, base, tamanho)

    def texto(self, txt, tamanho=60, fonte="fonte_texto", cor="texto", **kw):
        """Texto no padrão do estilo (tamanho em px na referência 1080). Aceita os mesmos argumentos de
        G.render_texto; sombra=True usa a sombra suave do estilo."""
        nf = self.e.get(fonte, fonte)
        kw["cor_destaque"] = self.cor(kw.get("cor_destaque") or "destaque")
        kw.setdefault("fonte_destaque", self.e.get("fonte_destaque"))
        kw.setdefault("marca_solida", bool(self.e.get("marca_solida", True)))
        if kw.get("sombra") is True:
            kw["sombra"] = self.sombra_texto()
        return G.render_texto(txt, nf, self.px(tamanho), self.cor(cor), **kw)
