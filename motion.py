"""Рухи «однією кнопкою»: вибрали героя й рух — програма сама задає, куди й як він рухається,
підбирає кадри (іде, біжить, летить), а для поїздок сама ставить санчата, самокат, коня чи дракона
й садить героя на них. Без Kivy — перевіряється на звичайному Python."""
import model

# (ключ, назва на кнопці)
MOTIONS = [
    ("stand", "Стоїть на місці"), ("walk", "Іде"), ("run", "Біжить"),
    ("sit_walk", "Сидить → встає й іде"), ("sit_run", "Сидить → встає й біжить"), ("hop", "Стрибає вперед"),
    ("sneak", "Крадеться"), ("fly", "Летить"), ("float", "Пливе в повітрі"), ("jump_up", "Стрибає вгору"),
    ("come", "Приходить у кадр"), ("leave", "Іде з кадру"), ("run_away", "Тікає з кадру"),
    ("sled", "На санчатах"), ("scooter", "На самокаті"), ("bike", "На біговелі"), ("boat", "На човні"),
    ("horse", "Верхи на коні"), ("dragon", "На драконі"), ("balloon", "На повітряній кулі"),
]

# поїздки на предметах: (id предмета, висота предмета відносно героя, де сидить (частка висоти предмета),
#                         кадр героя, шлях)
VEHICLES = {
    "sled": ("sled", 0.45, 0.1, "sit", "line"),
    "scooter": ("scooter", 0.75, 0.12, "side_calm", "line"),
    "bike": ("balance_bike", 0.62, 0.42, "sit", "line"),
    "boat": ("boat", 0.7, 0.35, "sit", "wave"),
    "balloon": ("hot_air_balloon", 2.6, 0.06, "front34_happy", "wave"),
}
# верхи на героях: (id героя, висота «коня» відносно вершника, (де спина: x, y частки), кадр «коня», шлях)
MOUNTS = {
    "horse": ("horse", 1.25, (0.42, 0.62), None, "line"),
    "dragon": ("pastel_dragon", 1.9, (0.44, 0.55), "flying_calm", "wave"),
}


def available(cat, item):
    """Які рухи можна вибрати для цього елемента."""
    keys = [k for k, _ in MOTIONS]
    if item.get("kind") != "char":
        return [k for k in keys if k in ("stand", "walk", "hop", "fly", "float", "come", "leave", "jump_up")]
    out = []
    has_standup = bool((cat.characters[item["id"]].get("cycles") or {}).get("standup"))
    for k in keys:
        if k in ("sit_walk", "sit_run") and not has_standup:
            continue
        if k in VEHICLES and VEHICLES[k][0] not in cat.objects:
            continue
        if k in MOUNTS and MOUNTS[k][0] not in cat.characters:
            continue
        out.append(k)
    return out


def current(item):
    return item.get("motion", "stand")


def _clear(scene, item):
    """Прибрати попередній рух: транспорт, «коня», зв'язки."""
    for key in ("vehicle",):
        uid = item.pop(key, None)
        g = item.pop("ground", None)
        if uid and g:
            item["x"], item["y"] = g             # повертаємо героя на землю, де він стояв
        if uid:
            scene["items"] = [it for it in scene["items"] if it.get("uid") != uid]
            for ln in scene.get("dialog", []):
                if ln.get("speaker") == uid:
                    ln["speaker"] = None
    if item.get("ride_frame_from"):
        item["frame"] = item.pop("ride_frame_from")
    for k in ("end", "ride", "on", "gait", "path"):
        item.pop(k, None)
    if item.get("y", 0) > 0.5 and item.get("motion") in ("fly", "float", "dragon", "balloon"):
        item["y"] = 0.07
    item.pop("motion", None)


def _dir_and_end(item, dist):
    """Куди рухатися: туди, куди дивиться герой; якщо місця мало — розвертається."""
    x = item["x"]
    right = not item.get("flip")
    if right and x + dist > 0.95 and x - dist >= 0.05:
        right = False
    elif not right and x - dist < 0.05 and x + dist <= 0.95:
        right = True
    if right:
        ex = min(0.95, x + dist)
    else:
        ex = max(0.05, x - dist)
    item["flip"] = not right          # усі кадри намальовані обличчям праворуч
    return ex


def _height(cat, it):
    return cat.base_height(it) * it.get("scale", 1.0)


def apply(cat, scene, item, kind):
    """Задати рух елементу сцени. Повертає підказку для користувача (або порожній рядок)."""
    _clear(scene, item)
    if kind == "stand":
        return ""
    frames = cat.characters[item["id"]]["frames"] if item.get("kind") == "char" else {}
    item["motion"] = kind
    y = item.get("y", 0.07)

    if kind in ("sit_walk", "sit_run"):
        item["frame"] = "sit"            # сидить, потім сам встає (кадри з відео) і рушає
        kind = kind[4:]
        item["motion"] = "sit_" + kind
    if kind in ("walk", "run", "hop", "sneak"):
        dist = {"walk": 0.45, "run": 0.7, "hop": 0.5, "sneak": 0.3}[kind]
        ex = _dir_and_end(item, dist)
        item["end"] = {"x": ex, "y": y, "scale": item.get("scale", 1.0)}
        item["gait"] = "run" if kind == "run" else "walk"
        item["path"] = "hops" if kind == "hop" else "line"
        if kind == "sneak":
            item["anim"] = "none"
        return ""
    if kind in ("come", "leave", "run_away"):
        right = not item.get("flip")
        if kind == "come":
            # заходить з-за краю туди, де стоїть зараз
            start = -0.25 if right else 1.25
            item["end"] = {"x": item["x"], "y": y, "scale": item.get("scale", 1.0)}
            item["x"] = start
        else:
            item["end"] = {"x": 1.3 if right else -0.3, "y": y, "scale": item.get("scale", 1.0)}
        item["gait"] = "run" if kind == "run_away" else "walk"
        return ""
    if kind == "jump_up":
        item["anim"] = "jump"
        return ""
    if kind in ("fly", "float"):
        ex = _dir_and_end(item, 0.6)
        item["end"] = {"x": ex, "y": min(0.55, y + 0.3), "scale": item.get("scale", 1.0)}
        item["path"] = "wave" if kind == "float" else "arc"
        if kind == "fly" and ("fly_a" in frames or "flying_calm" in frames or "fly" in frames):
            item["gait"] = "fly"
        else:
            item["ride"] = True          # без кадрів польоту — «чарівний» політ у тій самій позі
        return ""

    hero_h = _height(cat, item)
    item["ground"] = [item["x"], y]
    if kind in VEHICLES:
        oid, rel, seat, frame, path = VEHICLES[kind]
        veh = cat.new_item("obj", oid, x=item["x"], y=y)
        veh["uid"] = model.new_uid()
        veh["rot"] = 0.0
        base_v = cat.base_height(veh)
        veh["scale"] = max(0.05, hero_h * rel / max(0.01, base_v))
        if frame and frame in frames:
            item["ride_frame_from"] = item.get("frame")
            item["frame"] = frame
        hero_h = _height(cat, item)
        vh = cat.base_height(veh) * veh["scale"]
        dist = 0.55 if kind != "balloon" else 0.5
        ex = _dir_and_end(item, dist)
        veh["flip"] = item["flip"]
        lift = 0.3 if kind == "balloon" else 0.0
        veh["end"] = {"x": ex, "y": min(0.6, y + lift), "scale": veh["scale"]}
        veh["path"] = path
        veh["ride"] = True
        item["y"] = y + vh * seat
        item["end"] = {"x": ex, "y": veh["end"]["y"] + vh * seat, "scale": item.get("scale", 1.0)}
        item["path"] = path
        item["ride"] = True
        item["vehicle"] = veh["uid"]
        if kind != "balloon":
            item["on"] = veh["uid"]      # малюється поверх санчат/самоката; у кулі й ракеті — «всередині»
        scene["items"].insert(scene["items"].index(item), veh)
        return ""
    if kind in MOUNTS:
        mid, rel, back, mframe, path = MOUNTS[kind]
        mount = cat.new_item("char", mid, x=item["x"], y=y if kind != "dragon" else max(y, 0.15))
        mount["uid"] = model.new_uid()
        mount["rot"] = 0.0
        mount["anim"] = "none"
        if mframe and mframe in cat.characters[mid]["frames"]:
            mount["frame"] = mframe
            mount["ride"] = True
        if "sit" in frames:
            item["ride_frame_from"] = item.get("frame")
            item["frame"] = "sit"
        rider_h = _height(cat, item)
        mount["scale"] = max(0.05, rider_h * rel / max(0.01, cat.base_height(mount)))
        hm = cat.base_height(mount) * mount["scale"]
        dw, dh = cat.item_dims(mount)
        wm = hm * dw / float(dh) * 9 / 16.0
        ex = _dir_and_end(item, 0.6)
        mount["flip"] = item["flip"]
        bx = (back[0] - 0.5) * wm * (-1 if mount["flip"] else 1)
        lift = 0.3 if kind == "dragon" else 0.0
        mount["end"] = {"x": ex, "y": min(0.55, mount["y"] + lift), "scale": mount["scale"]}
        mount["path"] = path
        item["x"] = mount["x"] + bx
        item["y"] = mount["y"] + hm * back[1]
        item["end"] = {"x": ex + bx, "y": mount["end"]["y"] + hm * back[1], "scale": item.get("scale", 1.0)}
        item["path"] = path
        item["ride"] = True
        item["on"] = mount["uid"]
        item["vehicle"] = mount["uid"]
        item["anim"] = "none"
        scene["items"].insert(scene["items"].index(item), mount)
        return ""
    return ""
