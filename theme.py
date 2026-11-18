"""Світла яскрава тема: кнопки з м'якою тінню, картки, чипи, поля вводу й кольорові заголовки."""
import os

from kivy.core.text import LabelBase
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
# Шрифт із кирилицею й значками (←, ▶, ↶ …) — замість стандартного для всієї програми
LabelBase.register(name="Roboto", fn_regular=os.path.join(_FONTS, "DejaVuSans.ttf"),
                   fn_bold=os.path.join(_FONTS, "DejaVuSans-Bold.ttf"))

BG = (0.955, 0.950, 1.0, 1)          # ніжно-бузкове тло
PANEL = (1, 1, 1, 1)
CARD = (1, 1, 1, 1)
CARD_HI = (0.90, 0.88, 1.0, 1)
SOFT = (0.93, 0.91, 1.0, 1)          # світла підкладка (підказки, розбір тексту)
LINE = (0.87, 0.86, 0.97, 1)         # тонкі обвідки карток
TEXT = (0.15, 0.13, 0.30, 1)
MUTED = (0.46, 0.45, 0.62, 1)
WHITE = (1, 1, 1, 1)
ACCENT = (0.42, 0.33, 0.98, 1)       # фіолетовий
VIOLET = (0.62, 0.36, 1.0, 1)
CYAN = (0.10, 0.70, 0.98, 1)
PINK = (1.0, 0.38, 0.62, 1)
GREEN = (0.13, 0.77, 0.50, 1)
RED = (0.95, 0.30, 0.38, 1)
ORANGE = (1.0, 0.58, 0.16, 1)
YELLOW = (1.0, 0.80, 0.18, 1)
GREY = (0.82, 0.83, 0.90, 1)
SHADOW = (0.25, 0.18, 0.55, 0.13)

_grad_cache = {}

from kivy.lang import Builder  # noqa: E402
Builder.load_string("""
<Slider>:
    value_track: True
    value_track_color: 0.42, 0.33, 0.98, 1
    value_track_width: dp(4)
""")


def gradient(c1, c2):
    key = (tuple(c1), tuple(c2))
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


def _is_grad(bg):
    return isinstance(bg[0], (tuple, list))


def _light(bg):
    if _is_grad(bg):
        return False
    return 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2] > 0.8


def text_on(bg):
    """Колір тексту, який добре видно на цьому тлі."""
    return TEXT if _light(bg) else WHITE


class RoundButton(Button):
    """Кнопка із заокругленими краями й легкою тінню; bg — колір або пара кольорів (градієнт)."""

    def __init__(self, bg=ACCENT, radius=16, outline=None, shadow=True, **kw):
        kw.setdefault("font_size", sp(15))
        self._auto = "color" not in kw
        kw.setdefault("color", text_on(bg))
        if outline is None and _light(bg):
            outline = LINE
        kw.setdefault("disabled_color", tuple(kw["color"][:3]) + (0.4,))
        super().__init__(background_normal="", background_down="", background_disabled_normal="",
                         background_disabled_down="", background_color=(0, 0, 0, 0), **kw)
        self._bg = bg
        self._outline = outline
        self._shadow = shadow
        with self.canvas.before:
            self._scol = Color(0, 0, 0, 0)
            self._srr = RoundedRectangle(radius=[dp(radius)])
            self._col = Color(1, 1, 1, 1)
            self._rr = RoundedRectangle(radius=[dp(radius)])
            self._ocol = Color(0, 0, 0, 0)
            self._oline = Line(width=dp(1.2))
        self._radius = dp(radius)
        self.halign = "center"
        self.valign = "middle"
        self.bind(pos=self._upd, size=self._upd, state=self._upd, disabled=self._upd)
        self.bind(width=lambda w, v: setattr(w, "text_size", (max(1, v - dp(12)), None)))
        self._upd()

    def set_bg(self, bg, outline=None):
        self._bg = bg
        self._outline = outline if outline is not None or not _light(bg) else LINE
        if self._auto:
            self.color = text_on(bg)
        self._upd()

    def _upd(self, *_):
        down = self.state == "down"
        off = dp(1) if down else 0
        self._rr.pos, self._rr.size = (self.x, self.y - off), self.size
        k = 0.86 if down else 1.0
        a = 0.35 if self.disabled else 1.0
        if self._shadow and not self.disabled:
            s = SHADOW
            self._scol.rgba = (s[0], s[1], s[2], s[3] * (0.5 if down else 1.0) * (0.7 if _light(self._bg) else 1.0))
            self._srr.pos, self._srr.size = (self.x, self.y - dp(3)), self.size
        else:
            self._scol.rgba = (0, 0, 0, 0)
        if _is_grad(self._bg):
            self._rr.texture = gradient(self._bg[0], self._bg[1])
            self._col.rgba = (k, k, k, a)
        else:
            self._rr.texture = None
            r, g, b, al = self._bg
            self._col.rgba = (r * k, g * k, b * k, a * al)
        if self._outline:
            self._ocol.rgba = self._outline
            self._oline.rounded_rectangle = (self.x, self.y - off, self.width, self.height, self._radius)
        else:
            self._ocol.rgba = (0, 0, 0, 0)


GRAD = (CYAN, ACCENT)          # «Перегляд», «Готові сюжети»
GRAD2 = (ORANGE, PINK)         # головна дія «Створити»
GRAD3 = (GREEN, CYAN)
GRAD4 = (PINK, VIOLET)
GRAD5 = (ACCENT, VIOLET)       # заголовки
GRAD6 = (ORANGE, YELLOW)


def button(text, bg=ACCENT, **kw):
    kw.setdefault("size_hint_y", None)
    kw.setdefault("height", dp(50))
    return RoundButton(text=text, bg=bg, **kw)


def chip(text, selected=False, **kw):
    kw.setdefault("size_hint", (None, None))
    kw.setdefault("height", dp(40))
    kw.setdefault("font_size", sp(14))
    b = RoundButton(text=text, bg=GRAD5 if selected else CARD, radius=20, shadow=False, **kw)
    if "width" not in kw:
        b.texture_update()
        b.width = max(dp(70), b.texture_size[0] + dp(32)) if b.texture_size[0] else dp(90)
        b.text_size = (None, None)
    return b


def set_chip(b, selected):
    b.set_bg(GRAD5 if selected else CARD)


def label(text, size=15, bold=False, color=TEXT, **kw):
    lb = Label(text=text, font_size=sp(size), bold=bold, color=color, **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    return lb


def auto_label(text, size=14, bold=False, color=TEXT, **kw):
    """Підпис, що сам підлаштовує висоту під текст (для довгих пояснень)."""
    kw.setdefault("halign", "left")
    lb = Label(text=text, font_size=sp(size), bold=bold, color=color, size_hint_y=None, valign="top", **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lb.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(4)))
    return lb


def paint(widget, rgba, radius=0, outline=None, shadow=False):
    """Тло віджета: колір або градієнт (пара кольорів), за бажанням — обвідка й тінь."""
    rad = [dp(r) for r in radius] if isinstance(radius, (list, tuple)) else [dp(radius)]
    with widget.canvas.before:
        if shadow:
            sc = Color(*SHADOW)
            srr = RoundedRectangle(radius=rad)
        else:
            sc = srr = None
        if _is_grad(rgba):
            Color(1, 1, 1, 1)
            rr = RoundedRectangle(radius=rad, texture=gradient(rgba[0], rgba[1]))
        else:
            Color(*rgba)
            rr = RoundedRectangle(radius=rad)
        if outline:
            Color(*outline)
            ln = Line(width=dp(1.2))
        else:
            ln = None

    def upd(*_):
        rr.pos, rr.size = widget.pos, widget.size
        if srr is not None:
            srr.pos, srr.size = (widget.x, widget.y - dp(3)), widget.size
        if ln is not None:
            ln.rounded_rectangle = (widget.x, widget.y, widget.width, widget.height, rad[0] or 1)
    widget.bind(pos=upd, size=upd)
    upd()
    return rr


class Card(BoxLayout):
    def __init__(self, bg=CARD, radius=18, shadow=True, **kw):
        super().__init__(**kw)
        paint(self, bg, radius, outline=LINE if _light(bg) else None, shadow=shadow)


class SoftInput(TextInput):
    """Поле вводу: біла заокруглена картка, фіолетова рамка, коли пишеш."""

    def __init__(self, **kw):
        kw.pop("background_color", None)
        kw.setdefault("foreground_color", TEXT)
        kw.setdefault("cursor_color", ACCENT)
        kw.setdefault("hint_text_color", MUTED)
        kw.setdefault("padding", [dp(14), dp(12), dp(14), dp(8)])
        super().__init__(background_normal="", background_active="", background_disabled_normal="",
                         background_color=(0, 0, 0, 0), **kw)
        with self.canvas.before:
            Color(*SHADOW[:3], 0.08)
            self._sh = RoundedRectangle(radius=[dp(14)])
            Color(1, 1, 1, 1)
            self._bg = RoundedRectangle(radius=[dp(14)])
            self._lc = Color(*LINE)
            self._ln = Line(width=dp(1.4))
        self.bind(pos=self._u, size=self._u, focus=self._u)
        self._u()

    def _u(self, *_):
        self._sh.pos, self._sh.size = (self.x, self.y - dp(2)), self.size
        self._bg.pos, self._bg.size = self.pos, self.size
        self._lc.rgba = ACCENT if self.focus else LINE
        self._ln.width = dp(2) if self.focus else dp(1.4)
        self._ln.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(14))


def back_button(on_press, text="‹ Назад", on_dark=False, **kw):
    """Помітна кнопка «Назад» з підписом (замість голої стрілки)."""
    kw.setdefault("size_hint_x", None)
    kw.setdefault("width", dp(100))
    kw.setdefault("height", dp(44))
    kw.setdefault("font_size", sp(16))
    if on_dark:
        b = button(text, (1, 1, 1, 0.22), bold=True, shadow=False, outline=(1, 1, 1, 0.55), **kw)
        b.color = WHITE
    else:
        b = button(text, CARD, bold=True, **kw)
        b.color = ACCENT
        b.disabled_color = tuple(ACCENT[:3]) + (0.4,)
    b.bind(on_release=lambda *_: on_press())
    return b


def done_button(on_press, text="✓ Готово", **kw):
    kw.setdefault("size_hint_x", None)
    kw.setdefault("width", dp(112))
    kw.setdefault("height", dp(44))
    b = button(text, GREEN, font_size=sp(16), bold=True, **kw)
    b.bind(on_release=lambda *_: on_press())
    return b


def header(title, on_back=None, right=None, height=60, sub=None):
    """Кольоровий заголовок (фіолетовий градієнт, заокруглений знизу)."""
    top = BoxLayout(size_hint_y=None, height=dp(height), padding=[dp(10), dp(8), dp(10), dp(8)], spacing=dp(8))
    paint(top, GRAD5, [0, 0, 22, 22], shadow=True)
    if on_back is not None:
        top.add_widget(back_button(on_back, on_dark=True))
    box = BoxLayout(orientation="vertical")
    box.add_widget(label(title, 19, True, color=WHITE, halign="left", valign="middle", shorten=True,
                         max_lines=1))
    if sub:
        box.add_widget(label(sub, 12, color=(1, 1, 1, 0.85), halign="left", valign="top", shorten=True,
                             max_lines=1, size_hint_y=None, height=dp(16)))
    top.add_widget(box)
    for w in (right or []):
        top.add_widget(w)
    return top
