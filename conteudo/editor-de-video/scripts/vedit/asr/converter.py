"""Converte o Whisper exportado em ONNX (sherpa-onnx, GitHub Releases) para um .npz compacto (int8 por canal)
lido pelo whisper_np. Não depende do pacote 'onnx': lê o protobuf diretamente."""
import io
import json
import os
import re
import tarfile
import urllib.request

import numpy as np

from ..util import aviso, log

URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-%s.tar.bz2"


# ------------------------------------------------------------------ protobuf mínimo (ONNX)
def _varint(b, i):
    r = 0
    s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def _campos(b, i=0, fim=None):
    fim = len(b) if fim is None else fim
    while i < fim:
        k, i = _varint(b, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = _varint(b, i)
            yield f, w, v
        elif w == 1:
            yield f, w, (i, i + 8)
            i += 8
        elif w == 2:
            n, i = _varint(b, i)
            yield f, w, (i, i + n)
            i += n
        elif w == 5:
            yield f, w, (i, i + 4)
            i += 4
        else:
            raise ValueError("wire type %d" % w)


_DT = {1: np.float32, 2: np.uint8, 3: np.int8, 6: np.int32, 7: np.int64, 10: np.float16, 11: np.float64}


def _tensor(b, a, z):
    dims, nome, dt, raw, floats = [], "", 1, None, None
    for f, w, v in _campos(b, a, z):
        if f == 1:
            if w == 0:
                dims.append(v)
            else:
                j = v[0]
                while j < v[1]:
                    d, j = _varint(b, j)
                    dims.append(d)
        elif f == 2:
            dt = v
        elif f == 8:
            nome = bytes(b[v[0]:v[1]]).decode()
        elif f == 9:
            raw = v
        elif f == 4 and w == 2:
            floats = v
    if raw is not None:
        arr = np.frombuffer(bytes(b[raw[0]:raw[1]]), _DT.get(dt, np.float32))
    elif floats is not None:
        arr = np.frombuffer(bytes(b[floats[0]:floats[1]]), np.float32)
    else:
        arr = np.zeros(0, np.float32)
    if dims:
        arr = arr.reshape(dims)
    return nome, arr


def _no(b, a, z):
    n = {"in": [], "out": [], "nome": "", "op": ""}
    for f, w, v in _campos(b, a, z):
        if f == 1:
            n["in"].append(bytes(b[v[0]:v[1]]).decode())
        elif f == 2:
            n["out"].append(bytes(b[v[0]:v[1]]).decode())
        elif f == 3:
            n["nome"] = bytes(b[v[0]:v[1]]).decode()
        elif f == 4:
            n["op"] = bytes(b[v[0]:v[1]]).decode()
    return n


def ler_onnx(caminho_ou_bytes):
    b = caminho_ou_bytes if isinstance(caminho_ou_bytes, (bytes, bytearray)) else open(caminho_ou_bytes, "rb").read()
    b = memoryview(b)
    inits, nos = {}, []
    for f, w, v in _campos(b):
        if f == 7:
            for f2, w2, v2 in _campos(b, *v):
                if f2 == 5:
                    nome, arr = _tensor(b, *v2)
                    inits[nome] = arr
                elif f2 == 1:
                    nos.append(_no(b, *v2))
    return inits, nos


# ------------------------------------------------------------------ mapeamento para nomes do Whisper
def _mapear_encoder(inits, nos):
    P = {}
    for k, v in inits.items():
        m = re.match(r"audioEncoder\.(.+)$", k)
        if m:
            P["enc." + m.group(1)] = v
    for n in nos:
        nome = n["nome"]
        ins = [i for i in n["in"] if i in inits]
        if not ins:
            continue
        m = re.match(r"^/audioEncoder/(conv[12])/Conv$", nome)
        if m:
            P["enc.%s.weight" % m.group(1)] = inits[n["in"][1]]
            if len(n["in"]) > 2:
                P["enc.%s.bias" % m.group(1)] = inits[n["in"][2]]
            continue
        m = re.match(r"^/audioEncoder/blocks\.(\d+)/(attn/(query|key|value|out)|mlp/mlp\.(0|2))/(MatMul|Add)$", nome)
        if m:
            i = int(m.group(1))
            camada = m.group(3) or ("mlp%s" % m.group(4))
            sub = {"query": "attn.q", "key": "attn.k", "value": "attn.v", "out": "attn.o", "mlp0": "mlp.0", "mlp2": "mlp.2"}[camada]
            tipo = "w" if m.group(5) == "MatMul" else "b"
            P["enc.blocks.%d.%s.%s" % (i, sub, tipo)] = inits[ins[0]]
            continue
        m = re.match(r"^/(key|value)(?:_(\d+))?/(MatMul|Add)$", nome)
        if m:
            i = int(m.group(2) or 0)
            tipo = "w" if m.group(3) == "MatMul" else "b"
            P["dec.blocks.%d.cross.%s.%s" % (i, "k" if m.group(1) == "key" else "v", tipo)] = inits[ins[0]]
    return P


def _mapear_decoder(inits, nos):
    P = {}
    for k, v in inits.items():
        m = re.match(r"textDecoder\.(.+)$", k)
        if m:
            P["dec." + m.group(1)] = v
    camada, secao = -1, None
    for n in nos:
        ins = [i for i in n["in"] if i in inits]
        if not ins:
            continue
        w = ins[0]
        m = re.match(r"textDecoder\.blocks\.(\d+)\.(attn_ln|cross_attn_ln|mlp_ln)\.weight", w)
        if m:
            camada, secao = int(m.group(1)), m.group(2)
            continue
        nome = n["nome"]
        m = re.match(r"^/(query|key|value|out)(?:_\d+)?/(MatMul|Add)$", nome)
        m2 = re.match(r"^/mlp(?:_\d+)?/mlp\.(0|2)(?:_\d+)?/(MatMul|Add)$", nome)
        if m and camada >= 0:
            proj = {"query": "q", "key": "k", "value": "v", "out": "o"}[m.group(1)]
            pre = "attn" if secao == "attn_ln" else "cross"
            tipo = "w" if m.group(2) == "MatMul" else "b"
            P["dec.blocks.%d.%s.%s.%s" % (camada, pre, proj, tipo)] = inits[w]
        elif m2 and camada >= 0:
            tipo = "w" if m2.group(2) == "MatMul" else "b"
            P["dec.blocks.%d.mlp.%s.%s" % (camada, m2.group(1), tipo)] = inits[w]
    return P


def _quantizar(P):
    out = {}
    for k, v in P.items():
        v = np.asarray(v, np.float32)
        if v.ndim == 2 and min(v.shape) >= 128 and "positional_embedding" not in k:
            if k.endswith("token_embedding.weight"):
                eixo = 0  # uma escala por linha (token)
                esc = np.max(np.abs(v), axis=1, keepdims=True) / 127.0
            else:
                eixo = 1  # uma escala por coluna (canal de saída de [in, out])
                esc = np.max(np.abs(v), axis=0, keepdims=True) / 127.0
            esc = np.maximum(esc, 1e-8)
            q = np.clip(np.round(v / esc), -127, 127).astype(np.int8)
            out[k + "@q"] = q
            out[k + "@s"] = esc.astype(np.float16).reshape(-1)
            out[k + "@eixo"] = np.array([eixo], np.int8)
        else:
            out[k] = v.astype(np.float16) if v.ndim >= 2 or v.size > 4096 else v
    return out


def converter_pasta(pasta, destino, nome):
    def achar(sufixo):
        for f in os.listdir(pasta):
            if f.endswith(sufixo) and ".int8." not in f:
                return os.path.join(pasta, f)
        raise FileNotFoundError(sufixo)

    ie, ne = ler_onnx(achar("-encoder.onnx"))
    Pe = _mapear_encoder(ie, ne)
    idd, nd = ler_onnx(achar("-decoder.onnx"))
    Pd = _mapear_decoder(idd, nd)
    P = dict(Pe)
    P.update(Pd)
    tokens = open(achar("-tokens.txt"), encoding="utf-8").read()
    return salvar_npz(P, tokens, destino, nome)


def salvar_npz(P, tokens, destino, nome):
    d = P["dec.token_embedding.weight"].shape[1]
    n_enc = len({k.split(".")[2] for k in P if k.startswith("enc.blocks.")})
    n_dec = len({k.split(".")[2] for k in P if k.startswith("dec.blocks.")})
    # validação básica
    for i in range(n_enc):
        for s in ("attn.q.w", "attn.q.b", "attn.k.w", "attn.v.w", "attn.v.b", "attn.o.w", "attn.o.b", "mlp.0.w", "mlp.0.b",
                  "mlp.2.w", "mlp.2.b", "attn_ln.weight", "attn_ln.bias", "mlp_ln.weight", "mlp_ln.bias"):
            assert "enc.blocks.%d.%s" % (i, s) in P, "faltando enc %d %s" % (i, s)
    for i in range(n_dec):
        for s in ("attn.q.w", "attn.q.b", "attn.k.w", "attn.v.w", "attn.v.b", "attn.o.w", "attn.o.b", "cross.q.w",
                  "cross.q.b", "cross.k.w", "cross.v.w", "cross.v.b", "cross.o.w", "cross.o.b", "mlp.0.w", "mlp.0.b",
                  "mlp.2.w", "mlp.2.b"):
            assert "dec.blocks.%d.%s" % (i, s) in P, "faltando dec %d %s" % (i, s)
    meta = {"nome": nome, "d": int(d), "n_head": int(d // 64), "n_enc": n_enc, "n_dec": n_dec,
            "n_vocab": int(P["dec.token_embedding.weight"].shape[0]), "n_mels": int(P["enc.conv1.weight"].shape[1])}
    Q = _quantizar(P)
    Q["__meta__"] = np.frombuffer(json.dumps(meta).encode(), np.uint8)
    Q["__tokens__"] = np.frombuffer(tokens.encode("utf-8"), np.uint8)
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    tmp = destino + ".tmp.npz"
    np.savez_compressed(tmp, **Q)
    os.replace(tmp, destino)
    log("modelo convertido: %s (%.0f MB)" % (destino, os.path.getsize(destino) / 1e6))
    return destino


def baixar_e_converter(nome="small", pasta=None):
    pasta = pasta or os.path.expanduser("~/.cache/editor-de-video")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, "whisper-%s-pt.npz" % nome)
    if os.path.exists(destino):
        return destino
    url = URL % nome
    log("baixando Whisper %s de %s ..." % (nome, url))
    tar = os.path.join(pasta, "sherpa-whisper-%s.tar.bz2" % nome)
    if not os.path.exists(tar):
        req = urllib.request.Request(url, headers={"User-Agent": "editor-de-video"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tar + ".part", "wb") as f:
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
        os.replace(tar + ".part", tar)
    ext = os.path.join(pasta, "sherpa-%s" % nome)
    os.makedirs(ext, exist_ok=True)
    with tarfile.open(tar, "r:bz2") as tf:
        for m in tf.getmembers():
            base = os.path.basename(m.name)
            if base.endswith((".onnx", "tokens.txt")) and ".int8." not in base:
                m.name = base
                tf.extract(m, ext)
    out = converter_pasta(ext, destino, nome)
    for f in os.listdir(ext):
        os.remove(os.path.join(ext, f))
    os.rmdir(ext)
    try:
        os.remove(tar)
    except Exception:
        pass
    return out
