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
    """Троє героїв на подіумі: спокійно дихають, погойдуються, плавно змінюють емоції й по черзі говорять.
    Торкніться героя — він підстрибне."""
    HEROES = [("girl", "front34_happy"), ("helper_bot", "front34_happy"), ("boy", "front34_calm")]
    PHRASES = ["Привіт!\nГотові до пригод?", "Зробімо мультик!", "Оживи своє фото!",
               "Біп-буп!\nНатисни «Створити»", "Є готові сюжети!", "Ура-а-а!"]
    MOODS = ["happy", "calm", "laughing", "happy", "surprised", "calm"]
    FADE = 0.6

    def __init__(self, catalog, **kw):
        super().__init__(**kw)
        self.cat = catalog
        self.heroes = []
        for cid, frame in self.HEROES:
            c = catalog.characters.get(cid)
            if c is None:
                continue
            frame = frame if frame in c["frames"] else catalog.default_frame(cid)
            self.heroes.append({"c": c, "frame": frame, "old": None, "since": -9.0,
                                "ph": len(self.heroes) * 2.1, "jump": -9.0})
        self.t = 0.0
        self.speaker = 0
        self.phrase = 0
        self.next_say = 4.0
        self.next_mood = 2.5
        self.mood_i = 0
        # усе малюється в canvas.before, щоб підписи й текст хмаринки були поверх
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
            self.parts = []
            for _h in self.heroes:
                PushMatrix()
                tr = Translate()
                rot = Rotate()
                sc = Scale()
                c_old = Color(1, 1, 1, 0)
                r_old = Rectangle()
                c_new = Color(1, 1, 1, 1)
                r_new = Rectangle()
                PopMatrix()
                self.parts.append((tr, rot, sc, c_old, r_old, c_new, r_new))
            Color(0.4, 0.38, 1, 1)
            self.b_line = Line(width=dp(1.4))
            Color(1, 1, 1, 1)
            self.b_rect = RoundedRectangle(radius=[dp(16)])
            self.b_tip = Triangle()
        self.names = [Label(text=short_name(h["c"]), font_size=sp(13), bold=True, color=theme.TEXT,
                            halign="center", valign="middle", shorten=True) for h in self.heroes]
        for lb in self.names:
            self.add_widget(lb)
        self.bubble = Label(text=self.PHRASES[0], font_size=sp(15), bold=True, color=theme.TEXT,
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
        if not self.collide_point(*touch.pos) or not self.heroes:
            return super().on_touch_up(touch)
        if abs(touch.x - touch.ox) > dp(12) or abs(touch.y - touch.oy) > dp(12):
            return False
        k = min(len(self.heroes) - 1, int((touch.x - self.x) / max(1, self.width) * len(self.heroes)))
        self.heroes[k]["jump"] = self.t
        self._set_frame(self.heroes[k], "laughing")
        self._say(k)
        return True

    def _say(self, k):
        self.speaker = k
        self.phrase = (self.phrase + 1) % len(self.PHRASES)
        self.bubble.text = self.PHRASES[self.phrase]
        self.next_say = self.t + 4.5

    def _set_frame(self, h, mood):
        f = "front34_" + mood
        if f not in h["c"]["frames"]:
            f = "front34_happy" if "front34_happy" in h["c"]["frames"] else h["frame"]
        if f != h["frame"]:
            h["old"], h["frame"], h["since"] = h["frame"], f, self.t

    def tick(self, dt):
        self.t += min(dt, 0.1)
        if self.heroes and self.t >= self.next_say:
            self._say((self.speaker + 1) % len(self.heroes))
        if self.heroes and self.t >= self.next_mood:
            self.mood_i += 1
            h = self.heroes[self.mood_i % len(self.heroes)]
            self._set_frame(h, self.MOODS[self.mood_i % len(self.MOODS)])
            self.next_mood = self.t + 2.2
        self.layout()

    def layout(self, *_):
        x, y, w, h = self.x, self.y, self.width, self.height
        self.sky.pos, self.sky.size = (x + w * 0.04, y + h * 0.06), (w * 0.92, h * 0.9)
        self.sun.pos, self.sun.size = (x + w * 0.74, y + h * 0.62), (h * 0.2, h * 0.2)
        self.hill.pos, self.hill.size = (x, y + h * 0.05), (w, h * 0.32)
        self.pod_side.pos, self.pod_side.size = (x + w * 0.08, y + h * 0.04), (w * 0.84, h * 0.17)
        self.pod_top.pos, self.pod_top.size = (x + w * 0.1, y + h * 0.09), (w * 0.8, h * 0.13)
        n = len(self.heroes)
        base = y + h * 0.15
        t = self.t
        head = None
        for k, hero in enumerate(self.heroes):
            c = hero["c"]
            tr, rot, sc, c_old, r_old, c_new, r_new = self.parts[k]
            ch = h * (0.44 if c["size"] < 0.65 else 0.52)
            # плавна зміна емоції: старий кадр згасає, новий проявляється
            fade = min(1.0, (t - hero["since"]) / self.FADE)
            for frame, col, rect, a in ((hero["old"], c_old, r_old, 1 - fade), (hero["frame"], c_new, r_new, 1.0)):
                if not frame or a <= 0:
                    col.a = 0
                    continue
                try:
                    tex = imgload.texture(self.cat.abspath(c["frames"][frame]))
                except Exception:
                    col.a = 0
                    continue
                dims = c["dims"][frame]
                cw = ch * dims[0] / float(dims[1])
                rect.texture = tex
                rect.pos, rect.size = (-cw / 2, 0), (cw, ch)
                col.a = a if rect is r_old else (fade if hero["old"] else 1.0)
            cx = x + w * (k + 0.5) / max(1, n)
            ph = t * 1.6 + hero["ph"]
            bob = math.sin(ph) * h * 0.006
            if c["id"] == "helper_bot":
                bob = h * 0.025 + math.sin(t * 1.4) * h * 0.02       # робот повільно ширяє
            j = t - hero["jump"]
            if 0 <= j < 0.8:
                bob += math.sin(math.pi * j / 0.8) * h * 0.07
            breathe = 1 + 0.012 * math.sin(ph * 0.9)
            tr.xy = (cx, base + bob)
            rot.angle = math.sin(ph * 0.45) * 1.8
            sc.xyz = (1 / breathe ** 0.5, breathe, 1)
            lb = self.names[k]
            lb.size = (w / max(1, n) - dp(6), dp(20))
            lb.text_size = lb.size
            lb.center = (cx, y + h * 0.075)
            if k == self.speaker:
                head = (cx, base + bob + ch * 0.95)
        self.bubble.texture_update()
        bw, bh = self.bubble.texture_size[0] + dp(26), self.bubble.texture_size[1] + dp(16)
        if head is None:
            head = (x + w / 2, y + h * 0.7)
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
        a2 = BigAction("★", "Оживити героя", "Герой танцює, стрибає, сміється…", theme.GRAD3)
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
        col.add_widget(theme.label("Герої", 15, True, color=theme.MUTED, size_hint_y=None, height=dp(24),
                                   halign="left"))
        hs = ScrollView(do_scroll_y=False, bar_width=0, size_hint_y=None, height=dp(136))
        row = BoxLayout(size_hint_x=None, spacing=dp(8))
        row.bind(minimum_width=row.setter("width"))
        for ch in app.catalog.characters.values():
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

    HERO_ACTIONS = {
        "wave": ("Привіт!", "say", "sparkles", "none", "none", "magic_bells"),
        "dance": ("Танцюємо!", "shout", "confetti", "vivid", "none", "music_adventure"),
        "jump": ("Ух ти!", "shout", "none", "vivid", "none", "jump"),
        "hop": ("Гоп-гоп!", "say", "stars", "none", "none", "jump"),
        "laugh": ("Ха-ха-ха!", "shout", "sparkles", "warm", "none", "kid_laugh"),
        "talk": ("Привіт! Зараз я розповім тобі казку.", "say", "none", "none", "focus", None),
        "surprised": ("Ого!", "shout", "sparkles", "none", "focus", "bong"),
        "think": ("Хм… Що ж робити?", "think", "bubbles", "dream", "focus", "question"),
        "cry": ("Ой-ой-ой…", "say", "rain", "cold", "none", "child_cry"),
        "scared": ("Ой, страшно!", "shout", "none", "night", "shake", None),
        "angry": ("Гр-р-р!", "shout", "none", "warm", "shake", None),
        "sleep": ("Хр-р… хр-р…", "think", "fireflies", "night", "none", None),
        "spin": ("Вжу-у-ух!", "shout", "stars", "vivid", "none", "teleport"),
        "alive": ("", "say", "none", "none", "zoom_in", None),
    }

    def animate_hero(self):
        tabs = []
        for c in self.catalog.character_categories:
            items = [(self.catalog.abspath(ch["thumb"]), ch["name"], ch["id"]) for ch in self.catalog.chars_in(c["id"])]
            if items:
                tabs.append((c["name"], items))
        Picker("Кого оживимо?", tabs, self._hero_action).open()

    def _hero_action(self, cid):
        from editor import chip_wrap
        acts = [(k, n) for k, n in model.ANIMS if k in self.HERO_ACTIONS]
        sv, col = scroll_column(10)
        name = self.catalog.characters[cid]["name"]
        col.add_widget(theme.label(f"Що робитиме {name}?", 17, True, size_hint_y=None, height=dp(34)))
        mv = None

        def pick(i):
            mv.dismiss()
            self._make_hero_clip(cid, acts[i][0])
        col.add_widget(chip_wrap([n for _, n in acts], -1, pick, cols=2, height=56))
        mv = modal("Оживити героя", sv)
        mv.open()

    def _make_hero_clip(self, cid, anim):
        text, style, effect, filt, cam, snd = self.HERO_ACTIONS[anim]
        pid = self.store.new_id()
        c = self.catalog.characters[cid]
        pr = model.new_project(self.catalog.default_background(), f"Живий герой: {c['name']}")
        sc = pr["scenes"][0]
        it = self.catalog.new_item("char", cid, x=0.5, y=0.08)
        it.update(uid=model.new_uid(), rot=0.0, anim=anim, in_fx="pop", in_at=0.2)
        it["scale"] = it.get("scale", 1.0) * 1.35
        sc["items"].append(it)
        sc.update(effect=effect, filter=filt, camera=cam, focus=it["uid"], duration=6.0, transition="fade")
        if text:
            sc["dialog"].append({"speaker": it["uid"], "text": text, "style": style, "voice": None})
        if snd and self.sounds.path(snd):
            if snd.startswith("music_"):
                pr["music"] = {"builtin": snd, "volume": 0.35}
            else:
                sc["sfx"] = [{"sound": snd, "at": 0.8, "vol": 1.0}]
        self.store.save(pid, pr)
        self.editor.open_project(pid, pr)
        self.editor.dirty = True
        self.editor.save(quiet=True)            # мініатюра для «Моїх мультиків»
        self.open_player(pid, pr, 0)
        Clock.schedule_once(lambda dt: self.player.play(), 0.4)
        self.toast("Готово! «✎ Редагувати» — щоб змінити фон, додати друзів чи звук.", 4)

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
