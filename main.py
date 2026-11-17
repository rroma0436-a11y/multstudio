"""Мультстудія — конструктор сцен із героями на фонах.

Версія 1: сцена (фон + герої + предмети), емоції й пози, збереження сцен,
збереження картинки в Галерею й надсилання.
"""
import copy
import json
import os
import time

from kivy.app import App
from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform

import android_bridge as bridge
import imgload
import theme
from data import Catalog
from picker import Picker, ThumbGrid
from projects import ProjectStore
from stage import Stage, StageHolder

APP_TITLE = "Мультстудія"
UNDO_LIMIT = 30

if platform != "android":
    Window.size = (1280, 720)
Window.clearcolor = theme.BG


def fill(widget, rgba, radius=0):
    with widget.canvas.before:
        Color(*rgba)
        r = RoundedRectangle(radius=[dp(radius)]) if radius else Rectangle()
    widget.bind(pos=lambda w, v: setattr(r, "pos", v), size=lambda w, v: setattr(r, "size", v))
    return r


def label(text, size=16, bold=False, color=theme.TEXT, **kw):
    lb = Label(text=text, font_size=sp(size), bold=bold, color=color, **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    return lb


# ====================================================================== головна
class HomeScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        root = BoxLayout(padding=dp(24), spacing=dp(24))
        fill(root, theme.BG)
        pic = Image(source=os.path.join(os.path.dirname(os.path.abspath(__file__)), "presplash.jpg"),
                    fit_mode="contain", size_hint_x=0.42)
        root.add_widget(pic)

        col = BoxLayout(orientation="vertical", spacing=dp(14), padding=[dp(10), dp(30)])
        col.add_widget(Label())
        col.add_widget(label(APP_TITLE, 38, True, size_hint_y=None, height=dp(56), halign="center"))
        col.add_widget(label("Створюй сцени з героями, емоціями й фонами", 17, color=theme.MUTED,
                             size_hint_y=None, height=dp(30), halign="center"))
        col.add_widget(Label(size_hint_y=None, height=dp(10)))
        b = theme.button("Нова сцена", theme.ACCENT, height=dp(62), font_size=sp(20))
        b.bind(on_release=lambda *_: app.open_editor(None))
        col.add_widget(b)
        b = theme.button("Мої сцени", theme.BLUE, height=dp(56), font_size=sp(18))
        b.bind(on_release=lambda *_: app.go("gallery"))
        col.add_widget(b)
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        row.add_widget(theme.button("Комікс — скоро", theme.GREY, disabled=True))
        row.add_widget(theme.button("Мультик — скоро", theme.GREY, disabled=True))
        col.add_widget(row)
        col.add_widget(Label())
        root.add_widget(col)
        self.add_widget(root)


# ====================================================================== мої сцени
class GalleryScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        fill(root, theme.BG)
        top = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10))
        back = theme.button("← Назад", theme.GREY, size_hint_x=None, width=dp(130))
        back.bind(on_release=lambda *_: app.go("home"))
        top.add_widget(back)
        top.add_widget(label("Мої сцени", 24, True, halign="left", valign="middle"))
        new = theme.button("+ Нова сцена", theme.ACCENT, size_hint_x=None, width=dp(190))
        new.bind(on_release=lambda *_: app.open_editor(None))
        top.add_widget(new)
        root.add_widget(top)
        self.empty = label("Тут з'являться збережені сцени", 18, color=theme.MUTED, halign="center")
        self.grid = ThumbGrid()
        self.grid.on_pick = self._pick
        self.body = BoxLayout()
        root.add_widget(self.body)
        self.add_widget(root)
        self.items = []

    def on_pre_enter(self, *_):
        self.refresh()

    def refresh(self):
        self.items = self.app.store.list()
        self.body.clear_widgets()
        if not self.items:
            self.body.add_widget(self.empty)
            return
        self.grid.set_items([(it["thumb"], time.strftime("%d.%m.%Y %H:%M", time.localtime(it["mtime"])))
                             for it in self.items])
        self.body.add_widget(self.grid)

    def _pick(self, index):
        it = self.items[index]
        mv = ModalView(size_hint=(None, None), size=(dp(380), dp(250)), background_color=(0, 0, 0, 0.5))
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        fill(box, theme.BG, 16)
        box.add_widget(label("Що зробити зі сценою?", 18, True, halign="center"))
        b = theme.button("Відкрити", theme.ACCENT)
        b.bind(on_release=lambda *_: (mv.dismiss(), self.app.open_editor(it["id"])))
        box.add_widget(b)
        b = theme.button("Видалити", theme.RED)
        b.bind(on_release=lambda *_: (mv.dismiss(), self._confirm_delete(it)))
        box.add_widget(b)
        b = theme.button("Скасувати", theme.GREY)
        b.bind(on_release=lambda *_: mv.dismiss())
        box.add_widget(b)
        mv.add_widget(box)
        mv.open()

    def _confirm_delete(self, it):
        def yes():
            self.app.store.delete(it["id"])
            self.refresh()
            self.app.toast("Сцену видалено")
        self.app.confirm("Видалити сцену назавжди?", "Видалити", yes)


# ====================================================================== редактор
class EditorScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.cat = app.catalog
        self.pid = None
        self.dirty = False
        self.undo_stack = []
        self._pending = None

        root = BoxLayout()
        self.stage = Stage(catalog=self.cat)
        self.stage.bind(on_before_change=self._before_change, on_change=self._changed,
                        on_double_tap=lambda s, sp_: self.pick_frame(), selected=self._update_panel)
        root.add_widget(StageHolder(self.stage, size_hint_x=0.72))

        sv = ScrollView(size_hint_x=0.28, bar_width=dp(4), do_scroll_x=False)
        panel = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(7), padding=dp(8))
        panel.bind(minimum_height=panel.setter("height"))
        fill(sv, theme.BG)

        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b = theme.button("← Вийти", theme.GREY, height=dp(46), font_size=sp(15))
        b.bind(on_release=lambda *_: self.leave())
        row.add_widget(b)
        self.undo_btn = theme.button("↶ Назад", theme.GREY, height=dp(46), font_size=sp(15))
        self.undo_btn.bind(on_release=lambda *_: self.undo())
        row.add_widget(self.undo_btn)
        panel.add_widget(row)

        panel.add_widget(self._caption("Додати на сцену"))
        for text, color, fn in (("Фон", theme.BLUE, self.pick_background),
                                ("Героя", theme.ACCENT, self.pick_character),
                                ("Предмет", theme.GREEN, self.pick_object)):
            b = theme.button(text, color, height=dp(48))
            b.bind(on_release=lambda *_, f=fn: f())
            panel.add_widget(b)

        self.sel_label = self._caption("Торкніться героя чи предмета")
        panel.add_widget(self.sel_label)
        self.frame_btn = theme.button("Емоція / поза", theme.PURPLE, height=dp(48))
        self.frame_btn.bind(on_release=lambda *_: self.pick_frame())
        panel.add_widget(self.frame_btn)

        grid = GridLayout(cols=2, spacing=dp(6), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        self.item_buttons = [self.frame_btn]
        for text, fn in (("Дзеркало", self.flip), ("Копія", self.duplicate),
                         ("Більше", lambda: self.scale(1.15)), ("Менше", lambda: self.scale(1 / 1.15)),
                         ("Наперед", lambda: self.layer(1)), ("Позаду", lambda: self.layer(-1))):
            b = theme.button(text, theme.BLUE, height=dp(46), font_size=sp(15))
            b.bind(on_release=lambda *_, f=fn: f())
            grid.add_widget(b)
            self.item_buttons.append(b)
        panel.add_widget(grid)
        b = theme.button("Прибрати зі сцени", theme.RED, height=dp(46), font_size=sp(15))
        b.bind(on_release=lambda *_: self.delete())
        self.item_buttons.append(b)
        panel.add_widget(b)

        panel.add_widget(self._caption("Готово?"))
        b = theme.button("Зберегти сцену", theme.GREEN, height=dp(48))
        b.bind(on_release=lambda *_: self.save(show=True))
        panel.add_widget(b)
        b = theme.button("Картинка в Галерею", theme.ACCENT, height=dp(48))
        b.bind(on_release=lambda *_: self.export(share=False))
        panel.add_widget(b)
        b = theme.button("Надіслати", theme.BLUE, height=dp(48))
        b.bind(on_release=lambda *_: self.export(share=True))
        panel.add_widget(b)
        panel.add_widget(label("Підказка: двома пальцями — збільшити чи зменшити, "
                               "подвійний дотик — змінити емоцію.", 13, color=theme.MUTED,
                               size_hint_y=None, height=dp(70)))
        sv.add_widget(panel)
        root.add_widget(sv)
        self.add_widget(root)
        self._update_panel()

    @staticmethod
    def _caption(text):
        lb = label(text, 15, True, color=theme.MUTED, size_hint_y=None, height=dp(30),
                   halign="left", valign="bottom", shorten=True)
        return lb

    # ------------------------------------------------------------ відкриття / вихід
    def open_scene(self, pid):
        self.pid = pid
        self.undo_stack = []
        self.dirty = False
        if pid:
            try:
                scene = self.app.store.load(pid)
            except (OSError, ValueError):
                scene = {}
                self.app.toast("Не вдалося відкрити сцену")
        else:
            scene = {"background": self.cat.default_background(), "items": []}
        self.title = scene.get("title")
        self.stage.load_scene(scene)
        self._update_panel()

    def leave(self):
        if self.dirty and self.stage.sprites:
            self.save(show=False)
        self.app.go("gallery" if self.pid else "home")

    # ------------------------------------------------------------ зміни й «назад»
    def _snapshot(self):
        return copy.deepcopy(self.stage.scene())

    def _before_change(self, *_):
        self._pending = self._snapshot()

    def _changed(self, *_):
        if self._pending is not None:
            self._push(self._pending)
            self._pending = None
        self.dirty = True
        self._update_panel()

    def _push(self, snap):
        self.undo_stack.append(snap)
        del self.undo_stack[:-UNDO_LIMIT]

    def mutate(self, fn):
        snap = self._snapshot()
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self.app.toast(f"Помилка: {e}")
            return
        self._push(snap)
        self.dirty = True
        self._update_panel()

    def undo(self):
        if not self.undo_stack:
            self.app.toast("Більше нічого скасовувати")
            return
        self.stage.load_scene(self.undo_stack.pop())
        self.dirty = True
        self._update_panel()

    def _update_panel(self, *_):
        sel = self.stage.selected
        for b in self.item_buttons:
            b.disabled = sel is None
        if sel is not None and sel.item["kind"] != "char":
            self.frame_btn.disabled = True
        self.undo_btn.disabled = not self.undo_stack
        if sel is None:
            self.sel_label.text = "Торкніться героя чи предмета"
        else:
            self.sel_label.text = "Вибрано: " + self.cat.item_name(sel.item)

    # ------------------------------------------------------------ вибір
    def pick_background(self):
        tabs = []
        for p in self.cat.places:
            items = [(self.cat.abspath(b["thumb"]), b["name"].split("—")[-1].strip().capitalize(), b["id"])
                     for b in self.cat.backgrounds_in(p["id"])]
            if items:
                tabs.append((p["name"], items))
        start = next((i for i, (n, its) in enumerate(tabs) if any(v == self.stage.background for *_, v in its)), 0)
        Picker("Фон", tabs, lambda bid: self.mutate(lambda: self.stage.set_background(bid)), start_tab=start).open()

    def pick_character(self):
        tabs = []
        for c in self.cat.character_categories:
            items = [(self.cat.abspath(ch["thumb"]), ch["name"], ch["id"]) for ch in self.cat.chars_in(c["id"])]
            if items:
                tabs.append((c["name"], items))
        Picker("Герой", tabs, lambda cid: self._add("char", cid)).open()

    def pick_object(self):
        tabs = []
        for c in self.cat.object_categories:
            items = [(self.cat.abspath(o["thumb"]), o["name"], o["id"]) for o in self.cat.objects_in(c["id"])]
            if items:
                tabs.append((c["name"], items))
        Picker("Предмет", tabs, lambda oid: self._add("obj", oid)).open()

    def pick_frame(self):
        sel = self.stage.selected
        if sel is None or sel.item["kind"] != "char":
            return
        groups = self.cat.frame_groups(sel.item["id"])
        tabs = [(title, [(self.cat.abspath(th), lb, key) for key, lb, th in items]) for title, items in groups]
        start = next((i for i, (_, its) in enumerate(tabs) if any(v == sel.item["frame"] for *_, v in its)), 0)
        name = self.cat.characters[sel.item["id"]]["name"]
        Picker(f"{name}: емоція чи поза", tabs, lambda key: self._set_frame(sel, key), start_tab=start).open()

    def _add(self, kind, oid):
        n = len(self.stage.sprites)
        x = 0.5 + ((n % 5) - 2) * 0.12
        item = self.cat.new_item(kind, oid, x=x, y=0.06)
        self.mutate(lambda: self.stage.add_item(item))

    def _set_frame(self, sp_, key):
        def do():
            sp_.item["frame"] = key
            sp_.reload()
            self.stage.place(sp_)
        self.mutate(do)

    # ------------------------------------------------------------ дії з вибраним
    def flip(self):
        sel = self.stage.selected
        if sel is None:
            return

        def do():
            sel.item["flip"] = not sel.item.get("flip")
            sel.apply_flip()
        self.mutate(do)

    def duplicate(self):
        sel = self.stage.selected
        if sel is None:
            return
        item = dict(sel.item)
        item["x"] = min(1.0, item["x"] + 0.06)
        self.mutate(lambda: self.stage.add_item(item))

    def scale(self, k):
        if self.stage.selected is not None:
            self.mutate(lambda: self.stage.scale_selected(k))

    def layer(self, step):
        if self.stage.selected is not None:
            self.mutate(lambda: self.stage.raise_selected(step))

    def delete(self):
        if self.stage.selected is not None:
            self.mutate(self.stage.remove_selected)

    # ------------------------------------------------------------ збереження
    def save(self, show=True):
        store = self.app.store
        if not self.pid:
            self.pid = store.new_id()
        scene = self.stage.scene()
        scene["title"] = self.title or time.strftime("Сцена %d.%m %H:%M")
        self.title = scene["title"]
        try:
            store.save(self.pid, scene)
            self.stage.export_png(store.thumb(self.pid), width=480)
            self.dirty = False
            if show:
                self.app.toast("Сцену збережено")
        except Exception as e:  # noqa: BLE001
            self.app.toast(f"Не вдалося зберегти: {e}")

    def export(self, share=False):
        if bridge.needs_storage_permission():
            bridge.request_storage_permission(lambda ok: self._after_perm(ok, share))
            return
        tmp = os.path.join(self.app.user_data_dir, "export.png")
        try:
            self.stage.export_png(tmp, width=1920)
            name = time.strftime("scena_%Y%m%d_%H%M%S.png")
            target = bridge.save_to_gallery(tmp, name)
        except Exception as e:  # noqa: BLE001
            self.app.toast(f"Не вдалося зберегти картинку: {e}")
            return
        if share:
            try:
                bridge.share(target, "image/png", "Надіслати сцену")
            except Exception as e:  # noqa: BLE001
                self.app.toast(f"Не вдалося надіслати: {e}")
        else:
            self.app.toast(f"Картинку збережено в Галерею (Pictures/{bridge.GALLERY_FOLDER})")

    @mainthread
    def _after_perm(self, ok, share):
        if ok:
            self.export(share)
        else:
            self.app.toast("Без дозволу картинку не зберегти")


# ====================================================================== застосунок
class SceneApp(App):
    title = APP_TITLE

    def build(self):
        base = os.path.dirname(os.path.abspath(__file__))
        imgload.init(os.path.join(self.user_data_dir, "cache"), os.path.join(base, "assets", "probe.webp"))
        self.catalog = Catalog()
        self.store = ProjectStore(os.path.join(self.user_data_dir, "projects"))
        self.sm = ScreenManager(transition=FadeTransition(duration=0.15))
        self.sm.add_widget(HomeScreen(self, name="home"))
        self.sm.add_widget(GalleryScreen(self, name="gallery"))
        self.editor = EditorScreen(self, name="editor")
        self.sm.add_widget(self.editor)
        Window.bind(on_keyboard=self._key)
        return self.sm

    def go(self, name):
        self.sm.current = name

    def open_editor(self, pid):
        self.editor.open_scene(pid)
        self.go("editor")

    def on_pause(self):
        if self.sm.current == "editor" and self.editor.dirty and self.editor.stage.sprites:
            self.editor.save(show=False)
        return True

    def _key(self, window, key, *args):
        if key != 27:
            return False
        for w in list(Window.children):
            if isinstance(w, ModalView):
                w.dismiss()
                return True
        if self.sm.current == "editor":
            self.editor.leave()
            return True
        if self.sm.current == "gallery":
            self.go("home")
            return True
        return False

    # ------------------------------------------------------------ дрібниці інтерфейсу
    def toast(self, text, seconds=2.5):
        lb = Label(text=text, font_size=sp(16), color=(1, 1, 1, 1), size_hint=(None, None),
                   halign="center", valign="middle")
        lb.text_size = (min(Window.width * 0.8, dp(560)), None)
        lb.texture_update()
        lb.size = (lb.texture_size[0] + dp(32), lb.texture_size[1] + dp(20))
        lb.pos = ((Window.width - lb.width) / 2, dp(40))
        with lb.canvas.before:
            Color(0.12, 0.11, 0.1, 0.88)
            RoundedRectangle(pos=lb.pos, size=lb.size, radius=[dp(14)])
        Window.add_widget(lb)
        anim = Animation(opacity=1, duration=seconds) + Animation(opacity=0, duration=0.4)
        anim.bind(on_complete=lambda *_: Window.remove_widget(lb))
        anim.start(lb)

    def confirm(self, text, yes_text, on_yes):
        mv = ModalView(size_hint=(None, None), size=(dp(420), dp(200)), background_color=(0, 0, 0, 0.5))
        box = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        fill(box, theme.BG, 16)
        box.add_widget(label(text, 18, True, halign="center"))
        row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        b = theme.button("Скасувати", theme.GREY)
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
