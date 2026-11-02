"""Renderização em partes retomáveis (sobrevive a limites de tempo de execução), prévias e montagem final."""
import hashlib
import json
import math
import os
import subprocess
import sys
import time

from PIL import Image, ImageDraw

from . import VERSAO
from . import grafico as G
from .contexto import Contexto, carregar_plano
from .util import args_codec_video, cpu_count, ffmpeg_bin, filtros, fmt_tempo, log, num, rodar, sondar

DUR_PARTE = 3.0


def montar(plano_path, rascunho=False):
    plano, base = carregar_plano(plano_path)
    ctx = Contexto(plano, base, rascunho=rascunho)
    return ctx


def arquivo_saida(ctx, rascunho=False):
    arq = ctx.saida.get("arquivo") or "saida/video_editado.mp4"
    if not os.path.isabs(arq):
        arq = os.path.join(ctx.base_dir, arq)
    if not arq.lower().endswith((".mp4", ".mov", ".m4v")):
        arq += ".mp4"
    if rascunho:
        r, e = os.path.splitext(arq)
        arq = r + "_rascunho" + e
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    return arq


def _hash(ctx):
    h = hashlib.sha1()
    h.update(json.dumps(ctx.plano, sort_keys=True, ensure_ascii=False, default=str).encode())
    h.update(("%s|%dx%d|%s|%s" % (VERSAO, ctx.W, ctx.H, ctx.fps, ctx.rascunho)).encode())
    for p in sorted(set(ctx.bib.mapa.values())):
        try:
            st = os.stat(p)
            h.update(("%s|%d|%d" % (p, st.st_size, int(st.st_mtime))).encode())
        except Exception:
            pass
    tr = getattr(ctx, "arquivo_transcricao", None)
    if tr and os.path.exists(tr):
        h.update(str(os.stat(tr).st_mtime).encode())
    return h.hexdigest()[:10]


def _partes(ctx, dur_parte=DUR_PARTE):
    nq = int(math.floor(ctx.duracao * ctx.fps + 1e-6))
    por = max(1, int(round(dur_parte * ctx.fps)))
    out = []
    k = 0
    i = 0
    while k < nq:
        n = min(por, nq - k)
        out.append((i, k, n))
        k += n
        i += 1
    return out, nq


def _render_parte(ctx, k0, n, destino):
    tmp = destino + ".tmp.mp4"
    cmd = [ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (ctx.W, ctx.H),
           "-r", str(ctx.fps), "-i", "-"] + args_codec_video(ctx.saida.get("qualidade", "alta"), ctx.rascunho, ctx.fps) + \
          ["-an", "-r", str(ctx.fps), tmp]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for j in range(n):
            t = (k0 + j) / ctx.fps
            img = ctx.quadro(t)
            if img.size != (ctx.W, ctx.H):
                img = img.resize((ctx.W, ctx.H))
            p.stdin.write(img.tobytes())
        p.stdin.close()
        err = p.stderr.read().decode("utf-8", "replace")
        p.wait()
        if p.returncode != 0:
            raise RuntimeError("ffmpeg falhou ao codificar parte: " + err[-800:])
        os.replace(tmp, destino)
    finally:
        if p.poll() is None:
            p.kill()
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


_CTX_FILHO = None


def _iniciar_filho(plano_path, rascunho):
    """Sem fork (Windows/macOS): cada processo filho remonta o contexto a partir do plano, em silêncio."""
    global _CTX_FILHO
    sys.stdout = open(os.devnull, "w")
    _CTX_FILHO = montar(plano_path, rascunho)
    _precarregar(_CTX_FILHO)


def _trabalho_filho(args):
    i, k0, n, destino = args
    t = time.time()
    _CTX_FILHO.bib._leitores = {}
    _render_parte(_CTX_FILHO, k0, n, destino)
    _CTX_FILHO.bib.resetar()
    return i, time.time() - t


def renderizar(plano_path, rascunho=False, orcamento=None, jobs=None, so_video=False):
    """Renderiza o plano. Retorna (status, caminho). status: 'pronto' ou 'parcial'."""
    t_ini = time.time()
    ctx = montar(plano_path, rascunho)
    saida = arquivo_saida(ctx, rascunho)
    hid = _hash(ctx)
    pasta = os.path.join(os.path.dirname(saida), ".partes_%s" % hid)
    os.makedirs(pasta, exist_ok=True)
    # tamanho das partes fica fixo entre execuções (para retomar); com orçamento, partes menores
    cfg_p = os.path.join(pasta, "config.json")
    try:
        dur_parte = json.load(open(cfg_p))["dur_parte"]
    except Exception:
        dur_parte = 2.0 if orcamento else DUR_PARTE
        json.dump({"dur_parte": dur_parte}, open(cfg_p, "w"))
    partes, nq = _partes(ctx, dur_parte)
    log("plano: %s | %dx%d @ %sfps | %s (%d quadros) | %d efeitos | partes: %d%s" % (
        os.path.basename(plano_path), ctx.W, ctx.H, ctx.fps, fmt_tempo(ctx.duracao), nq, len(ctx.efeitos),
        len(partes), " | RASCUNHO" if rascunho else ""))
    pend = [(i, k0, n, os.path.join(pasta, "parte_%04d.mp4" % i)) for (i, k0, n) in partes
            if not os.path.exists(os.path.join(pasta, "parte_%04d.mp4" % i))]
    feitas = len(partes) - len(pend)
    if feitas:
        log("retomando: %d/%d partes já prontas" % (feitas, len(partes)))
    ctx.precarregar = getattr(ctx, "precarregar", None)
    _precarregar(ctx)
    if jobs is None:
        jobs = max(1, min(4, cpu_count()))
    estimativa = None
    if pend:
        if jobs <= 1 or len(pend) == 1:
            for (i, k0, n, dest) in pend:
                if orcamento and estimativa and (time.time() - t_ini) + estimativa > orcamento:
                    break
                t = time.time()
                _render_parte(ctx, k0, n, dest)
                dt = time.time() - t
                estimativa = dt if estimativa is None else 0.6 * estimativa + 0.4 * dt
                feitas += 1
                log("parte %d/%d pronta (%.1fs)" % (feitas, len(partes), dt))
            ctx.bib.resetar()
        else:
            import multiprocessing as mp

            global _CTX_FILHO
            _CTX_FILHO = ctx
            try:
                pool = mp.get_context("fork").Pool(jobs)
            except ValueError:
                pool = mp.get_context("spawn").Pool(jobs, initializer=_iniciar_filho, initargs=(plano_path, rascunho))
            with pool:
                fila = list(pend)
                voando = []
                while fila or voando:
                    while fila and len(voando) < jobs:
                        dec = time.time() - t_ini
                        if orcamento and estimativa and dec + estimativa * 1.1 > orcamento:
                            break
                        item = fila.pop(0)
                        voando.append(pool.apply_async(_trabalho_filho, (item,)))
                    if not voando:
                        break
                    time.sleep(0.05)
                    for r in list(voando):
                        if r.ready():
                            voando.remove(r)
                            i, dt = r.get()
                            estimativa = dt if estimativa is None else 0.6 * estimativa + 0.4 * dt
                            feitas += 1
                            log("parte %d/%d pronta (%.1fs)" % (feitas, len(partes), dt))
                    if orcamento and (time.time() - t_ini) > orcamento and not voando:
                        break
    restantes = [p for p in partes if not os.path.exists(os.path.join(pasta, "parte_%04d.mp4" % p[0]))]
    if restantes:
        log("PARCIAL: %d/%d partes prontas (%.0f%%). Rode o MESMO comando de novo para continuar."
            % (len(partes) - len(restantes), len(partes), 100.0 * (len(partes) - len(restantes)) / len(partes)))
        return "parcial", None
    # áudio
    wav = os.path.join(pasta, "audio.wav")
    info_a = os.path.join(pasta, "audio.json")
    if not os.path.exists(wav) or not os.path.exists(info_a):
        from .audio import mixar

        t = time.time()
        mixar(ctx, wav)
        json.dump({"so_efeitos": bool(getattr(ctx, "audio_so_efeitos", False))}, open(info_a, "w"))
        log("áudio mixado (%.1fs)" % (time.time() - t))
    so_efeitos = json.load(open(info_a)).get("so_efeitos", False)
    # junta tudo
    lista = os.path.join(pasta, "lista.txt")
    with open(lista, "w") as f:
        for (i, _, _) in partes:
            f.write("file '%s'\n" % os.path.join(pasta, "parte_%04d.mp4" % i).replace("'", "'\\''"))
    af = []
    cfg = ctx.audio_cfg
    alvo = num(cfg.get("loudness", cfg.get("lufs", -14)), -14)
    if cfg.get("normalizar", True) and not so_efeitos and "loudnorm" in filtros():
        af.append("loudnorm=I=%g:TP=-1.5:LRA=11" % alvo)
    cmd = [ffmpeg_bin(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lista, "-i", wav,
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    if af:
        cmd += ["-af", ",".join(af)]
    cmd += ["-t", "%.3f" % (nq / ctx.fps), "-movflags", "+faststart", saida]
    rodar(cmd)
    info = sondar.__wrapped__(saida) if hasattr(sondar, "__wrapped__") else sondar(saida)
    tam = os.path.getsize(saida) / 1e6
    log("PRONTO: %s | %s | %dx%d | %.1f MB | %.0fs de render" % (saida, fmt_tempo(info["duracao"]), info["largura"],
                                                                   info["altura"], tam, time.time() - t_ini))
    # limpeza das partes (economiza espaço; um novo render recomeça do zero)
    try:
        import shutil
        for d in os.listdir(os.path.dirname(saida)):
            if d.startswith(".partes_"):
                shutil.rmtree(os.path.join(os.path.dirname(saida), d), ignore_errors=True)
    except Exception:
        pass
    return "pronto", saida


def _precarregar(ctx):
    """Calcula no processo principal o que os processos filhos usariam (trilha de rostos)."""
    for b in ctx.linha.blocos:
        if b.tipo == "video" and (b.enquadrar in ("auto", "rosto")):
            inf = b.info
            asp_s = inf["largura"] / max(1, inf["altura"])
            asp_o = ctx.W / ctx.H
            if b.enquadrar == "rosto" or asp_s > asp_o * 1.03:
                try:
                    ctx.foco_rosto(b.midia, b.de, asp_o, asp_s)
                except Exception as ex:
                    log("rostos indisponíveis (%s) — enquadramento central" % ex)
                    ctx._cache_rostos[ctx.bib.caminho(b.midia)] = []


def previa(plano_path, tempos=None, n=8, rascunho=False, pasta=None):
    """Gera PNGs de quadros-chave e uma grade com todos (para conferir antes do render)."""
    ctx = montar(plano_path, rascunho)
    _precarregar(ctx)
    if not tempos:
        tempos = []
        # momentos interessantes: meio de cada efeito + distribuição uniforme
        for e in ctx.efeitos:
            if e.fase in ("camera",):
                continue
            tm = e.t0 + min(e.dur * 0.55, e.d_in + 0.6)
            if 0 <= tm < ctx.duracao:
                tempos.append(round(tm, 2))
        if len(tempos) < n:
            tempos += [round(ctx.duracao * (k + 0.5) / n, 2) for k in range(n)]
        tempos = sorted(set(tempos))[: max(n, 16)]
    pasta = pasta or os.path.join(os.path.dirname(arquivo_saida(ctx)), "previa")
    os.makedirs(pasta, exist_ok=True)
    arqs = []
    imgs = []
    for t in tempos:
        t = min(max(0.0, float(t)), max(0.0, ctx.duracao - 1.0 / ctx.fps))
        im = ctx.quadro(t)
        p = os.path.join(pasta, "previa_%06.2fs.png" % t)
        im.save(p)
        arqs.append(p)
        imgs.append((t, im))
    ctx.bib.resetar()
    grade = grade_imagens(imgs, os.path.join(pasta, "previa_grade.jpg"), ctx)
    log("prévia: %d quadros em %s" % (len(arqs), pasta))
    log("GRADE: %s" % grade)
    return arqs, grade


def grade_imagens(imgs, destino, ctx=None, largura_cel=300, colunas=None):
    if not imgs:
        return None
    w0, h0 = imgs[0][1].size
    cw = largura_cel
    ch = int(cw * h0 / w0)
    n = len(imgs)
    colunas = colunas or min(n, 6 if h0 > w0 else 4)
    linhas = int(math.ceil(n / colunas))
    rot = 34
    G_ = Image.new("RGB", (colunas * (cw + 10) + 10, linhas * (ch + rot + 10) + 10), (24, 24, 26))
    d = ImageDraw.Draw(G_)
    f = G.fonte("Inter-Bold", 22)
    for k, (t, im) in enumerate(imgs):
        x = 10 + (k % colunas) * (cw + 10)
        y = 10 + (k // colunas) * (ch + rot + 10)
        G_.paste(im.convert("RGB").resize((cw, ch), Image.BILINEAR), (x, y + rot))
        d.text((x + 4, y + 4), "%s" % fmt_tempo(t), font=f, fill=(255, 255, 255))
    G_.save(destino, quality=88)
    return destino


def render_trecho(plano_path, de, ate, rascunho=True):
    """Renderiza só um trecho (rápido) com áudio, para revisão pontual."""
    ctx = montar(plano_path, rascunho)
    _precarregar(ctx)
    saida = arquivo_saida(ctx, rascunho)
    r, e = os.path.splitext(saida)
    saida = "%s_trecho_%.1f-%.1f%s" % (r, de, ate, e)
    de = max(0.0, de)
    ate = min(ctx.duracao, ate)
    k0, k1 = int(de * ctx.fps), int(ate * ctx.fps)
    tmpv = saida + ".v.mp4"
    _render_parte(ctx, k0, k1 - k0, tmpv)
    from .audio import mixar

    wav = saida + ".wav"
    mixar(ctx, wav, de=de, ate=ate)
    rodar([ffmpeg_bin(), "-y", "-v", "error", "-i", tmpv, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", saida])
    for p in (tmpv, wav):
        try:
            os.remove(p)
        except Exception:
            pass
    log("PRONTO (trecho): %s" % saida)
    return saida
