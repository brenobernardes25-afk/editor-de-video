"""Transcrição de fala com tempo por palavra (Whisper em numpy puro — roda offline em qualquer sandbox).

Procura o modelo (.npz) nesta ordem: caminho passado, variável EDITOR_VIDEO_MODELO, pasta assets/modelos da
skill, pasta atual, /mnt/data (ChatGPT), /mnt/user-data/uploads e ~/.cache/editor-de-video. Se não achar e houver
internet liberada para github.com, baixa o Whisper (sherpa-onnx, licença MIT/Apache) e converte uma vez.
"""
import glob
import os

from ..util import ASSETS, aviso, log

NOMES = {
    "base": "whisper-base-pt.npz",
    "small": "whisper-small-pt.npz",
    "tiny": "whisper-tiny-pt.npz",
}
PASTA_CACHE = os.path.expanduser("~/.cache/editor-de-video")


def _candidatos():
    pastas = [os.environ.get("EDITOR_VIDEO_MODELOS", ""), os.path.join(ASSETS, "modelos"), os.getcwd(), "/mnt/data",
              "/mnt/user-data/uploads", "/mnt/user-data/outputs", PASTA_CACHE, os.path.expanduser("~")]
    out = []
    for p in pastas:
        if p and os.path.isdir(p):
            for ext in ("npz", "zip"):  # o .npz pode ser renomeado para .zip (é o mesmo formato)
                out += glob.glob(os.path.join(p, "whisper*." + ext)) + glob.glob(os.path.join(p, "*", "whisper*." + ext))
    return out


def local_modelo(nome="auto", baixar=True):
    nome = nome or "auto"
    if os.path.isfile(str(nome)):
        return nome
    env = os.environ.get("EDITOR_VIDEO_MODELO")
    if env and os.path.isfile(env):
        return env
    cands = _candidatos()
    pref = ["small", "base", "tiny"] if nome == "auto" else [nome]
    for p in pref:
        for c in cands:
            if os.path.basename(c).startswith("whisper-%s" % p):
                return c
    if nome == "auto" and cands:
        return cands[0]
    if baixar:
        from .converter import baixar_e_converter

        for alvo in (["small", "base"] if nome == "auto" else [nome]):
            try:
                return baixar_e_converter(alvo, PASTA_CACHE)
            except Exception as ex:
                aviso("não foi possível baixar o Whisper %s: %s" % (alvo, ex))
    return None


def transcrever(audio16k, modelo="auto", idioma="pt", vocabulario=None, fala=None, estado=None, orcamento=None):
    """audio16k: numpy float32 mono 16 kHz. Retorna {'palavras', 'segmentos', 'modelo'}, {'parcial': True} ou None."""
    arq = local_modelo(modelo)
    if not arq:
        return None
    from .whisper_np import Whisper

    log("transcrevendo com %s ..." % os.path.basename(arq))
    w = Whisper(arq)
    return w.transcrever(audio16k, idioma=idioma, prompt=vocabulario, fala=fala, estado=estado, orcamento=orcamento)
