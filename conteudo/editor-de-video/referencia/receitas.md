# Receitas de edição (quando o pedido for genérico)

Use como ponto de partida e adapte ao conteúdo e ao pedido. Ritmo de redes: algo novo na tela a cada 2–4 s.

## Reels dinâmico (padrão para "edita bonito", "deixa profissional", "estilo reels")
- Estilo `pro` (o padrão). `cortar_silencios: true` + `zoom_alternado: 1.1`.
- Gancho (0–3 s): `titulo` com a frase-gancho (a animação padrão `mascara` já é a de editor; `desfoque` para
  algo mais suave) ou `texto_recorte` vazado com a palavra-chave.
- `legendas` estilo `destaque` com `destacar` nas palavras-chave.
- A cada ideia nova, 1 efeito pertinente: lista → `checklist`/`lista`; comparação → `tela_dividida`/
  `antes_depois`; número → `contador`; "eu pedi pra IA" → `barra_prompt`; notícia/print → `papel`;
  explicação longa → `diminui_explica`; ferramentas/opções → `carrossel` ou `orbita`; "vários exemplos" →
  `galeria` ou `deck_cenas`; "não é X, é Y" → `riscado`.
- `zoom` (pulso) nas frases de impacto; `tremor`+`flash` raramente (1–2 vezes no vídeo).
- Fechamento: `cta` (seguir/comentar/link) nos últimos 3–4 s.
- Áudio: música do usuário com ducking; `sons_auto` ligado.

## Talking head limpo (institucional, aula, explicação séria)
- Estilo `minimal` ou `clean`; cortes de silêncio com `silencio_min` 0.6 (mais natural); sem zoom alternado.
- `rodape` com nome/cargo no início; `legendas` estilo `caixa` ou `minimal`.
- Poucos efeitos: `titulo` nas seções, `diminui_explica` para slides/prints, `checklist` no resumo.
- `color_grade` `natural` no vídeo todo (`tudo: true`, intensidade 0.7).

## Impacto / retenção (estilo Hormozi)
- Estilo `impacto`; legendas `impacto` (1–3 palavras, caixa alta) com `destacar`.
- `zoom` seco alternando 1.0/1.15 a cada frase; `flash` + som `impacto` nas viradas.
- `texto_recorte` adesivo para números e promessas; `contador` para resultados.

## Tutorial / tela do celular ou computador
- Gravação de tela como mídia: `pip` com a pessoa no canto ou `diminui_explica` (você no círculo, tela grande).
- `destaque_area` (círculo/seta) para mostrar onde clicar; `zoom` com `foco` na área.
- `passos` (1-2-3) para etapas; `barra_prompt` para mostrar o que digitar.

## Vendas / oferta
- Estilo `dinheiro` ou `impacto`. `riscado` (preço antigo → novo), `cupom` com código, `contador` (alunos,
  vendas), `notificacao` ("Pix recebido", "Nova venda"), `cta` modo `botao` ou `link`.

## Notícia / comentário
- Estilo `noticia`. `papel` com o print da notícia (destaque + zoom no trecho), `tela_dividida` você × notícia,
  `rodape` com a fonte, legendas `caixa`.

## Antes e depois / transformação
- `antes_depois` (cortina) com as duas mídias; ou a mesma mídia com `cor_depois: "cinema"` para mostrar a
  edição de cor; `color_grade` modo `revelar` para a virada.

## Storytelling / vlog
- Estilo `cinema` (ou `elegante` para luxo/moda) com `color_grade` `cinema` no vídeo todo (`tudo: true`, 0.8).
- Transições `fade`/`desfoque` entre blocos, `vazamento_luz` nas viradas,
  `broll` cobrindo falas descritivas, legendas `minimal`, música mais presente (`volume_musica` 0.22).

## Acabamento profissional (vale para todas)
- Uma cor de acento só (a do estilo) e no máximo 1–2 palavras destacadas por frase.
- Textos curtos e grandes; cartões de vidro para listas, checklists e nomes; nada de emoji como enfeite.
- Entradas rápidas e saídas curtas (já é o padrão do motor); não empilhe animações chamativas.
- Mantenha o mesmo estilo no vídeo inteiro; troque o estilo só quando o usuário pedir.

## Regras de bom senso
- No 9:16, textos e cartões entre 12% e 78% da altura; a faixa de baixo e a lateral direita são da interface do app.
- Não empilhe mais de 2 elementos ao mesmo tempo (além das legendas). Esconda legendas quando um cartão grande
  ocupar a parte de baixo (`ocultar_legendas: true` no efeito).
- Texto na tela: curto (até ~7 palavras), duração mínima de 1,5 s, palavras do próprio vídeo.
- Ancore efeitos em palavras (`{"palavra": ...}`) — sincroniza com a fala e sobrevive a mudanças nos cortes.
- Música: só a que o usuário mandar (direitos autorais). Sem música, deixe só a voz + efeitos sonoros.
