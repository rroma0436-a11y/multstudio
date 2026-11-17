"""Готові сюжети: мультик на 3–4 сцени одним натиском. Героїв потім можна замінити («⇄ Замінити»).

Звуки в сюжетах — лише ті, що пасують до подій (без чужих голосів і слів)."""
import time

import model

# (ключ, назва, опис, колір титру, значок)
TEMPLATES = [
    ("dragon_flight", "Політ на драконі", "Дівчинка сідає на дракона, і вони летять над горами", "sky", "▲"),
    ("baby_dragon", "Прогулянка з дракончиком", "Хлопчик і маленький дракончик гуляють лісом і біля озера",
     "mint", "♣"),
    ("puppy", "Навчання песика", "Хлопчик вчить цуценя сидіти, давати лапу й стрибати", "sun", "●"),
    ("kitten", "Гра з котиком", "Кошеня ганяється за м'ячиком, а потім солодко спить", "candy", "♥"),
    ("birthday", "День народження", "Друзі вітають іменинницю, торт і танці з конфеті", "candy", "★"),
    ("forest", "Прогулянка в лісі", "Дівчинка йде лісом і знаходить нового друга — зайчика", "mint", "♠"),
    ("bear", "Казка про ведмедика", "Ведмедик прокидається, а білочка пригощає його ягодами", "sun", "☼"),
    ("hedgehog", "Їжачок і осінь", "Їжачок збирає гриби, а лисичка допомагає", "sunset", "✿"),
    ("space", "Пригода в космосі", "Ракета летить до Місяця, де живе робот Біп", "night", "✦"),
    ("superhero", "Супергерой рятує котика", "Котик застряг на дереві — на допомогу летить супергерой",
     "sky", "⚑"),
    ("farm", "Ранок на фермі", "Півень будить ферму, коник і песик вітаються", "sun", "♨"),
    ("school", "Перший день у школі", "Дзвоник, клас і нові друзі", "mint", "✎"),
    ("winter", "Зимова казка", "Діти ліплять сніговика й катаються на санчатах", "sky", "❄"),
    ("new_year", "Новорічне диво", "Ялинка засяяла, а дідусь приніс подарунки", "night", "❆"),
    ("robot_home", "Робот-помічник", "Робот Біп допомагає прибрати кімнату, а дрон йому світить", "candy", "⚙"),
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
        if it.get("end") and it["end"].get("scale", 1.0) == 1.0:
            it["end"] = dict(it["end"], scale=it.get("scale", 1.0))     # «1.0» у шаблоні = той самий розмір
        return it

    def copy(self, it, **kw):
        new = dict(it, uid=model.new_uid())
        for k in ("in_fx", "in_at", "out_fx", "out_at", "end"):
            new.pop(k, None)
        new.update(kw)
        return new

    def rider(self, mount, oid, frame="sit", share=0.42, back=(0.44, 0.55)):
        """Вершник на спині (дракона, коня): рухається разом із ним."""
        cat = self.cat
        hm = cat.base_height(mount) * mount.get("scale", 1.0)
        dw, dh = cat.item_dims(mount)
        wm = hm * dw / float(dh) * 9 / 16.0
        r = self.it("char", oid, 0.5, frame=frame, ride=True, anim="none")
        hr = cat.base_height(r)
        r["scale"] = hm * share / max(0.01, hr)
        bx = (back[0] - 0.5) * wm
        if mount.get("flip"):
            bx = -bx
            r["flip"] = True
        r["x"] = mount["x"] + bx
        r["y"] = mount["y"] + hm * back[1]
        if mount.get("end"):
            e = mount["end"]
            r["end"] = {"x": e["x"] + bx, "y": e["y"] + hm * back[1], "scale": r["scale"]}
        r["path"] = mount.get("path", "line")
        return r

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

    def sfx(*pairs):
        out = []
        for sid, at in pairs:
            if snd(sid):
                out.append({"sound": sid, "at": at, "vol": 1.0})
        return out

    def amb(sid, vol=0.4):
        return {"sound": sid, "vol": vol} if snd(sid) else None

    meta = {k: (n, c) for k, n, _d, c, _i in TEMPLATES}
    title, color = meta[key]
    S = []
    music = "music_flower"
    end_sub = ""

    if key == "dragon_flight":
        girl = b.it("char", "girl", 0.25, anim="surprised")
        dragon = b.it("char", "pastel_dragon", 0.65, 0.05, scale=0.55, flip=True, in_fx="drop", in_at=0.5,
                      anim="alive")
        S.append(b.scene("mountains_summer", [dragon, girl],
                         [(girl, "Ого! Справжній дракон!", "shout"), (dragon, "Сідай, полетимо!", "say")],
                         camera="talk", sfx=sfx(("thud", 0.9)), ambience=amb("amb_river", 0.3)))
        d2 = b.copy(dragon, x=0.15, y=0.2, frame="flying_calm", flip=False, anim="none", path="wave", ride=True,
                    end={"x": 0.85, "y": 0.45, "scale": 0.55})
        S.append(b.scene("mountains_sunset", [d2, b.rider(d2, "girl")],
                         [(None, "І вони полетіли над горами!", "say")], auto_depth=False, effect="sparkles",
                         transition="slide_left", duration=6.0, sfx=sfx(("powerup", 0.3))))
        d3 = b.copy(dragon, x=0.85, y=0.5, frame="flying_calm", flip=True, anim="none", path="arc", ride=True,
                    end={"x": 0.3, "y": 0.05, "scale": 0.55})
        castle = b.it("obj", "castle", 0.78, 0.05, scale=0.8)
        S.append(b.scene("mountains_spring", [castle, d3, b.rider(d3, "girl")],
                         [(None, "А потім приземлилися біля чарівного замку.", "say")], auto_depth=False,
                         transition="dissolve", duration=5.5, effect="petals", sfx=sfx(("magic_bells", 4.6))))
        music = "music_adventure"
        end_sub = "Політ був чудовий!"
    elif key == "baby_dragon":
        boy = b.it("char", "boy", 0.12, end={"x": 0.4, "y": 0.07, "scale": 1.0})
        dr = b.it("char", "baby_dragon", 0.02, end={"x": 0.62, "y": 0.06, "scale": 1.0}, path="hops")
        S.append(b.scene("forest_spring", [boy, dr],
                         [(boy, "Ходімо гуляти, дракончику!", "say")], duration=5.0, ambience=amb("amb_birds")))
        boy2 = b.it("char", "boy", 0.3, anim="laugh")
        dr2 = b.it("char", "baby_dragon", 0.66, flip=True, anim="wave", frame="flying_calm", y=0.25)
        S.append(b.scene("lake_summer", [boy2, dr2],
                         [(dr2, "Дивись, я вмію літати!", "shout"), (boy2, "Ура! Як високо!", "shout")],
                         camera="talk", transition="wipe", effect="bubbles", ambience=amb("amb_river", 0.35)))
        boy3 = b.it("char", "boy", 0.38, frame="sit", anim="alive")
        dr3 = b.it("char", "baby_dragon", 0.62, flip=True, anim="sleep")
        S.append(b.scene("lake_sunset", [boy3, dr3], [(None, "Увечері дракончик солодко заснув.", "say")],
                         effect="fireflies", filter="warm", transition="dissolve", duration=5.5,
                         ambience=amb("amb_night", 0.3)))
        end_sub = "Найкращий друг — дракончик"
    elif key == "puppy":
        boy = b.it("char", "boy", 0.32)
        pup = b.it("char", "puppy", 0.66, flip=True, anim="hop", scale=1.4)
        S.append(b.scene("yard_summer", [boy, pup],
                         [(boy, "Цуцику, сидіти!", "shout")], camera="talk", duration=4.5,
                         sfx=sfx(("puppy_bark", 0.4)), ambience=amb("amb_birds", 0.25)))
        pup2 = b.it("char", "puppy", 0.62, flip=True, frame="sit", anim="alive", scale=1.4)
        boy2 = b.it("char", "boy", 0.32, anim="laugh")
        S.append(b.scene("yard_summer", [boy2, pup2],
                         [(boy2, "Молодець! А тепер дай лапу!", "say"), (pup2, "Гав!", "shout")],
                         camera="talk", transition="dissolve", effect="sparkles",
                         sfx=sfx(("puppy_bark", 2.6), ("sparkle", 3.4))))
        ball = b.it("obj", "football", 0.2, 0.05, scale=0.7, path="arc", end={"x": 0.85, "y": 0.05, "scale": 0.7})
        pup3 = b.it("char", "puppy", 0.1, end={"x": 0.75, "y": 0.07, "scale": 1.0}, path="hops", scale=1.4)
        boy3 = b.it("char", "boy", 0.45, anim="jump")
        S.append(b.scene("playground_summer", [boy3, ball, pup3], [(None, "Песик навчився всього!", "say")],
                         effect="confetti", transition="slide_left", duration=5.0,
                         sfx=sfx(("small_dog", 1.5), ("applause", 3.0))))
        end_sub = "Розумне цуценя!"
    elif key == "kitten":
        girl = b.it("char", "girl", 0.75, flip=True)
        ball = b.it("obj", "football", 0.15, 0.04, scale=0.4, end={"x": 0.6, "y": 0.04, "scale": 0.4}, path="hops")
        kit = b.it("char", "kitten", 0.02, end={"x": 0.45, "y": 0.06, "scale": 1.0}, scale=1.7)
        S.append(b.scene("room_summer", [girl, ball, kit],
                         [(girl, "Лови м'ячик, котику!", "say")], duration=5.0, sfx=sfx(("kitten_mew", 0.6))))
        kit2 = b.it("char", "kitten", 0.45, anim="jump", scale=1.7)
        girl2 = b.it("char", "girl", 0.72, flip=True, anim="laugh")
        S.append(b.scene("room_summer", [kit2, girl2], [(kit2, "Мяу! Ще! Ще!", "shout")],
                         camera="talk", transition="zoom", effect="hearts", sfx=sfx(("kitten_meow2", 0.8))))
        kit3 = b.it("char", "kitten", 0.5, 0.1, frame="lie", anim="sleep", scale=2.2)
        S.append(b.scene("room_night", [b.it("obj", "teddy_bear", 0.3, 0.06), kit3],
                         [(None, "Набігався котик і заснув.", "say")],
                         effect="stars", transition="dissolve", duration=5.0, camera="zoom_in"))
        end_sub = "Солодких снів, котику!"
    elif key == "birthday":
        girl = b.it("char", "girl_festive", 0.32)
        boy = b.it("char", "boy_festive", 0.68, flip=True, in_fx="fly_right", in_at=0.3)
        cake = b.it("obj", "cake", 0.5, 0.05, scale=0.9)
        teddy = b.it("obj", "teddy_bear", 0.12, 0.05)
        S.append(b.scene("room_summer", [teddy, cake, girl, boy],
                         [(boy, "З днем народження!", "shout"), (girl, "Дякую! Який гарний торт!", "say")],
                         camera="talk", effect="sparkles", sfx=sfx(("magic_bells", 0.5))))
        S.append(b.scene("room_summer", [b.copy(teddy), b.copy(cake), b.copy(girl, anim="dance"),
                                         b.copy(boy, anim="dance")],
                         [(None, "І почалося веселе свято!", "say")], effect="confetti", filter="vivid",
                         transition="flash", duration=5.0, sfx=sfx(("applause", 0.4), ("kid_laugh", 2.5))))
        music = "music_adventure"
        end_sub = "Свято вдалося!"
    elif key == "forest":
        girl = b.it("char", "girl", 0.12, end={"x": 0.42, "y": 0.07, "scale": 1.0})
        S.append(b.scene("forest_summer", [b.it("obj", "mushrooms", 0.8, 0.04), girl],
                         [(girl, "Як гарно в лісі!", "say")], duration=5.0, ambience=amb("amb_forest")))
        g2 = b.it("char", "girl", 0.3, anim="surprised")
        hare = b.it("char", "hare", 0.72, flip=True, in_fx="pop", in_at=0.6, anim="hop", scale=1.4)
        S.append(b.scene("forest_summer", [b.it("obj", "stump", 0.55, 0.04), g2, hare],
                         [(hare, "Привіт! Ходімо гратися!", "say"), (g2, "Ура! Ходімо!", "shout")],
                         camera="talk", transition="slide_left", ambience=amb("amb_forest")))
        S.append(b.scene("forest_sunset", [b.it("char", "girl", 0.35, anim="jump"),
                                           b.it("char", "hare", 0.62, anim="jump", flip=True, scale=1.4)],
                         [(None, "Вони гралися аж до вечора.", "say")],
                         effect="fireflies", filter="warm", transition="dissolve", duration=5.0))
    elif key == "bear":
        bear = b.it("char", "bear", 0.45, anim="sleep", scale=0.9)
        S.append(b.scene("forest_spring", [bear], [(None, "Жив-був у лісі ведмедик…", "say")],
                         effect="petals", camera="zoom_in", duration=4.5, ambience=amb("amb_birds")))
        bear2 = b.it("char", "bear", 0.3, scale=0.9)
        sq = b.it("char", "squirrel", 0.75, flip=True, in_fx="drop", in_at=0.4, scale=1.5)
        basket = b.it("obj", "berry_basket", 0.6, 0.05, in_fx="magic", in_at=1.5, scale=0.7)
        S.append(b.scene("forest_spring", [bear2, basket, sq],
                         [(sq, "Ведмедику, пригощайся ягідками!", "say"), (bear2, "Ой, дякую! Смачно!", "say")],
                         camera="talk", transition="wipe", sfx=sfx(("bear_growl", 0.2))))
        S.append(b.scene("forest_sunset", [b.it("char", "bear", 0.38, anim="dance", scale=0.9),
                                           b.it("char", "squirrel", 0.66, anim="dance", scale=1.5)],
                         [(None, "І стали вони найкращими друзями.", "say")],
                         effect="hearts", transition="dissolve", duration=5.0))
    elif key == "hedgehog":
        hh = b.it("char", "hedgehog", 0.1, end={"x": 0.45, "y": 0.06, "scale": 1.0}, scale=2.0)
        S.append(b.scene("forest_autumn", [b.it("obj", "mushrooms", 0.55, 0.04), hh, b.it("obj", "leaf_pile", 0.85, 0.04)],
                         [(hh, "Скільки грибочків!", "say")], effect="leaves", duration=5.0,
                         ambience=amb("amb_forest", 0.3)))
        fox = b.it("char", "fox", 0.75, flip=True, in_fx="fly_right", in_at=0.3)
        hh2 = b.it("char", "hedgehog", 0.35, anim="surprised", scale=2.0)
        S.append(b.scene("forest_autumn", [hh2, fox],
                         [(fox, "Давай я допоможу нести!", "say"), (hh2, "Дякую, лисичко!", "say")],
                         camera="talk", effect="leaves", transition="slide_left"))
        S.append(b.scene("forest_sunset", [b.it("char", "hedgehog", 0.4, anim="hop", scale=2.0),
                                           b.it("char", "fox", 0.62, anim="laugh", flip=True),
                                           b.it("obj", "berry_basket", 0.52, 0.04, scale=0.6)],
                         [(None, "Удвох і робота веселіша!", "say")], effect="leaves", filter="warm",
                         transition="dissolve", duration=5.0))
    elif key == "space":
        rocket = b.it("obj", "rocket", 0.1, 0.1, path="arc", scale=0.45, rot=-35.0,
                      end={"x": 0.88, "y": 0.42, "scale": 0.25})
        S.append(b.scene("space_planets", [rocket], [(None, "Ракета летить до далеких планет!", "say")],
                         effect="stars", duration=5.0, sfx=sfx(("rocket", 0.2)), ambience=amb("amb_space")))
        hero = b.it("char", "future_hero", 0.3, in_fx="drop", in_at=0.2)
        bot = b.it("char", "helper_bot", 0.72, flip=True, in_fx="magic", in_at=1.2, anim="wave")
        S.append(b.scene("space_moon", [hero, bot],
                         [(hero, "Ого! Робот на Місяці!", "shout"), (bot, "Біп-буп! Привіт, друже!", "say")],
                         camera="talk", transition="circle", sfx=sfx(("robot_beep", 1.4)),
                         ambience=amb("amb_space")))
        S.append(b.scene("space_stars", [b.it("char", "future_hero", 0.35, anim="jump"),
                                         b.it("char", "helper_bot", 0.65, anim="spin", flip=True)],
                         [(None, "На Місяці можна стрибати дуже високо!", "say")],
                         effect="sparkles", transition="zoom", duration=5.0))
        music = "music_adventure"
    elif key == "superhero":
        cat_ = b.it("char", "pet_cat", 0.7, 0.42, frame="sit", anim="scared", scale=1.1)
        tree = b.it("obj", "oak_summer", 0.7, 0.04, scale=1.2)
        girl = b.it("char", "girl", 0.3, anim="cry")
        S.append(b.scene("street_summer", [tree, cat_, girl],
                         [(cat_, "Мяу! Я боюся злазити!", "say"), (girl, "Хто ж допоможе котику?", "say")],
                         auto_depth=False, camera="talk", sfx=sfx(("cat_meow", 0.3))))
        hero = b.it("char", "caped_hero", -0.2, 0.6, frame="flying_calm", anim="none", path="arc", ride=True,
                    end={"x": 0.55, "y": 0.4, "scale": 1.0})
        S.append(b.scene("street_summer", [b.copy(tree), b.copy(cat_), hero],
                         [(None, "На допомогу летить супергерой!", "say")], auto_depth=False,
                         transition="flash", duration=4.0, sfx=sfx(("powerup", 0.2))))
        hero3 = b.it("char", "caped_hero", 0.55, anim="wave")
        S.append(b.scene("street_summer", [b.copy(tree), hero3, b.it("char", "pet_cat", 0.38, frame="sit", scale=1.3),
                                           b.it("char", "girl", 0.2, anim="jump")],
                         [(hero3, "Котик врятований!", "shout")], auto_depth=False, effect="hearts",
                         transition="dissolve", duration=5.0, sfx=sfx(("applause", 1.0))))
        music = "music_adventure"
        end_sub = "Герої завжди поруч"
    elif key == "farm":
        rooster = b.it("char", "rooster", 0.6, anim="wave", scale=1.3)
        S.append(b.scene("yard_spring", [b.it("obj", "haystack", 0.2, 0.05), rooster],
                         [(rooster, "Ку-ку-рі-ку! Вставайте!", "shout")], camera="focus", focus=rooster["uid"],
                         sfx=sfx(("rooster", 0.5)), ambience=amb("amb_farm", 0.35)))
        horse = b.it("char", "horse", 0.0, end={"x": 0.35, "y": 0.06, "scale": 1.0}, scale=0.8)
        dog = b.it("char", "pet_dog", 0.75, flip=True, anim="hop", scale=1.2)
        S.append(b.scene("yard_spring", [horse, dog],
                         [(dog, "Доброго ранку, коню!", "say")], transition="slide_left", duration=5.0,
                         sfx=sfx(("horse", 1.8), ("dog_bark", 3.4)), ambience=amb("amb_farm", 0.35)))
        boy = b.it("char", "boy", 0.5, anim="wave")
        S.append(b.scene("yard_summer", [b.it("char", "horse", 0.2, scale=0.8), boy,
                                         b.it("char", "pet_dog", 0.75, flip=True, anim="dance", scale=1.2)],
                         [(boy, "Привіт усім! Гарного дня!", "say")], effect="sparkles", transition="dissolve",
                         duration=5.0, ambience=amb("amb_farm", 0.3)))
    elif key == "school":
        girl = b.it("char", "schoolgirl", 0.1, end={"x": 0.4, "y": 0.07, "scale": 1.0})
        S.append(b.scene("street_autumn", [girl], [(girl, "Сьогодні мій перший день у школі!", "say")],
                         effect="leaves", duration=5.0, ambience=amb("amb_street", 0.25)))
        teacher = b.it("char", "woman", 0.25)
        boy = b.it("char", "schoolboy", 0.72, flip=True, in_fx="pop", in_at=1.0)
        S.append(b.scene("classroom_autumn", [b.it("obj", "chalkboard", 0.5, 0.25, scale=0.9), teacher,
                                              b.it("char", "schoolgirl", 0.5), boy],
                         [(teacher, "Вітаю, діти! Почнемо урок.", "say"), (boy, "Привіт! Будемо дружити?", "say")],
                         camera="talk", transition="wipe", sfx=sfx(("school_bell", 0.1))))
        S.append(b.scene("playground_autumn", [b.it("char", "schoolgirl", 0.35, anim="jump"),
                                               b.it("char", "schoolboy", 0.65, anim="jump", flip=True)],
                         [(None, "У школі так цікаво!", "say")], effect="confetti", transition="dissolve",
                         duration=5.0))
    elif key == "winter":
        boy = b.it("char", "boy", 0.25)
        girl = b.it("char", "girl", 0.75, flip=True)
        snowman = b.it("obj", "snowman", 0.5, 0.05, in_fx="grow", in_at=1.0)
        S.append(b.scene("yard_winter", [snowman, boy, girl],
                         [(boy, "Зліпімо сніговика!", "shout"), (girl, "Ой, який він гарний!", "say")],
                         effect="snow", camera="talk"))
        sled = b.it("obj", "sled", 0.15, 0.05, end={"x": 0.85, "y": 0.05, "scale": 0.8}, path="hops", scale=0.8)
        b2 = b.it("char", "boy", 0.15, 0.08, end={"x": 0.85, "y": 0.08, "scale": 1.0}, path="hops")
        S.append(b.scene("yard_winter", [sled, b2], [(b2, "Ура-а! З гірки!", "shout")],
                         effect="snow", transition="slide_left", duration=4.5, sfx=sfx(("kid_laugh", 1.0))))
        S.append(b.scene("yard_winter_night", [b.it("obj", "christmas_tree", 0.15, 0.05),
                                               b.it("char", "girl", 0.4, anim="laugh"),
                                               b.it("char", "boy", 0.6, anim="laugh", flip=True)],
                         [(None, "Найкраща зима!", "say")], effect="stars", filter="warm",
                         transition="dissolve", duration=5.0))
    elif key == "new_year":
        tree = b.it("obj", "christmas_tree", 0.5, 0.05, scale=1.1)
        S.append(b.scene("room_winter", [tree], [(None, "Настала новорічна ніч…", "say")],
                         effect="snow", filter="cold", camera="zoom_in", duration=4.0))
        S.append(b.scene("room_winter", [b.copy(tree), b.it("char", "girl_festive", 0.25, anim="surprised"),
                                         b.it("char", "boy_festive", 0.78, anim="surprised", flip=True)],
                         [(None, "І раптом ялинка засяяла!", "say")], effect="sparkles", filter="warm",
                         transition="flash", sfx=sfx(("magic_bells", 0.3))))
        gp = b.it("char", "grandpa", 0.75, flip=True, in_fx="magic", in_at=0.3, anim="wave")
        S.append(b.scene("room_winter", [b.copy(tree, x=0.2), b.it("obj", "teddy_bear", 0.45, 0.05, in_fx="pop", in_at=2.0),
                                         b.it("char", "girl_festive", 0.32, anim="dance"), gp],
                         [(gp, "З Новим роком, онуки!", "shout")], effect="confetti", transition="dissolve",
                         duration=5.0, sfx=sfx(("pop", 2.0), ("applause", 3.0))))
        end_sub = "З Новим роком!"
    elif key == "robot_home":
        bot = b.it("char", "helper_bot", 0.1, end={"x": 0.5, "y": 0.07, "scale": 1.0})
        S.append(b.scene("room_summer", [b.it("obj", "blocks", 0.7, 0.04), bot],
                         [(bot, "Біп! Час прибирати!", "say")], duration=4.5, sfx=sfx(("robot_beep", 0.5))))
        drone = b.it("char", "home_drone", 0.8, 0.55, in_fx="fly_right", in_at=0.2, anim="hop", scale=2.5)
        bot2 = b.it("char", "helper_bot", 0.4, anim="dance")
        S.append(b.scene("room_summer", [bot2, drone], [(drone, "Я посвічу тобі!", "say")],
                         camera="talk", transition="wipe", effect="sparkles", sfx=sfx(("computer", 0.4))))
        S.append(b.scene("room_summer", [b.it("char", "helper_bot", 0.45, anim="wave"),
                                         b.it("char", "girl", 0.75, anim="laugh", flip=True)],
                         [(None, "Кімната сяє чистотою!", "say")], effect="stars", filter="vivid",
                         transition="dissolve", duration=4.5, sfx=sfx(("win", 0.3))))

    S.insert(0, model.new_title(title, "", color))
    S.append(model.new_title("Кінець", end_sub, color, ending=True))
    pr = model.new_project(S[1].get("background"), f"{title} {time.strftime('%d.%m')}")
    pr["scenes"] = S
    if snd(music):
        pr["music"] = {"builtin": music, "volume": 0.3}
    return pr
