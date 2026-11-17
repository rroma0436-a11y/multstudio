"""Зміна голосу записаної репліки: мультяшний, писклявий, ведмежий, робот, луна.

Працює з numpy-масивом (моно, float, частота RATE) і записує результат у WAV,
який грає і MediaPlayer, і змішувач MP4. Без Kivy — перевіряється на звичайному Python.
"""
import wave

import numpy as np

VOICES = [("normal", "Звичайний"), ("cartoon", "Мультяшний"), ("squeaky", "Писклявий"),
          ("bear", "Ведмежий"), ("giant", "Велетень"), ("robot", "Робот"), ("echo", "Луна")]


def _resample(x, k):
    """Швидше/повільніше разом із висотою: k > 1 — вище й швидше."""
    n = max(1, int(len(x) / k))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def _echo(x, rate, delay=0.18, gain=0.45, times=3):
    d = int(rate * delay)
    out = np.concatenate([x, np.zeros(d * times)])
    for k in range(1, times + 1):
        out[d * k:d * k + len(x)] += x * (gain ** k)
    return out


def process(x, kind, rate):
    x = np.asarray(x, dtype=np.float64)
    if kind == "cartoon":
        y = _resample(x, 1.35)
    elif kind == "squeaky":
        y = _resample(x, 1.7)
    elif kind == "bear":
        y = _resample(x, 0.78)
    elif kind == "giant":
        y = _echo(_resample(x, 0.65), rate, 0.09, 0.3, 2)
    elif kind == "robot":
        t = np.arange(len(x)) / float(rate)
        y = x * (0.55 + 0.45 * np.sign(np.sin(2 * np.pi * 60 * t)))
        y = _echo(y, rate, 0.03, 0.4, 2)
        y = np.round(y / 2048.0) * 2048.0
    elif kind == "echo":
        y = _echo(x, rate)
    else:
        y = x
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 0:
        y = y * min(4.0, 30000.0 / peak)
    return y


def write_wav(path, x, rate):
    data = np.clip(np.asarray(x), -32767, 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    return len(x) / float(rate)
