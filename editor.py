"""Конструктор мультика: сцена 16:9, стрічка сцен, плитки «Персонажі / Діалог / Фон / Камера / Предмети / Звук»."""
import copy
import os
import time

from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput

import audio
import model
import theme
from picker import ChipRow, Picker
from render import FrameRenderer
from stage import Stage, StageHolder

UNDO_LIMIT = 40

# Вкладки вибору фону: пори року + «Ніч і захід» + «Космос і вода»
SEASON_TABS = [("winter", "Зима"), ("spring", "Весна"), ("summer", "Літо"), ("autumn", "Осінь")]
NIGHT_VARIANTS = ("night", "winter_night", "sunset")
SPECIAL_PLACES = ("space", "underwater")


# ====================================================================== дрібні віджети
class Tile(ButtonBehavior, BoxLayout):
    """Плитка конструктора: значок або картинка + назва + підпис."""

    def __init__(self, title, icon="", image=None, sub="", color=theme.CARD, **kw):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(2), **kw)
        self.rr = theme.paint(self, color, 16)
        self.base = color
        if image:
            self.img = Image(source=image, fit_mode="cover", nocache=True)
            self.add_widget(self.img)
        else:
            self.img = None
            self.add_widget(Label(text=icon, font_size=sp(30), color=theme.TEXT))
        row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(40))
        row.add_widget(theme.label(title, 15, True, halign="left", size_hint_y=None, height=dp(20)))
        self.sub = theme.label(sub, 12, color=theme.MUTED, halign="left", size_hint_y=None,
                               height=dp(18), shorten=True)
        row.add_widget(self.sub)
        self.add_widget(row)
        self.bind(state=self._st)

    def _st(self, *_):
        k = 1.25 if self.state == "down" else 1.0
        self.canvas.before.children[0].rgba = tuple(min(1, c * k) for c in self.base[:3]) + (1,)


class SceneCard(ButtonBehavior, BoxLayout):
    def __init__(self, index, source, selected, **kw):
        super().__init__(orientation="vertical", size_hint=(None, 1), width=dp(124),
                         padding=dp(4), spacing=dp(2), **kw)
        self.index = index
        theme.paint(self, theme.CARD_HI if selected else theme.CARD, 12,
                    outline=(0.72, 0.56, 1, 1) if selected else None)
        self.img = Image(source=source, fit_mode="contain", nocache=True)
        self.add_widget(self.img)
        self.add_widget(theme.label(f"Сцена {index + 1}", 12, selected,
                                    color=theme.TEXT if selected else theme.MUTED,
                                    size_hint_y=None, height=dp(18), halign="center"))


def modal(title, body, on_close=None, full=True):
    """Повноекранне вікно з заголовком і кнопкою «←»."""
    mv = ModalView(size_hint=(1, 1) if full else (0.92, None), auto_dismiss=True)
    mv.background_color = (0, 0, 0, 0)
    mv.overlay_color = (0, 0, 0, 0.6)
    root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    theme.paint(root, theme.BG, 0 if full else 18)
    top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    back = theme.button("←", theme.CARD, size_hint_x=None, width=dp(48), font_size=sp(22))
    back.bind(on_release=lambda *_: mv.dismiss())
    top.add_widget(back)
    top.add_widget(theme.label(title, 19, True, halign="left", valign="middle", shorten=True))
    root.add_widget(top)
    root.add_widget(body)
    mv.add_widget(root)
    if on_close:
        mv.bind(on_dismiss=lambda *_: on_close())
    return mv


def section(text):
    return theme.label(text, 14, True, color=theme.MUTED, size_hint_y=None, height=dp(26), halign="left")


def scroll_column(spacing=8):
    sv = ScrollView(do_scroll_x=False, bar_width=dp(4))
    col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(spacing), padding=[0, 0, 0, dp(20)])
    col.bind(minimum_height=col.setter("height"))
    sv.add_widget(col)
    return sv, col


def chip_wrap(names, current, on_select, cols=3, height=46):
    """Сітка вибору з кількох варіантів (одна вибрана)."""
    grid = GridLayout(cols=cols, spacing=dp(6), size_hint_y=None)
    grid.bind(minimum_height=grid.setter("height"))
    btns = []

    def pick(i):
        for k, b in enumerate(btns):
            theme.set_chip(b, k == i)
        on_select(i)
    for i, n in enumerate(names):
        b = theme.chip(n, selected=(i == current), size_hint=(1, None), height=dp(height), width=dp(10))
        b.bind(on_release=lambda _b, i=i: pick(i))
        grid.add_widget(b)
        btns.append(b)
    return grid


# ====================================================================== конструктор
class EditorScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.cat = app.catalog
        self.project = None
        self.pid = None
        self.si = 0
        self.dirty = False
        self.undo_stack = []
        self._pending = None
        self._thumb_ev = None
        self.thumb_renderer = None

        root = BoxLayout(orientation="vertical")
        theme.paint(root, theme.BG)

        # --- верхня панель
        top = BoxLayout(size_hint_y=None, height=dp(54), padding=[dp(8), dp(6)], spacing=dp(6))
        b = theme.button("←", theme.CARD, size_hint_x=None, width=dp(46), height=dp(42), font_size=sp(22))
        b.bind(on_release=lambda *_: self.leave())
        top.add_widget(b)
        self.title_btn = theme.RoundButton(text="", bg=theme.BG, font_size=sp(17), bold=True,
                                           size_hint_y=None, height=dp(42))
        self.title_btn.bind(on_release=lambda *_: self.rename())
        top.add_widget(self.title_btn)
        self.undo_btn = theme.button("↶", theme.CARD, size_hint_x=None, width=dp(46), height=dp(42),
                                     font_size=sp(22))
        self.undo_btn.bind(on_release=lambda *_: self.undo())
        top.add_widget(self.undo_btn)
        b = theme.button("▶ Перегляд", theme.GRAD, size_hint_x=None, width=dp(128), height=dp(42),
                         font_size=sp(15), bold=True)
        b.bind(on_release=lambda *_: self.preview())
        top.add_widget(b)
        root.add_widget(top)

        # --- сцена
        self.stage = Stage(catalog=self.cat)
        self.stage.bind(on_before_change=self._before_change, on_change=self._changed,
                        on_double_tap=lambda s, sp_: self.pick_frame(), selected=self._update_sel)
        self.holder = StageHolder(self.stage, bg=theme.BG, size_hint_y=None)
        root.bind(width=lambda w, v: setattr(self.holder, "height", v * 9 / 16.0))
        root.add_widget(self.holder)

        # --- режим руху й інформація
        mode = BoxLayout(size_hint_y=None, height=dp(48), padding=[dp(8), dp(5)], spacing=dp(6))
        self.mode_row = ChipRow(["● Початок", "➜ Кінець руху"], self._set_mode, size_hint_x=None,
                                width=dp(250), height=dp(40))
        mode.add_widget(self.mode_row)
        self.info = theme.label("", 13, color=theme.MUTED, halign="right", valign="middle")
        mode.add_widget(self.info)
        root.add_widget(mode)

        # --- дії з вибраним героєм
        self.sel_box = BoxLayout(size_hint_y=None, height=dp(48), padding=[dp(8), dp(4)])
        root.add_widget(self.sel_box)
        self.sel_hint = theme.label("Торкніться героя на сцені, щоб змінити його", 13, color=theme.MUTED,
                                    halign="left", valign="middle")
        self.sel_actions = ScrollView(do_scroll_y=False, bar_width=0)
        row = BoxLayout(size_hint_x=None, spacing=dp(6))
        row.bind(minimum_width=row.setter("width"))
        self.frame_chip = None
        for text, fn in (("☺ Емоція", self.pick_frame), ("⇆ Дзеркало", self.flip), ("+ Більше", lambda: self.scale(1.15)),
                         ("− Менше", lambda: self.scale(1 / 1.15)), ("✚ Копія", self.duplicate_item),
                         ("▲ Наперед", lambda: self.layer(1)), ("▼ Позаду", lambda: self.layer(-1)),
                         ("↺ Без руху", self.clear_motion), ("✕ Прибрати", self.delete_item)):
            c = theme.chip(text)
            c.bind(on_release=lambda _b, f=fn: f())
            row.add_widget(c)
            if text.startswith("☺"):
                self.frame_chip = c
        self.sel_actions.add_widget(row)

        # --- нижня частина з прокруткою
        sv, col = scroll_column(10)
        col.padding = [dp(10), dp(4), dp(10), dp(24)]
        head = BoxLayout(size_hint_y=None, height=dp(30))
        head.add_widget(section("Сцени"))
        b = theme.chip("⋯ Дії зі сценою")
        b.bind(on_release=lambda *_: self.scene_menu())
        head.add_widget(b)
        col.add_widget(head)
        self.strip_sv = ScrollView(do_scroll_y=False, bar_width=0, size_hint_y=None, height=dp(96))
        self.strip = BoxLayout(size_hint_x=None, spacing=dp(8))
        self.strip.bind(minimum_width=self.strip.setter("width"))
        self.strip_sv.add_widget(self.strip)
        col.add_widget(self.strip_sv)

        tiles = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, row_default_height=dp(118),
                           row_force_default=True)
        tiles.bind(minimum_height=tiles.setter("height"))
        self.t_chars = Tile("Персонажі", "☺", sub="Додати героя")
        self.t_dialog = Tile("Діалог", "❝", sub="Репліки й голос")
        self.t_bg = Tile("Фон", "▦", sub="Місце й пора року")
        self.t_cam = Tile("Камера", "◎", sub="Рух і тривалість")
        self.t_obj = Tile("Предмети", "★", sub="Дерева, меблі, іграшки")
        self.t_sound = Tile("Звук", "♫", sub="Фонова музика")
        for t, fn in ((self.t_chars, self.pick_character), (self.t_dialog, self.open_dialog),
                      (self.t_bg, self.pick_background), (self.t_cam, self.open_camera),
                      (self.t_obj, self.pick_object), (self.t_sound, self.open_sound)):
            t.bind(on_release=lambda _t, f=fn: f())
            tiles.add_widget(t)
        col.add_widget(tiles)
        b = theme.button("Зберегти кадр як картинку", theme.CARD, height=dp(44), font_size=sp(14))
        b.bind(on_release=lambda *_: self.export_still())
        col.add_widget(b)
        root.add_widget(sv)
        self.add_widget(root)
        self._update_sel()

    # ================================================================== проєкт
    @property
    def scene(self):
        return self.project["scenes"][self.si]

    def open_project(self, pid):
        store = self.app.store
        if pid:
            try:
                self.project = store.load(pid)
            except (OSError, ValueError):
                self.app.toast("Не вдалося відкрити мультик")
                pid = None
        if not pid:
            pid = store.new_id()
            self.project = model.new_project(self.cat.default_background())
        self.pid = pid
        self.undo_stack = []
        self.dirty = False
        self.si = 0
        self.mode_row.select(0, notify=False)
        self.stage.mode = "start"
        self.title_btn.text = self.project.get("title") or "Мультик"
        self.load_current()
        self.refresh_strip(rethumb=True)

    def load_current(self):
        self.si = max(0, min(self.si, len(self.project["scenes"]) - 1))
        self.stage.load_scene(self.scene)
        self._update_info()
        self._update_sel()

    def leave(self):
        self.save(quiet=True)
        self.app.go("home")

    def save(self, quiet=False):
        if not self.dirty and quiet:
            return
        try:
            self.app.store.save(self.pid, self.project)
            r = FrameRenderer(self.cat, (480, 270))
            r.render_scene(self.project, 0, 0.0)
            r.save_png(self.app.store.thumb(self.pid))
            self.dirty = False
            if not quiet:
                self.app.toast("Збережено")
        except Exception as e:  # noqa: BLE001
            self.app.toast(f"Не вдалося зберегти: {e}")

    def rename(self):
        box = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None, height=dp(130))
        ti = TextInput(text=self.project.get("title", ""), multiline=False, font_size=sp(17),
                       size_hint_y=None, height=dp(48), background_color=theme.CARD,
                       foreground_color=theme.TEXT, cursor_color=theme.TEXT)
        box.add_widget(ti)
        ok = theme.button("Готово", theme.GRAD)
        box.add_widget(ok)
        wrap = BoxLayout(orientation="vertical")
        wrap.add_widget(box)
        wrap.add_widget(Label())
        mv = modal("Назва мультика", wrap)

        def done(*_):
            t = ti.text.strip()
            if t:
                self.project["title"] = t
                self.title_btn.text = t
                self.dirty = True
            mv.dismiss()
        ok.bind(on_release=done)
        ti.bind(on_text_validate=done)
        mv.open()

    # ================================================================== зміни й «назад»
    def _snapshot(self):
        return (copy.deepcopy(self.project), self.si)

    def _before_change(self, *_):
        self._pending = self._snapshot()

    def _changed(self, *_):
        if self._pending is not None:
            self._push(self._pending)
            self._pending = None
        self._touched()

    def _push(self, snap):
        self.undo_stack.append(snap)
        del self.undo_stack[:-UNDO_LIMIT]
        self.undo_btn.disabled = False

    def _touched(self, rethumb=True):
        self.dirty = True
        self._update_info()
        self._update_sel()
        if rethumb:
            self._schedule_thumb()

    def mutate(self, fn, reload_stage=False):
        snap = self._snapshot()
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self.app.toast(f"Помилка: {e}")
            return
        self._push(snap)
        if reload_stage:
            self.load_current()
        self._touched()

    def undo(self):
        if not self.undo_stack:
            self.app.toast("Більше нічого скасовувати")
            return
        self.project, self.si = self.undo_stack.pop()
        self.title_btn.text = self.project.get("title") or "Мультик"
        self.load_current()
        self.refresh_strip(rethumb=True)
        self.dirty = True

    # ================================================================== інформація й вибір
    def _update_info(self):
        n = len(self.project["scenes"]) if self.project else 0
        if not n:
            return
        length, _ = model.scene_timing(self.scene)
        _, total = model.timeline(self.project)
        self.info.text = f"Сцена {self.si + 1} з {n} · {length:.1f} с  (усього {total:.0f} с)"
        self.t_dialog.sub.text = f"Реплік: {len(self.scene.get('dialog', []))}"
        cam = dict(model.CAMERA_MOVES).get(self.scene.get("camera", "none"), "")
        self.t_cam.sub.text = f"{cam} · {length:.1f} с"
        m = self.project.get("music")
        self.t_sound.sub.text = "Музика: є" if m else "Фонова музика"
        bg = self.cat.backgrounds.get(self.scene.get("background"))
        self.t_bg.sub.text = bg["name"] if bg else ""
        self.undo_btn.disabled = not self.undo_stack

    def _update_sel(self, *_):
        sel = self.stage.selected
        self.sel_box.clear_widgets()
        if sel is None:
            self.sel_box.add_widget(self.sel_hint)
        else:
            self.sel_box.add_widget(self.sel_actions)
            if self.frame_chip is not None:
                self.frame_chip.disabled = sel.item["kind"] != "char"

    def _set_mode(self, i):
        self.stage.mode = "end" if i == 1 else "start"
        if i == 1:
            self.app.toast("Перетягніть героїв туди, куди вони мають дійти до кінця сцени. "
                           "Герой сам піде, побіжить чи полетить.", 4)

    # ================================================================== сцени
    def _thumb_path(self, i):
        d = os.path.join(self.app.user_data_dir, "cache", "scenes")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{self.pid}_{i}.png")

    def _render_thumb(self, i):
        if self.thumb_renderer is None:
            self.thumb_renderer = FrameRenderer(self.cat, (256, 144))
        try:
            self.thumb_renderer.render_scene(self.project, i, 0.0)
            self.thumb_renderer.save_png(self._thumb_path(i))
        except Exception:
            pass

    def _schedule_thumb(self):
        if self._thumb_ev is not None:
            self._thumb_ev.cancel()
        self._thumb_ev = Clock.schedule_once(lambda dt: self.refresh_strip(only=self.si), 0.6)

    def refresh_strip(self, rethumb=False, only=None):
        n = len(self.project["scenes"])
        if rethumb:
            for i in range(n):
                self._render_thumb(i)
        elif only is not None and only < n:
            self._render_thumb(only)
        self.strip.clear_widgets()
        for i in range(n):
            card = SceneCard(i, self._thumb_path(i), i == self.si)
            card.bind(on_release=lambda c: self.select_scene(c.index))
            self.strip.add_widget(card)
        add = theme.button("+\nСцена", theme.CARD, size_hint=(None, 1), width=dp(80), font_size=sp(15))
        add.bind(on_release=lambda *_: self.add_scene())
        self.strip.add_widget(add)

    def select_scene(self, i):
        if i == self.si:
            return
        self.si = i
        self.load_current()
        self.refresh_strip()

    def add_scene(self):
        box = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None, height=dp(170))
        b1 = theme.button("Продовжити цю сцену\n(ті самі герої там, де закінчили рух)", theme.GRAD,
                          height=dp(70))
        b2 = theme.button("Порожня сцена з тим самим фоном", theme.CARD, height=dp(56))
        box.add_widget(b1)
        box.add_widget(b2)
        wrap = BoxLayout(orientation="vertical")
        wrap.add_widget(box)
        wrap.add_widget(Label())
        mv = modal("Нова сцена", wrap)

        def go(cont):
            mv.dismiss()

            def do():
                if cont:
                    sc = model.duplicate_scene(self.scene)
                    sc["dialog"] = []
                else:
                    sc = model.new_scene(self.scene.get("background"))
                self.project["scenes"].insert(self.si + 1, sc)
                self.si += 1
            self.mutate(do, reload_stage=True)
            self.refresh_strip(rethumb=True)
            Clock.schedule_once(lambda dt: setattr(self.strip_sv, "scroll_x", 1), 0.1)
        b1.bind(on_release=lambda *_: go(True))
        b2.bind(on_release=lambda *_: go(False))
        mv.open()

    def scene_menu(self):
        sv, col = scroll_column(10)
        mv = modal(f"Сцена {self.si + 1}", sv)
        n = len(self.project["scenes"])

        def act(fn):
            mv.dismiss()
            self.mutate(fn, reload_stage=True)
            self.refresh_strip(rethumb=True)

        def dup():
            self.project["scenes"].insert(self.si + 1, model.duplicate_scene(self.scene))
            self.si += 1

        def move(step):
            j = self.si + step
            sc = self.project["scenes"]
            sc[self.si], sc[j] = sc[j], sc[self.si]
            self.si = j

        def delete():
            del self.project["scenes"][self.si]
            self.si = max(0, self.si - 1)

        items = [("✚ Дублювати сцену", theme.CARD, dup, True),
                 ("◂ Перемістити ліворуч", theme.CARD, lambda: move(-1), self.si > 0),
                 ("▸ Перемістити праворуч", theme.CARD, lambda: move(1), self.si < n - 1),
                 ("✕ Видалити сцену", theme.RED, delete, n > 1)]
        for text, color, fn, ok in items:
            b = theme.button(text, color, disabled=not ok)
            b.bind(on_release=lambda _b, f=fn: act(f))
            col.add_widget(b)
        mv.open()

    # ================================================================== вибір фону, героїв, предметів
    def pick_background(self):
        cat = self.cat
        tabs = []
        for var, name in SEASON_TABS:
            items = []
            for p in cat.places:
                bid = f"{p['id']}_{var}"
                if bid in cat.backgrounds:
                    items.append((cat.abspath(cat.backgrounds[bid]["thumb"]), p["name"], bid))
            tabs.append((name, items))
        night = [(cat.abspath(b["thumb"]), b["name"], b["id"]) for b in cat.backgrounds.values()
                 if b["variant"] in NIGHT_VARIANTS]
        special = [(cat.abspath(b["thumb"]), b["name"], b["id"]) for b in cat.backgrounds.values()
                   if b["place"] in SPECIAL_PLACES]
        tabs += [("Ніч і захід", night), ("Космос і вода", special)]
        cur = self.scene.get("background")
        start = next((i for i, (_, its) in enumerate(tabs) if any(v == cur for *_, v in its)), 2)

        def apply(bid):
            self.mutate(lambda: self.stage.set_background(bid))
        Picker("Вибір локації та пори року", tabs, apply, start_tab=start, current_value=cur,
               ratio=0.62, fit="cover", min_cell=dp(150)).open()

    def pick_character(self):
        tabs = []
        for c in self.cat.character_categories:
            items = [(self.cat.abspath(ch["thumb"]), ch["name"], ch["id"]) for ch in self.cat.chars_in(c["id"])]
            if items:
                tabs.append((c["name"], items))
        Picker("Персонажі", tabs, lambda cid: self._add("char", cid)).open()

    def pick_object(self):
        tabs = []
        for c in self.cat.object_categories:
            items = [(self.cat.abspath(o["thumb"]), o["name"], o["id"]) for o in self.cat.objects_in(c["id"])]
            if items:
                tabs.append((c["name"], items))
        Picker("Предмети", tabs, lambda oid: self._add("obj", oid)).open()

    def pick_frame(self):
        sel = self.stage.selected
        if sel is None or sel.item["kind"] != "char":
            return
        groups = self.cat.frame_groups(sel.item["id"])
        tabs = [(t, [(self.cat.abspath(th), lb, key) for key, lb, th in its]) for t, its in groups]
        cur = sel.item["frame"]
        start = next((i for i, (_, its) in enumerate(tabs) if any(v == cur for *_, v in its)), 0)
        name = self.cat.characters[sel.item["id"]]["name"]

        def apply(key):
            def do():
                sel.item["frame"] = key
                sel.reload()
                self.stage.layout()
            self.mutate(do)
        Picker(f"{name}: емоція чи поза", tabs, apply, start_tab=start, current_value=cur).open()

    def _add(self, kind, oid):
        n = len(self.scene["items"])
        x = 0.5 + ((n % 5) - 2) * 0.13
        item = self.cat.new_item(kind, oid, x=x, y=0.06)
        item["uid"] = model.new_uid()
        item["rot"] = 0.0
        if self.stage.mode == "end":
            self.mode_row.select(0)
        self.mutate(lambda: self.stage.add_item(item))

    # ================================================================== дії з вибраним
    def _sel(self):
        return self.stage.selected

    def flip(self):
        sel = self._sel()
        if sel is None:
            return

        def do():
            sel.item["flip"] = not sel.item.get("flip")
            sel.apply_flip()
        self.mutate(do)

    def scale(self, k):
        if self._sel() is not None:
            self.mutate(lambda: self.stage.scale_selected(k))

    def layer(self, step):
        if self._sel() is not None:
            self.mutate(lambda: self.stage.raise_selected(step))

    def clear_motion(self):
        if self._sel() is not None:
            self.mutate(self.stage.clear_motion_selected)

    def delete_item(self):
        if self._sel() is not None:
            self.mutate(self.stage.remove_selected)

    def duplicate_item(self):
        sel = self._sel()
        if sel is None:
            return
        item = copy.deepcopy(sel.item)
        item["uid"] = model.new_uid()
        item["x"] = min(1.0, item["x"] + 0.07)
        if item.get("end"):
            item["end"]["x"] = min(1.1, item["end"].get("x", item["x"]) + 0.07)
        self.mutate(lambda: self.stage.add_item(item))

    # ================================================================== камера й тривалість
    def open_camera(self):
        sv, col = scroll_column(10)
        sc = self.scene
        col.add_widget(section("Рух камери"))
        keys = [k for k, _ in model.CAMERA_MOVES]

        def set_cam(i):
            self.mutate(lambda: sc.__setitem__("camera", keys[i]), )
        col.add_widget(chip_wrap([n for _, n in model.CAMERA_MOVES], keys.index(sc.get("camera", "none")),
                                 set_cam, cols=2))
        col.add_widget(section("Перехід до сцени"))
        tkeys = [k for k, _ in model.TRANSITIONS]
        col.add_widget(chip_wrap([n for _, n in model.TRANSITIONS], tkeys.index(sc.get("transition", "fade")),
                                 lambda i: self.mutate(lambda: sc.__setitem__("transition", tkeys[i])), cols=2))
        col.add_widget(section("Тривалість сцени"))
        lab = theme.label("", 16, True, size_hint_y=None, height=dp(28), halign="center")
        sl = Slider(min=1.5, max=20, step=0.5, value=float(sc.get("duration", 4.0)), size_hint_y=None,
                    height=dp(44), cursor_size=(dp(28), dp(28)))

        def upd(*_):
            length, _ = model.scene_timing(dict(sc, duration=sl.value))
            extra = "" if length <= sl.value + 0.01 else f"  → {length:.1f} с через репліки"
            lab.text = f"{sl.value:.1f} с{extra}"
        sl.bind(value=upd)
        upd()
        col.add_widget(lab)
        col.add_widget(sl)
        col.add_widget(theme.label("Якщо реплік багато, сцена сама подовжиться, щоб усі встигли договорити.",
                                   13, color=theme.MUTED, size_hint_y=None, height=dp(40)))
        col.add_widget(section("Глибина"))
        col.add_widget(chip_wrap(["Хто нижче — той ближче", "Як розставлено вручну"],
                                 0 if sc.get("auto_depth", True) else 1,
                                 lambda i: self.mutate(lambda: sc.__setitem__("auto_depth", i == 0),
                                                       reload_stage=True), cols=1))

        def closed():
            if abs(float(sc.get("duration", 4.0)) - sl.value) > 0.01:
                self.mutate(lambda: sc.__setitem__("duration", sl.value))
        modal("Камера та тривалість", sv, on_close=closed).open()

    # ================================================================== звук
    def open_sound(self):
        sv, col = scroll_column(10)
        mv = modal("Звук", sv)
        pr = self.project
        col.add_widget(section("Фонова музика (на весь мультик)"))
        m = pr.get("music")
        name = os.path.basename(m["file"]) if m else "не вибрано"
        col.add_widget(theme.label(f"♫ {name}", 15, size_hint_y=None, height=dp(30), halign="left"))
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b = theme.button("Вибрати з телефону", theme.GRAD)
        row.add_widget(b)
        rm = theme.button("Прибрати", theme.CARD, size_hint_x=0.5, disabled=not m)
        row.add_widget(rm)
        col.add_widget(row)
        col.add_widget(section("Гучність музики"))
        sl = Slider(min=0.05, max=1.0, value=float(m["volume"]) if m else 0.35, size_hint_y=None,
                    height=dp(44), cursor_size=(dp(28), dp(28)), disabled=not m)
        col.add_widget(sl)
        col.add_widget(theme.label(
            "Голос героїв записується в розділі «Діалог»: відкрийте репліку й натисніть «● Записати голос».",
            13, color=theme.MUTED, size_hint_y=None, height=dp(56)))
        if not audio.available():
            col.add_widget(theme.label("Звук працює лише на телефоні.", 13, color=theme.ORANGE,
                                       size_hint_y=None, height=dp(30)))

        def picked(path):
            if not path:
                return
            rel = os.path.relpath(path, self.app.store.dir(self.pid))
            self.mutate(lambda: pr.__setitem__("music", {"file": rel, "volume": 0.35}))
            mv.dismiss()
            self.app.toast("Музику додано")

        def choose(*_):
            audio.pick_audio(self.app.store.sub(self.pid, "music"), picked)

        def remove(*_):
            self.mutate(lambda: pr.__setitem__("music", None))
            mv.dismiss()

        def vol(*_):
            if pr.get("music"):
                pr["music"]["volume"] = round(sl.value, 2)
                self.dirty = True
        b.bind(on_release=choose)
        rm.bind(on_release=remove)
        sl.bind(value=vol)
        mv.open()

    # ================================================================== діалог
    def speakers(self):
        out = [(None, "Оповідач")]
        for it in self.scene["items"]:
            if it["kind"] == "char":
                out.append((it["uid"], self.cat.characters[it["id"]]["name"]))
        return out

    def open_dialog(self):
        DialogEditor(self).open()

    # ================================================================== перегляд
    def preview(self):
        self.save(quiet=True)
        self.app.open_player(self.pid, self.project, self.si)

    def export_still(self):
        try:
            r = FrameRenderer(self.cat, (1920, 1080))
            r.render_scene(self.project, self.si, 0.0)
            tmp = os.path.join(self.app.user_data_dir, "still.png")
            r.save_png(tmp)
            self.app.save_media(tmp, time.strftime("kadr_%Y%m%d_%H%M%S.png"), "image/png")
        except Exception as e:  # noqa: BLE001
            self.app.toast(f"Не вдалося: {e}")


# ====================================================================== діалог сцени
class DialogEditor:
    def __init__(self, editor):
        self.ed = editor
        self.sv, self.col = scroll_column(8)
        self.mv = modal(f"Діалог · Сцена {editor.si + 1}", self.sv, on_close=self._closed)
        self.playback = None
        self.fill()

    def open(self):
        self.mv.open()

    def _closed(self):
        if self.playback:
            self.playback.stop()
        self.ed.refresh_strip(only=self.ed.si)

    def fill(self):
        col = self.col
        col.clear_widgets()
        sc = self.ed.scene
        names = dict(self.ed.speakers())
        add = theme.button("✚ Додати репліку", theme.GRAD, bold=True)
        add.bind(on_release=lambda *_: self.edit(None))
        col.add_widget(add)
        if not sc["dialog"]:
            col.add_widget(theme.label("Реплік ще немає. Додайте першу — хто що каже, і "
                                       "над героєм з'явиться хмаринка з текстом.", 14, color=theme.MUTED,
                                       size_hint_y=None, height=dp(70)))
        _, spans = model.scene_timing(sc)
        for k, (ln, (a, b)) in enumerate(zip(sc["dialog"], spans)):
            card = theme.Card(orientation="vertical", size_hint_y=None, height=dp(112), padding=dp(10),
                              spacing=dp(4))
            who = names.get(ln.get("speaker"), "Оповідач")
            voice = "  ● голос" if ln.get("voice") else ""
            style = dict(model.BUBBLE_STYLES).get(ln.get("style", "say"), "")
            card.add_widget(theme.label(f"{k + 1}. {who} · {style}{voice} · {a:.1f}–{b:.1f} с", 13, True,
                                        color=theme.CYAN, size_hint_y=None, height=dp(20), halign="left",
                                        shorten=True))
            card.add_widget(theme.label(ln.get("text") or "(без тексту)", 15, size_hint_y=None,
                                        height=dp(38), halign="left", shorten=True, max_lines=2))
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
            for text, fn, ok in (("✎ Змінити", lambda k=k: self.edit(k), True),
                                 ("▲", lambda k=k: self.move(k, -1), k > 0),
                                 ("▼", lambda k=k: self.move(k, 1), k < len(sc["dialog"]) - 1),
                                 ("✕", lambda k=k: self.delete(k), True)):
                b_ = theme.button(text, theme.CARD_HI, height=dp(34), font_size=sp(14), disabled=not ok)
                b_.bind(on_release=lambda _b, f=fn: f())
                row.add_widget(b_)
            card.add_widget(row)
            col.add_widget(card)

    def move(self, k, step):
        d = self.ed.scene["dialog"]
        self.ed.mutate(lambda: d.insert(k + step, d.pop(k)))
        self.fill()

    def delete(self, k):
        d = self.ed.scene["dialog"]
        self.ed.mutate(lambda: d.pop(k))
        self.fill()

    def edit(self, k):
        LineEditor(self, k).open()


class LineEditor:
    """Одна репліка: хто говорить, текст, вигляд хмаринки, голос."""

    def __init__(self, dlg, index):
        self.dlg = dlg
        self.ed = dlg.ed
        self.index = index
        sc = self.ed.scene
        src = sc["dialog"][index] if index is not None else None
        speakers = self.ed.speakers()
        default_speaker = speakers[1][0] if len(speakers) > 1 else None
        self.line = copy.deepcopy(src) if src else {"speaker": default_speaker, "text": "", "style": "say",
                                                    "voice": None, "voice_dur": None}
        self.rec = audio.Recorder()
        self.pb = None

        sv, col = scroll_column(8)
        self.mv = modal("Репліка", sv, on_close=self._stop_all)
        col.add_widget(section("Хто говорить"))
        ids = [u for u, _ in speakers]
        cur = ids.index(self.line.get("speaker")) if self.line.get("speaker") in ids else 0
        col.add_widget(chip_wrap([n for _, n in speakers], cur,
                                 lambda i: self.line.__setitem__("speaker", ids[i]), cols=2))
        col.add_widget(section("Текст репліки"))
        self.ti = TextInput(text=self.line.get("text", ""), font_size=sp(17), size_hint_y=None, height=dp(96),
                            background_color=theme.CARD, foreground_color=theme.TEXT,
                            cursor_color=theme.TEXT, hint_text="Наприклад: Привіт! Готові до пригод?",
                            hint_text_color=theme.MUTED)
        col.add_widget(self.ti)
        col.add_widget(section("Хмаринка"))
        skeys = [k for k, _ in model.BUBBLE_STYLES]
        col.add_widget(chip_wrap([n for _, n in model.BUBBLE_STYLES], skeys.index(self.line.get("style", "say")),
                                 lambda i: self.line.__setitem__("style", skeys[i]), cols=3))
        col.add_widget(section("Голос"))
        self.voice_lab = theme.label("", 14, size_hint_y=None, height=dp(24), halign="left")
        col.add_widget(self.voice_lab)
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.rec_btn = theme.button("● Записати голос", theme.RED, height=dp(52))
        self.rec_btn.bind(on_release=lambda *_: self.toggle_record())
        row.add_widget(self.rec_btn)
        self.play_btn = theme.button("▶", theme.CARD, size_hint_x=None, width=dp(56), height=dp(52),
                                     font_size=sp(20))
        self.play_btn.bind(on_release=lambda *_: self.listen())
        row.add_widget(self.play_btn)
        self.del_btn = theme.button("✕", theme.CARD, size_hint_x=None, width=dp(56), height=dp(52))
        self.del_btn.bind(on_release=lambda *_: self.remove_voice())
        row.add_widget(self.del_btn)
        col.add_widget(row)
        col.add_widget(theme.label("Поки репліка звучить, герой «говорить» — ворушить губами.", 13,
                                   color=theme.MUTED, size_hint_y=None, height=dp(36)))
        save = theme.button("Зберегти репліку", theme.GRAD, height=dp(52), bold=True)
        save.bind(on_release=lambda *_: self.save())
        col.add_widget(save)
        self._voice_ui()

    def open(self):
        self.mv.open()

    def _voice_ui(self):
        v = self.line.get("voice")
        if self.rec.active:
            self.voice_lab.text = "● Іде запис… говоріть"
        elif v:
            self.voice_lab.text = f"Записано: {self.line.get('voice_dur') or 0:.1f} с"
        else:
            self.voice_lab.text = "Без голосу — тільки текст у хмаринці"
        self.play_btn.disabled = not v or self.rec.active
        self.del_btn.disabled = not v or self.rec.active
        self.rec_btn.text = "■ Зупинити запис" if self.rec.active else "● Записати голос"

    def toggle_record(self):
        if not audio.available():
            self.ed.app.toast("Запис голосу працює лише на телефоні")
            return
        if self.rec.active:
            dur = self.rec.stop()
            if dur:
                rel = os.path.relpath(self.rec.path, self.ed.app.store.dir(self.ed.pid))
                self.line["voice"] = rel
                self.line["voice_dur"] = round(dur, 2)
            else:
                self.ed.app.toast("Запис закороткий")
            self._voice_ui()
            return
        if not audio.has_mic_permission():
            audio.request_mic_permission(self._perm)
            return
        self._start_rec()

    @mainthread
    def _perm(self, ok):
        if ok:
            self._start_rec()
        else:
            self.ed.app.toast("Без дозволу на мікрофон голос не записати")

    def _start_rec(self):
        d = self.ed.app.store.sub(self.ed.pid, "voices")
        path = os.path.join(d, f"v_{model.new_uid()}.m4a")
        try:
            self.rec.start(path)
        except Exception as e:  # noqa: BLE001
            self.ed.app.toast(f"Не вдалося почати запис: {e}")
        self._voice_ui()

    def listen(self):
        v = self.line.get("voice")
        if not v:
            return
        if self.pb:
            self.pb.stop()
        self.pb = audio.play_once(os.path.join(self.ed.app.store.dir(self.ed.pid), v))

    def remove_voice(self):
        self.line["voice"] = None
        self.line["voice_dur"] = None
        self._voice_ui()

    def _stop_all(self):
        if self.rec.active:
            self.rec.stop()
        if self.pb:
            self.pb.stop()

    def save(self):
        if self.rec.active:
            self.toggle_record()
        self.line["text"] = self.ti.text.strip()
        if not self.line["text"] and not self.line.get("voice"):
            self.ed.app.toast("Напишіть текст або запишіть голос")
            return
        d = self.ed.scene["dialog"]
        line = self.line
        if self.index is None:
            self.ed.mutate(lambda: d.append(line))
        else:
            k = self.index
            self.ed.mutate(lambda: d.__setitem__(k, line))
        self.mv.dismiss()
        self.dlg.fill()
