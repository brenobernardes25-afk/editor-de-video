# Editor de vídeo com IA (Claude e ChatGPT)

Você manda o vídeo bruto, pede a edição em português e recebe o MP4 pronto. A edição tem cortes nos silêncios, legendas sincronizadas palavra por palavra, 36 efeitos e 11 estilos de acabamento. Tudo roda dentro do próprio Claude ou ChatGPT, sem instalar nada no computador.

## 1. Baixe os arquivos

| Arquivo | Para quê | Baixar |
|---|---|---|
| `editor-de-video.zip` | A skill (Claude e ChatGPT) | [baixar](https://github.com/brenobernardes25-afk/editor-de-video/releases/latest/download/editor-de-video.zip) |
| `whisper-small-pt.npz` | Modelo das legendas (só ChatGPT, cerca de 200 MB) | [baixar](https://github.com/brenobernardes25-afk/editor-de-video/releases/latest/download/whisper-small-pt.npz) |
| `INSTRUCOES_GPT.txt` | Texto para colar no GPT (só ChatGPT) | [baixar](https://github.com/brenobernardes25-afk/editor-de-video/releases/latest/download/INSTRUCOES_GPT.txt) |

Todos os arquivos ficam também na página [Releases](https://github.com/brenobernardes25-afk/editor-de-video/releases/latest).

**Não descompacte o `editor-de-video.zip`.** Envie o arquivo do jeito que ele baixou.

## 2. Instale no Claude

Precisa de um plano pago do Claude, como Pro ou Max.

1. Em **Configurações → Capacidades**, ligue **Execução de código e criação de arquivos**. Se houver opção de acesso à rede, deixe liberado. É isso que permite baixar o modelo das legendas.
2. Na mesma tela, na seção **Skills**, clique em enviar/adicionar skill e escolha o `editor-de-video.zip`.
3. Confira se a skill **editor-de-video** aparece ligada.
4. Abra uma conversa nova, anexe o vídeo e peça a edição.

## 3. Instale no ChatGPT

Precisa do plano Plus ou Pro.

1. Abra **Explorar GPTs → + Criar → Configurar**.
2. Em **Nome**, escreva `Editor de Vídeo`.
3. Em **Instruções**, cole todo o texto do `INSTRUCOES_GPT.txt`.
4. Em **Conhecimento**, envie o `editor-de-video.zip` e o `whisper-small-pt.npz`. Se o `.npz` for recusado, renomeie para `whisper-small-pt.zip` e envie de novo.
5. Em **Capacidades**, marque **Interpretador de código e análise de dados**.
6. Clique em **Criar**, escolha **Somente eu**, abra o GPT e envie o vídeo.

## 4. Peça a edição

Escreva do jeito que você falaria com um editor:

- "Edita esse vídeo pra Reels: corta os silêncios e coloca legenda destacando as palavras-chave."
- "Estilo Hormozi, legenda grande em caixa alta, zoom nas frases fortes e um CTA pra seguir @meuperfil no final."
- "Deixa profissional, cor cinematográfica, com meu nome e cargo no começo."

A IA mostra uma prévia antes de renderizar, e depois você pede ajustes: "legenda maior", "troca a cor de destaque para azul", "tira o zoom".

Se a IA editar de outro jeito, comece o pedido com **"Usa a skill editor-de-video para editar..."**.

O manual completo, com estilos, efeitos, dicas e problemas comuns, está no [LEIA-ME.txt](conteudo/LEIA-ME.txt).

## Licença

Todos os direitos reservados. O código está visível para consulta, mas não pode ser copiado, redistribuído nem revendido sem autorização.

Os componentes de terceiros mantêm as próprias licenças:

- Fontes Inter, Mona Sans, Lora e JetBrains Mono: SIL Open Font License 1.1.
- Modelo Whisper (OpenAI): MIT.
- Exportação sherpa-onnx: Apache-2.0.
- YuNet (OpenCV Zoo): MIT.

Os detalhes estão em [CREDITOS.md](conteudo/editor-de-video/CREDITOS.md).

Este projeto é independente e não é afiliado, patrocinado nem endossado pela Anthropic nem pela OpenAI.

---

<details>
<summary>Para desenvolvedores: gerar o modelo e o pacote (Windows)</summary>

Requisitos: Python 3, ffmpeg e `python -m pip install numpy pillow opencv-python`.

Rode no PowerShell, dentro da pasta do repositório:

```powershell
python -c "import sys; sys.path.insert(0, r'conteudo\editor-de-video\scripts'); from vedit.asr.converter import baixar_e_converter; print(baixar_e_converter('small', r'conteudo'))"
powershell -NoProfile -ExecutionPolicy Bypass -File .\montar-pacote.ps1
```

</details>
