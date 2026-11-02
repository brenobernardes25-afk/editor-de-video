"""Registro de todos os efeitos. Importar este pacote registra cada efeito pelo nome e aliases."""
from .base import ALIASES, FASES, REGISTRO, criar_efeito, normalizar_tipo  # noqa
from . import cor, texto, legendas, ui, cenas, papel  # noqa: F401  (registram efeitos)


def catalogo():
    """[(nome, aliases, fase, doc)] ordenado."""
    inv = {}
    for a, n in ALIASES.items():
        inv.setdefault(n, []).append(a)
    out = []
    for n, cls in sorted(REGISTRO.items()):
        out.append((n, sorted(inv.get(n, [])), cls.fase, (cls.__doc__ or "").strip()))
    return out
