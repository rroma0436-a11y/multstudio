"""Каталог ресурсів: персонажі, предмети, фони; підписи й розміри кадрів.

Модуль не залежить від Kivy, тож його можна перевіряти на звичайному Python.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Зріст дорослої людини на сцені — частка висоти кадру
ADULT = 0.5
# Найбільша висота предмета за замовчуванням (щоб замок чи дерево не вилазили за кадр)
MAX_DEFAULT = 0.92

EMOTIONS = [
    ("calm", "Спокій"), ("happy", "Радіє"), ("sad", "Сумує"), ("angry", "Сердиться"),
    ("scared", "Боїться"), ("surprised", "Дивується"), ("talking", "Говорить"),
    ("crying", "Плаче"), ("laughing", "Сміється"), ("thinking", "Думає"), ("sleeping", "Спить"),
]
VIEWS = [
    ("front_calm", "Анфас"), ("side_calm", "Збоку"), ("side_talking", "Збоку, говорить"),
    ("back", "Ззаду"), ("front_stand", "Стоїть анфас"), ("stand", "Стоїть"),
]
MOVES = [
    ("walk_a", "Іде 1"), ("walk_b", "Іде 2"), ("run_a", "Біжить 1"), ("run_b", "Біжить 2"),
    ("sit", "Сидить"), ("lie", "Лежить"), ("sleep_sofa", "Спить на дивані"), ("curl", "Клубочок"),
    ("flying_calm", "Летить"), ("fly", "Летить"), ("fly_a", "Летить 1"), ("fly_b", "Летить 2"),
    ("move", "Їде"), ("move_a", "Повзе 1"), ("move_b", "Повзе 2"),
]
FRAME_LABELS = {f"front34_{k}": v for k, v in EMOTIONS}
FRAME_LABELS.update(dict(VIEWS))
FRAME_LABELS.update(dict(MOVES))

FRAME_GROUPS = [
    ("emotions", "Емоції", [f"front34_{k}" for k, _ in EMOTIONS]),
    ("views", "Ракурси", [k for k, _ in VIEWS]),
    ("moves", "Рухи й пози", [k for k, _ in MOVES]),
]

HUMAN_CATEGORIES = ("people", "heroes")
UPRIGHT_IDS = ("android", "guard_robot", "helper_bot")  # роботи, що стоять як люди
# Найбільший зріст героя за замовчуванням (дракон не має бути вищим за кадр)
MAX_CHAR = 0.8
# Кадри, де фігура лежить або летить: розмір рахуємо за довжиною, а не за висотою
LONG_FRAMES = ("lie", "sleep_sofa", "flying_calm", "fly", "fly_a", "fly_b", "move_a", "move_b")
# Кадри тварин, де тіло видно збоку (довжина важливіша за висоту)
SIDE_FRAMES = ("side_calm", "side_talking", "walk_a", "walk_b", "run_a", "run_b", "move")


def frame_label(key):
    return FRAME_LABELS.get(key, key.replace("_", " "))


class Catalog:
    def __init__(self, path=None):
        path = path or os.path.join(BASE_DIR, "assets", "catalog.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.data = data
        self.character_categories = data["character_categories"]
        self.object_categories = data["object_categories"]
        self.places = data["background_places"]
        self.characters = {c["id"]: c for c in data["characters"]}
        self.objects = {o["id"]: o for o in data["objects"]}
        self.backgrounds = {b["id"]: b for b in data["backgrounds"]}
        # плавні цикли руху з відео (assets/cycles.json): кадри walk_c00, walk_c01, …
        cyc_path = os.path.join(BASE_DIR, "assets", "cycles.json")
        if os.path.exists(cyc_path):
            try:
                with open(cyc_path, encoding="utf-8") as f:
                    cycles = json.load(f)
            except (OSError, ValueError):
                cycles = {}
            for cid, kinds in cycles.items():
                c = self.characters.get(cid)
                if c is None:
                    continue
                for kind, cy in kinds.items():
                    keys = []
                    for k, rel in enumerate(cy.get("frames", [])):
                        if not os.path.exists(os.path.join(BASE_DIR, rel)):
                            keys = []
                            break
                        key = f"{kind}_c{k:02d}"
                        c["frames"][key] = rel
                        c["dims"][key] = cy["dims"]
                        keys.append(key)
                    if keys:
                        c.setdefault("cycles", {})[kind] = {"frames": keys, "period": float(cy.get("period", 1.0)),
                                                            "h_rel": float(cy.get("h_rel", 1.0)),
                                                            "once": bool(cy.get("once")),
                                                            "view": cy.get("view")}
        import acts
        acts.CHARS = self.characters
        # більші й чіткіші мініатюри (версія 3), якщо вони є
        if os.path.isdir(os.path.join(BASE_DIR, "assets", "thumbs2")):
            def big(p):
                return p.replace("assets/thumbs/", "assets/thumbs2/", 1) if isinstance(p, str) else p
            for c in data["characters"]:
                c["thumb"] = big(c.get("thumb"))
                c["thumbs"] = {k: big(v) for k, v in c.get("thumbs", {}).items()}
            for o in data["objects"]:
                o["thumb"] = big(o.get("thumb"))
            for b in data["backgrounds"]:
                b["thumb"] = big(b.get("thumb"))

    # ---------------- шляхи
    @staticmethod
    def abspath(rel):
        return os.path.join(BASE_DIR, rel)

    def default_background(self):
        for bid in ("yard_summer", "playground_summer", "lake_summer", "forest_summer"):
            if bid in self.backgrounds:
                return bid
        return next(iter(self.backgrounds))

    def resolve_background(self, bg_id):
        """Фон, якого вже немає (старі мультики, готові сюжети), — найближчий із тих, що є."""
        if not bg_id or bg_id.startswith("photo:") or bg_id in self.backgrounds:
            return bg_id or self.default_background()
        place, _, variant = bg_id.partition("_")
        for p in (place,) + PLACE_FALLBACK.get(place, ()):
            cands = [b for b in self.backgrounds.values() if b["place"] == p]
            if cands:
                same = [b for b in cands if b["variant"] == variant]
                return (same or cands)[0]["id"]
        return self.default_background()

    def live_frames(self, bg_id, t):
        """Живий фон: (кадр, наступний кадр, частка між ними) у момент t; None — фон звичайний."""
        bg = self.backgrounds.get(self.resolve_background(bg_id)) if bg_id else None
        frames = (bg or {}).get("frames")
        if not frames or len(frames) < 2:
            return None
        n = len(frames)
        f = max(0.0, t) * float(bg.get("fps", 8))
        if bg.get("loop", "pingpong") == "pingpong":
            period = 2 * (n - 1)
            p = f % period
            pos = p if p <= n - 1 else period - p
        else:
            pos = f % n
        i = int(pos)
        j = min(n - 1, i + 1) if bg.get("loop", "pingpong") == "pingpong" else (i + 1) % n
        if bg.get("loop", "pingpong") == "pingpong" and (f % (2 * (n - 1))) > n - 1:
            i, j = min(n - 1, i + 1), i          # назад: від наступного до попереднього
            k = 1.0 - (pos - int(pos))
        else:
            k = pos - int(pos)
        return self.abspath(frames[i]), self.abspath(frames[j]), k

    def background_path(self, bg_id, project_dir=None):
        """Шлях до картинки фону: із каталогу або фото з телефону («photo:файл» у папці проєкту)."""
        bg_id = bg_id or ""
        if bg_id.startswith("photo:"):
            if not project_dir:
                return None
            p = os.path.join(project_dir, bg_id[6:])
            return p if os.path.exists(p) else None
        bg = self.backgrounds.get(self.resolve_background(bg_id))
        return self.abspath(bg["path"]) if bg else None

    @property
    def stars(self):
        return [self.characters[c] for c in STAR_CHARACTERS if c in self.characters]

    def chars_in(self, cat_id):
        return [c for c in self.stars if c["category"] == cat_id]

    def objects_in(self, cat_id):
        return [o for o in self.objects.values() if o["category"] == cat_id]

    def backgrounds_in(self, place_id):
        return [b for b in self.backgrounds.values() if b["place"] == place_id]

    def frame_groups(self, char_id):
        """[(назва групи, [(ключ кадру, підпис, мініатюра)])] — лише ті кадри, що є."""
        c = self.characters[char_id]
        out = []
        for _, title, keys in FRAME_GROUPS:
            items = [(k, frame_label(k), c["thumbs"][k]) for k in keys if k in c["frames"] and k in c["thumbs"]]
            if items:
                out.append((title, items))
        known = {k for _, _, keys in FRAME_GROUPS for k in keys}
        rest = [(k, frame_label(k), c["thumbs"][k]) for k in c["frames"] if k not in known and k in c["thumbs"]]
        if rest:
            out.append(("Інше", rest))
        return out

    # ---------------- елементи сцени
    def item_path(self, item):
        if item["kind"] == "char":
            c = self.characters[item["id"]]
            frame = item["frame"] if item["frame"] in c["frames"] else self.default_frame(item["id"])
            return self.abspath(c["frames"][frame])
        return self.abspath(self.objects[item["id"]]["path"])

    def item_name(self, item):
        if item["kind"] == "char":
            return self.characters[item["id"]]["name"]
        return self.objects[item["id"]]["name"]

    def default_frame(self, char_id):
        c = self.characters[char_id]
        for k in ("front34_calm", "side_calm", "front_calm"):
            if k in c["frames"]:
                return k
        return next(iter(c["frames"]))

    def item_dims(self, item):
        if item["kind"] == "char":
            c = self.characters[item["id"]]
            return c["dims"].get(item["frame"]) or c["dims"][self.default_frame(item["id"])]
        return self.objects[item["id"]]["dims"]

    def base_height(self, item):
        """Висота елемента (частка висоти сцени) при масштабі 1."""
        w, h = self.item_dims(item)
        aspect = w / float(h)
        if item["kind"] == "obj":
            return min(self.objects[item["id"]]["size"] * ADULT, MAX_DEFAULT)
        c = self.characters[item["id"]]
        s = min(c["size"] * ADULT, MAX_CHAR)
        key = item["frame"]
        if key[-4:-2] == "_c" and key in c["frames"]:
            # кадри з відео — у тому ж масштабі, що й звичайні кадри ходьби, щоб герой не «стрибав» у розмірі
            kind = key[:-4]
            h_rel = (c.get("cycles", {}).get(kind) or {}).get("h_rel", 1.0)
            for ref_key in ("walk_a", "side_calm"):
                if ref_key in c["frames"]:
                    return self.base_height(dict(item, frame=ref_key)) * h_rel
        human = c["category"] in HUMAN_CATEGORIES or c["id"] in UPRIGHT_IDS
        ref = c["dims"].get("side_calm") or c["dims"][self.default_frame(item["id"])]
        ref_aspect = ref[0] / float(ref[1])
        if key in LONG_FRAMES:
            length = s * (1.0 if human else max(1.0, ref_aspect))
            if key == "sleep_sofa":
                length *= 1.3
            return length / aspect
        if not human and key.startswith("front") and "side_calm" in c["frames"] and ref_aspect >= 1.0:
            # тварина спереду — такої ж висоти, як збоку (щоб не «виростала», коли повертається до нас)
            return self.base_height(dict(item, frame="side_calm")) * 1.05
        if not human and key in SIDE_FRAMES and ref_aspect >= 1.0:
            return s * ref_aspect / aspect
        if key == "sit":
            return s * (0.72 if human else 1.0)
        if key == "front34_sleeping":
            return s * 0.62
        return s

    def new_item(self, kind, oid, x=0.5, y=0.08):
        item = {"kind": kind, "id": oid, "x": x, "y": y, "scale": 1.0, "flip": False}
        item["frame"] = self.default_frame(oid) if kind == "char" else ""
        return item


# Герої, з якими працює програма (решта лишається в каталозі для старих мультиків).
# Щоб додати героя — допишіть його id сюди й дайте йому відео-кліпи дій (assets/cycles.json).
STAR_CHARACTERS = ("puppy",)
# якщо фону місця немає — яке місце взяти замість нього
PLACE_FALLBACK = {"forest": ("mountains", "lake", "playground"), "yard": ("playground", "lake", "mountains"),
                  "street": ("playground", "lake"), "room": ("playground", "lake"), "classroom": ("playground",),
                  "cafe": ("playground",), "gym": ("playground",), "underwater": ("lake",), "space": ("space",),
                  "lake": ("lake",), "mountains": ("mountains", "lake"), "playground": ("playground", "lake")}

HIDDEN_SOUNDS = {"kids_laugh", "kids_laugh2", "amb_playground", "well_done"}


class SoundLib:
    """Бібліотека вбудованих звуків (assets/sounds.json)."""

    def __init__(self, path=None):
        path = path or os.path.join(BASE_DIR, "assets", "sounds.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {"categories": [], "sounds": [], "credits": []}
        self.categories = data["categories"]
        # записи, де чути слова іноземною мовою, — прибрано з програми
        self.sounds = {s["id"]: s for s in data["sounds"] if s["id"] not in HIDDEN_SOUNDS}
        self.credits = data.get("credits", [])

    def in_category(self, cat_id):
        return [s for s in self.sounds.values() if s["category"] == cat_id]

    def path(self, sid):
        s = self.sounds.get(sid)
        return os.path.join(BASE_DIR, s["path"]) if s else None

    def name(self, sid):
        s = self.sounds.get(sid)
        return s["name"] if s else "?"
