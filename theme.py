"""Світла яскрава тема: кнопки, картки, чипи й дрібні елементи інтерфейсу."""
import os

from kivy.core.text import LabelBase
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
# Шрифт із кирилицею й значками (←, ▶, ↶ …) — замість стандартного для всієї програми
LabelBase.register(name="Roboto", fn_regular=os.path.join(_FONTS, "DejaVuSans.ttf"),
                   fn_bold=os.path.join(_FONTS, "DejaVuSans-Bold.ttf"))

BG = (0.94, 0.96, 1.0, 1)          # світло-блакитне тло
PANEL = (1, 1, 1, 1)
CARD = (1, 1, 1, 1)
CARD_HI = (0.86, 0.9, 1.0, 1)
LINE = (0.84, 0.86, 0.95, 1)        # тонкі обвідки карток
TEXT = (0.14, 0.13, 0.26, 1)
MUTED = (0.45, 0.46, 0.6, 1)
WHITE = (1, 1, 1, 1)
ACCENT = (0.4, 0.38, 1.0, 1)       # синьо-фіолетовий
CYAN = (0.08, 0.7, 0.98, 1)
PINK = (1.0, 0.36, 0.6, 1)
GREEN = (0.16, 0.76, 0.45, 1)
RED = (0.95, 0.3, 0.36, 1)
ORANGE = (1.0, 0.6, 0.12, 1)
YELLOW = (1.0, 0.8, 0.15, 1)
GREY = (0.82, 0.83, 0.9, 1)

_grad_cache = {}


def gradient(c1, c2):
    key = (c1, c2)
    tex = _grad_cache.get(key)
    if tex is None:
        tex = Texture.create(size=(2, 1), colorfmt="rgba")
        buf = bytes(int(v * 255) for v in (c1[0], c1[1], c1[2], 1, c2[0], c2[1], c2[2], 1))
        tex.blit_buffer(buf, colorfmt="rgba", bufferfmt="ubyte")
        tex.mag_filter = "linear"
        tex.min_filter = "linear"
        tex.uvpos = (0.25, 0)
        tex.uvsize = (0.5, 1)
        _grad_cache[key] = tex
    return tex


class RoundButton(Button):
    """Кнопка із заокругленими краями; bg — колір або пара кольорів (градієнт)."""

    def __init__(self, bg=ACCENT, radius=14, outline=None, **kw):
        kw.setdefault("font_size", sp(15))
        self._auto = "color" not in kw
        kw.setdefault("color", text_on(bg))
        if outline is None and _light(bg):
            outline = LINE
        super().__init__(background_normal="", background_down="", background_disabled_normal="",
                         background_disabled_down="", background_color=(0, 0, 0, 0), **kw)
        self._bg = bg
        self._outline = outline
        with self.canvas.before:
            self._col = Color(1, 1, 1, 1)
            self._rr = RoundedRectangle(radius=[dp(radius)])
            self._ocol = Color(0, 0, 0, 0)
            self._oline = Line(width=dp(1.3))
        self._radius = dp(radius)
        self.halign = "center"
        self.valign = "middle"
        self.bind(pos=self._upd, size=self._upd, state=self._upd, disabled=self._upd)
        self.bind(width=lambda w, v: setattr(w, "text_size", (max(1, v - dp(10)), None)))
        self._upd()

    def set_bg(self, bg, outline=None):
        self._bg = bg
        self._outline = outline if outline is not None or not _light(bg) else LINE
        if self._auto:
            self.color = text_on(bg)
        self._upd()

    def _upd(self, *_):
        self._rr.pos, self._rr.size = self.pos, self.size
        k = 0.8 if self.state == "down" else 1.0
        a = 0.35 if self.disabled else 1.0
        if isinstance(self._bg[0], (tuple, list)):
            self._rr.texture = gradient(self._bg[0], self._bg[1])
            self._col.rgba = (k, k, k, a)
        else:
            self._rr.texture = None
            r, g, b, _ = self._bg
            self._col.rgba = (r * k, g * k, b * k, a)
        if self._outline:
            self._ocol.rgba = self._outline
            self._oline.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)
        else:
            self._ocol.rgba = (0, 0, 0, 0)


GRAD = (CYAN, ACCENT)          # кнопки «Завантажити», «Перегляд»
GRAD2 = (ORANGE, PINK)         # головна дія «Створити»
GRAD3 = (GREEN, CYAN)
GRAD4 = (PINK, ACCENT)


def _light(bg):
    if isinstance(bg[0], (tuple, list)):
        return False
    return 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2] > 0.8


def text_on(bg):
    """Колір тексту, який добре видно на цьому тлі."""
    return TEXT if _light(bg) else WHITE


def button(text, bg=ACCENT, **kw):
    kw.setdefault("size_hint_y", None)
    kw.setdefault("height", dp(48))
    return RoundButton(text=text, bg=bg, **kw)


def chip(text, selected=False, **kw):
    kw.setdefault("size_hint", (None, None))
    kw.setdefault("height", dp(38))
    kw.setdefault("font_size", sp(14))
    b = RoundButton(text=text, bg=ACCENT if selected else CARD, radius=19, **kw)
    if "width" not in kw:
        b.texture_update()
        b.width = max(dp(70), b.texture_size[0] + dp(30)) if b.texture_size[0] else dp(90)
        b.text_size = (None, None)
    return b


def set_chip(b, selected):
    b.set_bg(ACCENT if selected else CARD)


def label(text, size=15, bold=False, color=TEXT, **kw):
    lb = Label(text=text, font_size=sp(size), bold=bold, color=color, **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    return lb


def paint(widget, rgba, radius=0, outline=None):
    with widget.canvas.before:
        Color(*rgba)
        rr = RoundedRectangle(radius=[dp(radius)])
        if outline:
            Color(*outline)
            ln = Line(width=dp(1.2))
        else:
            ln = None

    def upd(*_):
        rr.pos, rr.size = widget.pos, widget.size
        if ln is not None:
            ln.rounded_rectangle = (widget.x, widget.y, widget.width, widget.height, dp(radius) or 1)
    widget.bind(pos=upd, size=upd)
    upd()
    return rr


class Card(BoxLayout):
    def __init__(self, bg=CARD, radius=16, **kw):
        super().__init__(**kw)
        paint(self, bg, radius, outline=LINE if _light(bg) else None)
