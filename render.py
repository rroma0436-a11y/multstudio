"""Малювання кадру мультика: фон (з каталогу чи фото), герої з рухом, діями, появою й зникненням,
камера, частинки (сніг, сердечка …), фільтри кольору, переходи між сценами, хмаринки реплік.
Використовується для перегляду, мініатюр і MP4.

Порядок: сцена -> raw (Fbo) -> фільтр (Fbo із шейдером) -> підсумок (fbo) з переходом і хмаринками.
"""
import math
import os

from kivy.core.text import Label as CoreLabel
from kivy.graphics import (ClearBuffers, ClearColor, Color, Ellipse, Fbo, Mesh, PopMatrix, PushMatrix,
                           Rectangle, Rotate, RoundedRectangle, Scale, Translate, Triangle)
from kivy.logger import Logger

import fx
import imgload
import model

FX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fx")


def flipped_coords(tc):
    u0, v0, u1, v1, u2, v2, u3, v3 = tc
    return (u1, v1, u0, v0, u3, v3, u2, v2)


BUBBLE_COLORS = {
    "say": ((1, 1, 1, 1), (0.15, 0.12, 0.25, 1)),
    "think": ((0.92, 0.95, 1, 1), (0.3, 0.35, 0.55, 1)),
    "shout": ((1, 0.9, 0.35, 1), (0.6, 0.2, 0.1, 1)),
}

FILTER_FS = """
$HEADER$
uniform float mode;
uniform float tick;
void main(void) {
    vec4 c = frag_color * texture2D(texture0, tex_coord0);
    vec3 col = c.rgb;
    float l = dot(col, vec3(0.299, 0.587, 0.114));
    vec2 d = tex_coord0 - vec2(0.5, 0.5);
    float vig = 1.0 - dot(d, d) * 1.1;
    if (mode > 0.5 && mode < 1.5) {
        col = vec3(l) * 1.05;
    } else if (mode < 2.5 && mode > 1.5) {
        col = vec3(l * 1.08 + 0.06, l * 0.9 + 0.03, l * 0.68) * vig;
    } else if (mode < 3.5 && mode > 2.5) {
        col = col * vec3(0.42, 0.52, 0.95) * 0.9 + vec3(0.0, 0.02, 0.08);
        col *= vig;
    } else if (mode < 4.5 && mode > 3.5) {
        col = col * vec3(1.08, 0.98, 0.82) + vec3(0.06, 0.03, 0.0);
    } else if (mode < 5.5 && mode > 4.5) {
        col = col * vec3(0.86, 0.97, 1.1) + vec3(0.0, 0.01, 0.04);
    } else if (mode < 6.5 && mode > 5.5) {
        col = mix(vec3(l), col, 1.4);
        col = (col - 0.5) * 1.12 + 0.53;
    } else if (mode < 7.5 && mode > 6.5) {
        col = mix(col, vec3(1.0, 0.86, 0.96), 0.2) + 0.05;
        col = mix(col, vec3(1.0), (1.0 - vig) * 0.8);
    } else if (mode > 7.5) {
        float fl = 0.94 + 0.06 * sin(tick * 37.0);
        col = vec3(l * 1.05 + 0.05, l * 0.93 + 0.02, l * 0.75) * vig * fl;
        float line = step(0.996, fract(tex_coord0.x * 7.0 + tick * 0.7));
        col = mix(col, vec3(0.2, 0.17, 0.12), line * 0.5);
    }
    gl_FragColor = vec4(clamp(col, 0.0, 1.0), c.a);
}
"""

# якщо шейдер не зібрався — приблизні відтінки замість фільтрів
TINT = {"bw": (0.92, 0.92, 0.92), "sepia": (1, 0.88, 0.7), "night": (0.45, 0.55, 0.95), "warm": (1, 0.93, 0.8),
        "cold": (0.86, 0.96, 1), "dream": (1, 0.93, 0.98), "film": (1, 0.88, 0.7)}


class FrameRenderer:
    def __init__(self, catalog, size=(1280, 720), project_dir=None):
        self.cat = catalog
        self.W, self.H = size
        self.project_dir = project_dir
        self.raw = Fbo(size=size)
        self.shader_ok = True
        self.cur = self._filter_fbo(size)
        self.prev = self._filter_fbo(size)
        self.fbo = Fbo(size=size)
        self._labels = {}

    def _filter_fbo(self, size):
        f = Fbo(size=size)
        if self.shader_ok:
            try:
                f.shader.fs = FILTER_FS
                ok = bool(getattr(f.shader, "success", True))
            except Exception as e:  # noqa: BLE001
                Logger.warning(f"render: фільтри недоступні ({e})")
                ok = False
            if not ok:
                self.shader_ok = False
                f = Fbo(size=size)
        return f

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

    def _bg_texture(self, bg_id):
        cat = self.cat
        path = cat.background_path(bg_id, self.project_dir) or cat.background_path(cat.default_background())
        try:
            tex = imgload.texture(path)
        except Exception:
            tex = imgload.texture(cat.background_path(cat.default_background()))
        return imgload.cover(tex, self.W / float(self.H))

    # ------------------------------------------------------------ кадр
    def render(self, project, t, still=False):
        loc = model.locate(project, t)
        if loc is None:
            return
        i, lt, length = loc
        self.render_scene(project, i, lt, length, still=still)

    def render_scene(self, project, index, lt, length=None, still=False):
        sc = project["scenes"][index]
        length = length or model.scene_timing(sc)[0]
        W, H = self.W, self.H
        tr = None if still else model.transition(project, index, lt, length)
        prev_tex = None
        if tr and tr[0] in model.NEEDS_PREV and index > 0:
            psc = project["scenes"][index - 1]
            plen = model.scene_timing(psc)[0]
            self._scene_pass(project, index - 1, plen - 0.001, plen, self.prev, lt)
            prev_tex = self.prev.texture
        heads, spans = self._scene_pass(project, index, lt, length, self.cur, lt)
        cur_tex = self.cur.texture

        out = self.fbo
        out.clear()
        with out:
            ClearColor(0, 0, 0, 1)
            ClearBuffers()
            kind, p = tr if tr else (None, 1.0)
            e = model.ease(p)
            if prev_tex is not None and kind in ("slide_left", "slide_right", "slide_up"):
                dx, dy = {"slide_left": (W, 0), "slide_right": (-W, 0), "slide_up": (0, -H)}[kind]
                Color(1, 1, 1, 1)
                Rectangle(texture=prev_tex, pos=(-dx * e, -dy * e), size=(W, H))
                Rectangle(texture=cur_tex, pos=(dx * (1 - e), dy * (1 - e)), size=(W, H))
            elif prev_tex is not None and kind == "wipe":
                Color(1, 1, 1, 1)
                Rectangle(texture=prev_tex, pos=(0, 0), size=(W, H))
                w = max(1, int(W * e))
                Rectangle(texture=cur_tex.get_region(0, 0, w, H), pos=(0, 0), size=(w, H))
                Color(1, 1, 1, 0.8 * (1 - e))
                Rectangle(pos=(w - H * 0.006, 0), size=(H * 0.012, H))
            else:
                Color(1, 1, 1, 1)
                Rectangle(texture=cur_tex, pos=(0, 0), size=(W, H))
                if prev_tex is not None and kind == "dissolve":
                    Color(1, 1, 1, 1 - p)
                    Rectangle(texture=prev_tex, pos=(0, 0), size=(W, H))
                elif prev_tex is not None and kind == "zoom":
                    k = 1 + 0.7 * e
                    Color(1, 1, 1, 1 - e)
                    Rectangle(texture=prev_tex, pos=(W * (1 - k) / 2, H * (1 - k) / 2), size=(W * k, H * k))
            sc_lines = model.active_lines(sc, lt, spans)
            for ln, prog in sc_lines:
                self._bubble(ln, prog, heads.get(ln.get("speaker")))
            if kind == "fade":
                Color(0, 0, 0, 1 - p)
                Rectangle(pos=(0, 0), size=(W, H))
            elif kind == "flash":
                Color(1, 1, 1, (1 - p) ** 1.5)
                Rectangle(pos=(0, 0), size=(W, H))
            elif kind == "circle":
                self._iris(e)
            if not still:
                a = model.end_fade(project, index, lt, length)
                if a > 0:
                    Color(0, 0, 0, a)
                    Rectangle(pos=(0, 0), size=(W, H))
        out.draw()

    def _iris(self, e):
        W, H = self.W, self.H
        cx, cy = W / 2.0, H / 2.0
        r0 = e * math.hypot(W, H) / 2.0 * 1.02
        r1 = math.hypot(W, H)
        n = 48
        verts, idx = [], []
        for k in range(n + 1):
            a = k / float(n) * 2 * math.pi
            ca, sa = math.cos(a), math.sin(a)
            verts += [cx + ca * r0, cy + sa * r0, 0, 0, cx + ca * r1, cy + sa * r1, 0, 0]
            idx += [2 * k, 2 * k + 1]
        Color(0, 0, 0, 1)
        Mesh(vertices=verts, indices=idx, mode="triangle_strip")

    # ------------------------------------------------------------ одна сцена (з фільтром)
    def _scene_pass(self, project, index, lt, length, target, tick):
        sc = project["scenes"][index]
        L, spans = model.scene_timing(sc)
        W, H = self.W, self.H
        cat = self.cat
        items = sc["items"]
        states = []
        for it in items:
            char = cat.characters.get(it["id"]) if it["kind"] == "char" else None
            states.append(model.item_state(it, sc, lt, length, char, spans))
        focus_pt = None
        if sc.get("camera") in model.FOCUS_MOVES:
            for it, st in zip(items, states):
                if it.get("uid") == sc.get("focus"):
                    try:
                        hf = cat.base_height(dict(it, frame=st["frame"])) * st["scale"] * st["sy"]
                    except Exception:
                        hf = 0.4
                    focus_pt = (st["x"] + st["dx"], st["y"] + st["dy"] + hf * 0.6)
                    break
            if focus_pt is None and items:
                st = states[0]
                focus_pt = (st["x"] + st["dx"], st["y"] + st["dy"] + 0.25)
        zoom, ox, oy = model.camera(sc, lt, length, focus_pt)
        filt = sc.get("filter", "none") or "none"

        raw = self.raw
        raw.clear()
        heads = {}
        with raw:
            ClearColor(0, 0, 0, 1)
            ClearBuffers()
            PushMatrix()
            Translate(W / 2.0 + ox * W, H / 2.0 + oy * H)
            Scale(zoom, zoom, 1)
            Translate(-W / 2.0, -H / 2.0)
            Color(1, 1, 1, 1)
            Rectangle(texture=self._bg_texture(sc.get("background")), pos=(0, 0), size=(W, H))
            sparks = []
            for k in model.draw_order(sc, states):
                it, st = items[k], states[k]
                if st["alpha"] <= 0.003:
                    continue
                tmp = dict(it, frame=st["frame"], scale=st["scale"])
                try:
                    tex = imgload.texture(cat.item_path(tmp))
                    h0 = cat.base_height(tmp) * st["scale"] * H
                    dw, dh = cat.item_dims(tmp)
                except Exception:
                    continue
                w0 = h0 * dw / float(dh)
                w, h = w0 * st["sx"], h0 * st["sy"]
                cx, by = (st["x"] + st["dx"]) * W, (st["y"] + st["dy"]) * H
                tc = tuple(tex.tex_coords)
                if st["flip"]:
                    tc = flipped_coords(tc)
                Color(1, 1, 1, st["alpha"])
                if st["rot"]:
                    PushMatrix()
                    Rotate(angle=st["rot"], origin=(cx, by + h / 2.0))
                    Rectangle(texture=tex, tex_coords=tc, pos=(cx - w / 2.0, by), size=(w, h))
                    PopMatrix()
                else:
                    Rectangle(texture=tex, tex_coords=tc, pos=(cx - w / 2.0, by), size=(w, h))
                if st["magic"] > 0:
                    sparks += fx.burst(cx / W, (by + h0 * 0.5) / H, st["magic"], h0 / H)
                if st.get("anim") == "sleep" and not st["moving"]:
                    self._zzz(cx + w0 * 0.25, by + h0 * 0.85, h0, tick)
                if st["alpha"] > 0.3:
                    # точка над головою (для хмаринки), з урахуванням камери
                    hx = W / 2.0 + ox * W + (cx - W / 2.0) * zoom
                    hy = H / 2.0 + oy * H + (by + h0 * 0.96 - H / 2.0) * zoom
                    heads[it.get("uid")] = (hx, hy, w0 * zoom)
            self._draw_particles(sparks)
            PopMatrix()
            eff = sc.get("effect", "none")
            if eff and eff != "none":
                self._draw_particles(fx.particles(eff, tick))
        raw.draw()

        target.clear()
        with target:
            ClearColor(0, 0, 0, 1)
            ClearBuffers()
            tint = (1, 1, 1) if self.shader_ok else TINT.get(filt, (1, 1, 1))
            Color(tint[0], tint[1], tint[2], 1)
            Rectangle(texture=raw.texture, pos=(0, 0), size=(W, H))
        if self.shader_ok:
            target["mode"] = float(model.FILTER_CODE.get(filt, 0))
            target["tick"] = float(tick)
        target.draw()
        return heads, spans

    def _draw_particles(self, parts):
        if not parts:
            return
        W, H = self.W, self.H
        for name, x, y, s, rot, rgba in parts:
            try:
                tex = imgload.texture(os.path.join(FX_DIR, name + ".png"))
            except Exception:
                continue
            d = s * H
            Color(*rgba)
            if rot:
                PushMatrix()
                Rotate(angle=rot, origin=(x * W, y * H))
                Rectangle(texture=tex, pos=(x * W - d / 2, y * H - d / 2), size=(d, d))
                PopMatrix()
            else:
                Rectangle(texture=tex, pos=(x * W - d / 2, y * H - d / 2), size=(d, d))

    def _zzz(self, x, y, h, t):
        for k in range(3):
            p = ((t * 0.6 + k / 3.0) % 1.0)
            tex = self._text_texture("Z", "say", 200, h * (0.08 + 0.06 * p), color=(0.35, 0.45, 0.95, 1))
            Color(1, 1, 1, math.sin(math.pi * p))
            Rectangle(texture=tex, pos=(x + h * 0.15 * p, y + h * 0.35 * p), size=tex.size)

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
