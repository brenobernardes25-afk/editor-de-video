# Formato do plano (plano.json)

O plano descreve a edição inteira. Chaves em português sem acento (aliases em inglês e com acento também
funcionam). Caminhos relativos são relativos à pasta do plano.

```json
{
  "saida": {"arquivo": "saida/video_editado.mp4", "formato": "9:16", "fps": 30, "qualidade": "alta"},
  "estilo": "pro",
  "midias": {"principal": "bruto.mp4", "print": "print.png", "musica": "musica.mp3", "logo": "logo.png"},
  "cortar_silencios": {"silencio_min": 0.45, "margem": 0.12, "remover": [[31.2, 34.0]]},
  "zoom_alternado": 1.1,
  "correcoes": {"cloud": "Claude", "chat gpt": "ChatGPT"},
  "efeitos": [ ... ],
  "audio": {"musica": "musica", "volume_musica": 0.15, "ducking": true}
}
```

## saida
- `arquivo`: caminho do MP4 final.
- `formato`: `9:16` (padrão: Reels/TikTok/Shorts), `16:9`, `1:1`, `4:5`, `original` ou `LxA` (ex. `1080x1920`).
- `fps`: 30 (padrão), 24, 25, 60 ou `original`. `qualidade`: `maxima` | `alta` (padrão) | `media` | `baixa`.
- `duracao_max`: corta o vídeo final nesse tempo (s).

## estilo
O estilo define fontes, cores, cartões e a legenda de uma vez. Sem `estilo`, vale `pro`.

| nome | visual | bom para |
|---|---|---|
| `pro` (padrão) | neutro, branco + preto, acento amarelo, cartões de vidro fosco, títulos Inter Display, legenda larga e pesada | qualquer coisa; "deixa profissional" |
| `minimal` | tudo branco, sem cor de acento, legenda discreta | marca pessoal sóbria, depoimento |
| `impacto` | legenda em CAIXA ALTA larga com contorno, amarelo + verde, cartões sólidos | retenção, estilo Hormozi, cortes |
| `clean` | cartões brancos, azul, legenda em caixa escura | tutorial, institucional, aula |
| `cinema` | títulos em caixa alta espaçada, legenda pequena, acento champanhe (use junto `color_grade` `cinema`) | vlog, storytelling, marca premium |
| `tech` | azul elétrico, rótulos em mono, caixa na palavra falada | tecnologia, IA, software |
| `neon` | verde-limão vivo com brilho na legenda | creator, games, jovem |
| `noticia` | vermelho, letras condensadas, cartões brancos | notícia, urgência, comentário |
| `elegante` | preto e branco, *destaques* em itálico serifado | luxo, moda, editorial |
| `terroso` | âmbar quente com serifa | gastronomia, lifestyle, viagem |
| `dinheiro` | verde dinheiro | finanças, vendas, resultados |

Aliases: `premium`/`profissional` → pro, `hormozi`/`viral` → impacto, `claro`/`tutorial` → clean,
`cinematografico` → cinema, `luxo`/`editorial` → elegante, `vendas`/`financas` → dinheiro, `jornal` → noticia.

Para ajustar só uma parte: `{"base": "pro", "destaque": "#3D8BFF"}` (troca o acento), `{"base": "pro",
"material": "solido"}` (cartões sólidos em vez de vidro), `{"base": "pro", "legenda": {"estilo": "caixa_palavra"}}`.
Não invente paletas: um estilo pronto + no máximo uma troca de cor costuma ficar melhor.

Chaves de cor: `fundo, fundo2, cartao, texto, texto_suave, texto_escuro, destaque, destaque2, sucesso, perigo,
ui_azul, ui_vermelho, ui_bolha_eu, ui_bolha_outro`. Material dos cartões: `material` = `vidro` (padrão, desfoca o
vídeo atrás) | `solido` | `claro` | `vidro_claro` | `preto`; cada efeito com cartão também aceita `material`.
Em qualquer efeito, `cor` aceita `#hex`, `#hexAA` (com alfa), nomes (`branco`, `amarelo`...) ou as chaves do
estilo (`destaque`, `texto`...).

Marcação nos textos: `*palavra*` = cor de destaque (no `elegante`, itálico serifado), `_palavra_` = fonte de
destaque, `==palavra==` = etiqueta sólida na cor de destaque, `\n` = quebra de linha.

Fontes incluídas: `InterDisplay-Medium, InterDisplay-SemiBold, InterDisplay-Bold, InterDisplay-ExtraBold,
InterDisplay-Black, InterDisplay-BlackItalic, Inter-Medium, Inter-SemiBold, Inter-Bold, MonaSansSemiExpanded-Bold,
MonaSansSemiExpanded-ExtraBold, MonaSansSemiExpanded-Black, MonaSansExpanded-Bold, MonaSansExpanded-Black,
MonaSansCondensed-ExtraBold, MonaSansCondensed-Black, Lora-Bold, Lora-SemiBoldItalic, JetBrainsMono-Medium,
JetBrainsMono-Bold`. Nomes comuns viram a mais parecida (`Montserrat` → Mona Sans SemiExpanded, `Bebas`/`Anton`
→ Mona Sans Condensed, `Helvetica`/`SF Pro` → Inter Display).

## midias
Nomes → arquivos. `principal` é o vídeo bruto. Tudo que um efeito usar (b-roll, prints, logo, música) entra aqui.

## Linha do tempo (o "corte")
Três jeitos:
1. **Automático por silêncio** (recomendado para falas): `"cortar_silencios": true` ou com opções
   `{"silencio_min": 0.45, "margem": 0.12, "remover": [[ini, fim], ...]}`. Usa as palavras da transcrição (se
   houver) para cortar pausas; `remover` tira trechos em tempo **bruto** (erros, repetições, "ééé").
2. **Manual**: `"linha_do_tempo": [bloco, bloco, ...]` — os blocos tocam em sequência.
3. Sem nada: o vídeo inteiro.

Bloco de vídeo: `{"midia": "principal", "de": 3.2, "ate": 9.8}` + opcionais:
`velocidade` (0.5–3), `zoom` (1.15 ou `{"de":1,"para":1.2}`), `enquadrar` (`auto` | `rosto` | `centro` |
`ajustar` (inteiro com fundo desfocado) | `{"x":0.4,"y":0.5}`), `espelhar`, `cor` (look, ex. `"cinema"`),
`mudo`, `volume`, `congelar` (true + `duracao`), `transicao` (entrada deste bloco: `corte`, `fade`, `preto`,
`branco`, `flash`, `deslizar`, `deslizar_cima`, `zoom`, `zoom_out`, `chicote`, `desfoque`, `glitch`, `cortina`,
`circulo`, `girar`, ou `{"tipo": "zoom", "duracao": 0.4}`).
Bloco de imagem: `{"imagem": "foto", "duracao": 3, "movimento": "kenburns" | "zoom_out" | "pan" | "nenhum"}`.
Cartão de tela cheia: `{"cartao": {"texto": "Capítulo *2*", "sobretitulo": "parte", "subtitulo": "..."},
"duracao": 2, "fundo": "#101012"}` (aceita os parâmetros do efeito `titulo`).
Cor sólida: `{"cor_solida": "#000000", "duracao": 0.5}`.

`zoom_alternado: 1.1` aplica zoom em um corte sim, outro não (ritmo de jump cut). Converter 16:9 → 9:16 usa
`enquadrar: auto`, que segue o rosto quando detectado.

## Tempos
Efeitos usam o tempo do vídeo **final** (depois dos cortes). Formas aceitas:
- número: `4.5` (s) ou texto `"1:05.2"`;
- `{"palavra": "clones", "n": 1, "ajuste": -0.15}` — quando a palavra é dita (n-ésima ocorrência; frases de
  várias palavras funcionam: `"clones com IA"`). Em `fim`, usa o fim da palavra. **É o jeito mais robusto**,
  porque não quebra quando os cortes mudam;
- `{"bruto": 37.2}` — instante do vídeo original;
- `{"bloco": 3, "t": 0.5}` — relativo ao início do bloco 3; `{"bloco": 3, "fim_bloco": true}`.
- `"inicio"` / `"fim"` (strings) = começo/fim do vídeo. `"tudo": true` = vídeo inteiro.

## Transcrição
`analisar` grava `VIDEO.transcricao.json` (palavras com início/fim) e `trabalho/transcricao.txt`. O render acha
sozinho. `correcoes` troca palavras/frases erradas (vale para legendas e para âncoras `palavra`):
`{"cloud": "Claude", "dois mil e vinte e seis": "2026"}`.

## audio
- `musica` (nome em midias), `volume_musica` (0.16 com voz), `musica_inicio` (s dentro da música),
  `fade_entrada_musica`, `fade_saida_musica`, `ducking` (true: abaixa a música quando há fala), `nivel_ducking` (0.35).
- `normalizar` (true: −14 LUFS, padrão das redes), `loudness` (−14), `volume_voz` (1.0).
- `limpar_voz` (filtro + compressor), `reduzir_ruido` (com limpar_voz; tira chiado).
- `sons_auto` (true: cada efeito toca um som discreto ao entrar), `volume_sons` (1.0).
- `sons`: lista manual `[{"t": 3.2, "tipo": "whoosh", "volume": 0.5}]`. Tipos: `whoosh, swish, pop, gota,
  click, tecla, ding, sucesso, caixa (ka-ching), impacto (boom), riser, glitch, notificacao, risco, papel`.

## Efeitos
Lista em `efeitos` (ordem = camada; o motor organiza por fase: câmera → cor do vídeo → cenas → sobreposições →
legendas → finais). Veja `referencia/efeitos.md` ou `editor.py efeitos NOME`.
Para desligar um efeito sem apagar: `"desativado": true`.
