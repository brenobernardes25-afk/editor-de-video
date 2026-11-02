"""Gera mídias sintéticas de teste e um plano que exercita todos os efeitos (autoteste do motor)."""
import json
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from . import grafico as G
from .audio import SR, salvar_wav
from .util import ffmpeg_bin, log


def _fala_sintetica(dur, semente=3):
    rng = np.random.default_rng(semente)
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    t = 0.3
    frases = []
    while t < dur - 1:
        d = rng.uniform(1.4, 3.6)
        d = min(d, dur - t - 0.2)
        i0, i1 = int(t * SR), int((t + d) * SR)
        tt = np.arange(i1 - i0) / SR
        f0 = rng.uniform(120, 170) * (1 + 0.06 * np.sin(2 * np.pi * 0.7 * tt))
        fase = 2 * np.pi * np.cumsum(f0) / SR
        voz = sum(np.sin(k * fase) / k for k in range(1, 9))
        silabas = np.clip(np.sin(2 * np.pi * rng.uniform(3.5, 5.5) * tt + rng.uniform(0, 6)), 0, 1) ** 0.6
        env = silabas * np.clip(tt / 0.05, 0, 1) * np.clip((d - tt) / 0.08, 0, 1)
        out[i0:i1] += (voz * 0.18 + rng.normal(0, 0.02, len(tt))) * env
        frases.append((round(t, 2), round(t + d, 2)))
        t += d + rng.uniform(0.35, 1.3)
    out += rng.normal(0, 0.002, n)
    return np.stack([out, out], 1), frases


def _musica_sintetica(dur=16.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    acordes = [(220.0, 277.18, 329.63), (196.0, 246.94, 293.66), (174.61, 220.0, 261.63), (196.0, 246.94, 329.63)]
    s = np.zeros(n)
    seg = dur / 4
    for k, ac in enumerate(acordes):
        m = (t >= k * seg) & (t < (k + 1) * seg)
        for f in ac:
            s[m] += 0.08 * np.sin(2 * np.pi * f * t[m]) + 0.03 * np.sin(2 * np.pi * 2 * f * t[m])
    bpm = 100
    for b in np.arange(0, dur, 60 / bpm):
        i = int(b * SR)
        L = min(int(0.25 * SR), n - i)
        tt = np.arange(L) / SR
        s[i:i + L] += 0.35 * np.sin(2 * np.pi * (50 + 60 * np.exp(-tt / 0.03)) * tt) * np.exp(-tt / 0.12)
    s = np.tanh(s * 1.2) * 0.6
    return np.stack([s, s], 1).astype(np.float32)


def _grao(h, w, forca, semente):
    return np.random.default_rng(semente).normal(0, 255 * forca, (h, w, 1)).astype(np.float32)


def _camada_bokeh(w, h, n, cores, semente, r=(30, 100), alto=0.8, borrar=24, forca=(0.25, 0.7)):
    """Luzes desfocadas (bokeh) em RGB escuro, para somar com 'screen'."""
    from PIL import ImageFilter
    rng = np.random.default_rng(semente)
    cam = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(cam)
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h * alto)
        rr = rng.uniform(*r)
        c = cores[int(rng.integers(0, len(cores)))]
        k = rng.uniform(*forca)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=tuple(int(v * k) for v in c))
    return cam.filter(ImageFilter.GaussianBlur(borrar))


def _silhueta(w, h, cx, cy, escala=1.0):
    """Máscara L de uma pessoa (cabeça, pescoço e ombros), suavizada."""
    from PIL import ImageFilter
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    hw = w * 0.17 * escala
    d.ellipse([cx - hw, cy - hw * 1.24, cx + hw, cy + hw * 1.2], fill=255)
    d.rectangle([cx - hw * 0.46, cy + hw * 0.9, cx + hw * 0.46, cy + hw * 1.75], fill=255)
    d.ellipse([cx - w * 0.47 * escala, cy + hw * 1.5, cx + w * 0.47 * escala, cy + hw * 1.5 + h * 0.66], fill=255)
    return m.filter(ImageFilter.GaussianBlur(max(1.5, w / 540)))


class CenaEstudio:
    """Quadros de um 'apresentador' estilizado num estúdio neutro: parede grafite com luz lateral, luzes desfocadas
    ao fundo, fita de LED fria, silhueta com luz de recorte. Gera bem em qualquer proporção."""

    def __init__(self, w=1080, h=1920):
        from PIL import ImageChops
        self.w, self.h = w, h
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        u, v = xs / w, ys / h
        k = max(w, h)
        luz = np.exp(-(((xs - w * 0.12) / (k * 0.55)) ** 2 + ((ys - h * 0.32) / (k * 0.55)) ** 2))
        base = np.stack([20 + 30 * luz, 22 + 31 * luz, 26 + 33 * luz], -1) * (1.05 - 0.35 * v[..., None])
        fita = np.exp(-((xs - w * 0.84) / (w * 0.035)) ** 2) * np.clip(1.2 - v * 1.1, 0, 1)
        base += fita[..., None] * np.array([60, 95, 150], np.float32)
        parede = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
        bok = _camada_bokeh(w, h, 22, [(255, 178, 104), (255, 214, 160), (170, 196, 255), (80, 200, 210)], 5,
                            r=(w * 0.025, w * 0.085), alto=0.72, borrar=int(w * 0.024))
        self.fundo = ImageChops.screen(parede, bok)
        self.vinheta = (1 - 0.55 * np.clip(np.sqrt(((u - 0.5) * 1.2) ** 2 + ((v - 0.45) * 0.9) ** 2) - 0.25, 0, 1) ** 1.3)[..., None]
        self.grao = [_grao(h, w, 0.012, 3)]  # grão fixo: textura sem pesar no arquivo
        # roupa: gradiente frio escuro; corpo recebe luz da esquerda
        g = np.stack([30 + 26 * (1 - u), 33 + 26 * (1 - u), 40 + 28 * (1 - u)], -1) * (1.0 - 0.45 * v[..., None])
        self.corpo = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8), "RGB")
        self.rim = Image.new("RGB", (w, h), (190, 210, 255))

    def quadro(self, t):
        from PIL import ImageFilter
        w, h = self.w, self.h
        cx = w * 0.5 + math.sin(t * 0.55) * w * 0.012
        cy = h * 0.4 + math.sin(t * 1.25) * h * 0.002
        m = _silhueta(w, h, cx, cy)
        im = self.fundo.copy()
        # volume: luz principal vinda da esquerda/frente (cabeça e ombro esquerdo mais claros)
        hw = w * 0.17
        k = max(w, h)
        if not hasattr(self, "_ys"):
            self._ys, self._xs = np.mgrid[0:h, 0:w].astype(np.float32)
        luz = np.exp(-(((self._xs - (cx - hw * 0.55)) / (hw * 1.5)) ** 2 + ((self._ys - (cy - hw * 0.15)) / (hw * 1.7)) ** 2))
        luz += 0.5 * np.exp(-(((self._xs - (cx - w * 0.28)) / (w * 0.22)) ** 2 + ((self._ys - (cy + hw * 2.6)) / (h * 0.12)) ** 2))
        corpo = np.asarray(self.corpo, np.float32) + luz[..., None] * np.array([34, 33, 36], np.float32)
        im.paste(Image.fromarray(np.clip(corpo, 0, 255).astype(np.uint8), "RGB"), (0, 0), m)
        # luz de recorte fria no lado direito (borda da máscara deslocada, suave)
        m2 = Image.new("L", (w, h), 0)
        m2.paste(m, (-int(w * 0.016), int(w * 0.004)))
        rim = np.clip(np.asarray(m, np.int16) - np.asarray(m2, np.int16), 0, 255).astype(np.float32) * 0.85
        rim = Image.fromarray(rim.astype(np.uint8)).filter(ImageFilter.GaussianBlur(w / 260))
        im.paste(self.rim, (0, 0), rim)
        arr = np.asarray(im, np.float32) * self.vinheta + self.grao[0]
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _escrever_video(dest, quadros, n, w, h, fps=30, wav=None, crf=20):
    cmd = [ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (w, h), "-r", str(fps),
           "-i", "-"]
    if wav:
        cmd += ["-i", wav, "-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", dest]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for k in range(n):
        p.stdin.write(quadros(k / fps).tobytes())
    p.stdin.close()
    p.wait()


def gerar_video_teste(dest, dur=90.0, w=1280, h=720, fps=30):
    """Vídeo de teste com 'fala' sintética (para o autoteste de cortes/legendas) e cena de estúdio."""
    wav = dest + ".wav"
    audio, frases = _fala_sintetica(dur)
    salvar_wav(wav, audio)
    cena = CenaEstudio(w, h)
    f = G.fonte("JetBrainsMono-Medium", max(14, h // 32))

    def q(t):
        im = cena.quadro(t)
        ImageDraw.Draw(im).text((24, 18), "TESTE %05.2fs" % t, font=f, fill=(255, 255, 255))
        return im
    _escrever_video(dest, q, int(dur * fps), w, h, fps, wav, crf=23)
    os.remove(wav)
    return frases


def gerar_estudio(dest, dur=12.0, w=1080, h=1920, fps=30):
    """Vídeo vertical do 'apresentador' (sem áudio útil) para catálogos e testes visuais."""
    cena = CenaEstudio(w, h)
    _escrever_video(dest, cena.quadro, int(dur * fps), w, h, fps, crf=19)


def gerar_broll(dest, dur=8.0, w=1080, h=1920, fps=30, tipo="luzes"):
    """B-roll sintético bonito: 'luzes' (cidade à noite desfocada, panorâmica lenta) ou 'ondas' (luz fluida)."""
    from PIL import ImageChops
    if tipo == "ondas":
        lw, lh = w // 10, h // 10
        ys, xs = np.mgrid[0:lh, 0:lw].astype(np.float32)
        xs /= lw
        ys /= lh
        c_fundo = np.array([6, 10, 26], np.float32)
        c1 = np.array([24, 90, 210], np.float32)
        c2 = np.array([40, 205, 230], np.float32)
        c3 = np.array([255, 170, 96], np.float32)
        graos = [_grao(h, w, 0.01, 4)]

        def q(t):
            a = np.sin(xs * 3.1 + ys * 1.7 + t * 0.55) * 0.5 + 0.5
            b = np.sin(xs * -2.3 + ys * 3.6 - t * 0.42 + 1.3) * 0.5 + 0.5
            c = np.sin((xs - 0.5) * 5.0 * np.cos(t * 0.2) + (ys - 0.6) * 4.0 + t * 0.3) * 0.5 + 0.5
            onda = np.clip(1 - np.abs(ys - (0.55 + 0.12 * np.sin(xs * 4 + t * 0.6))) * 3.2, 0, 1) ** 2
            arr = c_fundo + c1 * (a * 0.55)[..., None] + c2 * (b * a * 0.45)[..., None] + c3 * (onda * c * 0.55)[..., None]
            im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").resize((w, h), Image.BICUBIC)
            return Image.fromarray(np.clip(np.asarray(im, np.float32) + graos[0], 0, 255).astype(np.uint8))
    else:
        W2, H2 = int(w * 1.5), int(h * 1.25)
        fundo = G.gradiente_linear(W2, H2, (8, 10, 20), (20, 16, 24), 90).convert("RGB")
        quentes = [(255, 176, 92), (255, 208, 140), (255, 130, 80), (255, 236, 200)]
        frias = [(120, 170, 255), (90, 210, 255), (210, 220, 255)]
        longe = _camada_bokeh(W2, H2, 90, quentes + frias, 11, r=(w * 0.008, w * 0.03), alto=1.0, borrar=int(w * 0.01),
                              forca=(0.35, 0.9))
        perto = _camada_bokeh(W2, H2, 26, quentes + frias, 12, r=(w * 0.05, w * 0.12), alto=1.0, borrar=int(w * 0.045),
                              forca=(0.25, 0.6))
        graos = [_grao(h, w, 0.01, 5)]

        def q(t):
            p = t / max(1e-6, dur)
            x1 = int((W2 - w) * (0.15 + 0.5 * p))
            x2 = int((W2 - w) * (0.05 + 0.85 * p))
            y = int((H2 - h) * 0.5)
            im = ImageChops.screen(fundo.crop((x1, y, x1 + w, y + h)), longe.crop((x1, y, x1 + w, y + h)))
            im = ImageChops.screen(im, perto.crop((x2, y, x2 + w, y + h)))
            return Image.fromarray(np.clip(np.asarray(im, np.float32) + graos[0], 0, 255).astype(np.uint8))
    _escrever_video(dest, q, int(dur * fps), w, h, fps, crf=22)


def gerar_print(dest, w=1080, h=1350, foto=None):
    """Print genérico de notícia (veículo fictício) para testar 'papel' e 'diminui_explica'."""
    im = Image.new("RGB", (w, h), (252, 252, 250))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, 112], fill=(14, 14, 16))
    d.text((44, 56), "PORTAL EXEMPLO", font=G.fonte("InterDisplay-Black", 40), fill=(255, 255, 255), anchor="lm")
    d.text((w - 44, 56), "TECNOLOGIA", font=G.fonte("Inter-SemiBold", 24), fill=(255, 214, 10), anchor="rm")
    r = G.render_texto("Criadores trocam horas de edição por IA e postam todo dia", "Lora-Bold", 60, (16, 16, 18, 255),
                       largura_max=w - 88, alinhamento="esquerda", entrelinha=1.12)
    im.paste(r.img, (44 - r.pad, 150 - r.pad), r.img)
    y = 150 + r.img.height - 2 * r.pad + 24
    r2 = G.render_texto("Ferramentas fazem cortes, legendas e efeitos a partir do vídeo bruto.", "Inter-Medium", 32,
                        (96, 96, 102, 255), largura_max=w - 88, alinhamento="esquerda", entrelinha=1.3)
    im.paste(r2.img, (44 - r2.pad, y - r2.pad), r2.img)
    y += r2.img.height - 2 * r2.pad + 34
    fh = 470
    if foto is not None:
        im.paste(G.cobrir(foto.convert("RGB"), w - 88, fh), (44, y))
    else:
        im.paste(G.gradiente_linear(w - 88, fh, (30, 60, 120), (12, 14, 24), 70).convert("RGB"), (44, y))
    d.text((44, y + fh + 14), "Foto: Divulgação", font=G.fonte("Inter-Medium", 22), fill=(140, 140, 146))
    y += fh + 64
    for k in range(9):
        if y + 22 > h - 30:
            break
        d.rounded_rectangle([44, y, w - 44 - (k % 3 == 2) * 260, y + 18], radius=9, fill=(224, 224, 228))
        y += 40
    im.save(dest)


def gerar_logo(dest, s=400):
    """Logo genérico monocromático (monograma)."""
    im = G.circulo(s, (12, 12, 14, 255))
    im = G.borda_em(im, s / 2, (255, 255, 255, 40), max(2, s // 80))
    r = G.render_texto("A", "InterDisplay-Black", s * 0.56, (255, 255, 255, 255))
    G.compor(im, r.img, s / 2 - r.img.width / 2, s / 2 - r.img.height / 2 + s * 0.01)
    im.save(dest)


def plano_demo(pasta, frases):
    E = []

    def ef(**kw):
        E.append(kw)
    ef(tipo="titulo", inicio=2.2, duracao=3.0, texto="16 efeitos de *edição*", sobretitulo="pra testar hoje",
       posicao="terco_superior")
    ef(tipo="texto_recorte", modo="revelar", faixas=True, inicio=5.4, duracao=3.0, texto="CORTES\nRÁPIDOS\nE LIMPOS")
    ef(tipo="texto_recorte", modo="vazado", inicio=8.6, duracao=2.8, texto="IA", atravessar=True)
    ef(tipo="tela_dividida", inicio=11.6, duracao=3.4, paineis=[{"principal": True, "rotulo": "Eu"},
                                                                {"midia": "broll", "rotulo": "B-roll"}])
    ef(tipo="barra_prompt", inicio=15.2, duracao=4.6, texto="Edita meu vídeo com legendas e zoom",
       resposta="Pronto! Cortei os silêncios e adicionei 6 efeitos.", cursor=True)
    ef(tipo="deck_cenas", inicio=20.0, duracao=4.0, itens=["broll", {"imagem": "print"}, "principal",
                                                         {"texto": "Cena *4*"}], rotulos=["1", "2", "3", "4"])
    ef(tipo="riscado", inicio=24.2, duracao=3.4, itens=["Premiere", "After Effects", "CapCut"], novo="Só com *IA*")
    ef(tipo="antes_depois", inicio=27.8, duracao=3.4, rotulos=["ORIGINAL", "EDITADO"], cor_depois="cinema")
    ef(tipo="color_grade", inicio=31.4, duracao=2.6, preset="vintage", modo="revelar")
    ef(tipo="cupom", inicio=34.2, duracao=3.6, valor="50% OFF", codigo="PROMO10", detalhe="válido até domingo")
    ef(tipo="galeria", inicio=38.0, duracao=3.8, itens=["principal", "broll", {"imagem": "print"}, "broll"],
       titulo="Galeria de *vídeos*", destaque=0)
    ef(tipo="checklist", inicio=42.0, duracao=4.2, titulo="Checklist do reels",
       itens=["Gancho nos 3 primeiros segundos", "Legendas grandes", "Cortes nos silêncios", "CTA no final"])
    ef(tipo="orbita", inicio=46.4, duracao=4.2, itens=[{"icone": "chip", "texto": "IA"}, {"icone": "raio", "texto": "Rápido"},
                                                     "broll", {"icone": "coracao", "texto": "Fácil"}, {"imagem": "print"}])
    ef(tipo="afasta_revela", inicio=50.8, duracao=4.0, titulo="Por *dentro*", subtitulo="um plano em 3 passos",
       moldura="celular")
    ef(tipo="diminui_explica", inicio=55.0, duracao=4.4, conteudo={"imagem": "print"}, titulo="Como funciona",
       pontos=["Você grava", "A IA edita"])
    ef(tipo="papel", inicio=59.6, duracao=4.2, titulo="Criadores trocam a edição manual por IA",
       fonte_noticia="Jornal Exemplo", data="28 out 2026", subtitulo="Ferramentas fazem cortes, legendas e efeitos",
       destaque={"x": 0.5, "y": 0.22, "w": 0.86, "h": 0.1}, zoom_destaque=1.35)
    ef(tipo="cta", modo="seguir", inicio=64.0, duracao=3.6, usuario="@meuperfil", texto="Segue pra *mais*")
    ef(tipo="carrossel", inicio=67.8, duracao=4.0, titulo="Ferramentas",
       itens=[{"icone": "play", "texto": "Cortes"}, {"icone": "chip", "texto": "Legendas"},
              {"icone": "raio", "texto": "Efeitos"}, {"icone": "estrela", "texto": "Cor"}])
    ef(tipo="lista", inicio=72.0, duracao=4.0, titulo="Efeitos", itens=["Carrossel", "Textos com recorte",
                                                                        "Tela dividida", "Barra de prompt"])
    ef(tipo="passos", inicio=76.2, duracao=3.2, itens=["grava", "envia", "pronto"])
    ef(tipo="contador", inicio=79.6, duracao=3.0, ate=100000, prefixo="+", rotulo="visualizações")
    ef(tipo="cta", modo="comentar", inicio=82.8, duracao=3.8, palavra="EU QUERO", texto="Comenta *EU QUERO*")
    ef(tipo="mensagens", inicio=86.8, duracao=3.2, mensagens=[{"de": "outro", "texto": "Como você editou isso?"},
                                                             {"de": "eu", "texto": "Foi a IA 😄 (teste de emoji)"}])
    # sobrepostos (testes extras)
    ef(tipo="rodape", inicio=2.4, duracao=3.0, nome="Ana Souza", descricao="Estúdio Aurora", posicao="inf_esq")
    ef(tipo="zoom", inicio=6.0, duracao=2.0, intensidade=1.2)
    ef(tipo="notificacao", inicio=12.0, duracao=2.6, app="Aurora", titulo="Novo pedido", texto="Seu vídeo ficou pronto 🎉",
       icone="sino")
    ef(tipo="destaque_area", forma="circulo", inicio=28.5, duracao=2.0, alvo={"x": 0.5, "y": 0.4, "w": 0.4, "h": 0.2})
    ef(tipo="flash", inicio=27.8, duracao=0.3)
    ef(tipo="glitch", inicio=8.5, duracao=0.3)
    ef(tipo="tremor", inicio=24.2, duracao=0.5)
    ef(tipo="vazamento_luz", inicio=50.6, duracao=1.2)
    ef(tipo="pip", midia="broll", inicio=79.6, duracao=3.0, posicao="sup_dir", largura=0.3)
    ef(tipo="imagem", imagem="logo", inicio=86.8, duracao=3.0, posicao="sup_esq", largura=0.18, flutuar=True)
    ef(tipo="marca_dagua", imagem="logo", largura=0.1)
    ef(tipo="barra_progresso", cor="destaque")
    ef(tipo="legendas", estilo="destaque", texto=[{"texto": "isso aqui é um teste de legenda", "inicio": 2.2, "fim": 4.8},
                                                   {"texto": "com destaque na palavra falada", "inicio": 5.0, "fim": 7.5}])
    plano = {
        "saida": {"arquivo": "saida/demo_efeitos.mp4", "formato": "9:16", "fps": 30},
        "estilo": "pro",
        "midias": {"principal": "teste_principal.mp4", "broll": "teste_broll.mp4", "print": "teste_print.png",
                   "logo": "teste_logo.png", "musica": "teste_musica.wav"},
        "linha_do_tempo": [{"cartao": {"texto": "Demo do *editor*", "sobretitulo": "autoteste"},
                            "duracao": 2.0}, {"midia": "principal", "de": 0, "ate": 88.2, "transicao": "zoom"}],
        "efeitos": E,
        "audio": {"musica": "musica", "volume_musica": 0.12, "ducking": True},
    }
    with open(os.path.join(pasta, "plano_demo.json"), "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=1)
    return os.path.join(pasta, "plano_demo.json")


def rodar_demo(pasta="demo", rapido=False, orcamento=None, video=None):
    os.makedirs(pasta, exist_ok=True)
    pv = os.path.join(pasta, "teste_principal.mp4")
    frases = []
    if video:
        import shutil
        shutil.copy(video, pv)
    elif not os.path.exists(pv):
        log("gerando vídeo de teste...")
        frases = gerar_video_teste(pv)
    if not os.path.exists(os.path.join(pasta, "teste_broll.mp4")):
        gerar_broll(os.path.join(pasta, "teste_broll.mp4"), w=720, h=1280)
    if not os.path.exists(os.path.join(pasta, "teste_print.png")):
        gerar_print(os.path.join(pasta, "teste_print.png"))
    if not os.path.exists(os.path.join(pasta, "teste_logo.png")):
        gerar_logo(os.path.join(pasta, "teste_logo.png"))
    if not os.path.exists(os.path.join(pasta, "teste_musica.wav")):
        salvar_wav(os.path.join(pasta, "teste_musica.wav"), _musica_sintetica())
    plano = plano_demo(pasta, frases)
    log("plano de demonstração:", plano)
    from .render import previa, renderizar

    previa(plano, n=12, rascunho=rapido)
    st, arq = renderizar(plano, rascunho=rapido, orcamento=orcamento)
    return st, arq
