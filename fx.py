"""Ефекти частинок (сніг, дощ, блискітки, сердечка …) — розрахунок без Kivy.

particles(вид, час) -> [(текстура, x, y, розмір, кут, (r, g, b, a))]
x, y — частки кадру (0..1, y знизу вгору), розмір — частка висоти кадру.
Положення залежить тільки від часу, тому кадр можна намалювати в будь-який момент
(перемотування, збирання MP4) — і він завжди однаковий.
"""
import math

TEXTURES = ("snow", "dot", "rain", "sparkle", "star", "heart", "bubble", "leaf", "petal", "confetti",
            "firefly")

LEAF_COLORS = [(1.0, 0.55, 0.15), (0.95, 0.35, 0.12), (0.98, 0.78, 0.2), (0.7, 0.4, 0.15)]
CONFETTI_COLORS = [(1, 0.3, 0.4), (0.3, 0.7, 1), (1, 0.85, 0.2), (0.4, 0.9, 0.45), (0.85, 0.45, 1),
                   (1, 0.6, 0.2)]
PETAL_COLORS = [(1, 1, 1), (1, 0.92, 0.95), (1, 0.85, 0.9)]


def rnd(i, k):
    """Псевдовипадкове число 0..1, стале для пари (i, k)."""
    x = math.sin(i * 12.9898 + k * 78.233) * 43758.5453
    return x - math.floor(x)


def _fall(n, t, speed, size, tex, sway=0.02, spin=0.0, colors=None, alpha=1.0, up=False, drift=0.0):
    out = []
    for i in range(n):
        sp = speed * (0.6 + 0.8 * rnd(i, 1))
        y = (rnd(i, 2) + t * sp) % 1.2 - 0.1
        if not up:
            y = 1.1 - y
        x = (rnd(i, 3) + drift * t * (0.5 + rnd(i, 7)) + sway * math.sin(t * (0.8 + rnd(i, 4) * 1.5)
                                                                             + rnd(i, 5) * 6.28)) % 1.0
        s = size * (0.55 + 0.9 * rnd(i, 6))
        rot = (rnd(i, 8) * 360 + spin * t * (rnd(i, 9) - 0.5) * 2) if spin else 0.0
        c = colors[int(rnd(i, 10) * len(colors)) % len(colors)] if colors else (1, 1, 1)
        out.append((tex, x, y, s, rot, (c[0], c[1], c[2], alpha)))
    return out


def _twinkle(n, t, tex, size, period=1.6, colors=None, area=(0.0, 1.0, 0.0, 1.0)):
    out = []
    x0, x1, y0, y1 = area
    for i in range(n):
        ph = rnd(i, 1) * period
        cyc = int((t + ph) / period)
        p = ((t + ph) % period) / period
        a = math.sin(math.pi * p) ** 2
        x = x0 + (x1 - x0) * rnd(i * 31 + cyc, 2)
        y = y0 + (y1 - y0) * rnd(i * 31 + cyc, 3)
        s = size * (0.5 + rnd(i, 4)) * (0.4 + 0.6 * a)
        c = colors[i % len(colors)] if colors else (1, 1, 0.85)
        out.append((tex, x, y, s, p * 90, (c[0], c[1], c[2], a)))
    return out


def particles(kind, t):
    if kind == "snow":
        return (_fall(26, t, 0.07, 0.035, "snow", sway=0.025, spin=60)
                + _fall(40, t + 3, 0.05, 0.018, "dot", sway=0.02, alpha=0.9))
    if kind == "rain":
        return _fall(70, t, 1.4, 0.07, "rain", sway=0.0, alpha=0.6, drift=0.04)
    if kind == "sparkles":
        return _twinkle(28, t, "sparkle", 0.05, colors=[(1, 1, 0.8), (1, 0.9, 1), (0.85, 0.95, 1)])
    if kind == "stars":
        return _twinkle(22, t, "star", 0.045, period=2.2, colors=[(1, 1, 1)])
    if kind == "hearts":
        return _fall(18, t, 0.09, 0.05, "heart", sway=0.04, spin=30, up=True, alpha=0.9)
    if kind == "bubbles":
        return _fall(22, t, 0.1, 0.06, "bubble", sway=0.03, up=True, alpha=0.85)
    if kind == "leaves":
        return _fall(20, t, 0.09, 0.05, "leaf", sway=0.06, spin=160, colors=LEAF_COLORS, drift=0.03)
    if kind == "petals":
        return _fall(24, t, 0.07, 0.035, "petal", sway=0.06, spin=120, colors=PETAL_COLORS, drift=0.04)
    if kind == "confetti":
        return _fall(45, t, 0.16, 0.025, "confetti", sway=0.03, spin=400, colors=CONFETTI_COLORS)
    if kind == "fireflies":
        out = []
        for i in range(18):
            x = (rnd(i, 1) + 0.05 * math.sin(t * (0.3 + rnd(i, 2)) + i)) % 1.0
            y = 0.1 + 0.6 * rnd(i, 3) + 0.05 * math.sin(t * (0.4 + rnd(i, 4)) + 2 * i)
            a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * (1.5 + rnd(i, 5) * 2) + i))
            out.append(("firefly", x, y, 0.04 * (0.7 + 0.6 * rnd(i, 6)), 0.0, (1, 1, 1, a)))
        return out
    return []


def burst(cx, cy, p, size):
    """Іскри чарівної появи навколо героя: p — 1 на початку, 0 у кінці."""
    out = []
    for i in range(12):
        a = i / 12.0 * 6.283 + rnd(i, 1)
        r = size * (0.3 + 0.7 * (1 - p)) * (0.7 + 0.5 * rnd(i, 2))
        out.append(("sparkle", cx + math.cos(a) * r * 0.5625, cy + math.sin(a) * r, 0.04 * (0.5 + p),
                    (1 - p) * 180, (1, 0.95, 0.6, min(1.0, p * 1.6))))
    return out
