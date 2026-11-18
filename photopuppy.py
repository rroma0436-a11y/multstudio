"""Песик «як на фото» на головній: справжній бігль із відео.

Крутиш пальцем — він обертається (36 кадрів по колу: боком, мордочкою, спинкою).
Торкнешся або натиснеш кнопку — показує дію з відео: гавкає, лягає, встає, перекидається,
струшується, нюхає, крутиться, розмовляє… Кліпи ті самі, що й у мультиках (assets/cycles/puppy).
"""
import math

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, PopMatrix, PushMatrix, Rectangle, RoundedRectangle, Scale, Translate, \
    Triangle
from kivy.metrics import dp, sp
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import imgload
import theme

# дія → (кліпи по черзі, репліка, звук, поза після)
# "~спін" — оберт кадрами «довкола себе», "~hop" — підскок, "~face" — повернутися мордочкою
ACTIONS = {
    "bark": (["bark"], "Гав-гав!", "puppy_bark", "stand"),
    "jump": (["~hop"], "Гоп!", "jump", "stand"),
    "sit": (["sitdown"], "Сиджу!", None, "sit"),
    "lie": (["liedown"], "Відпочиваю…", None, "lie"),
    "stand": ([], "", None, "stand"),
    "paw": (["~face", "talk"], "Тримай лапу!", None, "stand"),
    "hello": (["~face", "talk"], "Привіт!", None, "stand"),
    "spin": (["~spin"], "Вжух!", None, "stand"),
    "roll": (["roll"], "Ух ти!", "fall_soft", "stand"),
    "dance": (["~hop", "play", "~spin"], "Танцюю!", None, "stand"),
    "play": (["play"], "Пограймося!", None, "stand"),
    "run": (["run", "run"], "Біжу!", None, "stand"),
    "walk": (["walk", "walk"], "Гуляю…", None, "stand"),
    "sniff": (["sniff", "sniff"], "Що тут пахне?", None, "stand"),
    "shake": (["shake"], "", None, "stand"),
    "tilt": (["~face", "look"], "Гм?", None, "stand"),
    "wag": (["play", "~hop"], "Я тебе люблю!", None, "stand"),
    "sleep": (["liedown"], "", None, "sleep"),
    "look": (["~face", "look"], "Привіт!", None, "stand"),
    "talk": (["~face", "talk"], "Гав! Я вмію говорити!", None, "stand"),
}
EMOTIONS = {"happy": ("wag", "Мені так весело!"), "sad": ("lie", "Мені сумно…"), "surprised": ("tilt", "Ого!"),
            "scared": ("lie", "Ой, страшно!"), "angry": ("bark", "Гр-р-р!"), "calm": ("stand", "Усе добре.")}
TAPS = ["bark", "play", "spin", "roll", "sniff", "jump", "talk", "lie", "stand", "bark", "dance", "look"]
IDLE_TALK = ["Привіт! Покрути мене пальцем!", "Торкнись — я щось покажу!", "Зробімо мультик?",
             "Я справжній бігль!", "Натисни «Перекид»!"]
# переходи між позами: (з, у) → кліп
POSE_CLIPS = {("sit", "stand"): "standup", ("lie", "stand"): "getup", ("sleep", "stand"): "getup",
              ("stand", "sit"): "sitdown", ("stand", "lie"): "liedown", ("stand", "sleep"): "liedown",
              ("sit", "lie"): "liedown", ("lie", "sit"): "standup"}


def available(catalog):
    c = catalog.characters.get("puppy") or {}
    return "turn360" in (c.get("cycles") or {})


class PhotoPuppy(Widget):
    def __init__(self, catalog, sound_cb=None, **kw):
        super().__init__(**kw)
        self.cat = catalog
        self.char = catalog.characters.get("puppy")
        self.cycles = (self.char or {}).get("cycles") or {}
        self.sound_cb = sound_cb
        self.ok = "turn360" in self.cycles
        self.turn = self.cycles.get("turn360", {}).get("frames", [])
        self.ref_h = self.cycles.get("turn360", {}).get("h_rel", 1.0)
        self.angle = 0.0           # 0 — боком управо, 90 — мордочкою до нас, 180 — боком уліво, 270 — спинкою
        self.vel = 0.0
        self.pose = "stand"        # stand | sit | lie | sleep
        self.queue = []            # що ще показати: ("clip", ключ) | ("spin",) | ("hop",) | ("face",) | ("pose", поза)
        self.cur = None            # поточний крок: dict
        self.t = 0.0
        self.idle_touch = 0.0
        self.tap_i = 0
        self.talk_i = 0
        self.next_talk = 7.0
        self.bubble_until = 0.0
        self.touches = []
        self._t0 = {}
        self._ev = None
        self._tex = {}
        self._pre = 0
        with self.canvas:
            Color(1, 1, 1, 1)
            self.sky = Rectangle(texture=theme.gradient((0.80, 0.89, 1.0), (1.0, 0.93, 0.86)))
            Color(0.99, 0.84, 0.66, 1)
            self.pod_side = Ellipse()
            Color(1.0, 0.95, 0.87, 1)
            self.pod_top = Ellipse()
            Color(0.35, 0.25, 0.45, 0.22)
            self.shadow = Ellipse()
            PushMatrix()
            self.tr = Translate()
            self.sc = Scale()
            Color(1, 1, 1, 1)
            self.rect = Rectangle()
            PopMatrix()
            self._bcol = Color(1, 1, 1, 0)
            self._brect = RoundedRectangle(radius=[dp(16)])
            self._btip = Triangle()
        self.bubble = Label(text="", font_size=sp(16), bold=True, color=theme.TEXT, halign="center", valign="middle",
                            opacity=0)
        self.add_widget(self.bubble)
        self.zzz = Label(text="", font_size=sp(22), bold=True, color=theme.ACCENT, opacity=0)
        self.add_widget(self.zzz)
        self.hint = Label(text="☝ Крути пальцем  ·  торкнись", font_size=sp(12), color=(0.3, 0.3, 0.45, 0.85))
        self.add_widget(self.hint)
        self.bind(pos=self._draw, size=self._draw)
        if self.ok:
            self.say(IDLE_TALK[0], 4.0)

    # ---------------------------------------------------------------- кадри
    def _texture(self, rel):
        tex = self._tex.get(rel)
        if tex is None:
            tex = imgload.texture(self.cat.abspath(rel))
            if rel in self.turn:
                self._tex[rel] = tex            # кадри оберту тримаємо завжди (крутити без затримок)
        return tex

    def _clip(self, key):
        c = self.cycles.get(key)
        if c is None:
            return None
        frames = [self.char["frames"][k] for k in c["frames"]]
        return {"frames": frames, "period": c["period"], "once": c.get("once", False), "h_rel": c["h_rel"]}

    def _turn_frame(self, angle):
        n = len(self.turn)
        i = int(round((angle % 360.0) / 360.0 * n)) % n
        return self.turn[i]

    # ---------------------------------------------------------------- життя
    def start(self):
        if self._ev is None and self.ok:
            self._ev = Clock.schedule_interval(self._tick, 1 / 30.0)

    def stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None

    def _tick(self, dt):
        dt = min(dt, 0.1)
        self.t += dt
        # потроху підвантажуємо кадри оберту, щоб потім крутилось без затримок
        if self._pre < len(self.turn):
            try:
                self._texture(self.turn[self._pre])
            except Exception:
                pass
            self._pre += 1
        if not self.touches and self.cur is None:
            if abs(self.vel) > 3:
                self.angle += self.vel * dt
                self.vel *= 0.92
            else:
                self.vel = 0.0
                self.idle_touch += dt
                if self.idle_touch > 12 and self.pose == "stand":
                    # давно не крутили — повертається боком, як стояв
                    d = (-self.angle) % 360.0
                    d = d - 360 if d > 180 else d
                    self.angle += max(-90 * dt, min(90 * dt, d))
        self._step(dt)
        if self.cur is None and not self.queue and self.t > self.next_talk and self.pose != "sleep":
            self.talk_i += 1
            self.say(IDLE_TALK[self.talk_i % len(IDLE_TALK)], 3.5)
            self.next_talk = self.t + 9.0
        self._draw()

    def _step(self, dt):
        """Черга кроків: оберт до потрібного кута, кліп, підскок…"""
        if self.cur is None:
            if not self.queue:
                return
            kind = self.queue.pop(0)
            self.cur = {"kind": kind[0], "arg": kind[1] if len(kind) > 1 else None, "u": 0.0}
            if self.cur["kind"] == "clip":
                c = self._clip(self.cur["arg"])
                if c is None:
                    self.cur = None
                    return
                self.cur["clip"] = c
        cur = self.cur
        cur["u"] += dt
        u = cur["u"]
        k = cur["kind"]
        if k == "to":                       # повернутися до кута
            target = cur["arg"]
            d = (target - self.angle) % 360.0
            d = d - 360 if d > 180 else d
            stepv = 320 * dt
            if abs(d) <= stepv:
                self.angle = target
                self.cur = None
            else:
                self.angle += stepv if d > 0 else -stepv
        elif k == "spin":
            if u >= 1.3:
                self.angle = round(self.angle / 360.0) * 360.0
                self.cur = None
            else:
                p = u / 1.3
                e = p * p * (3 - 2 * p)
                if "a0" not in cur:
                    cur["a0"] = self.angle
                self.angle = cur["a0"] + 360 * e
        elif k == "hop":
            if u >= 0.75:
                self.cur = None
        elif k == "clip":
            c = cur["clip"]
            dur = c["period"] * (1 if c["once"] else 1)
            if u >= dur:
                self.cur = None
        elif k == "pose":
            self.pose = cur["arg"]
            self.cur = None
        elif k == "wait":
            if u >= cur["arg"]:
                self.cur = None

    def _frame_now(self):
        """(шлях кадру, h_rel, підскок 0..1, стиск)"""
        cur = self.cur
        if cur is not None and cur["kind"] == "clip":
            c = cur["clip"]
            n = len(c["frames"])
            u = cur["u"]
            if c["once"]:
                i = min(n - 1, int(u / c["period"] * n))
            else:
                i = int(u / (c["period"] / n)) % n
            return c["frames"][i], c["h_rel"], 0.0
        hop = 0.0
        if cur is not None and cur["kind"] == "hop":
            hop = math.sin(math.pi * min(1.0, cur["u"] / 0.75))
        if self.pose in ("lie", "sleep"):
            c = self._clip("lie_idle")
            if c:
                n = len(c["frames"])
                return c["frames"][int(self.t / (c["period"] / n)) % n], c["h_rel"], hop
        if self.pose == "sit":
            c = self._clip("sitdown")
            if c:
                return c["frames"][-1], c["h_rel"], hop
        return self._turn_frame(self.angle), self.ref_h, hop

    # ---------------------------------------------------------------- малювання
    def _draw(self, *_):
        x, y, w, h = self.x, self.y, self.width, self.height
        self.sky.pos, self.sky.size = (x, y), (w, h)
        gy = y + h * 0.16
        pw = min(w * 0.86, h * 1.5)
        self.pod_side.pos, self.pod_side.size = (x + (w - pw) / 2, gy - h * 0.085), (pw, h * 0.16)
        self.pod_top.pos, self.pod_top.size = (x + (w - pw) / 2, gy - h * 0.055), (pw, h * 0.14)
        self.hint.size = (w, dp(18))
        self.hint.text_size = self.hint.size
        self.hint.halign = "center"
        self.hint.pos = (x, y + dp(2))
        self.hint.opacity = 0.85 if self.t < 12 else max(0.0, 0.85 - (self.t - 12) * 0.3)
        if not self.ok:
            return
        rel, h_rel, hop = self._frame_now()
        try:
            tex = self._texture(rel)
        except Exception:
            return
        dw, dh = tex.size
        stand_h = h * 0.56
        hh = stand_h * h_rel / max(0.01, self.ref_h)
        ww = hh * dw / float(max(1, dh))
        lift = hop * h * 0.16
        sq = 1.0
        if self.cur is not None and self.cur["kind"] == "hop":
            u = self.cur["u"] / 0.75
            sq = 1.0 - 0.08 * math.sin(math.pi * min(1.0, u * 4)) if u < 0.25 or u > 0.9 else 1.0 + 0.04 * hop
        cx = x + w / 2
        self.rect.texture = tex
        self.rect.pos, self.rect.size = (-ww / 2, 0), (ww, hh)
        self.tr.xy = (cx, gy + lift)
        self.sc.xyz = (1.0 / math.sqrt(sq), sq, 1)
        sw = ww * 0.62 * (1 - 0.35 * hop)
        self.shadow.pos, self.shadow.size = (cx - sw / 2, gy - h * 0.025), (sw, h * 0.05 * (1 - 0.3 * hop))
        # хмаринка над головою
        t = self.t
        show = t < self.bubble_until and self.bubble.text
        a = min(1.0, (self.bubble_until - t) / 0.3) if show else 0.0
        if show:
            head = (cx + ww * 0.18, gy + lift + hh * 0.95)
            self.bubble.texture_update()
            bw = self.bubble.texture_size[0] + dp(28)
            bh = self.bubble.texture_size[1] + dp(16)
            bx = min(max(x + dp(6), head[0] - bw / 2), x + w - bw - dp(6))
            by = min(head[1] + dp(14), y + h - bh - dp(6))
            self.bubble.size = (bw, bh)
            self.bubble.pos = (bx, by)
            self._brect.pos, self._brect.size = (bx, by), (bw, bh)
            tx = min(max(bx + dp(22), head[0]), bx + bw - dp(22))
            self._btip.points = [tx - dp(9), by + 1, tx + dp(9), by + 1, tx, max(by - dp(12), head[1])]
        self._bcol.a = 0.97 * a
        self.bubble.opacity = a
        if self.pose == "sleep" and self.cur is None:
            k = (t * 0.6) % 1.0
            self.zzz.text = "z Z z"[:1 + int(k * 5)]
            self.zzz.texture_update()
            self.zzz.size = self.zzz.texture_size
            self.zzz.pos = (cx + ww * 0.25, gy + hh * 0.9 + dp(20) * k)
            self.zzz.opacity = 1.0 - k * 0.6
        else:
            self.zzz.opacity = 0

    def say(self, text, seconds=2.2):
        if text:
            self.bubble.text = text
            self.bubble_until = self.t + seconds

    # ---------------------------------------------------------------- дії
    def _goto_pose(self, pose):
        """Кроки, щоб перейти в іншу позу (з кліпами вставання/сідання/лягання)."""
        steps = []
        cur = self.pose
        if cur == pose or (cur in ("lie", "sleep") and pose in ("lie", "sleep")):
            steps.append(("pose", pose))
            return steps
        if cur == "stand":
            steps.append(("to", 0.0))
        clip = POSE_CLIPS.get((cur, pose))
        if clip and clip in self.cycles:
            if (cur, pose) in (("sit", "lie"), ("lie", "sit")):
                mid = "getup" if cur == "lie" else "standup"
                steps += [("clip", mid), ("pose", "stand"), ("clip", "liedown" if pose == "lie" else "sitdown")]
            else:
                steps.append(("clip", clip))
        steps.append(("pose", pose))
        return steps

    def play(self, key):
        if not self.ok:
            return
        spec = ACTIONS.get(key) or ACTIONS["bark"]
        clips, text, sound, after = spec
        self.queue = []
        self.cur = None
        steps = []
        if key in ("sit", "lie", "sleep", "stand"):
            steps += self._goto_pose(after)
        else:
            if self.pose != "stand":
                steps += self._goto_pose("stand")
            for c in clips:
                if c == "~spin":
                    steps.append(("spin",))
                elif c == "~hop":
                    steps.append(("hop",))
                elif c == "~face":
                    steps.append(("to", 90.0))
                    steps.append(("wait", 0.3))
                else:
                    if c in ("walk", "run", "sniff", "talk", "look", "bark", "shake", "roll"):
                        steps.append(("to", 90.0 if c in ("talk", "look") else 0.0))
                    steps.append(("clip", c))
            steps.append(("pose", after))
        self.queue = steps
        if text:
            self.say(text, 2.6)
        if sound and self.sound_cb:
            Clock.schedule_once(lambda dt: self.sound_cb(sound), 0.25 if key != "bark" else 0.35)
        self.next_talk = self.t + 10.0

    def emotion(self, name):
        key, line = EMOTIONS.get(name, ("bark", ""))
        self.play(key)
        self.say(line, 2.6)
        if name == "angry" and self.sound_cb:
            self.sound_cb("dog_growl")

    # ---------------------------------------------------------------- дотики
    def on_touch_down(self, touch):
        if not self.ok or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        touch.grab(self)
        self.touches.append(touch)
        self._t0[touch.uid] = (self.t, touch.x, touch.y)
        self.vel = 0.0
        self.idle_touch = 0.0
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        self.idle_touch = 0.0
        if self.pose == "stand" and self.cur is None and not self.queue:
            k = 0.5 * 160.0 / max(80.0, dp(160))
            d = -touch.dx * k            # палець управо — песик повертається мордочкою до нас
            self.angle += d
            self.vel = d * 60 * 0.35
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        t0, x0, y0 = self._t0.pop(touch.uid, (self.t, touch.x, touch.y))
        if touch in self.touches:
            self.touches.remove(touch)
        moved = math.hypot(touch.x - x0, touch.y - y0)
        if moved < dp(10) and self.t - t0 < 0.45:
            self.vel = 0.0
            key = TAPS[self.tap_i % len(TAPS)]
            self.tap_i += 1
            self.play(key)
        return True
