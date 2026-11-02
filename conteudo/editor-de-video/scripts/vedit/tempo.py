"""Curvas de animação (easing), interpolação e utilidades de tempo."""
import math


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_tupla(a, b, t):
    return tuple(lerp(x, y, t) for x, y in zip(a, b))


def linear(t):
    return t


def entrada(t):  # ease-out cubic (desacelera)
    t = clamp(t)
    return 1 - (1 - t) ** 3


def saida(t):  # ease-in cubic (acelera)
    t = clamp(t)
    return t ** 3


def suave(t):  # ease-in-out cubic
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def expo(t):  # ease-out expo
    t = clamp(t)
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def expo_io(t):
    t = clamp(t)
    if t <= 0 or t >= 1:
        return t
    return 2 ** (20 * t - 10) / 2 if t < 0.5 else (2 - 2 ** (-20 * t + 10)) / 2


def volta(t, s=1.70158):  # ease-out back (passa do ponto e volta)
    t = clamp(t)
    c3 = s + 1
    return 1 + c3 * (t - 1) ** 3 + s * (t - 1) ** 2


def mola(t, amort=0.42, freq=2.6):  # mola amortecida (pop elástico)
    t = clamp(t)
    if t >= 1:
        return 1.0
    w = 2 * math.pi * freq
    return 1 - math.exp(-amort * w * t * 1.6) * math.cos(w * t * math.sqrt(max(1e-6, 1 - amort ** 2)))


def elastico(t):
    t = clamp(t)
    if t <= 0 or t >= 1:
        return t
    c4 = (2 * math.pi) / 3
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * c4) + 1


EASINGS = {
    "linear": linear, "entrada": entrada, "saida": saida, "suave": suave, "expo": expo,
    "expo_io": expo_io, "volta": volta, "mola": mola, "elastico": elastico,
    # aliases em inglês
    "ease_out": entrada, "ease_in": saida, "ease_in_out": suave, "back": volta, "spring": mola,
}


def easing(nome):
    if callable(nome):
        return nome
    return EASINGS.get(str(nome or "entrada"), entrada)


def prog(t, t0, dur, curva="entrada"):
    """Progresso 0..1 de uma animação que começa em t0 e dura dur segundos."""
    if dur <= 0:
        return 1.0 if t >= t0 else 0.0
    return easing(curva)(clamp((t - t0) / dur))


def kf(t, chaves, curva="suave"):
    """Interpola keyframes [(t, valor[, curva]), ...]; valores podem ser números ou tuplas."""
    if not chaves:
        return 0
    if t <= chaves[0][0]:
        return chaves[0][1]
    for i in range(1, len(chaves)):
        t1 = chaves[i][0]
        if t <= t1:
            t0, v0 = chaves[i - 1][0], chaves[i - 1][1]
            v1 = chaves[i][1]
            c = chaves[i][2] if len(chaves[i]) > 2 else curva
            p = easing(c)(clamp((t - t0) / max(1e-9, t1 - t0)))
            if isinstance(v0, (tuple, list)):
                return lerp_tupla(v0, v1, p)
            return lerp(v0, v1, p)
    return chaves[-1][1]


def ruido1d(x, semente=0):
    """Ruído suave determinístico (-1..1) para tremores e flutuações."""
    i = math.floor(x)
    f = x - i

    def h(n):
        n = (n * 374761393 + semente * 668265263) & 0xFFFFFFFF
        n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 0xFFFF) / 32767.5 - 1.0

    u = f * f * (3 - 2 * f)
    return h(i) * (1 - u) + h(i + 1) * u
