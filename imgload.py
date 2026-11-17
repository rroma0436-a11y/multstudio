"""Завантаження картинок у текстури з кешем.

Кадри героїв і предметів зберігаються у WebP. Якщо Kivy на телефоні не вміє читати WebP,
картинка один раз перетворюється в PNG засобами Android і далі береться з кешу.
"""
import hashlib
import os

from kivy.core.image import Image as CoreImage
from kivy.logger import Logger
from kivy.utils import platform

_cache = {}
_order = []
MAX_TEXTURES = 80
_state = {"webp": None, "cache_dir": None}


def init(cache_dir, probe_path):
    os.makedirs(cache_dir, exist_ok=True)
    _state["cache_dir"] = cache_dir
    try:
        tex = CoreImage(probe_path).texture
        _state["webp"] = tex is not None and tex.width == 4
    except Exception as e:  # noqa: BLE001
        Logger.info(f"imgload: WebP недоступний ({e})")
        _state["webp"] = False
    Logger.info(f"imgload: WebP={_state['webp']}")


def _android_png(path):
    name = hashlib.md5(path.encode("utf-8")).hexdigest() + ".png"
    out = os.path.join(_state["cache_dir"], name)
    if os.path.exists(out):
        return out
    from jnius import autoclass
    BitmapFactory = autoclass("android.graphics.BitmapFactory")
    CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
    FileOutputStream = autoclass("java.io.FileOutputStream")
    bmp = BitmapFactory.decodeFile(path)
    if bmp is None:
        raise IOError(f"Не вдалося прочитати {path}")
    tmp = out + ".tmp"
    fos = FileOutputStream(tmp)
    try:
        bmp.compress(CompressFormat.PNG, 100, fos)
    finally:
        fos.close()
        bmp.recycle()
    os.replace(tmp, out)
    return out


def real_path(path):
    if path.lower().endswith(".webp") and not _state["webp"] and platform == "android":
        return _android_png(path)
    return path


def texture(path):
    tex = _cache.get(path)
    if tex is not None:
        _order.remove(path)
        _order.append(path)
        return tex
    tex = CoreImage(real_path(path)).texture
    _cache[path] = tex
    _order.append(path)
    while len(_order) > MAX_TEXTURES:
        _cache.pop(_order.pop(0), None)
    return tex


_regions = {}


def cover(tex, aspect):
    """Частина текстури з потрібним співвідношенням сторін (обрізання по центру, як «на весь кадр»)."""
    key = (id(tex), round(aspect, 3))
    reg = _regions.get(key)
    if reg is not None and reg[0] is tex:
        return reg[1]
    tw, th = tex.size
    if tw <= 0 or th <= 0 or abs(tw / float(th) - aspect) < 0.01:
        out = tex
    elif tw / float(th) > aspect:
        w = int(th * aspect)
        out = tex.get_region((tw - w) // 2, 0, w, th)
    else:
        h = int(tw / aspect)
        out = tex.get_region(0, (th - h) // 2, tw, h)
    if len(_regions) > 40:
        _regions.clear()
    _regions[key] = (tex, out)
    return out
