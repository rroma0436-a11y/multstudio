"""Кольори й кнопки програми."""
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.button import Button

BG = (1.0, 0.97, 0.92, 1)        # теплий світлий фон
CARD = (1, 1, 1, 1)
TEXT = (0.18, 0.16, 0.15, 1)
MUTED = (0.45, 0.42, 0.4, 1)
ACCENT = (1.0, 0.54, 0.24, 1)    # помаранчевий
BLUE = (0.31, 0.48, 0.85, 1)
GREEN = (0.24, 0.62, 0.42, 1)
RED = (0.86, 0.3, 0.28, 1)
GREY = (0.6, 0.58, 0.56, 1)
PURPLE = (0.55, 0.4, 0.8, 1)


class RoundButton(Button):
    def __init__(self, bg=ACCENT, radius=12, **kw):
        kw.setdefault("font_size", sp(16))
        kw.setdefault("color", (1, 1, 1, 1))
        super().__init__(background_normal="", background_down="", background_disabled_normal="",
                         background_color=(0, 0, 0, 0), **kw)
        self._base = bg
        with self.canvas.before:
            self._col = Color(*bg)
            self._rr = RoundedRectangle(radius=[dp(radius)])
        self.halign = "center"
        self.valign = "middle"
        self.bind(pos=self._upd, size=self._upd, state=self._upd, disabled=self._upd)
        self.bind(width=lambda w, v: setattr(w, "text_size", (max(1, v - dp(10)), None)))

    def set_bg(self, bg):
        self._base = bg
        self._upd()

    def _upd(self, *_):
        self._rr.pos, self._rr.size = self.pos, self.size
        r, g, b, a = self._base
        if self.disabled:
            self._col.rgba = (r, g, b, 0.35)
        elif self.state == "down":
            self._col.rgba = (r * 0.8, g * 0.8, b * 0.8, a)
        else:
            self._col.rgba = (r, g, b, a)


def button(text, bg=ACCENT, **kw):
    kw.setdefault("size_hint_y", None)
    kw.setdefault("height", dp(48))
    return RoundButton(text=text, bg=bg, **kw)
