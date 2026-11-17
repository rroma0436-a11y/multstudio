"""Сцена: фон і елементи (герої, предмети), які можна перетягувати й масштабувати двома пальцями."""
import math

from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.properties import ObjectProperty
from kivy.uix.stencilview import StencilView
from kivy.uix.widget import Widget

import imgload

ASPECT = 16 / 9.0
MIN_SCALE, MAX_SCALE = 0.15, 6.0


def flipped_coords(tc):
    """Дзеркалить tex_coords по горизонталі (порядок: низ-ліво, низ-право, верх-право, верх-ліво)."""
    u0, v0, u1, v1, u2, v2, u3, v3 = tc
    return (u1, v1, u0, v0, u3, v3, u2, v2)


class Sprite(Widget):
    def __init__(self, item, catalog, **kw):
        super().__init__(**kw)
        self.item = item
        self.catalog = catalog
        self.size_hint = (None, None)
        with self.canvas:
            Color(1, 1, 1, 1)
            self.rect = Rectangle()
        with self.canvas.after:
            self.sel_color = Color(1, 0.45, 0.1, 0)
            self.sel_line = Line(width=dp(1.4))
        self.reload()
        self.bind(pos=self._redraw, size=self._redraw)

    def reload(self):
        tex = imgload.texture(self.catalog.item_path(self.item))
        self.rect.texture = tex
        self.apply_flip()

    def apply_flip(self):
        tex = self.rect.texture
        if tex is None:
            return
        tc = tuple(tex.tex_coords)
        self.rect.tex_coords = flipped_coords(tc) if self.item.get("flip") else tc

    def set_selected(self, on):
        self.sel_color.a = 1 if on else 0

    def _redraw(self, *_):
        self.rect.pos = self.pos
        self.rect.size = self.size
        self.sel_line.rectangle = (self.x - dp(2), self.y - dp(2), self.width + dp(4), self.height + dp(4))


class Stage(StencilView):
    """Сцена завжди 16:9; координати елементів — частки ширини/висоти сцени.

    item["x"] — центр по горизонталі, item["y"] — низ (ноги) по вертикалі.
    """
    catalog = ObjectProperty(None)
    selected = ObjectProperty(None, allownone=True)

    __events__ = ("on_change", "on_before_change", "on_double_tap")

    def __init__(self, **kw):
        super().__init__(**kw)
        self.background = None
        self.sprites = []
        self._grab = {}          # uid -> touch
        self._drag = None        # (sprite, dx, dy)
        self._pinch = None       # (d0, scale0)
        self._moved = False
        with self.canvas.before:
            Color(0.85, 0.88, 0.9, 1)
            self.bg_rect = Rectangle()
        self.bind(pos=self.layout, size=self.layout)

    # ------------------------------------------------------------ сцена
    def load_scene(self, scene):
        self.clear()
        self.set_background(scene.get("background"))
        for item in scene.get("items", []):
            try:
                self._add_sprite(dict(item))
            except Exception:
                continue  # пропускаємо елементи, яких уже немає в каталозі
        self.layout()

    def scene(self):
        return {"background": self.background, "items": [dict(s.item) for s in self.sprites]}

    def clear(self):
        for s in self.sprites:
            self.remove_widget(s)
        self.sprites = []
        self.select(None)

    def set_background(self, bg_id):
        if bg_id not in self.catalog.backgrounds:
            bg_id = self.catalog.default_background()
        self.background = bg_id
        path = self.catalog.abspath(self.catalog.backgrounds[bg_id]["path"])
        self.bg_rect.texture = imgload.texture(path)

    def _add_sprite(self, item):
        sp = Sprite(item, self.catalog)
        self.sprites.append(sp)
        self.add_widget(sp)
        self.place(sp)
        return sp

    def add_item(self, item):
        sp = self._add_sprite(item)
        self.select(sp)
        return sp

    def remove_selected(self):
        sp = self.selected
        if sp is None:
            return
        self.select(None)
        self.sprites.remove(sp)
        self.remove_widget(sp)

    def raise_selected(self, step):
        sp = self.selected
        if sp is None:
            return
        i = self.sprites.index(sp)
        j = max(0, min(len(self.sprites) - 1, i + step))
        if i == j:
            return
        self.sprites.insert(j, self.sprites.pop(i))
        for s in self.sprites:
            self.remove_widget(s)
        for s in self.sprites:
            self.add_widget(s)

    # ------------------------------------------------------------ геометрія
    def layout(self, *_):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        for sp in self.sprites:
            self.place(sp)

    def place(self, sp):
        it = sp.item
        h = self.catalog.base_height(it) * it.get("scale", 1.0) * self.height
        w_px, h_px = self.catalog.item_dims(it)
        w = h * w_px / float(h_px)
        sp.size = (w, h)
        sp.pos = (self.x + it["x"] * self.width - w / 2.0, self.y + it["y"] * self.height)

    def select(self, sp):
        if self.selected is not None:
            self.selected.set_selected(False)
        self.selected = sp
        if sp is not None:
            sp.set_selected(True)

    def hit(self, x, y):
        for sp in reversed(self.sprites):
            if sp.collide_point(x, y):
                return sp
        return None

    # ------------------------------------------------------------ дотики
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if touch.is_mouse_scrolling:
            if self.selected is not None:
                self.dispatch("on_before_change")
                k = 1.08 if touch.button == "scrolldown" else 1 / 1.08
                self._set_scale(self.selected, self.selected.item.get("scale", 1.0) * k)
                self.dispatch("on_change")
            return True
        # другий палець — масштабування вибраного елемента
        if self._drag is not None and len(self._grab) == 1:
            touch.grab(self)
            self._grab[touch.uid] = touch
            first = next(t for t in self._grab.values() if t is not touch)
            self._pinch = (max(dp(10), self._dist(first, touch)), self._drag[0].item.get("scale", 1.0))
            return True
        sp = self.hit(*touch.pos)
        self.select(sp)
        if sp is None:
            return True
        if touch.is_double_tap:
            self.dispatch("on_double_tap", sp)
            return True
        self.dispatch("on_before_change")
        touch.grab(self)
        self._grab[touch.uid] = touch
        self._moved = False
        self._drag = (sp, touch.x - (sp.center_x), touch.y - sp.y)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if self._drag is None:
            return True
        sp = self._drag[0]
        if self._pinch is not None and len(self._grab) >= 2:
            a, b = list(self._grab.values())[:2]
            d0, s0 = self._pinch
            self._set_scale(sp, s0 * self._dist(a, b) / d0)
            self._moved = True
            return True
        if touch.uid not in self._grab or len(self._grab) > 1:
            return True
        _, dx, dy = self._drag
        it = sp.item
        it["x"] = min(1.2, max(-0.2, (touch.x - dx - self.x) / float(self.width)))
        it["y"] = min(1.0, max(-0.5, (touch.y - dy - self.y) / float(self.height)))
        self.place(sp)
        self._moved = True
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        self._grab.pop(touch.uid, None)
        if len(self._grab) < 2:
            self._pinch = None
        if not self._grab:
            if self._drag is not None and self._moved:
                self.dispatch("on_change")
            self._drag = None
        else:
            # залишився один палець — продовжуємо тягнути від нього
            rest = next(iter(self._grab.values()))
            sp = self._drag[0] if self._drag else None
            if sp is not None:
                self._drag = (sp, rest.x - sp.center_x, rest.y - sp.y)
        return True

    @staticmethod
    def _dist(a, b):
        return math.hypot(a.x - b.x, a.y - b.y)

    def _set_scale(self, sp, scale):
        sp.item["scale"] = max(MIN_SCALE, min(MAX_SCALE, scale))
        self.place(sp)

    def scale_selected(self, k):
        if self.selected is not None:
            self._set_scale(self.selected, self.selected.item.get("scale", 1.0) * k)

    # ------------------------------------------------------------ знімок
    def export_png(self, path, width=1920):
        sel = self.selected
        if sel is not None:
            sel.set_selected(False)
        try:
            img = self.export_as_image(scale=width / float(self.width))
            img.save(path, flipped=False)
        finally:
            if sel is not None:
                sel.set_selected(True)

    # події
    def on_change(self, *_):
        pass

    def on_before_change(self, *_):
        pass

    def on_double_tap(self, *_):
        pass


class StageHolder(Widget):
    """Тримає сцену 16:9 по центру доступного місця."""

    def __init__(self, stage, **kw):
        super().__init__(**kw)
        self.stage = stage
        self.add_widget(stage)
        with self.canvas.before:
            Color(0.16, 0.15, 0.2, 1)
            self._bg = Rectangle()
        self.bind(pos=self._fit, size=self._fit)

    def _fit(self, *_):
        self._bg.pos, self._bg.size = self.pos, self.size
        pad = dp(6)
        w, h = self.width - 2 * pad, self.height - 2 * pad
        if w <= 0 or h <= 0:
            return
        if w / h > ASPECT:
            sw, sh = h * ASPECT, h
        else:
            sw, sh = w, w / ASPECT
        self.stage.size = (sw, sh)
        self.stage.pos = (self.x + (self.width - sw) / 2.0, self.y + (self.height - sh) / 2.0)
