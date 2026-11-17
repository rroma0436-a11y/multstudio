"""Готові сюжети: мультик на 3–4 сцени одним натиском. Героїв потім можна замінити («⇄ Замінити»)."""
import time

import model

TEMPLATES = [
    ("birthday", "День народження", "Друзі вітають іменинницю, торт і танці з конфеті", "candy"),
    ("forest", "Прогулянка в лісі", "Дівчинка йде лісом і знаходить нового друга", "mint"),
    ("bear", "Казка про ведмедика", "Ведмедик прокидається, а білочка пригощає його ягодами", "sun"),
    ("space", "Пригода в космосі", "Ракета летить до Місяця, де живе робот Біп", "night"),
    ("winter", "Зимова казка", "Діти ліплять сніговика й катаються на санчатах", "sky"),
]


class _B:
    """Помічник для складання сцен."""

    def __init__(self, cat):
        self.cat = cat

    def it(self, kind, oid, x, y=0.07, **kw):
        it = self.cat.new_item(kind, oid, x=x, y=y)
        it.update(uid=model.new_uid(), rot=0.0)
        if kind == "char":
            it["anim"] = "alive"
        scale = kw.pop("scale", None)
        if scale:
            it["scale"] = scale
        it.update(kw)
        return it

    def scene(self, bg, items, lines=(), **kw):
        sc = model.new_scene(bg)
        sc["items"] = items
        sc["dialog"] = [{"speaker": who["uid"] if who else None, "text": text, "style": style, "voice": None}
                        for who, text, style in lines]
        sc.update(kw)
        return sc


def build(cat, key, sounds=None):
    """Новий проєкт за шаблоном. sounds — бібліотека звуків (щоб брати лише наявні)."""
    b = _B(cat)

    def snd(sid):
        return sid if sounds is None or sounds.path(sid) else None

    def sfx(sid, at, vol=1.0):
        s = snd(sid)
        return [{"sound": s, "at": at, "vol": vol}] if s else []

    def amb(sid, vol=0.45):
        s = snd(sid)
        return {"sound": s, "vol": vol} if s else None

    title = dict((k, n) for k, n, *_ in TEMPLATES)[key]
    color = dict((k, c) for k, _, _, c in TEMPLATES)[key]
    scenes = [model.new_title(title, "", color)]
    music = None

    if key == "birthday":
        girl = b.it("char", "girl_festive", 0.32, anim="alive")
        boy = b.it("char", "boy_festive", 0.68, flip=True, in_fx="fly_right", in_at=0.3)
        cake = b.it("obj", "cake", 0.5, 0.05, scale=0.8)
        teddy = b.it("obj", "teddy_bear", 0.12, 0.05)
        scenes.append(b.scene("room_summer", [teddy, cake, girl, boy],
                              [(boy, "З днем народження!", "shout"), (girl, "Дякую! Який гарний торт!", "say")],
                              camera="talk", effect="sparkles", sfx=sfx("applause", 1.0, 0.8)))
        g2 = dict(girl, uid=model.new_uid(), anim="dance", in_fx="none")
        b2 = dict(boy, uid=model.new_uid(), anim="dance", in_fx="none")
        scenes.append(b.scene("room_summer", [dict(teddy, uid=model.new_uid()), dict(cake, uid=model.new_uid()),
                                              g2, b2],
                              [(None, "І почалося веселе свято!", "say")], effect="confetti", filter="vivid",
                              transition="flash", duration=5.0, sfx=sfx("kids_laugh", 0.6)))
        music = snd("music_adventure")
        scenes.append(model.new_title("Кінець", "Свято вдалося!", "candy", ending=True))
    elif key == "forest":
        girl = b.it("char", "girl", 0.12, end={"x": 0.42, "y": 0.07, "scale": 1.0})
        scenes.append(b.scene("forest_summer", [b.it("obj", "mushrooms", 0.8, 0.04), girl],
                              [(girl, "Як гарно в лісі!", "say")], duration=5.0, ambience=amb("amb_forest")))
        g2 = b.it("char", "girl", 0.3, anim="surprised")
        hare = b.it("char", "hare", 0.72, flip=True, in_fx="pop", in_at=0.6, anim="hop")
        scenes.append(b.scene("forest_summer", [b.it("obj", "stump", 0.55, 0.04), g2, hare],
                              [(hare, "Привіт! Ходімо гратися!", "say"), (g2, "Ура! Ходімо!", "shout")],
                              camera="talk", transition="slide_left", ambience=amb("amb_forest")))
        g3 = b.it("char", "girl", 0.35, anim="jump")
        h3 = b.it("char", "hare", 0.62, anim="jump", flip=True)
        scenes.append(b.scene("forest_sunset", [g3, h3], [(None, "Вони гралися аж до вечора.", "say")],
                              effect="fireflies", filter="warm", transition="dissolve", duration=5.0))
        music = snd("music_flower")
        scenes.append(model.new_title("Кінець", "", "mint", ending=True))
    elif key == "bear":
        bear = b.it("char", "bear", 0.45, anim="sleep", scale=0.9)
        scenes.append(b.scene("forest_spring", [bear], [(None, "Жив-був у лісі ведмедик…", "say")],
                              effect="petals", camera="zoom_in", duration=4.5, ambience=amb("amb_birds")))
        bear2 = b.it("char", "bear", 0.3, anim="alive", scale=0.9)
        sq = b.it("char", "squirrel", 0.75, flip=True, in_fx="drop", in_at=0.4)
        basket = b.it("obj", "berry_basket", 0.6, 0.05, in_fx="magic", in_at=1.5, scale=0.7)
        scenes.append(b.scene("forest_spring", [bear2, basket, sq],
                              [(sq, "Ведмедику, пригощайся ягідками!", "say"), (bear2, "Ой, дякую! Смачно!", "say")],
                              camera="talk", transition="wipe", sfx=sfx("bear_growl", 0.2, 0.7)))
        b3 = b.it("char", "bear", 0.38, anim="dance", scale=0.9)
        s3 = b.it("char", "squirrel", 0.66, anim="dance")
        scenes.append(b.scene("forest_sunset", [b3, s3], [(None, "І стали вони найкращими друзями.", "say")],
                              effect="hearts", transition="dissolve", duration=5.0))
        music = snd("music_flower")
        scenes.append(model.new_title("Кінець", "", "sun", ending=True))
    elif key == "space":
        rocket = b.it("obj", "rocket", 0.1, 0.1, path="arc", scale=0.45, rot=-35.0,
                      end={"x": 0.88, "y": 0.42, "scale": 0.25})
        scenes.append(b.scene("space_planets", [rocket], [(None, "Ракета летить до далеких планет!", "say")],
                              effect="stars", duration=5.0, sfx=sfx("rocket", 0.2), ambience=amb("amb_space")))
        hero = b.it("char", "future_hero", 0.3, in_fx="drop", in_at=0.2)
        bot = b.it("char", "helper_bot", 0.72, flip=True, in_fx="magic", in_at=1.2, anim="wave")
        scenes.append(b.scene("space_moon", [hero, bot],
                              [(hero, "Ого! Робот на Місяці!", "shout"), (bot, "Біп-буп! Привіт, друже!", "say")],
                              camera="talk", transition="circle", sfx=sfx("robot_beep", 1.4),
                              ambience=amb("amb_space")))
        h3 = b.it("char", "future_hero", 0.35, anim="jump")
        r3 = b.it("char", "helper_bot", 0.65, anim="spin", flip=True)
        scenes.append(b.scene("space_stars", [h3, r3], [(None, "На Місяці можна стрибати дуже високо!", "say")],
                              effect="sparkles", transition="zoom", duration=5.0))
        music = snd("music_adventure")
        scenes.append(model.new_title("Кінець", "", "night", ending=True))
    elif key == "winter":
        boy = b.it("char", "boy", 0.25)
        girl = b.it("char", "girl", 0.75, flip=True)
        snowman = b.it("obj", "snowman", 0.5, 0.05, in_fx="grow", in_at=1.0)
        scenes.append(b.scene("yard_winter", [snowman, boy, girl],
                              [(boy, "Зліпімо сніговика!", "shout"), (girl, "Ой, який він гарний!", "say")],
                              effect="snow", camera="talk", ambience=amb("amb_birds", 0.25)))
        sled = b.it("obj", "sled", 0.15, 0.05, end={"x": 0.85, "y": 0.05, "scale": 0.8}, path="hops", scale=0.8)
        b2 = b.it("char", "boy", 0.15, 0.08, end={"x": 0.85, "y": 0.08, "scale": 1.0}, path="hops")
        scenes.append(b.scene("yard_winter", [sled, b2], [(b2, "Ура-а! З гірки!", "shout")],
                              effect="snow", transition="slide_left", duration=4.5, sfx=sfx("kids_laugh", 1.0)))
        g3 = b.it("char", "girl", 0.4, anim="laugh")
        b3 = b.it("char", "boy", 0.6, anim="laugh", flip=True)
        scenes.append(b.scene("yard_winter_night", [b.it("obj", "christmas_tree", 0.15, 0.05), g3, b3],
                              [(None, "Найкраща зима!", "say")], effect="stars", filter="warm",
                              transition="dissolve", duration=5.0))
        music = snd("music_flower")
        scenes.append(model.new_title("Кінець", "", "sky", ending=True))

    pr = model.new_project(scenes[1].get("background"), f"{title} {time.strftime('%d.%m')}")
    pr["scenes"] = scenes
    if music:
        pr["music"] = {"builtin": music, "volume": 0.3}
    return pr
