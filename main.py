"""Мультстудія — конструктор мультиків: герої, фони й пори року, репліки й голос,
рух і камера, збирання MP4 на телефоні без інтернету.
"""
import os
import time

import theme  # першим: реєструє шрифт зі значками
from kivy.animation import Animation
from kivy.app import App
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle, Triangle
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
from data import Catalog
from editor import EditorScreen, modal, scroll_column
from picker import Picker, ThumbGrid
from player import PlayerScreen
from projects import ProjectStore

APP_TITLE = "Мультстудія"

if platform != "android":
    Window.size = (430, 900)
Window.clearcolor = theme.BG


# ====================================================================== головна
class Showcase(Widget):
    """Троє героїв на подіумі й хмаринка «Привіт! Готові до пригод?»."""
    HEROES = [("girl", "front34_happy"), ("helper_bot", "front34_happy"), ("boy", "front34_calm")]

    def __init__(self, catalog, **kw):
        super().__init__(**kw)
        self.cat = catalog
        self.items = []
        for cid, frame in self.HEROES:
            c = catalog.characters.get(cid)
            if c is None:
                continue
            frame = frame if frame in c["frames"] else catalog.default_frame(cid)
            try:
                tex = imgload.texture(catalog.abspath(c["frames"][frame]))
            except Exception:
                continue
            self.items.append((c["name"], tex, c["dims"][frame], c["size"]))
        self.names = [Label(text=n, font_size=sp(14), bold=True, color=theme.TEXT) for n, *_ in self.items]
        for lb in self.names:
            self.add_widget(lb)
        self.bubble = Label(text="Привіт!\nГотові до пригод?", font_size=sp(15), color=(0.12, 0.1, 0.18, 1),
                            halign="center")
        self.add_widget(self.bubble)
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *_):
        self.canvas.before.clear()
        x, y, w, h = self.x, self.y, self.width, self.height
        with self.canvas.before:
            Color(0.33, 0.18, 0.62, 0.55)
            Ellipse(pos=(x + w * 0.05, y + h * 0.05), size=(w * 0.9, h * 0.9))
            Color(0.2, 0.14, 0.38, 1)
            Ellipse(pos=(x + w * 0.06, y + h * 0.02), size=(w * 0.88, h * 0.2))
            Color(0.42, 0.3, 0.75, 1)
            Ellipse(pos=(x + w * 0.08, y + h * 0.07), size=(w * 0.84, h * 0.15))
            n = len(self.items)
            base = y + h * 0.15
            for k, (name, tex, dims, size) in enumerate(self.items):
                ch = h * 0.58 * min(1.0, size / 0.65) if size < 0.65 else h * 0.6
                cw = ch * dims[0] / float(dims[1])
                cx = x + w * (0.2 + 0.3 * k) if n == 3 else x + w * (k + 1) / (n + 1)
                Color(1, 1, 1, 1)
                Rectangle(texture=tex, pos=(cx - cw / 2, base), size=(cw, ch))
                lb = self.names[k]
                lb.size = (dp(80), dp(20))
                lb.center = (cx, y + h * 0.1)
            # хмаринка
            self.bubble.texture_update()
            bw, bh = self.bubble.texture_size[0] + dp(24), self.bubble.texture_size[1] + dp(16)
            bx, by = x + w * 0.24 - bw / 2 + dp(30), y + h * 0.78
            by = min(by, y + h - bh - dp(4))
            Color(1, 1, 1, 1)
            RoundedRectangle(pos=(bx, by), size=(bw, bh), radius=[dp(14)])
            Triangle(points=[bx + dp(26), by + 1, bx + dp(46), by + 1, bx + dp(20), by - dp(14)])
            self.bubble.size = (bw, bh)
            self.bubble.pos = (bx, by)


class HeroCard(ButtonBehavior, BoxLayout):
    def __init__(self, char, catalog, **kw):
        super().__init__(orientation="vertical", size_hint=(None, 1), width=dp(84), padding=dp(4),
                         spacing=dp(2), **kw)
        self.char = char
        theme.paint(self, theme.CARD, 14)
        self.add_widget(Image(source=catalog.abspath(char["thumb"]), fit_mode="contain"))
        self.add_widget(theme.label(char["name"], 11, size_hint_y=None, height=dp(28), halign="center",
                                    shorten=True, max_lines=2))


class NavBar(BoxLayout):
    def __init__(self, app, current, **kw):
        super().__init__(size_hint_y=None, height=dp(62), padding=[dp(8), dp(6)], spacing=dp(6), **kw)
        theme.paint(self, theme.PANEL)
        for key, icon, text in (("catalog", "▦", "Каталог"), ("create", "✚", "Створення"),
                                ("library", "▤", "Бібліотека")):
            on = key == current
            b = theme.RoundButton(text=f"{icon}\n{text}", bg=theme.CARD_HI if on else theme.PANEL,
                                  font_size=sp(13), color=theme.TEXT if on else theme.MUTED)
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
        root.add_widget(top)
        sv, col = scroll_column(12)
        col.padding = [dp(12), 0, dp(12), dp(16)]
        show = Showcase(app.catalog, size_hint_y=None, height=dp(300))
        col.add_widget(show)
        b = theme.button("✚ Створити мультик", theme.GRAD2, height=dp(58), font_size=sp(19), bold=True)
        b.bind(on_release=lambda *_: app.open_editor(None))
        col.add_widget(b)
        b = theme.button("▤ Мої мультики", theme.CARD, height=dp(50), font_size=sp(16))
        b.bind(on_release=lambda *_: app.nav("library"))
        col.add_widget(b)
        col.add_widget(theme.label("Герої", 15, True, color=theme.MUTED, size_hint_y=None, height=dp(24),
                                   halign="left"))
        hs = ScrollView(do_scroll_y=False, bar_width=0, size_hint_y=None, height=dp(120))
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
        self.grid = ThumbGrid(min_cell=dp(105))
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
            rows.append((it["thumb"], f"{it['title']}\nсцен: {it['scenes']}{extra}"))
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
