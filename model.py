"""Модель мультика: проєкт = стрічка сцен. Розрахунок часу, руху, ходьби, розмови й камери.

Модуль не залежить від Kivy (перевіряється на звичайному Python).

Проєкт:
  {"version": 2, "title", "scenes": [Scene], "music": {"file", "volume"} | None}
Сцена:
  {"background" (id з каталогу або "photo:photos/файл.jpg"), "items": [Item], "dialog": [Line],
   "duration", "camera", "focus": uid героя для камери, "transition", "filter", "effect", "auto_depth",
   "sfx", "ambience"}
Елемент (герой чи предмет):
  {"uid", "kind": "char"|"obj", "id", "frame", "x", "y", "scale", "flip", "rot",
   "end": {"x", "y", "scale"} | None,         # x — центр, y — низ (ноги); частки сцени
   "anim": дія (танцює, стрибає …), "in_fx"/"in_at", "out_fx"/"out_at": поява й зникнення}
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
    ("focus", "Наїзд на героя"), ("focus_out", "Від героя до всіх"), ("follow", "Стежити за героєм"),
    ("talk", "На того, хто говорить"),
]
FOCUS_MOVES = ("focus", "focus_out", "follow")
TRANSITIONS = [("fade", "Затемнення"), ("cut", "Різко"), ("flash", "Спалах"), ("dissolve", "Розчинення"),
               ("slide_left", "Зсув вліво"), ("slide_right", "Зсув вправо"), ("slide_up", "Зсув угору"),
               ("zoom", "Наїзд"), ("wipe", "Шторка"), ("circle", "Коло")]
TRANS_DUR = {"fade": 0.35, "cut": 0.0, "flash": 0.45, "dissolve": 0.7, "slide_left": 0.6,
             "slide_right": 0.6, "slide_up": 0.6, "zoom": 0.6, "wipe": 0.6, "circle": 0.7}
NEEDS_PREV = ("dissolve", "slide_left", "slide_right", "slide_up", "zoom", "wipe")
FILTERS = [("none", "Звичайно"), ("vivid", "Яскраво"), ("warm", "Тепло"), ("cold", "Холодно"),
           ("night", "Ніч"), ("dream", "Мрія"), ("bw", "Чорно-біле"), ("sepia", "Старе фото"),
           ("film", "Старе кіно")]
FILTER_CODE = {"none": 0, "bw": 1, "sepia": 2, "night": 3, "warm": 4, "cold": 5, "vivid": 6, "dream": 7,
               "film": 8}
EFFECTS = [("none", "Без ефекту"), ("snow", "Сніг"), ("rain", "Дощ"), ("sparkles", "Блискітки"),
           ("hearts", "Сердечка"), ("bubbles", "Бульбашки"), ("leaves", "Листопад"), ("petals", "Пелюстки"),
           ("stars", "Зірочки"), ("confetti", "Конфеті"), ("fireflies", "Світлячки")]
ANIMS = [("none", "Стоїть"), ("alive", "Живий (дихає)"), ("wave", "Вітається"), ("jump", "Стрибає"),
         ("hop", "Підскакує"), ("dance", "Танцює"), ("laugh", "Сміється"), ("talk", "Розповідає"),
         ("surprised", "Дивується"), ("think", "Думає"), ("cry", "Плаче"), ("scared", "Боїться"),
         ("angry", "Сердиться"), ("sleep", "Спить"), ("spin", "Крутиться")]
APPEAR = [("none", "Одразу на місці"), ("fade", "Проявитися"), ("pop", "Вискочити"), ("grow", "Вирости"),
          ("fly_left", "Прилетіти зліва"), ("fly_right", "Прилетіти справа"), ("drop", "Впасти згори"),
          ("spin", "Закрутитися"), ("magic", "Чарівно ★")]
VANISH = [("none", "Не зникати"), ("fade", "Розтанути"), ("pop", "Лопнути"), ("grow", "Зменшитися"),
          ("fly_left", "Полетіти вліво"), ("fly_right", "Полетіти вправо"), ("drop", "Злетіти вгору"),
          ("spin", "Закрутитися"), ("magic", "Чарівно ★")]
SHOW_DUR = 0.5
PATHS = [("line", "Прямо"), ("arc", "Дугою"), ("hops", "Стрибками"), ("wave", "Хвилькою")]
TITLE_COLORS = [("sunset", "Захід", (1.0, 0.55, 0.3), (0.9, 0.3, 0.6)),
                ("sky", "Небо", (0.3, 0.7, 1.0), (0.45, 0.35, 0.95)),
                ("mint", "М'ята", (0.25, 0.85, 0.6), (0.15, 0.6, 0.85)),
                ("candy", "Цукерка", (1.0, 0.5, 0.75), (0.75, 0.45, 1.0)),
                ("night", "Ніч", (0.12, 0.12, 0.35), (0.35, 0.15, 0.5)),
                ("sun", "Сонце", (1.0, 0.85, 0.3), (1.0, 0.55, 0.2))]
ANIM_RAMP = 0.4      # дія розгойдується поступово, а не ривком
BUBBLE_STYLES = [("say", "Звичайна"), ("think", "Думка"), ("shout", "Крик")]

MIN_SCENE = 1.5
FIRST_LINE_AT = 0.4
LINE_GAP = 0.25
MOVE_MARGIN = 0.3
STEP = 0.22          # тривалість одного кроку (кадр «іде 1» / «іде 2»)
RUN_STEP = 0.14      # біг — частіші кроки
FLAP = 0.32          # один змах крил (с)
SINGLE_FLY = ("flying_calm", "fly")    # польоти, намальовані одним кадром — крила «махають» при малюванні
TALK_STEP = 0.18     # як часто «ворушаться губи»
RUN_SPEED = 0.25     # частка ширини сцени за секунду, після якої герой біжить
FADE = 0.35


def new_uid():
    return uuid.uuid4().hex[:8]


def new_scene(background):
    return {"background": background, "items": [], "dialog": [], "duration": 4.0,
            "camera": "none", "transition": "fade", "auto_depth": True,
            "filter": "none", "effect": "none", "focus": None}


def new_project(background, title=None):
    return {"version": 2, "title": title or time.strftime("Мультик %d.%m %H:%M"),
            "scenes": [new_scene(background)], "music": None}


def new_title(text, sub="", color="sunset", ending=False):
    """Сцена-титр: великий напис на кольоровому тлі (назва на початку чи «Кінець»)."""
    return {"kind": "title", "text": text, "sub": sub, "color": color, "background": None, "items": [],
            "dialog": [], "duration": 3.0 if not ending else 2.5, "camera": "none",
            "transition": "fade" if not ending else "dissolve", "filter": "none",
            "effect": "stars" if ending else "sparkles", "auto_depth": True, "ending": ending}


def is_title(scene):
    return scene.get("kind") == "title"


def duplicate_scene(scene):
    s = copy.deepcopy(scene)
    remap = {}
    for it in s["items"]:
        old = it["uid"]
        it["uid"] = new_uid()
        remap[old] = it["uid"]
        for ln in s["dialog"]:
            if ln.get("speaker") == old:
                ln["speaker"] = it["uid"]
        # нова сцена починається там, де закінчився рух у попередній
        end = it.pop("end", None)
        if s.get("focus") == old:
            s["focus"] = it["uid"]
        for k in ("in_fx", "in_at", "out_fx", "out_at"):
            it.pop(k, None)
        if end:
            it.update({k: end[k] for k in ("x", "y", "scale") if k in end})
    for it in s["items"]:
        for k in ("on", "vehicle"):
            if it.get(k):
                it[k] = remap.get(it[k])
    for ln in s["dialog"]:
        ln["voice"] = ln.get("voice")  # голос залишаємо (файл спільний)
    # хто зник у попередній сцені, той у новій уже не з'являється
    gone = {it["uid"] for it, src in zip(s["items"], scene["items"]) if src.get("out_fx", "none") != "none"}
    if gone:
        s["items"] = [it for it in s["items"] if it["uid"] not in gone]
        for ln in s["dialog"]:
            if ln.get("speaker") in gone:
                ln["speaker"] = None
        if s.get("focus") in gone:
            s["focus"] = None
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
    import acts
    end_acts = acts.scene_end(scene)
    end_acts = end_acts + 0.6 if end_acts else 0
    length = max(MIN_SCENE, float(scene.get("duration") or 0), end_lines, end_acts)
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


ANIM_EMOTION = {"wave": ["happy"], "jump": ["happy"], "hop": ["happy"], "dance": ["happy", "laughing"],
                "laugh": ["laughing", "happy"], "talk": ["talking"], "surprised": ["surprised"],
                "think": ["thinking", "calm"], "cry": ["crying", "sad"], "scared": ["scared"],
                "angry": ["angry"], "sleep": ["sleeping"], "spin": ["happy"]}


def _emo(frame, frames, names):
    """Кадр потрібної емоції, якщо герой стоїть «у три чверті» і такий кадр є."""
    if not frame.startswith("front34_"):
        return frame
    for n in names:
        f = "front34_" + n
        if f in frames:
            return f
    return frame


def ease_back(p):
    p = max(0.0, min(1.0, p))
    c = 1.9
    return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2


def ease_bounce(p):
    p = max(0.0, min(1.0, p))
    if p < 1 / 2.75:
        return 7.5625 * p * p
    if p < 2 / 2.75:
        p -= 1.5 / 2.75
        return 7.5625 * p * p + 0.75
    if p < 2.5 / 2.75:
        p -= 2.25 / 2.75
        return 7.5625 * p * p + 0.9375
    p -= 2.625 / 2.75
    return 7.5625 * p * p + 0.984375


def apply_anim(st, anim, u, frames):
    """Дія героя («оживлення»): зміни кадру, підскоки, нахили, «дихання». u — час від початку дії."""
    if not anim or anim == "none":
        return
    tw = 2 * math.pi
    base = st["frame"]
    if frames is not None and anim in ANIM_EMOTION:
        st["frame"] = _emo(base, frames, ANIM_EMOTION[anim])
    # птахи й усі, хто вміє літати, махають крилами, коли радіють чи стрибають
    wings = None
    if frames is not None and anim in ("wave", "jump", "hop", "dance", "surprised", "spin"):
        if "fly_a" in frames and "fly_b" in frames:
            wings = ("fly_a", "fly_b")
        elif "flying_calm" in frames:
            wings = ("flying_calm", "flying_calm")
    if anim == "alive":
        k = math.sin(tw * u / 2.2)
        st["sy"] *= 1 + 0.035 * k
        st["sx"] *= 1 - 0.015 * k
        st["rot"] += 1.5 * math.sin(tw * u / 3.1)
    elif anim == "wave":
        st["rot"] += 14 * math.sin(tw * u * 1.3)
        st["dy"] += 0.025 * abs(math.sin(tw * u * 1.3))
        if wings:
            st["frame"] = wings[int(u / 0.16) % 2]
            st["dy"] += 0.04
    elif anim in ("jump", "hop"):
        per, hgt = (0.95, 0.2) if anim == "jump" else (0.5, 0.06)
        p = (u % per) / per
        if 0.18 < p < 0.82:
            q = (p - 0.18) / 0.64
            st["dy"] += hgt * 4 * q * (1 - q)
            st["sy"] *= 1.08
            st["sx"] *= 0.95
            if wings:
                st["frame"] = wings[int(u / 0.12) % 2]
        else:
            q = (p - 0.82) / 0.36 if p >= 0.82 else (p + 0.18) / 0.36
            sq = math.sin(math.pi * q) * (0.18 if anim == "jump" else 0.09)
            st["sy"] *= 1 - sq
            st["sx"] *= 1 + sq * 0.7
    elif anim == "dance":
        st["rot"] += 16 * math.sin(tw * u / 0.8)
        st["dy"] += 0.05 * abs(math.sin(tw * u / 0.8))
        st["sy"] *= 1 + 0.05 * abs(math.sin(tw * u / 0.4))
        if int(u / 1.6) % 2:
            st["flip"] = not st["flip"]
        if wings:
            st["frame"] = wings[int(u / 0.2) % 2]
        elif frames is not None and int(u / 0.4) % 2:
            st["frame"] = _emo(base, frames, ["laughing", "happy"])
    elif anim == "laugh":
        st["rot"] += 7 * math.sin(u * 22)
        st["sy"] *= 1 + 0.06 * abs(math.sin(u * 11))
        st["dy"] += 0.012 * abs(math.sin(u * 11))
        if frames is not None and int(u / 0.22) % 2:
            st["frame"] = _emo(base, frames, ["happy", "laughing"])
    elif anim == "talk":
        st["rot"] += 5 * math.sin(u * 3)
        st["dy"] += 0.01 * abs(math.sin(u * 6))
        if frames is not None and int(u / TALK_STEP) % 2:
            st["frame"] = _emo(base, frames, ["calm"])
    elif anim == "surprised":
        p = u / 0.6
        if p < 1:
            st["dy"] += 0.12 * 4 * p * (1 - p)
            if wings:
                st["frame"] = wings[int(u / 0.12) % 2]
        st["sy"] *= 1.07
        st["sx"] *= 0.97
    elif anim == "think":
        st["rot"] += 8 * math.sin(u * 1.3)
        st["dy"] += 0.008 * math.sin(u * 2.6)
    elif anim == "cry":
        st["dx"] += 0.006 * math.sin(u * 40)
        st["sy"] *= 0.95 - 0.04 * abs(math.sin(u * 6))
        st["rot"] += 4 * math.sin(u * 2)
    elif anim == "scared":
        st["dx"] += 0.012 * math.sin(u * 55)
        st["sy"] *= 0.93 + 0.02 * math.sin(u * 30)
    elif anim == "angry":
        p = (u % 0.6) / 0.6
        if p < 0.3:
            st["dy"] += 0.045 * math.sin(math.pi * p / 0.3)
        else:
            sq = math.sin(math.pi * (p - 0.3) / 0.7) * 0.06
            st["sy"] *= 1 - sq
            st["sx"] *= 1 + sq
        st["dx"] += 0.006 * math.sin(u * 45)
    elif anim == "sleep":
        if frames is not None and st["frame"] == base and base.startswith("front34_") and "lie" in frames \
                and "front34_sleeping" not in frames:
            st["frame"] = "lie"
        st["sy"] *= 1 + 0.05 * math.sin(u * 2.2)
    elif anim == "spin":
        st["rot"] += -360.0 * ((u / 1.2) % 1.0)
        st["dy"] += 0.04 * abs(math.sin(math.pi * u / 1.2))


def _show(st, item, t):
    """Поява й зникнення елемента."""
    fx_in, fx_out = item.get("in_fx", "none"), item.get("out_fx", "none")
    t_in = float(item.get("in_at", 0) or 0)
    t_out = float(item.get("out_at", 0) or 0)
    if fx_in != "none":
        if t < t_in:
            st["alpha"] = 0.0
            return
        p = (t - t_in) / SHOW_DUR
        if p < 1:
            _show_fx(st, fx_in, p, entering=True)
    if fx_out != "none" and t >= t_out:
        p = (t - t_out) / SHOW_DUR
        if p >= 1:
            st["alpha"] = 0.0
            return
        _show_fx(st, fx_out, 1 - p, entering=False)


def _show_fx(st, fx, p, entering):
    """p: 0 — невидимий, 1 — на місці."""
    e = ease(p)
    if fx == "fade":
        st["alpha"] *= p
    elif fx == "pop":
        k = ease_back(p) if entering else e
        st["sx"] *= max(0.0, k)
        st["sy"] *= max(0.0, k)
        st["alpha"] *= min(1.0, p * 3)
    elif fx == "grow":
        st["sx"] *= e
        st["sy"] *= e
    elif fx == "fly_left":
        st["dx"] -= (st["x"] + 0.35) * (1 - e)
    elif fx == "fly_right":
        st["dx"] += (1.35 - st["x"]) * (1 - e)
    elif fx == "drop":
        k = ease_bounce(p) if entering else e
        st["dy"] += (1.25 - st["y"]) * (1 - k)
    elif fx == "spin":
        st["rot"] += 540 * (1 - e)
        st["sx"] *= e
        st["sy"] *= e
    elif fx == "magic":
        st["alpha"] *= p
        k = 0.5 + 0.5 * e
        st["sx"] *= k
        st["sy"] *= k
        st["magic"] = 1 - p


def item_state(item, scene, local_t, length, char=None, spans=None):
    """Поточний стан елемента: x, y, scale, rot, flip, frame, moving, а ще
    alpha (прозорість), sx/sy (сплющення), dx/dy (зсув у частках сцени), magic (іскри появи).

    char — запис героя з каталогу (потрібен для кадрів ходьби й розмови)."""
    st = {"x": item["x"], "y": item["y"], "scale": item.get("scale", 1.0),
          "rot": item.get("rot", 0.0), "flip": bool(item.get("flip")),
          "frame": item.get("frame", ""), "moving": False,
          "alpha": 1.0, "sx": 1.0, "sy": 1.0, "dx": 0.0, "dy": 0.0, "magic": 0.0,
          "anim": item.get("anim", "none")}
    if item.get("acts") and char is not None:
        import acts
        acts.state(item, scene, local_t, length, char, st)
        if st["frame"] in SINGLE_FLY and "flap" not in st:
            st["flap"] = math.sin(2 * math.pi * local_t / (FLAP * 1.3))
        _show(st, item, local_t)
        return st
    end = item.get("end")
    stand = None
    if end and char is not None and item.get("frame") == "sit":
        stand = (char.get("cycles") or {}).get("standup")      # спершу встає, потім рушає
    if end:
        t0, t1 = MOVE_MARGIN, max(MOVE_MARGIN + 0.3, length - MOVE_MARGIN)
        if stand:
            t0 = MOVE_MARGIN + stand["period"]
            t1 = max(t0 + 0.3, t1)
        raw = (local_t - t0) / (t1 - t0)
        p = ease(raw)
        ex, ey, es = end.get("x", st["x"]), end.get("y", st["y"]), end.get("scale", st["scale"])
        dx, dy = ex - st["x"], ey - st["y"]
        st["x"] += dx * p
        st["y"] += dy * p
        st["scale"] += (es - st["scale"]) * p
        dist = math.hypot(dx, dy)
        path = item.get("path", "line")
        if 0.0 < raw < 1.0:
            if path == "arc":
                st["dy"] += min(0.35, 0.12 + dist * 0.35) * math.sin(math.pi * p)
            elif path == "hops":
                n = max(2, int(round(dist / 0.12)))
                st["dy"] += 0.07 * abs(math.sin(math.pi * p * n))
            elif path == "wave":
                st["dy"] += 0.04 * math.sin(2 * math.pi * p * max(1.5, dist / 0.2))
        if char is not None and dist > 0.01 and 0.0 < raw < 1.0 and not item.get("ride"):
            frames = char["frames"]
            speed = dist / (t1 - t0)
            forced = item.get("gait")
            cycles = char.get("cycles") or {}
            cyc = cycles.get("walk")
            dragon_air = char.get("category") in ("birds", "dragons") and forced != "walk"
            wants_run = forced == "run" or (forced != "walk" and speed > RUN_SPEED)
            if cycles.get("run") and wants_run and not dragon_air:
                cyc = cycles["run"]
                gait = tuple(cyc["frames"])
            elif cyc and forced != "run" and not dragon_air and (forced == "walk" or speed <= RUN_SPEED
                                                               or not ("run_a" in frames)):
                gait = tuple(cyc["frames"])
            elif forced == "run" and "run_a" in frames and "run_b" in frames:
                gait = ("run_a", "run_b")
            elif forced == "walk" and "walk_a" in frames and "walk_b" in frames:
                gait = ("walk_a", "walk_b")
            else:
                gait = _gait(frames, char.get("category"), speed if forced != "walk" else 0.0)
            if gait:
                running = gait[0].startswith("run")
                step = RUN_STEP if running else STEP
                if len(gait) > 2 and cyc:
                    step = cyc["period"] / len(gait)      # плавний цикл із відео
                st["frame"] = gait[int(local_t / step) % len(gait)]
                st["moving"] = True
                if st["frame"] in SINGLE_FLY:
                    st["flap"] = math.sin(2 * math.pi * local_t / FLAP)
                    st["dy"] += 0.012 * math.sin(2 * math.pi * local_t / FLAP + 1.2)
                elif len(gait) > 2:
                    pass                                  # у кадрах із відео рух тіла вже є
                elif path in ("line", "wave"):
                    # тіло підскакує в такт крокам і нахиляється вперед — ходьба й біг «живі»
                    ph = math.pi * local_t / step
                    lean = 1 if dx > 0 else -1
                    if running:
                        st["dy"] += 0.022 * abs(math.sin(ph))
                        st["rot"] += -6 * lean + 2 * math.sin(ph)
                        st["sy"] *= 1 - 0.04 * abs(math.cos(ph))
                    else:
                        st["dy"] += 0.012 * abs(math.sin(ph))
                        st["rot"] += -1.5 * lean + 2 * math.sin(ph)
                        st["sy"] *= 1 - 0.02 * abs(math.cos(ph))
                if abs(dx) > 0.005:
                    st["flip"] = dx < 0       # кадри руху дивляться вправо
    if stand:
        if local_t < t0:
            k = (local_t - MOVE_MARGIN) / stand["period"]
            if k >= 0:
                fr = stand["frames"]
                st["frame"] = fr[min(len(fr) - 1, int(k * len(fr)))]
        elif not st["moving"]:
            # дійшов — стоїть (а не сідає знову)
            st["frame"] = "side_calm" if "side_calm" in char["frames"] else stand["frames"][-1]
    anim = item.get("anim", "none")
    if anim != "none":
        u = local_t - (float(item.get("in_at", 0) or 0) if item.get("in_fx", "none") != "none" else 0.0)
        u = max(0.0, u)
        if end and 0.0 < (local_t - MOVE_MARGIN) and st["moving"] is False and char is not None:
            # після зупинки дія починається плавно
            u = max(0.0, local_t - max(MOVE_MARGIN + 0.3, length - MOVE_MARGIN))
        base = dict(st)
        if st["moving"]:
            apply_anim(st, "alive", u, None)
        else:
            apply_anim(st, anim, u, char["frames"] if char is not None else None)
        k = ease(u / ANIM_RAMP) if anim not in ("alive", "sleep") else 1.0
        if k < 1.0:
            for key in ("dx", "dy", "rot"):
                st[key] = base[key] + (st[key] - base[key]) * k
            for key in ("sx", "sy"):
                st[key] = base[key] + (st[key] - base[key]) * k
    if char is not None and not st["moving"] and spans is not None:
        uid = item.get("uid")
        for ln, (a, b) in zip(scene.get("dialog", []), spans):
            if ln.get("speaker") == uid and a <= local_t < b:
                talk = _talk_frame(st["frame"], char["frames"])
                if talk and int((local_t - a) / TALK_STEP) % 2 == 0:
                    st["frame"] = talk
                break
    if st["frame"] in SINGLE_FLY and "flap" not in st:
        st["flap"] = math.sin(2 * math.pi * local_t / (FLAP * 1.3))
    _show(st, item, local_t)
    return st


def active_lines(scene, local_t, spans):
    """[(репліка, частка показу 0..1)] — що зараз говорять."""
    out = []
    for ln, (a, b) in zip(scene.get("dialog", []), spans):
        if a <= local_t < b + 0.15:
            out.append((ln, (local_t - a) / max(0.01, b - a)))
    import acts
    for ln, a, b in acts.lines(scene):
        if a <= local_t < b + 0.15:
            out.append((ln, (local_t - a) / max(0.01, b - a)))
    return out


def camera(scene, local_t, length, focus_pt=None):
    """(zoom, зсув x, зсув y) — зсув у частках сцени; збільшення навколо центру.

    focus_pt — (x, y) героя в частках сцени для руху «на героя»."""
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
    if mode == "talk" and focus_pt is not None:
        z = 1.0 + 0.3 * focus_pt[2]
        lim = (z - 1) / 2.0
        ox = max(-lim, min(lim, -(focus_pt[0] - 0.5) * z))
        oy = max(-lim, min(lim, -(focus_pt[1] - 0.5) * z))
        return z, ox, oy
    if mode in FOCUS_MOVES and focus_pt is not None:
        q = ease(local_t / max(0.01, min(length * 0.55, 2.2)))
        if mode == "focus":
            z = 1.0 + 0.55 * q
        elif mode == "focus_out":
            z = 1.55 - 0.55 * ease((local_t - length * 0.25) / max(0.01, length * 0.6))
        else:
            z = 1.4
        lim = (z - 1) / 2.0
        ox = max(-lim, min(lim, -(focus_pt[0] - 0.5) * z))
        oy = max(-lim, min(lim, -(focus_pt[1] - 0.5) * z))
        return z, ox, oy
    return 1.0, 0.0, 0.0


def talk_target(scene, local_t, spans):
    """Для камери «на того, хто говорить»: (uid попереднього, uid поточного, прогрес переходу 0..1)."""
    cur, prev, since = None, None, 0.0
    for ln, (a, b) in zip(scene.get("dialog", []), spans):
        if a - 0.25 <= local_t:
            if ln.get("speaker") != cur:
                prev, cur, since = cur, ln.get("speaker"), a - 0.25
        else:
            break
    return prev, cur, ease((local_t - since) / 0.6)


def transition(project, scene_index, local_t, length):
    """Перехід на початку сцени: (вид, прогрес 0..1) або None, коли переходу вже немає.
    Для першої сцени переходи, яким потрібна попередня сцена, стають затемненням."""
    sc = project["scenes"][scene_index]
    kind = sc.get("transition", "fade")
    if scene_index == 0 and kind in NEEDS_PREV:
        kind = "fade"
    dur = TRANS_DUR.get(kind, 0.0)
    if dur <= 0 or local_t >= dur:
        return None
    return kind, max(0.0, local_t / dur)


def end_fade(project, scene_index, local_t, length):
    """Затемнення наприкінці останньої сцени (0 — немає)."""
    if scene_index == len(project["scenes"]) - 1 and length - local_t < FADE:
        return max(0.0, min(1.0, 1 - (length - local_t) / FADE))
    return 0.0


def fade_alpha(project, scene_index, local_t, length):
    """Прозорість чорного затемнення (0 — немає) — для простих випадків."""
    a = 0.0
    tr = transition(project, scene_index, local_t, length)
    if tr and tr[0] == "fade":
        a = 1 - tr[1]
    return max(0.0, min(1.0, max(a, end_fade(project, scene_index, local_t, length))))


def still_time(scene):
    """Момент, коли сцена вже «відкрилась» (для мініатюр і першого кадру)."""
    length, _ = scene_timing(scene)
    return min(length * 0.5, 0.75)


def draw_order(scene, states):
    """Індекси елементів у порядку малювання (дальні спершу)."""
    items = scene["items"]
    idx = list(range(len(items)))
    if scene.get("auto_depth", True):
        pos = {it.get("uid"): k for k, it in enumerate(items)}

        def key(i):
            m = pos.get(items[i].get("on"))
            if m is not None:              # вершник — одразу поверх свого «коня» чи санчат
                return -states[m]["y"] + 1e-4
            return -states[i]["y"]
        idx.sort(key=key)
    return idx


# ---------------------------------------------------------------------- звук
STEP_VOLUME = 0.35
STEP_CATEGORIES = ("people", "heroes")
SHOW_SOUND = {"magic": "magic_bells", "pop": "pop", "spin": "teleport"}
INDOOR = ("room", "classroom", "cafe", "gym")
CITY = ("street", "playground")


def step_sound(background):
    """Який звук кроків пасує до фону."""
    bg = background or ""
    if not bg or bg.startswith("photo:"):
        return None
    place, _, variant = bg.partition("_")
    if "winter" in variant:
        return "step_snow"
    if place in INDOOR:
        return "step_carpet" if place == "room" else "step_wood"
    if place in CITY:
        return "step_stone"
    return "step_grass"


def _step_times(item, scene, length, char, spans):
    """Моменти кроків, поки герой іде чи біжить (не летить і не повзе)."""
    if not item.get("end") or char is None:
        return []
    out = []
    t = 0.0
    last = None
    while t < length:
        st = item_state(item, scene, t, length, char, spans)
        f = st["frame"]
        if st["moving"] and f.startswith(("walk", "run")):
            if "_c" in f:
                k = int(f[-2:])
                kind = f.split("_c")[0]
                n = len((char.get("cycles") or {}).get(kind, {}).get("frames", [])) or 2
                f = "a" if k < n // 2 else "b"          # у циклі з відео — два кроки на цикл
            if f != last:
                out.append(t)
            last = f
        else:
            last = None
        t += STEP / 2.0
    return out


def sound_events(project, get_char=None):
    """Усі звуки мультика.

    Повертає (events, loops):
      events — [(час, джерело, гучність)]
      loops  — [(початок, кінець, джерело, гучність)]  (атмосфера сцени, по колу)
    джерело — ("voice", відносний шлях у папці проєкту) або ("asset", id звуку з бібліотеки).
    """
    tl, _ = timeline(project)
    events, loops = [], []
    steps_on = project.get("auto_steps", True)
    for i, start, length in tl:
        sc = project["scenes"][i]
        _, spans = scene_timing(sc)
        for ln, (a, _) in zip(sc.get("dialog", []), spans):
            if ln.get("voice"):
                events.append((start + a, ("voice", ln["voice"]), 1.0))
        import acts
        for ln, a, _b in acts.lines(sc):
            if ln.get("voice"):
                events.append((start + a, ("voice", ln["voice"]), 1.0))
            elif ln.get("style") == "shout" and ln.get("text", "").lower().startswith("гав"):
                events.append((start + a, ("asset", "puppy_bark"), 0.9))
        for fx in sc.get("sfx", []):
            at = min(max(0.0, float(fx.get("at", 0))), max(0.0, length - 0.05))
            events.append((start + at, ("asset", fx["sound"]), float(fx.get("vol", 1.0))))
        amb = sc.get("ambience")
        if amb and amb.get("sound"):
            loops.append((start, start + length, ("asset", amb["sound"]), float(amb.get("vol", 0.5))))
        for it in sc.get("items", []):
            for fx_key, at_key in (("in_fx", "in_at"), ("out_fx", "out_at")):
                snd_fx = SHOW_SOUND.get(it.get(fx_key, "none"))
                if snd_fx:
                    at = min(max(0.0, float(it.get(at_key, 0) or 0)), max(0.0, length - 0.05))
                    events.append((start + at, ("asset", snd_fx), 0.6))
        if steps_on and get_char is not None:
            snd = step_sound(sc.get("background"))
            for it in (sc.get("items", []) if snd else []):
                if it.get("kind") != "char":
                    continue
                ch = get_char(it["id"])
                if ch is None or ch.get("category") not in STEP_CATEGORIES:
                    continue           # кроки — лише для людей і героїв (тварини ходять тихо)
                for t in _step_times(it, sc, length, get_char(it["id"]), spans):
                    events.append((start + t, ("asset", snd), STEP_VOLUME))
    events.sort(key=lambda e: e[0])
    return events, loops
