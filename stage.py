"""Сцена для редагування: фон і елементи, які можна тягнути, масштабувати й обертати двома пальцями.

Режим «start» — розставляємо героїв на початку сцени.
Режим «end»   — куди герої мають дійти до кінця сцени (рух).
"""
import math

from kivy.graphics import Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.stencilview import StencilView
from kivy.uix.widget import Widget

import imgload
from render import flipped_coords

ASPECT = 16 / 9.0
MIN_SCALE, MAX_SCALE = 0.15, 6.0


class Sprite(Widget):
    def __init__(self, item, stage, **kw):
        super().__init__(**kw)
        self.item = item
        self.stage = stage
        self.size_hint = (None, None)
        with self.canvas:
            PushMatrix()
            self.rotate = Rotate(angle=0, origin=(0, 0))
            self.color = Color(1, 1, 1, 1)
            self.rect = Rectangle()
            PopMatrix()
        with self.canvas.after:
            self.sel_color = Color(0.75, 0.55, 1, 0)
            self.sel_line = Line(width=dp(1.4))
        self.reload()
        self.bind(pos=self._redraw, size=self._redraw)

    def state(self):
        """Позиція для поточного режиму сцени."""
        it = self.item
        if self.stage.mode == "end" and it.get("end"):
            e = it["end"]
            return e.get("x", it["x"]), e.get("y", it["y"]), e.get("scale", it.get("scale", 1.0))
        return it["x"], it["y"], it.get("scale", 1.0)

    def reload(self):
        tex = imgload.texture(self.stage.catalog.item_path(self.item))
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
        self.rotate.angle = self.item.get("rot", 0.0)
        self.rotate.origin = self.center
        self.sel_line.rectangle = (self.x - dp(2), self.y - dp(2), self.width + dp(4), self.height + dp(4))


class Stage(StencilView):
    catalog = ObjectProperty(None)
    selected = ObjectProperty(None, allownone=True)
    mode = StringProperty("start")

    __events__ = ("on_change", "on_before_change", "on_double_tap")

    def __init__(self, **kw):
        super().__init__(**kw)
        self.scene = None
        self.project_dir = None      # для фонів-фото з телефону
        self.sprites = []
        self._grab = {}
        self._drag = None
        self._pinch = None
        self._moved = False
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.bg_rect = Rectangle()
        with self.canvas.after:
            self.path_group_color = Color(1, 0.85, 0.3, 0.9)
            self.paths = []
        self.bind(pos=self.layout, size=self.layout, mode=self._mode_changed)

    # ------------------------------------------------------------ сцена
    def load_scene(self, scene):
        """scene — словник сцени з проєкту; редагуємо його напряму."""
        sel_uid = self.selected.item.get("uid") if self.selected is not None else None
        self.clear()
        self.scene = scene
        self.set_background(scene.get("background"))
        for item in scene.get("items", []):
            try:
                sp = self._add_sprite(item)
                if item.get("uid") == sel_uid:
                    self.select(sp)
            except Exception:
                continue
        self.layout()

    def clear(self):
        for s in self.sprites:
            self.remove_widget(s)
        self.sprites = []
        self.select(None)

    def set_background(self, bg_id):
        cat = self.catalog
        path = cat.background_path(bg_id, self.project_dir)
        if path is None:
            bg_id = cat.default_background()
            path = cat.background_path(bg_id)
        if self.scene is not None:
            self.scene["background"] = bg_id
        try:
            self.bg_rect.texture = imgload.cover(imgload.texture(path), 16 / 9.0)
        except Exception:
            self.bg_rect.texture = imgload.texture(cat.background_path(cat.default_background()))

    def _add_sprite(self, item):
        sp = Sprite(item, self)
        self.sprites.append(sp)
        self.add_widget(sp)
        self.place(sp)
        return sp

    def add_item(self, item):
        self.scene["items"].append(item)
        sp = self._add_sprite(item)
        self.select(sp)
        self.layout()
        return sp

    def remove_selected(self):
        sp = self.selected
        if sp is None:
            return
        self.select(None)
        self.sprites.remove(sp)
        self.remove_widget(sp)
        uid = sp.item.get("uid")
        self.scene["items"].remove(sp.item)
        for ln in self.scene.get("dialog", []):
            if ln.get("speaker") == uid:
                ln["speaker"] = None
        self.layout()

    def raise_selected(self, step):
        sp = self.selected
        if sp is None:
            return
        self.scene["auto_depth"] = False
        items = self.scene["items"]
        i = items.index(sp.item)
        j = max(0, min(len(items) - 1, i + step))
        items.insert(j, items.pop(i))
        self.sprites.sort(key=lambda s: items.index(s.item))
        self._restack()

    def _restack(self):
        for s in self.sprites:
            self.remove_widget(s)
        for s in self.sprites:
            self.add_widget(s)

    # ------------------------------------------------------------ геометрія
    def _mode_changed(self, *_):
        self.layout()

    def layout(self, *_):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        for sp in self.sprites:
            self.place(sp)
        if self.scene is not None and self.scene.get("auto_depth", True):
            ys = {s.item.get("uid"): s.state()[1] for s in self.sprites}

            def key(s):
                m = s.item.get("on")
                if m in ys:
                    return -ys[m] + 1e-4          # вершник — поверх свого «коня»
                return -s.state()[1]
            order = sorted(self.sprites, key=key)
            if order != self.sprites:
                self.sprites = order
                self._restack()
        self._draw_paths()

    def place(self, sp):
        x, y, scale = sp.state()
        it = dict(sp.item, scale=scale)
        h = self.catalog.base_height(it) * scale * self.height
        w_px, h_px = self.catalog.item_dims(it)
        w = h * w_px / float(h_px)
        sp.size = (w, h)
        sp.pos = (self.x + x * self.width - w / 2.0, self.y + y * self.height)

    def _draw_paths(self):
        for ins in self.paths:
            self.canvas.after.remove(ins)
        self.paths = []
        if self.scene is None:
            return
        for it in self.scene["items"]:
            e = it.get("end")
            if not e:
                continue
            x0, y0 = self.x + it["x"] * self.width, self.y + it["y"] * self.height
            x1 = self.x + e.get("x", it["x"]) * self.width
            y1 = self.y + e.get("y", it["y"]) * self.height
            ln = Line(points=[x0, y0, x1, y1], width=dp(1.5), dash_length=dp(6), dash_offset=dp(4))
            r = dp(5)
            dot = Ellipse(pos=(x1 - r, y1 - r), size=(2 * r, 2 * r))
            for ins in (ln, dot):
                self.canvas.after.add(ins)
                self.paths.append(ins)

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

    # ------------------------------------------------------------ запис позиції
    def _target(self, sp):
        """Словник, у який пишемо позицію: сам елемент чи його «кінець руху»."""
        it = sp.item
        if self.mode == "end":
            if not it.get("end"):
                it["end"] = {"x": it["x"], "y": it["y"], "scale": it.get("scale", 1.0)}
            return it["end"]
        return it

    # ------------------------------------------------------------ дотики
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if touch.is_mouse_scrolling:
            if self.selected is not None:
                self.dispatch("on_before_change")
                k = 1.08 if touch.button == "scrolldown" else 1 / 1.08
                self.scale_selected(k)
                self.dispatch("on_change")
            return True
        if self._drag is not None and len(self._grab) == 1:
            touch.grab(self)
            self._grab[touch.uid] = touch
            first = next(t for t in self._grab.values() if t is not touch)
            sp = self._drag[0]
            self._pinch = (max(dp(10), self._dist(first, touch)), sp.state()[2],
                           self._angle(first, touch), sp.item.get("rot", 0.0))
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
        self._drag = (sp, touch.x - sp.center_x, touch.y - sp.y)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if self._drag is None:
            return True
        sp = self._drag[0]
        if self._pinch is not None and len(self._grab) >= 2:
            a, b = list(self._grab.values())[:2]
            d0, s0, a0, r0 = self._pinch
            self._set_scale(sp, s0 * self._dist(a, b) / d0)
            if self.mode == "start":
                rot = r0 + self._angle(a, b) - a0
                rot = (rot + 180) % 360 - 180
                if abs(rot) < 4:
                    rot = 0.0
                sp.item["rot"] = rot
            self.place(sp)
            sp._redraw()
            self._moved = True
            return True
        if touch.uid not in self._grab or len(self._grab) > 1:
            return True
        _, dx, dy = self._drag
        tgt = self._target(sp)
        ox, oy = tgt["x"], tgt["y"]
        tgt["x"] = min(1.2, max(-0.2, (touch.x - dx - self.x) / float(self.width)))
        tgt["y"] = min(1.0, max(-0.5, (touch.y - dy - self.y) / float(self.height)))
        self.place(sp)
        # хто сидить на ньому (санчата, кінь, дракон) — рухається разом
        uid = sp.item.get("uid")
        for other in self.sprites:
            if other is not sp and uid and other.item.get("vehicle") == uid:
                ot = self._target(other)
                ot["x"] += tgt["x"] - ox
                ot["y"] += tgt["y"] - oy
                self.place(other)
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
                self.layout()
                self.dispatch("on_change")
            self._drag = None
        else:
            rest = next(iter(self._grab.values()))
            sp = self._drag[0] if self._drag else None
            if sp is not None:
                self._drag = (sp, rest.x - sp.center_x, rest.y - sp.y)
        return True

    @staticmethod
    def _dist(a, b):
        return math.hypot(a.x - b.x, a.y - b.y)

    @staticmethod
    def _angle(a, b):
        return math.degrees(math.atan2(b.y - a.y, b.x - a.x))

    def _set_scale(self, sp, scale):
        tgt = self._target(sp)
        tgt["scale"] = max(MIN_SCALE, min(MAX_SCALE, scale))
        self.place(sp)

    def scale_selected(self, k):
        sp = self.selected
        if sp is not None:
            self._set_scale(sp, sp.state()[2] * k)
            self.layout()

    def clear_motion_selected(self):
        sp = self.selected
        if sp is not None:
            sp.item.pop("end", None)
            self.layout()

    # події
    def on_change(self, *_):
        pass

    def on_before_change(self, *_):
        pass

    def on_double_tap(self, *_):
        pass


class StageHolder(Widget):
    """Тримає сцену 16:9 по центру доступного місця."""

    def __init__(self, stage, bg=(0.07, 0.05, 0.13, 1), **kw):
        super().__init__(**kw)
        self.stage = stage
        self.add_widget(stage)
        with self.canvas.before:
            Color(*bg)
            self._bg = Rectangle()
        self.bind(pos=self._fit, size=self._fit)

    def _fit(self, *_):
        self._bg.pos, self._bg.size = self.pos, self.size
        w, h = self.width, self.height
        if w <= 0 or h <= 0:
            return
        if w / h > ASPECT:
            sw, sh = h * ASPECT, h
        else:
            sw, sh = w, w / ASPECT
        self.stage.size = (sw, sh)
        self.stage.pos = (self.x + (self.width - sw) / 2.0, self.y + (self.height - sh) / 2.0)
