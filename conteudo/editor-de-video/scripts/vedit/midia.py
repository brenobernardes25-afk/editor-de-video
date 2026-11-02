"""Leitura de mídias: quadros de vídeo via ffmpeg (sequencial, com reabertura em saltos), imagens e áudio."""
import os
import subprocess

import numpy as np
from PIL import Image, ImageOps

from .util import aviso, ffmpeg_bin, sondar

LIMITE_LADO = 2160  # decodifica no máximo em 4K no lado maior


class LeitorVideo:
    """Entrega quadros (numpy HxWx3 uint8) em tempos crescentes, reabrindo o ffmpeg em saltos."""

    def __init__(self, caminho, fps, tamanho=None):
        self.caminho = caminho
        self.info = sondar(caminho)
        self.fps = float(fps)
        self.dt = 1.0 / self.fps
        w, h = self.info["largura"], self.info["altura"]
        if tamanho is None:
            m = max(w, h)
            if m > LIMITE_LADO:
                f = LIMITE_LADO / m
                tamanho = (int(w * f) // 2 * 2, int(h * f) // 2 * 2)
        self.tamanho = tamanho
        self.w, self.h = (tamanho if tamanho else (w, h))
        self.proc = None
        self.t0 = 0.0
        self.k = -1
        self.ultimo = None
        self.dur = max(0.0, self.info["duracao"])

    def _abrir(self, t):
        self.fechar()
        t = max(0.0, t)
        vf = "fps=%s" % repr(self.fps)
        if self.tamanho:
            vf += ",scale=%d:%d:flags=bicubic" % (self.w, self.h)
        cmd = [ffmpeg_bin(), "-v", "error", "-nostdin"]
        if t > 0:
            cmd += ["-ss", "%.4f" % t]
        cmd += ["-i", self.caminho, "-an", "-sn", "-dn", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     bufsize=self.w * self.h * 3 * 2)
        self.t0 = t
        self.k = -1

    def _ler(self):
        n = self.w * self.h * 3
        buf = self.proc.stdout.read(n) if self.proc else b""
        if len(buf) < n:
            return False
        self.ultimo = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        self.k += 1
        return True

    def quadro(self, t):
        t = max(0.0, min(t, max(0.0, self.dur - self.dt * 0.5)))
        atual = self.t0 + self.k * self.dt
        if self.proc is None or self.ultimo is None and self.k >= 0:
            self._abrir(t)
        elif t < atual - self.dt * 0.51 or t > atual + 2.5:
            self._abrir(t)
        while self.t0 + self.k * self.dt < t - self.dt * 0.5:
            if not self._ler():
                break
        if self.ultimo is None:
            if not self._ler():
                # vídeo acabou antes do esperado: tenta reabrir um pouco antes
                if t > 0.2:
                    self._abrir(max(0.0, t - 0.5))
                    while self._ler() and self.t0 + self.k * self.dt < t - self.dt * 0.5:
                        pass
                if self.ultimo is None:
                    return np.zeros((self.h, self.w, 3), np.uint8)
        return self.ultimo

    def fechar(self):
        if self.proc is not None:
            try:
                self.proc.stdout.close()
            except Exception:
                pass
            try:
                self.proc.kill()
                self.proc.wait(timeout=2)
            except Exception:
                pass
        self.proc = None
        self.ultimo = None


class Biblioteca:
    """Resolve nomes de mídias do plano para caminhos e fornece leitores/imagens com cache por processo."""

    def __init__(self, midias, base_dir, fps):
        self.base_dir = base_dir
        self.fps = fps
        self.mapa = {}
        for nome, v in (midias or {}).items():
            if isinstance(v, dict):
                v = v.get("arquivo") or v.get("caminho") or v.get("midia")
            self.mapa[str(nome)] = self._abs(v)
        self._leitores = {}
        self._imagens = {}

    def _abs(self, p):
        if p is None:
            return None
        p = os.path.expanduser(str(p))
        if not os.path.isabs(p):
            cand = os.path.join(self.base_dir, p)
            if os.path.exists(cand) or not os.path.exists(p):
                p = cand
        return os.path.abspath(p)

    def caminho(self, ref):
        if ref is None:
            return None
        ref = str(ref)
        if ref in self.mapa:
            return self.mapa[ref]
        p = self._abs(ref)
        if os.path.exists(p):
            return p
        raise FileNotFoundError("Mídia '%s' não encontrada (defina em \"midias\" ou use um caminho válido)." % ref)

    def info(self, ref):
        return sondar(self.caminho(ref))

    def e_imagem(self, ref):
        return self.info(ref).get("imagem", False)

    def leitor(self, ref, chave="", tamanho=None):
        k = (self.caminho(ref), chave, tamanho)
        if k not in self._leitores:
            self._leitores[k] = LeitorVideo(k[0], self.fps, tamanho)
        return self._leitores[k]

    def imagem(self, ref):
        p = self.caminho(ref)
        if p not in self._imagens:
            im = Image.open(p)
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            self._imagens[p] = im.convert("RGBA")
        return self._imagens[p]

    def quadro_pil(self, ref, t, chave="", tamanho=None):
        """Quadro como PIL RGB (vídeo) ou a própria imagem (RGB)."""
        if self.e_imagem(ref):
            return self.imagem(ref).convert("RGB")
        arr = self.leitor(ref, chave, tamanho).quadro(t)
        return Image.fromarray(arr, "RGB")

    def resetar(self):
        for l in self._leitores.values():
            l.fechar()
        self._leitores = {}

    def fechar(self):
        self.resetar()


def extrair_audio(caminho, de=0.0, ate=None, sr=48000, canais=2, velocidade=1.0):
    """Áudio float32 (n, canais) do trecho [de, ate] já com mudança de velocidade (atempo)."""
    info = sondar(caminho)
    if not info.get("tem_audio"):
        dur = ((ate if ate is not None else info["duracao"]) - de) / max(1e-6, velocidade)
        return np.zeros((max(0, int(dur * sr)), canais), np.float32)
    cmd = [ffmpeg_bin(), "-v", "error", "-nostdin"]
    if de > 0:
        cmd += ["-ss", "%.4f" % de]
    if ate is not None:
        cmd += ["-t", "%.4f" % max(0.01, ate - de)]
    cmd += ["-i", caminho, "-vn", "-sn"]
    af = []
    v = float(velocidade)
    if abs(v - 1.0) > 1e-3:
        while v > 2.0:
            af.append("atempo=2.0")
            v /= 2.0
        while v < 0.5:
            af.append("atempo=0.5")
            v /= 0.5
        af.append("atempo=%.5f" % v)
    if af:
        cmd += ["-af", ",".join(af)]
    cmd += ["-ac", str(canais), "-ar", str(sr), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        aviso("não consegui extrair áudio de %s: %s" % (os.path.basename(caminho), r.stderr[-300:]))
        return np.zeros((0, canais), np.float32)
    a = np.frombuffer(r.stdout, np.float32)
    n = len(a) // canais
    return a[: n * canais].reshape(n, canais).copy()


def audio_mono16k(caminho):
    a = extrair_audio(caminho, 0.0, None, sr=16000, canais=1)
    return a[:, 0] if a.ndim == 2 and len(a) else np.zeros(0, np.float32)
