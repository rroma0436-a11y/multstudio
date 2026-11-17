"""Ланцюжок дій героя: «сидить → встає → іде → гавкає → стрибає → радіє».

Елемент сцени має item["acts"] = [{"a": ключ дії, "dur": секунди, "dir": "left"|"right"|None,
                                  "text": репліка, "style", "voice", "voice_dur"}].
Програма сама вставляє переходи між позами (встати, сісти, лягти), рахує, куди герой дійшов,
і підбирає кадри: спершу кадри з відео (char["cycles"][ключ]), а якщо їх немає — звичайні картинки
з легким «оживленням». Без Kivy — перевіряється на звичайному Python.

Щоб додати нового героя з повним набором дій, достатньо дати йому відео-кліпи з тими самими ключами.
"""
import math

import model

CHARS = {}          # id героя -> запис каталогу (заповнює data.Catalog)

# ключ: (підпис, група, тривалість за замовчуванням, поза до, поза після, швидкість руху (частка ширини/с))
ACTIONS = {
    "walk": ("Іде", "Рух", 3.0, "stand", "stand", 0.12),
    "run": ("Біжить", "Рух", 2.0, "stand", "stand", 0.3),
    "sneak": ("Крадеться", "Рух", 3.0, "stand", "stand", 0.06),
    "sniff": ("Нюхає слід", "Рух", 3.0, "stand", "stand", 0.07),
    "leap": ("Стрибок уперед", "Рух", 1.0, "stand", "stand", 0.25),
    "turn": ("Розвертається", "Рух", 0.8, "stand", "stand", 0.0),
    "stand": ("Встає", "Пози", 0.6, None, "stand", 0.0),
    "sit": ("Сідає", "Пози", 2.0, None, "sit", 0.0),
    "lie": ("Лягає", "Пози", 2.0, None, "lie", 0.0),
    "sleep": ("Спить", "Пози", 3.0, None, "lie", 0.0),
    "wait": ("Стоїть, чекає", "Пози", 1.5, None, None, 0.0),
    "look": ("Дивиться на нас", "Пози", 1.5, "stand", "stand", 0.0),
    "happy": ("Радіє", "Емоції", 2.0, None, None, 0.0),
    "sad": ("Сумує", "Емоції", 2.0, None, None, 0.0),
    "scared": ("Боїться", "Емоції", 2.0, None, None, 0.0),
    "angry": ("Сердиться", "Емоції", 2.0, None, None, 0.0),
    "surprised": ("Дивується", "Емоції", 1.5, None, None, 0.0),
    "talk": ("Говорить", "Говорить", 2.0, None, None, 0.0),
    "bark": ("Гавкає", "Говорить", 1.0, None, None, 0.0),
    "jump": ("Стрибає", "Трюки", 1.6, "stand", "stand", 0.0),
    "spin": ("Крутиться", "Трюки", 1.4, "stand", "stand", 0.0),
    "roll": ("Перекидається", "Трюки", 2.0, "lie", "lie", 0.0),
    "paw": ("Дає лапу", "Трюки", 2.0, "sit", "sit", 0.0),
    "dance": ("Танцює", "Трюки", 2.5, "stand", "stand", 0.0),
    "shake": ("Струшується", "Трюки", 1.2, "stand", "stand", 0.0),
    "play": ("Грається", "Трюки", 2.0, "stand", "stand", 0.0),
}
GROUPS = ["Рух", "Пози", "Емоції", "Говорить", "Трюки"]
MOVES = ("walk", "run", "sneak", "sniff", "leap")
# переходи між позами: (з, у) -> ключ кліпу; без кліпу перехід миттєвий
TRANSITIONS = {("sit", "stand"): "standup", ("lie", "stand"): "getup", ("stand", "sit"): "sitdown",
               ("stand", "lie"): "liedown", ("sit", "lie"): "liedown", ("lie", "sit"): "standup"}
POSE_FRAME = {"stand": "side_calm", "sit": "sit", "lie": "lie"}
EMO_FRAME = {"happy": "happy", "sad": "sad", "scared": "scared", "angry": "angry", "surprised": "surprised",
             "talk": "talking", "bark": "talking"}
EMO_ANIM = {"happy": "hop", "sad": "cry", "scared": "scared", "angry": "angry", "surprised": "surprised",
            "dance": "dance", "play": "hop"}


def label(key):
    return ACTIONS.get(key, (key,))[0]


def new_act(key):
    a = {"a": key, "dur": ACTIONS[key][2]}
    if key in ("talk", "bark"):
        a.update(text="Гав!" if key == "bark" else "Привіт!", style="say" if key == "talk" else "shout")
    return a


def _clips(char):
    return (char or {}).get("cycles") or {}


def start_pose(item):
    f = item.get("frame", "")
    if f.startswith("sit"):
        return "sit"
    if f.startswith(("lie", "sleep")):
        return "lie"
    return "stand"


# ---------------------------------------------------------------------- розклад
def plan(item, char):
    """Розклад: [(t0, t1, ключ, вид, dict дії)], де вид — "act" або "trans"; плюс кінцевий час."""
    clips = _clips(char)
    pose = start_pose(item)
    t = model.MOVE_MARGIN
    out = []
    for act in item.get("acts", []):
        key = act.get("a")
        spec = ACTIONS.get(key)
        if spec is None:
            continue
        need = spec[3]
        if need and need != pose:
            tk = TRANSITIONS.get((pose, need))
            clip = clips.get(tk) if tk else None
            if clip:
                out.append((t, t + clip["period"], tk, "trans", {"from": pose, "to": need}))
                t += clip["period"]
            pose = need
        dur = max(0.3, float(act.get("dur", spec[2])))
        if key in ("talk",) and act.get("voice") and act.get("voice_dur"):
            dur = max(dur, float(act["voice_dur"]) + 0.2)
        clip = clips.get(key)
        if clip and clip.get("once"):
            dur = clip["period"]
        out.append((t, t + dur, key, "act", act))
        t += dur
        if spec[4]:
            pose = spec[4]
    return out, t


def total(item, char):
    return plan(item, char)[1]


# ---------------------------------------------------------------------- стан у момент часу
EDGE = (0.1, 0.9)


def _bounce(x, dist, right):
    lo, hi = EDGE
    while dist > 1e-6:
        room = (hi - x) if right else (x - lo)
        if room <= 0:
            right = not right
            room = hi - lo
        step = min(dist, room)
        x += step if right else -step
        dist -= step
        if dist > 1e-6:
            right = not right
    return x, right
def _frame(char, name, fallback):
    frames = (char or {}).get("frames", {})
    if name in frames:
        return name
    return fallback if fallback in frames else next(iter(frames), "")


def _emo_frame(char, emo, pose):
    if pose == "sit":
        return _frame(char, "sit", "front34_calm")
    if pose == "lie":
        return _frame(char, "lie", "front34_calm")
    return _frame(char, "front34_" + emo, "front34_calm")


def state(item, scene, t, length, char, st):
    """Доповнює st (з model.item_state) позицією й кадром за ланцюжком дій."""
    clips = _clips(char)
    segs, end_t = plan(item, char)
    x, y = item["x"], item["y"]
    right = not item.get("flip")
    pose = start_pose(item)
    cur = None
    for seg in segs:
        t0, t1, key, kind, act = seg
        if t < t0:
            break
        u = min(t, t1) - t0
        if kind == "act":
            d = act.get("dir")
            if d in ("left", "right"):
                right = d == "right"
            if key in MOVES:
                spd = ACTIONS[key][5] * float(act.get("speed", 1.0))
                dist = spd * u if key != "leap" else ACTIONS[key][5] * min(1.0, u / max(0.01, t1 - t0))
                if d in ("left", "right"):
                    x += dist if right else -dist      # напрямок задано — іде навіть за край кадру
                else:
                    # напрямок «як зараз» — біля краю сам розвертається й лишається в кадрі
                    x, right = _bounce(x, dist, right)
            elif key == "turn" and t >= t1:
                right = not right
            if ACTIONS[key][4]:
                pose = ACTIONS[key][4]
        else:
            pose = act["to"] if t >= t1 else act["from"]
        if t < t1:
            cur = seg
            break
    st["x"], st["y"] = x, y
    st["flip"] = not right
    frames = (char or {}).get("frames", {})
    if cur is None:
        # усі дії закінчились — стоїть у кінцевій позі й «дихає»
        st["frame"] = _frame(char, POSE_FRAME[pose], item.get("frame", ""))
        model.apply_anim(st, "alive", t, None)
        return st
    t0, t1, key, kind, act = cur
    u = t - t0
    dur = max(0.01, t1 - t0)
    clip = clips.get(key)
    if clip:
        n = len(clip["frames"])
        if clip.get("once") or kind == "trans":
            st["frame"] = clip["frames"][min(n - 1, int(u / dur * n))]
        else:
            st["frame"] = clip["frames"][int(u / (clip["period"] / n)) % n]
        st["moving"] = key in MOVES
        if key == "leap":
            st["dy"] += 0.12 * math.sin(math.pi * u / dur)
        return st
    if kind == "trans":
        st["frame"] = _frame(char, POSE_FRAME[act["from"] if u < dur / 2 else act["to"]], item.get("frame", ""))
        return st
    # без кліпу — картинки й «оживлення»
    if key in MOVES:
        gait_key = "run" if key == "run" else "walk"
        cyc = clips.get(gait_key)
        if cyc:
            n = len(cyc["frames"])
            step = cyc["period"] / n * (1.6 if key in ("sneak", "sniff") else 1.0)
            st["frame"] = cyc["frames"][int(u / step) % n]
        else:
            a, b = (gait_key + "_a", gait_key + "_b")
            if a not in frames:
                a, b = "walk_a", "walk_b"
            stp = model.RUN_STEP if key == "run" else model.STEP * (1.5 if key in ("sneak", "sniff") else 1.0)
            st["frame"] = _frame(char, a if int(u / stp) % 2 == 0 else b, "side_calm")
        st["moving"] = True
        if key == "sneak":
            st["sy"] *= 0.9
        if key == "leap":
            st["dy"] += 0.12 * math.sin(math.pi * u / dur)
        return st
    if key == "turn":
        st["frame"] = _frame(char, "front_calm", "side_calm") if 0.3 < u / dur < 0.7 else \
            _frame(char, POSE_FRAME["stand"], "")
        st["sx"] *= max(0.15, abs(math.cos(math.pi * u / dur)))
        if u / dur >= 0.5:
            st["flip"] = right            # друга половина — вже в інший бік
        return st
    if key in ("sit", "lie", "stand", "wait"):
        st["frame"] = _frame(char, POSE_FRAME[pose], "side_calm")
        model.apply_anim(st, "alive", u, None)
        return st
    if key == "sleep":
        st["frame"] = _frame(char, "front34_sleeping", "lie")
        model.apply_anim(st, "sleep", u, None)
        st["anim"] = "sleep"
        return st
    if key == "look":
        st["frame"] = _frame(char, "front_calm", "front34_calm")
        model.apply_anim(st, "alive", u, None)
        return st
    if key in ("talk", "bark"):
        talk = _frame(char, "front34_talking" if pose == "stand" else "side_talking", "front34_calm")
        calm = _emo_frame(char, "happy", pose)
        st["frame"] = talk if int(u / model.TALK_STEP) % 2 == 0 else calm
        if key == "bark":
            st["dy"] += 0.01 * abs(math.sin(u * 14))
        return st
    if key in EMO_FRAME:
        st["frame"] = _emo_frame(char, EMO_FRAME[key], pose)
        model.apply_anim(st, EMO_ANIM.get(key, "alive"), u, None)
        return st
    if key == "jump":
        st["frame"] = _frame(char, "side_calm", "")
        model.apply_anim(st, "jump", u, None)
        return st
    if key == "spin":
        st["frame"] = _frame(char, "side_calm", "")
        c = math.cos(2 * math.pi * model.ease(u / dur) * 2)
        st["sx"] *= c if abs(c) > 0.12 else 0.12
        st["dy"] += 0.015 * abs(math.sin(2 * math.pi * u / dur))
        return st
    if key == "roll":
        st["frame"] = _frame(char, "lie", "side_calm")
        st["rot"] += -360.0 * model.ease(u / dur)
        st["dy"] += 0.05 * math.sin(math.pi * u / dur)
        return st
    if key == "paw":
        st["frame"] = _frame(char, "sit", "side_calm")
        st["rot"] += 6 * math.sin(math.pi * min(1.0, u / dur * 2))
        return st
    if key == "shake":
        st["frame"] = _frame(char, "front34_happy", "side_calm")
        st["rot"] += 9 * math.sin(u * 40) * (1 - u / dur)
        return st
    if key in ("dance", "play"):
        st["frame"] = _frame(char, "front34_happy", "side_calm")
        model.apply_anim(st, EMO_ANIM[key], u, frames)
        return st
    return st


# ---------------------------------------------------------------------- репліки
def lines(scene):
    """Репліки з дій «Говорить»/«Гавкає»: [(репліка, початок, кінець)]."""
    out = []
    for it in scene.get("items", []):
        if not it.get("acts"):
            continue
        char = CHARS.get(it.get("id"))
        segs, _ = plan(it, char)
        for t0, t1, key, kind, act in segs:
            if kind == "act" and key in ("talk", "bark") and (act.get("text") or act.get("voice")):
                ln = {"speaker": it.get("uid"), "text": act.get("text", ""), "style": act.get("style", "say"),
                      "voice": act.get("voice"), "voice_dur": act.get("voice_dur")}
                out.append((ln, t0, t1))
    return out


def scene_end(scene):
    m = 0.0
    for it in scene.get("items", []):
        if it.get("acts"):
            m = max(m, total(it, CHARS.get(it.get("id"))))
    return m
