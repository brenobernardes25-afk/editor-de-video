"""Elementos de interface: barra de prompt, checklist, cartão de desconto (cupom), CTA ilustrativo, notificação,
conversa (mensagens) e barra de progresso. Imitam interfaces reais sem usar marcas."""
import math

import numpy as np
from PIL import Image, ImageDraw

from .. import grafico as G
from ..tempo import clamp, easing, entrada, expo, lerp, mola, suave, volta
from ..util import num
from .base import Efeito, registrar


def _brilho_diagonal(w, h, p, largura=0.22, forca=0.55):
    """Faixa de brilho diagonal (RGBA) na posição p (0..1)."""
    xs = np.arange(w, dtype=np.float32)[None, :] / max(1, w)
    ys = np.arange(h, dtype=np.float32)[:, None] / max(1, h)
    d = (xs + ys * 0.45) - lerp(-0.4, 1.6, p)
    a = np.clip(1 - np.abs(d) / largura, 0, 1) ** 2 * 255 * forca
    m = Image.fromarray(a.astype(np.uint8), "L")
    im = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    im.putalpha(m)
    return im


def _mat_solido(c, borda=0.1, texto=None):
    c = tuple(c)
    return {"tipo": "solido", "tinta": c, "opacidade": c[3] / 255.0 if len(c) > 3 else 1.0, "borda": borda,
            "brilho": 0.0, "desfoque": 0, "texto": texto or ("escuro" if G.luminancia(c) > 0.6 else "claro")}


def _pontos_pensando(t, cor_p, s, n=3):
    """Três pontinhos pulsando (pensando/digitando)."""
    d = int(16 * s)
    gap = int(12 * s)
    im = Image.new("RGBA", (n * d + (n - 1) * gap, int(d * 2.2)), (0, 0, 0, 0))
    for k in range(n):
        fase = 0.5 + 0.5 * math.sin(t * 7.5 - k * 0.9)
        dot = G.circulo(d, tuple(cor_p[:3]) + (int(110 + 145 * fase),))
        im.paste(dot, (k * (d + gap), int(d * 0.6 - fase * d * 0.45)), dot)
    return im


@registrar("barra_prompt", "prompt", "barra_de_prompt", "caixa_de_texto", "digitando_prompt", "chat_input",
           "campo_de_busca", "busca")
class BarraPrompt(Efeito):
    """Barra de prompt (estilo chat de IA, sem marca) com o texto sendo digitado, botão de enviar e resposta
    opcional. texto (o prompt), placeholder, velocidade (caracteres/s, padrão 20), tema: 'escuro' | 'claro' |
    'vidro', resposta (texto que aparece num cartão acima depois do envio, com 'pensando…' antes), cursor (true =
    ponteiro do mouse clica em enviar), posicao (padrão 'centro'), largura (0..1, padrão 0.88), tamanho (padrão 42)."""
    entrada_padrao = "subir"
    duracao_padrao = 5.0
    som_entrada = "swish"
    vol_som = 0.18

    TEMAS = {
        "escuro": dict(bg=(43, 43, 46, 252), borda=0.10, txt=(244, 244, 246, 255), ph=(150, 150, 158, 255),
                       ic=(170, 170, 178, 255), env=(255, 255, 255, 255), env_off=(78, 78, 84, 255), resp=(30, 30, 33, 250)),
        "claro": dict(bg=(255, 255, 255, 255), borda=0.0, txt=(14, 14, 16, 255), ph=(142, 142, 147, 255),
                      ic=(120, 120, 126, 255), env=(14, 14, 16, 255), env_off=(209, 209, 214, 255), resp=(255, 255, 255, 255)),
    }

    def preparar(self):
        e = self.e
        self.txt = str(self.param("texto", ""))
        self.vel = num(self.param("velocidade"), 20)
        tema = str(self.param("tema", "escuro"))
        tema = {"light": "claro", "branco": "claro", "dark": "escuro", "glass": "vidro"}.get(tema, tema)
        self.tema = tema if tema in ("escuro", "claro", "vidro") else "escuro"
        self.T = dict(self.TEMAS["claro" if self.tema == "claro" else "escuro"])
        if self.tema == "vidro":
            self.T.update(txt=(255, 255, 255, 255), ph=(220, 220, 226, 200), ic=(230, 230, 236, 220))
        self.tam = self.px(num(self.param("tamanho"), 42))
        self.w = self.W * num(self.param("largura"), 0.88)
        self.x, self.y = self.pos(None, "centro")
        self.t_dig = self.t0 + self.d_in + 0.15
        self.t_fim_dig = self.t_dig + len(self.txt) / max(1, self.vel)
        self.t_envio = self.t_fim_dig + num(self.param("pausa_envio"), 0.35)
        self.resp = self.param("resposta")
        self.tem_cursor = bool(self.param("cursor", False))
        self.placeholder = str(self.param("placeholder", "Pergunte qualquer coisa"))
        self._cache = {}
        self.fn = e.get("fonte_ui", "Inter-Medium")
        self.pad_l, self.pad_r = self.px(100), self.px(124)
        self.d_bot = self.px(80)
        self.resp_h = 0
        if self.resp:
            rf = G.render_texto(str(self.resp), self.fn, self.tam * 0.94, self.T["txt"], largura_max=self.w - self.px(96),
                                alinhamento="esquerda", entrelinha=1.28)
            self.resp_h = rf.img.height - 2 * rf.pad + self.px(84)

    def area(self, t):
        hb = self.px(132)
        topo = self.y - hb / 2 - ((self.resp_h + self.px(28)) if self.resp else 0)
        return (self.x - self.w / 2, topo, self.x + self.w / 2, self.y + hb / 2)

    def _mat(self, cor_bg):
        if self.tema == "vidro":
            return "vidro"
        return _mat_solido(cor_bg, self.T["borda"])

    def _barra(self, n, cursor_on, enviado_p):
        k = (n, cursor_on, round(enviado_p, 2))
        if k in self._cache:
            return self._cache[k]
        if len(self._cache) > 40:
            self._cache = {}
        T = self.T
        larg_txt = self.w - self.pad_l - self.pad_r
        vis = self.txt[:n]
        if vis:
            r = G.render_texto(vis + ("|" if cursor_on else " "), self.fn, self.tam, T["txt"], largura_max=larg_txt,
                               alinhamento="esquerda", entrelinha=1.22)
        else:
            r = G.render_texto(self.placeholder, self.fn, self.tam, T["ph"], largura_max=larg_txt, alinhamento="esquerda")
        th = r.img.height - 2 * r.pad
        h = max(self.px(132), th + self.px(64))
        raio = min(h / 2, self.px(66))
        c = G.cartao(self.w, h, raio, self.e, self._mat(T["bg"]), s=self.s,
                     sombra={"raio": 40, "dy": 18, "opacidade": 0.38 if self.tema != "claro" else 0.22})
        mais = G.icone("mais", self.px(42), T["ic"])
        c.colar(mais, self.px(38), h / 2, (0, 0.5))
        c.colar(r.img, self.pad_l - r.pad, h / 2 - th / 2 - r.pad)
        ativo = n > 0
        cb = T["env"] if ativo else T["env_off"]
        d_b = self.d_bot * (1 - 0.12 * math.sin(math.pi * clamp(enviado_p * 2)) if enviado_p < 0.5 else 1)
        bot = G.circulo(d_b, cb)
        seta = G.icone("enviar", d_b * 0.5, G.contraste_para(cb) if ativo else T["bg"][:3] + (255,))
        bot.paste(seta, (int((d_b - seta.width) / 2), int((d_b - seta.height) / 2)), seta)
        c.colar(bot, self.w - self.px(26) - self.d_bot / 2, h / 2, (0.5, 0.5))
        self._cache[k] = (c, h)
        return self._cache[k]

    def aplicar(self, img, t):
        a = self.anim(t)
        n = int(clamp((t - self.t_dig) * self.vel, 0, len(self.txt)))
        cursor_on = n < len(self.txt) or int(t * 2.2) % 2 == 0
        cursor_on = cursor_on and t < self.t_envio
        ep = clamp((t - self.t_envio) / 0.35)
        enviado = t >= self.t_envio and self.param("limpar_ao_enviar", bool(self.resp))
        n_vis = 0 if enviado else n
        c, h = self._barra(n_vis, cursor_on and not enviado, ep if t >= self.t_envio else 0)
        img = self.colar_cartao(img, c, self.x, self.y, a=a)
        xb = self.x + self.w / 2 - self.px(26) - self.d_bot / 2
        if 0 < ep < 1:
            r = self.d_bot / 2 + self.px(46) * entrada(ep)
            anel = G.circulo(r * 2, (0, 0, 0, 0), (255, 255, 255, int(150 * (1 - ep))), max(2, self.px(3)))
            img = G.colar(img, anel, xb + a["dx"], self.y + a["dy"], (0.5, 0.5), 1, 0, a["op"])
        if self.tem_cursor and t >= self.t_fim_dig - 0.5:
            p = suave(clamp((t - (self.t_fim_dig - 0.5)) / 0.7))
            cx = lerp(self.x + self.w * 0.12, xb + self.px(8), p)
            cy = lerp(self.y + self.px(270), self.y + self.px(16), p)
            cur = G.icone("cursor", self.px(92), (255, 255, 255, 255))
            cur = G.com_sombra(cur, self.px(8), 0, self.px(4), 0.4)
            esc = 0.86 if 0 < ep < 0.4 else 1.0
            img = G.colar(img, cur, cx, cy, (0.27, 0.12), esc, 0, a["op"])
        if self.resp and t >= self.t_envio + 0.2:
            img = self._resposta(img, t, a, h)
        return img

    def _resposta(self, img, t, a, h_barra):
        T = self.T
        t_r = self.t_envio + 0.2
        t_txt = t_r + num(self.param("tempo_pensando"), 0.55)
        vel = num(self.param("velocidade_resposta"), 48)
        txt = str(self.resp)
        n = int(clamp((t - t_txt) * vel, 0, len(txt)))
        larg = self.w - self.px(96)
        hh = self.resp_h
        k = ("r", n if t >= t_txt else -int(t * 30))
        if k not in self._cache:
            mat = "vidro" if self.tema == "vidro" else _mat_solido(T["resp"], self.T["borda"])
            card = G.cartao(self.w, hh, self.px(44), self.e, mat, s=self.s,
                            sombra={"raio": 36, "dy": 16, "opacidade": 0.32 if self.tema != "claro" else 0.2})
            if t < t_txt:
                card.colar(_pontos_pensando(t, T["ph"], self.s), self.px(48), hh / 2, (0, 0.5))
            else:
                r = G.render_texto(txt[:n] if n else " ", self.fn, self.tam * 0.94, T["txt"], largura_max=larg,
                                   alinhamento="esquerda", entrelinha=1.28)
                card.colar(r.img, self.px(48) - r.pad, self.px(42) - r.pad)
            self._cache = {kk: vv for kk, vv in self._cache.items() if not (isinstance(kk, tuple) and kk[0] == "r")}
            self._cache[k] = card
        card = self._cache[k]
        p = clamp((t - t_r) / 0.45)
        y = self.y - h_barra / 2 - self.px(28) - hh / 2
        return self.colar_cartao(img, card, self.x, y + self.px(34) * (1 - expo(p)),
                                 a=dict(a, op=a["op"] * clamp(p * 2), esc=a["esc"] * (0.97 + 0.03 * expo(p))))

    def sons_extra(self):
        s = [(self.t_dig + k / self.vel, "tecla", 0.16) for k in range(0, len(self.txt), 2)]
        s.append((self.t_envio, "click", 0.4))
        if self.resp:
            s.append((self.t_envio + 0.75, "pop", 0.22))
        return s


@registrar("checklist", "check_list", "lista_de_checagem", "tarefas", "lista_check", "checagem", "to_do", "todo")
class Checklist(Efeito):
    """Checklist com itens sendo marcados em sequência (✓ desenhado) num cartão de vidro. titulo (opcional),
    itens: textos ou {texto, em: tempo}, aparecer_um_a_um (false = todos visíveis desde o início), riscar (false),
    tamanho (46), largura (0.84), posicao (padrão 'centro'), cor_check (destaque), material."""
    entrada_padrao = "subir"
    duracao_padrao = 5.0
    som_entrada = "swish"
    vol_som = 0.15

    def preparar(self):
        e = self.e
        itens = self.param("itens") or []
        n = max(1, len(itens))
        ini = self.t0 + max(0.6, self.d_in + 0.2)
        passo = num(self.param("intervalo"), max(0.3, min(1.1, (self.dur - (ini - self.t0) - 0.8) / n)))
        self.itens = []
        for i, it in enumerate(itens):
            if isinstance(it, dict):
                txt = str(it.get("texto", ""))
                em = self.ctx.resolver_tempo(it["em"]) if it.get("em") is not None else ini + i * passo
            else:
                txt, em = str(it), ini + i * passo
            self.itens.append((txt, em))
        self.tam = self.px(num(self.param("tamanho"), 46))
        self.larg = self.W * num(self.param("largura"), 0.84)
        self.pad = self.px(60)
        self.box = self.tam * 1.3
        self.um_a_um = bool(self.param("aparecer_um_a_um", False))
        self.riscar = bool(self.param("riscar", False))
        self.cc = self.cor(self.param("cor_check", "destaque"))
        self.ct, self.cs = self.cores_cartao()
        larg_txt = self.larg - 2 * self.pad - self.box - self.px(30)
        self.rs = [G.render_texto(txt, e["fonte_forte"], self.tam, self.ct, largura_max=larg_txt,
                                  alinhamento="esquerda", cor_destaque=self.cor("destaque"),
                                  fonte_destaque=e["fonte_destaque"]) for txt, _ in self.itens]
        self.tit = G.render_texto(str(self.param("titulo")), e["fonte_titulo"], self.tam * 1.3, self.ct,
                                  largura_max=self.larg - 2 * self.pad, alinhamento="esquerda",
                                  cor_destaque=self.cor("destaque"), fonte_destaque=e["fonte_destaque"]) if self.param("titulo") else None
        self.gap = self.px(30)
        self.hs = [max(r.img.height - 2 * r.pad, self.box) for r in self.rs]
        alt = sum(self.hs) + self.gap * (len(self.hs) - 1) + 2 * self.pad
        if self.tit:
            alt += self.tit.img.height - 2 * self.tit.pad + self.gap * 1.4
        self.alt = alt
        self.card = self.cartao(self.larg, alt)
        self.x, self.y = self.pos(None, "centro")
        anel = (255, 255, 255, 120) if self.material().get("texto") != "escuro" else (0, 0, 0, 70)
        self.vazio = G.ret_arred(self.box, self.box, self.box * 0.3, (0, 0, 0, 0), anel, max(2, self.px(3.5)))
        self.cheio = G.ret_arred(self.box, self.box, self.box * 0.3, self.cc)

    def area(self, t):
        return self.caixa(self.x, self.y, self.larg, self.alt)

    def aplicar(self, img, t):
        a = self.anim(t)
        img = self.colar_cartao(img, self.card, self.x, self.y, a=a)
        x0 = self.x - self.larg / 2 + self.pad + a["dx"]
        y = self.y - self.alt / 2 + self.pad + a["dy"]
        if self.tit:
            img = G.colar(img, self.tit.img, x0 - self.tit.pad, y - self.tit.pad, (0, 0), 1, 0, a["op"])
            y += self.tit.img.height - 2 * self.tit.pad + self.gap * 1.4
        for i, ((txt, em), r, h) in enumerate(zip(self.itens, self.rs, self.hs)):
            vis = 1.0
            if self.um_a_um:
                vis = clamp((t - (em - 0.45)) / 0.3)
                if vis <= 0:
                    y += h + self.gap
                    continue
            p = clamp((t - em) / 0.3)
            op = a["op"] * vis
            cy = y + h / 2
            bx = x0 + self.box / 2
            if p <= 0:
                img = G.colar(img, self.vazio, bx, cy, (0.5, 0.5), 1, 0, op)
            else:
                esc = 0.7 + 0.3 * volta(p, 2.2)
                img = G.colar(img, self.vazio, bx, cy, (0.5, 0.5), 1, 0, op * (1 - p))
                img = G.colar(img, self.cheio, bx, cy, (0.5, 0.5), esc, 0, op)
                ck = G.icone("check", self.box * 0.78, G.contraste_para(self.cc), progresso=clamp((t - em - 0.05) / 0.25))
                img = G.colar(img, ck, bx, cy, (0.5, 0.5), esc, 0, op)
            op_t = op * (0.55 + 0.45 * p)
            tx = x0 + self.box + self.px(30)
            img = G.colar(img, r.img, tx - r.pad, cy, (0, 0.5), 1, 0, op_t)
            if self.riscar and p > 0:
                ln = r.linhas[0]
                x_ini = tx - r.pad + ln[0]
                larg_r = (ln[2] - ln[0]) * entrada(clamp((t - em - 0.2) / 0.3))
                if larg_r > 2:
                    risco = G.ret_arred(larg_r, max(3, self.px(4)), self.px(2), self.cs[:3] + (220,))
                    img = G.colar(img, risco, x_ini, cy, (0, 0.5), 1, 0, op)
            y += h + self.gap
        return img

    def sons_extra(self):
        return [(em, "pop", 0.3) for (_, em) in self.itens] + [(em + 0.08, "ding", 0.12) for (_, em) in self.itens]


@registrar("cupom", "cartao_de_desconto", "cartao_desconto", "desconto", "coupon", "voucher", "oferta", "promocao")
class Cupom(Efeito):
    """Cartão de desconto (ticket) com valor grande, código e brilho passando. valor ('50% OFF'), titulo
    ('CUPOM DE DESCONTO'), codigo ('PROMO10'), detalhe ('válido até domingo'), tema: 'destaque' (fundo na cor de
    acento) | 'escuro' | 'claro', posicao (centro), largura (0.78), preco_de / preco_por (opcional: mostra
    'de R$ 197 por R$ 97')."""
    entrada_padrao = "mola"
    duracao_padrao = 4.0
    som_entrada = "caixa"
    vol_som = 0.35

    def preparar(self):
        e = self.e
        tema = str(self.param("tema", "destaque"))
        if tema == "escuro":
            bg, ct, cv, cm = (22, 22, 24, 255), (255, 255, 255, 255), self.cor("destaque"), (185, 185, 192, 255)
        elif tema == "claro":
            bg, ct, cv, cm = (255, 255, 255, 255), (14, 14, 16, 255), (14, 14, 16, 255), (110, 110, 116, 255)
        else:
            bg = self.cor("destaque")
            ct = G.contraste_para(bg)
            cv, cm = ct, ct[:3] + (175,)
        W = self.W * num(self.param("largura"), 0.78)
        pad = self.px(58)
        partes = []
        tit = str(self.param("titulo", "CUPOM DE DESCONTO"))
        partes.append(G.render_texto(tit, e["fonte_rotulo"], self.px(28), cm if tema != "destaque" else ct,
                                     maiusculas=True, rastreio=self.px(5)))
        val = str(self.param("valor", "50% OFF"))
        fv = e.get("fonte_impacto", e["fonte_pesada"])
        tv = G.ajustar_tamanho(val, fv, self.px(num(self.param("tamanho"), 200)), W - 2 * pad,
                               minimo=self.px(50), linhas_max=1)
        partes.append(G.render_texto(val, fv, tv, cv, largura_max=W - 2 * pad, entrelinha=0.92))
        if self.param("preco_de") or self.param("preco_por"):
            s = ""
            if self.param("preco_de"):
                s += "de R$ %s " % self.param("preco_de")
            if self.param("preco_por"):
                s += "por *R$ %s*" % self.param("preco_por")
            partes.append(G.render_texto(s, e["fonte_forte"], self.px(40), ct, cor_destaque=cv))
        self.cab = partes
        gap = self.px(4)
        hcab = sum(p.img.height - 2 * p.pad for p in partes) + gap * (len(partes) - 1)
        cod = self.param("codigo")
        det = self.param("detalhe")
        rc = G.render_texto(str(cod), e["fonte_mono"], self.px(50), ct, rastreio=self.px(4)) if cod else None
        rd = G.render_texto(str(det), e["fonte_texto"], self.px(30), cm, largura_max=W - 2 * pad) if det else None
        hrod = ((rc.img.height - 2 * rc.pad) + self.px(36) if rc else 0) + ((rd.img.height - 2 * rd.pad) + self.px(18) if rd else 0)
        H = pad * 2 + hcab + (self.px(64) + hrod if (rc or rd) else 0)
        self.Wc, self.Hc = W, H
        card = G.ret_arred(W, H, self.px(30), bg, (255, 255, 255, 36) if tema == "escuro" else None,
                           max(1, self.px(2)) if tema == "escuro" else 0)
        y = pad
        for p in partes:
            G.compor(card, p.img, W / 2 - p.img.width / 2, y - p.pad)
            y += p.img.height - 2 * p.pad + gap
        if rc or rd:
            ys = y + self.px(26)
            rr = self.px(30)
            buraco = Image.new("L", card.size, 255)
            db = ImageDraw.Draw(buraco)
            db.ellipse([-rr, ys - rr, rr, ys + rr], fill=0)
            db.ellipse([W - rr, ys - rr, W + rr, ys + rr], fill=0)
            al = np.minimum(np.asarray(card.getchannel("A")), np.asarray(buraco))
            card.putalpha(Image.fromarray(al.astype(np.uint8), "L"))
            d = ImageDraw.Draw(card)
            x = rr + self.px(18)
            cor_l = ct[:3] + (110,)
            while x < W - rr - self.px(18):
                d.line([x, ys, x + self.px(16), ys], fill=cor_l, width=max(2, int(self.px(3))))
                x += self.px(28)
            y = ys + self.px(38)
            if rc:
                bw, bh = rc.img.width - 2 * rc.pad + self.px(64), rc.img.height - 2 * rc.pad + self.px(30)
                caixa = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
                dc = ImageDraw.Draw(caixa)
                dc.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=self.px(14), fill=ct[:3] + (24,))
                # contorno tracejado
                per = 2 * (bw + bh)
                k = 0.0
                passo = self.px(18)
                while k < per:
                    for (x1, y1, x2, y2) in self._segmentos_borda(bw, bh, k, min(k + passo * 0.55, per)):
                        dc.line([x1, y1, x2, y2], fill=ct[:3] + (150,), width=max(2, int(self.px(2.5))))
                    k += passo
                G.compor(card, caixa, W / 2 - bw / 2, y)
                G.compor(card, rc.img, W / 2 - rc.img.width / 2, y + bh / 2 - rc.img.height / 2)
                y += bh + self.px(18)
            if rd:
                G.compor(card, rd.img, W / 2 - rd.img.width / 2, y - rd.pad)
        self.card = card
        self.sombra, self.pad_sombra = G.so_sombra(card.getchannel("A"), self.px(44), 0, self.px(24), self.e["sombra"] + 0.08)
        self.x, self.y = self.pos(None, "centro")
        self.t_brilho = self.t0 + num(self.param("tempo_brilho"), 0.75)

    def area(self, t):
        return self.caixa(self.x, self.y, self.Wc, self.Hc, self.px(20))

    @staticmethod
    def _segmentos_borda(w, h, a, b):
        """Segmentos do perímetro de um retângulo w×h entre os comprimentos a e b."""
        lados = [((0, 0), (w, 0)), ((w, 0), (w, h)), ((w, h), (0, h)), ((0, h), (0, 0))]
        out = []
        pos = 0.0
        for (x1, y1), (x2, y2) in lados:
            L = math.hypot(x2 - x1, y2 - y1)
            s0, s1 = max(a, pos), min(b, pos + L)
            if s1 > s0:
                u0, u1 = (s0 - pos) / L, (s1 - pos) / L
                out.append((x1 + (x2 - x1) * u0, y1 + (y2 - y1) * u0, x1 + (x2 - x1) * u1, y1 + (y2 - y1) * u1))
            pos += L
        return out

    def aplicar(self, img, t):
        p = clamp((t - self.t0) / 0.7)
        po = easing("saida")(self.p_saida(t))
        esc = (0.4 + 0.6 * mola(p, 0.5, 2.0)) * (1 - 0.2 * po)
        rot = -8 * (1 - entrada(p)) + math.sin((t - self.t0) * 1.6) * 0.8
        op = clamp(p * 4) * (1 - po)
        bob = math.sin((t - self.t0) * 2.0) * self.px(5)
        card = self.card
        pb = clamp((t - self.t_brilho) / 0.7)
        if 0 < pb < 1:
            br = _brilho_diagonal(card.width, card.height, pb)
            alfa = card.getchannel("A")
            br_a = np.minimum(np.asarray(br.getchannel("A")), np.asarray(alfa))
            br.putalpha(Image.fromarray(br_a.astype(np.uint8), "L"))
            card = Image.alpha_composite(card, br)
        sp = self.sombra.copy()
        sp.alpha_composite(card, (self.pad_sombra, self.pad_sombra))
        return G.colar(img, sp, self.x, self.y + bob - self.px(110) * (1 - entrada(p)), (0.5, 0.5), esc, rot, op)

    def sons_extra(self):
        return [(self.t_brilho + 0.1, "ding", 0.18)]


def _avatar(d, letra, cor_bg, imagem=None, anel=None, s=1.0):
    """Avatar redondo (imagem ou inicial sobre gradiente), com anel opcional."""
    d = int(d)
    if imagem is not None:
        im = G.cobrir(imagem.convert("RGB"), d, d).convert("RGBA")
        av = G.cantos(im, d / 2)
    else:
        c1 = G.cor(cor_bg)
        c2 = G.misturar_cor(c1, (0, 0, 0, 255), 0.35)
        g = G.gradiente_linear(d, d, c1, c2, 60)
        av = G.cantos(g, d / 2)
        r = G.render_texto(letra.upper()[:1] or "@", "InterDisplay-Bold", d * 0.46, G.contraste_para(c1))
        G.compor(av, r.img, d / 2 - r.img.width / 2, d / 2 - r.img.height / 2)
    if anel is not None:
        e = max(2, int(4 * s))
        D = d + 4 * e
        base = G.circulo(D, (0, 0, 0, 0), anel, e)
        base.alpha_composite(av, (2 * e, 2 * e))
        return base
    return av


@registrar("cta", "cta_ilustrativo", "chamada", "call_to_action", "seguir", "comente", "comentar", "curtir",
           "link_na_bio", "inscreva_se", "salvar_video")
class CTA(Efeito):
    """Chamada para ação ilustrada (interface genérica, sem marca). modo: 'seguir' (cartão de perfil + botão Seguir
    clicado pelo cursor), 'comentar' (campo de comentário digitando a palavra-chave e o comentário publicado),
    'curtir' (coração que explode), 'salvar', 'compartilhar', 'link' ('link na bio' com seta), 'botao' (botão com
    clique), 'combo' (curtir, comentar, compartilhar, salvar em sequência). texto (frase acima, ex. 'Comenta
    *EU QUERO*'), usuario ('@seuperfil'), subtitulo, palavra (para 'comentar'), botao (texto do botão), avatar
    (imagem opcional), verificado (true: selo azul), posicao (padrão 'terco_inferior' / 'centro')."""
    entrada_padrao = "subir"
    duracao_padrao = 4.0
    som_entrada = "pop"
    vol_som = 0.3

    def preparar(self):
        nome = str(self.spec.get("tipo", ""))
        modo = self.param("modo")
        if not modo:
            mapa = {"seguir": "seguir", "comente": "comentar", "comentar": "comentar", "curtir": "curtir",
                    "link_na_bio": "link", "inscreva_se": "botao", "salvar_video": "salvar"}
            modo = mapa.get(nome, "seguir")
        self.modo = modo
        e = self.e
        self.usuario = str(self.param("usuario", "@seuperfil"))
        txt = self.param("texto")
        self.rt = G.render_texto(str(txt), e["fonte_titulo"], self.px(num(self.param("tamanho"), 66)), self.cor("texto"),
                                 largura_max=self.W * 0.86, cor_destaque=self.cor("destaque"),
                                 fonte_destaque=e["fonte_destaque"], marca_solida=bool(e.get("marca_solida", True)),
                                 sombra=self.sombra_texto()) if txt else None
        self.x, self.y = self.pos(None, "terco_inferior" if modo in ("seguir", "comentar", "botao", "link") else "centro")
        av = self.param("avatar")
        self.av_img = self.ctx.bib.imagem(av) if av else None
        self.t_click = self.t0 + num(self.param("tempo_clique"), 1.35)
        self.ct, self.cs = self.cores_cartao()
        self.azul = self.cor("ui_azul")
        self._cache = {}

    def area(self, t):
        rt = (self.rt.img.height - 2 * self.rt.pad + self.px(26)) if self.rt else 0
        m, y = self.modo, self.y
        if m == "seguir":
            y0, y1 = y - self.px(88) - rt, y + self.px(88)
        elif m == "comentar":
            y0, y1 = y - self.px(60) - self.px(196) - rt, y + self.px(60)
        elif m == "link":
            y0, y1 = y - self.px(62) - self.px(150) - rt, y + self.px(62)
        elif m == "botao":
            y0, y1 = y - self.px(68) - rt, y + self.px(110)
        elif m in ("curtir", "salvar", "compartilhar"):
            sz = self.px(num(self.param("tamanho_icone"), 250))
            y0, y1 = y - sz / 2, y + sz / 2 + self.px(30) + rt
        else:
            y0, y1 = y - self.px(110) - rt, y + self.px(140)
        return (self.W * 0.07, y0, self.W * 0.93, y1)

    # ---- desenhos
    def _cartao_seguir(self, seguindo):
        k = ("seg", seguindo)
        if k in self._cache:
            return self._cache[k]
        e = self.e
        w, h = self.W * 0.86, self.px(176)
        c = self.cartao(w, h, h / 2)
        av = _avatar(self.px(116), self.usuario.lstrip("@"), self.cor("destaque"), self.av_img, None, self.s)
        c.colar(av, self.px(30), h / 2, (0, 0.5))
        ru = G.render_texto(self.usuario, e.get("fonte_ui_forte", "Inter-SemiBold"), self.px(42), self.ct)
        xu = self.px(30) + av.width + self.px(24)
        c.colar(ru.img, xu - ru.pad, h / 2 - self.px(20) - ru.img.height / 2)
        if self.param("verificado", True):
            sel = G.circulo(self.px(34), self.azul)
            ck = G.icone("check", self.px(30), (255, 255, 255, 255))
            sel.alpha_composite(ck, (int(self.px(2)), int(self.px(2))))
            c.colar(sel, xu + ru.img.width - 2 * ru.pad + self.px(10), h / 2 - self.px(20), (0, 0.5))
        sub = self.param("subtitulo", "Conteúdo novo toda semana")
        rs = G.render_texto(str(sub), e.get("fonte_ui", "Inter-Medium"), self.px(30), self.cs)
        c.colar(rs.img, xu - rs.pad, h / 2 + self.px(24) - rs.img.height / 2)
        bw, bh = self.px(222), self.px(88)
        if seguindo:
            claro = self.material().get("texto") == "escuro"
            bt = G.ret_arred(bw, bh, bh / 2, (0, 0, 0, 16) if claro else (255, 255, 255, 40),
                             (0, 0, 0, 46) if claro else (255, 255, 255, 60), max(1, self.px(2)))
            rb = G.render_texto("Seguindo", e.get("fonte_ui_forte", "Inter-SemiBold"), self.px(34), self.ct)
        else:
            bt = G.ret_arred(bw, bh, bh / 2, self.azul)
            rb = G.render_texto(str(self.param("botao", "Seguir")), e.get("fonte_ui_forte", "Inter-SemiBold"), self.px(36),
                                (255, 255, 255, 255))
        G.compor(bt, rb.img, bw / 2 - rb.img.width / 2, bh / 2 - rb.img.height / 2)
        bx = w - bw - self.px(32)
        c.colar(bt, bx, h / 2, (0, 0.5))
        self._bot = (bx + bw / 2 - w / 2, 0)
        self._cache[k] = c
        return c

    def _cursor(self, img, t, alvo_x, alvo_y, a):
        t_in = self.t_click - 0.8
        if t < t_in:
            return img
        p = suave(clamp((t - t_in) / 0.7))
        cx = lerp(alvo_x + self.px(220), alvo_x, p)
        cy = lerp(alvo_y + self.px(300), alvo_y, p)
        esc = 0.84 if 0 <= t - self.t_click < 0.15 else 1.0
        if "cursor" not in self._cache:
            self._cache["cursor"] = G.com_sombra(G.icone("cursor", self.px(96), (255, 255, 255, 255)), self.px(8), 0,
                                                 self.px(4), 0.4)
        img = G.colar(img, self._cache["cursor"], cx, cy, (0.27, 0.12), esc, 0, a["op"])
        pc = clamp((t - self.t_click) / 0.45)
        if 0 < pc < 1:
            anel = G.circulo(self.px(60) + self.px(90) * entrada(pc), (0, 0, 0, 0), (255, 255, 255, int(190 * (1 - pc))),
                             max(2, self.px(3)))
            img = G.colar(img, anel, alvo_x, alvo_y, (0.5, 0.5), 1, 0, a["op"])
        return img

    def _particulas(self, img, t, cx, cy, t_ini, icone="coracao", n=9, cor_p=None):
        p = clamp((t - t_ini) / 0.9)
        if p <= 0 or p >= 1:
            return img
        cor_p = cor_p or self.cor("ui_vermelho")
        for k in range(n):
            ang = -math.pi / 2 + (k - (n - 1) / 2) * 0.32 + 0.15 * math.sin(k * 7.1)
            dist = self.px(90 + 140 * entrada(p) + 20 * (k % 3))
            sz = self.px(30 + 10 * (k % 3))
            ic = G.icone(icone, sz, cor_p)
            img = G.colar(img, ic, cx + math.cos(ang) * dist, cy + math.sin(ang) * dist - self.px(60) * p, (0.5, 0.5),
                          1 - 0.4 * p, (k - n / 2) * 6, 1 - p)
        return img

    def aplicar(self, img, t):
        a = self.anim(t)
        m = self.modo
        y_txt = None
        if m == "seguir":
            c = self._cartao_seguir(t >= self.t_click + 0.08)
            img = self.colar_cartao(img, c, self.x, self.y, a=a)
            bx = self.x + self._bot[0]
            img = self._cursor(img, t, bx, self.y + a["dy"], a)
            img = self._particulas(img, t, bx, self.y - self.px(40), self.t_click, "coracao", 7)
            y_txt = self.y - c.h / 2 - self.px(26)
        elif m == "comentar":
            img, y_txt = self._comentar(img, t, a)
        elif m in ("curtir", "salvar", "compartilhar"):
            ic = {"curtir": "coracao", "salvar": "marcador", "compartilhar": "aviao"}[m]
            cor_i = self.cor("ui_vermelho") if m == "curtir" else self.cor("texto")
            p = clamp((t - self.t0) / 0.6)
            sz = self.px(num(self.param("tamanho_icone"), 250))
            k = ("ic", m)
            if k not in self._cache:
                self._cache[k] = G.com_sombra(G.icone(ic, sz, cor_i), self.px(26), 0, self.px(12), 0.4)
            sp = self._cache[k]
            pulso = 1 + 0.06 * math.sin((t - self.t0) * 6) * (1 - clamp((t - self.t0 - 1.2) / 0.5))
            dx = 0
            if m == "compartilhar":
                q = clamp((t - self.t0 - 1.0) / 0.6)
                dx = self.px(700) * easing("saida")(q)
            img = G.colar(img, sp, self.x + dx + a["dx"], self.y + a["dy"], (0.5, 0.5), (0.35 + 0.65 * mola(p)) * pulso,
                          -20 * easing("saida")(clamp((t - self.t0 - 1.0) / 0.6)) if m == "compartilhar" else 0, a["op"])
            if m == "curtir":
                img = self._particulas(img, t, self.x, self.y, self.t0 + 0.25, "coracao", 11, cor_i)
            if self.rt:
                img = G.colar(img, self.rt.img, self.x + a["dx"], self.y + sz / 2 + self.px(30) + a["dy"], (0.5, 0), 1, 0,
                              a["op"] * clamp((t - self.t0 - 0.3) / 0.3))
                return img
        elif m == "link":
            k = "link"
            if k not in self._cache:
                cc = self.cor(self.param("cor_botao", "#FFFFFF"))
                ctx_ = G.contraste_para(cc)
                rl = G.render_texto(str(self.param("botao", "Link na bio")), self.e.get("fonte_ui_forte", "Inter-SemiBold"),
                                    self.px(48), ctx_)
                ic = G.icone("link", self.px(56), ctx_)
                w = rl.img.width - 2 * rl.pad + ic.width + self.px(120)
                h = self.px(124)
                chip = G.cartao(w, h, h / 2, self.e, _mat_solido(cc, 0.0), s=self.s, sombra={"opacidade": 0.35})
                chip.colar(ic, self.px(44), h / 2, (0, 0.5))
                chip.colar(rl.img, self.px(44) + ic.width + self.px(18) - rl.pad, h / 2, (0, 0.5))
                self._cache[k] = chip
            chip = self._cache[k]
            pulso = 1 + 0.035 * math.sin((t - self.t0) * 5)
            img = self.colar_cartao(img, chip, self.x, self.y, a=dict(a, esc=a["esc"] * pulso))
            direc = str(self.param("seta", "cima"))
            if ("seta", direc) not in self._cache:
                self._cache[("seta", direc)] = G.com_sombra(
                    G.icone("seta_cima" if direc == "cima" else "seta_baixo", self.px(104), self.cor("texto")),
                    self.px(12), 0, self.px(4), 0.45)
            seta = self._cache[("seta", direc)]
            bob = math.sin((t - self.t0) * 5) * self.px(14)
            sy = self.y - chip.h / 2 - self.px(84) + bob if direc == "cima" else self.y + chip.h / 2 + self.px(84) + bob
            img = G.colar(img, seta, self.x, sy, (0.5, 0.5), 1, 0, a["op"])
            y_txt = (sy - self.px(70)) if direc == "cima" else self.y - chip.h / 2 - self.px(24)
        elif m == "botao":
            k = "bot"
            if k not in self._cache:
                cb = self.cor(self.param("cor_botao", "destaque"))
                rb = G.render_texto(str(self.param("botao", "Quero agora")), self.e["fonte_titulo"], self.px(54),
                                    G.contraste_para(cb))
                w, h = max(self.px(480), rb.img.width - 2 * rb.pad + self.px(130)), self.px(136)
                b = G.ret_arred(w, h, h / 2, cb)
                b.alpha_composite(G.ret_arred(w, h, h / 2, (255, 255, 255, 0), (255, 255, 255, 90), max(1, self.px(2))))
                G.compor(b, rb.img, w / 2 - rb.img.width / 2, h / 2 - rb.img.height / 2)
                self._cache[k] = (G.com_sombra(b, self.px(30), 0, self.px(14), 0.4),
                                  G.brilho_externo(b, self.px(34), cb[:3], 0.55))
            b, glow = self._cache[k]
            pulso = 0.5 + 0.5 * math.sin((t - self.t0) * 4.5)
            img = G.colar(img, glow, self.x + a["dx"], self.y + a["dy"], (0.5, 0.5), a["esc"], 0, a["op"] * pulso * 0.8)
            esc_b = 0.93 if 0 <= t - self.t_click < 0.15 else 1.0
            img = G.colar(img, b, self.x + a["dx"], self.y + a["dy"], (0.5, 0.5), a["esc"] * esc_b, 0, a["op"])
            img = self._cursor(img, t, self.x + self.px(90), self.y + a["dy"] + self.px(10), a)
            y_txt = self.y - self.px(68) - self.px(26)
        else:  # combo
            icones = [("coracao", "Curte"), ("balao", "Comenta"), ("aviao", "Compartilha"), ("marcador", "Salva")]
            n = len(icones)
            esp = self.W * 0.21
            for k, (ic, rot) in enumerate(icones):
                tk = self.t0 + 0.25 + k * 0.35
                p = clamp((t - tk) / 0.45)
                if p <= 0:
                    continue
                cx = self.x + (k - (n - 1) / 2) * esp
                cor_i = self.cor("ui_vermelho") if ic == "coracao" else self.cor("texto")
                kk = ("combo", ic)
                if kk not in self._cache:
                    self._cache[kk] = G.com_sombra(G.icone(ic, self.px(116), cor_i), self.px(14), 0, self.px(5), 0.45)
                img = G.colar(img, self._cache[kk], cx, self.y + a["dy"], (0.5, 0.5), 0.4 + 0.6 * volta(p, 2.2), 0, a["op"])
                rr = self._cache.get(("rot", rot))
                if rr is None:
                    rr = G.render_texto(rot, self.e["fonte_forte"], self.px(32), self.cor("texto"),
                                        sombra=self.sombra_texto(0.8)).img
                    self._cache[("rot", rot)] = rr
                img = G.colar(img, rr, cx, self.y + self.px(92) + a["dy"], (0.5, 0), 1, 0, a["op"] * p)
            y_txt = self.y - self.px(110)
        if self.rt and y_txt is not None:
            img = G.colar(img, self.rt.img, self.x + a["dx"], y_txt + a["dy"], (0.5, 1), a["esc"], 0, a["op"])
        return img

    def _comentar(self, img, t, a):
        e = self.e
        palavra = str(self.param("palavra", "EU QUERO"))
        w = self.W * 0.86
        t_dig = self.t0 + 0.55
        vel = 12.0
        n = int(clamp((t - t_dig) * vel, 0, len(palavra)))
        t_env = t_dig + len(palavra) / vel + 0.35
        enviado = t >= t_env
        k = ("campo", 0 if enviado else n)
        if k not in self._cache:
            h = self.px(120)
            c = self.cartao(w, h, h / 2)
            av = _avatar(self.px(76), "v", "#8E8E93", None)
            c.colar(av, self.px(22), h / 2, (0, 0.5))
            vis = "" if enviado else palavra[:n]
            rt = G.render_texto(vis + ("|" if not enviado and n < len(palavra) else "") if vis else "Adicione um comentário…",
                                e.get("fonte_ui", "Inter-Medium"), self.px(38), self.ct if vis else self.cs)
            c.colar(rt.img, self.px(122) - rt.pad, h / 2, (0, 0.5))
            ce = self.azul if (n > 0 and not enviado) else self.cs
            re_ = G.render_texto("Publicar", e.get("fonte_ui_forte", "Inter-SemiBold"), self.px(34), ce)
            c.colar(re_.img, w - self.px(30) + re_.pad, h / 2, (1, 0.5))
            self._cache = {kk: vv for kk, vv in self._cache.items() if not (isinstance(kk, tuple) and kk[0] == "campo")}
            self._cache[k] = c
        campo = self._cache[k]
        img = self.colar_cartao(img, campo, self.x, self.y, a=a)
        y_top = self.y - campo.h / 2
        if enviado:
            p = clamp((t - t_env) / 0.45)
            kb = ("bolha",)
            if kb not in self._cache:
                ru = G.render_texto(self.usuario, e.get("fonte_ui_forte", "Inter-SemiBold"), self.px(30), self.cs)
                rp = G.render_texto(palavra, e["fonte_titulo"], self.px(50), self.ct)
                bw = max(ru.img.width - 2 * ru.pad, rp.img.width - 2 * rp.pad) + self.px(210)
                bh = (ru.img.height - 2 * ru.pad) + (rp.img.height - 2 * rp.pad) + self.px(56)
                b = self.cartao(bw, bh, self.px(38))
                av = _avatar(self.px(80), self.usuario.lstrip("@"), self.cor("destaque"), self.av_img)
                b.colar(av, self.px(24), bh / 2, (0, 0.5))
                b.colar(ru.img, self.px(126) - ru.pad, self.px(22) - ru.pad)
                b.colar(rp.img, self.px(126) - rp.pad, self.px(22) + ru.img.height - 2 * ru.pad + self.px(6) - rp.pad)
                co = G.icone("coracao", self.px(40), self.cor("ui_vermelho"))
                b.colar(co, bw - self.px(36), bh / 2, (1, 0.5))
                self._cache[kb] = b
            b = self._cache[kb]
            yb = y_top - self.px(26) - b.h / 2
            img = self.colar_cartao(img, b, self.x - w / 2 + b.w / 2, yb + self.px(40) * (1 - expo(p)),
                                    a=dict(a, op=a["op"] * clamp(p * 2), esc=a["esc"] * (0.92 + 0.08 * volta(p))))
            y_top = yb - b.h / 2
        return img, y_top - self.px(14)

    def sons_extra(self):
        out = []
        if self.modo in ("seguir", "botao"):
            out.append((self.t_click, "click", 0.45))
            out.append((self.t_click + 0.05, "pop", 0.3))
        if self.modo == "comentar":
            palavra = str(self.param("palavra", "EU QUERO"))
            t_dig = self.t0 + 0.55
            out += [(t_dig + k / 12.0, "tecla", 0.15) for k in range(len(palavra))]
            out.append((t_dig + len(palavra) / 12.0 + 0.35, "pop", 0.35))
        if self.modo == "combo":
            out += [(self.t0 + 0.25 + k * 0.35, "pop", 0.25) for k in range(4)]
        if self.modo == "compartilhar":
            out.append((self.t0 + 1.0, "whoosh", 0.3))
        return out


@registrar("notificacao", "notification", "alerta", "push", "banner_notificacao")
class Notificacao(Efeito):
    """Banner de notificação (estilo celular, vidro fosco) que desce do topo. app (nome), titulo, texto, icone
    ('sino', 'dinheiro', 'balao', 'carrinho'...), cor_icone (padrão destaque), tempo ('agora'), tema 'escuro' |
    'claro'."""
    entrada_padrao = "descer"
    duracao_padrao = 3.2
    som_entrada = "notificacao"
    vol_som = 0.4

    def preparar(self):
        e = self.e
        claro = str(self.param("tema", "escuro")) == "claro"
        mat = "vidro_claro" if claro else "vidro"
        self.mat = mat
        ct, cm = G.cores_material(G.material(e, mat), e)
        w = self.W * 0.92
        pad = self.px(32)
        ics = self.px(88)
        ci = self.cor(self.param("cor_icone", "destaque"))
        ic = G.ret_arred(ics, ics, ics * 0.26, gradiente=(G.misturar_cor(ci, (255, 255, 255, 255), 0.18),
                                                          G.misturar_cor(ci, (0, 0, 0, 255), 0.16), 90))
        gl = G.icone(self.param("icone", "sino"), ics * 0.54, G.contraste_para(ci))
        ic.alpha_composite(gl, (int((ics - gl.width) / 2), int((ics - gl.height) / 2)))
        fui = e.get("fonte_ui", "Inter-Medium")
        fuf = e.get("fonte_ui_forte", "Inter-SemiBold")
        titulo = self.param("titulo") or self.param("app", "Mensagens")
        larg_txt = w - ics - 3 * pad - self.px(90)
        rti = G.render_texto(str(titulo), fuf, self.px(35), ct, largura_max=larg_txt, alinhamento="esquerda")
        rtm = G.render_texto(str(self.param("tempo", "agora")), fui, self.px(27), cm)
        rtx = G.render_texto(str(self.param("texto", "")), fui, self.px(33), ct[:3] + (225,), largura_max=w - ics - 3 * pad,
                             alinhamento="esquerda", entrelinha=1.18)
        app = self.param("app") if self.param("titulo") else None
        rap = G.render_texto(str(app).upper(), e.get("fonte_rotulo", "Inter-Bold"), self.px(22), cm,
                             rastreio=self.px(2)) if app else None
        h_txt = (rap.img.height - 2 * rap.pad + self.px(8) if rap else 0) + (rti.img.height - 2 * rti.pad) + self.px(6) + \
            (rtx.img.height - 2 * rtx.pad)
        h = max(h_txt, ics) + 2 * pad
        c = G.cartao(w, h, self.px(44), e, mat, s=self.s, sombra={"raio": 40, "dy": 18, "opacidade": 0.3})
        c.colar(ic, pad, pad)
        x = pad * 2 + ics
        y = pad
        if rap:
            c.colar(rap.img, x - rap.pad, y - rap.pad)
            y += rap.img.height - 2 * rap.pad + self.px(8)
        c.colar(rti.img, x - rti.pad, y - rti.pad)
        c.colar(rtm.img, w - pad + rtm.pad, pad - rtm.pad, (1, 0))
        y += rti.img.height - 2 * rti.pad + self.px(6)
        c.colar(rtx.img, x - rtx.pad, y - rtx.pad)
        self.card = c
        self.x, self.y = self.pos(None, "topo")
        if self.spec.get("posicao") is None:
            self.y = self.px(118) + h / 2

    def area(self, t):
        return self.caixa(self.x, self.y, self.card.w, self.card.h, self.px(10))

    def aplicar(self, img, t):
        p = clamp((t - self.t0) / 0.6)
        po = easing("saida")(self.p_saida(t))
        dy = -self.px(260) * (1 - mola(p, 0.6, 1.5)) - self.px(300) * po
        esc = 0.96 + 0.04 * expo(p)
        return G.colar_cartao(img, self.card, self.x, self.y + dy, (0.5, 0.5), esc, 0, clamp(p * 3) * (1 - po))


def _bolha(w, h, r, r_cauda, lado, c, s=1.0):
    """Bolha de mensagem: cantos arredondados, com o canto de baixo do lado do remetente mais fechado."""
    w, h = max(2, int(round(w))), max(2, int(round(h)))
    a = np.asarray(G.mascara_ret(w, h, r), np.uint8).copy()
    pequeno = np.asarray(G.mascara_ret(w, h, r_cauda), np.uint8)
    if lado == "dir":
        a[h // 2:, w // 2:] = pequeno[h // 2:, w // 2:]
    else:
        a[h // 2:, :w // 2] = pequeno[h // 2:, :w // 2]
    im = Image.new("RGBA", (w, h), tuple(c[:3]) + (0,))
    k = (c[3] if len(c) > 3 else 255) / 255.0
    im.putalpha(Image.fromarray((a.astype(np.float32) * k).astype(np.uint8), "L"))
    return im


@registrar("mensagens", "conversa", "chat", "bolhas", "dialogo", "whats", "mensagem")
class Mensagens(Efeito):
    """Conversa em bolhas (estilo app de mensagens, sem marca) aparecendo uma a uma, com 'digitando...'.
    mensagens: [{de: 'eu'|'outro', texto, em?}], posicao (centro), largura (0.86), tamanho (40)."""
    entrada_padrao = "fade"
    duracao_padrao = 6.0
    som_entrada = None

    def preparar(self):
        e = self.e
        msgs = self.param("mensagens", self.param("itens")) or []
        self.tam = self.px(num(self.param("tamanho"), 40))
        self.larg = self.W * num(self.param("largura"), 0.86)
        n = max(1, len(msgs))
        passo = max(0.5, (self.dur - 1.0) / n)
        self.msgs = []
        t = self.t0 + 0.4
        fui = e.get("fonte_ui", "Inter-Medium")
        for i, m in enumerate(msgs):
            if isinstance(m, str):
                m = {"de": "outro" if i % 2 == 0 else "eu", "texto": m}
            de = str(m.get("de", "outro"))
            em = self.ctx.resolver_tempo(m["em"]) if m.get("em") is not None else t + (0.7 if de != "eu" else 0)
            eu = de in ("eu", "me", "direita", "voce")
            cb = self.cor("ui_bolha_eu") if eu else self.cor("ui_bolha_outro")
            ct = (255, 255, 255, 255) if G.luminancia(cb) < 0.6 else (14, 14, 16, 255)
            r = G.render_texto(str(m.get("texto", "")), fui, self.tam, ct, largura_max=self.larg * 0.72,
                               alinhamento="esquerda", entrelinha=1.2)
            pad_x, pad_y = self.px(34), self.px(22)
            bw, bh = r.img.width - 2 * r.pad + 2 * pad_x, r.img.height - 2 * r.pad + 2 * pad_y
            b = _bolha(bw, bh, min(bh / 2, self.px(40)), self.px(10), "dir" if eu else "esq", cb, self.s)
            G.compor(b, r.img, pad_x - r.pad, pad_y - r.pad)
            self.msgs.append({"eu": eu, "em": em, "img": G.com_sombra(b, self.px(20), 0, self.px(8), 0.28),
                              "h": bh, "w": bw, "digitando": not eu})
            t = em + passo
        self.x, self.y = self.pos(None, "centro")
        self.gap = self.px(14)

    def area(self, t):
        alt = sum(m["h"] for m in self.msgs) + self.gap * max(0, len(self.msgs) - 1) + self.px(98)
        return self.caixa(self.x, self.y, self.larg, alt)

    def aplicar(self, img, t):
        a = self.anim(t)
        vis = [m for m in self.msgs if m["em"] <= t]
        prox = next((m for m in self.msgs if m["em"] > t), None)
        alt = sum(m["h"] for m in vis) + self.gap * max(0, len(vis) - 1)
        digitando = prox is not None and prox["digitando"] and prox["em"] - t < 0.8
        if digitando:
            alt += self.px(84) + self.gap
        y = self.y + alt / 2
        x_esq = self.x - self.larg / 2
        x_dir = self.x + self.larg / 2
        if digitando:
            hb = self.px(84)
            b = _bolha(self.px(150), hb, hb / 2, self.px(10), "esq", self.cor("ui_bolha_outro"), self.s)
            pts = _pontos_pensando(t, (200, 200, 206, 255), self.s)
            b.alpha_composite(pts, (int(self.px(150) / 2 - pts.width / 2), int(hb / 2 - pts.height / 2)))
            img = G.colar(img, b, x_esq, y, (0, 1), 1, 0, a["op"])
            y -= hb + self.gap
        for m in reversed(vis):
            p = clamp((t - m["em"]) / 0.35)
            q = volta(p, 1.6)
            x = x_dir if m["eu"] else x_esq
            anc = (1, 1) if m["eu"] else (0, 1)
            pad = (m["img"].width - m["w"]) / 2
            img = G.colar(img, m["img"], x + (pad if m["eu"] else -pad), y + pad, anc, 0.86 + 0.14 * q, 0, clamp(p * 2) * a["op"])
            y -= m["h"] + self.gap
        return img

    def sons_extra(self):
        return [(m["em"], "pop", 0.3) for m in self.msgs]


@registrar("barra_progresso", "progresso", "progress_bar", "barra_de_progresso")
class BarraProgresso(Efeito):
    """Barra fina mostrando o progresso do vídeo. posicao 'topo' | 'baixo', cor (destaque), espessura (8)."""
    fase = "final"
    duracao_padrao = 1e6

    def preparar(self):
        if self.spec.get("inicio") is None:
            self.t0 = 0.0
        if self.spec.get("fim") is None and self.spec.get("duracao") is None:
            self.t1 = self.ctx.duracao + 1
        self.esp = max(3, int(self.px(num(self.param("espessura"), 8))))
        self.topo = str(self.param("posicao", "topo")) != "baixo"

    def aplicar(self, img, t):
        d = ImageDraw.Draw(img)
        tot = min(self.t1, self.ctx.duracao) - self.t0
        p = clamp((t - self.t0) / max(1e-6, tot))
        y = 0 if self.topo else self.H - self.esp
        trilho = Image.new("RGBA", (self.W, self.esp), (255, 255, 255, 46))
        img.paste(trilho, (0, y), trilho)
        d.rectangle([0, y, int(self.W * p), y + self.esp], fill=self.cor(self.param("cor", "destaque"))[:3])
        return img
