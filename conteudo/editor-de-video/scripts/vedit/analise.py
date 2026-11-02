"""Análise do vídeo bruto: metadados, fala/silêncios (VAD), cortes sugeridos, rostos, cenas, folha de contato e
transcrição com tempo por palavra."""
import json
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from . import grafico as G
from .midia import audio_mono16k
from .util import ASSETS, aviso, ffmpeg_bin, fmt_tempo, log, salvar_json, sondar


# ------------------------------------------------------------------ fala / silêncio
def energia_db(a, sr=16000, janela=0.03, passo=0.01):
    k, h = int(janela * sr), int(passo * sr)
    if len(a) < k:
        return np.array([-90.0]), passo
    n = 1 + (len(a) - k) // h
    idx = np.arange(k)[None, :] + h * np.arange(n)[:, None]
    q = a[idx]
    rms = np.sqrt(np.mean(q * q, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9), passo


def segmentos_fala(a, sr=16000, min_fala=0.12, preencher=0.18):
    db, passo = energia_db(a, sr)
    if len(db) < 5:
        return []
    piso = np.percentile(db, 12)
    topo = np.percentile(db, 95)
    lim = max(piso + 7.0, piso + 0.32 * (topo - piso), -55.0)
    ativo = db > lim
    # suaviza: preenche buracos curtos e remove ruídos curtos
    segs = []
    i = 0
    n = len(ativo)
    while i < n:
        if ativo[i]:
            j = i
            while j < n and ativo[j]:
                j += 1
            segs.append([i * passo, j * passo + 0.03])
            i = j
        else:
            i += 1
    unidos = []
    for s in segs:
        if unidos and s[0] - unidos[-1][1] < preencher:
            unidos[-1][1] = s[1]
        else:
            unidos.append(s)
    return [(round(a_, 3), round(b_, 3)) for a_, b_ in unidos if b_ - a_ >= min_fala]


def cortes_por_silencio(caminho, silencio_min=0.45, margem=0.12, palavras=None):
    """Trechos a manter (de, ate) removendo silêncios maiores que silencio_min."""
    info = sondar(caminho)
    dur = info["duracao"]
    if palavras:
        fala = [(w["i"], w["f"]) for w in palavras]
    else:
        a = audio_mono16k(caminho)
        fala = segmentos_fala(a)
    if not fala:
        return [(0.0, dur)]
    manter = []
    for s, e in fala:
        s, e = max(0.0, s - margem), min(dur, e + margem)
        if manter and s - manter[-1][1] < silencio_min:
            manter[-1][1] = max(manter[-1][1], e)
        else:
            manter.append([s, e])
    # junta trechos muito curtos ao vizinho
    out = []
    for s, e in manter:
        if out and (e - s < 0.35):
            out[-1][1] = e
        else:
            out.append([s, e])
    return [(round(s, 3), round(e, 3)) for s, e in out]


# ------------------------------------------------------------------ rostos
URL_YUNET = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")


def _arquivo_yunet():
    nome = "face_detection_yunet_2023mar.onnx"
    for p in (os.path.join(ASSETS, "modelos", nome), os.path.expanduser("~/.cache/editor-de-video/" + nome)):
        if os.path.exists(p) and os.path.getsize(p) > 100000:
            return p
    # não veio junto (ex.: motor baixado sem binários): tenta baixar do OpenCV Zoo (MIT)
    dest = os.path.expanduser("~/.cache/editor-de-video/" + nome)
    try:
        import urllib.request
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with urllib.request.urlopen(URL_YUNET, timeout=30) as r:
            dados = r.read()
        if len(dados) > 100000:
            open(dest, "wb").write(dados)
            return dest
    except Exception:
        pass
    return None


def _detector():
    import cv2  # noqa

    yunet = _arquivo_yunet() or ""
    if hasattr(cv2, "FaceDetectorYN") and os.path.exists(yunet):
        try:
            d = cv2.FaceDetectorYN.create(yunet, "", (320, 320), 0.6, 0.3, 20)

            def det(img_bgr):
                h, w = img_bgr.shape[:2]
                d.setInputSize((w, h))
                _, faces = d.detect(img_bgr)
                if faces is None:
                    return []
                return [(f[0], f[1], f[2], f[3], f[-1]) for f in faces]
            return det
        except Exception as ex:
            aviso("YuNet indisponível (%s)" % ex)
    casc = getattr(getattr(cv2, "data", None), "haarcascades", "") or ""
    xml = os.path.join(casc, "haarcascade_frontalface_default.xml")
    if os.path.exists(xml):
        cc = cv2.CascadeClassifier(xml)

        def det(img_bgr):
            g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            fs = cc.detectMultiScale(g, 1.15, 5, minSize=(30, 30))
            return [(x, y, w, h, 1.0) for (x, y, w, h) in fs]
        return det
    return None


def _quadros_baixa(caminho, fps=4, largura=480):
    info = sondar(caminho)
    w, h = info["largura"], info["altura"]
    if w >= h:
        nw, nh = largura, int(round(largura * h / w / 2)) * 2
    else:
        nh, nw = largura, int(round(largura * w / h / 2)) * 2
    cmd = [ffmpeg_bin(), "-v", "error", "-nostdin", "-i", caminho, "-an", "-vf",
           "fps=%g,scale=%d:%d" % (fps, nw, nh), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    k = 0
    n = nw * nh * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield k / fps, np.frombuffer(b, np.uint8).reshape(nh, nw, 3)
        k += 1
    p.wait()


def trilha_rostos(caminho, fps=4, usar_cache=True):
    """[(t, cx, cy, tamanho)] normalizados e suavizados; [] se não houver detector/rosto."""
    cache = caminho + ".rostos.json"
    try:
        st = os.stat(caminho)
        chave = "%d-%d" % (st.st_size, int(st.st_mtime))
    except Exception:
        chave = ""
    if usar_cache and os.path.exists(cache):
        try:
            d = json.load(open(cache))
            if d.get("chave") == chave:
                return [tuple(x) for x in d["trilha"]]
        except Exception:
            pass
    try:
        det = _detector()
    except Exception:
        det = None
    if det is None:
        return []
    amostras = []
    ant = None
    for t, img in _quadros_baixa(caminho, fps):
        h, w = img.shape[:2]
        fs = det(img)
        if fs:
            if ant is None:
                f = max(fs, key=lambda f: f[2] * f[3])
            else:
                f = min(fs, key=lambda f: math.hypot((f[0] + f[2] / 2) / w - ant[0], (f[1] + f[3] / 2) / h - ant[1])
                        - 0.5 * (f[2] * f[3]) / (w * h))
            cx, cy = (f[0] + f[2] / 2) / w, (f[1] + f[3] / 2) / h
            amostras.append((t, cx, cy, f[3] / h))
            ant = (cx, cy)
        else:
            amostras.append((t, None, None, None))
    validas = [a for a in amostras if a[1] is not None]
    if len(validas) < max(2, 0.1 * len(amostras)):
        trilha = []
    else:
        ts = np.array([a[0] for a in amostras])
        vt = np.array([a[0] for a in validas])
        xs = np.interp(ts, vt, [a[1] for a in validas])
        ys = np.interp(ts, vt, [a[2] for a in validas])
        ss = np.interp(ts, vt, [a[3] for a in validas])

        def suavizar(v, tau=0.7):
            k = math.exp(-1.0 / (fps * tau))
            f = np.copy(v)
            for i in range(1, len(f)):
                f[i] = k * f[i - 1] + (1 - k) * v[i]
            b = np.copy(f)
            for i in range(len(b) - 2, -1, -1):
                b[i] = k * b[i + 1] + (1 - k) * f[i]
            return b

        xs, ys, ss = suavizar(xs), suavizar(ys), suavizar(ss, 1.2)
        # zona morta: só move o enquadramento se o rosto andar mais que 3%
        zx, zy = xs[0], ys[0]
        for i in range(len(xs)):
            if abs(xs[i] - zx) > 0.03:
                zx += (xs[i] - zx) - math.copysign(0.03, xs[i] - zx)
            if abs(ys[i] - zy) > 0.03:
                zy += (ys[i] - zy) - math.copysign(0.03, ys[i] - zy)
            xs[i], ys[i] = zx, zy
        xs, ys = suavizar(xs, 0.35), suavizar(ys, 0.35)
        trilha = [(round(float(t), 3), round(float(x), 4), round(float(y), 4), round(float(s), 4))
                  for t, x, y, s in zip(ts, xs, ys, ss)]
    try:
        json.dump({"chave": chave, "trilha": trilha}, open(cache, "w"))
    except Exception:
        pass
    return trilha


# ------------------------------------------------------------------ cenas
def mudancas_de_cena(caminho, fps=4):
    cache = caminho + ".cenas.json"
    try:
        st = os.stat(caminho)
        chave = "%d-%d" % (st.st_size, int(st.st_mtime))
        d = json.load(open(cache))
        if d.get("chave") == chave:
            return d["cenas"]
    except Exception:
        chave = ""
    r = _mudancas_de_cena(caminho, fps)
    try:
        json.dump({"chave": chave, "cenas": r}, open(cache, "w"))
    except Exception:
        pass
    return r


def _mudancas_de_cena(caminho, fps=4):
    ant = None
    difs = []
    for t, img in _quadros_baixa(caminho, fps, 160):
        g = img.mean(axis=2)
        g = g[::4, ::4]
        if ant is not None:
            difs.append((t, float(np.mean(np.abs(g - ant)))))
        ant = g
    if not difs:
        return []
    v = np.array([d for _, d in difs])
    lim = max(18.0, float(np.median(v)) * 4 + 6)
    out = []
    for t, d in difs:
        if d > lim and (not out or t - out[-1] > 0.8):
            out.append(round(t, 2))
    return out


# ------------------------------------------------------------------ folha de contato
def folha_contato(caminho, destino, n=12, palavras=None, fala=None, largura=1500):
    info = sondar(caminho)
    dur = info["duracao"]
    if dur <= 0:
        return None
    w, h = info["largura"], info["altura"]
    col = 6 if h > w else 4
    lin = int(math.ceil(n / col))
    cw = (largura - 10 * (col + 1)) // col
    ch = int(cw * h / w)
    rot = 64
    faixa = 90
    H = lin * (ch + rot + 10) + 10 + faixa + 30
    folha = Image.new("RGB", (largura, H), (22, 22, 24))
    d = ImageDraw.Draw(folha)
    f = G.fonte("Inter-Bold", 20)
    f2 = G.fonte("Inter-Medium", 15)
    tempos = [dur * (k + 0.5) / n for k in range(n)]
    from .midia import LeitorVideo

    lv = LeitorVideo(caminho, 30, (max(2, cw // 2 * 2), max(2, ch // 2 * 2)))
    for k, t in enumerate(tempos):
        x = 10 + (k % col) * (cw + 10)
        y = 10 + (k // col) * (ch + rot + 10)
        arr = lv.quadro(t)
        folha.paste(Image.fromarray(arr).resize((cw, ch)), (x, y))
        d.text((x + 6, y + ch + 4), fmt_tempo(t), font=f, fill=(255, 205, 150))
        if palavras:
            perto = [p["p"] for p in palavras if t - 1.4 <= p["i"] <= t + 1.4]
            txt = " ".join(perto)[:60]
            d.text((x + 6, y + ch + 30), txt, font=f2, fill=(215, 215, 215))
    lv.fechar()
    # faixa de fala
    y0 = H - faixa - 20
    d.text((10, y0 - 26), "fala (verde) x silêncio (cinza) — 0:00 a %s" % fmt_tempo(dur), font=f2, fill=(200, 200, 200))
    d.rectangle([10, y0, largura - 10, y0 + faixa - 30], fill=(55, 55, 60))
    L = largura - 20
    for s, e in (fala or []):
        d.rectangle([10 + L * s / dur, y0, 10 + L * e / dur, y0 + faixa - 30], fill=(80, 200, 120))
    passo = 5 if dur <= 60 else 10 if dur <= 180 else 30 if dur <= 600 else 60
    tt = 0
    while tt <= dur:
        x = 10 + L * tt / dur
        d.line([x, y0 + faixa - 30, x, y0 + faixa - 22], fill=(220, 220, 220), width=2)
        d.text((x + 2, y0 + faixa - 22), fmt_tempo(tt)[:-3], font=f2, fill=(220, 220, 220))
        tt += passo
    folha.save(destino, quality=86)
    return destino


# ------------------------------------------------------------------ análise completa
_T0 = [0.0]


def refinar_palavras(ws, fala):
    """Encaixa início/fim das palavras nos trechos de fala detectados pela energia (corrige o DTW nas pausas)."""
    if not ws or not fala:
        return ws
    import bisect
    ini = [a for a, b in fala]

    def gap_de(t):
        """(início, fim) do silêncio que contém t, ou None se t está em fala."""
        i = bisect.bisect_right(ini, t) - 1
        if i >= 0 and fala[i][0] <= t <= fala[i][1]:
            return None
        a = fala[i][1] if i >= 0 else 0.0
        b = fala[i + 1][0] if i + 1 < len(fala) else float("inf")
        return (a, b)

    for k, w in enumerate(ws):
        g1, g2 = gap_de(w["i"]), gap_de(w["f"])
        if g1 is not None and g1 == g2:
            # palavra inteira caiu num silêncio: leva para a fala mais próxima
            dur = min(w["f"] - w["i"], 0.6)
            centro = (w["i"] + w["f"]) / 2
            if (centro - g1[0] < g1[1] - centro or g1[1] == float("inf")) and g1[0] > 0:
                ant = ws[k - 1]["f"] if k > 0 else 0.0
                w["f"] = round(g1[0], 3)
                w["i"] = round(max(ant, g1[0] - dur), 3)
            else:
                prox = ws[k + 1]["i"] if k + 1 < len(ws) else float("inf")
                w["i"] = round(g1[1], 3)
                w["f"] = round(min(g1[1] + dur, max(g1[1] + 0.05, prox)), 3)
            continue
    for w in ws:
        i = bisect.bisect_right(ini, w["i"]) - 1
        dentro = i >= 0 and fala[i][0] <= w["i"] <= fala[i][1]
        if not dentro and i + 1 < len(fala) and fala[i + 1][0] < w["f"]:
            w["i"] = round(fala[i + 1][0], 3)
        j = bisect.bisect_right(ini, w["f"]) - 1
        dentro_f = j >= 0 and fala[j][0] <= w["f"] <= fala[j][1]
        if not dentro_f and j >= 0 and fala[j][1] > w["i"]:
            w["f"] = round(fala[j][1], 3)
        if w["f"] <= w["i"]:
            w["f"] = round(w["i"] + 0.08, 3)
    return ws


def analisar(caminho, pasta=None, transcrever=True, modelo="auto", idioma="pt", vocabulario=None,
             rostos=True, quadros=12, orcamento=None):
    import time as _t
    _T0[0] = _t.time()
    caminho = os.path.abspath(caminho)
    pasta = pasta or os.path.join(os.path.dirname(caminho), "trabalho")
    os.makedirs(pasta, exist_ok=True)
    info = sondar(caminho)
    log("== ANÁLISE: %s" % os.path.basename(caminho))
    log("duração %s | %dx%d | %.2f fps | áudio: %s | codec %s%s" % (
        fmt_tempo(info["duracao"]), info["largura"], info["altura"], info["fps"], "sim" if info["tem_audio"] else "NÃO",
        info["codec"], " | rotação %d°" % info["rotacao"] if info["rotacao"] else ""))
    orient = "vertical" if info["altura"] > info["largura"] else "horizontal" if info["largura"] > info["altura"] else "quadrado"
    res = {"arquivo": caminho, "info": info, "orientacao": orient}
    a = audio_mono16k(caminho) if info["tem_audio"] else np.zeros(0, np.float32)
    fala = segmentos_fala(a) if len(a) else []
    tot_fala = sum(e - s for s, e in fala)
    res["fala"] = fala
    palavras = []
    if transcrever and info["tem_audio"] and len(a) > 16000 * 0.5:
        try:
            from .asr import transcrever as tr

            fala_fina = segmentos_fala(a, preencher=0.08, min_fala=0.06)
            pronta = caminho + ".transcricao.json"
            out = None
            if os.path.exists(pronta) and os.path.getmtime(pronta) > os.path.getmtime(caminho):
                try:
                    dj = json.load(open(pronta, encoding="utf-8"))
                    if dj.get("idioma") == idioma and dj.get("vocabulario") == vocabulario and dj.get("palavras"):
                        out = {"palavras": dj["palavras"], "segmentos": dj["segmentos"], "modelo": dj.get("modelo"),
                               "_cache": True}
                except Exception:
                    out = None
            if out is None:
                out = tr(a, modelo=modelo, idioma=idioma, vocabulario=vocabulario, fala=fala,
                         estado=caminho + ".transcricao.parcial.json", orcamento=orcamento)
            if out and out.get("parcial"):
                log("PARCIAL: transcrição em %.0f%%. Rode o MESMO comando de novo para continuar." % (100 * out["progresso"]))
                return {"parcial": True}
            if out:
                palavras = out["palavras"] if out.get("_cache") else refinar_palavras(out["palavras"], fala_fina)
                res["transcricao"] = {"modelo": out.get("modelo"), "segmentos": out["segmentos"]}
                arq_t = caminho + ".transcricao.json"
                salvar_json(arq_t, {"arquivo": caminho, "modelo": out.get("modelo"), "idioma": idioma,
                                    "vocabulario": vocabulario, "palavras": palavras, "segmentos": out["segmentos"]})
                salvar_json(os.path.join(pasta, "transcricao.json"), {"arquivo": caminho, "palavras": palavras,
                                                                      "segmentos": out["segmentos"]})
                with open(os.path.join(pasta, "transcricao.txt"), "w", encoding="utf-8") as f:
                    for sg in out["segmentos"]:
                        f.write("[%s - %s] %s\n" % (fmt_tempo(sg["i"]), fmt_tempo(sg["f"]), sg["texto"]))
        except Exception as ex:
            import traceback
            traceback.print_exc()
            aviso("transcrição indisponível: %s" % ex)
    if palavras:
        # refina a fala com as palavras (mais preciso que energia)
        cortes = cortes_por_silencio(caminho, 0.45, 0.12, palavras)
    else:
        cortes = cortes_por_silencio(caminho, 0.45, 0.12) if fala else [(0.0, info["duracao"])]
    mantido = sum(e - s for s, e in cortes)
    res["cortes_sugeridos"] = [{"midia": "principal", "de": s, "ate": e} for s, e in cortes]
    res["silencios_removiveis_s"] = round(info["duracao"] - mantido, 2)
    import time as _t
    if orcamento and (_t.time() - _T0[0]) > orcamento * 0.8:
        log("PARCIAL: transcrição pronta; falta rostos/cenas. Rode o MESMO comando de novo para continuar.")
        return {"parcial": True}
    if rostos and info["tem_video"]:
        try:
            tr_ = trilha_rostos(caminho)
            res["rosto_detectado"] = bool(tr_)
            if tr_:
                xs = [p[1] for p in tr_]
                res["rosto_posicao_media"] = {"x": round(float(np.mean(xs)), 3), "y": round(float(np.mean([p[2] for p in tr_])), 3)}
        except Exception as ex:
            aviso("rostos: %s" % ex)
    if info["tem_video"]:
        try:
            res["cenas"] = mudancas_de_cena(caminho)
        except Exception as ex:
            aviso("cenas: %s" % ex)
        try:
            res["folha_contato"] = folha_contato(caminho, os.path.join(pasta, "folha_contato.jpg"), quadros,
                                                 palavras, fala)
        except Exception as ex:
            aviso("folha de contato: %s" % ex)
    salvar_json(os.path.join(pasta, "analise.json"), res)
    # resumo legível
    log("fala: %.1fs de %.1fs (%d trechos) | silêncio removível: %.1fs | cortes sugeridos: %d" % (
        tot_fala, info["duracao"], len(fala), res["silencios_removiveis_s"], len(cortes)))
    if "rosto_detectado" in res:
        log("rosto: %s%s" % ("sim" if res["rosto_detectado"] else "não",
                             " (x médio %.2f)" % res["rosto_posicao_media"]["x"] if res.get("rosto_posicao_media") else ""))
    if res.get("cenas"):
        log("mudanças de cena em: %s" % ", ".join(fmt_tempo(c) for c in res["cenas"][:20]))
    if palavras:
        log("transcrição (%s, %d palavras):" % (res["transcricao"]["modelo"], len(palavras)))
        for sg in res["transcricao"]["segmentos"]:
            log("  [%s-%s] %s" % (fmt_tempo(sg["i"]), fmt_tempo(sg["f"]), sg["texto"]))
    elif transcrever:
        log("sem transcrição (modelo indisponível ou sem fala).")
    log("arquivos: %s" % pasta)
    if res.get("folha_contato"):
        log("FOLHA DE CONTATO: %s" % res["folha_contato"])
    return res
