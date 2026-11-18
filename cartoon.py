"""Мультяшні написи: товсті різнокольорові літери з обведенням, що «підстрибують», —
як у заголовках старих мультфільмів. Шрифт Ruslan Display (SIL OFL 1.1, див. RuslanDisplay-OFL.txt)."""
import math
import os
import random

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.text import LabelBase
from kivy.graphics import Color, PopMatrix, PushMatrix, Rectangle, Rotate
from kivy.metrics import sp
from kivy.uix.widget import Widget

FONT = "Cartoon"
_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = next((p for p in (os.path.join(_HERE, "RuslanDisplay-Regular.ttf"),
                          os.path.join(_HERE, "fonts", "RuslanDisplay-Regular.ttf")) if os.path.exists(p)),
             os.path.join(_HERE, "RuslanDisplay-Regular.ttf"))
_ok = {"font": None}

PALETTE = [(1.0, 0.84, 0.25, 1), (1.0, 0.47, 0.32, 1), (0.47, 0.80, 1.0, 1), (0.55, 0.90, 0.47, 1),
           (1.0, 0.55, 0.80, 1), (0.80, 0.62, 1.0, 1)]
OUTLINE = (0.17, 0.10, 0.30, 1)


def font():
    if _ok["font"] is None:
        try:
            LabelBase.register(name=FONT, fn_regular=_PATH)
            _ok["font"] = os.path.exists(_PATH)
        except Exception:  # noqa: BLE001
            _ok["font"] = False
    return FONT if _ok["font"] else "Roboto"


def clean(text):
    # у шрифті немає «ʼ» — замінюємо на звичайний апостроф
    return (text or "").replace("ʼ", "'").replace("’", "'")


def _glyph(ch, size, color, outline):
    kw = dict(text=ch, font_name=font(), font_size=size, color=color)
    if outline:
        kw.update(outline_width=max(1, int(size / 14)), outline_color=OUTLINE[:3])
    try:
        lb = CoreLabel(**kw)
        lb.refresh()
    except TypeError:          # старіший рушій тексту без обведення
        kw.pop("outline_width", None)
        kw.pop("outline_color", None)
        lb = CoreLabel(**kw)
        lb.refresh()
    return lb.texture


class CartoonTitle(Widget):
    """Напис мультяшними літерами. bounce — літери легенько гойдаються; intro — «вилітають» по черзі."""

    def __init__(self, text, font_size=None, colors=None, bounce=True, intro=True, seed=None, **kw):
        super().__init__(**kw)
        self.text = clean(text)
        self.fs = font_size or sp(30)
        self.colors = colors or PALETTE
        self.bounce = bounce
        self.t = 0.0 if intro else 10.0
        rnd = random.Random(seed if seed is not None else self.text)
        self.letters = []
        with self.canvas:
            for i, ch in enumerate(self.text):
                if ch == " ":
                    self.letters.append(None)
                    continue
                col = self.colors[i % len(self.colors)]
                tex = _glyph(ch, self.fs, col, True)
                PushMatrix()
                rot = Rotate(angle=0)
                shc = Color(*OUTLINE[:3], 0.35)
                sh = Rectangle(texture=tex, size=tex.size)          # тінь
                c = Color(1, 1, 1, 1)
                r = Rectangle(texture=tex, size=tex.size)
                PopMatrix()
                self.letters.append({"tex": tex, "rot": rot, "sh": sh, "r": r, "c": c, "shc": shc,
                                     "tilt": rnd.uniform(-8, 8), "dy": rnd.uniform(-0.08, 0.08),
                                     "ph": rnd.uniform(0, 6.28)})
        self._ev = None
        self.bind(pos=self._layout, size=self._layout, parent=self._on_parent)
        self._layout()

    @property
    def natural_width(self):
        gap = self.fs * 0.32
        w = 0.0
        for L in self.letters:
            w += gap if L is None else L["tex"].size[0] - self.fs * 0.06
        return w

    def _on_parent(self, *_):
        if self.parent is not None and self._ev is None and (self.bounce or self.t < 2):
            self._ev = Clock.schedule_interval(self._tick, 1 / 30.0)
        elif self.parent is None and self._ev is not None:
            self._ev.cancel()
            self._ev = None

    def _tick(self, dt):
        if self.t > 1.0 and self.get_root_window() is None:     # вікно закрили — більше не малюємо
            if self._ev is not None:
                self._ev.cancel()
                self._ev = None
            return False
        self.t += dt
        self._layout()
        if not self.bounce and self.t > 2.0 and self._ev is not None:
            self._ev.cancel()
            self._ev = None
            return False
        return None

    def _layout(self, *_):
        total = self.natural_width
        k = min(1.0, self.width / total) if total > 0 and self.width > 0 else 1.0
        x = self.center_x - total * k / 2
        gap = self.fs * 0.32 * k
        for i, L in enumerate(self.letters):
            if L is None:
                x += gap
                continue
            tw, th = L["tex"].size
            w, h = tw * k, th * k
            # поява: літери по черзі падають згори й «пружинять»
            u = max(0.0, min(1.0, (self.t - i * 0.05) / 0.45))
            drop = (1 - u) ** 2 * h * 1.2 - math.sin(u * math.pi) * h * 0.12 * (1 - u)
            wob = math.sin(self.t * 2.2 + L["ph"]) * h * 0.035 if self.bounce else 0.0
            y = self.center_y - h / 2 + L["dy"] * h + drop + wob
            L["r"].pos, L["r"].size = (x, y), (w, h)
            L["sh"].pos, L["sh"].size = (x + h * 0.04, y - h * 0.06), (w, h)
            ang = L["tilt"] + (math.sin(self.t * 1.7 + L["ph"]) * 2.5 if self.bounce else 0.0)
            L["rot"].angle = ang
            L["rot"].origin = (x + w / 2, y + h / 2)
            L["c"].a = u
            L["shc"].a = 0.35 * u
            x += w - self.fs * 0.06 * k
