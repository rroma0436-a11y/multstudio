"""3D-песик (бігль) на головному екрані.

Крутиться пальцем у будь-який бік (і догори дриґом), двома пальцями — більше/менше й поворот,
подвійний дотик — назад. Дотик — песик щось робить; кнопки — дії й емоції.

Модель лежить у puppy3d.bin (зроблена заздалегідь: шерсть, очі, ніс, брови, язик, нашийник),
малюється власним шейдером у Fbo з буфером глибини. «Кістки» (голова, вуха, хвіст, лапи, очі,
брови, язик) рухаються в шейдері — тому анімація плавна й легка для телефона.
Якщо 3D на телефоні не запрацює — головна покаже звичайного песика (main.Showcase).
"""
import json
import math
import os
import random
import struct
import zlib

from kivy.clock import Clock
from kivy.graphics import (Callback, ClearBuffers, ClearColor, Color, Fbo, Mesh, Rectangle, RoundedRectangle,
                           Triangle)
from kivy.graphics.opengl import GL_DEPTH_TEST, glDisable, glEnable
from kivy.logger import Logger
from kivy.metrics import dp, sp
from kivy.uix.label import Label
from kivy.uix.widget import Widget

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "puppy3d.bin")
FMT = [(b"v_pos", 3, "float"), (b"v_normal", 3, "float"), (b"v_color", 4, "float"), (b"v_bone", 3, "float")]


def model_available():
    return os.path.exists(MODEL)


# ====================================================================== кватерніони й матриці
def q_axis(axis, deg):
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    a = math.radians(deg) * 0.5
    s = math.sin(a) / n
    return (x * s, y * s, z * s, math.cos(a))


def q_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def q_norm(q):
    n = math.sqrt(sum(v * v for v in q)) or 1.0
    return tuple(v / n for v in q)


def q_rot(q, v):
    qx, qy, qz, qw = q
    vx, vy, vz = v
    tx = 2 * (qy * vz - qz * vy)
    ty = 2 * (qz * vx - qx * vz)
    tz = 2 * (qx * vy - qy * vx)
    return (vx + qw * tx + (qy * tz - qz * ty),
            vy + qw * ty + (qz * tx - qx * tz),
            vz + qw * tz + (qx * ty - qy * tx))


def q_nlerp(a, b, k):
    if sum(x * y for x, y in zip(a, b)) < 0:
        b = tuple(-x for x in b)
    return q_norm(tuple(x + (y - x) * k for x, y in zip(a, b)))


def q_euler(yaw=0.0, pitch=0.0, roll=0.0):
    """yaw — навколо вертикалі (y), pitch — ніс угору/вниз (навколо z), roll — набік (навколо x)."""
    q = (0.0, 0.0, 0.0, 1.0)
    if yaw:
        q = q_mul(q, q_axis((0, 1, 0), yaw))
    if pitch:
        q = q_mul(q, q_axis((0, 0, 1), pitch))
    if roll:
        q = q_mul(q, q_axis((1, 0, 0), roll))
    return q


def m_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def m_translate(x, y, z):
    return [[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]]


def m_scale(s):
    return [[s, 0, 0, 0], [0, s, 0, 0], [0, 0, s, 0], [0, 0, 0, 1]]


def m_quat(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
            [0, 0, 0, 1]]


def m_perspective(fov, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov) / 2)
    return [[f / aspect, 0, 0, 0], [0, f, 0, 0],
            [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]]


def m_apply(m, p):
    x, y, z = p
    return tuple(m[i][0] * x + m[i][1] * y + m[i][2] * z + m[i][3] for i in range(4))


def m_flat(m):
    """Для kivy Matrix.set(flat=…): по стовпцях (як в OpenGL)."""
    return [float(m[r][c]) for c in range(4) for r in range(4)]


# ====================================================================== модель
def load(path=MODEL):
    """(meta, [(vertices, indices)…]) — вершини для kivy Mesh у форматі FMT."""
    import numpy as np
    raw = open(path, "rb").read()
    if raw[:4] != b"PUP3":
        raise ValueError("не той файл моделі")
    hl = struct.unpack("<I", raw[4:8])[0]
    meta = json.loads(raw[8:8 + hl].decode("utf-8"))
    data = zlib.decompress(raw[8 + hl:])
    out = []
    o = 0
    for m in meta["meshes"]:
        nv, nt = m["nv"], m["nt"]
        pos = np.frombuffer(data, "<i2", nv * 3, o).reshape(nv, 3).astype(np.float32) / meta["pos_k"]
        o += nv * 6
        nor = np.frombuffer(data, "i1", nv * 3, o).reshape(nv, 3).astype(np.float32) / 127.0
        o += nv * 3
        col = np.frombuffer(data, "u1", nv * 4, o).reshape(nv, 4).astype(np.float32) / 255.0
        o += nv * 4
        bone = np.frombuffer(data, "u1", nv * 3, o).reshape(nv, 3).astype(np.float32)
        o += nv * 3
        tri = np.frombuffer(data, "<u2", nt * 3, o)
        o += nt * 6
        bone[:, 1:] /= 255.0
        verts = np.concatenate([pos, nor, col, bone], axis=1).ravel()
        out.append((verts.tolist(), tri.astype(np.int64).tolist()))
    return meta, out


def _vert(p, n, c, b):
    return [p[0], p[1], p[2], n[0], n[1], n[2], c[0], c[1], c[2], c[3], b[0], b[1], b[2]]


def stage_meshes():
    """Тло (градієнт) і кругла підставка — прості сітки, рахуються тут (тінь малює шейдер)."""
    out = []
    # тло — у координатах екрана (-1…1)
    top, bot = (0.80, 0.89, 1.0, 1.0), (1.0, 0.93, 0.86, 1.0)
    v = []
    for x, y, c in ((-1, -1, bot), (1, -1, bot), (1, 1, top), (-1, 1, top)):
        v += _vert((x, y, 0), (0, 0, 1), c, (16, 0, 0))
    out.append((v, [0, 1, 2, 0, 2, 3]))
    # підставка: верх + бортик
    R, H, cx, n = 1.30, 0.13, 0.04, 64
    v, idx = [], []
    top_c, ring_c, side_c = (0.93, 0.88, 0.80, 0.12), (0.95, 0.80, 0.62, 0.2), (0.97, 0.62, 0.42, 0.25)
    v += _vert((cx, 0, 0), (0, 1, 0), top_c, (15, 0, 0))
    for i in range(n):
        a = 2 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        v += _vert((cx + ca * R * 0.86, 0, sa * R * 0.86), (0, 1, 0), top_c, (15, 0, 0))
    for i in range(n):
        a = 2 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        v += _vert((cx + ca * R, 0, sa * R), (0, 1, 0), ring_c, (15, 0, 0))
    for i in range(n):
        j = (i + 1) % n
        idx += [0, 1 + j, 1 + i]
        idx += [1 + i, 1 + j, 1 + n + i, 1 + j, 1 + n + j, 1 + n + i]
    base = len(v) // 13
    for i in range(n):
        a = 2 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        v += _vert((cx + ca * R, 0, sa * R), (ca, 0.15, sa), side_c, (15, 0, 0))
        v += _vert((cx + ca * R * 0.96, -H, sa * R * 0.96), (ca, -0.2, sa), side_c, (15, 0, 0))
    for i in range(n):
        j = (i + 1) % n
        a0, b0, a1, b1 = base + 2 * i, base + 2 * i + 1, base + 2 * j, base + 2 * j + 1
        idx += [a0, a1, b0, b0, a1, b1]
    out.append((v, idx))
    return out


# ====================================================================== шейдер
VS = """
#ifdef GL_ES
    precision highp float;
#endif
attribute vec3 v_pos;
attribute vec3 v_normal;
attribute vec4 v_color;
attribute vec3 v_bone;
uniform mat4 u_mv;
uniform mat4 u_proj;
uniform vec4 q_body;
uniform vec3 p_body;
uniform vec3 t_body;
uniform vec3 s_body;
uniform vec4 q_head;
uniform vec4 q_earL;
uniform vec4 q_earR;
uniform vec4 q_tail;
uniform vec4 q_lfl;
uniform vec4 q_lfr;
uniform vec4 q_lbl;
uniform vec4 q_lbr;
uniform vec4 u_eyes;
uniform vec4 u_brow;
varying vec3 v_n;
varying vec3 v_v;
varying vec3 v_w;
varying vec4 v_c;
varying float v_k;

vec3 qrot(vec4 q, vec3 v) {
    vec3 t = 2.0 * cross(q.xyz, v);
    return v + q.w * t + cross(q.xyz, t);
}

vec3 arot(vec3 ax, float a, vec3 v) {
    float c = cos(a);
    float s = sin(a);
    return v * c + cross(ax, v) * s + ax * dot(ax, v) * (1.0 - c);
}

void main(void) {
    vec3 p = v_pos;
    vec3 n = v_normal;
    float b = v_bone.x;
    float wb = v_bone.y;
    float wh = v_bone.z;
    v_c = v_color;
    v_k = 0.0;
    if (b > 15.5) {
        v_k = 2.0;
        v_n = vec3(0.0, 0.0, 1.0);
        v_v = vec3(0.0, 0.0, -1.0);
        v_w = p;
        gl_Position = vec4(p.xy, 0.999, 1.0);
        return;
    }
    if (b > 14.5) {
        v_k = 3.0;
    } else {
        if (b > 1.5 && b < 8.5) {
            vec4 q;
            vec3 c;
            if (b < 2.5) { q = q_earL; c = %(earL)s; }
            else if (b < 3.5) { q = q_earR; c = %(earR)s; }
            else if (b < 4.5) { q = q_tail; c = %(tail)s; }
            else if (b < 5.5) { q = q_lfl; c = %(legFL)s; }
            else if (b < 6.5) { q = q_lfr; c = %(legFR)s; }
            else if (b < 7.5) { q = q_lbl; c = %(legBL)s; }
            else { q = q_lbr; c = %(legBR)s; }
            p = mix(p, qrot(q, p - c) + c, wb);
            n = mix(n, qrot(q, n), wb);
        } else if (b > 8.5 && b < 10.5) {
            vec3 c = b < 9.5 ? %(eyeL)s : %(eyeR)s;
            vec3 s = vec3(u_eyes.z, b < 9.5 ? u_eyes.x : u_eyes.y, u_eyes.z);
            p = c + (p - c) * s;
            n = n / s;
        } else if (b > 10.5 && b < 11.5) {
            p = %(tongue)s + (p - %(tongue)s) * u_brow.w + vec3(0.015, -0.03, 0.0) * u_brow.w;
        } else if (b > 11.5) {
            vec3 c = b < 12.5 ? %(browL)s : %(browR)s;
            vec3 ax = b < 12.5 ? %(abrowL)s : %(abrowR)s;
            float a = b < 12.5 ? u_brow.x : u_brow.y;
            p = arot(ax, a, p - c) + c + vec3(0.0, u_brow.z, 0.0);
            n = arot(ax, a, n);
        }
        if (wh > 0.002) {
            p = mix(p, qrot(q_head, p - %(head)s) + %(head)s, wh);
            n = mix(n, qrot(q_head, n), wh);
        }
        p = qrot(q_body, (p - p_body) * s_body) + p_body + t_body;
        n = qrot(q_body, n / s_body);
    }
    vec4 mv = u_mv * vec4(p, 1.0);
    v_w = p;
    v_v = mv.xyz;
    v_n = (u_mv * vec4(n, 0.0)).xyz;
    gl_Position = u_proj * mv;
}
"""

FS = """
#ifdef GL_ES
    precision mediump float;
#endif
varying vec3 v_n;
varying vec3 v_v;
varying vec3 v_w;
varying vec4 v_c;
varying float v_k;
uniform vec4 u_shadow;
uniform vec4 u_shade;

void main(void) {
    if (v_k > 1.5 && v_k < 2.5) {
        gl_FragColor = vec4(v_c.rgb, 1.0);
        return;
    }
    vec3 N = normalize(v_n);
    vec3 V = normalize(-v_v);
    vec3 L1 = normalize(vec3(-0.45, 0.75, 0.55));
    float x = clamp((dot(N, L1) + 0.3) / 1.15, 0.0, 1.0);
    float diff = x * x * (3.0 - 2.0 * x);
    vec3 base = v_c.rgb;
    float gloss = v_c.a;
    vec3 col = base * (0.40 + 0.70 * diff) * vec3(1.0, 0.98, 0.95);
    vec3 L2 = normalize(vec3(0.7, -0.15, 0.6));
    col += base * 0.20 * max(dot(N, L2), 0.0) * vec3(0.8, 0.9, 1.0);
    float hemi = N.y * 0.5 + 0.5;
    col *= mix(vec3(0.86, 0.83, 0.82), vec3(1.04, 1.04, 1.08), hemi);
    float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
    col += rim * 0.22 * vec3(1.0, 0.96, 0.9);
    vec3 H = normalize(L1 + V);
    col += vec3(pow(max(dot(N, H), 0.0), 8.0 + 72.0 * gloss) * gloss * 0.9);
    col = min(col, vec3(1.0));
    if (v_k > 2.5) {
        // м'яка тінь песика на підставці (еліпс під тулубом)
        vec2 d = v_w.xz - u_shadow.xy;
        float c = cos(u_shadow.w);
        float s = sin(u_shadow.w);
        vec2 q = vec2(d.x * c - d.y * s, d.x * s + d.y * c) / max(0.2, u_shadow.z);
        float r = length(q / vec2(0.95, 0.48));
        float sh = (1.0 - smoothstep(0.15, 1.0, r)) * 0.6 * u_shade.x;
        col = mix(col, col * vec3(0.52, 0.46, 0.66), sh);
    }
    gl_FragColor = vec4(col, 1.0);
}
"""


def _v3(p):
    return "vec3(%.5f, %.5f, %.5f)" % tuple(float(v) for v in p)


def shader_source(meta):
    pv = meta["pivots"]
    eyes = meta["eyes"]
    consts = {k: _v3(pv[k]) for k in ("head", "earL", "earR", "tail", "legFL", "legFR", "legBL", "legBR")}
    consts.update(eyeL=_v3(eyes["eyeL"][0]), eyeR=_v3(eyes["eyeR"][0]), browL=_v3(eyes["browL"][0]),
                  browR=_v3(eyes["browR"][0]), abrowL=_v3(eyes["browL"][1]), abrowR=_v3(eyes["browR"][1]),
                  tongue=_v3(meta["tongue"]))
    return VS % consts, FS


def brow_signs(meta):
    """Знак кута брови, щоб «+» для обох означало «внутрішній край угору» (сумний вираз)."""
    out = {}
    for k in ("browL", "browR"):
        c, ax = meta["eyes"][k]
        inner = (0.0, 0.0, -0.045 if c[2] > 0 else 0.045)
        q = q_axis(ax, 10)
        out[k] = 1.0 if q_rot(q, inner)[1] > 0 else -1.0
    return out


# ====================================================================== пози, емоції, дії
PARAMS = ("bx", "by", "bz", "pitch", "yaw", "roll", "sq", "px", "py", "hp", "hy", "hr", "eLo", "eLs", "eRo",
          "eRs", "tw", "tl", "fl", "fr", "bl", "br", "eo", "ew", "ba", "bh", "tg")
DEFAULT = dict.fromkeys(PARAMS, 0.0)
DEFAULT.update(sq=1.0, px=0.0, py=0.55, eo=1.0, ew=1.0)

POSES = {
    "stand": {},
    # сидить: спина піднята навколо плечей, передні лапи рівно, задні — уперед
    "sit": {"pitch": 34.0, "px": 0.30, "py": 0.64, "fl": -34.0, "fr": -34.0, "bl": 58.0, "br": 58.0,
            "hp": -26.0, "tl": 40.0, "by": 0.0},
    # лежить: живіт на підставці, передні лапи вперед, задні — назад («жабкою»)
    "lie": {"by": -0.345, "fl": 80.0, "fr": 80.0, "bl": -78.0, "br": -78.0, "hp": -6.0, "tl": 55.0,
            "pitch": -2.0},
}
EMOTIONS = {
    "calm": {},
    "happy": {"tg": 1.0, "eo": 0.9, "ba": 6.0, "bh": 0.008, "eLs": 10.0, "eRs": 10.0, "eLo": 8.0, "eRo": 8.0},
    "sad": {"hp": -16.0, "eLo": -6.0, "eRo": -6.0, "eLs": -14.0, "eRs": -14.0, "tl": 50.0, "eo": 0.72,
            "ba": 26.0, "bh": -0.004},
    "scared": {"sq": -0.08, "hp": -12.0, "eLs": -30.0, "eRs": -30.0, "tl": 85.0, "eo": 1.22, "ew": 0.12,
               "ba": 22.0, "bh": 0.02},
    "angry": {"hp": -8.0, "pitch": -4.0, "ba": -26.0, "bh": -0.012, "eo": 0.78, "tl": -20.0, "eLs": -10.0,
              "eRs": -10.0},
    "surprised": {"eo": 1.35, "ew": 0.14, "ba": 12.0, "bh": 0.035, "hp": 8.0, "eLo": 16.0, "eRo": 16.0},
    "sleep": {"eo": -0.95, "hp": -16.0, "hr": 8.0, "tl": 20.0, "eLs": -6.0, "eRs": -6.0},
}
EMOTION_LABELS = [("happy", "Радіє"), ("sad", "Сумує"), ("surprised", "Дивується"), ("scared", "Боїться"),
                  ("angry", "Сердиться"), ("calm", "Спокійний")]
# хвіст: (розмах, частота) залежно від настрою
WAG = {"calm": (14.0, 1.1), "happy": (34.0, 3.4), "sad": (4.0, 0.6), "scared": (2.0, 7.0), "angry": (4.0, 5.0),
       "surprised": (10.0, 2.0), "sleep": (0.0, 0.5)}


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def bump(u, a, b):
    """0 → 1 → 0 між a і b (м'яко)."""
    if u <= a or u >= b:
        return 0.0
    return math.sin(math.pi * (u - a) / (b - a))


def _jump(u, d):
    out = {}
    if u < 0.22:
        k = bump(u, 0, 0.44)
        out.update(sq=-0.14 * k, by=-0.04 * k, hp=-6 * k)
    elif u < 0.88:
        k = (u - 0.22) / 0.66
        h = math.sin(math.pi * k)
        out.update(by=0.46 * h, fl=34 * h, fr=34 * h, bl=-36 * h, br=-36 * h, eLo=55 * h, eRo=55 * h,
                   pitch=10 * math.cos(math.pi * k), sq=0.06 * h, tw=0, tl=-15 * h)
    else:
        k = bump(u, 0.84, 1.1)
        out.update(sq=-0.12 * k, by=-0.03 * k, eLo=-8 * k, eRo=-8 * k)
    return out


def _bark(u, d):
    k = bump(u, 0.02, 0.28) + 0.85 * bump(u, 0.36, 0.62)
    return {"hp": 16 * k, "by": 0.03 * k, "eLo": 12 * k, "eRo": 12 * k, "pitch": 3 * k, "tg": 0.6 * k,
            "ba": -6 * k}


def _wag(u, d):
    env = ease(u / 0.25) * ease((d - u) / 0.3)
    return {"tw": 40 * math.sin(2 * math.pi * 4.2 * u) * env, "yaw": 7 * math.sin(2 * math.pi * 2.1 * u) * env,
            "by": 0.05 * abs(math.sin(2 * math.pi * 2.1 * u)) * env, "tg": env, "eo": -0.2 * env,
            "ba": 8 * env, "hr": 8 * math.sin(2 * math.pi * 1.05 * u) * env}


def _spin(u, d):
    k = ease(u / d)
    h = math.sin(math.pi * u / d)
    return {"yaw": 360 * k, "by": 0.16 * h, "eLo": 40 * h, "eRo": 40 * h, "tw": 25 * h}


def _roll(u, d):
    k = ease(u / d)
    h = math.sin(math.pi * k)
    return {"roll": 360 * k, "by": 0.46 * h, "py": 0.18, "fl": -45 * h, "fr": -45 * h, "bl": 40 * h, "br": 40 * h,
            "eLo": 50 * h, "eRo": 50 * h, "tl": -30 * h}


def _paw(u, d):
    k = ease(u / 0.35) * ease((d - u) / 0.35)
    return {"fr": 100 * k + 6 * math.sin(2 * math.pi * 2 * u) * k, "hr": 16 * k, "hp": 6 * k, "roll": -4 * k,
            "ba": 10 * k, "tg": 0.6 * k}


def _dance(u, d):
    f = 2.2
    s = math.sin(2 * math.pi * f * u)
    env = ease(u / 0.3) * ease((d - u) / 0.3)
    return {"by": 0.12 * abs(s) * env, "roll": 14 * s * env, "yaw": 30 * math.sin(math.pi * f * u) * env,
            "fl": 30 * max(0, s) * env, "fr": 30 * max(0, -s) * env, "hr": -14 * s * env, "tw": 35 * s * env,
            "eLo": 30 * abs(s) * env, "eRo": 30 * abs(s) * env, "tg": env}


def _shake(u, d):
    k = 1 - u / d
    s = math.sin(2 * math.pi * 6.5 * u)
    return {"roll": 13 * s * k, "hr": 26 * math.sin(2 * math.pi * 6.5 * u + 0.6) * k,
            "eLo": 45 * abs(s) * k, "eRo": 45 * abs(math.sin(2 * math.pi * 6.5 * u + 0.6)) * k,
            "tw": 30 * s * k, "eo": -0.5 * k}


def _tilt(u, d):
    k = ease(u / 0.3) * ease((d - u) / 0.4)
    return {"hr": 26 * k, "eLo": 20 * k, "eRs": -12 * k, "ba": 14 * k, "hp": 4 * k}


def _run(u, d):
    env = ease(u / 0.3) * ease((d - u) / 0.3)
    f = 3.2
    ph = 2 * math.pi * f * u
    ang = 2 * math.pi * ease(u / d)          # біжить колом по підставці
    r = 0.55
    return {"bx": r * math.sin(ang) * env, "bz": (r - r * math.cos(ang)) * env * 0.9, "yaw": -math.degrees(ang) * env,
            "fl": 38 * math.sin(ph) * env, "fr": 38 * math.sin(ph + 0.6) * env, "bl": -38 * math.sin(ph + 2.4) * env,
            "br": -38 * math.sin(ph + 3.0) * env, "by": 0.07 * abs(math.sin(ph)) * env,
            "pitch": 6 * math.sin(ph) * env, "eLo": 30 * abs(math.sin(ph)) * env, "eRo": 30 * abs(math.sin(ph)) * env,
            "tw": 20 * math.sin(ph) * env, "tg": env}


def _walk(u, d):
    env = ease(u / 0.4) * ease((d - u) / 0.4)
    f = 1.6
    ph = 2 * math.pi * f * u
    ang = 2 * math.pi * ease(u / d)
    r = 0.45
    return {"bx": r * math.sin(ang) * env, "bz": (r - r * math.cos(ang)) * env * 0.9, "yaw": -math.degrees(ang) * env,
            "fl": 22 * math.sin(ph) * env, "fr": -22 * math.sin(ph) * env, "bl": -22 * math.sin(ph) * env,
            "br": 22 * math.sin(ph) * env, "by": 0.02 * abs(math.sin(ph)) * env, "hp": 3 * math.sin(2 * ph) * env,
            "roll": 2 * math.sin(ph) * env}


def _sniff(u, d):
    env = ease(u / 0.4) * ease((d - u) / 0.4)
    return {"hp": -30 * env + 4 * math.sin(2 * math.pi * 5 * u) * env, "hy": 18 * math.sin(2 * math.pi * 0.7 * u) * env,
            "pitch": -6 * env, "eLs": 12 * env, "eRs": 12 * env, "tw": 18 * math.sin(2 * math.pi * 3 * u) * env}


def _hello(u, d):
    k = ease(u / 0.3) * ease((d - u) / 0.3)
    return {"fr": 70 * k + 25 * math.sin(2 * math.pi * 3 * u) * k, "hr": -10 * k, "tg": k, "ba": 8 * k}


def _nothing(u, d):
    return {}


# ключ: (підпис, тривалість, функція, потрібна поза, поза після, репліка, звук, емоція після)
ACTIONS = {
    "bark": ("Гав!", 0.9, _bark, None, None, "Гав-гав!", "puppy_bark", None),
    "jump": ("Стрибок", 1.1, _jump, "stand", "stand", "Гоп!", "jump", None),
    "wag": ("Хвостик", 2.2, _wag, None, None, "Я тебе люблю!", None, "happy"),
    "sit": ("Сидіти", 0.6, _nothing, "sit", "sit", "Сиджу!", None, None),
    "lie": ("Лежати", 0.6, _nothing, "lie", "lie", "Відпочиваю…", None, None),
    "stand": ("Встати", 0.6, _nothing, "stand", "stand", "", None, None),
    "paw": ("Лапу", 2.0, _paw, "sit", "sit", "Тримай лапу!", None, None),
    "hello": ("Привіт", 1.8, _hello, "sit", "sit", "Привіт!", None, "happy"),
    "spin": ("Крутись", 1.3, _spin, "stand", "stand", "Вжух!", None, None),
    "roll": ("Перекид", 1.9, _roll, "lie", "stand", "Ух ти!", "fall_soft", None),
    "dance": ("Танець", 2.8, _dance, "stand", "stand", "Танцюю!", None, "happy"),
    "shake": ("Струснись", 1.3, _shake, "stand", "stand", "", None, None),
    "tilt": ("Що?", 1.6, _tilt, None, None, "Гм?", None, None),
    "run": ("Біжи", 3.2, _run, "stand", "stand", "Біжу!", None, "happy"),
    "walk": ("Гуляй", 4.0, _walk, "stand", "stand", "Гуляю…", None, None),
    "sniff": ("Нюхай", 2.4, _sniff, "stand", "stand", "Що тут пахне?", None, None),
    "sleep": ("Спати", 0.8, _nothing, "lie", "lie", "", None, "sleep"),
}
BUTTONS = ["bark", "jump", "sit", "lie", "stand", "paw", "hello", "spin", "roll", "dance", "run", "walk",
           "sniff", "shake", "tilt", "wag", "sleep"]
TAPS = ["bark", "jump", "wag", "spin", "tilt", "shake", "paw", "dance", "sniff", "roll", "hello", "run"]
IDLE_TALK = ["Привіт! Покрути мене пальцем!", "Торкнись — я щось покажу!", "Зробімо мультик?",
             "Гав! Я вмію сидіти й давати лапу!", "Два пальці — ближче або далі"]


class Animator:
    """Стан песика в часі: поза (стоїть/сидить/лежить), настрій і поточна дія."""

    def __init__(self):
        self.t = 0.0
        self.pose = "stand"
        self.pose_from = dict(DEFAULT)
        self.pose_t0 = -10.0
        self.emotion = "calm"
        self.emo_from = {}
        self.emo_t0 = -10.0
        self.action = None
        self.act_t0 = 0.0
        self.next_blink = 2.5
        self.blink_t0 = -1.0
        self.twitch_t0 = -10.0
        self.twitch_side = 1
        self.rng = random.Random(7)
        self.last = dict(DEFAULT)

    # ---------------------------------------------------------------- керування
    def _pose_now(self):
        k = ease((self.t - self.pose_t0) / 0.5)
        tgt = POSES[self.pose]
        return {p: self.pose_from.get(p, DEFAULT[p]) + (tgt.get(p, DEFAULT[p]) -
                                                         self.pose_from.get(p, DEFAULT[p])) * k for p in PARAMS}

    def _emo_now(self):
        k = ease((self.t - self.emo_t0) / 0.4)
        tgt = EMOTIONS[self.emotion]
        keys = set(tgt) | set(self.emo_from)
        return {p: self.emo_from.get(p, 0.0) + (tgt.get(p, 0.0) - self.emo_from.get(p, 0.0)) * k for p in keys}

    def set_pose(self, name):
        if name == self.pose:
            return 0.0
        self.pose_from = self._pose_now()
        self.pose = name
        self.pose_t0 = self.t
        return 0.5

    def set_emotion(self, name):
        if name == self.emotion:
            return
        self.emo_from = self._emo_now()
        self.emotion = name
        self.emo_t0 = self.t

    def play(self, key):
        """Почати дію. Повертає (репліка, звук, затримка звуку)."""
        spec = ACTIONS[key]
        _label, dur, _fn, need, _after, text, sound, emo = spec
        if self.emotion == "sleep" and key != "sleep":
            self.set_emotion("calm")
        delay = self.set_pose(need) if need else 0.0
        self.action = key
        self.act_t0 = self.t + delay
        if emo:
            self.set_emotion(emo)
        return text, sound, delay

    def busy(self):
        return self.action is not None

    # ---------------------------------------------------------------- кадр
    def update(self, dt):
        self.t += dt
        t = self.t
        p = self._pose_now()
        for k, v in self._emo_now().items():
            p[k] = p.get(k, 0.0) + v
        # дія
        if self.action is not None:
            _l, dur, fn, _need, after, _text, _snd, _emo = ACTIONS[self.action]
            u = t - self.act_t0
            if u >= dur:
                self.action = None
                if after:
                    self.set_pose(after)
            elif u >= 0:
                for k, v in fn(u, dur).items():
                    p[k] = p.get(k, 0.0) + v
        # «життя»: дихання, хвостик, кліпання, погляд
        sleeping = self.emotion == "sleep"
        br = 3.6 if sleeping else 2.6
        p["sq"] += (0.02 if sleeping else 0.012) * math.sin(2 * math.pi * t / br)
        amp, f = WAG.get(self.emotion, WAG["calm"])
        p["tw"] += amp * math.sin(2 * math.pi * f * t)
        if not sleeping:
            p["hy"] += 7 * math.sin(0.37 * t) + 4 * math.sin(0.71 * t + 1)
            p["hp"] += 3 * math.sin(0.53 * t + 2)
            if t >= self.next_blink:
                self.blink_t0 = t
                self.next_blink = t + self.rng.uniform(2.2, 5.0)
            p["eo"] *= 1 - 0.92 * bump(t - self.blink_t0, 0, 0.16)
            if self.rng.random() < dt * 0.12:
                self.twitch_t0 = t
                self.twitch_side = self.rng.choice((1, -1))
            tw = bump(t - self.twitch_t0, 0, 0.25)
            p["eLo" if self.twitch_side < 0 else "eRo"] += 18 * tw
        if self.emotion == "scared":
            p["roll"] += 1.5 * math.sin(40 * t)
        p["eo"] = max(0.05, p["eo"])
        self.last = p
        return p


# ====================================================================== параметри → шейдер
class Rig:
    def __init__(self, meta):
        self.meta = meta
        self.bsign = brow_signs(meta)
        self.center = tuple(meta.get("center", (0.15, 0.86, 0.0)))
        self.head = tuple(meta["pivots"]["head"])
        self.head_top = tuple(meta.get("head_top", (0.58, 1.8, 0.0)))

    def body(self, p):
        q = q_euler(p["yaw"], p["pitch"], p["roll"])
        piv = (p["px"], p["py"], 0.0)
        sq = max(0.5, p["sq"])
        sxz = 1.0 / math.sqrt(sq)
        return q, piv, (p["bx"], p["by"], p["bz"]), (sxz, sq, sxz)

    def uniforms(self, p):
        qb, piv, tb, sb = self.body(p)
        u = {"q_body": qb, "p_body": piv, "t_body": tb, "s_body": sb,
             "q_head": q_euler(p["hy"], p["hp"], p["hr"]),
             # вуха: «назовні» для обох — додатний кут; «уперед» — навколо z
             "q_earL": q_mul(q_axis((1, 0, 0), p["eLo"]), q_axis((0, 0, 1), p["eLs"])),
             "q_earR": q_mul(q_axis((1, 0, 0), -p["eRo"]), q_axis((0, 0, 1), p["eRs"])),
             "q_tail": q_mul(q_axis((0, 1, 0), p["tw"]), q_axis((0, 0, 1), p["tl"])),
             "q_lfl": q_axis((0, 0, 1), p["fl"]), "q_lfr": q_axis((0, 0, 1), p["fr"]),
             "q_lbl": q_axis((0, 0, 1), p["bl"]), "q_lbr": q_axis((0, 0, 1), p["br"])}
        eo = max(0.05, p["eo"])
        u["u_eyes"] = (eo, eo, max(0.6, p["ew"]), 0.0)
        a = math.radians(p["ba"])
        u["u_brow"] = (a * self.bsign["browL"], a * self.bsign["browR"], p["bh"], max(0.0, min(1.0, p["tg"])))
        # тінь: під тулубом, менша й світліша, коли песик у повітрі
        c = self.world((0.05, 0.0, 0.0), p, head=False)
        h = max(0.0, p["by"])
        lie = 1.0 + 0.25 * max(0.0, -p["by"]) / 0.35
        u["u_shadow"] = (c[0], c[2], max(0.45, (1.0 - 0.55 * h)) * lie, math.radians(p["yaw"]))
        u["u_shade"] = (max(0.25, 1.0 - 0.9 * h), 0.0, 0.0, 0.0)
        return {k: tuple(float(x) for x in v) for k, v in u.items()}

    def world(self, pt, p, head=True):
        """Де опиниться точка моделі (для хмаринки над головою)."""
        if head:
            qh = q_euler(p["hy"], p["hp"], p["hr"])
            d = tuple(a - b for a, b in zip(pt, self.head))
            pt = tuple(a + b for a, b in zip(q_rot(qh, d), self.head))
        qb, piv, tb, sb = self.body(p)
        d = tuple((a - b) * s for a, b, s in zip(pt, piv, sb))
        r = q_rot(qb, d)
        return tuple(a + b + c for a, b, c in zip(r, piv, tb))


# ====================================================================== віджет
Q_DEFAULT = q_mul(q_axis((1, 0, 0), 9.0), q_axis((0, 1, 0), -36.0))


class Puppy3D(Widget):
    """Сцена з 3D-песиком. on_action(key) — щоб головна могла озвучити дію (звук)."""

    SUPERSAMPLE = 1.35
    FOV = 30.0

    def __init__(self, sound_cb=None, **kw):
        super().__init__(**kw)
        self.sound_cb = sound_cb
        self.ok = False
        self.anim = Animator()
        self.rig = None
        self.q_user = Q_DEFAULT
        self.zoom = 1.0
        self.vel = (0.0, 0.0)
        self.touches = []
        self._t0 = {}
        self.idle_touch = 0.0
        self.tap_i = 0
        self.talk_i = 0
        self.next_talk = 6.0
        self.bubble_until = 0.0
        self._ev = None
        self._fbo_size = (0, 0)
        self._mats = None
        try:
            self._setup()
            self.ok = True
        except Exception as e:  # noqa: BLE001
            Logger.warning(f"Puppy3D: 3D недоступне: {e}")
            self.ok = False
        with self.canvas:
            self._bcol = Color(1, 1, 1, 0)
            self._brect = RoundedRectangle(radius=[dp(16)])
            self._btip = Triangle()
        self.bubble = Label(text="", font_size=sp(16), bold=True, color=(0.14, 0.13, 0.26, 1), halign="center",
                            valign="middle", opacity=0)
        self.add_widget(self.bubble)
        self.zzz = Label(text="", font_size=sp(22), bold=True, color=(0.4, 0.38, 1, 1))
        self.add_widget(self.zzz)
        self.hint = Label(text="☝ Крути пальцем  ·  торкнись", font_size=sp(12), color=(0.3, 0.3, 0.45, 0.85))
        self.add_widget(self.hint)
        self.bind(pos=self._layout, size=self._layout)
        if self.ok:
            self.say(IDLE_TALK[0], 4.0)

    # ---------------------------------------------------------------- OpenGL
    def _setup(self):
        if not model_available():
            raise FileNotFoundError("немає puppy3d.bin")
        meta, meshes = load(MODEL)
        self.rig = Rig(meta)
        vs, fs = shader_source(meta)
        self.fbo = Fbo(size=(64, 64), with_depthbuffer=True)
        self._compile(vs, fs)
        with self.fbo:
            ClearColor(0.9, 0.93, 1.0, 1.0)
            Callback(self._gl_on)
            ClearBuffers(clear_color=True, clear_depth=True)
            for v, i in stage_meshes():
                Mesh(vertices=v, indices=i, fmt=FMT, mode="triangles")
            for v, i in meshes:
                Mesh(vertices=v, indices=i, fmt=FMT, mode="triangles")
            Callback(self._gl_off)
        with self.canvas:
            Color(1, 1, 1, 1)
            self.view = Rectangle(texture=self.fbo.texture)
        self.canvas.insert(0, self.fbo)

    def _compile(self, vs, fs):
        sh = self.fbo.shader
        path = None
        try:
            from kivy.app import App
            app = App.get_running_app()
            d = os.path.join(app.user_data_dir if app else HERE, "cache")
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, "puppy3d.glsl")
            with open(path, "w") as f:
                f.write("---VERTEX SHADER---\n" + vs + "\n---FRAGMENT SHADER---\n" + fs)
            sh.source = path
        except Exception:
            sh.vs = vs
            sh.fs = fs
        if not getattr(sh, "success", True):
            sh.vs = vs
            sh.fs = fs
        if not getattr(sh, "success", True):
            raise RuntimeError("шейдер не зібрався")

    def _gl_on(self, *_):
        glEnable(GL_DEPTH_TEST)

    def _gl_off(self, *_):
        glDisable(GL_DEPTH_TEST)

    # ---------------------------------------------------------------- життєвий цикл
    def start(self):
        if self._ev is None and self.ok:
            self._ev = Clock.schedule_interval(self._tick, 1 / 30.0)

    def stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None

    def _layout(self, *_):
        if not self.ok:
            return
        w, h = max(8, int(self.width)), max(8, int(self.height))
        k = self.SUPERSAMPLE
        if max(w, h) * k > 1700:
            k = 1700.0 / max(w, h)
        fs = (max(8, int(w * k)), max(8, int(h * k)))
        if fs != self._fbo_size:
            self._fbo_size = fs
            self.fbo.size = fs
            tex = self.fbo.texture
            try:
                tex.mag_filter = "linear"
                tex.min_filter = "linear"
            except Exception:
                pass
            self.view.texture = tex
        self.view.pos, self.view.size = self.pos, self.size
        self.hint.size = (self.width, dp(18))
        self.hint.text_size = self.hint.size
        self.hint.halign = "center"
        self.hint.pos = (self.x, self.y + dp(4))
        self._draw(0.0)

    # ---------------------------------------------------------------- кадр
    def matrices(self):
        w, h = max(1.0, self.width), max(1.0, self.height)
        aspect = w / h
        fov = self.FOV
        # відстань, щоб песик із підставкою вміщався і у вузькому, і в широкому віконці
        dist = 6.0 if aspect >= 1.0 else 6.0 / max(0.55, aspect)
        c = self.rig.center
        mv = m_mul(m_translate(0, 0.12, -dist), m_mul(m_scale(self.zoom),
                                                       m_mul(m_quat(self.q_user), m_translate(-c[0], -c[1], -c[2]))))
        proj = m_perspective(fov, aspect, 1.0, 40.0)
        return mv, proj

    def to_screen(self, pt):
        mv, proj = self._mats or self.matrices()
        v = m_apply(proj, m_apply(mv, pt)[:3])
        if v[3] <= 1e-6:
            return None
        return (self.x + (v[0] / v[3] * 0.5 + 0.5) * self.width, self.y + (v[1] / v[3] * 0.5 + 0.5) * self.height)

    def _tick(self, dt):
        dt = min(dt, 0.1)
        # інерція після «кидка» пальцем
        if not self.touches:
            vx, vy = self.vel
            if abs(vx) + abs(vy) > 0.5:
                self._rotate(vx * dt, vy * dt)
                self.vel = (vx * 0.93, vy * 0.93)
            else:
                self.vel = (0.0, 0.0)
                self.idle_touch += dt
                if self.idle_touch > 14.0:          # давно не крутили — плавно назад
                    self.q_user = q_nlerp(self.q_user, Q_DEFAULT, 0.02)
                    self.zoom += (1.0 - self.zoom) * 0.02
        # балакає сам, коли нічого не відбувається
        if not self.anim.busy() and self.anim.t > self.next_talk and self.anim.emotion != "sleep":
            self.talk_i += 1
            self.say(IDLE_TALK[self.talk_i % len(IDLE_TALK)], 3.5)
            self.next_talk = self.anim.t + 9.0
        self._draw(dt)

    def _draw(self, dt):
        if not self.ok:
            return
        p = self.anim.update(dt)
        mv, proj = self.matrices()
        self._mats = (mv, proj)
        from kivy.graphics.transformation import Matrix
        m1 = Matrix()
        m1.set(flat=m_flat(mv))
        m2 = Matrix()
        m2.set(flat=m_flat(proj))
        f = self.fbo
        f["u_mv"] = m1
        f["u_proj"] = m2
        # тінь блідне, коли дивимось знизу (підставка тоді над песиком)
        up = m_apply(mv, (0, 1, 0))
        org = m_apply(mv, (0, 0, 0))
        look = up[1] - org[1]
        un = self.rig.uniforms(p)
        if look < 0:
            a = un["u_shade"]
            un["u_shade"] = (a[0] * max(0.0, 1 + look * 2), a[1], a[2], a[3])
        for k, v in un.items():
            f[k] = v
        f.ask_update()
        self.canvas.ask_update()
        self._overlay(p)

    def _overlay(self, p):
        t = self.anim.t
        show = t < self.bubble_until and self.bubble.text
        a = min(1.0, (self.bubble_until - t) / 0.3) if show else 0.0
        if show:
            hp = self.to_screen(self.rig.world(self.rig.head_top, p))
            if hp is None:
                hp = (self.center_x, self.top - dp(40))
            self.bubble.texture_update()
            bw = self.bubble.texture_size[0] + dp(28)
            bh = self.bubble.texture_size[1] + dp(16)
            bx = min(max(self.x + dp(6), hp[0] - bw / 2), self.right - bw - dp(6))
            by = min(hp[1] + dp(16), self.top - bh - dp(6))
            by = max(by, self.y + dp(30))
            self.bubble.size = (bw, bh)
            self.bubble.pos = (bx, by)
            self._brect.pos, self._brect.size = (bx, by), (bw, bh)
            tx = min(max(bx + dp(22), hp[0]), bx + bw - dp(22))
            tip_y = max(min(hp[1] + dp(2), by - dp(4)), by - dp(14))
            self._btip.points = [tx - dp(9), by + 1, tx + dp(9), by + 1, hp[0] if abs(hp[0] - tx) < dp(30) else tx,
                                 tip_y]
        self._bcol.a = 0.97 * a
        self.bubble.opacity = a
        if self.anim.emotion == "sleep" and self.anim.pose == "lie":
            k = (t * 0.6) % 1.0
            hp = self.to_screen(self.rig.world(self.rig.head_top, p)) or (self.center_x, self.top - dp(60))
            self.zzz.text = "z Z z"[:1 + int(k * 5)]
            self.zzz.texture_update()
            self.zzz.size = self.zzz.texture_size
            self.zzz.pos = (hp[0] + dp(10), hp[1] + dp(6) + dp(20) * k)
            self.zzz.opacity = 1.0 - k * 0.6
        else:
            self.zzz.opacity = 0
        self.hint.opacity = 0.85 if t < 12 else max(0.0, 0.85 - (t - 12) * 0.3)

    def say(self, text, seconds=2.2):
        if not text:
            return
        self.bubble.text = text
        self.bubble_until = self.anim.t + seconds

    # ---------------------------------------------------------------- дії
    def play(self, key):
        if not self.ok:
            return
        text, sound, delay = self.anim.play(key)
        if text:
            self.say(text, max(1.8, ACTIONS[key][1] + delay + 0.6))
        if sound and self.sound_cb:
            Clock.schedule_once(lambda dt: self.sound_cb(sound), delay + (0.25 if key == "jump" else 0.02))
        self.next_talk = self.anim.t + 10.0

    def emotion(self, name):
        if not self.ok:
            return
        if self.anim.emotion == "sleep" and name != "sleep":
            self.anim.set_pose("stand")
        self.anim.set_emotion(name)
        lines = {"happy": "Мені так весело!", "sad": "Мені сумно…", "surprised": "Ого!", "scared": "Ой, страшно!",
                 "angry": "Гр-р-р!", "calm": "Усе добре."}
        self.say(lines.get(name, ""), 2.4)
        if name == "surprised":
            self.anim.play("tilt")
        elif name == "happy":
            self.anim.play("wag")
        if name == "angry" and self.sound_cb:
            self.sound_cb("dog_growl")
        self.next_talk = self.anim.t + 10.0

    def reset_view(self):
        self.q_user = Q_DEFAULT
        self.zoom = 1.0
        self.vel = (0.0, 0.0)

    # ---------------------------------------------------------------- дотики
    def _rotate(self, dx_deg, dy_deg):
        # пальцем убік — песик крутиться навколо себе (як на крутилці), угору/вниз — перекидається
        # до нас чи від нас; разом це дає будь-який поворот, навіть догори дриґом
        q = q_mul(self.q_user, q_axis((0, 1, 0), dx_deg))
        q = q_mul(q_axis((1, 0, 0), -dy_deg), q)
        self.q_user = q_norm(q)

    def on_touch_down(self, touch):
        if not self.ok or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        touch.grab(self)
        self.touches.append(touch)
        self._t0[touch.uid] = (self.anim.t, touch.x, touch.y)
        self.vel = (0.0, 0.0)
        self.idle_touch = 0.0
        if getattr(touch, "is_double_tap", False) and len(self.touches) == 1:
            self.reset_view()
            self.say("Ось я!", 1.5)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        self.idle_touch = 0.0
        if len(self.touches) == 1:
            k = 0.45 * 160.0 / max(80.0, dp(160))      # градусів на піксель (не залежить від щільності екрана)
            dx, dy = touch.dx * k, touch.dy * k
            self._rotate(dx, dy)
            self.vel = (dx * 60 * 0.3, dy * 60 * 0.3)      # для «докручування» після відпускання
        elif len(self.touches) >= 2 and touch in self.touches[:2]:
            a, b = self.touches[0], self.touches[1]
            o = b if touch is a else a
            px, py = touch.px, touch.py
            d0 = math.hypot(px - o.x, py - o.y)
            d1 = math.hypot(touch.x - o.x, touch.y - o.y)
            if d0 > 10 and d1 > 10:
                self.zoom = max(0.55, min(2.0, self.zoom * d1 / d0))
                a0 = math.atan2(py - o.y, px - o.x)
                a1 = math.atan2(touch.y - o.y, touch.x - o.x)
                da = math.degrees(a1 - a0)
                if abs(da) < 30:
                    self.q_user = q_norm(q_mul(q_axis((0, 0, 1), da), self.q_user))
            self.vel = (0.0, 0.0)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        t0, x0, y0 = self._t0.pop(touch.uid, (self.anim.t, touch.x, touch.y))
        many = len(self.touches) > 1
        if touch in self.touches:
            self.touches.remove(touch)
        moved = math.hypot(touch.x - x0, touch.y - y0)
        if not many and moved < dp(10) and self.anim.t - t0 < 0.45 and not getattr(touch, "is_double_tap", False):
            self.vel = (0.0, 0.0)
            key = TAPS[self.tap_i % len(TAPS)]
            self.tap_i += 1
            self.play(key)
        if many:
            self.vel = (0.0, 0.0)
        return True
