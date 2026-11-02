"""Estilos visuais prontos (cores, fontes, materiais, legendas). O plano escolhe um pelo nome ou sobrescreve campos.

O padrão é 'pro': neutro (branco puro + preto), um único acento vivo, cartões de vidro fosco, tipografia de
display apertada nos títulos e legenda larga e pesada — o visual de editor de vídeo profissional de hoje.
"""
import copy

BASE = {
    # cores
    "fundo": "#09090A",         # fundo de cenas geradas
    "fundo2": "#1D1D21",        # luz do gradiente de fundo
    "cartao": "#141416",        # cor dos cartões sólidos
    "cartao_borda": "#FFFFFF24",
    "texto": "#FFFFFF",
    "texto_suave": "#B9B9C0",
    "texto_escuro": "#0B0B0C",  # texto sobre fundos claros
    "destaque": "#FFD60A",      # acento principal (amarelo vivo)
    "destaque2": "#FFFFFF",
    "sucesso": "#30D158",
    "perigo": "#FF453A",
    "papel": "#F7F5F0",
    # cores de interface (imitações de app: botões, bolhas, curtir)
    "ui_azul": "#0A84FF",
    "ui_vermelho": "#FF3040",
    "ui_bolha_eu": "#0A84FF",
    "ui_bolha_outro": "#26262A",
    # materiais
    "material": "vidro",        # vidro | solido | claro | vidro_claro | preto
    "vidro": {"desfoque": 34, "tinta": "#121214", "opacidade": 0.50, "saturacao": 1.35, "borda": 0.20, "brilho": 0.07},
    "sombra": 0.32,             # opacidade das sombras de cartões
    "sombra_texto": [[3, 1, 0.32], [18, 6, 0.42]],  # camadas (raio, dy, opacidade) da sombra de texto
    "raio": 36,                 # raio padrão dos cantos (px em 1080)
    "grao_fundo": 0.012,
    # tipografia
    "fonte_titulo": "InterDisplay-ExtraBold",
    "fonte_texto": "Inter-Medium",
    "fonte_forte": "Inter-SemiBold",
    "fonte_pesada": "InterDisplay-Black",
    "fonte_destaque": "InterDisplay-BlackItalic",   # usada em _palavras_
    "fonte_serif": "Lora-Bold",                      # manchetes do efeito 'papel'
    "fonte_mono": "JetBrainsMono-Bold",
    "fonte_legenda": "MonaSansSemiExpanded-Black",
    "fonte_rotulo": "Inter-Bold",                    # rótulos/etiquetas em caixa alta
    "fonte_impacto": "MonaSansCondensed-Black",      # letras altas (texto vazado, impacto)
    "fonte_ui": "Inter-Medium",                      # imitações de interface
    "fonte_ui_forte": "Inter-SemiBold",
    "marca_solida": True,       # ==marca== vira etiqueta sólida na cor de destaque
    "destaque_fonte": False,    # true: *palavra* também troca para a fonte de destaque (ex. itálico serifado)
    "legenda": {"estilo": "destaque", "maiusculas": False, "tamanho": 64, "contorno": 0, "cor": "#FFFFFF",
                "cor_destaque": None, "caixa": "#000000C2", "altura": 0.70, "pulo": True},
    "transicao_padrao": "corte",
}

ESTILOS = {
    # neutro, acento amarelo, vidro fosco — padrão
    "pro": {},
    # escuro minimalista: tudo branco, sem cor de acento
    "minimal": {
        "destaque": "#FFFFFF", "destaque2": "#D6D6DC", "texto_suave": "#A8A8AF", "marca_solida": True,
        "fonte_titulo": "InterDisplay-Bold", "fonte_legenda": "InterDisplay-Bold",
        "vidro": {"desfoque": 30, "tinta": "#0E0E10", "opacidade": 0.42, "saturacao": 1.2, "borda": 0.16, "brilho": 0.05},
        "legenda": {"estilo": "destaque", "tamanho": 58, "cor": "#FFFFFFB8", "cor_destaque": "#FFFFFF", "pulo": False},
    },
    # retenção (estilo Hormozi): legenda em caixa alta, larga e pesada, contorno preto, amarelo + verde
    "impacto": {
        "fundo": "#050505", "fundo2": "#161616", "cartao": "#0B0B0B", "destaque": "#FFE11A", "destaque2": "#39FF7A",
        "fonte_titulo": "MonaSansExpanded-Black", "fonte_pesada": "MonaSansExpanded-Black",
        "fonte_destaque": "MonaSansExpanded-Black", "fonte_legenda": "MonaSansExpanded-Black", "raio": 26,
        "material": "solido", "sombra_texto": [[2, 2, 0.6], [14, 6, 0.5]],
        "legenda": {"estilo": "impacto", "maiusculas": True, "tamanho": 74, "contorno": 9, "cor": "#FFFFFF"},
    },
    # claro e limpo: cartões brancos, azul — tutoriais, institucional
    "clean": {
        "fundo": "#F2F2F4", "fundo2": "#FFFFFF", "cartao": "#FFFFFF", "destaque": "#0A84FF", "destaque2": "#0B0B0C",
        "material": "claro", "sombra": 0.18, "fonte_titulo": "InterDisplay-Bold", "grao_fundo": 0.006,
        "fonte_legenda": "InterDisplay-Bold",
        "legenda": {"estilo": "caixa", "tamanho": 56, "contorno": 0, "cor": "#FFFFFF", "caixa": "#0B0B0CD9"},
    },
    # cinema: títulos em caixa alta espaçada, legenda discreta, acento branco quente
    "cinema": {
        "fundo": "#070707", "fundo2": "#17150F", "destaque": "#F2E6C9", "destaque2": "#FFFFFF",
        "fonte_titulo": "InterDisplay-SemiBold", "fonte_destaque": "Lora-SemiBoldItalic", "fonte_legenda": "InterDisplay-SemiBold",
        "marca_solida": False, "titulo_maiusculas": True, "titulo_rastreio": 0.12,
        "vidro": {"desfoque": 30, "tinta": "#0A0A0A", "opacidade": 0.40, "saturacao": 1.1, "borda": 0.12, "brilho": 0.04},
        "legenda": {"estilo": "minimal", "tamanho": 46, "cor": "#FFFFFF", "cor_destaque": "#FFFFFF", "pulo": False,
                    "altura": 0.78},
    },
    # tecnologia: azul elétrico, rótulos em mono, caixa na palavra falada
    "tech": {
        "fundo": "#05070B", "fundo2": "#101A2B", "cartao": "#0C111A", "destaque": "#3D8BFF", "destaque2": "#7CF3FF",
        "fonte_rotulo": "JetBrainsMono-Bold", "fonte_legenda": "InterDisplay-Black",
        "vidro": {"desfoque": 34, "tinta": "#0A0F18", "opacidade": 0.55, "saturacao": 1.4, "borda": 0.22, "brilho": 0.07},
        "legenda": {"estilo": "caixa_palavra", "tamanho": 62, "cor": "#FFFFFF"},
    },
    # neon/creator: verde-limão vivo com brilho
    "neon": {
        "fundo": "#050505", "fundo2": "#141A0C", "destaque": "#C6FF3D", "destaque2": "#FFFFFF",
        "fonte_legenda": "MonaSansSemiExpanded-Black", "fonte_titulo": "MonaSansSemiExpanded-Black",
        "legenda": {"estilo": "destaque", "maiusculas": True, "tamanho": 62, "cor": "#FFFFFF", "brilho": True},
    },
    # notícia/urgência: vermelho, letras condensadas, cartões brancos
    "noticia": {
        "fundo": "#0B0B0C", "fundo2": "#1C1C1F", "cartao": "#FFFFFF", "destaque": "#FF2D2D", "destaque2": "#FFD60A",
        "fonte_titulo": "MonaSansCondensed-Black", "fonte_pesada": "MonaSansCondensed-Black", "raio": 14,
        "material": "claro", "fonte_legenda": "InterDisplay-Bold",
        "legenda": {"estilo": "caixa", "tamanho": 58, "contorno": 0, "cor": "#FFFFFF", "caixa": "#D91E1EEB"},
    },
    # editorial/luxo: preto e branco com itálico serifado nos destaques
    "elegante": {
        "destaque": "#FFFFFF", "destaque2": "#E7E2D8", "fonte_titulo": "InterDisplay-Medium",
        "fonte_destaque": "Lora-SemiBoldItalic", "fonte_legenda": "InterDisplay-SemiBold", "marca_solida": False,
        "destaque_fonte": True, "escala_destaque": 1.12,
        "legenda": {"estilo": "destaque", "tamanho": 56, "cor": "#FFFFFFB0", "cor_destaque": "#FFFFFF", "pulo": False},
    },
    # quente/lifestyle: âmbar, serifa
    "terroso": {
        "fundo": "#120F0C", "fundo2": "#2A2219", "cartao": "#1C1712", "destaque": "#F0B35A", "destaque2": "#F7EFE3",
        "texto": "#FFF9F0", "fonte_titulo": "Lora-Bold", "fonte_destaque": "Lora-SemiBoldItalic", "marca_solida": False,
        "vidro": {"desfoque": 32, "tinta": "#17120D", "opacidade": 0.5, "saturacao": 1.2, "borda": 0.16, "brilho": 0.05},
    },
    # finanças/vendas: verde dinheiro
    "dinheiro": {
        "fundo": "#06100B", "fundo2": "#0F2418", "cartao": "#0C1A13", "destaque": "#2EE59D", "destaque2": "#FFD166",
        "fonte_legenda": "MonaSansSemiExpanded-Black",
        "vidro": {"desfoque": 34, "tinta": "#08140E", "opacidade": 0.52, "saturacao": 1.3, "borda": 0.2, "brilho": 0.06},
    },
}

ALIAS_ESTILO = {
    "padrao": "pro", "default": "pro", "premium": "pro", "profissional": "pro", "moderno": "pro", "editor": "pro",
    "minimalista": "minimal", "minimo": "minimal", "simples": "minimal",
    "hormozi": "impacto", "retencao": "impacto", "viral": "impacto", "agressivo": "impacto",
    "claro": "clean", "limpo": "clean", "branco": "clean", "light": "clean", "tutorial": "clean",
    "cinematografico": "cinema", "filme": "cinema", "documentario": "cinema",
    "tecnologia": "tech", "ia": "tech", "azul": "tech",
    "creator": "neon", "gamer": "neon", "games": "neon",
    "jornal": "noticia", "urgente": "noticia", "news": "noticia",
    "luxo": "elegante", "editorial": "elegante", "serifa": "elegante", "classico": "elegante",
    "quente": "terroso", "lifestyle": "terroso", "gastronomia": "terroso",
    "financas": "dinheiro", "vendas": "dinheiro", "money": "dinheiro",
}

DESCRICOES = {
    "pro": "padrão — neutro, acento amarelo, vidro fosco, títulos Inter Display, legenda larga e pesada",
    "minimal": "tudo branco, sem cor de acento, legenda discreta",
    "impacto": "retenção (Hormozi): legenda em CAIXA ALTA com contorno, amarelo e verde",
    "clean": "claro: cartões brancos, azul, legenda em caixa escura — tutoriais",
    "cinema": "títulos em caixa alta espaçada, legenda pequena, tom de filme (combine com color_grade 'cinema')",
    "tech": "azul elétrico, rótulos em mono, caixa na palavra falada",
    "neon": "verde-limão vivo com brilho — creator, games",
    "noticia": "vermelho, letras condensadas, cartões brancos — notícia, urgência",
    "elegante": "preto e branco com itálico serifado nos destaques — luxo, editorial",
    "terroso": "âmbar quente com serifa — lifestyle, gastronomia",
    "dinheiro": "verde dinheiro — finanças, vendas",
}


def mesclar(a, b):
    r = copy.deepcopy(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(r.get(k), dict):
            r[k] = mesclar(r[k], v)
        else:
            r[k] = v
    return r


def nome_estilo(nome):
    n = str(nome or "pro").strip().lower()
    try:
        from .util import sem_acento
        n = sem_acento(n)
    except Exception:
        pass
    n = n.replace(" ", "_").replace("-", "_")
    return ALIAS_ESTILO.get(n, n)


def montar_estilo(spec):
    """spec: nome (str), dict {"base": nome, ...overrides} ou None."""
    nome, extra = "pro", {}
    if isinstance(spec, str):
        nome = spec
    elif isinstance(spec, dict):
        nome = spec.get("base", spec.get("nome", "pro"))
        extra = {k: v for k, v in spec.items() if k not in ("base", "nome")}
    nome = nome_estilo(nome)
    if nome not in ESTILOS:
        try:
            from .util import aviso
            aviso("estilo '%s' não existe — usando 'pro'. Estilos: %s" % (nome, ", ".join(ESTILOS)))
        except Exception:
            pass
        nome = "pro"
    e = mesclar(BASE, ESTILOS[nome])
    e = mesclar(e, extra)
    e["nome"] = nome
    return e
