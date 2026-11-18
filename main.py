"""Мультстудія — конструктор мультиків: герої, фони й пори року, репліки й голос,
рух і камера, збирання MP4 на телефоні без інтернету.
"""
import math
import os
import time

import theme  # першим: реєструє шрифт зі значками
from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate, RoundedRectangle,
                           Scale, Translate, Triangle)
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.logger import Logger
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

import android_bridge as bridge
import imgload
import model
from data import Catalog, SoundLib
from editor import EditorScreen, chip_wrap, modal, scroll_column, section as section_label
from picker import Picker, ThumbGrid
from player import PlayerScreen
from projects import ProjectStore

APP_TITLE = "Мультстудія"
APP_VERSION = "6.0"

if platform != "android":
    Window.size = (430, 900)
Window.clearcolor = theme.BG


# ====================================================================== головна
def short_name(c):
    """Коротке ім'я для підписів: без уточнення в дужках."""
    if c.get("id") == "helper_bot":
        return "Робот Біп"
    return c["name"].split("(")[0].strip()


class Showcase(Widget):
    """Песик на головній: дихає, сам час від часу щось робить, а від дотику — стрибає, крутиться,
    гавкає, радіє, сідає… (ті самі дії й кадри, що й у мультиках)."""
    TAPS = [("jump", "Гоп!"), ("bark", "Гав-гав!"), ("spin", "Кручуся!"), ("happy", "Ура!"), ("sit", "Сиджу!"),
            ("stand", ""), ("paw", "Тримай лапу!"), ("run", "Біжу!"), ("shake", ""), ("surprised", "Ого!"),
            ("walk", "Гуляю…"), ("play", "Пограймося!"), ("lie", "Відпочину…"), ("stand", ""), ("dance", "Танцюю!")]
    IDLE = ["Привіт! Я песик.\nТоркнись мене!", "Зробімо мультик!", "Гав! Є готові сюжети!",
            "Оживи своє фото!", "Торкнись — я щось покажу!"]

    def __init__(self, catalog, **kw):
        super().__init__(**kw)
        import acts as acts_mod
        self.acts = acts_mod
        self.cat = catalog
        stars = catalog.stars
        self.char = stars[0] if stars else None
        self.item = None
        if self.char is not None:
            fr = "side_calm" if "side_calm" in self.char["frames"] else catalog.default_frame(self.char["id"])
            self.item = {"kind": "char", "id": self.char["id"], "frame": fr, "x": 0.5, "y": 0.0, "scale": 1.0,
                         "flip": False, "uid": "show", "acts": [], "anim": "alive"}
        self.t = 0.0
        self.act = None
        self.act_t0 = 0.0
        self.tap_i = 0
        self.idle_i = 0
        self.next_idle = 4.0
        with self.canvas.before:
            Color(0.8, 0.91, 1, 1)
            self.sky = Ellipse()
            Color(1, 0.93, 0.55, 0.9)
            self.sun = Ellipse()
            Color(0.6, 0.86, 0.52, 1)
            self.hill = Ellipse()
            Color(1, 0.64, 0.32, 1)
            self.pod_side = Ellipse()
            Color(1, 0.82, 0.42, 1)
            self.pod_top = Ellipse()
            PushMatrix()
            self.tr = Translate()
            self.rot = Rotate()
            self.sc = Scale()
            Color(1, 1, 1, 1)
            self.rect = Rectangle()
            PopMatrix()
            Color(0.4, 0.38, 1, 1)
            self.b_line = Line(width=dp(1.4))
            Color(1, 1, 1, 1)
            self.b_rect = RoundedRectangle(radius=[dp(16)])
            self.b_tip = Triangle()
        self.name = Label(text=short_name(self.char) if self.char else "", font_size=sp(14), bold=True,
                          color=theme.TEXT, halign="center", valign="middle")
        self.add_widget(self.name)
        self.bubble = Label(text=self.IDLE[0], font_size=sp(15), bold=True, color=theme.TEXT,
                            halign="center", valign="middle")
        self.add_widget(self.bubble)
        self._ev = None
        self.bind(pos=self.layout, size=self.layout)

    def start(self):
        if self._ev is None:
            self._ev = Clock.schedule_interval(self.tick, 1 / 30.0)

    def stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None

    def on_touch_up(self, touch):
        if not self.collide_point(*touch.pos) or self.item is None:
            return super().on_touch_up(touch)
        if abs(touch.x - touch.ox) > dp(12) or abs(touch.y - touch.oy) > dp(12):
            return False
        key, text = self.TAPS[self.tap_i % len(self.TAPS)]
        self.tap_i += 1
        self.play(key, text)
        return True

    def play(self, key, text=""):
        self._finish()
        a = self.acts.new_act(key)
        if key in ("bark", "talk"):
            a["text"] = text
        self.item["acts"] = [a]
        self.act = key
        self.act_t0 = self.t
        if text:
            self.bubble.text = text
        self.next_idle = self.t + 6.0

    def _finish(self):
        """Дія скінчилась — песик лишається в тій позі, у яку перейшов."""
        it = self.item
        if it and it.get("acts"):
            segs, _end = self.acts.plan(it, self.char)
            pose = self.acts.start_pose(it)
            for _t0, _t1, key, kind, act in segs:
                if kind == "trans":
                    pose = act["to"]
                elif self.acts.ACTIONS[key][4]:
                    pose = self.acts.ACTIONS[key][4]
            fr = self.acts.POSE_FRAME[pose]
            if fr in self.char["frames"]:
                it["frame"] = fr
            it["acts"] = []
        self.act = None

    def tick(self, dt):
        self.t += min(dt, 0.1)
        if self.act is not None:
            if self.t - self.act_t0 > self.acts.total(self.item, self.char) + 0.2:
                self._finish()
        elif self.t >= self.next_idle and self.item is not None:
            self.idle_i += 1
            self.bubble.text = self.IDLE[self.idle_i % len(self.IDLE)]
            if self.idle_i % 2 == 0:
                key, text = self.TAPS[(self.idle_i * 3) % len(self.TAPS)]
                if key not in ("lie", "sit", "walk", "run"):
                    self.play(key, text)
            self.next_idle = self.t + 5.0
        self.layout()

    def layout(self, *_):
        x, y, w, h = self.x, self.y, self.width, self.height
        self.sky.pos, self.sky.size = (x + w * 0.04, y + h * 0.06), (w * 0.92, h * 0.9)
        self.sun.pos, self.sun.size = (x + w * 0.74, y + h * 0.62), (h * 0.2, h * 0.2)
        self.hill.pos, self.hill.size = (x, y + h * 0.05), (w, h * 0.32)
        self.pod_side.pos, self.pod_side.size = (x + w * 0.08, y + h * 0.04), (w * 0.84, h * 0.17)
        self.pod_top.pos, self.pod_top.size = (x + w * 0.1, y + h * 0.09), (w * 0.8, h * 0.13)
        self.name.size = (w * 0.5, dp(20))
        self.name.text_size = self.name.size
        self.name.center = (x + w / 2, y + h * 0.075)
        if self.item is None:
            return
        it, char, cat = self.item, self.char, self.cat
        u = self.t - self.act_t0 + model.MOVE_MARGIN if self.act else self.t
        scene = {"items": [it], "dialog": []}
        st = model.item_state(it, scene, u, 99.0, char, None)
        frame = st["frame"] if st["frame"] in char["frames"] else it["frame"]
        try:
            tex = imgload.texture(cat.abspath(char["frames"][frame]))
        except Exception:
            return
        ref = cat.base_height(dict(it, frame="side_calm" if "side_calm" in char["frames"] else frame))
        hh = h * 0.42 * cat.base_height(dict(it, frame=frame)) / max(0.01, ref)
        dw, dh = cat.item_dims(dict(it, frame=frame))
        ww = hh * dw / float(dh)
        cx, base = x + w / 2, y + h * 0.15 + st["dy"] * h * 1.6
        tc = tuple(tex.tex_coords)
        if st["flip"]:
            from render import flipped_coords
            tc = flipped_coords(tc)
        self.rect.texture = tex
        self.rect.tex_coords = tc
        self.rect.pos, self.rect.size = (-ww / 2, 0), (ww, hh)
        self.tr.xy = (cx + st["dx"] * w, base)
        self.rot.angle = st["rot"]
        self.rot.origin = (0, hh / 2)
        self.sc.xyz = (st["sx"], st["sy"], 1)
        head = (cx + ww * 0.25 * (-1 if st["flip"] else 1), base + hh * 0.95)
        self.bubble.texture_update()
        bw, bh = self.bubble.texture_size[0] + dp(26), self.bubble.texture_size[1] + dp(16)
        bx = min(max(x + dp(4), head[0] - bw / 2), x + w - bw - dp(4))
        by = min(head[1] + dp(12), y + h - bh - dp(4))
        self.b_rect.pos, self.b_rect.size = (bx, by), (bw, bh)
        tx = min(max(bx + dp(20), head[0]), bx + bw - dp(20))
        self.b_tip.points = [tx - dp(9), by + 1, tx + dp(9), by + 1, head[0], by - dp(10)]
        self.b_line.rounded_rectangle = (bx - dp(1), by - dp(1), bw + dp(2), bh + dp(2), dp(16))
        self.bubble.size = (bw, bh)
        self.bubble.pos = (bx, by)


class TemplateCard(ButtonBehavior, BoxLayout):
    """Картка готового сюжету: кадр із мультика, назва й опис."""

    def __init__(self, icon, title, desc, **kw):
        super().__init__(size_hint_y=None, height=dp(112), padding=dp(8), spacing=dp(10), **kw)
        theme.paint(self, theme.CARD, 18, outline=theme.LINE, shadow=True)
        self.img = Image(source="", fit_mode="cover", size_hint_x=None, width=dp(170), nocache=True)
        self.add_widget(self.img)
        box = BoxLayout(orientation="vertical", spacing=dp(2))
        box.add_widget(theme.label(f"{icon}  {title}", 16, True, color=theme.ACCENT, size_hint_y=None,
                                   height=dp(28), halign="left", valign="middle", shorten=True))
        box.add_widget(theme.label(desc, 13, color=theme.MUTED, halign="left", valign="top"))
        self.add_widget(box)


class BigAction(ButtonBehavior, BoxLayout):
    """Велика кольорова картка-дія на головній: значок у кружечку, назва, підпис, мітка («ШІ»)."""

    def __init__(self, icon, title, sub, grad, badge=None, **kw):
        super().__init__(orientation="vertical", padding=[dp(12), dp(8), dp(12), dp(8)], spacing=dp(1), **kw)
        btex = None
        if badge:
            from kivy.core.text import Label as CoreLabel
            cl = CoreLabel(text=badge, font_size=sp(11), bold=True, color=tuple(grad[1][:3]) + (1,))
            cl.refresh()
            btex = cl.texture
        with self.canvas.before:
            Color(*theme.SHADOW)
            self._sh = RoundedRectangle(radius=[dp(22)])
            self._c = Color(1, 1, 1, 1)
            self._rr = RoundedRectangle(radius=[dp(22)], texture=theme.gradient(*grad))
            Color(1, 1, 1, 0.25)
            self._ic = Ellipse()
        with self.canvas.after:
            Color(1, 1, 1, 0.95 if btex is not None else 0)
            self._badge = RoundedRectangle(radius=[dp(10)])
            Color(1, 1, 1, 1 if btex is not None else 0)
            self._btex = Rectangle(texture=btex, size=tuple(btex.size) if btex is not None else (0, 0))
        self.bind(pos=self._u, size=self._u, state=self._u)
        self.add_widget(Label(text=icon, font_size=sp(24), color=theme.WHITE, size_hint_y=None, height=dp(42)))
        self.add_widget(Label(text=title, font_size=sp(16), bold=True, color=theme.WHITE, size_hint_y=None,
                              height=dp(24)))
        lb = Label(text=sub, font_size=sp(12), color=(1, 1, 1, 0.93), halign="center", valign="top")
        lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        self.add_widget(lb)
        self._u()

    def _u(self, *_):
        down = self.state == "down"
        off = dp(1.5) if down else 0
        self._rr.pos, self._rr.size = (self.x, self.y - off), self.size
        self._sh.pos, self._sh.size = (self.x, self.y - dp(4)), self.size
        k = 0.88 if down else 1.0
        self._c.rgba = (k, k, k, 1)
        d = dp(40)
        self._ic.pos, self._ic.size = (self.center_x - d / 2, self.top - dp(9) - d - off), (d, d)
        bw, bh = dp(36), dp(20)
        self._badge.pos, self._badge.size = (self.right - bw - dp(8), self.top - bh - dp(8)), (bw, bh)
        tw, th = self._btex.size
        self._btex.pos = (self._badge.pos[0] + (bw - tw) / 2, self._badge.pos[1] + (bh - th) / 2)


class HeroCard(ButtonBehavior, BoxLayout):
    def __init__(self, char, catalog, **kw):
        super().__init__(orientation="vertical", size_hint=(None, 1), width=dp(104), padding=dp(4),
                         spacing=dp(2), **kw)
        self.char = char
        theme.paint(self, theme.CARD, 14, outline=theme.LINE)
        self.add_widget(Image(source=catalog.abspath(char["thumb"]), fit_mode="contain"))
        self.add_widget(theme.label(short_name(char), 12, size_hint_y=None, height=dp(28), halign="center",
                                    shorten=True, max_lines=2))


class NavBar(BoxLayout):
    def __init__(self, app, current, **kw):
        super().__init__(size_hint_y=None, height=dp(64), padding=[dp(10), dp(8)], spacing=dp(8), **kw)
        theme.paint(self, theme.PANEL, [22, 22, 0, 0], shadow=False)
        with self.canvas.before:
            Color(*theme.SHADOW[:3], 0.10)
            self._ln = Rectangle()
        self.bind(pos=self._u, size=self._u)
        for key, icon, text in (("catalog", "▦", "Герої"), ("create", "✚", "Створення"),
                                ("library", "▤", "Мої мультики")):
            on = key == current
            b = theme.RoundButton(text=f"{icon}\n{text}", bg=theme.GRAD5 if on else theme.PANEL, font_size=sp(12),
                                  color=theme.WHITE if on else theme.MUTED, outline=(0, 0, 0, 0), shadow=on,
                                  radius=18, bold=on)
            b.bind(on_release=lambda _b, k=key: app.nav(k))
            self.add_widget(b)

    def _u(self, *_):
        self._ln.pos, self._ln.size = (self.x, self.top), (self.width, dp(2))


# кнопки під 3D-песиком: (ключ дії, підпис)
ACTION_CHIPS = [("bark", "♪ Гав!"), ("jump", "⬆ Стрибок"), ("sit", "Сидіти"), ("lie", "Лежати"),
                ("stand", "Встати"), ("paw", "✌ Лапу"), ("hello", "Привіт"), ("spin", "↺ Крутись"),
                ("roll", "Перекид"), ("dance", "♫ Танець"), ("run", "Біжи"), ("walk", "Гуляй"),
                ("sniff", "Нюхай"), ("shake", "Струснись"), ("tilt", "Що?"), ("wag", "♥ Хвостик"),
                ("sleep", "☾ Спати")]
EMO_CHIPS = [("happy", "☺ Радіє"), ("sad", "☹ Сумує"), ("surprised", "Дивується"), ("scared", "Боїться"),
             ("angry", "Сердиться"), ("calm", "Спокійний")]


def chip_strip(items, on_pick, bg=None, height=50):
    """Горизонтальна стрічка кнопок, що гортається пальцем."""
    hs = ScrollView(do_scroll_y=False, bar_width=0, size_hint_y=None, height=dp(height))
    row = BoxLayout(size_hint_x=None, padding=[dp(12), dp(5), dp(12), dp(7)], spacing=dp(8))
    row.bind(minimum_width=row.setter("width"))
    for key, text in items:
        b = theme.RoundButton(text=text, bg=bg or theme.CARD, radius=19, size_hint=(None, 1), font_size=sp(14),
                              shadow=True)
        b.texture_update()
        b.width = max(dp(64), (b.texture_size[0] or dp(60)) + dp(30))
        b.text_size = (None, None)
        b.bind(on_release=lambda _b, k=key: on_pick(k))
        row.add_widget(b)
    hs.add_widget(row)
    return hs


class HomeScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        root = BoxLayout(orientation="vertical")
        theme.paint(root, theme.BG)
        # --- сцена з песиком: 3D (крутиться пальцем), а якщо телефон не потягне — звичайний
        stage = FloatLayout(size_hint_y=None, height=max(dp(270), Window.height * 0.40))
        self.pup = None
        self.show = None
        try:
            import puppy3d
            if puppy3d.model_available():
                p = puppy3d.Puppy3D(sound_cb=app.play_sound, size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
                if p.ok:
                    self.pup = p
        except Exception as e:  # noqa: BLE001
            Logger.warning(f"Home: 3D-песик недоступний: {e}")
        if self.pup is None:
            self.show = Showcase(app.catalog, size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
            theme.paint(stage, (0.86, 0.92, 1.0, 1))
        stage.add_widget(self.pup or self.show)
        title = Label(text=APP_TITLE, font_size=sp(23), bold=True, color=theme.TEXT, size_hint=(None, None),
                      size=(dp(220), dp(34)), pos_hint={"x": 0.03, "top": 0.985}, halign="left", valign="middle")
        title.text_size = title.size
        stage.add_widget(title)
        gear = theme.RoundButton(text="⚙", bg=theme.CARD, radius=23, size_hint=(None, None), size=(dp(46), dp(46)),
                                 pos_hint={"right": 0.975, "top": 0.97}, font_size=sp(22))
        gear.color = theme.ACCENT
        gear.bind(on_release=lambda *_: app.show_settings())
        stage.add_widget(gear)
        root.add_widget(stage)
        if self.pup is not None:
            root.add_widget(chip_strip(ACTION_CHIPS, self.pup.play))
            root.add_widget(chip_strip(EMO_CHIPS, self.pup.emotion, bg=(1.0, 0.94, 0.97, 1), height=48))
        # --- головні дії
        sv, col = scroll_column(12)
        col.padding = [dp(14), dp(8), dp(14), dp(18)]
        Clock.schedule_once(lambda dt: setattr(sv, "scroll_y", 1), 0.3)
        b = theme.button("✚  Створити мультик", theme.GRAD2, height=dp(62), font_size=sp(20), bold=True, radius=22)
        b.bind(on_release=lambda *_: app.open_editor(None))
        col.add_widget(b)
        grid = GridLayout(cols=2, spacing=dp(12), size_hint_y=None, height=dp(2 * 132 + 12))
        cards = [("✎", "Мультик зі слів", "Напишіть історію — песик зіграє, голос прочитає", theme.GRAD4, "ШІ",
                  app.show_story),
                 ("✦", "Готові сюжети", "Мультик одним натиском", theme.GRAD, None, app.show_templates),
                 ("▣", "Оживити фото", "Ваше фото + сніг, блискітки, рух камери", theme.GRAD3, None,
                  app.animate_photo),
                 ("★", "Оживити песика", "Одна кнопка — і песик стрибає, гавкає, радіє", theme.GRAD6, None,
                  app.animate_hero)]
        for icon, name, sub, grad, badge, fn in cards:
            c = BigAction(icon, name, sub, grad, badge=badge)
            c.bind(on_release=lambda _c, f=fn: f())
            grid.add_widget(c)
        col.add_widget(grid)
        b = theme.button("▤  Мої мультики", theme.CARD, height=dp(54), font_size=sp(16), bold=True, radius=20)
        b.color = theme.ACCENT
        b.bind(on_release=lambda *_: app.nav("library"))
        col.add_widget(b)
        root.add_widget(sv)
        root.add_widget(NavBar(app, "create"))
        self.add_widget(root)
        Clock.schedule_once(lambda dt: (self.pup or self.show).start(), 0.5)

    def on_pre_enter(self, *_):
        (self.pup or self.show).start()

    def on_leave(self, *_):
        (self.pup or self.show).stop()


# ====================================================================== каталог
class CatalogScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        cat = app.catalog
        root = BoxLayout(orientation="vertical")
        theme.paint(root, theme.BG)
        root.add_widget(theme.header("Герої", sub="Торкніться героя — побачите всі пози й емоції"))
        from picker import ChipRow
        self.tabs = [(c["name"], cat.chars_in(c["id"])) for c in cat.character_categories if cat.chars_in(c["id"])]
        root.add_widget(ChipRow([n for n, _ in self.tabs], self.show_tab))
        self.grid = ThumbGrid(min_cell=dp(150))
        self.grid.on_pick = lambda i: app.show_hero(self.current[i]["id"])
        root.add_widget(self.grid)
        root.add_widget(NavBar(app, "catalog"))
        self.add_widget(root)
        self.show_tab(0)

    def show_tab(self, i):
        self.current = self.tabs[i][1]
        self.grid.set_items([(self.app.catalog.abspath(c["thumb"]), c["name"]) for c in self.current])


# ====================================================================== бібліотека
class LibraryScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        root = BoxLayout(orientation="vertical")
        theme.paint(root, theme.BG)
        b = theme.button("✚ Новий", theme.GRAD2, size_hint_x=None, width=dp(116), height=dp(44), bold=True)
        b.bind(on_release=lambda *_: app.open_editor(None))
        root.add_widget(theme.header("Мої мультики", right=[b], sub="Торкніться мультика, щоб відкрити"))
        self.body = BoxLayout(padding=[dp(6), 0])
        root.add_widget(self.body)
        root.add_widget(NavBar(app, "library"))
        self.add_widget(root)
        self.grid = ThumbGrid(min_cell=dp(160), ratio=0.5625)
        self.grid.on_pick = self._pick
        self.items = []

    def on_pre_enter(self, *_):
        self.refresh()

    def refresh(self):
        self.items = self.app.store.list()
        self.body.clear_widgets()
        if not self.items:
            self.body.add_widget(theme.label("Тут з'являться ваші мультики.\nНатисніть «✚ Новий», щоб почати.",
                                             16, color=theme.MUTED, halign="center"))
            return
        rows = []
        for it in self.items:
            extra = " · MP4" if it["has_video"] else ""
            rows.append((it["thumb"], f"{it['title']}{extra}"))
        self.grid.set_items(rows, fit="cover")
        self.body.add_widget(self.grid)

    def _pick(self, index):
        it = self.items[index]
        sv, col = scroll_column(10)
        mv = modal(it["title"], sv)
        img = Image(source=it["thumb"], size_hint_y=None, height=dp(190), fit_mode="contain", nocache=True)
        col.add_widget(img)
        acts = [("✎ Відкрити й редагувати", theme.GRAD2, lambda: self.app.open_editor(it["id"])),
                ("▶ Переглянути / відео", theme.GRAD, lambda: self.app.open_player_saved(it["id"])),
                ("Перейменувати", theme.CARD, lambda: self.rename(it)),
                ("✚ Дублювати", theme.CARD, lambda: self.duplicate(it)),
                ("✕ Видалити", theme.RED, lambda: self.delete(it))]
        for text, color, fn in acts:
            b = theme.button(text, color)
            b.bind(on_release=lambda _b, f=fn: (mv.dismiss(), f()))
            col.add_widget(b)
        mv.open()

    def rename(self, it):
        box = BoxLayout(orientation="vertical", spacing=dp(10))
        ti = TextInput(text=it["title"], multiline=False, font_size=sp(17), size_hint_y=None, height=dp(48),
                       background_color=theme.CARD, foreground_color=theme.TEXT, cursor_color=theme.TEXT)
        ok = theme.button("Готово", theme.GRAD)
        box.add_widget(ti)
        box.add_widget(ok)
        box.add_widget(Widget())
        mv = modal("Нова назва", box)

        def done(*_):
            if ti.text.strip():
                self.app.store.rename(it["id"], ti.text.strip())
            mv.dismiss()
            self.refresh()
        ok.bind(on_release=done)
        ti.bind(on_text_validate=done)
        mv.open()

    def duplicate(self, it):
        try:
            self.app.store.duplicate(it["id"])
            self.app.toast("Копію створено")
        except Exception as e:  # noqa: BLE001
            self.app.toast(f"Не вдалося: {e}")
        self.refresh()

    def delete(self, it):
        def yes():
            self.app.store.delete(it["id"])
            self.refresh()
            self.app.toast("Видалено")
        self.app.confirm(f"Видалити «{it['title']}» назавжди?", "Видалити", yes)


# ====================================================================== застосунок
class SceneApp(App):
    title = APP_TITLE

    def build(self):
        base = os.path.dirname(os.path.abspath(__file__))
        imgload.init(os.path.join(self.user_data_dir, "cache"), os.path.join(base, "assets", "probe.webp"))
        self.catalog = Catalog()
        self.sounds = SoundLib()
        self.store = ProjectStore(os.path.join(self.user_data_dir, "projects"))
        try:
            self.store.migrate_v1(lambda old: model.from_v1(old, self.catalog.default_background()))
        except Exception:
            pass
        self.sm = ScreenManager(transition=FadeTransition(duration=0.12))
        self.sm.add_widget(HomeScreen(self, name="home"))
        self.sm.add_widget(CatalogScreen(self, name="catalog"))
        self.sm.add_widget(LibraryScreen(self, name="library"))
        self.editor = EditorScreen(self, name="editor")
        self.sm.add_widget(self.editor)
        self.player = PlayerScreen(self, name="player")
        self.sm.add_widget(self.player)
        Window.bind(on_keyboard=self._key)
        return self.sm

    # ------------------------------------------------------------ навігація
    def go(self, name):
        self.sm.current = name

    def nav(self, key):
        self.go({"catalog": "catalog", "create": "home", "library": "library"}[key])

    def open_editor(self, pid):
        self.editor.open_project(pid)
        self.go("editor")

    def open_player(self, pid, project, scene_index=0):
        self.player.open(pid, project, scene_index)
        self.go("player")

    def open_player_saved(self, pid):
        self.editor.open_project(pid)
        self.open_player(pid, self.editor.project, 0)

    # ------------------------------------------------------------ «оживити фото» й «оживити героя»
    def animate_photo(self):
        pid = self.store.new_id()
        self.toast("Виберіть фото з Галереї…", 1.5)

        def got(name):
            if not name:
                self.store.delete(pid)
                self.toast("Фото не вибрано" if platform == "android" else "Фото можна вибрати лише на телефоні")
                return
            pr = model.new_project("photo:photos/" + name, time.strftime("Оживлене фото %d.%m %H:%M"))
            sc = pr["scenes"][0]
            sc.update(camera="zoom_in", effect="sparkles", duration=6.0, transition="fade")
            self.store.save(pid, pr)
            self.editor.open_project(pid, pr)
            self.editor.dirty = True
            self.editor.save(quiet=True)
            self.go("editor")
            Clock.schedule_once(lambda dt: self.editor.open_effects(), 0.35)
            self.toast("Виберіть ефект. Ще можна додати героїв, репліки й музику!", 4)
        bridge.pick_image(self.store.sub(pid, "photos"), got)

    # ------------------------------------------------------------ звуки для 3D-песика
    def play_sound(self, sid):
        try:
            import audio
            path = self.sounds.path(sid)
            if path:
                audio.play_once(path)
        except Exception:
            pass

    # ------------------------------------------------------------ мультик зі слів (+ озвучка)
    def show_story(self, text=""):
        import random

        import storyteller
        sv, col = scroll_column(10)
        col.add_widget(theme.auto_label("Напишіть кількома реченнями, що робить песик і де. Програма сама "
                                        "складе мультик: фон, предмети, дії, звуки — а оповідач прочитає "
                                        "історію. Слова песика пишіть у лапках «…».", 14, color=theme.MUTED))
        ti = theme.SoftInput(text=text, multiline=True, font_size=sp(17), size_hint_y=None, height=dp(150),
                             hint_text="Наприклад: Песик гуляє в лісі. Він бачить гриби, радіє й гавкає: «Ура!»")
        col.add_widget(ti)
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        rb = theme.button("⚄ Придумай сам", theme.GRAD6, height=dp(48), bold=True)
        rb.bind(on_release=lambda *_: setattr(ti, "text", storyteller.invent(random.Random())))
        row.add_widget(rb)
        cb = theme.button("✕ Очистити", theme.CARD, height=dp(48), size_hint_x=0.6)
        cb.bind(on_release=lambda *_: setattr(ti, "text", ""))
        row.add_widget(cb)
        col.add_widget(row)
        # що зрозуміла програма — оновлюється, поки пишете
        card = theme.Card(bg=theme.SOFT, orientation="vertical", size_hint_y=None, padding=[dp(12), dp(8)],
                          spacing=dp(2), shadow=False)
        card.add_widget(theme.label("☺ Програма зрозуміла:", 13, True, color=theme.ACCENT, size_hint_y=None,
                                    height=dp(22), halign="left"))
        got = theme.auto_label("Почніть писати — тут з'явиться, які будуть сцени й дії.", 13, color=theme.TEXT)
        card.add_widget(got)
        got.bind(height=lambda w, v: setattr(card, "height", v + dp(40)))
        card.height = dp(80)
        col.add_widget(card)
        ev = [None]

        def refresh(*_):
            t = ti.text.strip()
            got.text = storyteller.explain(t, self.catalog) if t else \
                "Почніть писати — тут з'явиться, які будуть сцени й дії."

        def changed(*_):
            if ev[0] is not None:
                ev[0].cancel()
            ev[0] = Clock.schedule_once(refresh, 0.45)
        ti.bind(text=changed)
        if text:
            refresh()
        opts = {"voice": 0, "captions": True}
        col.add_widget(section_label("Голос"))
        col.add_widget(chip_wrap(["♪ Оповідач і песик", "Лише песик", "Без голосу"], 0,
                                 lambda i: opts.__setitem__("voice", i), cols=3, height=50))
        col.add_widget(section_label("Текст історії внизу кадру"))
        col.add_widget(chip_wrap(["Показувати", "Не показувати"], 0,
                                 lambda i: opts.__setitem__("captions", i == 0), cols=2))
        mv = None

        def go(*_):
            t = ti.text.strip()
            if not t:
                self.toast("Напишіть хоча б одне речення або натисніть «⚄ Придумай сам»")
                return
            pr = storyteller.build(self.catalog, t, self.sounds, captions=opts["captions"])
            if pr is None:
                self.toast("Не зрозумів, що робить песик. Спробуйте слова з прикладів нижче.", 4)
                return
            mv.dismiss()
            v = opts["voice"]
            self._open_story(pr, narrator=v == 0, dog=v in (0, 1))
        b = theme.button("✓ Створити мультик", theme.GRAD3, height=dp(58), font_size=sp(19), bold=True, radius=20)
        b.bind(on_release=go)
        col.add_widget(b)
        col.add_widget(section_label("Приклади (торкніться, щоб вставити)"))
        for ex in storyteller.EXAMPLES:
            e = theme.button(ex, theme.CARD, height=dp(70), font_size=sp(13), radius=16)
            e.halign = "left"
            e.bind(width=lambda w, v: setattr(w, "text_size", (v - dp(24), None)))
            e.bind(on_release=lambda _b, t=ex: setattr(ti, "text", t))
            col.add_widget(e)
        col.add_widget(theme.auto_label(
            "Програма розуміє: іде, біжить, стрибає, сідає, лягає, спить, прокидається, нюхає, їсть, грається, "
            "радіє, сумує, боїться, дивується, сердиться, гавкає, каже, думає, кричить, крутиться, танцює, "
            "дає лапу, качається… А ще «швидко», «повільно», «довго», «двічі», «вправо», «додому», «не …». "
            "Місця: ліс, парк, двір, кімната, кухня, озеро, гори, вулиця, школа, космос, море. Пори року, ніч, "
            "сніг, дощ, зірки, свято. Предмети: м'ячик, торт, гриби, ялинка, сніговик, санчата, човен, скарб…",
            12, color=theme.MUTED))
        mv = modal("✎ Мультик зі слів", sv, done=False)
        mv.open()

    def _open_story(self, pr, narrator=True, dog=True):
        import storyteller
        pid = self.store.new_id()
        self.store.save(pid, pr)

        def show(err=None):
            storyteller.finalize(pr)
            storyteller.arrange(pr, self.catalog)
            self.store.save(pid, pr)
            self.editor.open_project(pid, pr)
            self.editor.dirty = True
            self.editor.save(quiet=True)
            self.open_player(pid, pr, 0)
            Clock.schedule_once(lambda dt: self.player.play(), 0.4)
            if err is not None:
                Clock.schedule_once(lambda dt: self.voice_help(err, "Мультик готовий, але без голосу."), 0.6)
            else:
                self.toast("Мультик готовий! «✎ Редагувати» — щоб щось змінити.", 4)
        if narrator or dog:
            self.voice_all(pid, pr, show, narrator=narrator, dog=dog)
        else:
            show()

    def voice_all(self, pid, pr, done, narrator=True, dog=True):
        """Озвучити репліки (песик — мультяшним голосом) і оповідь (звичайним) по черзі, потім done(помилка)."""
        import storyteller
        import tts
        jobs = []
        for sc in pr["scenes"]:
            for it in sc.get("items", []):
                for a in it.get("acts", []):
                    if dog and a.get("a") in ("talk", "bark") and a.get("text") and not a.get("voice") and \
                            not storyteller.is_bark(a["text"]):
                        jobs.append((a, "cartoon", 1.0, 1.15))
            for ln in sc.get("dialog", []):
                if ln.get("text") and not ln.get("voice"):
                    if ln.get("narr") and narrator:
                        jobs.append((ln, "normal", 0.92, 1.0))
                    elif not ln.get("narr") and dog:
                        jobs.append((ln, "normal", 0.95, 1.05))
        if not jobs:
            done()
            return
        if not tts.available():
            self.toast("Озвучка працює лише на телефоні — мультик буде з підписами.", 3)
            done()
            return
        self.store.sub(pid, "voices")
        base = self.store.dir(pid)
        prog = self.progress("Озвучую історію…", len(jobs))
        state = {"i": 0}

        def nxt(*_):
            if state["i"] >= len(jobs):
                prog.dismiss()
                done()
                return
            job, voice, rate, pitch = jobs[state["i"]]
            rel = os.path.join("voices", f"tts_{model.new_uid()}.wav")

            def fin(ok, val):
                if not ok:
                    prog.dismiss()
                    done(val)                     # голосу немає — далі не пробуємо, показуємо підказку
                    return
                job["voice"], job["voice_dur"] = rel, round(val, 2)
                state["i"] += 1
                prog.set(state["i"])
                nxt()
            tts.speak_to_file(job["text"], os.path.join(base, rel), fin, voice, rate=rate, pitch=pitch)
        nxt()

    def progress(self, title, total):
        """Невелике вікно з поступом (не закривається дотиком)."""
        from kivy.uix.progressbar import ProgressBar
        mv = ModalView(size_hint=(0.86, None), height=dp(150), auto_dismiss=False)
        mv.background_color = (0, 0, 0, 0)
        mv.overlay_color = (0.08, 0.05, 0.2, 0.55)
        box = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(10))
        theme.paint(box, theme.PANEL, 22, shadow=True)
        lb = theme.label(title, 17, True, halign="center")
        box.add_widget(lb)
        pb = ProgressBar(max=max(1, total), value=0, size_hint_y=None, height=dp(24))
        box.add_widget(pb)
        cnt = theme.label(f"0 з {total}", 13, color=theme.MUTED, halign="center", size_hint_y=None, height=dp(20))
        box.add_widget(cnt)
        mv.add_widget(box)
        mv.open()

        def set_(i):
            pb.value = i
            cnt.text = f"{i} з {total}"
        mv.set = set_
        return mv

    # ------------------------------------------------------------ голос: перевірка й підказки
    def voice_help(self, err=None, intro=""):
        """Вікно «Озвучка не працює»: що сталося й кнопки, щоб виправити."""
        import tts
        kind = getattr(err, "kind", tts.FAILED) if err is not None else None
        sv, col = scroll_column(10)
        if intro:
            col.add_widget(theme.auto_label(intro, 15, True))
        msg = str(err) if err is not None else "Перевірте, чи працює озвучка на цьому телефоні."
        card = theme.Card(bg=theme.SOFT, orientation="vertical", size_hint_y=None, padding=dp(12), shadow=False)
        lb = theme.auto_label(msg, 15)
        card.add_widget(lb)
        lb.bind(height=lambda w, v: setattr(card, "height", v + dp(24)))
        col.add_widget(card)
        rep = tts.report()
        if rep:
            col.add_widget(theme.auto_label(rep, 13, color=theme.MUTED))
        mv = None
        acts_ = []
        if kind in (tts.NO_ENGINE, None, tts.FAILED):
            acts_.append(("Play Маркет: «Синтезатор мовлення Google»", theme.GRAD, tts.open_store))
        acts_.append(("♪ Встановити український голос", theme.GRAD3, tts.install_voice))
        acts_.append(("⚙ Налаштування синтезу мовлення", theme.CARD, tts.open_settings))
        for text, bg, fn in acts_:
            b = theme.button(text, bg, height=dp(52), bold=True)
            b.bind(on_release=lambda _b, f=fn: (f() or self.toast("Відкрийте Налаштування → Мова → Синтез мовлення",
                                                                   4)))
            col.add_widget(b)
        col.add_widget(theme.auto_label(
            "Як установити: Налаштування телефона → Система → Мова й введення → Синтез мовлення (Text-to-speech) → "
            "рушій Google → ⚙ → Установити голосові дані → Українська. Потім поверніться сюди й натисніть "
            "«Перевірити ще раз».", 13, color=theme.MUTED))
        b = theme.button("↺ Перевірити ще раз", theme.GRAD5, height=dp(54), bold=True)
        b.bind(on_release=lambda *_: (mv.dismiss(), self.check_voice()))
        col.add_widget(b)
        mv = modal("Озвучка", sv, done=False)
        mv.open()

    def check_voice(self):
        """Сказати «Привіт! Я песик.» — щоб переконатися, що голос працює."""
        import audio
        import tts
        tts.reset()
        if not tts.available():
            self.toast("Озвучка працює лише на телефоні", 3)
            return
        path = os.path.join(self.user_data_dir, "cache", "voice_test.wav")
        prog = self.progress("Перевіряю голос…", 1)

        def fin(ok, val):
            prog.dismiss()
            if ok:
                audio.play_once(path)
                self.toast("Голос працює! ☺", 3)
            else:
                self.voice_help(val)
        tts.speak_to_file("Привіт! Я песик. Озвучка працює.", path, fin, "cartoon", rate=1.0, pitch=1.15)

    def show_settings(self):
        sv, col = scroll_column(10)
        items = [("♪ Перевірити озвучку", theme.GRAD3, self.check_voice),
                 ("Озвучка не працює — що робити?", theme.CARD, lambda: self.voice_help()),
                 ("♫ Автори звуків", theme.CARD, self.show_credits)]
        mv = None
        for text, bg, fn in items:
            b = theme.button(text, bg, height=dp(54), bold=bg is not theme.CARD)
            b.bind(on_release=lambda _b, f=fn: (mv.dismiss(), f()))
            col.add_widget(b)
        try:
            import puppy3d
            three = "3D-песик: працює" if (self.sm.get_screen("home").pup is not None) else \
                ("3D-песик: телефон не підтримує — показано звичайного" if puppy3d.model_available()
                 else "3D-песик: немає файлу puppy3d.bin")
        except Exception:
            three = ""
        col.add_widget(theme.auto_label(f"Мультстудія {APP_VERSION}\n{three}", 12, color=theme.MUTED))
        mv = modal("⚙ Налаштування", sv, done=False)
        mv.open()

    def show_templates(self):
        import templates
        sv, col = scroll_column(10)
        col.add_widget(theme.label("Готовий мультик з титрами, музикою й звуками. Потім можна замінити героїв "
                                   "(«⇄ Замінити»), змінити репліки й записати свій голос.", 14,
                                   size_hint_y=None, height=dp(60)))
        mv = None
        cards = []
        for key, name, desc, _c, icon in templates.TEMPLATES:
            card = TemplateCard(icon, name, desc)
            card.bind(on_release=lambda _c, k=key: (mv.dismiss(), self._from_template(k)))
            col.add_widget(card)
            cards.append((key, card))
        mv = modal("Готові сюжети", sv)
        mv.open()
        # мініатюри малюються по одній, щоб вікно відкрилося одразу
        d = os.path.join(self.user_data_dir, "cache", "templates")
        os.makedirs(d, exist_ok=True)
        r = [None]

        def step(dt):
            if not cards:
                return False
            key, card = cards.pop(0)
            path = os.path.join(d, f"{key}_v1.png")
            if not os.path.exists(path):
                try:
                    from render import FrameRenderer
                    pr = templates.build(self.catalog, key, self.sounds)
                    if r[0] is None:
                        r[0] = FrameRenderer(self.catalog, (384, 216))
                    r[0].render_scene(pr, 1, model.still_time(pr["scenes"][1]) + 0.8, still=True)
                    r[0].save_png(path)
                except Exception:
                    return True
            card.img.source = path
            return True
        Clock.schedule_interval(step, 0.05)

    def _from_template(self, key):
        import templates
        try:
            pr = templates.build(self.catalog, key, self.sounds)
        except Exception as e:  # noqa: BLE001
            self.toast(f"Не вдалося: {e}")
            return
        pid = self.store.new_id()
        self.store.save(pid, pr)
        self.editor.open_project(pid, pr)
        self.editor.dirty = True
        self.editor.save(quiet=True)
        self.open_player(pid, pr, 0)
        Clock.schedule_once(lambda dt: self.player.play(), 0.4)
        self.toast("Мультик готовий! «✎ Редагувати» — щоб замінити героїв і репліки.", 4)

    # «Оживити песика»: дія -> (що каже, ефект, фільтр, камера)
    QUICK = {"happy": ("Гав! Як я радію!", "sparkles", "vivid", "none"),
             "jump": ("Гоп!", "stars", "none", "none"), "spin": ("Вжух!", "confetti", "vivid", "none"),
             "dance": ("Танцюю!", "confetti", "vivid", "none"), "run": ("", "none", "none", "follow"),
             "walk": ("", "none", "none", "none"), "paw": ("Тримай лапу!", "hearts", "warm", "focus"),
             "sad": ("Ой…", "rain", "cold", "focus"), "scared": ("Страшно!", "none", "night", "shake"),
             "angry": ("Гр-р!", "none", "warm", "none"), "surprised": ("Ого!", "sparkles", "none", "focus"),
             "sleep": ("", "fireflies", "night", "zoom_in"), "roll": ("", "stars", "none", "none"),
             "shake": ("", "bubbles", "none", "none"), "play": ("Пограймося!", "confetti", "none", "none"),
             "bark": ("Гав-гав!", "none", "none", "focus")}

    def animate_hero(self):
        stars = self.catalog.stars
        if not stars:
            return
        self._hero_action(stars[0]["id"])

    def _hero_action(self, cid):
        from editor import chip_wrap
        import acts as acts_mod
        keys = [k for k in acts_mod.ACTIONS if k in self.QUICK]
        sv, col = scroll_column(10)
        name = self.catalog.characters[cid]["name"]
        col.add_widget(theme.label(f"Що робитиме {name}?", 17, True, size_hint_y=None, height=dp(34)))
        mv = None

        def pick(i):
            mv.dismiss()
            self._make_hero_clip(cid, keys[i])
        col.add_widget(chip_wrap([acts_mod.label(k) for k in keys], -1, pick, cols=2, height=56))
        mv = modal("Оживити песика", sv)
        mv.open()

    def _make_hero_clip(self, cid, key):
        import acts as acts_mod
        text, effect, filt, cam = self.QUICK.get(key, ("", "none", "none", "none"))
        pid = self.store.new_id()
        c = self.catalog.characters[cid]
        pr = model.new_project(self.catalog.default_background(), f"Живий {c['name'].lower()}: {acts_mod.label(key)}")
        sc = pr["scenes"][0]
        moving = key in acts_mod.MOVES
        it = self.catalog.new_item("char", cid, x=0.12 if moving else 0.5, y=0.06)
        it.update(uid=model.new_uid(), rot=0.0, scale=1.8, frame="side_calm" if "side_calm" in c["frames"]
                  else it["frame"], in_fx="pop", in_at=0.0)
        a = acts_mod.new_act(key)
        if moving:
            a["dir"] = "right"
            a["dur"] = 4.0
        it["acts"] = [a]
        if text:
            it["acts"].append(dict(acts_mod.new_act("bark"), text=text))
        it["acts"].append(acts_mod.new_act("happy" if key not in ("sad", "scared", "sleep") else "wait"))
        sc["items"].append(it)
        sc.update(effect=effect, filter=filt, camera=cam, focus=it["uid"], transition="fade")
        self.store.save(pid, pr)
        self.editor.open_project(pid, pr)
        self.editor.dirty = True
        self.editor.save(quiet=True)            # мініатюра для «Моїх мультиків»
        self.open_player(pid, pr, 0)
        Clock.schedule_once(lambda dt: self.player.play(), 0.4)
        self.toast("Готово! «✎ Редагувати» — щоб додати ще дій, фон чи звук.", 4)

    def audio_plan(self, pid, project):
        """Усі звуки мультика з абсолютними шляхами: (events, loops, music)."""
        base = self.store.dir(pid)
        cat = self.catalog

        def resolve(src):
            kind, ref = src
            return os.path.join(base, ref) if kind == "voice" else self.sounds.path(ref)
        ev, lp = model.sound_events(project, lambda cid: cat.characters.get(cid))
        events = [(t, resolve(src), v) for t, src, v in ev if resolve(src)]
        loops = [(a, b, resolve(src), v) for a, b, src, v in lp if resolve(src)]
        m = project.get("music")
        music = None
        if m:
            path = self.sounds.path(m["builtin"]) if m.get("builtin") else os.path.join(base, m.get("file", ""))
            if path:
                music = (path, float(m.get("volume", 0.35)))
        return events, loops, music

    def show_credits(self):
        sv, col = scroll_column(8)
        col.add_widget(theme.label("Звуки й музика в програмі — з вільних бібліотек. Дякуємо авторам!", 15,
                                   size_hint_y=None, height=dp(46)))
        for c in self.sounds.credits:
            card = theme.Card(orientation="vertical", size_hint_y=None, height=dp(86), padding=dp(10))
            card.add_widget(theme.label(c["who"], 14, True, size_hint_y=None, height=dp(40), halign="left",
                                        max_lines=2, shorten=True))
            card.add_widget(theme.label(f"{c['what']} · ліцензія {c['license']}", 12, color=theme.MUTED,
                                        size_hint_y=None, height=dp(26), halign="left"))
            col.add_widget(card)
        col.add_widget(theme.label("Шрифт DejaVu Sans — вільна ліцензія Bitstream Vera / DejaVu.", 12,
                                   color=theme.MUTED, size_hint_y=None, height=dp(40)))
        modal("Автори звуків", sv).open()

    def show_hero(self, cid):
        c = self.catalog.characters[cid]
        groups = self.catalog.frame_groups(cid)
        tabs = [(t, [(self.catalog.abspath(th), lb, key) for key, lb, th in its]) for t, its in groups]
        Picker(f"{c['name']} — емоції й пози", tabs, lambda key: None).open()

    def on_pause(self):
        try:
            if self.sm.current == "editor":
                self.editor.save(quiet=True)
            self.player.stop()
            self.editor.stop_preview()
        except Exception:
            pass
        return True

    def _key(self, window, key, *args):
        if key != 27:
            return False
        for w in list(Window.children):
            if isinstance(w, ModalView):
                w.dismiss()
                return True
        cur = self.sm.current
        if cur == "editor":
            self.editor.leave()
            return True
        if cur == "player":
            self.player.back()
            return True
        if cur in ("catalog", "library"):
            self.go("home")
            return True
        return False

    # ------------------------------------------------------------ збереження в Галерею
    def save_media(self, path, name, mime, done=None):
        if bridge.needs_storage_permission():
            bridge.request_storage_permission(lambda ok: self._after_perm(ok, path, name, mime, done))
            return
        try:
            target = bridge.save_to_gallery(path, name, mime)
        except Exception as e:  # noqa: BLE001
            self.toast(f"Не вдалося зберегти: {e}")
            return
        if done:
            done(target)
        else:
            self.toast("Збережено в Галерею (Pictures/Мультстудія)")

    @mainthread
    def _after_perm(self, ok, path, name, mime, done):
        if ok:
            self.save_media(path, name, mime, done)
        else:
            self.toast("Без дозволу файл не зберегти")

    # ------------------------------------------------------------ підказки й підтвердження
    def toast(self, text, seconds=2.5):
        lb = Label(text=text, font_size=sp(15), color=(1, 1, 1, 1), size_hint=(None, None),
                   halign="center", valign="middle")
        lb.text_size = (min(Window.width * 0.86, dp(520)), None)
        lb.texture_update()
        lb.size = (lb.texture_size[0] + dp(28), lb.texture_size[1] + dp(18))
        lb.pos = ((Window.width - lb.width) / 2, dp(90))
        with lb.canvas.before:
            Color(0.17, 0.11, 0.36, 0.95)
            RoundedRectangle(pos=lb.pos, size=lb.size, radius=[dp(18)])
        Window.add_widget(lb)
        anim = Animation(opacity=1, duration=seconds) + Animation(opacity=0, duration=0.4)
        anim.bind(on_complete=lambda *_: Window.remove_widget(lb))
        anim.start(lb)

    def confirm(self, text, yes_text, on_yes):
        mv = ModalView(size_hint=(0.9, None), height=dp(190))
        mv.background_color = (0, 0, 0, 0)
        mv.overlay_color = (0.08, 0.05, 0.2, 0.6)
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        theme.paint(box, theme.PANEL, 22, shadow=True)
        box.add_widget(theme.label(text, 17, True, halign="center"))
        row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        b = theme.button("Скасувати", theme.CARD)
        b.bind(on_release=lambda *_: mv.dismiss())
        row.add_widget(b)
        b = theme.button(yes_text, theme.RED)
        b.bind(on_release=lambda *_: (mv.dismiss(), on_yes()))
        row.add_widget(b)
        box.add_widget(row)
        mv.add_widget(box)
        mv.open()


if __name__ == "__main__":
    SceneApp().run()
