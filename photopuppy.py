"""Песик «як на фото» на головній: справжній бігль із відео.

Крутиш пальцем — він обертається (кадри по колу: боком, мордочкою, спинкою).
Торкнешся або натиснеш кнопку — показує дію з відео: гавкає, сідає, дає лапу, стрибає, струшується,
танцює, махає хвостом, засинає… Кліпи ті самі, що й у мультиках (assets/cycles/puppy).

Плавність: кадри читаються у фоновому потоці (imgload.Decoder) наперед, дія починається, коли перші
кадри вже готові; кадри оберту й спокою весь час у пам'яті; між різними позами — короткий м'який перехід.
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

CACHE = 48           # скільки кадрів дій тримати в пам'яті (кадри оберту й спокою — завжди)
SPEED = 1.0          # швидкість кліпів (самі кліпи вже трохи пришвидшені при нарізанні)
AHEAD = 14           # скільки кадрів читати наперед
FADE = 0.2           # м'який перехід між позами, с
PREROLL = 0.6        # найдовше очікування перших кадрів дії, с

# дія → (кроки, репліка, звук, поза після)
# кроки: назва кліпу або "~hop" (підскок), "~spin" (оберт довкола себе), "~face" (мордочкою до нас),
# "~wiggle" (струшується)
ACTIONS = {
    "bark": (["bark"], "Гав-гав!", "puppy_bark", "stand"),
    "jump": (["jump"], "Гоп!", "jump", "stand"),
    "sit": (["sitdown"], "Сиджу!", None, "sit"),
    "lie": (["liedown"], "Відпочиваю…", None, "lie"),
    "stand": ([], "Стою!", None, "stand"),
    "paw": (["paw"], "Тримай лапу!", None, "stand"),
    "hello": (["paw"], "Привіт!", None, "stand"),
    "talk": (["talk"], "Гав! Я вмію говорити!", None, "stand"),
    "spin": (["~spin"], "Вжух!", None, "stand"),
    "roll": (["roll"], "Ух ти!", "fall_soft", "stand"),
    "play": (["play"], "Пограймося!", None, "stand"),
    "dance": (["dance"], "Танцюю!", None, "stand"),
    "run": (["run", "run", "run"], "Біжу!", None, "stand"),
    "walk": (["walk", "walk", "walk"], "Гуляю…", None, "stand"),
    "sniff": (["sniff", "sniff", "sniff"], "Що тут пахне?", None, "stand"),
    "shake": (["shake"], "Брр!", None, "stand"),
    "tilt": (["look"], "Гм?", None, "stand"),
    "look": (["look"], "Привіт!", None, "stand"),
    "wag": (["wag"], "Я тебе люблю!", None, "stand"),
    "sleep": (["liedown"], "", None, "sleep"),
}
# якщо кліпу ще немає (старі файли assets) — чим його замінити
FALLBACK = {"jump": ["~hop"], "shake": ["~wiggle"], "paw": ["~face", "talk"], "dance": ["~hop", "play", "~spin"],
            "wag": ["play", "~hop"], "look": ["~face", "talk"], "talk": ["~face", "look"]}
EMOTIONS = {"happy": ("wag", "Мені так весело!"), "sad": ("lie", "Мені сумно…"), "surprised": ("look", "Ого!"),
            "scared": ("lie", "Ой, страшно!"), "angry": ("bark", "Гр-р-р!"), "calm": ("stand", "Усе добре.")}
TAPS = ["bark", "wag", "jump", "paw", "spin", "shake", "talk", "roll", "dance", "look", "sniff", "play"]
IDLE_TALK = ["Привіт! Покрути мене пальцем!", "Торкнись — я щось покажу!", "Скажи мені мультик!",
             "Я справжній бігль!", "Натисни «Дай лапу»!"]
# переходи між позами: (з, у) → кліп
POSE_CLIPS = {("sit", "stand"): "standup", ("lie", "stand"): "getup", ("sleep", "stand"): "getup",
              ("stand", "sit"): "sitdown", ("stand", "lie"): "liedown", ("stand", "sleep"): "liedown"}
STEP_TIME = {"hop": 0.7, "spin": 1.2, "wiggle": 0.9}
FRONT = ("talk", "look")   # старі кліпи без позначки «view», зняті спереду (тоді спершу — мордочкою до нас)


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
        # кадри: постійні (кожен другий кадр оберту + спокій) і кеш дій
        self._keep = {}
        self._lru = OrderedDict()
        self.resident = set(self.turn[::2])
        sc = self._clip("stand_idle")
        if sc:
            self.resident.update(sc["frames"])
        self._dec = None
        try:
            self._dec = imgload.decoder()
            if not self._dec.ok:
                self._dec = None
        except Exception:  # noqa: BLE001
            self._dec = None
        self._preload = [f for f in self.turn[::2]] + (sc["frames"] if sc else []) + \
            [f for f in self.turn[1::2]]
        self._last = None          # (текстура, висота, ширина) — що показано минулого разу
        self._fade = None          # (текстура, висота, ширина, час початку) — попередня поза, що зникає
        self._key = None
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
            self.rect2 = Rectangle()        # попередня поза, що м'яко зникає
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
        out = {"key": key, "frames": frames, "period": c["period"], "once": c.get("once", False),
               "h_rel": c["h_rel"], "view": c.get("view") or ("front" if key in FRONT else "side")}
        self._clips[key] = out
        return out

    def _path(self, rel):
        return self.cat.abspath(rel)

    def _loaded(self, rel):
        return rel in self._keep or rel in self._lru

    def _store(self, rel, tex):
        if rel in self.resident:
            self._keep[rel] = tex
        else:
            self._lru[rel] = tex
            self._lru.move_to_end(rel)
            while len(self._lru) > CACHE:
                self._lru.popitem(last=False)

    def _cached(self, rel):
        tex = self._keep.get(rel)
        if tex is not None:
            return tex
        tex = self._lru.get(rel)
        if tex is not None:
            self._lru.move_to_end(rel)
        return tex

    def _texture(self, rel):
        """Текстура зараз (якщо немає — читаємо одразу, без фону)."""
        tex = self._cached(rel)
        if tex is None:
            tex = imgload.load_texture(self._path(rel))
            self._store(rel, tex)
        return tex

    def _request(self, rels, urgent=False):
        """Попросити кадри наперед (фоном; без фонового потоку — по одному за кадр малювання)."""
        if self._dec is None:
            for rel in rels:
                if not self._loaded(rel):
                    try:
                        self._texture(rel)
                    except Exception:  # noqa: BLE001
                        pass
                    return
            return
        for rel in (reversed(rels) if urgent else rels):
            if not self._loaded(rel):
                self._dec.request(self._path(rel), urgent=urgent)

    def _poll(self):
        if self._dec is None:
            return
        for path, tex in self._dec.poll(6):
            rel = self._rel_of.get(path) if hasattr(self, "_rel_of") else None
            if rel is None:
                self._rel_of = {self._path(r): r for c in self.cycles for r in
                                [self.char["frames"][k] for k in self.cycles[c]["frames"]]}
                rel = self._rel_of.get(path)
            if rel is not None and tex is not None:
                self._store(rel, tex)

    def _turn_index(self, angle):
        n = len(self.turn)
        return int(round((angle % 360.0) / 360.0 * n)) % n

    def _turn_frame(self, angle):
        """Найближчий кадр оберту, що вже в пам'яті (кожен другий є завжди)."""
        n = len(self.turn)
        i = self._turn_index(angle)
        rel = self.turn[i]
        if self._loaded(rel):
            return rel
        self._request([rel], urgent=True)
        f = (angle % 360.0) / 360.0 * n
        for j in sorted(range(i - 2, i + 3), key=lambda j: abs(j - f)):
            r = self.turn[j % n]
            if self._loaded(r):
                return r
        return rel

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
        self._poll()
        busy = self.cur is not None or self.queue
        ahead = self._ahead()
        if ahead:
            self._request(ahead[:4], urgent=True)
            self._request(ahead[4:])
        elif self._preload and not self.touches:
            batch, self._preload = self._preload[:3], self._preload[3:]
            self._request(batch)
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

    def _clip_index(self, c, u):
        n = len(c["frames"])
        f = int(u * SPEED / c["period"] * n)
        return min(n - 1, f) if c["once"] else f % n

    def _ahead(self):
        """Кадри, які знадобляться найближчим часом (у порядку потреби)."""
        out = []
        cur = self.cur
        if cur is not None and cur["kind"] == "clip":
            c = cur["clip"]
            n = len(c["frames"])
            i = self._clip_index(c, cur["u"])
            for k in range(AHEAD):
                j = i + k
                if c["once"] and j >= n:
                    break
                out.append(c["frames"][j % n])
        left = AHEAD - len(out)
        for st in self.queue[:3]:
            if left <= 0:
                break
            if st[0] == "clip":
                c = self._clip(st[1])
                if c:
                    out += c["frames"][:left]
                    left -= len(c["frames"][:left])
        if self.pose == "sleep" or (self.queue and self.queue[-1] == ("pose", "sleep")):
            c = self._clip("sleep")
            if c:
                out += c["frames"][:8]
        return [r for r in out if not self._loaded(r)]

    def _step(self, dt):
        """Черга кроків: оберт до потрібного кута, кліп, підскок…"""
        if self.cur is None:
            if not self.queue:
                return
            st = self.queue.pop(0)
            self.cur = {"kind": st[0], "arg": st[1] if len(st) > 1 else None, "u": 0.0, "wait": 0.0}
            if self.cur["kind"] == "clip":
                c = self._clip(self.cur["arg"])
                if c is None:
                    self.cur = None
                    return
                self.cur["clip"] = c
                self._request(c["frames"][:AHEAD], urgent=False)
        cur = self.cur
        k = cur["kind"]
        if k == "clip" and cur["u"] == 0.0:
            # чекаємо перших кадрів (не довше PREROLL), щоб дія не почалась ривком
            first = cur["clip"]["frames"][:6]
            if not all(self._loaded(r) for r in first) and cur["wait"] < PREROLL:
                cur["wait"] += dt
                self._request(first, urgent=True)
                return
        cur["u"] += dt
        u = cur["u"]
        if k == "to":
            target = cur["arg"]
            d = (target - self.angle) % 360.0
            d = d - 360 if d > 180 else d
            stepv = 420 * dt * (0.35 + 0.65 * min(1.0, abs(d) / 60.0))   # сповільнюється наприкінці
            if abs(d) <= max(stepv, 0.5):
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

    def _loop_frame(self, c, t):
        n = len(c["frames"])
        return c["frames"][int(max(0.0, t) / (c["period"] / n)) % n]

    def _frame_now(self):
        """(кадр, h_rel, ключ «що показуємо» — зміна ключа = м'який перехід)"""
        cur = self.cur
        if cur is not None and cur["kind"] == "clip":
            c = cur["clip"]
            i = self._clip_index(c, cur["u"])
            rel = c["frames"][i]
            if not self._loaded(rel):
                # кадр ще читається — показуємо найближчий попередній готовий
                for j in range(i - 1, max(-1, i - 8), -1):
                    if self._loaded(c["frames"][j % len(c["frames"])]):
                        rel = c["frames"][j % len(c["frames"])]
                        break
            return rel, c["h_rel"], "clip:" + c["key"]
        if self.pose == "sleep":
            c = self._clip("sleep") or self._clip("lie_idle")
            if c:
                return self._loop_frame(c, self.t), c["h_rel"], "pose:sleep"
        if self.pose in ("lie", "sleep"):
            c = self._clip("lie_idle")
            if c:
                return self._loop_frame(c, self.t), c["h_rel"], "pose:lie"
        if self.pose == "sit":
            c = self._clip("sitdown")
            if c:
                return c["frames"][-1], c["h_rel"], "pose:sit"
        ang = self.angle % 360.0
        moving = cur is not None and cur["kind"] in ("to", "spin")
        if (ang < 2.5 or ang > 357.5) and not self.touches and abs(self.vel) < 3 and not moving:
            c = self._clip("stand_idle")      # стоїть боком — ледь ворушиться (дихає, повертає голову)
            if c:
                return self._loop_frame(c, self.t), c["h_rel"], "pose:stand"
        return self._turn_frame(self.angle), self.ref_h, "turn"

    def _get(self, rel):
        """Текстура кадру, якщо вже в пам'яті (інакше None — показуємо попередній кадр)."""
        if rel is None:
            return None
        tex = self._cached(rel)
        if tex is not None:
            return tex
        if self._dec is None or self._last is None:
            try:
                return self._texture(rel)
            except Exception:  # noqa: BLE001
                return None
        self._request([rel], urgent=True)
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
        rel, h_rel, key = self._frame_now()
        tex = self._get(rel)
        stand_h = h * 0.58
        if tex is None:
            if self._last is None:
                return
            tex, hh, ww = self._last            # кадр ще читається — тримаємо попередній
        else:
            dw, dh = tex.size
            hh = stand_h * h_rel / max(0.01, self.ref_h)
            ww = hh * dw / float(max(1, dh))
            if self._key is not None and key != self._key and self._last is not None and \
                    not (key == "turn" or self._key == "turn"):
                # інша поза чи інша дія — попередній кадр м'яко зникає поверх нового
                self._fade = self._last + (self.t,)
            self._key = key
            self._last = (tex, hh, ww)
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
            sq *= 1.0 + 0.006 * math.sin(self.t * 2.4)      # дихає
        cx = x + w / 2
        self.rect.texture = tex
        self.rect.pos, self.rect.size = (-ww / 2, 0), (ww, hh)
        fade = self._fade
        if fade is not None and self.t - fade[3] < FADE and fade[0] is not tex:
            k = (self.t - fade[3]) / FADE
            self.rect2.texture = fade[0]
            self.rect2.pos, self.rect2.size = (-fade[2] / 2, 0), (fade[2], fade[1])
            self._c2.a = (1.0 - k) * (1.0 - k)
        else:
            self._fade = None
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

    def _steps(self, c):
        """Кроки для одного кліпу (або його заміни, якщо кліпу немає)."""
        if c in ("~spin", "~hop", "~wiggle"):
            return [(c[1:],)]
        if c == "~face":
            return [("to", 90.0), ("wait", 0.1)]
        clip = self._clip(c)
        if clip is None:
            out = []
            for f in FALLBACK.get(c, []):
                if f.startswith("~") or self._clip(f):
                    out += self._steps(f)
            return out
        if clip["view"] == "front":
            return [("to", 90.0), ("clip", c)]
        return [("to", 0.0), ("clip", c)]

    def play(self, key):
        if not self.ok:
            return
        clips, text, sound, after = ACTIONS.get(key) or ACTIONS["bark"]
        self.queue = []
        self.cur = None
        if self._dec is not None:
            self._dec.cancel_all()       # кадри попередньої дії вже не потрібні
        steps = []
        if key in ("sit", "lie", "sleep", "stand"):
            steps += self._goto_pose(after)
        else:
            if self.pose != "stand":
                steps += self._goto_pose("stand")
            for c in clips:
                steps += self._steps(c)
            steps.append(("pose", after))
        self.queue = steps
        self._request(self._ahead()[:AHEAD], urgent=False)
        if text:
            self.say(text, 2.6)
        if sound and self.sound_cb:
            Clock.schedule_once(lambda dt: self.sound_cb(sound), 0.35 if key != "bark" else 0.45)
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
