# Editor de vídeo com IA

Uma skill para Claude e ChatGPT que recebe um vídeo bruto e devolve o MP4 editado. Ela faz cortes nos silêncios, legendas sincronizadas palavra por palavra, 36 efeitos e 11 estilos de acabamento. A IA transcreve a fala e monta o plano de edição. O motor em Python incluído renderiza o vídeo com ffmpeg.

## Conteúdo

| Caminho | O que é |
|---|---|
| `conteudo/editor-de-video/` | A skill: `SKILL.md`, o motor (`scripts/`), as fontes e as referências |
| `conteudo/LEIA-ME.txt` | Manual de instalação e uso (Claude e ChatGPT) |
| `conteudo/INSTRUCOES_GPT.txt` | Texto das instruções do GPT personalizado |
| `montar-pacote.ps1` | Gera o `editor-de-video-pacote.zip` para distribuição |

O modelo de transcrição (`whisper-small-pt.npz`, cerca de 200 MB) e os zips gerados não ficam no repositório.

## Gerar o modelo e o pacote (Windows)

Requisitos: Python 3, ffmpeg e `python -m pip install numpy pillow opencv-python`.

Rode os comandos no PowerShell, dentro desta pasta:

```powershell
python -c "import sys; sys.path.insert(0, r'conteudo\editor-de-video\scripts'); from vedit.asr.converter import baixar_e_converter; print(baixar_e_converter('small', r'conteudo'))"
python conteudo\editor-de-video\scripts\editor.py verificar
powershell -NoProfile -ExecutionPolicy Bypass -File .\montar-pacote.ps1
```

## Licença

Todos os direitos reservados. O código está visível para consulta, mas não pode ser copiado, redistribuído nem revendido sem autorização.

Componentes de terceiros mantêm as próprias licenças:
- Fontes Inter, Mona Sans, Lora e JetBrains Mono: SIL Open Font License 1.1 (`assets/fontes/OFL.txt`).
- Modelo Whisper (OpenAI): MIT.
- Exportação sherpa-onnx: Apache-2.0.
- YuNet (OpenCV Zoo): MIT.

Os detalhes estão em `conteudo/editor-de-video/CREDITOS.md`.

Este projeto é independente e não é afiliado, patrocinado nem endossado pela Anthropic nem pela OpenAI.
