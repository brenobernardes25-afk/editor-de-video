---
name: editor-de-video
description: Edita vídeo bruto e exporta MP4 com cortes de silêncio, legendas sincronizadas e 36 efeitos (tela dividida, barra de prompt, antes/depois, color grade, CTA...). Use sempre que pedirem para editar, cortar ou finalizar um vídeo — "edita pra Reels/TikTok/Shorts", "coloca legenda", "tira os silêncios", "deixa profissional", "adiciona zoom/efeitos/música", "transforma em vertical" — mesmo que não digam a palavra "editar".
---

# Editor de vídeo (plano JSON → MP4)

Você edita o vídeo do usuário com o **motor incluído** (Python + ffmpeg + Pillow + numpy, roda offline). Seu
trabalho é entender o pedido, analisar o vídeo, escrever um **plano JSON** e mandar o motor renderizar. Não
edite quadro a quadro com código próprio, não use moviepy/Remotion: o motor já faz cortes, legendas, efeitos,
áudio e exportação — e é retomável quando o ambiente tem limite de tempo.

## 0. Preparar o ambiente (sempre)

1. **Ache o motor** — a pasta que contém `scripts/editor.py` (nesta ordem):
   - a pasta deste SKILL.md, se ela tiver `scripts/` (skill instalada com arquivos);
   - um `editor-de-video*.zip` em `/mnt/data` (ChatGPT), `/mnt/user-data/uploads` (anexos do Claude) ou na pasta
     conectada do computador do usuário: descompacte (`unzip -q editor-de-video.zip -d /tmp/motor`; o motor fica
     em `/tmp/motor/editor-de-video`);
   - se nada disso existir, peça ao usuário para anexar `editor-de-video.zip`.
2. Defina `M=<pasta do motor>` e rode `python3 $M/scripts/editor.py verificar` (confere ffmpeg, fontes, modelo).
3. **Ache o vídeo**: anexos (`/mnt/user-data/uploads`, `/mnt/data`) ou, se o chat estiver ligado ao computador
   do usuário, traga o arquivo da pasta dele. Copie para uma pasta de trabalho (ex. `/tmp/edicao/`); nunca altere
   o original. Mídias extras (b-roll, prints, logo, música) vão para a mesma pasta.

**No computador do usuário (Claude Code, sobretudo Windows):** os caminhos `/tmp` e `/mnt/...` acima não
existem. Use `python` no lugar de `python3` (no Windows, `python3` costuma ser só o atalho da Microsoft Store) e
uma pasta de trabalho local ao lado do vídeo ou na pasta do projeto. Se o `verificar` falhar, faltam
dependências: peça ao usuário para instalar Python 3 e ffmpeg (ex. `winget install Python.Python.3.12` e
`winget install Gyan.FFmpeg`) e rode `python -m pip install numpy pillow opencv-python`
(sem ffmpeg no PATH, `pip install imageio-ffmpeg` também serve).

**Limite de tempo por comando:** `analisar` e `renderizar` podem levar minutos. Passe sempre `--orcamento` um
pouco abaixo do limite do ambiente (ChatGPT: `--orcamento 50`; terminal do Claude: `--orcamento 100`, ou mais se
você aumentar o tempo limite do comando). Se a saída terminar com `PARCIAL`, rode exatamente o mesmo comando de
novo até aparecer `PRONTO`. Nada se perde.

## 1. Analisar

```bash
cd /tmp/edicao
python3 $M/scripts/editor.py analisar bruto.mp4 --orcamento 100 --vocabulario "nomes, marcas e termos da fala"
```
Isso imprime duração, resolução, fala/silêncios, cortes sugeridos, rosto, cenas e a **transcrição com tempo por
palavra** (salva em `bruto.mp4.transcricao.json` e `trabalho/transcricao.txt`). Gera `trabalho/folha_contato.jpg`:
**abra a imagem** para ver o enquadramento e o cenário. Leia a transcrição inteira: é assim que você "assiste".
- Erros de transcrição (nomes, termos): corrija no plano com `"correcoes": {"errado": "certo"}`.
- O modelo de transcrição (Whisper) é procurado como `whisper-*.npz` (pasta do motor, `/mnt/data`, anexos,
  `~/.cache/editor-de-video`). Se não houver e o ambiente tiver acesso ao GitHub, ele baixa e converte sozinho
  (uma vez por sessão). Sem modelo e sem internet: avise o usuário (no ChatGPT, o arquivo
  `whisper-small-pt.npz` precisa estar nos arquivos do GPT) e siga sem legendas, ou peça o roteiro e use
  `legendas` com `texto` manual.

## 2. Planejar

Escreva `plano.json` na pasta de trabalho. Formato completo: `$M/referencia/plano.md`. Todos os efeitos com
parâmetros e exemplos: `$M/referencia/efeitos.md` (ou `editor.py efeitos NOME`). Ideias de estilo prontas:
`$M/referencia/receitas.md`. Leia os três na primeira edição da conversa. Esqueleto típico:

```json
{
  "saida": {"arquivo": "saida/video_editado.mp4", "formato": "9:16"},
  "estilo": "pro",
  "midias": {"principal": "bruto.mp4"},
  "cortar_silencios": true,
  "zoom_alternado": 1.1,
  "correcoes": {},
  "efeitos": [
    {"tipo": "titulo", "inicio": 0.2, "duracao": 2.6, "texto": "Frase *gancho*", "animacao": "palavra"},
    {"tipo": "legendas", "estilo": "destaque", "destacar": ["palavra-chave"]}
  ],
  "audio": {"sons_auto": true}
}
```

Como traduzir o pedido:
- Siga o pedido do usuário à risca (efeitos, ordem, textos, estilo). O que ele não especificar, decida com bom
  gosto usando as receitas. Pedido vago ("edita pra reels") → receita **Reels dinâmico**.
- **Ancore os efeitos nas palavras** (`"inicio": {"palavra": "clones"}`): sincroniza com a fala e não quebra
  quando os cortes mudam. Números puros são segundos do vídeo **final**.
- Textos na tela: curtos, do próprio vídeo, com `*destaque*` em 1–2 palavras (`==palavra==` vira etiqueta).
- Visual: o estilo padrão `pro` já tem acabamento de editor profissional (neutro, um acento amarelo, cartões de
  vidro fosco, tipografia de display). Não crie paletas próprias: troque de estilo (tabela em `plano.md`) ou só a
  cor de acento (`{"base": "pro", "destaque": "#3D8BFF"}`) quando o usuário pedir.
- Só use mídias que existem. Música só se o usuário mandar (direitos autorais).

| O usuário pede... | Use |
|---|---|
| visual / clima / "deixa profissional" / "estilo Hormozi" / "cinematográfico" | `estilo`: `pro` (padrão), `minimal`, `impacto`, `clean`, `cinema`, `tech`, `neon`, `noticia`, `elegante`, `terroso`, `dinheiro` |
| carrossel de elementos / vitrine de itens | `carrossel` |
| textos com recorte / texto vazado / letras mostrando o vídeo | `texto_recorte` (modo `revelar`, `vazado`, `adesivo`) |
| tela dividida / comparação lado a lado / eu × outra coisa | `tela_dividida` |
| barra de prompt / digitando no ChatGPT/Claude | `barra_prompt` |
| deck de cenas / cartas que saem voando | `deck_cenas` |
| elemento riscado / "não é X, é Y" / preço riscado | `riscado` |
| antes e depois / original × editado | `antes_depois` |
| color grade / filtro / cinematográfico / preto e branco | `color_grade` (preset) |
| cartão de desconto / cupom / oferta | `cupom` |
| galeria de vídeos / grade / mosaico | `galeria` |
| checklist / passo marcado | `checklist` |
| órbita de vídeos / coisas girando em volta | `orbita` |
| afasta e revela / zoom out / vídeo dentro do celular | `afasta_revela` |
| diminui e explica / eu no cantinho explicando | `diminui_explica` |
| motion de papel / print de notícia / documento | `papel` |
| CTA / segue / comenta palavra / link na bio | `cta` (modo seguir, comentar, curtir, link, botao, combo) |
| legenda / legenda animada / karaokê | `legendas` (destaque, caixa_palavra, pop, impacto, caixa, palavra, minimal) |
| título / frase na tela / gancho | `titulo` (animação `mascara` padrão, `desfoque`, `palavra`...); capítulo em tela cheia: bloco `cartao` |
| zoom / punch-in / dar ênfase | `zoom` (suave, seco, pulso, lento) ou `zoom_alternado` |
| tirar silêncios / cortes secos | `cortar_silencios` |
| mostrar imagem/vídeo por cima / cobertura | `broll` (tela cheia) ou `pip` (janela) ou `imagem` (adesivo/logo) |
| lista / top 3 / ranking | `lista`; etapas 1-2-3: `passos` |
| número subindo / estatística | `contador` |
| nome e cargo | `rodape` |
| circular / apontar / sublinhar algo | `destaque_area` |
| notificação / mensagem / conversa | `notificacao`, `mensagens` |
| marca d'água / logo fixo | `marca_dagua` |
| transição | `transicao` no bloco (fade, zoom, chicote, glitch, deslizar, flash...) |
| tremor, flash, glitch, luz, vinheta, desfoque | `tremor`, `flash`, `glitch`, `vazamento_luz`, `vinheta`, `desfocar` |
| melhorar o áudio / tirar chiado | `"audio": {"limpar_voz": true, "reduzir_ruido": true}` |
| música de fundo | `"audio": {"musica": "nome", "volume_musica": 0.15}` (ducking automático) |
| horizontal / quadrado / feed | `saida.formato`: `16:9`, `1:1`, `4:5` |

## 3. Conferir antes de renderizar (obrigatório)

```bash
python3 $M/scripts/editor.py previa plano.json            # quadros-chave automáticos
python3 $M/scripts/editor.py previa plano.json --tempos 2.5,8,14.2
```
**Abra `saida/previa/previa_grade.jpg`** e confira: texto legível e dentro da área segura (no 9:16, entre ~12% e
78% da altura; laterais livres), nada importante tapando o rosto sem motivo, legendas sem colidir com cartões,
efeitos no momento certo. Corrija o plano e gere a prévia de novo. Se algo der erro, a mensagem diz o campo.

## 4. Renderizar

```bash
python3 $M/scripts/editor.py renderizar plano.json --orcamento 100              # final (1080p)
python3 $M/scripts/editor.py renderizar plano.json --orcamento 100 --rascunho   # metade da resolução, ~3x mais rápido
python3 $M/scripts/editor.py trecho plano.json 10 18            # só um trecho, para revisão rápida
```
Repita o mesmo comando enquanto aparecer `PARCIAL`. Ao final aparece `PRONTO: caminho | duração | tamanho`.
Vídeos longos: renderize um trecho primeiro para validar o estilo com o usuário.

## 5. Entregar e revisar

- Claude: envie o MP4 como arquivo para o usuário (e, se ele pediu e o computador estiver conectado, grave na
  pasta dele). ChatGPT: dê o link `sandbox:/mnt/data/...mp4`.
- Resuma em poucas linhas o que foi feito (cortes, estilo, efeitos e onde) e o que pode ajustar.
- Ajustes ("tira o zoom", "legenda maior", "troca a cor"): edite o `plano.json` e renderize de novo — a análise
  e a transcrição já estão salvas.

## Limitações (seja honesto com o usuário)

- Não separa a pessoa do fundo (sem "texto atrás da pessoa" nem troca de fundo).
- A transcrição pode errar nomes; sempre revise e use `correcoes`/`--vocabulario`.
- Render de 1080p leva de 1 a 3× a duração do vídeo (mais com muitos efeitos de cena); use `--rascunho` para testar.
- Sem internet no ChatGPT: músicas, prints e b-rolls precisam ser enviados pelo usuário.
- Emojis no texto só aparecem se o ambiente tiver fonte de emoji (o `verificar` avisa).

## No ChatGPT (interpretador de código)

Os comandos acima são de terminal. No ChatGPT, rode cada um pelo Python com
`subprocess.run(cmd, shell=True, capture_output=True, text=True)` e leia `stdout` inteiro (é lá que aparecem
`PARCIAL`, `PRONTO`, a transcrição e os erros). Cada execução tem cerca de 60 s: use sempre `--orcamento 50` e
repita o comando enquanto aparecer `PARCIAL`. Mostre as imagens (folha de contato, prévia) abrindo-as com PIL.
