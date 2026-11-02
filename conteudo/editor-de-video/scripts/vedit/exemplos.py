"""Plano de exemplo (documentação viva do formato)."""

PLANO_EXEMPLO = {
    "saida": {"arquivo": "saida/video_editado.mp4", "formato": "9:16", "fps": 30, "qualidade": "alta"},
    "estilo": "pro",
    "midias": {
        "principal": "bruto.mp4",
        "print": "print_noticia.png",
        "musica": "musica.mp3"
    },
    "cortar_silencios": {"silencio_min": 0.45, "margem": 0.12},
    "zoom_alternado": 1.1,
    "correcoes": {"cloud": "Claude"},
    "efeitos": [
        {"tipo": "titulo", "inicio": 0.2, "duracao": 2.6, "texto": "16 efeitos de *edição*",
         "sobretitulo": "pra testar hoje", "posicao": "terco_superior"},
        {"tipo": "zoom", "inicio": {"palavra": "importante"}, "duracao": 1.6, "intensidade": 1.18},
        {"tipo": "tela_dividida", "inicio": 6.0, "duracao": 3.5,
         "paineis": [{"principal": True, "rotulo": "Eu"}, {"midia": "print", "rotulo": "A notícia"}]},
        {"tipo": "barra_prompt", "inicio": 10.0, "duracao": 4.5, "texto": "Edita meu vídeo com legendas e zoom",
         "resposta": "Pronto! Cortei os silêncios e adicionei 6 efeitos."},
        {"tipo": "papel", "inicio": 15.0, "duracao": 4.0, "imagem": "print",
         "destaque": {"x": 0.5, "y": 0.3, "w": 0.8, "h": 0.08}, "zoom_destaque": 1.4},
        {"tipo": "cta", "modo": "seguir", "inicio": {"palavra": "segue"}, "duracao": 3.5, "usuario": "@seuperfil",
         "texto": "Segue pra mais"},
        {"tipo": "legendas", "estilo": "destaque", "destacar": ["IA", "Claude"]}
    ],
    "audio": {"musica": "musica", "volume_musica": 0.15, "ducking": True, "normalizar": True, "sons_auto": True}
}
