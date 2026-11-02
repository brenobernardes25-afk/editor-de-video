# Catálogo de efeitos (gerado de `editor.py efeitos --md`)

Campos comuns a todos: `tipo`, `inicio`, `fim` ou `duracao`, `entrada` (subir, descer, esquerda, direita, pop,
mola, zoom, girar, fade, nenhuma), `saida` (fade, subir, descer, esquerda, direita, encolher, zoom, nenhuma),
`duracao_entrada`, `duracao_saida`, `posicao` (centro, topo, terco_superior, terco_inferior, baixo, rodape,
sup_esq, sup_dir, inf_esq, inf_dir, esquerda, direita ou {"x": 0..1, "y": 0..1}), `som` (tipo de efeito
sonoro ou false), `volume_som`, `ocultar_legendas` (true esconde as legendas enquanto o efeito dura).
Tempos aceitam número (s na saída), `{"palavra": "texto", "n": 1, "ajuste": -0.1}`, `{"bruto": s}`,
`{"bloco": i, "t": s}`. Textos aceitam `*cor de destaque*`, `_fonte de destaque_`, `==etiqueta==`, `\n`.
Estilos: pro (padrão), minimal, impacto, clean, cinema, tech, neon, noticia, elegante, terroso, dinheiro
(ver referencia/plano.md).

## 01. Carrossel de elementos — `carrossel`

Fase: sobre. Aliases: carousel, carrossel_de_elementos, esteira, marquee, slider, vitrine.

Carrossel de elementos sobre o vídeo. itens: [textos | {texto, icone, imagem, midia, rotulo}],
modo: 'passo' (um item central em destaque, avança a cada 'intervalo') | 'esteira' (rolagem contínua infinita),
largura_item (0.5), proporcao (altura/largura do cartão, padrão 1.0 para texto e 1.25 para mídia),
posicao (padrão 'centro'), titulo (opcional acima), fundo ('gradiente' escurece atrás), velocidade (esteira, px/s).

```json
{"tipo": "carrossel", "inicio": 30.0, "duracao": 4, "titulo": "Ferramentas", "itens": [{"icone": "play", "texto": "Cortes"}, {"icone": "chip", "texto": "Legendas"}, {"icone": "raio", "texto": "Efeitos"}]}
```

## 02. Textos com recorte — `texto_recorte`

Fase: sobre. Aliases: adesivo_texto, knockout, recorte, texto_adesivo, texto_mascara, texto_vazado, textos_com_recorte.

Texto com recorte. modo: 'revelar' (linhas surgem de uma máscara; 'faixas': true põe faixas de cor atrás
de cada linha), 'vazado' (tela escura com o vídeo aparecendo DENTRO das letras; 'atravessar': true faz a
câmera passar pelas letras no fim), 'adesivo' (texto recortado como adesivo, contorno branco grosso e sombra).
texto, tamanho (automático no vazado; 150 revelar; 96 adesivo), fonte (padrão 'fonte_impacto', letras altas),
cor, cores_faixas, posicao, maiusculas (padrão true).

```json
{"tipo": "texto_recorte", "modo": "vazado", "inicio": {"palavra": "IA"}, "duracao": 2.5, "texto": "IA", "atravessar": true}
```

## 03. Tela dividida — `tela_dividida`

Fase: cena. Aliases: comparacao, comparar, dividir_tela, duas_telas, lado_a_lado, split, split_screen, tela_dupla.

Tela dividida com 2 a 4 painéis. paineis: [fonte, ...] onde fonte = 'principal' | nome de mídia |
{midia, de, velocidade} | {imagem} | {texto, fundo} | {bruto: segundos} (outro momento do vídeo principal);
cada painel aceita 'rotulo' e 'cor' (look). direcao: 'vertical' (empilhado, padrão em 9:16) | 'horizontal'
(lado a lado) | 'grade' (2×2), espaco (px, padrão 14), raio (padrão 28), margem (padrão 28),
rotulos_posicao ('topo' | 'baixo'), entrada ('deslizar' | 'fade' | 'expandir').

```json
{"tipo": "tela_dividida", "inicio": 6.0, "duracao": 4, "paineis": [{"principal": true, "rotulo": "Eu"}, {"midia": "broll", "rotulo": "Resultado"}]}
```

## 04. Barra de prompt — `barra_prompt`

Fase: sobre. Aliases: barra_de_prompt, busca, caixa_de_texto, campo_de_busca, chat_input, digitando_prompt, prompt.

Barra de prompt (estilo chat de IA, sem marca) com o texto sendo digitado, botão de enviar e resposta
opcional. texto (o prompt), placeholder, velocidade (caracteres/s, padrão 20), tema: 'escuro' | 'claro' |
'vidro', resposta (texto que aparece num cartão acima depois do envio, com 'pensando…' antes), cursor (true =
ponteiro do mouse clica em enviar), posicao (padrão 'centro'), largura (0..1, padrão 0.88), tamanho (padrão 42).

```json
{"tipo": "barra_prompt", "inicio": 4.0, "duracao": 5, "texto": "Edita meu vídeo com legendas", "resposta": "Pronto! Cortei os silêncios e coloquei 6 efeitos.", "cursor": true}
```

## 05. Deck de cenas — `deck_cenas`

Fase: cena. Aliases: baralho, cartas, deck, deck_de_cenas, pilha, pilha_de_cartoes.

Cenas empilhadas como cartas: a de cima sai voando e revela a próxima. itens: [fontes] (vídeos, imagens,
{texto}), intervalo (s por carta; padrão divide a duração), largura (0.76), proporcao (altura/largura, padrão
1.3), direcao_saida ('esquerda' | 'direita' | 'cima' | 'alternar'), rotulos (opcional), fundo.

```json
{"tipo": "deck_cenas", "inicio": 22.0, "duracao": 4, "itens": ["clip1", "clip2", {"imagem": "print"}]}
```

## 06. Elemento riscado — `riscado`

Fase: sobre. Aliases: elemento_riscado, riscar, risco, strike, tachado.

Texto que é riscado (e opcionalmente substituído). texto ou itens: ['Premiere', 'After Effects'] (riscados
em sequência), novo: texto que aparece depois (ex. 'Só com IA'), cor_risco (padrão 'perigo'), estilo_risco:
'mao' (traço à mão, padrão) | 'reto' | 'x' (dois traços), tempo_risco (s após o início, padrão 0.6),
intervalo (entre itens, padrão 0.45), tamanho (padrão 76), cartao (padrão true: vidro fosco), posicao.

```json
{"tipo": "riscado", "inicio": 8.0, "duracao": 3.5, "itens": ["Premiere", "After Effects"], "novo": "Só com *IA*"}
```

## 07. Antes e depois — `antes_depois`

Fase: cena. Aliases: antes_e_depois, before_after, comparativo, original_editado.

Comparação antes/depois com cortina deslizante (linha com alça) ou lado a lado. antes / depois: fontes
(padrão as duas = 'principal'), cor_antes / cor_depois: look aplicado a cada lado (ex. depois: 'cinema'),
modo: 'cortina' (padrão) | 'lado_a_lado' | 'alternar', rotulos: ['ANTES', 'DEPOIS'] (ex. ['ORIGINAL',
'EDITADO']), posicao_final (0..1 onde a cortina para, padrão 0.5), vertical (true = cortina de cima p/ baixo).

```json
{"tipo": "antes_depois", "inicio": 14.0, "duracao": 3.5, "rotulos": ["ORIGINAL", "EDITADO"], "cor_depois": "cinema"}
```

## 08. Color grade — `color_grade`

Fase: base. Aliases: colorgrade, colorir, cor, correcao_de_cor, filtro, filtro_de_cor, grade_de_cor, look.

Look de cor no vídeo. preset: natural, cinema, quente, frio, pb, noir, vintage, vibrante, moody, pastel,
dourado, neon, matrix, lavado, dramatico. intensidade 0..1 (padrão 1). Ajustes finos opcionais: contraste,
saturacao, brilho, temperatura, matiz, desbotar, vinheta, grao. modo: 'aplicar' (padrão, entra suave) ou
'revelar' (uma linha passa revelando o look — ótimo para 'antes e depois' de cor). Use 'tudo': true para o
vídeo inteiro.

```json
{"tipo": "color_grade", "preset": "cinema", "tudo": true, "intensidade": 0.8}
```

## 09. Cartão de desconto — `cupom`

Fase: sobre. Aliases: cartao_de_desconto, cartao_desconto, coupon, desconto, oferta, promocao, voucher.

Cartão de desconto (ticket) com valor grande, código e brilho passando. valor ('50% OFF'), titulo
('CUPOM DE DESCONTO'), codigo ('PROMO10'), detalhe ('válido até domingo'), tema: 'destaque' (fundo na cor de
acento) | 'escuro' | 'claro', posicao (centro), largura (0.78), preco_de / preco_por (opcional: mostra
'de R$ 197 por R$ 97').

```json
{"tipo": "cupom", "inicio": 20.0, "duracao": 4, "valor": "50% OFF", "codigo": "PROMO10", "detalhe": "válido até domingo"}
```

## 10. Galeria de vídeos — `galeria`

Fase: cena. Aliases: colagem, galeria_de_videos, grade, grade_de_videos, grid, mosaico.

Grade de vídeos/imagens tocando juntos, entrando em cascata. itens: [fontes] (2–9; 'principal' vale),
colunas (auto), espaco (16), raio (24), margem (40), titulo (texto no topo), destaque: índice que cresce até
tela cheia no fim (opcional), rotulos: ['A', 'B', ...] (opcional), fundo ('estilo' | 'desfoque' | cor).

```json
{"tipo": "galeria", "inicio": 18.0, "duracao": 4, "itens": ["principal", "clip1", "clip2", "clip3"], "titulo": "Galeria de *vídeos*"}
```

## 11. Checklist — `checklist`

Fase: sobre. Aliases: checagem, check_list, lista_check, lista_de_checagem, tarefas, to_do, todo.

Checklist com itens sendo marcados em sequência (✓ desenhado) num cartão de vidro. titulo (opcional),
itens: textos ou {texto, em: tempo}, aparecer_um_a_um (false = todos visíveis desde o início), riscar (false),
tamanho (46), largura (0.84), posicao (padrão 'centro'), cor_check (destaque), material.

```json
{"tipo": "checklist", "inicio": 10.0, "duracao": 5, "titulo": "Checklist do reels", "itens": ["Gancho forte", {"texto": "Legendas", "em": {"palavra": "legendas"}}, "CTA no final"]}
```

## 12. Órbita de vídeos — `orbita`

Fase: cena. Aliases: girando_em_volta, orbit, orbita_de_videos, orbitar, sistema_solar.

Itens orbitando em elipse (com profundidade) ao redor de um centro. centro: fonte (padrão 'principal',
em círculo) ou {texto}/{icone}; itens: [fontes ou {texto}/{icone}/{imagem}] (3–8); raio_x (0.4), raio_y (0.14),
velocidade (voltas/s, padrão 0.12), tamanho_itens (0.24), tamanho_centro (0.5), fundo.

```json
{"tipo": "orbita", "inicio": 26.0, "duracao": 4, "itens": [{"icone": "chip", "texto": "IA"}, {"icone": "raio", "texto": "Rápido"}, "clip1"]}
```

## 13. Afasta e revela — `afasta_revela`

Fase: cena. Aliases: afastar, afastar_e_revelar, encolher_tela, por_dentro, revelar, tela_no_celular, zoom_out, zoom_out_revela.

O vídeo encolhe (câmera 'se afasta') e revela o que está em volta: títulos acima/abaixo, fundo e, se quiser,
uma moldura de celular. escala (padrão 0.62), raio (40), titulo / subtitulo (textos revelados acima/abaixo),
moldura ('nenhuma' | 'celular'), volta (true: volta à tela cheia no fim), posicao_y (centro do vídeo, 0..1),
fundo ('desfoque' padrão | 'estilo' | cor | mídia).

```json
{"tipo": "afasta_revela", "inicio": 34.0, "duracao": 4, "titulo": "Por *dentro*", "subtitulo": "um plano em 3 passos", "moldura": "celular"}
```

## 14. Diminui e explica — `diminui_explica`

Fase: cena. Aliases: apresentador_no_canto, diminui, diminuir_e_explicar, explicacao, explicar, pip_explica, voce_no_canto.

Você encolhe para um canto (círculo) e o conteúdo da explicação ocupa a tela. conteudo: fonte (imagem/print,
vídeo, ou {texto}); pontos: ['tópico 1', 'tópico 2'] (lista que aparece item a item, opcional); titulo (opcional);
pip: posicao 'inf_dir' | 'inf_esq' | 'sup_dir' | 'sup_esq' (padrão inf_dir); forma 'circulo' | 'arredondado';
tamanho (0.36); borda (cor, padrão destaque); fundo ('estilo' | cor | 'desfoque').

```json
{"tipo": "diminui_explica", "inicio": 38.0, "duracao": 5, "conteudo": {"imagem": "print"}, "titulo": "Como funciona", "pontos": ["Você grava", "A IA edita"]}
```

## 15. Motion de papel — `papel`

Fase: sobre. Aliases: artigo, documento, folha, manchete_jornal, motion_de_papel, noticia, paper, print_noticia.

Folha/print que entra girando em 3D e flutua. imagem (print de notícia, documento, post) OU gere um:
titulo (manchete), texto (corpo), fonte_noticia (nome do veículo — use o nome real só se for um print real),
data, subtitulo. destaque: {x, y, w, h} (0..1 dentro do papel) recebe marca-texto; zoom_destaque (ex. 1.5)
aproxima nele; tempo_destaque (s após o início, padrão 1.2); largura (0.86), fundo ('escurecer' padrão |
'desfoque' | 'nenhum'), inclinacao (graus finais, padrão 6).

```json
{"tipo": "papel", "inicio": 44.0, "duracao": 4.5, "imagem": "print", "destaque": {"x": 0.5, "y": 0.2, "w": 0.9, "h": 0.1}, "zoom_destaque": 1.4}
```

## 16. CTA ilustrativo — `cta`

Fase: sobre. Aliases: call_to_action, chamada, comentar, comente, cta_ilustrativo, curtir, inscreva_se, link_na_bio.

Chamada para ação ilustrada (interface genérica, sem marca). modo: 'seguir' (cartão de perfil + botão Seguir
clicado pelo cursor), 'comentar' (campo de comentário digitando a palavra-chave e o comentário publicado),
'curtir' (coração que explode), 'salvar', 'compartilhar', 'link' ('link na bio' com seta), 'botao' (botão com
clique), 'combo' (curtir, comentar, compartilhar, salvar em sequência). texto (frase acima, ex. 'Comenta
*EU QUERO*'), usuario ('@seuperfil'), subtitulo, palavra (para 'comentar'), botao (texto do botão), avatar
(imagem opcional), verificado (true: selo azul), posicao (padrão 'terco_inferior' / 'centro').

```json
{"tipo": "cta", "modo": "seguir", "inicio": {"palavra": "segue"}, "duracao": 3.5, "usuario": "@seuperfil", "texto": "Segue pra *mais*"}
```

## Legendas sincronizadas — `legendas`

Fase: legenda. Aliases: captions, legenda, legenda_automatica, legendas_animadas, subtitles.

Legendas sincronizadas com a fala (usa a transcrição da análise).
estilo: 'destaque' (palavra falada muda de cor e dá um pulinho — karaokê), 'caixa_palavra' (caixa colorida
atrás da palavra falada), 'pop' (palavras surgem uma a uma), 'impacto' (CAIXA ALTA, 1–3 palavras, contorno),
'caixa' (bloco com fundo), 'palavra' (uma palavra por vez, grande), 'minimal' (discreta).
max_palavras (padrão 4; impacto 3), linhas (padrão 2), posicao (padrão: 70% da altura no vertical), tamanho
(64), fonte, cor, cor_destaque, contorno (0; impacto 9), maiusculas, pulo (true: a palavra falada cresce um
pouco), desviar (true: sobe/desce para não bater em cartões, CTAs e prints), fundo_auto (true: caixa escura
quando o fundo atrás é claro), destacar: ['IA', 'Claude'] (sempre na cor de destaque), pontuacao (false =
remove . e ,),
ocultar: [[ini, fim], ...] (esconde nesses intervalos), texto: [{texto, inicio, fim}] (legenda manual quando
não há transcrição). Por padrão cobre o vídeo todo.

```json
{"tipo": "legendas", "estilo": "destaque", "destacar": ["IA", "Claude"]}
```

## Título / texto animado — `titulo`

Fase: sobre. Aliases: chamada_texto, frase, headline, manchete, texto, texto_animado, title.

Texto animado. texto (aceita *cor de destaque*, _ênfase_ na fonte de destaque do estilo, ==etiqueta==
e \n), sobretitulo (rótulo pequeno acima, ex. 'EDIÇÃO AUTOMÁTICA'; sobretitulo_estilo 'pilula' | 'texto'),
subtitulo, icone (opcional no rótulo, ex. 'raio', 'chip'), posicao (sem posição, no vídeo vertical o título
desvia sozinho do rosto e de cartões ativos), tamanho (px em 1080, padrão 96),
fonte ('fonte_titulo' | 'fonte_pesada' | 'fonte_impacto' | nome), cor, alinhamento, largura (0..1),
maiusculas, rastreio (espaço extra entre letras, fração do tamanho), fundo: None | 'cartao' (vidro fosco) |
'faixa' | 'caixa' | 'gradiente' | cor, animacao: 'mascara' (padrão: as palavras sobem de dentro de uma
máscara) | 'desfoque' (palavras surgem do desfoque) | 'palavra' (pop palavra a palavra) | 'revelar' (linha a
linha) | 'digitar' | 'letra' | 'subir' | 'pop' | 'mola' | 'zoom' | 'fade', saida: 'fade' | 'subir' |
'encolher' | 'nenhuma'.

```json
{"tipo": "titulo", "inicio": 0.3, "duracao": 2.8, "texto": "16 efeitos de *edição*", "sobretitulo": "pra testar hoje"}
```

## Zoom (punch-in) — `zoom`

Fase: camera. Aliases: aproximar, punch_in, push_in, zoom_in, zoom_lento, zoom_rapido.

Zoom de câmera no vídeo principal (qualidade máxima, recorta da fonte). intensidade (1.15), tipo: 'suave'
(entra e sai suave), 'seco' (corte direto, estilo jump cut), 'pulso' (batida rápida 1→i→1), 'lento' (aproxima
devagar durante todo o efeito). foco: 'rosto' (padrão) ou {x, y} em 0..1.

```json
{"tipo": "zoom", "inicio": {"palavra": "importante"}, "duracao": 1.5, "intensidade": 1.18}
```

## B-roll / cobertura — `broll`

Fase: cena. Aliases: b_roll, cobertura, corte_para, cutaway, inserir_imagem, inserir_video, mostrar, tela_cheia.

Cobertura em tela cheia (b-roll): mostra outra mídia por cima do vídeo principal, mantendo a voz.
midia (vídeo ou imagem), de (início na mídia), velocidade, enquadrar ('cobrir' | 'ajustar'), movimento (imagens:
'kenburns' | 'zoom_out' | 'pan' | 'nenhum'), transicao ('corte' | 'fade' | 'zoom' | 'deslizar' | 'desfoque'),
audio (volume do som do b-roll, padrão 0), abafar_voz (0..1, reduz a voz durante o b-roll), cor (look).

```json
{"tipo": "broll", "inicio": {"palavra": "praia"}, "duracao": 2.5, "midia": "clip_praia", "transicao": "fade"}
```

## Picture-in-picture — `pip`

Fase: sobre. Aliases: janela, overlay_video, picture_in_picture, sobrepor_video, video_no_canto.

Janela com outra mídia sobre o vídeo (picture-in-picture). midia, de, velocidade, posicao (padrão sup_dir),
largura (0.4), proporcao (altura/largura; padrão a da mídia), forma ('arredondado' | 'circulo'), raio, borda
(cor), audio (volume, padrão 0), rotulo (opcional).

```json
{"tipo": "pip", "inicio": 12.0, "duracao": 4, "midia": "tela_celular", "posicao": "sup_dir", "largura": 0.36}
```

## Lista numerada — `lista`

Fase: sobre. Aliases: itens, lista_numerada, ranking, top, topicos.

Lista numerada que aparece item a item (como '01 Carrossel de elementos ...'). itens (textos ou
{texto, em: tempo}), titulo (opcional), numeros (true), destaque_atual (true: o item mais recente fica em
destaque e os anteriores esmaecem), intervalo (padrão: distribui no tempo), tamanho (46), cartao (true: vidro
fosco), posicao.

```json
{"tipo": "lista", "inicio": 12.0, "duracao": 5, "titulo": "Efeitos", "itens": ["Carrossel", "Tela dividida", "Barra de prompt"]}
```

## Etapas 1-2-3 — `passos`

Fase: sobre. Aliases: etapas, numeros_etapas, progresso_etapas, steps.

Indicador de etapas (círculos 1-2-3 que acendem em sequência) com rótulo da etapa atual.
itens: ['rápido', 'fácil', 'barato'] (ou total: 3), tempos opcionais 'em': [...], posicao (padrão topo),
tamanho (diâmetro, padrão 92), cor_ativa (padrão destaque).

```json
{"tipo": "passos", "inicio": 3.0, "duracao": 3.5, "itens": ["grava", "envia", "pronto"]}
```

## Contador de números — `contador`

Fase: sobre. Aliases: contagem, count_up, estatistica, numero, numero_animado.

Número que conta até o valor (ex. 0 → 100.000). ate (valor final), de (0), prefixo ('R$ ', '+'), sufixo
('%', ' mil'), casas (decimais), rotulo (texto abaixo, em caixa alta espaçada), tamanho (padrão 180), cor
(padrão texto; prefixo/sufixo em letras/%/R$ ficam menores e na cor de destaque), duracao_contagem (1.4s),
posicao.

```json
{"tipo": "contador", "inicio": 5.0, "duracao": 3, "ate": 100000, "prefixo": "+", "rotulo": "visualizações"}
```

## Rodapé com nome (lower third) — `rodape`

Fase: sobre. Aliases: identificacao, legenda_nome, lower_third, nome, terco_inferior.

Identificação estilo 'lower third': nome (forte) + descricao (cargo/@perfil) num cartão de vidro com barra
de cor. posicao (padrão inf_esq), cor_barra (destaque), material ('vidro' | 'solido' | 'claro').

```json
{"tipo": "rodape", "inicio": 1.0, "duracao": 3.5, "nome": "Ana Souza", "descricao": "Estúdio Aurora"}
```

## Círculo / seta / sublinhado — `destaque_area`

Fase: sobre. Aliases: apontar, circular, circulo, highlight, marca_texto, marcar, realce, seta.

Desenha (animado, traço à mão) um círculo, retângulo, sublinhado, marca-texto ou seta apontando para uma área.
forma: 'circulo' | 'retangulo' | 'sublinhado' | 'marca_texto' | 'seta', alvo: {x, y, w, h} (0..1, centro e
tamanho), cor (padrão destaque), espessura (9), texto (rótulo opcional junto da seta), de: 'esquerda'|'direita'|
'cima'|'baixo' (de onde vem a seta).

```json
{"tipo": "destaque_area", "forma": "circulo", "inicio": 6.0, "duracao": 2.0, "alvo": {"x": 0.5, "y": 0.4, "w": 0.4, "h": 0.15}}
```

## Imagem, logo, adesivo, marca d'água — `imagem`

Fase: sobre. Aliases: adesivo, foto, logo, marca_d_agua, marca_dagua, overlay_imagem, print, sobrepor_imagem.

Imagem/print/logo/adesivo sobre o vídeo. imagem (nome em midias ou caminho), posicao, largura (0..1 da tela,
padrão 0.6; logos 0.16), raio (cantos, padrão do estilo), sombra (true), borda (cor), rotacao (graus), flutuar
(true = balanço suave), opacidade. 'marca_dagua': logo pequeno no canto o vídeo todo.

```json
{"tipo": "imagem", "imagem": "logo", "inicio": 2.0, "duracao": 3, "posicao": "sup_esq", "largura": 0.2, "flutuar": true}
```

## Notificação — `notificacao`

Fase: sobre. Aliases: alerta, banner_notificacao, notification, push.

Banner de notificação (estilo celular, vidro fosco) que desce do topo. app (nome), titulo, texto, icone
('sino', 'dinheiro', 'balao', 'carrinho'...), cor_icone (padrão destaque), tempo ('agora'), tema 'escuro' |
'claro'.

```json
{"tipo": "notificacao", "inicio": 7.0, "duracao": 3, "app": "Banco", "titulo": "Pix recebido", "texto": "Você recebeu R$ 1.500,00", "icone": "dinheiro"}
```

## Conversa em bolhas — `mensagens`

Fase: sobre. Aliases: bolhas, chat, conversa, dialogo, mensagem, whats.

Conversa em bolhas (estilo app de mensagens, sem marca) aparecendo uma a uma, com 'digitando...'.
mensagens: [{de: 'eu'|'outro', texto, em?}], posicao (centro), largura (0.86), tamanho (40).

```json
{"tipo": "mensagens", "inicio": 9.0, "duracao": 4, "mensagens": [{"de": "outro", "texto": "Como editou isso?"}, {"de": "eu", "texto": "Com IA"}]}
```

## Barra de progresso — `barra_progresso`

Fase: final. Aliases: barra_de_progresso, progress_bar, progresso.

Barra fina mostrando o progresso do vídeo. posicao 'topo' | 'baixo', cor (destaque), espessura (8).

```json
{"tipo": "barra_progresso", "posicao": "topo"}
```

## Tremor de câmera — `tremor`

Fase: camera. Aliases: impacto_camera, shake, terremoto, tremer.

Tremor de câmera (ênfase/impacto). intensidade em px (padrão 16), frequencia (Hz, padrão 9). Curto: 0.3–0.8s.

```json
{"tipo": "tremor", "inicio": 9.2, "duracao": 0.5}
```

## Flash — `flash`

Fase: final. Aliases: clarao, piscar.

Clarão branco (ou cor) que some rápido — marca batidas/cortes. duracao padrão 0.3s, cor, intensidade.

```json
{"tipo": "flash", "inicio": 9.2}
```

## Glitch — `glitch`

Fase: final. Aliases: distorcao_digital, falha.

Falha digital (separação RGB + fatias deslocadas). Curto (0.2–0.6s). intensidade 0..1.

```json
{"tipo": "glitch", "inicio": 9.2, "duracao": 0.35}
```

## Vinheta — `vinheta`

Fase: final. Aliases: vignette.

Escurece as bordas. intensidade 0..1 (padrão 0.4). Use 'tudo': true para o vídeo todo.

```json
{"tipo": "vinheta", "tudo": true, "intensidade": 0.35}
```

## Vazamento de luz — `vazamento_luz`

Fase: final. Aliases: brilho_cinematico, light_leak, luz.

Mancha de luz quente que atravessa a tela (transições cinematográficas). cor (padrão laranja), duracao 1.2s.

```json
{"tipo": "vazamento_luz", "inicio": 15.0, "duracao": 1.2}
```

## Desfoque de fundo — `desfocar`

Fase: base. Aliases: blur, desfoque, desfoque_fundo.

Desfoca (e opcionalmente escurece) o vídeo por um período — útil atrás de textos grandes.
raio (padrão 18), escurecer 0..1 (padrão 0.25).

```json
{"tipo": "desfocar", "inicio": 3.0, "duracao": 2.5, "raio": 18}
```

