"""Готові сюжети про песика: мультик на 3–4 сцени одним натиском (дії песика — ланцюжком).

Звуки — лише ті, що пасують до подій."""
import time

import acts
import model

HERO = "puppy"

# (ключ, назва, опис, колір титру, значок)
TEMPLATES = [
    ("morning", "Песик прокидається", "Песик спить, потягується, встає й радіє новому дню", "sun", "☼"),
    ("ball", "Песик і м'ячик", "М'ячик котиться — песик встає, біжить за ним і стрибає", "mint", "●"),
    ("walk", "Прогулянка в лісі", "Песик нюхає слід, дивується й біжить додому", "mint", "♣"),
    ("training", "Навчання песика", "Сидіти! Дай лапу! Крутись! — песик усе вміє", "sky", "★"),
    ("winter", "Песик і сніг", "Перший сніг: песик стрибає, струшується й грається", "sky", "❄"),
    ("birthday", "День народження песика", "Торт, конфеті й танці іменинника", "candy", "♥"),
    ("scared", "Хто там шумить?", "Уночі песик боїться шуму, а потім спокійно засинає", "night", "☾"),
]

# короткі назви для переліку (мультяшними літерами)
SHORT = {"morning": "Добрий ранок!", "ball": "М'ячик!", "walk": "У лісі", "training": "Навчання",
         "winter": "Сніжок!", "birthday": "Іменини!", "scared": "Хто там?"}


def _A(key, **kw):
    a = acts.new_act(key)
    a.update(kw)
    return a


class _B:
    def __init__(self, cat):
        self.cat = cat

    def dog(self, x, frame="side_calm", scale=1.6, flip=False, actions=(), **kw):
        it = self.cat.new_item("char", HERO, x=x, y=0.06)
        it.update(uid=model.new_uid(), rot=0.0, scale=scale, flip=flip, acts=list(actions))
        if frame in self.cat.characters[HERO]["frames"]:
            it["frame"] = frame
        it.update(kw)
        return it

    def obj(self, oid, x, y=0.05, **kw):
        it = self.cat.new_item("obj", oid, x=x, y=y)
        it.update(uid=model.new_uid(), rot=0.0)
        sc = kw.pop("scale", None)
        if sc:
            it["scale"] = sc
        it.update(kw)
        if it.get("end") and it["end"].get("scale", 1.0) == 1.0:
            it["end"] = dict(it["end"], scale=it.get("scale", 1.0))
        return it

    def scene(self, bg, items, lines=(), **kw):
        sc = model.new_scene(bg)
        sc["items"] = items
        sc["dialog"] = [{"speaker": None, "text": text, "style": "say", "voice": None} for text in lines]
        sc.update(kw)
        return sc


def build(cat, key, sounds=None):
    b = _B(cat)

    def snd(sid):
        return sid if sounds is None or sounds.path(sid) else None

    def sfx(*pairs):
        return [{"sound": s, "at": at, "vol": 1.0} for s, at in pairs if snd(s)]

    def amb(sid, vol=0.4):
        return {"sound": sid, "vol": vol} if snd(sid) else None

    meta = {k: (n, c) for k, n, _d, c, _i in TEMPLATES}
    title, color = meta[key]
    S = []
    music = "music_flower"
    end_sub = ""

    if key == "morning":
        S.append(b.scene("room_spring", [b.dog(0.35, "lie", actions=[_A("sleep", dur=3.0)])],
                         ["Ранок. Песик ще спить…"], camera="zoom_in", ambience=amb("amb_birds", 0.3)))
        S.append(b.scene("room_spring", [b.dog(0.3, "lie", actions=[
            _A("stand"), _A("shake"), _A("walk", dur=2.5, dir="right"),
            _A("bark", text="Гав! Доброго ранку!"), _A("happy")])],
            transition="dissolve", effect="sparkles"))
        end_sub = "Гарного дня!"
    elif key == "ball":
        ball = b.obj("football", 0.1, 0.04, scale=0.35, end={"x": 0.85, "y": 0.04, "scale": 1.0}, path="hops")
        S.append(b.scene("yard_summer", [b.dog(0.25, "sit", actions=[_A("surprised", dur=1.5), _A("look", dur=1.0)]),
                                         ball], ["Ой, що це котиться?"], ambience=amb("amb_birds", 0.3)))
        S.append(b.scene("yard_summer", [b.dog(0.15, "sit", actions=[
            _A("run", dur=2.0, dir="right"), _A("jump"), _A("bark", text="Гав! Піймав!"), _A("happy")]),
            b.obj("football", 0.82, 0.04, scale=0.35)], transition="slide_left",
            sfx=sfx(("puppy_bark", 4.6))))
        S.append(b.scene("playground_summer", [b.dog(0.5, actions=[_A("play"), _A("spin"), _A("dance")])],
                         ["Найкраща гра — з м'ячиком!"], effect="confetti", transition="dissolve"))
        music = "music_adventure"
    elif key == "walk":
        S.append(b.scene("forest_summer", [b.dog(0.05, actions=[_A("walk", dur=3.0, dir="right"),
                                                               _A("sniff", dur=2.5)])],
                         ["Песик пішов гуляти в ліс."], ambience=amb("amb_forest")))
        S.append(b.scene("forest_summer", [b.dog(0.35, actions=[_A("surprised"),
                                                               _A("talk", text="Ого, скільки грибів!"), _A("happy")]),
                                           b.obj("mushrooms", 0.7, 0.04)], transition="wipe",
                         ambience=amb("amb_forest")))
        S.append(b.scene("forest_sunset", [b.dog(0.9, flip=True, actions=[_A("run", dur=2.5, dir="left")])],
                         ["Уже вечір — бігом додому!"], filter="warm", effect="fireflies", transition="dissolve"))
        end_sub = "Гарна була прогулянка!"
    elif key == "training":
        S.append(b.scene("yard_summer", [b.dog(0.5, actions=[_A("sit"), _A("happy", dur=1.0)])],
                         ["— Сидіти!"], sfx=sfx(("sparkle", 1.8))))
        S.append(b.scene("yard_summer", [b.dog(0.5, "sit", actions=[_A("paw"), _A("bark", text="Гав!")])],
                         ["— Дай лапу!"], transition="dissolve"))
        S.append(b.scene("yard_summer", [b.dog(0.5, "sit", actions=[_A("spin"), _A("jump"), _A("happy")])],
                         ["— Крутись! Стрибай!"], effect="confetti", transition="flash",
                         sfx=sfx(("applause", 2.5))))
        end_sub = "Розумний песик!"
    elif key == "winter":
        S.append(b.scene("yard_winter", [b.dog(0.1, actions=[_A("walk", dur=2.0, dir="right"), _A("surprised"),
                                                            _A("jump"), _A("jump")])],
                         ["Перший сніг!"], effect="snow"))
        S.append(b.scene("yard_winter", [b.dog(0.5, actions=[_A("roll"), _A("stand"), _A("shake"), _A("play")]),
                                         b.obj("snowman", 0.82, 0.05, scale=0.8)], effect="snow",
                         transition="slide_left"))
        S.append(b.scene("yard_winter_night", [b.dog(0.4, actions=[_A("bark", text="Гав! Ще хочу гуляти!"),
                                                                  _A("happy")])],
                         effect="snow", filter="warm", transition="dissolve"))
    elif key == "birthday":
        S.append(b.scene("room_summer", [b.obj("cake", 0.62, 0.05, scale=0.9, in_fx="magic", in_at=0.8),
                                         b.dog(0.3, "sit", actions=[_A("surprised"), _A("bark", text="Це мені?!"),
                                                                     _A("happy")])],
                         effect="sparkles", sfx=sfx(("magic_bells", 0.8))))
        S.append(b.scene("room_summer", [b.obj("cake", 0.62, 0.05, scale=0.9),
                                         b.dog(0.3, actions=[_A("dance", dur=3.0), _A("spin"), _A("jump")])],
                         ["З днем народження, песику!"], effect="confetti", filter="vivid", transition="flash",
                         sfx=sfx(("applause", 0.5))))
        music = "music_adventure"
        end_sub = "Свято вдалося!"
    elif key == "scared":
        S.append(b.scene("yard_night", [b.dog(0.3, "lie", actions=[_A("sleep", dur=2.0), _A("stand"),
                                                                  _A("scared", dur=2.5)])],
                         ["Уночі щось зашуміло…"], effect="fireflies", ambience=amb("amb_night")))
        S.append(b.scene("yard_night", [b.dog(0.3, actions=[_A("surprised"), _A("talk", text="Ой, це лише вітер!"),
                                                           _A("happy"), _A("lie"), _A("sleep", dur=2.0)])],
                         transition="dissolve", effect="leaves", ambience=amb("amb_night", 0.3)))
        end_sub = "Солодких снів!"

    S.insert(0, model.new_title(title, "", color))
    S.append(model.new_title("Кінець", end_sub, color, ending=True))
    pr = model.new_project(S[1].get("background"), f"{title} {time.strftime('%d.%m')}")
    pr["scenes"] = S
    if snd(music):
        pr["music"] = {"builtin": music, "volume": 0.3}
    return pr
