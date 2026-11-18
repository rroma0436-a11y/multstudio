"""Конструктор мультика: сцена 16:9, стрічка сцен, плитки «Персонажі / Діалог / Фон / Камера / Предмети / Звук»."""
import copy
import os
import threading
import time

from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle
from kivy.uix.widget import Widget
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput

import android_bridge as bridge
import acts
import audio
import motion
import tts
import voicefx
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
        self.rr = theme.paint(self, color, 16, outline=theme.LINE)
        self.base = color
        if image:
            self.img = Image(source=image, fit_mode="cover", nocache=True)
            self.add_widget(self.img)
        else:
            self.img = None
            self.add_widget(Label(text=icon, font_size=sp(34), color=theme.ACCENT))
        row = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(40))
        row.add_widget(theme.label(title, 15, True, halign="left", size_hint_y=None, height=dp(20)))
        self.sub = theme.label(sub, 12, color=theme.MUTED, halign="left", size_hint_y=None,
                               height=dp(18), shorten=True)
        row.add_widget(self.sub)
        self.add_widget(row)
        self.bind(state=self._st)

    def _st(self, *_):
        k = 0.88 if self.state == "down" else 1.0
        self.canvas.before.children[0].rgba = tuple(min(1, c * k) for c in self.base[:3]) + (1,)


class SceneCard(ButtonBehavior, BoxLayout):
    def __init__(self, index, source, selected, **kw):
        super().__init__(orientation="vertical", size_hint=(None, 1), width=dp(124),
                         padding=dp(4), spacing=dp(2), **kw)
        self.index = index
        theme.paint(self, theme.CARD_HI if selected else theme.CARD, 12,
                    outline=theme.ACCENT if selected else theme.LINE)
        self.img = Image(source=source, fit_mode="contain", nocache=True)
        self.add_widget(self.img)
        self.add_widget(theme.label(f"Сцена {index + 1}", 12, selected,
                                    color=theme.TEXT if selected else theme.MUTED,
                                    size_hint_y=None, height=dp(18), halign="center"))


def modal(title, body, on_close=None, full=True, done=True, on_done=None):
    """Повноекранне вікно: «‹ Назад», заголовок і «✓ Готово» (on_done — що робить «Готово»)."""
    mv = ModalView(size_hint=(1, 1) if full else (0.92, None), auto_dismiss=True)
    mv.background_color = (0, 0, 0, 0)
    mv.overlay_color = (0, 0, 0, 0.6)
    root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    theme.paint(root, theme.BG, 0 if full else 18)
    top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    top.add_widget(theme.back_button(mv.dismiss))
    top.add_widget(theme.label(title, 18, True, halign="left", valign="middle", shorten=True))
    if full and done:
        top.add_widget(theme.done_button(on_done or mv.dismiss))
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


class LiveView(Widget):
    """«Живий» перегляд сцени прямо в конструкторі: поверх сцени крутиться готовий кадр
    з діями, появою, ефектами й хмаринками. Дотик — повернутися до редагування."""

    def __init__(self, editor, **kw):
        super().__init__(size_hint=(None, None), **kw)
        self.ed = editor
        self.r = None
        self.t = 0.0
        self._ev = None
        self.opacity = 0
        with self.canvas:
            Color(1, 1, 1, 1)
            self.rect = Rectangle()
        self.bind(pos=self._upd, size=self._upd)

    @property
    def active(self):
        return self._ev is not None

    def fit(self, *_):
        st = self.ed.stage
        self.pos, self.size = st.pos, st.size

    def _upd(self, *_):
        self.rect.pos, self.rect.size = self.pos, self.size

    def start(self):
        ed = self.ed
        if self.r is None:
            self.r = FrameRenderer(ed.cat, (640, 360))
            self.rect.texture = self.r.texture
        self.r.project_dir = ed.app.store.dir(ed.pid)
        self.t = 0.0
        self.fit()
        self.opacity = 1
        if self._ev is None:
            self._ev = Clock.schedule_interval(self.tick, 1 / 30.0)
        self.tick(0)

    def stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        self.opacity = 0

    def tick(self, dt):
        ed = self.ed
        if ed.project is None:
            return
        sc = ed.scene
        length, _ = model.scene_timing(sc)
        self.t += min(dt, 0.1)
        if self.t > length + 0.8:
            self.t = 0.0
        try:
            self.r.render_scene(ed.project, ed.si, min(self.t, length - 0.001), length)
        except Exception:
            self.stop()
            return
        self.canvas.ask_update()

    def on_touch_down(self, touch):
        if self.active and self.collide_point(*touch.pos):
            if model.is_title(self.ed.scene):
                self.ed.open_title()
            else:
                self.ed.toggle_live()
            return True
        return False


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
        self.preview_pb = None

        root = BoxLayout(orientation="vertical")
        theme.paint(root, theme.BG)

        # --- верхня панель
        top = BoxLayout(size_hint_y=None, height=dp(56), padding=[dp(8), dp(6)], spacing=dp(6))
        top.add_widget(theme.back_button(self.leave, width=dp(94)))
        self.undo_btn = theme.button("↶", theme.CARD, size_hint_x=None, width=dp(46), height=dp(44),
                                     font_size=sp(22))
        self.undo_btn.color = theme.ACCENT
        self.undo_btn.bind(on_release=lambda *_: self.undo())
        top.add_widget(self.undo_btn)
        self.save_btn = theme.button("✓ Зберегти", theme.GREEN, height=dp(44), font_size=sp(15), bold=True)
        self.save_btn.bind(on_release=lambda *_: self.save())
        top.add_widget(self.save_btn)
        b = theme.button("▶ Перегляд", theme.GRAD, height=dp(44), font_size=sp(15), bold=True)
        b.bind(on_release=lambda *_: self.preview())
        top.add_widget(b)
        root.add_widget(top)
        trow = BoxLayout(size_hint_y=None, height=dp(30), padding=[dp(12), 0], spacing=dp(6))
        self.title_btn = Button(text="", font_size=sp(15), bold=True, color=theme.TEXT, halign="left",
                                valign="middle", shorten=True, background_normal="", background_down="",
                                background_color=(0, 0, 0, 0))
        self.title_btn.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.title_btn.bind(on_release=lambda *_: self.rename())
        trow.add_widget(self.title_btn)
        self.info = theme.label("", 12, color=theme.MUTED, halign="right", valign="middle", size_hint_x=0.8)
        trow.add_widget(self.info)
        root.add_widget(trow)

        # --- сцена
        self.stage = Stage(catalog=self.cat)
        self.stage.bind(on_before_change=self._before_change, on_change=self._changed,
                        on_double_tap=lambda s, sp_: self.pick_frame(), selected=self._update_sel)
        self.holder = StageHolder(self.stage, bg=theme.BG, size_hint_y=None)
        root.bind(width=lambda w, v: setattr(self.holder, "height", v * 9 / 16.0))
        root.add_widget(self.holder)
        self.live = LiveView(self)
        self.holder.add_widget(self.live)
        self.stage.bind(pos=self.live.fit, size=self.live.fit)

        # --- режим руху й інформація
        # «Ожити сцену» або (у ручному режимі) підказка «перетягніть, куди йде» з кнопкою «Готово»
        self.mode_box = BoxLayout(size_hint_y=None, height=dp(50), padding=[dp(8), dp(5)], spacing=dp(6))
        self.live_btn = theme.button("◉ Ожити сцену — подивитися, як рухаються", theme.GRAD4, height=dp(40),
                                     font_size=sp(14), bold=True)
        self.live_btn.bind(on_release=lambda *_: self.toggle_live())
        self.end_hint = theme.label("➜ Перетягніть героя туди, куди він має прийти", 13, True, color=theme.ACCENT,
                                    halign="left", valign="middle")
        self.end_done = theme.done_button(lambda: self.set_end_mode(False), width=dp(100), height=dp(40))
        self.mode_box.add_widget(self.live_btn)
        root.add_widget(self.mode_box)

        # --- дії з вибраним героєм
        self.sel_box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(48), padding=[dp(8), dp(4)],
                                 spacing=dp(4))
        root.add_widget(self.sel_box)
        self.sel_hint = theme.label("Додайте героя, торкніться його й натисніть «➜ Рух»", 13, color=theme.MUTED,
                                    halign="left", valign="middle")
        self.sel_actions = ScrollView(do_scroll_y=False, bar_width=0)
        row = BoxLayout(size_hint_x=None, spacing=dp(6))
        row.bind(minimum_width=row.setter("width"))
        self.frame_chip = None
        self.emo_sv = ScrollView(do_scroll_y=False, bar_width=0, size_hint_y=None, height=dp(42))
        self.emo_row = BoxLayout(size_hint_x=None, spacing=dp(6))
        self.emo_row.bind(minimum_width=self.emo_row.setter("width"))
        self.emo_sv.add_widget(self.emo_row)
        self.acts_sv = ScrollView(do_scroll_y=False, bar_width=0, size_hint_y=None, height=dp(46))
        self.acts_row = BoxLayout(size_hint_x=None, spacing=dp(6), padding=[0, dp(2)])
        self.acts_row.bind(minimum_width=self.acts_row.setter("width"))
        self.acts_sv.add_widget(self.acts_row)
        # швидкі кнопки: найчастіші дії одним дотиком (додаються в кінець ланцюжка)
        self.quick_sv = ScrollView(do_scroll_y=False, bar_width=0, size_hint_y=None, height=dp(46))
        qrow = BoxLayout(size_hint_x=None, spacing=dp(6), padding=[0, dp(2)])
        qrow.bind(minimum_width=qrow.setter("width"))
        for key in ("walk", "run", "jump", "sit", "lie", "happy", "bark", "talk", "spin", "paw", "sad", "sleep"):
            b = theme.chip("+ " + acts.label(key), height=dp(40))
            b.set_bg((1, 0.93, 0.8, 1))
            b.bind(on_release=lambda _b, k=key: self.quick_act(k))
            qrow.add_widget(b)
        more = theme.chip("Усі дії…", selected=True, height=dp(40))
        more.bind(on_release=lambda *_: self.add_act())
        qrow.add_widget(more)
        self.quick_sv.add_widget(qrow)
        # головні кнопки — завжди на виду; решта — у «⋯ Ще»
        for text, fn in (("✚ Дія", self.add_act), ("⇆ Дзеркало", self.flip), ("+ Більше", lambda: self.scale(1.15)),
                         ("− Менше", lambda: self.scale(1 / 1.15)), ("✕ Прибрати", self.delete_item),
                         ("⋯ Ще", self.more_actions)):
            c = theme.chip(text, selected=text.startswith("✚"))
            c.bind(on_release=lambda _b, f=fn: f())
            row.add_widget(c)
            if text.startswith("☺"):
                self.frame_chip = c
        self.sel_actions.size_hint_y = None
        self.sel_actions.height = dp(40)
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
        self.t_chars = Tile("Песик", "☺", sub="Додати песика на сцену", color=(1, 0.92, 0.82, 1))
        self.t_dialog = Tile("Діалог", "❝", sub="Репліки й голос", color=(0.87, 0.94, 1, 1))
        self.t_bg = Tile("Фон", "▦", sub="Місце й пора року", color=(0.86, 0.98, 0.88, 1))
        self.t_cam = Tile("Камера", "◎", sub="Рух і тривалість", color=(0.94, 0.9, 1, 1))
        self.t_obj = Tile("Предмети", "★", sub="Дерева, меблі, іграшки", color=(1, 0.97, 0.8, 1))
        self.t_sound = Tile("Звуки", "♫", sub="Ефекти, атмосфера, музика", color=(1, 0.89, 0.93, 1))
        self.t_fx = Tile("Ефекти й монтаж", "❄", sub="Сніг, фільтри, переходи", color=(0.85, 0.97, 1, 1))
        self.t_photo = Tile("Своє фото", "▣", sub="Фото з телефону як фон", color=(0.93, 1, 0.85, 1))
        for t, fn in ((self.t_chars, self.pick_character), (self.t_bg, self.pick_background),
                      (self.t_dialog, self.open_dialog), (self.t_sound, self.open_sound),
                      (self.t_obj, self.pick_object), (self.t_fx, self.open_effects),
                      (self.t_cam, self.open_camera), (self.t_photo, self.pick_photo)):
            t.bind(on_release=lambda _t, f=fn: self._tile(f))
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

    def open_project(self, pid, project=None):
        store = self.app.store
        if project is not None:
            self.project = project
        elif pid:
            try:
                self.project = store.load(pid)
            except (OSError, ValueError):
                self.app.toast("Не вдалося відкрити мультик")
                pid = None
        if not pid:
            pid = store.new_id()
            self.project = model.new_project(self.cat.default_background())
        self.pid = pid
        self.stage.project_dir = store.dir(pid)
        self.thumb_renderer = None
        self.undo_stack = []
        self.dirty = False
        self.si = 0
        self.set_end_mode(False, quiet=True)
        self.title_btn.text = "✎ " + (self.project.get("title") or "Мультик")
        self.load_current()
        self.refresh_strip(rethumb=True)

    def load_current(self):
        self.si = max(0, min(self.si, len(self.project["scenes"]) - 1))
        if model.is_title(self.scene):
            self.stage.load_scene({"background": self.cat.default_background(), "items": []})
            self.live.start()
        else:
            self.stage.load_scene(self.scene)
            if self.live.active:
                self.live.start()       # перезапуск з початку нової сцени
        self._update_info()
        self._update_sel()
        self._update_live_btn()

    def on_pre_enter(self, *_):
        if self.project is not None and model.is_title(self.scene):
            self.live.start()

    def on_leave(self, *_):
        self.live.stop()
        self._update_live_btn()

    def _update_live_btn(self):
        title = model.is_title(self.scene)
        self.live_btn.text = ("■ Зупинити й редагувати" if self.live.active and not title
                              else "◉ Ожити сцену — подивитися, як рухаються")
        self.live_btn.disabled = title
        self.mode_box.disabled = title

    def toggle_live(self):
        if model.is_title(self.scene):
            return
        if self.live.active:
            self.live.stop()
        else:
            self.stage.select(None)
            self.live.start()
            self.app.toast("Сцена ожила! Торкніться її, щоб знову редагувати.", 2.5)
        self._update_live_btn()

    def leave(self):
        self.live.stop()
        self.save(quiet=True)
        self.app.go("home")

    def save(self, quiet=False):
        if not self.dirty and quiet:
            return
        try:
            self.app.store.save(self.pid, self.project)
            r = getattr(self, "_save_r", None)
            if r is None:
                r = self._save_r = FrameRenderer(self.cat, (480, 270))
            r.project_dir = self.app.store.dir(self.pid)
            r.render_scene(self.project, 0, model.still_time(self.project["scenes"][0]), still=True)
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
        mv = modal("Назва мультика", wrap, done=False)

        def done(*_):
            t = ti.text.strip()
            if t:
                self.project["title"] = t
                self.title_btn.text = "✎ " + t
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
        n_fx = len(self.scene.get("sfx", []))
        amb = self.scene.get("ambience")
        parts = []
        if n_fx:
            parts.append(f"звуків: {n_fx}")
        if amb:
            parts.append("атмосфера")
        if self.project.get("music"):
            parts.append("музика")
        self.t_sound.sub.text = ", ".join(parts) if parts else "Ефекти, атмосфера, музика"
        bid = self.scene.get("background") or ""
        bg = self.cat.backgrounds.get(bid)
        self.t_bg.sub.text = bg["name"] if bg else ("Ваше фото" if bid.startswith("photo:") else "")
        parts = []
        for key, names in (("effect", model.EFFECTS), ("filter", model.FILTERS)):
            v = self.scene.get(key, "none")
            if v and v != "none":
                parts.append(dict(names).get(v, ""))
        parts.append(dict(model.TRANSITIONS).get(self.scene.get("transition", "fade"), ""))
        self.t_fx.sub.text = ", ".join(p for p in parts if p)
        self.undo_btn.disabled = not self.undo_stack

    def _tile(self, fn):
        if self.project and model.is_title(self.scene) and fn not in (self.open_effects, self.open_sound,
                                                                         self.open_camera):
            self.open_title()
            return
        fn()

    def _update_sel(self, *_):
        sel = self.stage.selected
        self.sel_box.clear_widgets()
        if self.project and model.is_title(self.scene):
            self.sel_hint.text = "Це титр. Торкніться сцени, щоб змінити напис і колір"
        else:
            has = bool(self.project and self.scene.get("items"))
            self.sel_hint.text = ("Торкніться песика — і додавайте йому дії кнопкою «✚ Дія»"
                                  if has else "Почніть з плитки «Песик» — додайте песика")
        if sel is None:
            self.sel_box.height = dp(48)
            self.sel_box.add_widget(self.sel_hint)
        else:
            self.sel_box.add_widget(self.sel_actions)
            if self.frame_chip is not None:
                self.frame_chip.disabled = sel.item["kind"] != "char"
            if sel.item["kind"] == "char":
                self._fill_acts(sel)
                self.sel_box.add_widget(self.acts_sv)
                self.sel_box.add_widget(self.quick_sv)
                self.sel_box.height = dp(150)
            else:
                self.sel_box.height = dp(48)

    # ================================================================== ланцюжок дій героя
    POSES = [("stand", "Стоїть", "side_calm"), ("sit", "Сидить", "sit"), ("lie", "Лежить", "lie")]

    def _fill_acts(self, sel):
        """Стрічка дій: «Спочатку: сидить» → 1. Встає → 2. Іде … → «✚ Дія»."""
        row = self.acts_row
        row.clear_widgets()
        it = sel.item
        pose = acts.start_pose(it)
        name = dict((k, n) for k, n, _ in self.POSES).get(pose, "Стоїть")
        b = theme.chip(f"Спочатку: {name.lower()}", height=dp(40))
        b.bind(on_release=lambda *_: self.cycle_start_pose())
        row.add_widget(b)
        for i, a in enumerate(it.get("acts", [])):
            extra = ""
            if a.get("a") in ("talk", "bark") and a.get("text"):
                extra = f" «{a['text'][:10]}»"
            elif a.get("dir") in ("left", "right"):
                extra = " ←" if a["dir"] == "left" else " →"
            c = theme.chip(f"{i + 1}. {acts.label(a.get('a'))}{extra}", height=dp(40))
            c.bind(on_release=lambda _b, i=i: self.edit_act(i))
            row.add_widget(c)
        add = theme.chip("✚ Дія", selected=True, height=dp(40))
        add.bind(on_release=lambda *_: self.add_act())
        row.add_widget(add)
        Clock.schedule_once(lambda dt: setattr(self.acts_sv, "scroll_x", 1), 0)

    def cycle_start_pose(self):
        sel = self._sel()
        if sel is None:
            return
        it = sel.item
        keys = [k for k, _, _ in self.POSES]
        frames = self.cat.characters[it["id"]]["frames"]
        cur = keys.index(acts.start_pose(it))
        for step in range(1, 4):
            k, _, fr = self.POSES[(cur + step) % 3]
            if fr in frames:
                break

        def do():
            it["frame"] = fr
            sel.reload()
            self.stage.layout()
        self.mutate(do)
        self._fill_acts(sel)

    def _acts_changed(self, sel):
        self._fill_acts(sel)
        self._update_info()
        if not self.live.active:
            self.toggle_live()
        else:
            self.live.start()
            self._update_live_btn()

    def clear_acts(self):
        sel = self._sel()
        if sel is None:
            return
        self.mutate(lambda: sel.item.__setitem__("acts", []))
        self._acts_changed(sel)

    def quick_act(self, key):
        sel = self._sel()
        if sel is None or sel.item["kind"] != "char":
            return
        it = sel.item

        def do():
            it.setdefault("acts", []).append(acts.new_act(key))
            it.pop("end", None)
            it.pop("motion", None)
        self.mutate(do)
        if key in ("talk", "bark"):
            Clock.schedule_once(lambda dt: self.edit_act(len(it["acts"]) - 1), 0.2)
        self._acts_changed(sel)

    def add_act(self):
        """Вибір дії кнопкою; дія додається в кінець ланцюжка."""
        sel = self._sel()
        if sel is None or sel.item["kind"] != "char":
            if sel is not None:
                self.open_motion()
            return
        it = sel.item
        sv, col = scroll_column(8)
        mv = None
        col.add_widget(theme.label(f"Що робить {self.cat.item_name(it)} далі? Дії йдуть одна за одною — "
                                   "програма сама з'єднає їх (наприклад, спершу встане, а потім піде).", 14,
                                   size_hint_y=None, height=dp(50)))

        def pick(key):
            mv.dismiss()

            def do():
                it.setdefault("acts", []).append(acts.new_act(key))
                it.pop("end", None)
                it.pop("motion", None)
            self.mutate(do)
            if key in ("talk", "bark"):
                Clock.schedule_once(lambda dt: self.edit_act(len(it["acts"]) - 1), 0.2)
            self._acts_changed(sel)
        for g in acts.GROUPS:
            keys = [k for k, v in acts.ACTIONS.items() if v[1] == g]
            if not keys:
                continue
            col.add_widget(section(g))
            col.add_widget(chip_wrap([acts.label(k) for k in keys], -1, lambda i, keys=keys: pick(keys[i]),
                                     cols=3, height=50))
        mv = modal("Додати дію", sv)
        mv.open()

    def edit_act(self, i):
        sel = self._sel()
        if sel is None:
            return
        it = sel.item
        lst = it.get("acts", [])
        if not 0 <= i < len(lst):
            return
        a = lst[i]
        key = a.get("a")
        spec = acts.ACTIONS.get(key, ("", "", 2.0, None, None, 0))
        sv, col = scroll_column(10)
        vals = dict(a)
        mv = None
        clip = (self.cat.characters[it["id"]].get("cycles") or {}).get(key)
        if not (clip and clip.get("once")):
            col.add_widget(section("Скільки триває"))
            lab = theme.label("", 15, True, size_hint_y=None, height=dp(24), halign="center")
            sl = Slider(min=0.5, max=10, step=0.5, value=float(a.get("dur", spec[2])), size_hint_y=None,
                        height=dp(44), cursor_size=(dp(28), dp(28)))

            def upd(*_):
                lab.text = f"{sl.value:.1f} с"
                vals["dur"] = sl.value
            sl.bind(value=upd)
            upd()
            col.add_widget(lab)
            col.add_widget(sl)
        if key in acts.MOVES or key in ("wait", "happy", "talk", "bark", "jump", "spin", "dance"):
            col.add_widget(section("Куди дивиться / куди йде"))
            dkeys = [None, "left", "right"]
            col.add_widget(chip_wrap(["Як зараз", "← Вліво", "Вправо →"], dkeys.index(a.get("dir")),
                                     lambda k: vals.__setitem__("dir", dkeys[k]), cols=3))
        ti = None
        if key in ("talk", "bark"):
            col.add_widget(section("Що каже (у хмаринці)"))
            ti = TextInput(text=a.get("text", ""), multiline=False, font_size=sp(17), size_hint_y=None,
                           height=dp(50), background_color=theme.CARD, foreground_color=theme.TEXT,
                           cursor_color=theme.TEXT)
            col.add_widget(ti)
            skeys = [k for k, _ in model.BUBBLE_STYLES]
            col.add_widget(chip_wrap([n for _, n in model.BUBBLE_STYLES],
                                     skeys.index(a.get("style", "say")) if a.get("style", "say") in skeys else 0,
                                     lambda k: vals.__setitem__("style", skeys[k]), cols=3))
            # озвучка тексту синтезом мовлення
            col.add_widget(section("Озвучити голосом"))
            vkeys = [k for k, _ in voicefx.VOICES]
            vstate = {"voice": a.get("tts_voice", "cartoon")}
            col.add_widget(chip_wrap([n for _, n in voicefx.VOICES],
                                     vkeys.index(vstate["voice"]) if vstate["voice"] in vkeys else 0,
                                     lambda k: vstate.__setitem__("voice", vkeys[k]), cols=3))
            vlab = theme.label("З голосом" if a.get("voice") else "Поки без голосу — лише хмаринка", 13,
                               color=theme.MUTED, size_hint_y=None, height=dp(24), halign="left")
            vrow = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
            sb = theme.button("♪ Озвучити", theme.GRAD3, height=dp(50), bold=True)
            pb = theme.button("▶ Слухати", theme.CARD, height=dp(50), disabled=not a.get("voice"))
            xb = theme.button("✕ Без голосу", theme.CARD, height=dp(50), disabled=not a.get("voice"))
            base = self.app.store.dir(self.pid)

            def spoken(ok, val, rel):
                if not ok:
                    vlab.text = str(val)
                    self.app.toast(str(val), 5)
                    sb.disabled = False
                    return
                for d in (a, vals):
                    d["voice"], d["voice_dur"], d["tts_voice"] = rel, round(val, 2), vstate["voice"]
                vlab.text = f"Озвучено: {val:.1f} с"
                sb.disabled = False
                pb.disabled = xb.disabled = False
                self.dirty = True
                audio.play_once(os.path.join(base, rel))

            def speak(*_):
                text = ti.text.strip()
                if not text:
                    self.app.toast("Спершу напишіть, що каже песик")
                    return
                rel = os.path.join("voices", f"tts_{model.new_uid()}.wav")
                self.app.store.sub(self.pid, "voices")
                vlab.text = "Озвучую…"
                sb.disabled = True
                tts.speak_to_file(text, os.path.join(base, rel), lambda ok, v: spoken(ok, v, rel),
                                  vstate["voice"])

            def listen(*_):
                v = vals.get("voice") or a.get("voice")
                if v:
                    audio.play_once(os.path.join(base, v))

            def unvoice(*_):
                for d in (a, vals):
                    d["voice"] = None
                    d["voice_dur"] = None
                vlab.text = "Без голосу — лише хмаринка"
                pb.disabled = xb.disabled = True
            sb.bind(on_release=speak)
            pb.bind(on_release=listen)
            xb.bind(on_release=unvoice)
            vrow.add_widget(sb)
            vrow.add_widget(pb)
            vrow.add_widget(xb)
            col.add_widget(vrow)
            col.add_widget(vlab)
        row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        for text, fn in (("◀ Раніше", lambda: self._move_act(i, -1)), ("Пізніше ▶", lambda: self._move_act(i, 1)),
                         ("✕ Прибрати", lambda: self._del_act(i))):
            b = theme.button(text, theme.RED if text.startswith("✕") else theme.CARD, height=dp(50))
            b.bind(on_release=lambda _b, f=fn: (mv.dismiss(), f()))
            row.add_widget(b)
        col.add_widget(row)

        def apply():
            if ti is not None:
                vals["text"] = ti.text.strip()

            def do():
                if 0 <= i < len(it.get("acts", [])) and it["acts"][i] is a:
                    a.update(vals)
            self.mutate(do)
            self._acts_changed(sel)
        mv = modal(f"{i + 1}. {acts.label(key)}", sv, on_done=None)
        mv.bind(on_dismiss=lambda *_: apply() if not getattr(mv, "_skip", False) else None)
        mv.open()

    def _move_act(self, i, step):
        sel = self._sel()
        lst = sel.item.get("acts", []) if sel else []
        j = i + step
        if sel is None or not (0 <= j < len(lst)):
            return
        self.mutate(lambda: lst.insert(j, lst.pop(i)))
        self._acts_changed(sel)

    def _del_act(self, i):
        sel = self._sel()
        lst = sel.item.get("acts", []) if sel else []
        if sel is None or not (0 <= i < len(lst)):
            return
        self.mutate(lambda: lst.pop(i))
        self._acts_changed(sel)

    EMOTIONS = [("front34_calm", "Спокій"), ("front34_happy", "Радість"), ("front34_laughing", "Сміх"),
                ("front34_talking", "Говорить"), ("front34_surprised", "Подив"), ("front34_sad", "Сум"),
                ("front34_crying", "Плач"), ("front34_scared", "Страх"), ("front34_angry", "Злість"),
                ("front34_thinking", "Думає"), ("front34_sleeping", "Спить"), ("front_calm", "Прямо"),
                ("front_stand", "Прямо"), ("side_calm", "Боком"), ("back", "Спиною"), ("sit", "Сидить"),
                ("lie", "Лежить"), ("flying_calm", "Летить"), ("stand", "Стоїть")]

    def _fill_emotions(self, sel):
        """Кнопки емоцій і поз вибраного героя — одним дотиком."""
        self.emo_row.clear_widgets()
        frames = self.cat.characters[sel.item["id"]]["frames"]
        cur = sel.item.get("frame")
        seen = set()
        for key, name in self.EMOTIONS:
            if key not in frames or name in seen:
                continue
            seen.add(name)
            c = theme.chip(name, selected=(key == cur), height=dp(38))
            c.bind(on_release=lambda _b, k=key: self._set_emotion(k))
            self.emo_row.add_widget(c)

    def _set_emotion(self, key):
        sel = self._sel()
        if sel is None:
            return

        def do():
            sel.item["frame"] = key
            sel.item.pop("ride_frame_from", None)
            sel.reload()
            self.stage.layout()
        self.mutate(do)
        self._fill_emotions(sel)

    def set_end_mode(self, on, quiet=False):
        """Ручний режим «куди йде»: перетягуємо героя в кінцеву точку руху."""
        self.stage.mode = "end" if on else "start"
        self.mode_box.clear_widgets()
        if on:
            self.live.stop()
            self.mode_box.add_widget(self.end_hint)
            self.mode_box.add_widget(self.end_done)
        else:
            self.mode_box.add_widget(self.live_btn)
        if not quiet:
            self._update_live_btn()

    def more_actions(self):
        sel = self._sel()
        if sel is None:
            return
        sv, col = scroll_column(8)
        mv = None
        acts_ = [("◐ Поява й зникнення", self.open_show, True),
                ("⇄ Замінити на іншого героя", self.replace_item, len(self.cat.stars) > 1 or sel.item["kind"] == "obj"),
                ("☺ Усі емоції й пози (картинками)", self.pick_frame, sel.item["kind"] == "char"),
                ("✚ Зробити копію", self.duplicate_item, True),
                ("▲ Поставити наперед", lambda: self.layer(1), True),
                ("▼ Поставити позаду", lambda: self.layer(-1), True),
                ("➜ Вказати вручну, куди йде", lambda: self.set_end_mode(True), sel.item["kind"] != "char"),
                ("↺ Прибрати рух", self.clear_motion, sel.item["kind"] != "char"),
                ("✕ Прибрати всі дії песика", self.clear_acts, sel.item["kind"] == "char")]
        acts_ = [a for a in acts_ if a[2]]
        for text, fn, ok in acts_:
            b = theme.button(text, theme.CARD, height=dp(52), font_size=sp(16))
            b.bind(on_release=lambda _b, f=fn: (mv.dismiss(), f()))
            col.add_widget(b)
        mv = modal("Ще дії", sv, done=False)
        mv.open()

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
            self.thumb_renderer = FrameRenderer(self.cat, (256, 144), self.app.store.dir(self.pid))
        try:
            self.thumb_renderer.render_scene(self.project, i, model.still_time(self.project["scenes"][i]),
                                             still=True)
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
                    sc["sfx"] = []
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
               ratio=0.5625, fit="cover", min_cell=dp(150),
               extra=("▣ Своє фото з телефону", self.pick_photo)).open()

    def pick_photo(self):
        """Фото з телефону стає фоном сцени (його можна «оживити» камерою, ефектами й героями)."""
        self.app.toast("Виберіть фото…", 1.5)
        bridge.pick_image(self.app.store.sub(self.pid, "photos"), self._photo_picked)

    def _photo_picked(self, name):
        if not name:
            self.app.toast("Фото не вибрано")
            return
        self.mutate(lambda: self.stage.set_background("photo:photos/" + name))
        self.refresh_strip(only=self.si)

    def pick_character(self):
        stars = self.cat.stars
        if len(stars) == 1:
            self._add("char", stars[0]["id"])       # герой один — додаємо одразу
            self.app.toast("Песик на сцені! Натисніть «✚ Дія», щоб він щось зробив.", 3)
            return
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
        if kind == "char":
            item["anim"] = "alive"
            if "side_calm" in self.cat.characters[oid]["frames"]:
                item["frame"] = "side_calm"
            item["acts"] = []
        if self.stage.mode == "end":
            self.set_end_mode(False, quiet=True)
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
        sel = self._sel()
        if sel is not None:
            it = sel.item
            self.mutate(lambda: motion.apply(self.cat, self.scene, it, "stand"), reload_stage=True)

    def delete_item(self):
        if self._sel() is not None:
            self.mutate(self.stage.remove_selected)

    def open_motion(self):
        """Рух однією кнопкою: програма сама задає шлях, кадри й транспорт."""
        sel = self._sel()
        if sel is None:
            return
        it = sel.item
        keys = motion.available(self.cat, it)
        names = dict(motion.MOTIONS)
        sv, col = scroll_column(10)
        col.add_widget(theme.label(f"Що робить {self.cat.item_name(it)}? Виберіть — і програма сама "
                                   "все зробить: куди йти, як бігти, на чому їхати.", 14,
                                   size_hint_y=None, height=dp(48)))
        mv = None
        cur = motion.current(it)

        def pick(i):
            key = keys[i]
            mv.dismiss()
            hint = []

            def do():
                hint.append(motion.apply(self.cat, self.scene, it, key))
            self.mutate(do, reload_stage=True)
            self.refresh_strip(only=self.si)
            if key != "stand":
                if not self.live.active:
                    self.toggle_live()
                else:
                    self.live.start()
                    self._update_live_btn()
            if hint and hint[0]:
                self.app.toast(hint[0], 3)
        col.add_widget(chip_wrap([names[k] for k in keys], keys.index(cur) if cur in keys else 0, pick,
                                 cols=2, height=52))
        col.add_widget(theme.label("Напрямок — туди, куди дивиться герой (кнопка «⇆ Дзеркало»). "
                                   "Санчата, коня чи дракона можна потім замінити чи прибрати.", 13,
                                   color=theme.MUTED, size_hint_y=None, height=dp(54)))
        mv = modal("Рух", sv)
        mv.open()

    def replace_item(self):
        """Замінити героя (чи предмет) на іншого — місце, дія, рух і репліки залишаються.
        Заміна робиться в усіх сценах, де був цей самий герой (зручно для шаблонів)."""
        sel = self._sel()
        if sel is None:
            return
        old = sel.item
        kind = old["kind"]
        cats = self.cat.character_categories if kind == "char" else self.cat.object_categories
        tabs = []
        for c in cats:
            src = self.cat.chars_in(c["id"]) if kind == "char" else self.cat.objects_in(c["id"])
            items = [(self.cat.abspath(o["thumb"]), o["name"], o["id"]) for o in src]
            if items:
                tabs.append((c["name"], items))

        def apply(new_id):
            old_id = old["id"]

            def do():
                n = 0
                for sc in self.project["scenes"]:
                    for it in sc.get("items", []):
                        if it["kind"] == kind and it["id"] == old_id:
                            it["id"] = new_id
                            if kind == "char":
                                frames = self.cat.characters[new_id]["frames"]
                                if it.get("frame") not in frames:
                                    it["frame"] = self.cat.default_frame(new_id)
                            n += 1
                return n
            self.mutate(do, reload_stage=True)
            self.refresh_strip(rethumb=True)
            self.app.toast("Замінено в усіх сценах")
        Picker("Замінити на…", tabs, apply).open()

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
        cur_cam = sc.get("camera", "none")
        col.add_widget(chip_wrap([n for _, n in model.CAMERA_MOVES],
                                 keys.index(cur_cam) if cur_cam in keys else 0, set_cam, cols=2))
        heroes = [(it["uid"], self.cat.item_name(it)) for it in sc["items"]]
        if heroes:
            col.add_widget(section("На кого дивиться камера (для «на героя»)"))
            uids = [u for u, _ in heroes]
            sel = self.stage.selected
            if sc.get("focus") not in uids:
                sc["focus"] = sel.item["uid"] if sel is not None else uids[0]
            col.add_widget(chip_wrap([n for _, n in heroes], uids.index(sc["focus"]),
                                     lambda i: self.mutate(lambda: sc.__setitem__("focus", uids[i])), cols=2))
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

    # ================================================================== ефекти й монтаж
    def open_effects(self):
        sv, col = scroll_column(10)
        sc = self.scene

        def chooser(title, options, key, default, cols):
            col.add_widget(section(title))
            ks = [k for k, _ in options]
            cur = sc.get(key, default)
            col.add_widget(chip_wrap([n for _, n in options], ks.index(cur) if cur in ks else 0,
                                     lambda i: self.mutate(lambda: sc.__setitem__(key, ks[i])), cols=cols))
        chooser("Ефект у кадрі", model.EFFECTS, "effect", "none", 2)
        chooser("Фільтр кольору", model.FILTERS, "filter", "none", 3)
        chooser("Перехід до цієї сцени", model.TRANSITIONS, "transition", "fade", 2)
        col.add_widget(section("Титри"))
        mv = None
        scenes = self.project["scenes"]
        if not (scenes and model.is_title(scenes[0]) and not scenes[0].get("ending")):
            b = theme.button("✚ Назва мультика на початку", theme.GRAD2, bold=True)
            b.bind(on_release=lambda *_: (mv.dismiss(), self.add_title(False)))
            col.add_widget(b)
        if not (scenes and model.is_title(scenes[-1]) and scenes[-1].get("ending")):
            b = theme.button("✚ «Кінець» наприкінці", theme.GRAD4, bold=True)
            b.bind(on_release=lambda *_: (mv.dismiss(), self.add_title(True)))
            col.add_widget(b)
        col.add_widget(theme.label("Подивитися результат — кнопка «▶ Перегляд» угорі.", 13,
                                   color=theme.MUTED, size_hint_y=None, height=dp(30)))
        mv = modal("Ефекти й монтаж", sv)
        mv.open()

    # ================================================================== титри
    def add_title(self, ending):
        def do():
            if ending:
                self.project["scenes"].append(model.new_title("Кінець", "", "night", ending=True))
                self.si = len(self.project["scenes"]) - 1
            else:
                self.project["scenes"].insert(0, model.new_title(self.project.get("title") or "Мій мультик",
                                                                 "", "sunset"))
                self.si = 0
        self.live.stop()
        self.mutate(do, reload_stage=True)
        self.refresh_strip(rethumb=True)
        Clock.schedule_once(lambda dt: self.open_title(), 0.2)

    def open_title(self):
        sc = self.scene
        if not model.is_title(sc):
            return
        sv, col = scroll_column(10)
        vals = {"text": sc.get("text", ""), "sub": sc.get("sub", ""), "color": sc.get("color", "sunset"),
                "duration": float(sc.get("duration", 3.0))}
        col.add_widget(section("Великий напис"))
        t1 = TextInput(text=vals["text"], multiline=False, font_size=sp(18), size_hint_y=None, height=dp(50),
                       background_color=theme.CARD, foreground_color=theme.TEXT, cursor_color=theme.TEXT)
        col.add_widget(t1)
        col.add_widget(section("Маленький підпис (можна порожнім)"))
        t2 = TextInput(text=vals["sub"], multiline=False, font_size=sp(16), size_hint_y=None, height=dp(46),
                       background_color=theme.CARD, foreground_color=theme.TEXT, cursor_color=theme.TEXT,
                       hint_text="Наприклад: Автор — Софійка, 5 років", hint_text_color=theme.MUTED)
        col.add_widget(t2)
        col.add_widget(section("Колір тла"))
        keys = [c[0] for c in model.TITLE_COLORS]
        col.add_widget(chip_wrap([c[1] for c in model.TITLE_COLORS],
                                 keys.index(vals["color"]) if vals["color"] in keys else 0,
                                 lambda i: vals.__setitem__("color", keys[i]), cols=3))
        col.add_widget(section("Скільки триває"))
        lab = theme.label("", 15, True, size_hint_y=None, height=dp(24), halign="center")
        sl = Slider(min=1.5, max=8, step=0.5, value=vals["duration"], size_hint_y=None, height=dp(44),
                    cursor_size=(dp(28), dp(28)))
        sl.bind(value=lambda w, v: setattr(lab, "text", f"{v:.1f} с"))
        lab.text = f"{sl.value:.1f} с"
        col.add_widget(lab)
        col.add_widget(sl)
        col.add_widget(theme.label("Блискітки, сніг чи зірочки — у плитці «Ефекти й монтаж».", 13,
                                   color=theme.MUTED, size_hint_y=None, height=dp(30)))

        def apply():
            def do():
                sc["text"] = t1.text.strip()
                sc["sub"] = t2.text.strip()
                sc["color"] = vals["color"]
                sc["duration"] = sl.value
            self.mutate(do)
        modal("Титр", sv, on_close=apply).open()

    # ================================================================== дія й поява вибраного
    def open_anim(self):
        sel = self._sel()
        if sel is None:
            return
        it = sel.item
        keys = [k for k, _ in model.ANIMS]
        sv, col = scroll_column(10)
        col.add_widget(theme.label("Що робить " + self.cat.item_name(it) + " у цій сцені? Якщо герой іде, "
                                   "дія почнеться, коли він зупиниться.", 14, size_hint_y=None, height=dp(44)))
        cur = it.get("anim", "none")
        mv = None

        def pick(i):
            def do():
                it["anim"] = keys[i]
            self.mutate(do)
        col.add_widget(chip_wrap([n for _, n in model.ANIMS], keys.index(cur) if cur in keys else 0, pick,
                                 cols=2, height=50))
        col.add_widget(section("Як рухається до кінця руху"))
        pkeys = [k for k, _ in model.PATHS]
        pcur = it.get("path", "line")

        def pick_path(i):
            def do():
                it["path"] = pkeys[i]
            self.mutate(do)
        col.add_widget(chip_wrap([n for _, n in model.PATHS], pkeys.index(pcur) if pcur in pkeys else 0,
                                 pick_path, cols=2))
        col.add_widget(theme.label("Шлях працює, коли героєві задано «➜ Кінець руху».", 13, color=theme.MUTED,
                                   size_hint_y=None, height=dp(24)))
        mv = modal("Дія й рух", sv)
        mv.open()

    def open_show(self):
        sel = self._sel()
        if sel is None:
            return
        it = sel.item
        sc = self.scene
        length, _ = model.scene_timing(sc)
        sv, col = scroll_column(10)
        vals = {}

        def block(title, options, fx_key, at_key, default_at):
            col.add_widget(section(title))
            ks = [k for k, _ in options]
            cur = it.get(fx_key, "none")
            vals[fx_key] = cur if cur in ks else "none"
            col.add_widget(chip_wrap([n for _, n in options], ks.index(vals[fx_key]),
                                     lambda i: vals.__setitem__(fx_key, ks[i]), cols=2))
            lab = theme.label("", 14, size_hint_y=None, height=dp(24), halign="left")
            sl = Slider(min=0, max=max(0.5, length - 0.5), step=0.1,
                        value=min(float(it.get(at_key, default_at) or 0), max(0.5, length - 0.5)),
                        size_hint_y=None, height=dp(44), cursor_size=(dp(28), dp(28)))

            def upd(*_):
                lab.text = f"Коли: на {sl.value:.1f} с від початку сцени"
                vals[at_key] = round(sl.value, 2)
            sl.bind(value=upd)
            upd()
            col.add_widget(lab)
            col.add_widget(sl)
        block("Як з'являється", model.APPEAR, "in_fx", "in_at", 0.0)
        block("Як зникає", model.VANISH, "out_fx", "out_at", max(0.5, length - 1.0))

        def closed():
            def do():
                for k, v in vals.items():
                    it[k] = v
                if it.get("in_fx", "none") != "none" and it.get("out_fx", "none") != "none" \
                        and it["out_at"] < it["in_at"] + 0.6:
                    it["out_at"] = round(it["in_at"] + 0.6, 2)
            self.mutate(do)
        modal("Поява й зникнення", sv, on_close=closed).open()

    # ================================================================== звуки
    def preview_sound(self, path):
        if self.preview_pb is None:
            self.preview_pb = audio.Playback()
        self.preview_pb.stop()
        self.preview_pb._play(path)

    def stop_preview(self):
        if self.preview_pb is not None:
            self.preview_pb.stop()

    def open_sound(self):
        SoundsEditor(self).open()

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
        self.live.stop()
        self._update_live_btn()
        self.save(quiet=True)
        self.app.open_player(self.pid, self.project, self.si)

    def export_still(self):
        try:
            r = FrameRenderer(self.cat, (1920, 1080), self.app.store.dir(self.pid))
            r.render_scene(self.project, self.si, model.still_time(self.scene), still=True)
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
        if len({ln.get("speaker") for ln in sc["dialog"] if ln.get("speaker")}) >= 1:
            conv = theme.button("☺ ☺  Розставити героїв для розмови", theme.GRAD3, bold=True)
            conv.bind(on_release=lambda *_: self.arrange())
            col.add_widget(conv)
            col.add_widget(theme.label("Герої стануть обличчям одне до одного, а камера сама підлітатиме "
                                       "до того, хто говорить.", 13, color=theme.MUTED, size_hint_y=None,
                                       height=dp(36)))
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

    def arrange(self):
        """Розмова: ті, хто говорить, — у ряд обличчям одне до одного; камера — на того, хто говорить."""
        sc = self.ed.scene
        order = []
        for ln in sc["dialog"]:
            u = ln.get("speaker")
            if u and u not in order:
                order.append(u)
        items = {it["uid"]: it for it in sc["items"]}
        order = [u for u in order if u in items]
        if not order:
            return
        n = len(order)
        xs = [0.5] if n == 1 else [0.22 + 0.56 * k / (n - 1) for k in range(n)]

        def do():
            for k, u in enumerate(order):
                it = items[u]
                it["x"], it["y"] = xs[k], 0.07
                it.pop("end", None)
                it["flip"] = xs[k] > 0.5          # усі герої намальовані обличчям праворуч
                if it.get("frame", "").startswith(("side", "back", "walk", "run")):
                    it["frame"] = self.ed.cat.default_frame(it["id"])
                if it.get("anim", "none") == "none":
                    it["anim"] = "alive"
            sc["camera"] = "talk"
        self.ed.mutate(do, reload_stage=True)
        self.ed.app.toast("Готово! Натисніть «◉ Ожити» чи «▶ Перегляд», щоб подивитися розмову.", 3)
        self.fill()

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
        self.mv = modal("Репліка", sv, on_close=self._stop_all, on_done=self.save)
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
        self.tts_btn = theme.button("♪ Озвучити текст штучним голосом", theme.GRAD3, height=dp(50), bold=True)
        self.tts_btn.bind(on_release=lambda *_: self.speak_text())
        col.add_widget(self.tts_btn)
        col.add_widget(section("Змінити голос"))
        vkeys = [k for k, _ in voicefx.VOICES]
        vcur = self.line.get("voice_fx", "normal")
        self.voice_chips = chip_wrap([n for _, n in voicefx.VOICES], vkeys.index(vcur) if vcur in vkeys else 0,
                                     lambda i: self.set_voice(vkeys[i]), cols=3)
        col.add_widget(self.voice_chips)
        col.add_widget(theme.label("Спершу запишіть голос, потім виберіть, яким він має звучати. "
                                   "Поки репліка звучить, герой «говорить» — ворушить губами.", 13,
                                   color=theme.MUTED, size_hint_y=None, height=dp(54)))
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
        if hasattr(self, "voice_chips"):
            self.voice_chips.disabled = not v or self.rec.active
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
                self.line.pop("voice_src", None)
                self.line["voice_fx"] = "normal"
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

    def speak_text(self):
        """Озвучити текст репліки синтезом мовлення (замість запису з мікрофона)."""
        text = self.ti.text.strip()
        if not text:
            self.ed.app.toast("Спершу напишіть текст репліки")
            return
        self.ed.app.store.sub(self.ed.pid, "voices")
        rel = os.path.join("voices", f"tts_{model.new_uid()}.wav")
        path = os.path.join(self.ed.app.store.dir(self.ed.pid), rel)
        self.voice_lab.text = "Озвучую…"
        self.tts_btn.disabled = True

        def done(ok, val):
            self.tts_btn.disabled = False
            if not ok:
                self.voice_lab.text = str(val)
                self.ed.app.toast(str(val), 5)
                return
            self.line["voice"] = rel
            self.line["voice_dur"] = round(val, 2)
            self.line.pop("voice_src", None)
            self.line["voice_fx"] = "normal"
            self._voice_ui()
            self.listen()
        tts.speak_to_file(text, path, done, "normal")

    def set_voice(self, kind):
        src = self.line.get("voice_src") or self.line.get("voice")
        if not src:
            return
        base = self.ed.app.store.dir(self.ed.pid)
        if kind == "normal":
            self.line["voice"] = src
            self.line.pop("voice_src", None)
            self.line["voice_fx"] = "normal"
            try:
                self.line["voice_dur"] = round(audio.duration(os.path.join(base, src)) or
                                               self.line.get("voice_dur") or 1.0, 2)
            except Exception:
                pass
            self._voice_ui()
            self.listen()
            return
        if not audio.available():
            self.ed.app.toast("Змінювати голос можна лише на телефоні")
            return
        self.voice_lab.text = "Змінюю голос…"
        out_rel = os.path.join("voices", f"fx_{model.new_uid()}_{kind}.wav")

        def work():
            try:
                x = audio.decode_pcm(os.path.join(base, src))
                y = voicefx.process(x, kind, audio.RATE)
                dur = voicefx.write_wav(os.path.join(base, out_rel), y, audio.RATE)
                ok = True
            except Exception as e:  # noqa: BLE001
                ok, dur = False, str(e)
            finally:
                try:
                    from jnius import detach
                    detach()
                except Exception:
                    pass
            self._voice_done(ok, kind, src, out_rel, dur)
        threading.Thread(target=work, daemon=True).start()

    @mainthread
    def _voice_done(self, ok, kind, src, out_rel, dur):
        if not ok:
            self.ed.app.toast(f"Не вдалося змінити голос: {dur}")
            self._voice_ui()
            return
        self.line["voice_src"] = src
        self.line["voice"] = out_rel
        self.line["voice_dur"] = round(dur, 2)
        self.line["voice_fx"] = kind
        self._voice_ui()
        self.listen()

    def remove_voice(self):
        self.line["voice"] = None
        self.line["voice_dur"] = None
        self.line.pop("voice_src", None)
        self.line["voice_fx"] = "normal"
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


# ====================================================================== звуки
from kivy.lang import Builder  # noqa: E402
from kivy.properties import ObjectProperty, StringProperty  # noqa: E402
from kivy.uix.recycleview import RecycleView  # noqa: E402

Builder.load_string("""
<SoundRow>:
    size_hint_y: None
    height: dp(56)
    padding: dp(8), dp(5)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.x, self.y + dp(2)
            size: self.width, self.height - dp(4)
            radius: [dp(12)]
    Label:
        text: root.text
        font_size: sp(15)
        color: 0.14, 0.13, 0.26, 1
        halign: 'left'
        valign: 'middle'
        text_size: self.size
        shorten: True
    Button:
        text: '\u25b6'
        size_hint_x: None
        width: dp(48)
        font_size: sp(18)
        background_normal: ''
        color: 0.4, 0.38, 1, 1
        background_color: 0.88, 0.9, 1, 1
        on_release: root.picker.listen(root.sid)
    Button:
        text: 'Додати'
        size_hint_x: None
        width: dp(92)
        font_size: sp(15)
        background_normal: ''
        background_color: 0.4, 0.38, 1, 1
        on_release: root.picker.choose(root.sid)

<SoundList>:
    viewclass: 'SoundRow'
    bar_width: dp(4)
    RecycleBoxLayout:
        orientation: 'vertical'
        default_size: None, dp(56)
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        spacing: dp(4)
""")


class SoundRow(BoxLayout):
    text = StringProperty("")
    sid = StringProperty("")
    picker = ObjectProperty(None, allownone=True)


class SoundList(RecycleView):
    pass


class SoundPicker:
    """Вибір звуку з бібліотеки: вкладки-категорії, ▶ — прослухати, «Додати» — вибрати."""

    def __init__(self, editor, categories, callback, title="Звуки"):
        self.ed = editor
        self.lib = editor.app.sounds
        self.callback = callback
        self.tabs = [c for c in self.lib.categories if c["id"] in categories and self.lib.in_category(c["id"])]
        body = BoxLayout(orientation="vertical", spacing=dp(6))
        if len(self.tabs) > 1:
            body.add_widget(ChipRow([c["name"] for c in self.tabs], self.show))
        self.list = SoundList()
        body.add_widget(self.list)
        self.mv = modal(title, body, on_close=editor.stop_preview)
        self.show(0)

    def open(self):
        self.mv.open()

    def show(self, i):
        items = sorted(self.lib.in_category(self.tabs[i]["id"]), key=lambda s: s["name"])
        self.list.data = [{"text": f"{s['name']}  · {s['dur']:.1f} с", "sid": s["id"], "picker": self} for s in items]
        self.list.scroll_y = 1

    def listen(self, sid):
        if not audio.available():
            self.ed.app.toast("Звук працює лише на телефоні")
            return
        self.ed.preview_sound(self.lib.path(sid))

    def choose(self, sid):
        self.mv.dismiss()
        self.callback(sid)


FX_CATEGORIES = ("animals", "people", "steps", "home", "hits", "magic", "scifi", "game", "jingles")


class SoundsEditor:
    """Звуки сцени (ефекти в потрібний момент), атмосфера сцени, музика мультика, автоматичні кроки."""

    def __init__(self, editor):
        self.ed = editor
        self.lib = editor.app.sounds
        self.sv, self.col = scroll_column(8)
        self.mv = modal(f"Звуки · Сцена {editor.si + 1}", self.sv, on_close=editor.stop_preview)
        self.fill()

    def open(self):
        self.mv.open()

    def fill(self):
        ed, col, lib = self.ed, self.col, self.lib
        sc, pr = ed.scene, ed.project
        col.clear_widgets()
        length, _ = model.scene_timing(sc)

        # --- ефекти
        col.add_widget(section("Звуки в цій сцені"))
        add = theme.button("✚ Додати звук", theme.GRAD, bold=True)
        add.bind(on_release=lambda *_: SoundPicker(ed, FX_CATEGORIES, self._picked_fx).open())
        col.add_widget(add)
        for k, fx in enumerate(sorted(sc.get("sfx", []), key=lambda f: f.get("at", 0))):
            row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
            theme.paint(row, theme.CARD, 12)
            row.add_widget(theme.label(f"  {lib.name(fx['sound'])} — на {fx.get('at', 0):.1f} с", 14,
                                       halign="left", valign="middle", shorten=True))
            for text, fn in (("▶", lambda fx=fx: ed.preview_sound(lib.path(fx["sound"]))),
                             ("✎", lambda fx=fx: self.edit_time(fx)),
                             ("✕", lambda fx=fx: self.remove_fx(fx))):
                b = theme.button(text, theme.CARD_HI, size_hint_x=None, width=dp(46), height=dp(42))
                b.bind(on_release=lambda _b, f=fn: f())
                row.add_widget(b)
            col.add_widget(row)
        if not sc.get("sfx"):
            col.add_widget(theme.label("Наприклад: півень кукурікає на початку, а дзвіночки — коли з'являється фея.",
                                       13, color=theme.MUTED, size_hint_y=None, height=dp(40)))

        # --- атмосфера
        col.add_widget(section("Атмосфера сцени (звучить увесь час)"))
        amb = sc.get("ambience")
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b = theme.button(("♫ " + lib.name(amb["sound"])) if amb else "Вибрати атмосферу", theme.CARD)
        b.bind(on_release=lambda *_: SoundPicker(ed, ("ambience",), self._picked_amb, "Атмосфера").open())
        row.add_widget(b)
        if amb:
            rm = theme.button("✕", theme.CARD, size_hint_x=None, width=dp(52))
            rm.bind(on_release=lambda *_: self._set(lambda: sc.__setitem__("ambience", None)))
            row.add_widget(rm)
        col.add_widget(row)

        # --- музика
        col.add_widget(section("Фонова музика (на весь мультик)"))
        m = pr.get("music")
        if m:
            name = lib.name(m["builtin"]) if m.get("builtin") else os.path.basename(m.get("file", ""))
            col.add_widget(theme.label(f"♫ {name}", 15, size_hint_y=None, height=dp(28), halign="left",
                                       shorten=True))
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b1 = theme.button("З бібліотеки", theme.CARD)
        b1.bind(on_release=lambda *_: SoundPicker(ed, ("music",), self._picked_music, "Музика").open())
        row.add_widget(b1)
        b2 = theme.button("З телефону", theme.CARD)
        b2.bind(on_release=lambda *_: audio.pick_audio(ed.app.store.sub(ed.pid, "music"), self._picked_file))
        row.add_widget(b2)
        if m:
            rm = theme.button("✕", theme.CARD, size_hint_x=None, width=dp(52))
            rm.bind(on_release=lambda *_: self._set(lambda: pr.__setitem__("music", None)))
            row.add_widget(rm)
        col.add_widget(row)
        if m:
            col.add_widget(theme.label("Гучність музики", 13, color=theme.MUTED, size_hint_y=None, height=dp(20),
                                       halign="left"))
            sl = Slider(min=0.05, max=1.0, value=float(m.get("volume", 0.35)), size_hint_y=None, height=dp(40),
                        cursor_size=(dp(26), dp(26)))

            def vol(*_):
                if pr.get("music"):
                    pr["music"]["volume"] = round(sl.value, 2)
                    ed.dirty = True
            sl.bind(value=vol)
            col.add_widget(sl)

        # --- кроки
        col.add_widget(section("Кроки"))
        col.add_widget(chip_wrap(["Звучать самі, коли герой іде", "Без кроків"],
                                 0 if pr.get("auto_steps", True) else 1,
                                 lambda i: self._set(lambda: pr.__setitem__("auto_steps", i == 0), refill=False),
                                 cols=1))
        col.add_widget(theme.label("Кроки підбираються під фон: трава, сніг, підлога чи асфальт.", 13,
                                   color=theme.MUTED, size_hint_y=None, height=dp(30)))
        if not audio.available():
            col.add_widget(theme.label("Звук працює лише на телефоні.", 13, color=theme.ORANGE,
                                       size_hint_y=None, height=dp(30)))

    def _set(self, fn, refill=True):
        self.ed.mutate(fn)
        if refill:
            self.fill()

    # --- ефекти
    def _picked_fx(self, sid):
        fx = {"sound": sid, "at": 0.5, "vol": 1.0}
        self.edit_time(fx, new=True)

    def edit_time(self, fx, new=False):
        ed = self.ed
        length, _ = model.scene_timing(ed.scene)
        box = BoxLayout(orientation="vertical", spacing=dp(10), padding=[0, dp(10)])
        box.add_widget(theme.label(self.lib.name(fx["sound"]), 18, True, size_hint_y=None, height=dp(30)))
        lab = theme.label("", 16, size_hint_y=None, height=dp(28), halign="center")
        sl = Slider(min=0, max=max(0.1, length - 0.1), step=0.1, value=min(fx.get("at", 0.5), length - 0.1),
                    size_hint_y=None, height=dp(48), cursor_size=(dp(28), dp(28)))

        def upd(*_):
            lab.text = f"Звучить на {sl.value:.1f} с із {length:.1f} с сцени"
        sl.bind(value=upd)
        upd()
        box.add_widget(lab)
        box.add_widget(sl)
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        lb = theme.button("▶ Прослухати", theme.CARD)
        lb.bind(on_release=lambda *_: ed.preview_sound(self.lib.path(fx["sound"])))
        row.add_widget(lb)
        ok = theme.button("Готово", theme.GRAD, bold=True)
        row.add_widget(ok)
        box.add_widget(row)
        box.add_widget(theme.label("Порада: подивіться сцену в «▶ Перегляд», щоб влучити в потрібний момент.",
                                   13, color=theme.MUTED, size_hint_y=None, height=dp(40)))
        box.add_widget(Label())
        mv = modal("Коли звучить", box, done=False)

        def done(*_):
            at = round(sl.value, 1)
            sc = ed.scene

            def do():
                if new:
                    sc.setdefault("sfx", []).append(dict(fx, at=at))
                else:
                    fx["at"] = at
            ed.mutate(do)
            mv.dismiss()
            self.fill()
        ok.bind(on_release=done)
        mv.open()

    def remove_fx(self, fx):
        sc = self.ed.scene
        self._set(lambda: sc["sfx"].remove(fx))

    # --- атмосфера й музика
    def _picked_amb(self, sid):
        sc = self.ed.scene
        self._set(lambda: sc.__setitem__("ambience", {"sound": sid, "vol": 0.5}))

    def _picked_music(self, sid):
        pr = self.ed.project
        self._set(lambda: pr.__setitem__("music", {"builtin": sid, "volume": 0.35}))

    def _picked_file(self, path):
        if not path:
            return
        pr = self.ed.project
        rel = os.path.relpath(path, self.ed.app.store.dir(self.ed.pid))
        self._set(lambda: pr.__setitem__("music", {"file": rel, "volume": 0.35}))
        self.ed.app.toast("Музику додано")
