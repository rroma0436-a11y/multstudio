"""Помічник-сюжетник (без інтернету): з простих речень робить мультик із песиком.

«Песик спить у кімнаті. Він прокидається, бачить м'ячик і біжить за ним. Гавкає: "Ура!"»
→ сцени з фоном, предметами, ефектами, звуками, ланцюжком дій песика й оповіддю внизу кадру,
яку може прочитати голос оповідача (tts). Песик «грає» кожне речення саме тоді, коли його читають.

Розуміє основи слів, тому працює з різними формами: «біжить», «побіг», «бігає»; «не спить» — пропускає;
«швидко», «повільно», «довго», «двічі» — змінюють дію; «вправо», «додому» — напрямок.
"""
import random
import re
import time

import acts
import model

HERO = "puppy"

# основа слова → дія (порядок важливий: довші/точніші основи — раніше)
VERBS = [
    ("прокида", "stand"), ("проснув", "stand"), ("прокину", "stand"), ("встає", "stand"), ("встав", "stand"),
    ("підвод", "stand"), ("підвів", "stand"), ("піднявся", "stand"),
    ("засина", "sleep"), ("спала$", "sleep"), ("спало$", "sleep"), ("засн", "sleep"), ("спить", "sleep"), ("спав", "sleep"), ("дріма", "sleep"),
    ("задріма", "sleep"), ("сопе", "sleep"), ("хропе", "sleep"),
    ("потягу", "shake"), ("позіха", "shake"), ("чуха", "shake"), ("струшу", "shake"), ("обтруш", "shake"),
    ("трусит", "shake"),
    ("сіда", "sit"), ("сів", "sit"), ("сіла$", "sit"), ("сіло$", "sit"), ("сиді", "sit"), ("сидить", "sit"), ("присів", "sit"), ("присіда", "sit"),
    ("ляг", "lie"), ("ліг", "lie"), ("лежа", "lie"), ("лежить", "lie"), ("відпочива", "lie"), ("розлігся", "lie"),
    ("вмости", "lie"), ("впав", "lie"),
    ("біж", "run"), ("біга", "run"), ("бігл", "run"), ("побіг", "run"), ("мчить", "run"), ("мчи", "run"), ("тікає", "run"),
    ("втіка", "run"), ("женеться", "run"), ("наздоган", "run"), ("кинувся", "run"), ("гаса", "run"),
    ("прино", "run"), ("приніс", "run"), ("несе", "run"),
    ("стриб", "jump"), ("скач", "jump"), ("скака", "jump"), ("підскак", "jump"), ("підстриб", "jump"),
    ("плига", "jump"), ("лови", "jump"), ("піймав", "jump"), ("спійма", "jump"), ("хапа", "jump"),
    ("літа", "jump"), ("летить", "jump"),
    ("нюха", "sniff"), ("шука", "sniff"), ("принюх", "sniff"), ("обнюх", "sniff"), ("винюх", "sniff"),
    ("копа", "sniff"), ("риє", "sniff"), ("їсть", "sniff"), ("їв", "sniff"), ("з'ї", "sniff"), ("їл", "sniff"), ("гризе", "sniff"),
    ("п'є", "sniff"), ("хлебче", "sniff"), ("смаку", "sniff"), ("обіда", "sniff"), ("снідає", "sniff"),
    ("вечеря", "sniff"), ("досліджу", "sniff"),
    ("крадет", "sneak"), ("підкрада", "sneak"), ("крадуч", "sneak"), ("повзе", "sneak"), ("лізе", "sneak"),
    ("хова", "sneak"),
    ("повертається додому", "walk"), ("вертається", "walk"),
    ("розверта", "turn"), ("оберта", "turn"), ("огляда", "turn"), ("поверта", "turn"),
    ("крут", "spin"), ("верти", "spin"), ("кружля", "spin"), ("закрут", "spin"),
    ("перекида", "roll"), ("перекинув", "roll"), ("качаєт", "roll"), ("качався", "roll"), ("покача", "roll"),
    ("качаю", "roll"), ("валя", "roll"),
    ("дає лап", "paw"), ("подає лап", "paw"), ("лапу", "paw"), ("лапк", "paw"),
    ("танц", "dance"), ("витанц", "dance"),
    ("грає", "play"), ("граєть", "play"), ("грався", "play"), ("гратися", "play"), ("бавит", "play"),
    ("бавить", "play"), ("пустує", "play"), ("грал", "play"), ("веселиться", "play"),
    ("гавка", "bark"), ("гавкн", "bark"), ("загавка", "bark"), ("гав", "bark"), ("дзявка", "bark"),
    ("каже", "talk"), ("сказав", "talk"), ("сказа", "talk"), ("говори", "talk"), ("питає", "talk"),
    ("запита", "talk"), ("спита", "talk"), ("кличе", "talk"), ("поклика", "talk"), ("відповіда", "talk"),
    ("відповів", "talk"), ("кричить", "talk"), ("закрича", "talk"), ("вигуку", "talk"), ("шепоче", "talk"),
    ("прошепоті", "talk"), ("співа", "talk"), ("заспіва", "talk"), ("думає", "talk"), ("подума", "talk"),
    ("мріє", "talk"), ("вітаєть", "talk"), ("привіта", "talk"), ("дяку", "talk"), ("подякува", "talk"),
    ("просить", "talk"), ("попроси", "talk"), ("розповіда", "talk"),
    ("радіє", "happy"), ("зраді", "happy"), ("весел", "happy"), ("щасли", "happy"), ("виляє", "happy"),
    ("усміха", "happy"), ("посміха", "happy"), ("тішит", "happy"), ("сміється", "happy"), ("засмія", "happy"),
    ("регоче", "happy"), ("смія", "happy"), ("раді", "happy"), ("обійма", "happy"), ("цілує", "happy"), ("лащит", "happy"),
    ("сумує", "sad"), ("засмут", "sad"), ("сумн", "sad"), ("плаче", "sad"), ("заплака", "sad"),
    ("скиглить", "sad"), ("плака", "sad"), ("сумува", "sad"), ("скавучить", "sad"), ("журить", "sad"),
    ("боїть", "scared"), ("злякав", "scared"), ("злякал", "scared"), ("страшн", "scared"), ("лякає", "scared"),
    ("перелякав", "scared"), ("тремтить", "scared"), ("боял", "scared"), ("боїт", "scared"), ("труситься", "scared"),
    ("серди", "angry"), ("розсерди", "angry"), ("гарчить", "angry"), ("загарча", "angry"), ("злиться", "angry"),
    ("злий", "angry"),
    ("дивуєт", "surprised"), ("здивув", "surprised"), ("бачить", "surprised"), ("помічає", "surprised"),
    ("помітив", "surprised"), ("побачи", "surprised"), ("знаходить", "surprised"), ("знайшов", "surprised"),
    ("ого", "surprised"), ("раптом", "surprised"),
    ("дивиться на нас", "look"), ("дивиться", "look"), ("роздивля", "look"), ("спостеріга", "look"),
    ("вдивля", "look"), ("дивил", "look"),
    ("гуля", "walk"), ("іде", "walk"), ("йде", "walk"), ("іду", "walk"), ("піш", "walk"), ("ходи", "walk"),
    ("крокує", "walk"), ("прийш", "walk"), ("прогулю", "walk"), ("мандру", "walk"), ("вируша", "walk"),
    ("плава", "walk"), ("пливе", "walk"), ("захо", "walk"), ("прихо", "walk"), ("вихо", "walk"),
    ("чека", "wait"), ("стоїть", "wait"),
]
# що сказати, якщо репліки в лапках немає
SAY_DEFAULT = {"вітаєть": "Привіт!", "привіта": "Привіт!", "дяку": "Дякую!", "подякува": "Дякую!",
               "співа": "Ля-ля-ля!", "заспіва": "Ля-ля-ля!", "кличе": "Гей, ходи сюди!", "поклика": "Гей, ходи сюди!",
               "просить": "Будь ласка!", "попроси": "Будь ласка!", "кричить": "Агов!", "закрича": "Агов!"}
THINK = ("думає", "подума", "мріє")
SHOUT = ("кричить", "закрича", "вигуку", "гавка", "гавкн", "загавка", "гав", "дзявка")

PLACES = [("ліс", "forest"), ("гай", "forest"), ("кімнат", "room"), ("вдома", "room"), ("удома", "room"),
          ("дома", "room"), ("додому", "room"), ("дім", "room"), ("будин", "room"), ("хат", "room"),
          ("квартир", "room"), ("кухн", "room"), ("спальн", "room"), ("вітальн", "room"), ("двір", "yard"), ("подвір", "yard"), ("сад", "yard"), ("город", "yard"),
          ("поле$", "yard"), ("полі$", "yard"), ("поля$", "yard"), ("луг", "yard"), ("галявин", "yard"), ("село", "yard"), ("парк", "playground"),
          ("майданчик", "playground"), ("озер", "lake"), ("річк", "lake"), ("ставок", "lake"), ("ставку", "lake"),
          ("берег", "lake"), ("пляж", "lake"), ("гори$", "mountains"), ("горах$", "mountains"), ("гору$", "mountains"),
          ("горі$", "mountains"), ("гірськ", "mountains"), ("горам$", "mountains"),
          ("вулиц", "street"), ("місто", "street"), ("місті", "street"), ("міста", "street"), ("кафе", "cafe"),
          ("ресторан", "cafe"), ("школ", "classroom"), ("клас$", "classroom"), ("класі$", "classroom"),
          ("класу$", "classroom"), ("спортзал", "gym"),
          ("космос", "space"), ("космічн", "space"), ("ракет", "space"), ("під вод", "underwater"),
          ("море", "underwater"), ("морі", "underwater"), ("океан", "underwater")]
PLACE_TITLE = {"forest": "у лісі", "room": "вдома", "yard": "у дворі", "playground": "у парку",
               "lake": "біля озера", "mountains": "у горах", "street": "на вулиці", "cafe": "у кафе",
               "classroom": "у школі", "gym": "у спортзалі", "space": "у космосі", "underwater": "під водою"}
PLACE_NAME = {"forest": "Ліс", "room": "Кімната", "yard": "Двір", "playground": "Парк", "lake": "Озеро",
              "mountains": "Гори", "street": "Вулиця", "cafe": "Кафе", "classroom": "Школа", "gym": "Спортзал",
              "space": "Космос", "underwater": "Під водою"}
SEASONS = [("зим", "winter"), ("взимку", "winter"), ("сніг", "winter"), ("осін", "autumn"), ("восени", "autumn"),
           ("листопад", "autumn"), ("весн", "spring"), ("навесні", "spring"), ("літо", "summer"),
           ("літку", "summer"), ("влітку", "summer"), ("улітку", "summer"), ("літн", "summer"), ("спек", "summer")]
SEASON_NAME = {"winter": "зима", "autumn": "осінь", "spring": "весна", "summer": "літо"}
NIGHT = ("ніч$", "ночі$", "нічк", "нічн", "вночі", "уночі", "вечір", "ввечері", "увечері", "темно", "місяц")
OBJECTS = [("м'яч", "football"), ("мяч", "football"), ("торт", "cake"), ("сніговик", "snowman"),
           ("ялинк", "christmas_tree"), ("ялина$", "spruce"), ("ялину$", "spruce"), ("ялини$", "spruce"), ("сосн", "spruce"), ("ведмедик", "teddy_bear"),
           ("іграшк", "teddy_bear"), ("гриб", "mushrooms"), ("тюльпан", "tulip_bed"), ("квіт", "tulip_bed"),
           ("ромашк", "wildflowers"), ("соняшник", "sunflower"), ("дуб", "oak"), ("берез", "birch"),
           ("дерев", "oak"), ("кущ", "bush"), ("гарбуз", "pumpkin"), ("санчат", "sled"), ("санк", "sled"),
           ("кавун", "watermelon"), ("яблук", "apple"), ("морозив", "ice_cream"), ("піц", "pizza"),
           ("скриньк", "treasure_chest"), ("скарб", "treasure_chest"), ("диван", "sofa"), ("ліжк", "bed"),
           ("лавк", "bench"), ("гойдалк", "swing"), ("гірк", "slide"), ("повітряна кул", "hot_air_balloon"),
           ("повітряну кул", "hot_air_balloon"), ("повітрян", "kite"), ("змія$", "kite"), ("змій$", "kite"), ("парасольк", "umbrella"),
           ("кубик", "blocks"), ("листя", "leaf_pile"), ("пень", "stump"), ("колод", "log"), ("сіно", "haystack"),
           ("копиц", "haystack"), ("міст$", "bridge"), ("мосту$", "bridge"), ("мості$", "bridge"), ("замок", "castle"), ("замку", "castle"),
           ("ліхтар", "lantern"), ("криниц", "well"), ("колодяз", "well"), ("кошик", "berry_basket"), ("ягід", "berry_basket"),
           ("книжк", "books"), ("книг", "books"), ("рюкзак", "backpack"), ("машин", "car"), ("автобус", "bus"),
           ("потяг$", "train"), ("потягом$", "train"), ("поїзд", "train"), ("ракет", "rocket"), ("човен", "boat"), ("човник", "boat"),
           ("велосипед", "balance_bike"), ("беговел", "balance_bike"), ("самокат", "scooter"),
           ("трактор", "tractor"), ("стіл$", "table"), ("столі$", "table"), ("стола$", "table"), ("стільц", "chair"),
           ("стілець", "chair"),
           ("крісл", "armchair"), ("телевізор", "tv"), ("глобус", "globe"), ("хліб", "bread"), ("чашк", "tea_cup"),
           ("чай", "tea_cup"), ("скакалк", "jump_rope"), ("баскетб", "basketball_hoop"), ("гантел", "dumbbell"),
           ("писанк", "easter_eggs"), ("яйц", "easter_eggs"), ("паличк", "magic_wand"), ("камін", "boulder"),
           ("камінц", "pebbles"), ("трав", "tall_grass")]
SMALL = ("football", "apple", "ice_cream", "teddy_bear", "blocks", "books", "backpack", "bread", "tea_cup",
         "pebbles", "magic_wand", "easter_eggs", "jump_rope", "berry_basket", "pizza", "watermelon", "pumpkin",
         "mushrooms", "dumbbell", "globe")
EFFECTS = [("сніг", "snow"), ("дощ", "rain"), ("злив", "rain"), ("день народження", "confetti"),
           ("свято", "confetti"), ("конфеті", "confetti"), ("салют", "confetti"), ("зірк", "stars"),
           ("зорі", "stars"), ("чарів", "sparkles"), ("диво", "sparkles"), ("магі", "sparkles"),
           ("веселк", "sparkles"), ("листопад", "leaves"), ("листя пада", "leaves"), ("бульбаш", "bubbles"),
           ("світлячк", "fireflies"), ("сердечк", "hearts"), ("любить", "hearts"), ("кохає", "hearts"),
           ("пелюстк", "petals")]
AMBIENCE = {"forest": "amb_forest", "yard": "amb_birds", "playground": "amb_birds", "lake": "amb_river",
            "mountains": "amb_river", "street": "amb_street", "space": "amb_space", "underwater": "amb_river"}
FAST = ("швидко", "хутко", "щодуху", "стрімголов", "мерщій")
SLOW = ("повільно", "поволі", "тихо", "тихенько", "обережно", "помалу")
LONG = ("довго", "довгенько")
SHORT = ("трохи", "трішки", "трошки", "хвилинку")
TWICE = ("двічі", "два рази")
THRICE = ("тричі", "три рази")
RIGHT = ("вправо", "праворуч", "направо")
LEFT = ("вліво", "ліворуч", "наліво", "назад", "додому")
GAV = re.compile(r"^\s*((г[аa]в|тяв|ррр?|р-р+)[\s\-!,.…]*)+$", re.IGNORECASE)


def _low(s):
    return s.lower().replace("’", "'").replace("ʼ", "'").replace("`", "'")


_RX = {}


def _rx(stem):
    """Основа слова має стояти на початку слова: «ого!» — так, «його» — ні.
    «слово$» — лише ціле слово («ніч$» — так, «нічого» — ні)."""
    r = _RX.get(stem)
    if r is None:
        if stem.endswith("$"):
            r = re.compile(r"(?<![\w'])" + re.escape(stem[:-1]) + r"(?![\w'])")
        else:
            r = re.compile(r"(?<![\w'])" + re.escape(stem))
        _RX[stem] = r
    return r


def _has(text, stem):
    return _rx(stem).search(text) is not None


def _any(text, stems):
    return any(_has(text, s) for s in stems)


def _find(text, table):
    for stem, val in table:
        if _has(text, stem):
            return val
    return None


def _all(text, table):
    out, seen = [], set()
    hits = []
    for stem, val in table:
        m = _rx(stem).search(text)
        if m and val not in seen:
            seen.add(val)
            hits.append((m.start(), val))
    hits.sort()
    for _p, val in hits:
        out.append(val)
    return out


def is_bark(text):
    """Репліка — лише гавкіт («Гав!», «Гав-гав!») → справжній звук, а не голос."""
    return bool(text) and bool(GAV.match(text.strip()))


def _verbs(fragment):
    """[(позиція, кінець, ключ дії, основа)] у порядку тексту, без заперечених («не спить»)."""
    low = _low(fragment)
    hits = []
    for stem, key in VERBS:
        for m in _rx(stem).finditer(low):
            hits.append((m.start(), -len(stem), key, stem))
    hits.sort()
    out, used = [], []
    for pos, neg, key, stem in hits:
        if any(a <= pos < b for a, b in used):
            continue                          # частина вже знайденого слова
        end = pos - neg
        while end < len(low) and (low[end].isalpha() or low[end] == "'"):
            end += 1
        used.append((pos, end))
        if low[max(0, pos - 3):pos] == "не ":
            continue                          # «не спить» — не спить
        out.append((pos, end, key, stem))
    return out


def _modify(a, window):
    key = a["a"]
    mv = key in acts.MOVES
    if _any(window, FAST):
        if mv:
            a["speed"] = 1.6
            if key == "walk":
                a["a"] = "run"
                a["dur"] = acts.ACTIONS["run"][2]
        else:
            a["dur"] = round(a["dur"] * 0.7, 2)
    elif _any(window, SLOW):
        if mv:
            a["speed"] = 0.6
            a["dur"] = round(a["dur"] * 1.3, 2)
    if _any(window, LONG):
        a["dur"] = round(a["dur"] * 1.8, 2)
    elif _any(window, SHORT):
        a["dur"] = round(max(0.6, a["dur"] * 0.6), 2)
    if a["a"] in acts.MOVES:
        if _any(window, RIGHT):
            a["dir"] = "right"
        elif _any(window, LEFT):
            a["dir"] = "left"
    rep = 3 if _any(window, THRICE) else 2 if _any(window, TWICE) else 1
    return rep


def _background(cat, place, season, night):
    cands = [b for b in cat.backgrounds if b.startswith(place + "_")]
    if not cands:
        return None
    if night:
        for suf in ("_winter_night", "_night", "_sunset"):
            for b in cands:
                if b.endswith(suf) and (suf != "_winter_night" or season == "winter"):
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
        if ch in "«“„":
            inq = True
        elif ch in "»”":
            inq = False
        elif ch == '"':
            inq = not inq
        # кінець речення: крапка/знак поза лапками або закриті лапки після «!» чи «?» і далі велика літера
        after_quote = (ch in "»”" or (ch == '"' and not inq)) and len(buf) > 1 and buf[-2] in ".!?…" and \
            i + 2 < len(text) and text[i + 1] == " " and text[i + 2].isupper()
        if not inq and (ch == "\n" or after_quote or
                        (ch in ".!?…" and (i + 1 == len(text) or text[i + 1] in " \n"))):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


SEP = re.compile(r",|;|:|(?<![\w'])(?:і|й|та|а|потім|тоді)(?![\w'])")
QUOTE = re.compile(r"[«\"“„](.+?)[»\"”“]")


def _narration(sent):
    """Що читає оповідач: речення без реплік у лапках."""
    t = QUOTE.sub("", sent)
    t = re.sub(r"\s+", " ", t).strip()
    end = "!" if re.search(r"!\s*$", t) and not QUOTE.search(sent) else "."
    t = re.sub(r"[\s:;,.!?…—–-]+$", "", t).strip()
    t = re.sub(r"\s+([,.!?…])", r"\1", t)
    if not re.search(r"\w", t):
        return ""
    return t[0].upper() + t[1:] + end


def _genitive(name):
    """Бім → Біма, Тузик → Тузика, Лайка → Лайки (для назви «Пригоди …»)."""
    if not name:
        return name
    if name[-1] in "аАя":
        return name[:-1] + ("и" if name[-1] == "а" else "і")
    if name[-1] in "оО":
        return name[:-1] + "а"
    if name[-1] in "йь":
        return name[:-1] + "я"
    return name + "а"


def hero_name(text):
    m = re.search(r"(?:[Пп]есик|[Цц]уценя|[Пп]ес|[Сс]обачка|[Пп]есика)\s+([А-ЯІЇЄҐ][а-яіїєґ']{1,14})", text)
    if m and m.group(1) not in ("Він", "Вона", "Потім", "Раптом", "Аж"):
        return m.group(1)
    return None


def understand(text, cat):
    """Розібрати текст: сцени [{"bg", "place", "night", "objects", "effect", "sentences": [
    {"narr": текст для оповідача, "acts": [дії]}]}]."""
    full = _low(text)
    season = _find(full, SEASONS) or "summer"
    scenes = []
    cur = None
    place_now = None
    for sent in _sentences(text):
        low = _low(sent)
        place = _find(low, PLACES)
        night = _any(low, NIGHT)
        if cur is None or (place and place != place_now):
            place_now = place or place_now or "yard"
            cur = {"place": place_now, "night": night,
                   "bg": None, "objects": [], "effect": None, "sentences": [], "words": ""}
            cur["bg"] = _background(cat, place_now, season, cur["night"])
            scenes.append(cur)
        elif night and not cur["night"]:
            cur["night"] = True
            cur["bg"] = _background(cat, place_now, season, True) or cur["bg"]
        cur["words"] += " " + low
        speech = QUOTE.findall(sent)
        if not speech and ":" in sent:
            tail = sent.split(":", 1)[1].strip(" .")
            if tail:
                speech = [tail]
        body = QUOTE.sub(" ", sent)
        hits = _verbs(body)
        body_low = _low(body)
        out = []
        said = False
        for i, (pos, end, key, stem) in enumerate(hits):
            nxt = hits[i + 1][0] if i + 1 < len(hits) else len(body_low)
            prv = hits[i - 1][1] if i > 0 else 0
            # слова, що стосуються саме цієї дії: від попередньої коми/«і» до наступної
            left = [m.end() for m in SEP.finditer(body_low, prv, pos)]
            right = [m.start() for m in SEP.finditer(body_low, end, nxt)]
            window = body_low[left[-1] if left else prv:right[0] if right else nxt]
            a = acts.new_act(key)
            if key in ("talk", "bark"):
                if speech:
                    a["text"] = speech.pop(0).strip()
                elif stem in SAY_DEFAULT:
                    a["text"] = SAY_DEFAULT[stem]
                elif key == "talk":
                    continue                      # «каже» без слів — нічого показувати
                a["style"] = "think" if stem in THINK else "shout" if (stem in SHOUT or "!" in a["text"]) else "say"
                said = True
            rep = _modify(a, window)
            for _r in range(rep):
                out.append(dict(a))
        if not said:
            for sp in speech:
                a = acts.new_act("talk")
                a["text"] = sp.strip()
                a["style"] = "shout" if "!" in sp else "say"
                out.append(a)
        # однакові дії поспіль — одна (крім повторів «двічі»)
        clean = []
        for a in out:
            if clean and clean[-1]["a"] == a["a"] and a["a"] not in ("talk", "bark", "jump", "spin", "roll") and \
                    clean[-1].get("text") == a.get("text"):
                continue
            clean.append(a)
        cur["sentences"].append({"narr": _narration(sent), "acts": clean})
        for base in _all(low, OBJECTS):
            oid = _obj_id(cat, base, season)
            if oid and oid not in cur["objects"]:
                cur["objects"].append(oid)
        eff = _find(low, EFFECTS)
        if eff:
            cur["effect"] = eff
    for sc in scenes:
        if sc["effect"] is None and season == "winter" and _has(full, "сніг"):
            sc["effect"] = "snow"
        if sc["effect"] is None and sc["night"] and sc["place"] in ("forest", "yard", "lake", "mountains"):
            sc["effect"] = "fireflies" if season == "summer" else None
    return scenes, season


def explain(text, cat):
    """Коротко: що програма зрозуміла (для підказки під полем вводу)."""
    try:
        scenes, season = understand(text, cat)
    except Exception:
        return ""
    if not scenes:
        return ""
    rows = []
    n_acts = 0
    for i, sc in enumerate(scenes):
        where = PLACE_NAME.get(sc["place"], sc["place"])
        if sc["night"]:
            where += ", ніч"
        elif season != "summer" or i == 0:
            where += ", " + SEASON_NAME[season]
        chain = []
        for s in sc["sentences"]:
            for a in s["acts"]:
                n_acts += 1
                lb = acts.label(a["a"]).lower()
                if a["a"] in ("talk", "bark") and a.get("text"):
                    lb += f" «{a['text'][:18]}»"
                chain.append(lb)
        line = f"{i + 1}) {where}: " + (" → ".join(chain) if chain else "…")
        extra = []
        if sc["objects"]:
            extra.append(", ".join(_obj_name(cat, o) for o in sc["objects"][:3]))
        if sc["effect"]:
            extra.append(dict(model.EFFECTS).get(sc["effect"], sc["effect"]).lower())
        if extra:
            line += "  · " + "; ".join(extra)
        rows.append(line)
    if n_acts == 0:
        return "Поки не бачу, що робить песик. Додайте дію: іде, біжить, стрибає, радіє…"
    return "\n".join(rows)


def _obj_name(cat, oid):
    o = cat.objects.get(oid) or {}
    return (o.get("name") or oid).split("(")[0].strip().lower()


# ---------------------------------------------------------------------- мультик
def build(cat, text, sounds=None, captions=True):
    """Готовий проєкт із тексту (оповідь — репліки «Оповідача» внизу кадру)."""
    descs, season = understand(text, cat)
    if not descs or not any(s["acts"] for d in descs for s in d["sentences"]):
        return None
    char = cat.characters.get(HERO)
    if char is None:
        return None
    scenes = []
    x_end = None
    for i, d in enumerate(descs):
        sc = model.new_scene(d["bg"] or cat.default_background())
        sc["transition"] = "fade" if i == 0 else "dissolve"
        chain = []
        for k, s in enumerate(d["sentences"]):
            for a in s["acts"]:
                a = dict(a)
                a["s"] = k
                chain.append(a)
        first = chain[0]["a"] if chain else "wait"
        frame = "side_calm"
        if first in ("stand", "sleep"):
            frame = "lie"                     # прокидається / спить — починає лежачи
        moving = any(a["a"] in acts.MOVES for a in chain)
        x0 = 0.18 if moving else 0.45
        if i > 0 and x_end is not None and descs[i - 1]["place"] == d["place"]:
            x0 = x_end
        it = cat.new_item("char", HERO, x=x0, y=0.06)
        it.update(uid=model.new_uid(), rot=0.0, scale=1.6, anim="alive", acts=chain)
        if frame in char["frames"]:
            it["frame"] = frame
        items = []
        for k, oid in enumerate(d["objects"][:3]):
            if moving:
                ox = 0.72 + 0.1 * k
            else:
                ox = (0.8, 0.16, 0.66)[k]
            ob = cat.new_item("obj", oid, x=min(0.9, ox), y=0.05)
            ob.update(uid=model.new_uid(), rot=0.0)
            if oid in SMALL:
                ob["scale"] = 0.45
            items.append(ob)
        items.append(it)
        sc["items"] = items
        sc["focus"] = it["uid"]
        if d["effect"]:
            sc["effect"] = d["effect"]
        # оповідач
        for k, s in enumerate(d["sentences"]):
            if s["narr"]:
                sc["dialog"].append({"speaker": None, "text": s["narr"], "style": "say", "narr": True, "s": k,
                                     "hide": not captions})
        # атмосфера місця
        amb = "amb_night" if d["night"] and d["place"] in ("forest", "yard", "lake", "mountains") else \
            AMBIENCE.get(d["place"])
        if d["effect"] == "rain":
            amb = "amb_rain"
        if amb and (sounds is None or sounds.path(amb)):
            sc["ambience"] = {"sound": amb, "vol": 0.22}
        if any(a["a"] == "sleep" for a in chain):
            sc["camera"] = "zoom_in"
        scenes.append(sc)
        try:
            st = acts.state(it, sc, 999.0, 999.0, char, {"x": it["x"], "y": it["y"], "frame": it["frame"],
                                                          "flip": False, "rot": 0.0, "scale": 1.0, "sx": 1.0,
                                                          "sy": 1.0, "dx": 0.0, "dy": 0.0, "alpha": 1.0})
            x_end = max(0.1, min(0.9, st["x"]))
        except Exception:
            x_end = None
    name = hero_name(text)
    who = name or "Песик"
    whose = _genitive(name) if name else "песика"
    places = [d["place"] for d in descs]
    if len(set(places)) == 1:
        title = f"{who} {PLACE_TITLE.get(places[0], '')}".strip()
        if descs[0]["night"]:
            title = f"Нічна пригода {whose}"
    else:
        title = f"Пригоди {whose}"
    sub = {"winter": "Зимова історія", "autumn": "Осіння історія", "spring": "Весняна історія",
           "summer": "Літня історія"}[season]
    scenes.insert(0, model.new_title(title, sub, "sky" if season == "winter" else "sunset"))
    scenes.append(model.new_title("Кінець", "", "candy", ending=True))
    pr = model.new_project(scenes[1]["background"], f"{title[:28]} {time.strftime('%d.%m')}")
    pr["scenes"] = scenes
    pr["story"] = {"text": text, "captions": captions}
    if sounds is None or sounds.path("music_flower"):
        pr["music"] = {"builtin": "music_flower", "volume": 0.16}
    arrange(pr, cat)
    return pr


def _plan_end(item, char):
    return acts.total(item, char)


def arrange(pr, cat=None):
    """Розкласти в часі: кожне речення починається, коли закінчилось попереднє (і його прочитали),
    а песик говорить лише після оповідача. Викликати знову після озвучення (тривалості змінюються)."""
    for sc in pr["scenes"]:
        if model.is_title(sc):
            continue
        dog = next((it for it in sc.get("items", []) if it.get("kind") == "char" and it.get("acts")), None)
        narr = {ln.get("s"): ln for ln in sc.get("dialog", []) if ln.get("narr")}
        if dog is None:
            continue
        char = (cat.characters.get(dog["id"]) if cat is not None else None) or acts.CHARS.get(dog["id"])
        src = [a for a in dog["acts"] if not a.get("pad")]
        groups = {}
        for a in src:
            groups.setdefault(a.get("s", 0), []).append(a)
        n = max([*groups.keys(), *[k for k in narr if k is not None], 0]) + 1
        chain = []
        probe = dict(dog, acts=chain)
        prev_narr_end = 0.0
        for k in range(n):
            probe["acts"] = chain
            acts_end = _plan_end(probe, char) if chain else model.MOVE_MARGIN
            start = max(acts_end, prev_narr_end + model.LINE_GAP) if k else model.FIRST_LINE_AT
            ln = narr.get(k)
            narr_end = start
            if ln is not None:
                ln["at"] = round(start, 2)
                narr_end = start + model.line_duration(ln)
            voiced = ln is not None and (ln.get("voice") or not ln.get("hide"))
            pad = start - acts_end
            if pad > 0.3:
                chain.append({"a": "wait", "dur": round(pad, 2), "pad": True, "s": k})
            for a in groups.get(k, []):
                if a["a"] in ("talk", "bark") and voiced:
                    probe["acts"] = chain
                    cur = _plan_end(probe, char)
                    gap = narr_end + 0.15 - cur
                    if gap > 0.3:
                        chain.append({"a": "wait", "dur": round(gap, 2), "pad": True, "s": k})
                chain.append(a)
            probe["acts"] = chain
            prev_narr_end = narr_end
        dog["acts"] = chain
        # звуки дій
        sfx = [fx for fx in sc.get("sfx", []) if not fx.get("auto")]
        segs, _end = acts.plan(dog, char)
        for t0, t1, key, kind, _a in segs:
            if kind != "act":
                continue
            if key == "jump":
                sfx.append({"sound": "jump", "at": round(t0 + 0.15, 2), "vol": 0.55, "auto": True})
            elif key == "roll":
                sfx.append({"sound": "fall_soft", "at": round((t0 + t1) / 2, 2), "vol": 0.5, "auto": True})
        sc["sfx"] = sfx
    return pr


# ---------------------------------------------------------------------- «Придумай сам»
_HEROES = ["Песик", "Песик Бім", "Цуценя Рекс", "Маленький песик", "Песик Тузик", "Песик Бублик"]
_PLACES = {"forest": "у лісі", "playground": "у парку", "yard": "у дворі", "lake": "біля озера",
           "mountains": "у горах", "room": "у кімнаті"}
_SEASONS = {"winter": "Взимку", "autumn": "Восени", "spring": "Навесні", "summer": "Влітку"}
_FINDS = {"winter": ["сніговика", "санчата", "ялинку"], "autumn": ["гриби", "гарбуз", "купу листя"],
          "spring": ["квіти", "м'ячик", "повітряного змія"], "summer": ["м'ячик", "кавун", "скриньку зі скарбом"]}
_START = ["гуляє", "біжить", "прокидається й потягується", "нюхає слід", "крокує"]
_REACT = ["дивується і каже: «Ого, що це?»", "радіє і гавкає: «Гав! Як цікаво!»",
          "лякається, а потім сміється", "обережно нюхає і виляє хвостиком"]
_MIDDLE = ["стрибає, крутиться й танцює", "біжить колом і качається", "грається, стрибає і гавкає: «Ура!»",
           "сідає і дає лапу", "швидко біжить вправо, а потім стрибає двічі"]
_END = ["Увечері він біжить додому, лягає і засинає.", "Потім він сідає і каже: «Який чудовий день!»",
        "Наприкінці песик танцює і гавкає: «Гав-гав!»",
        "Він повертається додому, позіхає і каже: «На добраніч!»"]


def invent(rng=None):
    """Випадкова коротка історія (щоб було з чого почати)."""
    rng = rng or random.Random()
    season = rng.choice(list(_SEASONS))
    place = rng.choice(list(_PLACES))
    if place == "room":
        place = rng.choice(["forest", "playground", "yard"])
    hero = rng.choice(_HEROES)
    s1 = f"{_SEASONS[season]} {hero[0].lower() + hero[1:]} {rng.choice(_START)} {_PLACES[place]}."
    find = rng.choice(_FINDS[season])
    s2 = f"Раптом він бачить {find} і {rng.choice(_REACT)}."
    s3 = f"Песик {rng.choice(_MIDDLE)}."
    s4 = rng.choice(_END)
    return " ".join([s1, s2, s3, s4])


EXAMPLES = [
    "Песик спить у кімнаті. Він прокидається, потягується і гавкає: «Доброго ранку!»",
    "Песик гуляє в лісі восени. Він нюхає слід, бачить гриби й радіє.",
    "Взимку песик біжить по снігу, стрибає й качається. Потім струшується і каже: «Як весело!»",
    "У парку песик Бім бачить м'ячик. Він швидко біжить за ним, стрибає двічі і гавкає: «Гав! Піймав!»",
    "Уночі у дворі песик злякався. Потім він побачив зірки, ліг і заснув.",
    "Песик Рекс гуляє біля озера. Він бачить човен, дивується і каже: «Ого, кораблик!» "
    "Потім біжить додому, лягає й засинає.",
]


def finalize(pr):
    """Прибрати оповідь, яку не показують і не озвучили (інакше вона лише забирала б час)."""
    for sc in pr["scenes"]:
        sc["dialog"] = [ln for ln in sc.get("dialog", [])
                        if not (ln.get("narr") and ln.get("hide") and not ln.get("voice"))]
    return pr
