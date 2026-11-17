"""Модель мультика: проєкт = стрічка сцен. Розрахунок часу, руху, ходьби, розмови й камери.

Модуль не залежить від Kivy (перевіряється на звичайному Python).

Проєкт:
  {"version": 2, "title", "scenes": [Scene], "music": {"file", "volume"} | None}
Сцена:
  {"background", "items": [Item], "dialog": [Line], "duration", "camera", "transition", "auto_depth"}
Елемент (герой чи предмет):
  {"uid", "kind": "char"|"obj", "id", "frame", "x", "y", "scale", "flip", "rot",
   "end": {"x", "y", "scale"} | None}         # x — центр, y — низ (ноги); частки сцени
Репліка:
  {"speaker": uid | None, "text", "style": "say"|"think"|"shout", "voice": файл | None, "voice_dur"}
"""
import copy
import math
import time
import uuid

CAMERA_MOVES = [
    ("none", "Без руху"), ("zoom_in", "Наближення"), ("zoom_out", "Віддалення"),
    ("pan_left", "Панорама вліво"), ("pan_right", "Панорама вправо"), ("shake", "Хитання"),
]
TRANSITIONS = [("fade", "Затемнення"), ("cut", "Різко")]
BUBBLE_STYLES = [("say", "Звичайна"), ("think", "Думка"), ("shout", "Крик")]

MIN_SCENE = 1.5
FIRST_LINE_AT = 0.4
LINE_GAP = 0.25
MOVE_MARGIN = 0.3
STEP = 0.22          # тривалість одного кроку (кадр «іде 1» / «іде 2»)
TALK_STEP = 0.18     # як часто «ворушаться губи»
RUN_SPEED = 0.25     # частка ширини сцени за секунду, після якої герой біжить
FADE = 0.35


def new_uid():
    return uuid.uuid4().hex[:8]


def new_scene(background):
    return {"background": background, "items": [], "dialog": [], "duration": 4.0,
            "camera": "none", "transition": "fade", "auto_depth": True}


def new_project(background, title=None):
    return {"version": 2, "title": title or time.strftime("Мультик %d.%m %H:%M"),
            "scenes": [new_scene(background)], "music": None}


def duplicate_scene(scene):
    s = copy.deepcopy(scene)
    for it in s["items"]:
        old = it["uid"]
        it["uid"] = new_uid()
        for ln in s["dialog"]:
            if ln.get("speaker") == old:
                ln["speaker"] = it["uid"]
        # нова сцена починається там, де закінчився рух у попередній
        end = it.pop("end", None)
        if end:
            it.update({k: end[k] for k in ("x", "y", "scale") if k in end})
    for ln in s["dialog"]:
        ln["voice"] = ln.get("voice")  # голос залишаємо (файл спільний)
    return s


def from_v1(scene_v1, background_default):
    """Сцена з версії 1 (одна картинка) -> проєкт версії 2."""
    sc = new_scene(scene_v1.get("background") or background_default)
    for it in scene_v1.get("items", []):
        it = dict(it)
        it.setdefault("uid", new_uid())
        it.setdefault("rot", 0.0)
        sc["items"].append(it)
    pr = new_project(sc["background"], scene_v1.get("title"))
    pr["scenes"] = [sc]
    return pr


# ---------------------------------------------------------------------- час
def line_duration(line):
    if line.get("voice") and line.get("voice_dur"):
        return max(0.6, float(line["voice_dur"]))
    n = len((line.get("text") or "").strip())
    return min(7.0, max(1.6, 0.9 + 0.065 * n))


def scene_timing(scene):
    """(тривалість сцени, [(початок, кінець) для кожної репліки])"""
    t = FIRST_LINE_AT
    spans = []
    for ln in scene.get("dialog", []):
        d = line_duration(ln)
        spans.append((t, t + d))
        t += d + LINE_GAP
    end_lines = spans[-1][1] + 0.6 if spans else 0
    length = max(MIN_SCENE, float(scene.get("duration") or 0), end_lines)
    return length, spans


def timeline(project):
    """[(індекс сцени, початок, тривалість)], загальна тривалість"""
    out, t = [], 0.0
    for i, sc in enumerate(project["scenes"]):
        length, _ = scene_timing(sc)
        out.append((i, t, length))
        t += length
    return out, t


def locate(project, t):
    """Глобальний час -> (індекс сцени, локальний час, тривалість сцени)."""
    tl, total = timeline(project)
    if not tl:
        return None
    t = max(0.0, min(t, total - 1e-6))
    for i, start, length in tl:
        if t < start + length:
            return i, t - start, length
    i, start, length = tl[-1]
    return i, length, length


def ease(p):
    p = max(0.0, min(1.0, p))
    return p * p * (3 - 2 * p)


# ---------------------------------------------------------------------- стан героя в момент часу
def _gait(frames, char_category, speed):
    def pair(a, b):
        return (a, b) if a in frames and b in frames else None
    if char_category in ("birds", "dragons") or "fly" in frames:
        g = pair("fly_a", "fly_b")
        if g:
            return g
        if "flying_calm" in frames:
            return ("flying_calm", "flying_calm")
        if "fly" in frames:
            return ("fly", "fly")
    if speed > RUN_SPEED:
        g = pair("run_a", "run_b")
        if g:
            return g
    g = pair("walk_a", "walk_b") or pair("move_a", "move_b") or pair("run_a", "run_b")
    if g:
        return g
    if "move" in frames:
        return ("move", "move")
    return None


def _talk_frame(frame, frames):
    if frame.startswith("front"):
        cand = "front34_talking"
    elif frame.startswith("side"):
        cand = "side_talking"
    else:
        cand = None
    return cand if cand in frames and cand != frame else None


def item_state(item, scene, local_t, length, char=None, spans=None):
    """Поточний стан елемента: x, y, scale, rot, flip, frame, moving.

    char — запис героя з каталогу (потрібен для кадрів ходьби й розмови)."""
    st = {"x": item["x"], "y": item["y"], "scale": item.get("scale", 1.0),
          "rot": item.get("rot", 0.0), "flip": bool(item.get("flip")),
          "frame": item.get("frame", ""), "moving": False}
    end = item.get("end")
    if end:
        t0, t1 = MOVE_MARGIN, max(MOVE_MARGIN + 0.3, length - MOVE_MARGIN)
        raw = (local_t - t0) / (t1 - t0)
        p = ease(raw)
        ex, ey, es = end.get("x", st["x"]), end.get("y", st["y"]), end.get("scale", st["scale"])
        dx, dy = ex - st["x"], ey - st["y"]
        st["x"] += dx * p
        st["y"] += dy * p
        st["scale"] += (es - st["scale"]) * p
        dist = math.hypot(dx, dy)
        if char is not None and dist > 0.01 and 0.0 < raw < 1.0:
            frames = char["frames"]
            speed = dist / (t1 - t0)
            gait = _gait(frames, char.get("category"), speed)
            if gait:
                st["frame"] = gait[int(local_t / STEP) % 2]
                st["moving"] = True
                if abs(dx) > 0.005:
                    st["flip"] = dx < 0       # кадри руху дивляться вправо
    if char is not None and not st["moving"] and spans is not None:
        uid = item.get("uid")
        for ln, (a, b) in zip(scene.get("dialog", []), spans):
            if ln.get("speaker") == uid and a <= local_t < b:
                talk = _talk_frame(st["frame"], char["frames"])
                if talk and int((local_t - a) / TALK_STEP) % 2 == 0:
                    st["frame"] = talk
                break
    return st


def active_lines(scene, local_t, spans):
    """[(репліка, частка показу 0..1)] — що зараз говорять."""
    out = []
    for ln, (a, b) in zip(scene.get("dialog", []), spans):
        if a <= local_t < b + 0.15:
            out.append((ln, (local_t - a) / max(0.01, b - a)))
    return out


def camera(scene, local_t, length):
    """(zoom, зсув x, зсув y) — зсув у частках сцени; збільшення навколо центру."""
    p = ease(local_t / max(0.01, length))
    mode = scene.get("camera", "none")
    if mode == "zoom_in":
        return 1.0 + 0.25 * p, 0.0, 0.0
    if mode == "zoom_out":
        return 1.25 - 0.25 * p, 0.0, 0.0
    if mode == "pan_left":
        return 1.18, -0.07 + 0.14 * p, 0.0
    if mode == "pan_right":
        return 1.18, 0.07 - 0.14 * p, 0.0
    if mode == "shake":
        return 1.05, 0.008 * math.sin(local_t * 31), 0.008 * math.sin(local_t * 23 + 1)
    return 1.0, 0.0, 0.0


def fade_alpha(project, scene_index, local_t, length):
    """Прозорість чорного затемнення (0 — немає)."""
    sc = project["scenes"][scene_index]
    a = 0.0
    if sc.get("transition", "fade") == "fade" and local_t < FADE:
        a = 1 - local_t / FADE
    if scene_index == len(project["scenes"]) - 1 and length - local_t < FADE:
        a = max(a, 1 - (length - local_t) / FADE)
    return max(0.0, min(1.0, a))


def draw_order(scene, states):
    """Індекси елементів у порядку малювання (дальні спершу)."""
    idx = list(range(len(scene["items"])))
    if scene.get("auto_depth", True):
        idx.sort(key=lambda i: -states[i]["y"])
    return idx


def sound_events(project, voices_dir=None):
    """[(час початку в секундах, ім'я файлу голосу)] для озвучки всього мультика."""
    tl, _ = timeline(project)
    out = []
    for i, start, _ in tl:
        sc = project["scenes"][i]
        _, spans = scene_timing(sc)
        for ln, (a, _) in zip(sc.get("dialog", []), spans):
            if ln.get("voice"):
                out.append((start + a, ln["voice"]))
    return out
