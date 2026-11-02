"""Utilidades: localizar ffmpeg, sondar mídias, rodar processos, normalizar chaves do plano."""
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from functools import lru_cache

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_SKILL = os.path.abspath(os.path.join(AQUI, "..", ".."))
ASSETS = os.path.join(RAIZ_SKILL, "assets")


def log(*a):
    print(*a, flush=True)


def aviso(*a):
    print("AVISO:", *a, flush=True)


class ErroPlano(Exception):
    pass


# ----------------------------------------------------------------- ffmpeg
@lru_cache(None)
def ffmpeg_bin():
    p = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError(
        "ffmpeg não encontrado. Instale (apt install ffmpeg / pip install imageio-ffmpeg) "
        "ou defina FFMPEG_BIN."
    )


@lru_cache(None)
def ffprobe_bin():
    p = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
    if p:
        return p
    cand = os.path.join(os.path.dirname(ffmpeg_bin()), "ffprobe")
    return cand if os.path.exists(cand) else None


@lru_cache(None)
def encoders():
    try:
        out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    except Exception:
        return set()
    s = set()
    for ln in out.splitlines():
        m = re.match(r"\s*[VAS][\.A-Z]{5}\s+(\S+)", ln)
        if m:
            s.add(m.group(1))
    return s


@lru_cache(None)
def filtros():
    try:
        out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    except Exception:
        return set()
    s = set()
    for ln in out.splitlines():
        m = re.match(r"\s*[\.TSC]{2,3}\s+(\S+)\s", ln)
        if m:
            s.add(m.group(1))
    return s


def codec_video():
    e = encoders()
    for c in ("libx264", "libopenh264", "h264", "mpeg4"):
        if c in e:
            return c
    return "mpeg4"


def args_codec_video(qualidade="alta", rascunho=False, fps=30):
    c = codec_video()
    g = str(int(round(fps * 2)))
    if c == "libx264":
        crf = {"maxima": "16", "alta": "18", "media": "21", "baixa": "24"}.get(qualidade, "18")
        # teto de bitrate: qualidade de rede social sem arquivo gigante quando a fonte tem muito ruído/grão
        teto = {"maxima": 28, "alta": 16, "media": 10, "baixa": 6}.get(qualidade, 16)
        preset = "ultrafast" if rascunho else "veryfast"
        if rascunho:
            crf, teto = "26", 8
        return ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-maxrate", "%dM" % teto, "-bufsize", "%dM" % (teto * 2),
                "-g", g, "-pix_fmt", "yuv420p"]
    if c == "libopenh264":
        return ["-c:v", "libopenh264", "-b:v", "8M", "-g", g, "-pix_fmt", "yuv420p"]
    return ["-c:v", c, "-q:v", "3", "-g", g, "-pix_fmt", "yuv420p"]


def rodar(cmd, entrada=None, silencioso=True):
    r = subprocess.run(cmd, input=entrada, capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace")[-2500:]
        raise RuntimeError("Falhou: %s\n%s" % (" ".join(map(str, cmd[:6])) + " ...", err))
    return r


# ----------------------------------------------------------------- sondagem
def _fps_de(txt):
    try:
        if "/" in txt:
            a, b = txt.split("/")
            return float(a) / float(b) if float(b) else 0.0
        return float(txt)
    except Exception:
        return 0.0


@lru_cache(None)
def sondar(caminho):
    """Retorna dict com duracao, largura, altura (já rotacionadas), fps, tem_audio, tem_video, rotacao."""
    if not os.path.exists(caminho):
        raise FileNotFoundError("Arquivo não encontrado: %s" % caminho)
    info = {"caminho": caminho, "duracao": 0.0, "largura": 0, "altura": 0, "fps": 0.0,
            "tem_video": False, "tem_audio": False, "rotacao": 0, "codec": "", "taxa_audio": 0, "imagem": False}
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic"):
        try:
            from PIL import Image

            with Image.open(caminho) as im:
                info.update(largura=im.width, altura=im.height, imagem=True, tem_video=False)
                if ext != ".gif" or getattr(im, "n_frames", 1) == 1:
                    return info
        except Exception:
            pass
    fp = ffprobe_bin()
    if fp:
        r = subprocess.run([fp, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", caminho],
                           capture_output=True, text=True)
        if r.returncode == 0:
            d = json.loads(r.stdout or "{}")
            fmt = d.get("format", {})
            try:
                info["duracao"] = float(fmt.get("duration", 0) or 0)
            except Exception:
                pass
            for s in d.get("streams", []):
                if s.get("codec_type") == "video" and not info["tem_video"]:
                    if (s.get("disposition") or {}).get("attached_pic"):
                        continue
                    info["tem_video"] = True
                    info["codec"] = s.get("codec_name", "")
                    w, h = int(s.get("width", 0)), int(s.get("height", 0))
                    rot = 0
                    try:
                        rot = int(float((s.get("tags") or {}).get("rotate", 0)))
                    except Exception:
                        pass
                    for sd in s.get("side_data_list", []) or []:
                        if "rotation" in sd:
                            try:
                                rot = int(float(sd["rotation"]))
                            except Exception:
                                pass
                    rot = rot % 360
                    if rot in (90, 270):
                        w, h = h, w
                    info.update(largura=w, altura=h, rotacao=rot)
                    fps = _fps_de(s.get("avg_frame_rate", "0/0")) or _fps_de(s.get("r_frame_rate", "0/0"))
                    info["fps"] = fps if 1 <= fps <= 240 else 30.0
                    if not info["duracao"]:
                        try:
                            info["duracao"] = float(s.get("duration", 0) or 0)
                        except Exception:
                            pass
                elif s.get("codec_type") == "audio" and not info["tem_audio"]:
                    info["tem_audio"] = True
                    info["taxa_audio"] = int(s.get("sample_rate", 0) or 0)
            return info
    # sem ffprobe: interpretar a saída do ffmpeg -i
    r = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", caminho], capture_output=True, text=True)
    txt = r.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", txt)
    if m:
        info["duracao"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Stream #\S+.*Video: ([^,\s]+).*?, (\d{2,5})x(\d{2,5})", txt)
    if m:
        info["tem_video"] = True
        info["codec"] = m.group(1)
        w, h = int(m.group(2)), int(m.group(3))
        rot = 0
        mr = re.search(r"rotate\s*:\s*(-?\d+)", txt) or re.search(r"rotation of (-?[\d\.]+) degrees", txt)
        if mr:
            rot = int(float(mr.group(1))) % 360
        if rot in (90, 270):
            w, h = h, w
        info.update(largura=w, altura=h, rotacao=rot)
        mf = re.search(r"([\d\.]+) fps", txt)
        info["fps"] = float(mf.group(1)) if mf else 30.0
    if re.search(r"Stream #\S+.*Audio:", txt):
        info["tem_audio"] = True
        ma = re.search(r"Audio:.*?(\d{4,6}) Hz", txt)
        info["taxa_audio"] = int(ma.group(1)) if ma else 48000
    return info


# ----------------------------------------------------------------- chaves do plano
def sem_acento(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c))


ALIAS_CHAVES = {
    "type": "tipo", "effect": "tipo", "kind": "tipo",
    "start": "inicio", "begin": "inicio", "from_time": "inicio", "comeco": "inicio",
    "end": "fim", "stop": "fim", "termino": "fim",
    "duration": "duracao", "dur": "duracao",
    "text": "texto", "title": "titulo", "subtitle": "subtitulo",
    "position": "posicao", "pos": "posicao",
    "items": "itens", "item": "itens",
    "color": "cor", "colors": "cores", "size": "tamanho", "font": "fonte",
    "source": "midia", "media": "midia", "src": "midia", "video": "midia", "clip": "midia",
    "image": "imagem", "img": "imagem",
    "from": "de", "to": "ate", "in": "de", "out": "ate",
    "speed": "velocidade", "style": "estilo", "output": "saida", "file": "arquivo",
    "timeline": "linha_do_tempo", "linha": "linha_do_tempo", "blocos": "linha_do_tempo", "cortes": "linha_do_tempo",
    "effects": "efeitos", "overlays": "efeitos", "medias": "midias", "sources": "midias", "assets": "midias",
    "music": "musica", "volume_music": "volume_musica", "sounds": "sons", "sfx": "sons_auto",
    "transition": "transicao", "label": "rotulo", "labels": "rotulos",
    "before": "antes", "after": "depois", "panels": "paineis", "direction": "direcao",
    "intensity": "intensidade", "preset": "preset", "code": "codigo", "value": "valor",
    "user": "usuario", "word": "palavra", "words": "palavras", "highlight": "destacar",
    "background": "fundo", "radius": "raio", "opacity": "opacidade", "scale": "escala",
    "animation": "animacao", "enter": "entrada", "exit": "saida_anim", "width": "largura", "height": "altura",
    "lines": "linhas", "columns": "colunas", "center": "centro", "target": "alvo",
    "zoom_level": "zoom", "mute": "mudo", "audio_volume": "volume", "card": "cartao",
    "mode": "modo", "raw": "bruto", "block": "bloco", "offset": "ajuste", "occurrence": "n", "captions": "legendas",
    "subtitles": "legendas", "corrections": "correcoes", "silence_cut": "cortar_silencios",
    "cut_silences": "cortar_silencios", "remove_silences": "cortar_silencios", "format": "formato",
    "quality": "qualidade", "music_volume": "volume_musica", "new": "novo", "points": "pontos", "content": "conteudo",
    "icon": "icone", "user": "usuario", "username": "usuario", "button": "botao", "frame": "moldura",
    "transitions": "transicao", "intensity_zoom": "intensidade",
}

ALIAS_SECOES_PLANO = {"saida": "saida", "output": "saida"}


SECOES_CHAVE_LIVRE = {"midias", "correcoes", "substituicoes", "vocabulario_extra"}


def normalizar_chaves(obj, raiz=False, livre=False):
    """Remove acentos, padroniza para minúsculas_com_underscore e traduz aliases em inglês.

    Em seções de chave livre (ex.: "midias", "correcoes") as chaves são nomes do usuário e
    ficam como estão; só os valores são normalizados.
    """
    if isinstance(obj, list):
        return [normalizar_chaves(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    novo = {}
    for k, v in obj.items():
        if livre:
            novo[k] = normalizar_chaves(v)
            continue
        kk = sem_acento(k).strip().lower().replace(" ", "_").replace("-", "_")
        kk = ALIAS_CHAVES.get(kk, kk)
        # "saida" dentro de um efeito é animação de saída; no topo do plano é a seção de saída
        if not raiz and kk == "saida" and isinstance(v, (str, bool)):
            kk = "saida_anim"
        novo[kk] = normalizar_chaves(v, livre=kk in SECOES_CHAVE_LIVRE)
    return novo


def ler_json(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        txt = f.read()
    # tolera comentários // e vírgulas finais (erros comuns de IA)
    txt = re.sub(r"(^|[^:\"'])//[^\n]*", r"\1", txt)
    txt = re.sub(r",\s*([\]}])", r"\1", txt)
    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        linhas = txt.splitlines()
        trecho = "\n".join(linhas[max(0, e.lineno - 3): e.lineno + 2])
        raise ErroPlano("JSON inválido em %s (linha %d, col %d): %s\n%s" % (caminho, e.lineno, e.colno, e.msg, trecho))


def salvar_json(caminho, obj):
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def fmt_tempo(s):
    s = max(0.0, float(s))
    m = int(s // 60)
    return "%d:%05.2f" % (m, s - 60 * m)


def num(v, padrao=0.0):
    try:
        if v is None:
            return padrao
        if isinstance(v, str):
            v = v.strip().replace(",", ".")
            if v.endswith("s"):
                v = v[:-1]
            if ":" in v:
                p = [float(x) for x in v.split(":")]
                r = 0.0
                for x in p:
                    r = r * 60 + x
                return r
        return float(v)
    except Exception:
        return padrao


def cpu_count():
    try:
        return len(os.sched_getaffinity(0))
    except Exception:
        return os.cpu_count() or 1
