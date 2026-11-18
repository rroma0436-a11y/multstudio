"""Песик «як на фото» на головній: справжній бігль із відео.

Крутиш пальцем — він обертається (кадри по колу: боком, мордочкою, спинкою).
Торкнешся або натиснеш кнопку — показує дію з відео: гавкає, лягає, встає, перекидається,
нюхає, крутиться, розмовляє, грається… Кліпи ті самі, що й у мультиках (assets/cycles/puppy).

Плавність: кадри тримаємо в пам'яті (власний кеш, щоб не витісняли одне одного), наперед
підвантажуємо наступні кадри дії, а між сусідніми кадрами робимо м'який перехід.
"""
import math
from collections import OrderedDict

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, PopMatrix, PushMatrix, Rectangle, Rotate, RoundedRectangle, Scale, \
    Translate, Triangle
from kivy.metrics import dp, sp
from kivy.uix.label import Label
from kivy.uix.widget import Widget

import imgload
import theme

STEP = 2             # на головній беремо кожен другий кадр (12 на секунду) + плавний перехід між ними
CACHE = 90           # скільки кадрів дій тримати в пам'яті (кадри оберту й спокою — завжди)
SPEED = 1.2          # дії трохи швидші, ніж у відео — живіше

# дія → (кроки, репліка, звук, поза після)
# кроки: назва кліпу або "~hop" (підскок), "~spin" (оберт довкола себе), "~face" (мордочкою до нас),
# "~wiggle" (струшується)
ACTIONS = {
    "bark": (["bark"], "Гав-гав!", "puppy_bark", "stand"),
    "jump": (["~hop"], "Гоп!", "jump", "stand"),
    "sit": (["sitdown"], "Сиджу!", None, "sit"),
    "lie": (["liedown"], "Відпочиваю…", None, "lie"),
    "stand": ([], "Стою!", None, "stand"),
    "paw": (["~face", "talk"], "Тримай лапу!", None, "stand"),
    "hello": (["~face", "talk"], "Привіт!", None, "stand"),
    "talk": (["~face", "talk"], "Гав! Я вмію говорити!", None, "stand"),
    "spin": (["~spin"], "Вжух!", None, "stand"),
    "roll": (["roll"], "Ух ти!", "fall_soft", "stand"),
    "play": (["play"], "Пограймося!", None, "stand"),
    "dance": (["~hop", "play", "~spin"], "Танцюю!", None, "stand"),
    "run": (["run", "run", "run"], "Біжу!", None, "stand"),
    "walk": (["walk", "walk"], "Гуляю…", None, "stand"),
    "sniff": (["sniff", "sniff", "sniff"], "Що тут пахне?", None, "stand"),
    "shake": (["~wiggle"], "Брр!", None, "stand"),
    "tilt": (["~face", "look"], "Гм?", None, "stand"),
    "look": (["~face", "look"], "Привіт!", None, "stand"),
    "wag": (["play", "~hop"], "Я тебе люблю!", None, "stand"),
    "sleep": (["liedown"], "", None, "sleep"),
}
EMOTIONS = {"happy": ("wag", "Мені так весело!"), "sad": ("lie", "Мені сумно…"), "surprised": ("look", "Ого!"),
            "scared": ("lie", "Ой, страшно!"), "angry": ("bark", "Гр-р-р!"), "calm": ("stand", "Усе добре.")}
TAPS = ["bark", "play", "spin", "roll", "sniff", "jump", "talk", "lie", "stand", "bark", "dance", "look"]
IDLE_TALK = ["Привіт! Покрути мене пальцем!", "Торкнись — я щось покажу!", "Напиши мені мультик!",
             "Я справжній бігль!", "Натисни «Перекид»!"]
# переходи між позами: (з, у) → кліп
POSE_CLIPS = {("sit", "stand"): "standup", ("lie", "stand"): "getup", ("sleep", "stand"): "getup",
              ("stand", "sit"): "sitdown", ("stand", "lie"): "liedown", ("stand", "sleep"): "liedown"}
STEP_TIME = {"hop": 0.7, "spin": 1.2, "wiggle": 0.9}


def available(catalog):
    c = catalog.characters.get("puppy") or {}
    return "turn360" in (c.get("cycles") or {})


def _sub(frames, once):
    out = frames[::STEP]
    if once and frames and out[-1] != frames[-1]:
        out.append(frames[-1])
    return out


class PhotoPuppy(Widget):
    def __init__(self, catalog, sound_cb=None, **kw):
        super().__init__(**kw)
        self.cat = catalog
        self.char = catalog.characters.get("puppy")
        self.cycles = (self.char or {}).get("cycles") or {}
        self.sound_cb = sound_cb
        self.ok = "turn360" in self.cycles
        self._clips = {}
        tc = self._clip("turn360")
        self.turn = tc["frames"] if tc else []
        self.ref_h = tc["h_rel"] if tc else 1.0
        self.angle = 0.0           # 0 — боком управо, 90 — мордочкою до нас, 180 — боком уліво, 270 — спинкою
        self.vel = 0.0
        self.pose = "stand"        # stand | sit | lie | sleep
        self.queue = []
        self.cur = None
        self.t = 0.0
        self.idle_touch = 0.0
        self.tap_i = 0
        self.talk_i = 0
        self.next_talk = 7.0
        self.bubble_until = 0.0
        self.touches = []
        self._t0 = {}
        self._ev = None
        # кадри: постійні (оберт, спокій) і кеш дій
        self._keep = {}
        self._lru = OrderedDict()
        self.resident = []
        for key in ("stand_idle", "turn360", "lie_idle"):
            c = self._clip(key)
            if c:
                self.resident += [f for f in c["frames"] if f not in self.resident]
        self._preload = list(self.resident)
        self._last = None
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
            self.rot = Rotate()
            self.sc = Scale()
            Color(1, 1, 1, 1)
            self.rect = Rectangle()
            self._c2 = Color(1, 1, 1, 0)
            self.rect2 = Rectangle()        # наступний кадр, напівпрозоро — рух плавніший
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
    def _clip(self, key):
        if key in self._clips:
            return self._clips[key]
        c = self.cycles.get(key)
        if c is None:
            self._clips[key] = None
            return None
        frames = [self.char["frames"][k] for k in c["frames"]]
        once = c.get("once", False)
        out = {"frames": _sub(frames, once), "period": c["period"], "once": once, "h_rel": c["h_rel"]}
        self._clips[key] = out
        return out

    def _load(self, rel):
        return imgload.load_texture(self.cat.abspath(rel))

    def _loaded(self, rel):
        return rel in self._keep or rel in self._lru

    def _texture(self, rel):
        tex = self._keep.get(rel)
        if tex is not None:
            return tex
        tex = self._lru.get(rel)
        if tex is not None:
            self._lru.move_to_end(rel)
            return tex
        tex = self._load(rel)
        if rel in self.resident:
            self._keep[rel] = tex
        else:
            self._lru[rel] = tex
            while len(self._lru) > CACHE:
                self._lru.popitem(last=False)
        return tex

    def _prefetch(self, rels, n):
        """Підвантажити наперед до n кадрів, яких ще немає в пам'яті."""
        for rel in rels:
            if n <= 0:
                return
            if not self._loaded(rel):
                try:
                    self._texture(rel)
                except Exception:
                    pass
                n -= 1

    def _turn_frames(self, angle):
        """Два сусідні кадри оберту й частка між ними (для плавного переходу)."""
        n = len(self.turn)
        f = (angle % 360.0) / 360.0 * n
        i = int(f) % n
        return self.turn[i], self.turn[(i + 1) % n], f - int(f)

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
        busy = self.cur is not None or self.queue
        # наперед: кадри поточної й наступної дії; коли спокійно — постійні кадри
        ahead = self._ahead()
        if ahead:
            self._prefetch(ahead, 1)
        elif self._preload and not self.touches:
            self._prefetch([self._preload.pop(0)], 1)
        if not self.touches and not busy:
            if abs(self.vel) > 3:
                self.angle += self.vel * dt
                self.vel *= 0.92
            else:
                self.vel = 0.0
                self.idle_touch += dt
                if self.idle_touch > 12 and self.pose == "stand":
                    d = (-self.angle) % 360.0      # давно не крутили — повертається боком, як стояв
                    d = d - 360 if d > 180 else d
                    self.angle += max(-90 * dt, min(90 * dt, d))
        self._step(dt)
        if not busy and self.t > self.next_talk and self.pose != "sleep":
            self.talk_i += 1
            self.say(IDLE_TALK[self.talk_i % len(IDLE_TALK)], 3.5)
            self.next_talk = self.t + 9.0
        self._draw()

    def _ahead(self):
        """Кадри, які знадобляться найближчим часом."""
        out = []
        cur = self.cur
        if cur is not None and cur["kind"] == "clip":
            c = cur["clip"]
            n = len(c["frames"])
            i = int(cur["u"] * SPEED / c["period"] * n)
            out += [c["frames"][(i + k) % n] for k in range(0, 6) if c["once"] is False or i + k < n]
        for st in self.queue[:3]:
            if st[0] == "clip":
                c = self._clip(st[1])
                if c:
                    out += c["frames"][:6]
        return [r for r in out if not self._loaded(r)]

    def _step(self, dt):
        """Черга кроків: оберт до потрібного кута, кліп, підскок…"""
        if self.cur is None:
            if not self.queue:
                return
            st = self.queue.pop(0)
            self.cur = {"kind": st[0], "arg": st[1] if len(st) > 1 else None, "u": 0.0}
            if self.cur["kind"] == "clip":
                c = self._clip(self.cur["arg"])
                if c is None:
                    self.cur = None
                    return
                self.cur["clip"] = c
                self._prefetch(c["frames"][:3], 3)      # щоб перший кадр не «замерз»
        cur = self.cur
        cur["u"] += dt
        u = cur["u"]
        k = cur["kind"]
        if k == "to":
            target = cur["arg"]
            d = (target - self.angle) % 360.0
            d = d - 360 if d > 180 else d
            stepv = 480 * dt
            if abs(d) <= stepv:
                self.angle = target
                self.cur = None
            else:
                self.angle += stepv if d > 0 else -stepv
        elif k in STEP_TIME:
            if k == "spin":
                if "a0" not in cur:
                    cur["a0"] = self.angle
                p = min(1.0, u / STEP_TIME[k])
                self.angle = cur["a0"] + 360 * p * p * (3 - 2 * p)
            if u >= STEP_TIME[k]:
                if k == "spin":
                    self.angle = round(self.angle / 360.0) * 360.0
                self.cur = None
        elif k == "clip":
            if u * SPEED >= cur["clip"]["period"]:
                self.cur = None
        elif k == "pose":
            self.pose = cur["arg"]
            self.cur = None
        elif k == "wait":
            if u >= cur["arg"]:
                self.cur = None

    @staticmethod
    def _at(c, u, loop):
        """Кадр кліпу в момент u: (кадр, наступний кадр, частка між ними)."""
        n = len(c["frames"])
        f = u / c["period"] * n
        if not loop:
            if f >= n - 1:
                return c["frames"][-1], None, 0.0
            i = int(f)
            return c["frames"][i], c["frames"][i + 1], f - i
        i = int(f) % n
        return c["frames"][i], c["frames"][(i + 1) % n], f - int(f)

    def _frame_now(self):
        """(кадр, наступний кадр, частка, h_rel)"""
        cur = self.cur
        if cur is not None and cur["kind"] == "clip":
            c = cur["clip"]
            a, b, k = self._at(c, cur["u"] * SPEED, not c["once"])
            return a, b, k, c["h_rel"]
        if self.pose in ("lie", "sleep"):
            c = self._clip("lie_idle")
            if c:
                a, b, k = self._at(c, self.t, True)
                return a, b, k, c["h_rel"]
        if self.pose == "sit":
            c = self._clip("sitdown")
            if c:
                return c["frames"][-1], None, 0.0, c["h_rel"]
        ang = self.angle % 360.0
        moving = cur is not None and cur["kind"] in ("to", "spin")
        if (ang < 2.5 or ang > 357.5) and not self.touches and abs(self.vel) < 3 and not moving:
            c = self._clip("stand_idle")      # стоїть боком — ледь ворушиться (дихає, повертає голову)
            if c:
                a, b, k = self._at(c, self.t, True)
                return a, b, k, c["h_rel"]
        a, b, k = self._turn_frames(self.angle)
        return a, b, k, self.ref_h

    def _get(self, rel):
        """Текстура кадру; якщо ще не готова й не встигає — показуємо попередній кадр."""
        if rel is None:
            return None
        try:
            return self._texture(rel)
        except Exception:
            return None

    # ---------------------------------------------------------------- малювання
    def _draw(self, *_):
        x, y, w, h = self.x, self.y, self.width, self.height
        self.sky.pos, self.sky.size = (x, y), (w, h)
        gy = y + h * 0.15
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
        rel, rel2, mix, h_rel = self._frame_now()
        tex = self._get(rel) or self._last
        if tex is None:
            return
        self._last = tex
        tex2 = self._get(rel2) if rel2 is not None and mix > 0.08 and self._loaded(rel2) else None
        dw, dh = tex.size
        stand_h = h * 0.58
        hh = stand_h * h_rel / max(0.01, self.ref_h)
        ww = hh * dw / float(max(1, dh))
        cur = self.cur
        lift, sq, rot = 0.0, 1.0, 0.0
        if cur is not None and cur["kind"] == "hop":
            u = cur["u"] / STEP_TIME["hop"]
            if u < 0.18:
                sq = 1.0 - 0.12 * math.sin(math.pi * u / 0.18)          # присів перед стрибком
            elif u < 0.88:
                k = (u - 0.18) / 0.70
                lift = math.sin(math.pi * k) * h * 0.22
                sq = 1.0 + 0.05 * math.sin(math.pi * k)
            else:
                sq = 1.0 - 0.10 * math.sin(math.pi * (u - 0.88) / 0.12)  # приземлився
        elif cur is not None and cur["kind"] == "wiggle":
            u = cur["u"] / STEP_TIME["wiggle"]
            rot = 7.0 * math.sin(2 * math.pi * 6 * u) * (1 - u)
        if cur is None:
            sq *= 1.0 + 0.008 * math.sin(self.t * 2.4)      # дихає
        cx = x + w / 2
        self.rect.texture = tex
        self.rect.pos, self.rect.size = (-ww / 2, 0), (ww, hh)
        if tex2 is not None:
            d2w, d2h = tex2.size
            ww2 = hh * d2w / float(max(1, d2h))
            self.rect2.texture = tex2
            self.rect2.pos, self.rect2.size = (-ww2 / 2, 0), (ww2, hh)
            self._c2.a = mix
        else:
            self._c2.a = 0.0
        self.tr.xy = (cx, gy + lift)
        self.rot.angle = rot
        self.rot.origin = (0, hh * 0.4)
        self.sc.xyz = (1.0 / math.sqrt(sq), sq, 1)
        hop = lift / max(1.0, h * 0.22)
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
        cur = self.pose
        if cur == pose or (cur in ("lie", "sleep") and pose in ("lie", "sleep")):
            return [("pose", pose)]
        steps = []
        if cur != "stand" and pose != "stand":
            steps += self._goto_pose("stand")
            cur = "stand"
        if cur == "stand":
            steps.append(("to", 0.0))
        clip = POSE_CLIPS.get((cur, pose))
        if clip and self._clip(clip):
            steps.append(("clip", clip))
        steps.append(("pose", pose))
        return steps

    def play(self, key):
        if not self.ok:
            return
        clips, text, sound, after = ACTIONS.get(key) or ACTIONS["bark"]
        self.queue = []
        self.cur = None
        steps = []
        if key in ("sit", "lie", "sleep", "stand"):
            steps += self._goto_pose(after)
        else:
            if self.pose != "stand":
                steps += self._goto_pose("stand")
            for c in clips:
                if c in ("~spin", "~hop", "~wiggle"):
                    steps.append((c[1:],))
                elif c == "~face":
                    steps.append(("to", 90.0))
                    steps.append(("wait", 0.15))
                else:
                    steps.append(("to", 90.0 if c in ("talk", "look") else 0.0))
                    steps.append(("clip", c))
            steps.append(("pose", after))
        self.queue = steps
        self._prefetch(self._ahead(), 4)
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
            d = -touch.dx * k            # палець уліво — песик повертається мордочкою до нас
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
