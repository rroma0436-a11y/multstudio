"""Помічник-сюжетник (без інтернету): з простих речень робить мультик із песиком.

«Песик спить у кімнаті. Він прокидається, бачить м'ячик і біжить за ним. Гавкає: "Ура!"»
→ сцени з фоном, предметами, ефектами й ланцюжком дій песика.

Розуміє знайомі слова (основи слів), тому працює з різними формами: «біжить», «побіг», «бігає».
"""
import re
import time

import acts
import model

HERO = "puppy"

# основа слова → дія (порядок важливий: довші/точніші основи — раніше)
VERBS = [
    ("прокида", "stand"), ("проснув", "stand"), ("встає", "stand"), ("встав", "stand"), ("підвод", "stand"),
    ("засина", "sleep"), ("засн", "sleep"), ("спить", "sleep"), ("потягу", "shake"), ("спав", "sleep"), ("дріма", "sleep"),
    ("сіда", "sit"), ("сів", "sit"), ("сидить", "sit"), ("присів", "sit"),
    ("ляга", "lie"), ("ліг", "lie"), ("лежить", "lie"), ("відпочива", "lie"),
    ("біж", "run"), ("біга", "run"), ("побіг", "run"), ("мчить", "run"), ("тікає", "run"), ("женеться", "run"),
    ("стриб", "jump"), ("скач", "jump"), ("підскак", "jump"),
    ("нюха", "sniff"), ("шука", "sniff"),
    ("крадет", "sneak"), ("підкрада", "sneak"),
    ("розверта", "turn"), ("оберта", "turn"),
    ("крут", "spin"), ("верти", "spin"), ("хвіст", "spin"),
    ("перекида", "roll"), ("кача", "roll"),
    ("лап", "paw"),
    ("танц", "dance"),
    ("струшу", "shake"), ("обтруш", "shake"),
    ("грає", "play"), ("гра", "play"), ("бавит", "play"),
    ("гавка", "bark"), ("гав", "bark"), ("дзявка", "bark"),
    ("каже", "talk"), ("говорить", "talk"), ("питає", "talk"), ("кличе", "talk"), ("відповіда", "talk"),
    ("сказав", "talk"), ("співа", "talk"),
    ("радіє", "happy"), ("зраді", "happy"), ("весел", "happy"), ("щасли", "happy"), ("виляє", "happy"),
    ("усміха", "happy"), ("тішит", "happy"),
    ("сумує", "sad"), ("засмут", "sad"), ("сумн", "sad"), ("плаче", "sad"), ("скиглить", "sad"),
    ("боїть", "scared"), ("злякав", "scared"), ("страшн", "scared"), ("лякає", "scared"), ("тремтить", "scared"),
    ("серди", "angry"), ("гарчить", "angry"), ("злиться", "angry"), ("злий", "angry"),
    ("дивуєт", "surprised"), ("здивув", "surprised"), ("бачить", "surprised"), ("помічає", "surprised"),
    ("помітив", "surprised"), ("побачив", "surprised"), ("ого", "surprised"),
    ("дивиться на нас", "look"), ("дивиться", "look"),
    ("гуля", "walk"), ("іде", "walk"), ("йде", "walk"), ("піш", "walk"), ("ходить", "walk"), ("крокує", "walk"),
    ("прийшов", "walk"), ("прогулю", "walk"), ("чека", "wait"),
]
PLACES = [("ліс", "forest"), ("кімнат", "room"), ("вдома", "room"), ("дім", "room"), ("будин", "room"), ("хат", "room"),
          ("двір", "yard"), ("подвір", "yard"), ("сад", "yard"), ("парк", "playground"), ("майданчик", "playground"),
          ("озер", "lake"), ("річк", "lake"), ("ставок", "lake"), ("ставку", "lake"), ("гор", "mountains"), ("вулиц", "street"),
          ("місто", "street"), ("кафе", "cafe"), ("школ", "classroom"), ("клас", "classroom"),
          ("спортзал", "gym"), ("космос", "space"), ("під вод", "underwater"), ("море", "underwater")]
SEASONS = [("зим", "winter"), ("сніг", "winter"), ("осін", "autumn"), ("восени", "autumn"), ("листопад", "autumn"),
           ("весн", "spring"), ("навесні", "spring"), ("літ", "summer"), ("влітку", "summer")]
NIGHT = ("ніч", "вночі", "уночі", "вечір", "ввечері", "зірки")
OBJECTS = [("м'яч", "football"), ("мяч", "football"), ("торт", "cake"), ("сніговик", "snowman"),
           ("ялинк", "christmas_tree"), ("ведмедик", "teddy_bear"), ("іграшк", "teddy_bear"), ("гриб", "mushrooms"),
           ("квіт", "tulip_bed"), ("соняшник", "sunflower"), ("дерев", "oak"), ("кущ", "bush"),
           ("гарбуз", "pumpkin"), ("санчат", "sled"), ("кавун", "watermelon"), ("яблук", "apple"),
           ("морозив", "ice_cream"), ("піц", "pizza"), ("скриньк", "treasure_chest"), ("скарб", "treasure_chest"),
           ("диван", "sofa"), ("ліжк", "bed"), ("лавк", "bench"), ("гойдалк", "swing"), ("гірк", "slide"),
           ("повітрян", "kite"), ("змій", "kite"), ("парасольк", "umbrella"), ("кубик", "blocks"),
           ("листя", "leaf_pile"), ("пень", "stump"), ("колод", "log"), ("сіно", "haystack"), ("міст", "bridge"),
           ("замок", "castle"), ("ліхтар", "lantern"), ("криниц", "well"), ("кошик", "berry_basket")]
EFFECTS = [("сніг", "snow"), ("дощ", "rain"), ("день народження", "confetti"), ("свято", "confetti"),
           ("конфеті", "confetti"), ("зірк", "stars"), ("чарів", "sparkles"), ("диво", "sparkles"),
           ("листопад", "leaves"), ("бульбаш", "bubbles"), ("світлячк", "fireflies"), ("сердечк", "hearts"),
           ("любить", "hearts"), ("пелюстк", "petals")]
SOUNDS = [("гавка", "puppy_bark"), ("гав", "puppy_bark"), ("оплеск", "applause"), ("дзвін", "school_bell")]


def _low(s):
    return s.lower().replace("’", "'").replace("ʼ", "'")


def _rx(stem):
    """Основа слова має стояти на початку слова: «ого!» — так, «його» — ні."""
    return re.compile(r"(?<![\w'])" + re.escape(stem))


def _has(text, stem):
    return _rx(stem).search(text) is not None


def _find(text, table):
    for stem, val in table:
        if _has(text, stem):
            return val
    return None


def _all(text, table):
    out, seen = [], set()
    for stem, val in table:
        if _has(text, stem) and val not in seen:
            seen.add(val)
            out.append(val)
    return out


def _verbs_in_order(fragment):
    """Дії в тому порядку, як вони стоять у тексті."""
    low = _low(fragment)
    hits = []
    for stem, key in VERBS:
        for m in _rx(stem).finditer(low):
            hits.append((m.start(), -len(stem), key))
    hits.sort()
    out, used = [], []
    for pos, neg, key in hits:
        if any(a <= pos < b for a, b in used):
            continue                          # частина вже знайденого слова
        used.append((pos, pos - neg))
        if not out or out[-1] != key:
            out.append(key)
    return out


def _background(cat, place, season, night):
    cands = [b for b in cat.backgrounds if b.startswith(place + "_")]
    if not cands:
        return None
    if night:
        for suf in ("_night", "_winter_night", "_sunset"):
            for b in cands:
                if b.endswith(suf) and (season != "winter" or "winter" in b or suf == "_night"):
                    return b
    pref = f"{place}_{season}"
    if pref in cands:
        return pref
    for s in ("summer", "spring", "autumn", "winter"):
        if f"{place}_{s}" in cands:
            return f"{place}_{s}"
    return cands[0]


def _obj_id(cat, base, season):
    if base in cat.objects:
        return base
    for s in (season, "summer", "spring", "autumn", "winter"):
        if f"{base}_{s}" in cat.objects:
            return f"{base}_{s}"
    return None


def _sentences(text):
    """Поділ на речення, але не всередині лапок («Гав! Піймав!» — одна репліка)."""
    out, buf, inq = [], "", False
    for i, ch in enumerate(text):
        buf += ch
        if ch in "«“":
            inq = True
        elif ch in "»”":
            inq = False
        elif ch == '"':
            inq = not inq
        if not inq and (ch == "\n" or (ch in ".!?…" and (i + 1 == len(text) or text[i + 1] in " \n"))):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def understand(text, cat):
    """Розібрати текст: список сцен-описів [{"bg", "acts": [...], "objects": [...], "effect"}]."""
    full = _low(text)
    season = _find(full, SEASONS) or "summer"
    sentences = _sentences(text)
    scenes = []
    cur = None
    place_now = None
    for sent in sentences:
        low = _low(sent)
        place = _find(low, PLACES)
        night = any(_has(low, w) for w in NIGHT)
        if cur is None or (place and place != place_now):
            place_now = place or place_now or "yard"
            cur = {"bg": _background(cat, place_now, season, night or any(_has(full, w) for w in NIGHT) and not scenes),
                   "acts": [], "objects": [], "effect": None, "words": ""}
            scenes.append(cur)
        cur["words"] += " " + low
        # репліка в лапках або після двокрапки
        speech = re.findall(r"[«\"“](.+?)[»\"”]", sent)
        if not speech and ":" in sent:
            speech = [sent.split(":", 1)[1].strip(" .!")]
        verbs = _verbs_in_order(re.sub(r"[«\"“].+?[»\"”]", "", sent))
        said = False
        for v in verbs:
            a = acts.new_act(v)
            if v in ("talk", "bark"):
                if speech:
                    a["text"] = speech.pop(0)
                    a["style"] = "shout" if "!" in a["text"] else "say"
                said = True
            if _has(low, "вправо") or _has(low, "праворуч"):
                if v in acts.MOVES:
                    a["dir"] = "right"
            if _has(low, "вліво") or _has(low, "ліворуч") or _has(low, "додому"):
                if v in acts.MOVES:
                    a["dir"] = "left"
            cur["acts"].append(a)
        for sp in speech if not said else speech:
            a = acts.new_act("talk")
            a["text"] = sp
            cur["acts"].append(a)
        for base in _all(low, OBJECTS):
            oid = _obj_id(cat, base, season)
            if oid and oid not in cur["objects"]:
                cur["objects"].append(oid)
        eff = _find(low, EFFECTS)
        if eff:
            cur["effect"] = eff
    for sc in scenes:
        if sc["effect"] is None and season == "winter" and "сніг" in full:
            sc["effect"] = "snow"
    return scenes


def build(cat, text, sounds=None):
    """Готовий проєкт із тексту."""
    descs = understand(text, cat)
    if not descs or not any(d["acts"] for d in descs):
        return None
    char = cat.characters.get(HERO)
    if char is None:
        return None
    scenes = []
    for i, d in enumerate(descs):
        sc = model.new_scene(d["bg"] or cat.default_background())
        sc["transition"] = "fade" if i == 0 else "dissolve"
        first = d["acts"][0]["a"] if d["acts"] else "wait"
        frame = "side_calm"
        if first in ("stand", "sleep"):
            frame = "lie"                     # прокидається / спить — починає лежачи
        it = cat.new_item("char", HERO, x=0.18, y=0.06)
        it.update(uid=model.new_uid(), rot=0.0, scale=1.6, anim="alive", acts=d["acts"])
        if frame in char["frames"]:
            it["frame"] = frame
        moving = any(a["a"] in acts.MOVES for a in d["acts"])
        if not moving:
            it["x"] = 0.45
        items = []
        for k, oid in enumerate(d["objects"][:3]):
            ob = cat.new_item("obj", oid, x=0.72 + 0.12 * k if moving else 0.75 - 0.5 * (k % 2), y=0.05)
            ob.update(uid=model.new_uid(), rot=0.0)
            if oid in ("football", "apple", "ice_cream", "teddy_bear", "blocks"):
                ob["scale"] = 0.45
            items.append(ob)
        items.append(it)
        sc["items"] = items
        if d["effect"]:
            sc["effect"] = d["effect"]
        if sounds is not None and any(a["a"] == "bark" for a in d["acts"]):
            pass                               # гавкіт додається сам (репліка «Гав…»)
        scenes.append(sc)
    words = re.sub(r"\s+", " ", text.strip())
    title = words.split(".")[0][:40] or "Мій мультик"
    scenes.insert(0, model.new_title(title, "", "sun"))
    scenes.append(model.new_title("Кінець", "", "sun", ending=True))
    pr = model.new_project(scenes[1]["background"], f"{title[:28]} {time.strftime('%d.%m')}")
    pr["scenes"] = scenes
    if sounds is None or sounds.path("music_flower"):
        pr["music"] = {"builtin": "music_flower", "volume": 0.25}
    return pr


EXAMPLES = [
    "Песик спить у кімнаті. Він прокидається, потягується і гавкає: «Доброго ранку!»",
    "Песик гуляє в лісі восени. Він нюхає слід, бачить гриби й радіє.",
    "Взимку песик біжить по снігу, стрибає й качається. Потім струшується і каже: «Як весело!»",
    "У парку песик бачить м'ячик. Він біжить за ним, стрибає і гавкає: «Гав! Піймав!»",
    "Уночі у дворі песик злякався. Потім він побачив зірки, ліг і заснув.",
]
