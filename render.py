"""Малювання одного кадру мультика в Fbo: фон, герої (з рухом, ходьбою, розмовою),
камера, хмаринки реплік, затемнення. Використовується і для перегляду, і для MP4."""
from kivy.core.text import Label as CoreLabel
from kivy.graphics import (ClearBuffers, ClearColor, Color, Ellipse, Fbo, Line, PopMatrix,
                           PushMatrix, Rectangle, Rotate, RoundedRectangle, Scale, Translate,
                           Triangle)

import imgload
import model


def flipped_coords(tc):
    u0, v0, u1, v1, u2, v2, u3, v3 = tc
    return (u1, v1, u0, v0, u3, v3, u2, v2)


BUBBLE_COLORS = {
    "say": ((1, 1, 1, 1), (0.15, 0.12, 0.25, 1)),
    "think": ((0.92, 0.95, 1, 1), (0.3, 0.35, 0.55, 1)),
    "shout": ((1, 0.9, 0.35, 1), (0.6, 0.2, 0.1, 1)),
}


class FrameRenderer:
    def __init__(self, catalog, size=(1280, 720)):
        self.cat = catalog
        self.W, self.H = size
        self.fbo = Fbo(size=size)
        self._labels = {}

    @property
    def texture(self):
        return self.fbo.texture

    # ------------------------------------------------------------ текст
    def _text_texture(self, text, style, max_w, font_size, color=(0.12, 0.1, 0.16, 1)):
        key = (text, style, int(max_w), int(font_size), color)
        tex = self._labels.get(key)
        if tex is None:
            lb = CoreLabel(text=text, font_size=font_size, bold=(style == "shout"),
                           text_size=(max_w, None), halign="center", valign="middle", color=color)
            lb.refresh()
            tex = lb.texture
            if len(self._labels) > 60:
                self._labels.clear()
            self._labels[key] = tex
        return tex

    # ------------------------------------------------------------ кадр
    def render(self, project, t):
        loc = model.locate(project, t)
        if loc is None:
            return
        i, lt, length = loc
        self.render_scene(project, i, lt, length)

    def render_scene(self, project, index, lt, length=None):
        sc = project["scenes"][index]
        L, spans = model.scene_timing(sc)
        length = length or L
        W, H = self.W, self.H
        cat = self.cat
        items = sc["items"]
        states = []
        for it in items:
            char = cat.characters.get(it["id"]) if it["kind"] == "char" else None
            states.append(model.item_state(it, sc, lt, length, char, spans))
        zoom, ox, oy = model.camera(sc, lt, length)

        fbo = self.fbo
        fbo.clear()
        with fbo:
            ClearColor(0, 0, 0, 1)
            ClearBuffers()
            PushMatrix()
            Translate(W / 2.0 + ox * W, H / 2.0 + oy * H)
            Scale(zoom, zoom, 1)
            Translate(-W / 2.0, -H / 2.0)
            Color(1, 1, 1, 1)
            bg = cat.backgrounds.get(sc.get("background")) or cat.backgrounds[cat.default_background()]
            Rectangle(texture=imgload.texture(cat.abspath(bg["path"])), pos=(0, 0), size=(W, H))
            heads = {}
            for k in model.draw_order(sc, states):
                it, st = items[k], states[k]
                tmp = dict(it, frame=st["frame"], scale=st["scale"])
                try:
                    tex = imgload.texture(cat.item_path(tmp))
                except Exception:
                    continue
                h = cat.base_height(tmp) * st["scale"] * H
                dw, dh = cat.item_dims(tmp)
                w = h * dw / float(dh)
                cx, by = st["x"] * W, st["y"] * H
                tc = tuple(tex.tex_coords)
                if st["flip"]:
                    tc = flipped_coords(tc)
                Color(1, 1, 1, 1)
                if st["rot"]:
                    PushMatrix()
                    Rotate(angle=st["rot"], origin=(cx, by + h / 2.0))
                    Rectangle(texture=tex, tex_coords=tc, pos=(cx - w / 2.0, by), size=(w, h))
                    PopMatrix()
                else:
                    Rectangle(texture=tex, tex_coords=tc, pos=(cx - w / 2.0, by), size=(w, h))
                # точка над головою (для хмаринки), з урахуванням камери
                hx = W / 2.0 + ox * W + (cx - W / 2.0) * zoom
                hy = H / 2.0 + oy * H + (by + h * 0.96 - H / 2.0) * zoom
                heads[it.get("uid")] = (hx, hy, w * zoom)
            PopMatrix()
            for ln, prog in model.active_lines(sc, lt, spans):
                self._bubble(ln, prog, heads.get(ln.get("speaker")))
            a = model.fade_alpha(project, index, lt, length)
            if a > 0:
                Color(0, 0, 0, a)
                Rectangle(pos=(0, 0), size=(W, H))
        fbo.draw()

    # ------------------------------------------------------------ хмаринка
    def _bubble(self, line, prog, head):
        text = (line.get("text") or "").strip()
        if not text:
            return
        W, H = self.W, self.H
        style = line.get("style", "say")
        alpha = min(1.0, prog / 0.06) if prog < 0.06 else 1.0
        if head is None:
            # оповідач — підпис унизу кадру
            tex = self._text_texture(text, "say", W * 0.8, H * 0.045, color=(1, 1, 1, 1))
            bw, bh = tex.width + H * 0.06, tex.height + H * 0.04
            x, y = (W - bw) / 2.0, H * 0.04
            Color(0, 0, 0, 0.62 * alpha)
            RoundedRectangle(pos=(x, y), size=(bw, bh), radius=[H * 0.02])
            Color(1, 1, 1, alpha)
            Rectangle(texture=tex, pos=(x + (bw - tex.width) / 2.0, y + (bh - tex.height) / 2.0),
                      size=tex.size)
            return
        fill, edge = BUBBLE_COLORS.get(style, BUBBLE_COLORS["say"])
        tex = self._text_texture(text, style, W * 0.32, H * 0.042)
        pad_x, pad_y = H * 0.035, H * 0.025
        bw, bh = tex.width + 2 * pad_x, tex.height + 2 * pad_y
        hx, hy, _ = head
        m = H * 0.02
        gap = H * 0.07
        bx = min(max(m, hx - bw / 2.0), W - bw - m)
        by = hy + gap
        if by + bh > H - m:
            by = H - m - bh
        r = [min(bh / 2.0, H * 0.04)]
        bw2 = H * (0.006 if style != "shout" else 0.01)
        # обвідка
        Color(edge[0], edge[1], edge[2], alpha)
        RoundedRectangle(pos=(bx - bw2, by - bw2), size=(bw + 2 * bw2, bh + 2 * bw2), radius=r)
        tx = min(max(bx + r[0], hx), bx + bw - r[0])
        tip_y = max(hy + H * 0.01, by - gap * 0.85)
        if style == "think":
            Color(edge[0], edge[1], edge[2], alpha)
            for k, s in ((0.35, 0.03), (0.7, 0.018)):
                cx = tx + (hx - tx) * k
                cy = by + (tip_y - by) * k
                d = H * s
                Ellipse(pos=(cx - d / 2 - bw2, cy - d / 2 - bw2), size=(d + 2 * bw2, d + 2 * bw2))
                Color(fill[0], fill[1], fill[2], alpha)
                Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d))
                Color(edge[0], edge[1], edge[2], alpha)
        else:
            half = H * 0.025
            Triangle(points=[tx - half - bw2, by + 1, tx + half + bw2, by + 1, hx, tip_y - bw2 * 1.5])
            Color(fill[0], fill[1], fill[2], alpha)
            Triangle(points=[tx - half, by + 2, tx + half, by + 2, hx, tip_y])
        Color(fill[0], fill[1], fill[2], alpha)
        RoundedRectangle(pos=(bx, by), size=(bw, bh), radius=r)
        Color(1, 1, 1, alpha)
        Rectangle(texture=tex, pos=(bx + pad_x, by + pad_y), size=tex.size)

    # ------------------------------------------------------------ знімки
    def save_png(self, path):
        self.fbo.texture.save(path)

    def pixels(self):
        """RGBA-байти кадру (рядки знизу вгору)."""
        return self.fbo.pixels
