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
from kivy.uix.boxlayout import BoxLayout
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
from editor import EditorScreen, modal, scroll_column
from picker import Picker, ThumbGrid
from player import PlayerScreen
from projects import ProjectStore

APP_TITLE = "Мультстудія"

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
        theme.paint(self, theme.CARD, 16, outline=theme.LINE)
        self.img = Image(source="", fit_mode="cover", size_hint_x=None, width=dp(170), nocache=True)
        self.add_widget(self.img)
        box = BoxLayout(orientation="vertical", spacing=dp(2))
        box.add_widget(theme.label(f"{icon}  {title}", 16, True, color=theme.ACCENT, size_hint_y=None,
                                   height=dp(28), halign="left", valign="middle", shorten=True))
        box.add_widget(theme.label(desc, 13, color=theme.MUTED, halign="left", valign="top"))
        self.add_widget(box)


class BigAction(ButtonBehavior, BoxLayout):
    """Велика кольорова картка-дія на головній: значок, назва, підпис."""

    def __init__(self, icon, title, sub, grad, **kw):
        super().__init__(orientation="vertical", padding=[dp(12), dp(8)], spacing=dp(2), **kw)
        with self.canvas.before:
            self._c = Color(1, 1, 1, 1)
            self._rr = RoundedRectangle(radius=[dp(18)], texture=theme.gradient(*grad))
        self.bind(pos=self._u, size=self._u, state=self._u)
        self.add_widget(Label(text=icon, font_size=sp(30), color=theme.WHITE))
        self.add_widget(Label(text=title, font_size=sp(17), bold=True, color=theme.WHITE, size_hint_y=None,
                              height=dp(24)))
        lb = Label(text=sub, font_size=sp(12), color=(1, 1, 1, 0.9), size_hint_y=None, height=dp(30),
                   halign="center", valign="top")
        lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        self.add_widget(lb)

    def _u(self, *_):
        self._rr.pos, self._rr.size = self.pos, self.size
        k = 0.85 if self.state == "down" else 1.0
        self._c.rgba = (k, k, k, 1)


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
        super().__init__(size_hint_y=None, height=dp(62), padding=[dp(8), dp(6)], spacing=dp(6), **kw)
        theme.paint(self, theme.PANEL, outline=theme.LINE)
        for key, icon, text in (("catalog", "▦", "Каталог"), ("create", "✚", "Створення"),
                                ("library", "▤", "Бібліотека")):
            on = key == current
            b = theme.RoundButton(text=f"{icon}\n{text}", bg=theme.ACCENT if on else theme.PANEL,
                                  font_size=sp(13), color=theme.WHITE if on else theme.MUTED, outline=(0, 0, 0, 0))
            b.bind(on_release=lambda _b, k=key: app.nav(k))
            self.add_widget(b)


class HomeScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        root = BoxLayout(orientation="vertical")
        theme.paint(root, theme.BG)
        top = BoxLayout(size_hint_y=None, height=dp(54), padding=[dp(14), dp(8)])
        top.add_widget(theme.label(APP_TITLE, 22, True, halign="left", valign="middle"))
        cb = theme.button("♫ Автори звуків", theme.CARD, size_hint_x=None, width=dp(150), height=dp(38),
                          font_size=sp(13))
        cb.bind(on_release=lambda *_: app.show_credits())
        top.add_widget(cb)
        root.add_widget(top)
        sv, col = scroll_column(12)
        col.padding = [dp(12), dp(4), dp(12), dp(16)]
        Clock.schedule_once(lambda dt: setattr(sv, "scroll_y", 1), 0.3)
        self.show = Showcase(app.catalog, size_hint_y=None, height=dp(300))
        Clock.schedule_once(lambda dt: self.show.start(), 0.5)
        col.add_widget(self.show)
        b = theme.button("✚ Створити мультик", theme.GRAD2, height=dp(60), font_size=sp(20), bold=True)
        b.bind(on_release=lambda *_: app.open_editor(None))
        col.add_widget(b)
        row2 = BoxLayout(size_hint_y=None, height=dp(130), spacing=dp(10))
        a1 = BigAction("▣", "Оживити фото", "Ваше фото + сніг, блискітки, рух камери", theme.GRAD)
        a1.bind(on_release=lambda *_: app.animate_photo())
        a2 = BigAction("★", "Оживити песика", "Одна кнопка — і песик стрибає, гавкає, радіє…", theme.GRAD3)
        a2.bind(on_release=lambda *_: app.animate_hero())
        row2.add_widget(a1)
        row2.add_widget(a2)
        col.add_widget(row2)
        b = theme.button("✦ Готові сюжети — мультик одним натиском", theme.GRAD4, height=dp(54),
                         font_size=sp(16), bold=True)
        b.bind(on_release=lambda *_: app.show_templates())
        col.add_widget(b)
        b = theme.button("▤ Мої мультики", theme.CARD, height=dp(50), font_size=sp(16))
        b.bind(on_release=lambda *_: app.nav("library"))
        col.add_widget(b)
        col.add_widget(theme.label("Герой", 15, True, color=theme.MUTED, size_hint_y=None, height=dp(24),
                                   halign="left"))
        hs = ScrollView(do_scroll_y=False, bar_width=0, size_hint_y=None, height=dp(136))
        row = BoxLayout(size_hint_x=None, spacing=dp(8))
        row.bind(minimum_width=row.setter("width"))
        for ch in app.catalog.stars:
            card = HeroCard(ch, app.catalog)
            card.bind(on_release=lambda c: app.show_hero(c.char["id"]))
            row.add_widget(card)
        hs.add_widget(row)
        col.add_widget(hs)
        root.add_widget(sv)
        root.add_widget(NavBar(app, "create"))
        self.add_widget(root)

    def on_pre_enter(self, *_):
        self.show.start()

    def on_leave(self, *_):
        self.show.stop()


# ====================================================================== каталог
class CatalogScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        cat = app.catalog
        root = BoxLayout(orientation="vertical")
        theme.paint(root, theme.BG)
        top = BoxLayout(size_hint_y=None, height=dp(54), padding=[dp(14), dp(8)])
        top.add_widget(theme.label("Каталог героїв", 20, True, halign="left", valign="middle"))
        root.add_widget(top)
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
        top = BoxLayout(size_hint_y=None, height=dp(54), padding=[dp(14), dp(8)], spacing=dp(8))
        top.add_widget(theme.label("Мої мультики", 20, True, halign="left", valign="middle"))
        b = theme.button("✚ Новий", theme.GRAD2, size_hint_x=None, width=dp(120), height=dp(40))
        b.bind(on_release=lambda *_: app.open_editor(None))
        top.add_widget(b)
        root.add_widget(top)
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
            Color(0.05, 0.03, 0.1, 0.92)
            RoundedRectangle(pos=lb.pos, size=lb.size, radius=[dp(14)])
        Window.add_widget(lb)
        anim = Animation(opacity=1, duration=seconds) + Animation(opacity=0, duration=0.4)
        anim.bind(on_complete=lambda *_: Window.remove_widget(lb))
        anim.start(lb)

    def confirm(self, text, yes_text, on_yes):
        mv = ModalView(size_hint=(0.9, None), height=dp(190))
        mv.background_color = (0, 0, 0, 0)
        mv.overlay_color = (0, 0, 0, 0.6)
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        theme.paint(box, theme.PANEL, 18)
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
