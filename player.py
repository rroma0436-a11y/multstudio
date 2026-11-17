"""Екран готового відео: перегляд мультика, збирання MP4, «Завантажити» й «Поділитися»."""
import math
import os
import threading
import time

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

import audio
import model
import theme
import video_export
from picker import ChipRow
from render import FrameRenderer

FPS = 30
EXPORT_SIZE = (1280, 720)
PREVIEW_SIZE = (960, 540)


def fmt_time(t):
    t = max(0, int(t + 0.5))
    return f"{t // 60:02d}:{t % 60:02d}"


class PlayerView(Widget):
    """Показує текстуру рендера по центру (16:9)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas:
            Color(0, 0, 0, 1)
            self.back = Rectangle()
            Color(1, 1, 1, 1)
            self.rect = Rectangle()
        self.bind(pos=self._fit, size=self._fit)

    def set_texture(self, tex):
        self.rect.texture = tex

    def _fit(self, *_):
        self.back.pos, self.back.size = self.pos, self.size
        w, h = self.width, self.height
        if w / max(1, h) > 16 / 9.0:
            sw, sh = h * 16 / 9.0, h
        else:
            sw, sh = w, w * 9 / 16.0
        self.rect.pos = (self.x + (w - sw) / 2, self.y + (h - sh) / 2)
        self.rect.size = (sw, sh)


class PlayerScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.cat = app.catalog
        self.project = None
        self.pid = None
        self.t = 0.0
        self.total = 0.0
        self.playing = False
        self._ev = None
        self._export = None
        self.renderer = None
        self.playback = audio.Playback()
        self.gallery_target = None

        root = BoxLayout(orientation="vertical", padding=[dp(10), dp(6)], spacing=dp(8))
        theme.paint(root, theme.BG)
        top = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        top.add_widget(theme.back_button(self.back))
        self.title = theme.label("", 18, True, halign="left", valign="middle", shorten=True)
        top.add_widget(self.title)
        root.add_widget(top)

        self.view = PlayerView(size_hint_y=None)
        root.bind(width=lambda w, v: setattr(self.view, "height", (v - dp(20)) * 9 / 16.0))
        self.view.bind(on_touch_down=lambda w, t: self.toggle() if w.collide_point(*t.pos) else None)
        root.add_widget(self.view)

        ctl = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.play_btn = theme.button("▶", theme.ACCENT, size_hint_x=None, width=dp(56), height=dp(44),
                                     font_size=sp(20))
        self.play_btn.bind(on_release=lambda *_: self.toggle())
        ctl.add_widget(self.play_btn)
        self.slider = Slider(min=0, max=1, value=0, cursor_size=(dp(22), dp(22)))
        self.slider.bind(on_touch_move=self._scrub, on_touch_down=self._scrub)
        ctl.add_widget(self.slider)
        root.add_widget(ctl)
        self.time_lab = theme.label("00:00 / 00:00", 13, color=theme.MUTED, size_hint_y=None, height=dp(20),
                                    halign="left")
        root.add_widget(self.time_lab)
        self.scenes_box = BoxLayout(size_hint_y=None, height=dp(46))
        root.add_widget(self.scenes_box)

        # --- збирання й експорт
        self.export_box = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.export_box.bind(minimum_height=self.export_box.setter("height"))
        root.add_widget(self.export_box)
        root.add_widget(Widget())
        bottom = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b = theme.button("✎ Редагувати сцену", theme.CARD)
        b.bind(on_release=lambda *_: self.back())
        bottom.add_widget(b)
        b = theme.button("✚ Новий проєкт", theme.CARD)
        b.bind(on_release=lambda *_: (self.stop(), self.app.open_editor(None)))
        bottom.add_widget(b)
        root.add_widget(bottom)
        self.add_widget(root)

    # ------------------------------------------------------------ відкриття
    def open(self, pid, project, scene_index=0):
        self.pid = pid
        self.project = project
        self.title.text = project.get("title") or "Мультик"
        if self.renderer is None:
            self.renderer = FrameRenderer(self.cat, PREVIEW_SIZE)
            self.view.set_texture(self.renderer.texture)
        self.renderer.project_dir = self.app.store.dir(pid)
        tl, self.total = model.timeline(project)
        self.slider.max = max(0.1, self.total)
        self.t = tl[scene_index][1] if scene_index < len(tl) else 0.0
        self._restart_at = None
        if scene_index < len(tl):
            # перший кадр паузи — коли сцена вже «відкрилася»; «▶» почне з самого початку сцени
            self._restart_at = (self.t + model.still_time(project["scenes"][scene_index]), self.t)
            self.t = self._restart_at[0]
        self.gallery_target = None
        self.scenes_box.clear_widgets()
        if len(tl) > 1:
            self.scenes_box.add_widget(ChipRow([f"Сцена {i + 1}" for i in range(len(tl))], self.jump_scene,
                                               start=scene_index))
        self._export_ui()
        self.show()

    def jump_scene(self, i):
        tl, _ = model.timeline(self.project)
        self.seek(tl[i][1] + 0.01)

    def back(self):
        self.stop()
        if self._export is not None:
            self.app.toast("Зачекайте, відео ще збирається")
            return
        self.app.go("editor")

    # ------------------------------------------------------------ перегляд
    def show(self):
        # на паузі — кадр без затемнення переходу (щоб на початку не було чорного екрана)
        self.renderer.render(self.project, self.t, still=not self.playing)
        self.view.canvas.ask_update()
        self.slider.value = self.t
        self.time_lab.text = f"{fmt_time(self.t)} / {fmt_time(self.total)}"

    def toggle(self):
        if self.playing:
            self.stop()
        else:
            self.play()

    def _events(self):
        """(events, loops, music) з абсолютними шляхами до файлів."""
        return self.app.audio_plan(self.pid, self.project)

    def play(self):
        if self._export is not None:
            return
        if self.t >= self.total - 0.05:
            self.t = 0.0
        if getattr(self, "_restart_at", None) and abs(self.t - self._restart_at[0]) < 1e-6:
            self.t = self._restart_at[1]
        self._restart_at = None
        self.playing = True
        self.play_btn.text = "❚❚"
        ev, loops, music = self._events()
        self.playback.start(ev, music, self.t, loops)
        self._t0 = time.time() - self.t
        self._ev = Clock.schedule_interval(self._tick, 1 / 30.0)

    def _tick(self, dt):
        self.t = time.time() - self._t0
        if self.t >= self.total:
            self.t = self.total
            self.stop()
            return False
        self.playback.update(self.t)
        self.show()

    def stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        was = self.playing
        self.playing = False
        self.play_btn.text = "▶"
        self.playback.stop()
        if was and self.renderer is not None:
            self.show()        # кадр без затемнення замість чорного екрана

    def seek(self, t):
        was = self.playing
        self.stop()
        self.t = max(0.0, min(self.total, t))
        self.show()
        if was:
            self.play()

    def _scrub(self, slider, touch):
        if slider.collide_point(*touch.pos) and self._export is None:
            self.stop()
            Clock.schedule_once(lambda dt: self._after_scrub(), 0)

    def _after_scrub(self):
        self.t = self.slider.value
        self.show()

    # ------------------------------------------------------------ збирання MP4
    def _export_ui(self, state=None):
        box = self.export_box
        box.clear_widgets()
        video = self.app.store.video(self.pid) if self.pid else None
        has_video = bool(video and os.path.exists(video))
        if has_video:
            pj = os.path.join(self.app.store.dir(self.pid), "project.json")
            # мультик змінили після збирання — старе відео не пропонуємо
            if os.path.exists(pj) and os.path.getmtime(pj) > os.path.getmtime(video) + 1:
                has_video = False
        if state == "progress":
            self.pbar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(18))
            self.plab = theme.label("Готую звук…", 15, size_hint_y=None, height=dp(26), halign="center")
            box.add_widget(self.plab)
            box.add_widget(self.pbar)
            b = theme.button("Скасувати", theme.CARD)
            b.bind(on_release=lambda *_: self.cancel_export())
            box.add_widget(b)
            return
        b = theme.button("Створити MP4" if not has_video else "Перезібрати MP4", theme.GRAD2, bold=True,
                         height=dp(52))
        b.bind(on_release=lambda *_: self.start_export())
        box.add_widget(b)
        if has_video:
            b = theme.button("⬇ Завантажити MP4", theme.GRAD, bold=True, height=dp(52))
            b.bind(on_release=lambda *_: self.save_video())
            box.add_widget(b)
            row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
            b = theme.button("↗ Поділитися", theme.GRAD, bold=True, height=dp(52))
            b.bind(on_release=lambda *_: self.share_video())
            row.add_widget(b)
            b = theme.button("▶ У плеєрі", theme.CARD, height=dp(52))
            b.bind(on_release=lambda *_: self.open_in_player())
            row.add_widget(b)
            box.add_widget(row)

    def start_export(self):
        if not video_export.available():
            self.app.toast("Збирання MP4 працює лише на телефоні")
            return
        self.stop()
        self._export = {"cancel": False}
        self.gallery_target = None
        self._export_ui("progress")
        ev, loops, music = self._events()
        if not ev and not music and not loops:
            self._begin_video(None)
            return
        exp = self._export

        def work():
            try:
                pcm = audio.mix_track(ev, music, self.total, loops=loops,
                                      progress=lambda p: Clock.schedule_once(
                                          lambda dt: self._progress(f"Готую звук… {int(p * 100)}%", 0), 0))
                Clock.schedule_once(lambda dt: self._begin_video(pcm), 0)
            except Exception as e:  # noqa: BLE001
                err = str(e)
                Clock.schedule_once(lambda dt: self._fail(f"Звук не вдалося обробити ({err}), "
                                                           "збираю без звуку", soft=True), 0)
                Clock.schedule_once(lambda dt: self._begin_video(None), 0.1)
        if exp is self._export:
            threading.Thread(target=work, daemon=True).start()

    def _progress(self, text, value):
        if self._export is not None and hasattr(self, "plab"):
            self.plab.text = text
            self.pbar.value = value

    def _begin_video(self, pcm):
        if self._export is None or self._export.get("cancel"):
            return
        tmp = os.path.join(self.app.store.dir(self.pid), "video_tmp.mp4")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
            writer = video_export.Mp4Writer(tmp, EXPORT_SIZE[0], EXPORT_SIZE[1], FPS, pcm=pcm)
            writer.start()
        except Exception as e:  # noqa: BLE001
            self._fail(f"Не вдалося запустити збирання відео: {e}")
            return
        self._export.update({"writer": writer, "tmp": tmp, "frame": 0,
                             "frames": int(math.ceil(self.total * FPS)),
                             "renderer": FrameRenderer(self.cat, EXPORT_SIZE, self.app.store.dir(self.pid))})
        self._export["ev"] = Clock.schedule_interval(self._export_step, 0)

    def _export_step(self, dt):
        exp = self._export
        if exp is None:
            return False
        if exp.get("cancel"):
            self._cleanup()
            return False
        try:
            t_end = time.time() + 0.08
            while exp["frame"] < exp["frames"] and time.time() < t_end:
                r = exp["renderer"]
                r.render(self.project, exp["frame"] / float(FPS))
                exp["writer"].add_frame(r.pixels())
                exp["frame"] += 1
            f, n = exp["frame"], exp["frames"]
            self._progress(f"Збираю відео: кадр {f} з {n}", 100.0 * f / max(1, n))
            if f >= n:
                exp["writer"].finish()
                os.replace(exp["tmp"], self.app.store.video(self.pid))
                self._export = None
                self._export_ui()
                self.app.toast("Відео готове!")
                return False
        except Exception as e:  # noqa: BLE001
            self._fail(f"Помилка під час збирання: {e}")
            return False

    def cancel_export(self):
        if self._export is not None:
            self._export["cancel"] = True
            if "ev" not in self._export:
                self._export = None
                self._export_ui()

    def _cleanup(self):
        exp, self._export = self._export, None
        if exp:
            ev = exp.get("ev")
            if ev is not None:
                ev.cancel()
            w = exp.get("writer")
            if w is not None:
                w.close()
            tmp = exp.get("tmp")
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        self._export_ui()

    def _fail(self, text, soft=False):
        self.app.toast(text, 5)
        if not soft:
            self._cleanup()

    # ------------------------------------------------------------ готове відео
    def save_video(self, then=None):
        video = self.app.store.video(self.pid)
        name = time.strftime("multyk_%Y%m%d_%H%M%S.mp4")

        def done(target):
            self.gallery_target = target
            if then:
                then(target)
            else:
                self.app.toast("Відео збережено в Галерею (Movies/Мультстудія)")
        self.app.save_media(video, name, "video/mp4", done)

    def share_video(self):
        import android_bridge as bridge
        if self.gallery_target is not None:
            bridge.share(self.gallery_target, "video/mp4", "Поділитися мультиком")
        else:
            self.save_video(then=lambda t: bridge.share(t, "video/mp4", "Поділитися мультиком"))

    def open_in_player(self):
        import android_bridge as bridge
        if self.gallery_target is not None:
            bridge.open_video(self.gallery_target)
        else:
            self.save_video(then=bridge.open_video)
