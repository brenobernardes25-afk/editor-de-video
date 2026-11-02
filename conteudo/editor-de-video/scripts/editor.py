#!/usr/bin/env python3
"""Editor de vídeo por plano JSON — CLI.

Comandos:
  verificar                         confere ffmpeg, Python, fontes e modelo de transcrição
  analisar VIDEO [opções]           metadados, fala/silêncios, cortes sugeridos, rostos, cenas, folha de contato
                                    e transcrição com tempo por palavra
  efeitos [NOME]                    lista os efeitos (ou detalha um)
  exemplo [ARQUIVO]                 escreve um plano de exemplo
  previa PLANO [--tempos 1,4.5,9]   gera quadros PNG + uma grade para conferir antes do render
  renderizar PLANO [opções]         renderiza (retomável: se parar no meio, rode de novo)
  trecho PLANO INI FIM              renderiza só um trecho (revisão rápida)
  demo [PASTA]                      gera um vídeo de teste e renderiza uma demonstração de todos os efeitos
"""
import argparse
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)


def cmd_verificar(a):
    from vedit import VERSAO
    from vedit.util import codec_video, ffmpeg_bin, filtros, ASSETS, cpu_count
    print("editor-de-video %s | Python %s" % (VERSAO, sys.version.split()[0]))
    try:
        print("ffmpeg:", ffmpeg_bin(), "| codec de vídeo:", codec_video())
        f = filtros()
        print("filtros de áudio: loudnorm=%s afftdn=%s atempo=%s" % ("loudnorm" in f, "afftdn" in f, "atempo" in f))
    except Exception as ex:
        print("ERRO ffmpeg:", ex)
    import numpy
    import PIL
    print("numpy", numpy.__version__, "| Pillow", PIL.__version__)
    try:
        import cv2
        print("opencv", cv2.__version__, "(rostos: ok)")
    except Exception:
        print("opencv: ausente (enquadramento por rosto desativado, usa o centro)")
    fontes = sorted(os.listdir(os.path.join(ASSETS, "fontes")))
    print("fontes:", ", ".join(x for x in fontes if x.endswith((".ttf", ".otf"))))
    from vedit.grafico import _fonte_emoji, fonte as _fonte
    print("emojis no texto:", "sim" if _fonte_emoji() is not None else "não (serão removidos do texto)")
    try:
        _var = abs(_fonte("Lora-Bold", 60).getlength("Hamburgo") - _fonte("Lora-Regular", 60).getlength("Hamburgo")) > 1
    except Exception:
        _var = False
    print("fontes variáveis (Lora):", "ok" if _var else "sem suporte — a serifa fica no peso normal")
    from vedit.asr import local_modelo
    m = local_modelo(a.modelo if hasattr(a, "modelo") else "auto", baixar=False)
    print("modelo de transcrição:", m or "não encontrado (veja SKILL.md › Transcrição)")
    print("núcleos:", cpu_count())


def cmd_analisar(a):
    from vedit.analise import analisar
    voc = a.vocabulario
    r = analisar(a.video, a.pasta, transcrever=not a.sem_transcricao, modelo=a.modelo, idioma=a.idioma, vocabulario=voc,
                 rostos=not a.sem_rostos, quadros=a.quadros, orcamento=a.orcamento)
    if r and r.get("parcial"):
        sys.exit(3)


def markdown_efeitos():
    from vedit.efeitos import catalogo
    from vedit.efeitos.exemplos import EXEMPLOS, TITULOS
    cat = {n: (al, fase, doc) for n, al, fase, doc in catalogo()}
    out = ["# Catálogo de efeitos (gerado de `editor.py efeitos --md`)", "",
           "Campos comuns a todos: `tipo`, `inicio`, `fim` ou `duracao`, `entrada` (subir, descer, esquerda, direita, pop,",
           "mola, zoom, girar, fade, nenhuma), `saida` (fade, subir, descer, esquerda, direita, encolher, zoom, nenhuma),",
           "`duracao_entrada`, `duracao_saida`, `posicao` (centro, topo, terco_superior, terco_inferior, baixo, rodape,",
           "sup_esq, sup_dir, inf_esq, inf_dir, esquerda, direita ou {\"x\": 0..1, \"y\": 0..1}), `som` (tipo de efeito",
           "sonoro ou false), `volume_som`, `ocultar_legendas` (true esconde as legendas enquanto o efeito dura).",
           "Tempos aceitam número (s na saída), `{\"palavra\": \"texto\", \"n\": 1, \"ajuste\": -0.1}`, `{\"bruto\": s}`,",
           "`{\"bloco\": i, \"t\": s}`. Textos aceitam `*cor de destaque*`, `_fonte de destaque_`, `==etiqueta==`, `\\n`.",
           "Estilos: pro (padrão), minimal, impacto, clean, cinema, tech, neon, noticia, elegante, terroso, dinheiro",
           "(ver referencia/plano.md).", ""]
    vistos = set()
    for i, (n, titulo) in enumerate(TITULOS):
        if n not in cat:
            continue
        vistos.add(n)
        al, fase, doc = cat[n]
        num = "%02d. " % (i + 1) if i < 16 else ""
        out.append("## %s%s — `%s`" % (num, titulo, n))
        out.append("")
        out.append("Fase: %s. Aliases: %s." % (fase, ", ".join(al[:8]) or "—"))
        out.append("")
        out.append(doc)
        out.append("")
        if n in EXEMPLOS:
            out.append("```json")
            out.append(json.dumps(EXEMPLOS[n], ensure_ascii=False))
            out.append("```")
            out.append("")
    for n, (al, fase, doc) in sorted(cat.items()):
        if n not in vistos:
            out += ["## `%s`" % n, "", doc, ""]
    return "\n".join(out)


def cmd_efeitos(a):
    from vedit.efeitos import catalogo
    if getattr(a, "md", False):
        print(markdown_efeitos())
        return
    cat = catalogo()
    if a.nome:
        from vedit.efeitos import normalizar_tipo
        from vedit.efeitos.exemplos import EXEMPLOS
        import difflib
        alvo = normalizar_tipo(a.nome)
        nomes = [n for n, _, _, _ in cat]
        if alvo not in nomes:
            cand = [n for n in nomes if n.startswith(alvo)] or difflib.get_close_matches(alvo, nomes, n=1, cutoff=0.4)
            alvo = cand[0] if cand else alvo
        for n, al, fase, doc in cat:
            if n == alvo:
                print("%s  (fase: %s)\naliases: %s\n\n%s" % (n, fase, ", ".join(al), doc))
                if n in EXEMPLOS:
                    print("\nexemplo:\n" + json.dumps(EXEMPLOS[n], ensure_ascii=False))
                return
        print("efeito não encontrado:", a.nome)
        return
    for n, al, fase, doc in cat:
        print("- %-16s %s" % (n, " ".join(doc.split()).split(". ")[0][:150]))


def cmd_exemplo(a):
    from vedit.exemplos import PLANO_EXEMPLO
    dest = a.arquivo or "plano.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(PLANO_EXEMPLO, f, ensure_ascii=False, indent=2)
    print("plano de exemplo salvo em", dest)


def cmd_previa(a):
    from vedit.render import previa
    tempos = [float(x) for x in a.tempos.split(",")] if a.tempos else None
    previa(a.plano, tempos, n=a.n, rascunho=a.rascunho)


def cmd_renderizar(a):
    from vedit.render import renderizar
    st, arq = renderizar(a.plano, rascunho=a.rascunho, orcamento=a.orcamento, jobs=a.jobs)
    sys.exit(0 if st == "pronto" else 3)


def cmd_trecho(a):
    from vedit.render import render_trecho
    render_trecho(a.plano, a.ini, a.fim, rascunho=not a.final)


def cmd_demo(a):
    from vedit.demo import rodar_demo
    rodar_demo(a.pasta or "demo", rapido=a.rapido, orcamento=a.orcamento, video=a.video)


def main():
    p = argparse.ArgumentParser(description="Editor de vídeo por plano JSON")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("verificar")
    s.add_argument("--modelo", default="auto")
    s.set_defaults(f=cmd_verificar)
    s = sub.add_parser("analisar")
    s.add_argument("video")
    s.add_argument("--pasta", default=None, help="pasta de trabalho (padrão: ./trabalho ao lado do vídeo)")
    s.add_argument("--sem-transcricao", action="store_true")
    s.add_argument("--sem-rostos", action="store_true")
    s.add_argument("--modelo", default="auto", help="auto | base | small | caminho do .npz")
    s.add_argument("--idioma", default="pt")
    s.add_argument("--vocabulario", default=None, help="nomes/termos que aparecem na fala (melhora a transcrição)")
    s.add_argument("--quadros", type=int, default=12)
    s.add_argument("--orcamento", type=float, default=None,
                   help="segundos máximos desta execução (a transcrição continua de onde parou na próxima)")
    s.set_defaults(f=cmd_analisar)
    s = sub.add_parser("efeitos")
    s.add_argument("nome", nargs="?")
    s.add_argument("--md", action="store_true", help="catálogo completo em Markdown")
    s.set_defaults(f=cmd_efeitos)
    s = sub.add_parser("exemplo")
    s.add_argument("arquivo", nargs="?")
    s.set_defaults(f=cmd_exemplo)
    s = sub.add_parser("previa")
    s.add_argument("plano")
    s.add_argument("--tempos", default=None)
    s.add_argument("--n", type=int, default=8)
    s.add_argument("--rascunho", action="store_true")
    s.set_defaults(f=cmd_previa)
    s = sub.add_parser("renderizar")
    s.add_argument("plano")
    s.add_argument("--rascunho", action="store_true", help="metade da resolução, bem mais rápido")
    s.add_argument("--orcamento", type=float, default=None,
                   help="segundos máximos desta execução (para ambientes com limite de tempo; rode de novo para continuar)")
    s.add_argument("--jobs", type=int, default=None)
    s.set_defaults(f=cmd_renderizar)
    s = sub.add_parser("trecho")
    s.add_argument("plano")
    s.add_argument("ini", type=float)
    s.add_argument("fim", type=float)
    s.add_argument("--final", action="store_true", help="resolução cheia")
    s.set_defaults(f=cmd_trecho)
    s = sub.add_parser("demo")
    s.add_argument("pasta", nargs="?")
    s.add_argument("--rapido", action="store_true")
    s.add_argument("--orcamento", type=float, default=None)
    s.add_argument("--video", default=None, help="usar este vídeo como principal na demo")
    s.set_defaults(f=cmd_demo)
    a = p.parse_args()
    if not getattr(a, "f", None):
        p.print_help()
        return
    try:
        a.f(a)
    except Exception as ex:
        from vedit.util import ErroPlano
        if isinstance(ex, ErroPlano):
            print("ERRO NO PLANO:", ex)
            sys.exit(2)
        raise


if __name__ == "__main__":
    main()
