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


def _android_texture(path):
    """WebP без підтримки в Kivy: декодуємо вбудованим декодером Android прямо в текстуру
    (без збереження PNG на диск — у рази швидше, кадри дій песика не «гальмують»)."""
    from jnius import autoclass
    from kivy.graphics.texture import Texture
    BitmapFactory = autoclass("android.graphics.BitmapFactory")
    Options = autoclass("android.graphics.BitmapFactory$Options")
    Config = autoclass("android.graphics.Bitmap$Config")
    ByteBuffer = autoclass("java.nio.ByteBuffer")
    opts = Options()
    opts.inPreferredConfig = Config.ARGB_8888
    opts.inPremultiplied = False          # Kivy змішує «звичайну» прозорість
    bmp = BitmapFactory.decodeFile(path, opts)
    if bmp is None:
        raise IOError(f"Не вдалося прочитати {path}")
    try:
        w, h = bmp.getWidth(), bmp.getHeight()
        buf = ByteBuffer.allocate(w * h * 4)
        bmp.copyPixelsToBuffer(buf)       # байти R, G, B, A, рядки згори донизу
    finally:
        bmp.recycle()
    raw = _to_bytes(buf.array())
    if len(raw) != w * h * 4:
        raise IOError("неповні пікселі")
    tex = Texture.create(size=(w, h), colorfmt="rgba")
    tex.blit_buffer(raw, colorfmt="rgba", bufferfmt="ubyte")
    tex.flip_vertical()
    return tex


def _to_bytes(arr):
    if isinstance(arr, (bytes, bytearray)):
        return bytes(arr)
    if hasattr(arr, "tostring"):
        return arr.tostring()
    if hasattr(arr, "tobytes"):
        return arr.tobytes()
    try:
        return bytes(arr)
    except ValueError:                    # байти Java зі знаком (-128…127)
        import array
        return array.array("b", arr).tobytes()


_fast = {"ok": None}


def load_texture(path):
    """Нова текстура з файлу (без кешу). WebP на телефоні без підтримки — через Android."""
    if path.lower().endswith(".webp") and not _state["webp"] and platform == "android" and _fast["ok"] is not False:
        try:
            tex = _android_texture(path)
            _fast["ok"] = True
            return tex
        except Exception as e:  # noqa: BLE001
            Logger.info(f"imgload: швидке читання WebP не вдалося ({e}), перетворюю в PNG")
            _fast["ok"] = False
    return CoreImage(real_path(path)).texture


def real_path(path):
    if path.lower().endswith(".webp") and not _state["webp"] and platform == "android":
        return _android_png(path)
    return path


# ---------------------------------------------------------------------- фонове читання кадрів
class Decoder:
    """Читає картинки наперед, а текстуру створює головний потік — кадри анімації не «гальмують».

    На телефоні читає Java-потік (java/FrameDecoder.java): Python лише просить і забирає кадри з головного
    потоку (Python-потоки з Java на деяких телефонах закривали програму). На комп'ютері — потік із PIL.
    Якщо читати фоном нічим — ok=False, і кадри читаються звичайним способом."""

    def __init__(self):
        import collections
        self._mode = _decode_mode()
        self.ok = False
        self._good = 0
        self._bad = 0
        self._want = set()
        self._java = None
        if self._mode == "java":
            try:
                from jnius import autoclass
                self._java = autoclass("org.multstudio.FrameDecoder")()
                self.ok = True
            except Exception as e:  # noqa: BLE001
                Logger.info(f"imgload: Java-читач недоступний ({e})")
                self._mode = None
        elif self._mode == "pil":
            import threading
            self._q = collections.deque()
            self._done = collections.deque()
            self._lock = threading.Lock()
            self._wake = threading.Event()
            self.ok = True
            threading.Thread(target=self._run, daemon=True).start()

    @property
    def mode(self):
        return self._mode if self.ok else None

    def request(self, path, urgent=False):
        if not self.ok:
            return
        if self._mode == "java":
            if path in self._want and not urgent:
                return
            self._want.add(path)
            try:
                self._java.request(path, bool(urgent))
            except Exception as e:  # noqa: BLE001
                Logger.warning(f"imgload: Java-читач зламався ({e})")
                self.ok = False
            return
        with self._lock:
            if path in self._want:
                if urgent:
                    try:
                        self._q.remove(path)
                    except ValueError:
                        return
                    self._q.appendleft(path)
                return
            self._want.add(path)
            if urgent:
                self._q.appendleft(path)
            else:
                self._q.append(path)
        self._wake.set()

    def pending(self, path):
        return path in self._want

    def cancel_all(self):
        if self._mode == "java":
            try:
                self._java.cancelAll()
            except Exception:  # noqa: BLE001
                pass
            self._want.clear()        # те, що вже читається, однаково прийде через poll
            return
        with self._lock:
            for p in self._q:
                self._want.discard(p)
            self._q.clear()

    def poll(self, limit=4):
        """[(шлях, текстура)] — готові кадри (викликати з головного потоку)."""
        out = []
        if not self.ok:
            return out
        while len(out) < limit:
            if self._mode == "java":
                try:
                    if not self._java.poll():
                        break
                    path = self._java.getPath()
                    w, h = self._java.getWidth(), self._java.getHeight()
                    px = self._java.getPixels()
                    raw = _to_bytes(px) if px is not None else None
                except Exception as e:  # noqa: BLE001
                    Logger.warning(f"imgload: Java-читач зламався ({e})")
                    self.ok = False
                    break
            else:
                if not self._done:
                    break
                path, w, h, raw = self._done.popleft()
                with self._lock:
                    pass
            self._want.discard(path)
            if raw is None or len(raw) != w * h * 4:
                self._bad += 1
                if self._bad >= 3 and self._good == 0:
                    Logger.warning("imgload: фонове читання не працює, вимикаю")
                    self.ok = False
                out.append((path, None))
                continue
            try:
                from kivy.graphics.texture import Texture
                tex = Texture.create(size=(w, h), colorfmt="rgba")
                tex.blit_buffer(raw, colorfmt="rgba", bufferfmt="ubyte")
                tex.flip_vertical()
                self._good += 1
                out.append((path, tex))
            except Exception:  # noqa: BLE001
                out.append((path, None))
        return out

    def _run(self):
        while True:
            self._wake.wait(0.5)
            while True:
                with self._lock:
                    if not self._q:
                        self._wake.clear()
                        break
                    path = self._q.popleft()
                try:
                    w, h, raw = self._decode(path)
                except Exception:  # noqa: BLE001
                    w = h = 0
                    raw = None
                self._done.append((path, w, h, raw))

    def _decode(self, path):
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            im = im.convert("RGBA")
            return im.width, im.height, im.tobytes()


def _decode_mode():
    if platform == "android":
        return "java"
    try:
        import PIL.Image  # noqa: F401
        return "pil"
    except Exception:  # noqa: BLE001
        return None


_decoder = [None]
_named = {}
THREADS = {"on": True}       # безпечний режим вимикає фонові потоки


def decoder(name=None):
    """Фоновий читач кадрів (окремий для кожного name). None — якщо потоки вимкнено."""
    if not THREADS["on"]:
        return None
    if name is None:
        if _decoder[0] is None:
            _decoder[0] = Decoder()
        return _decoder[0]
    if name not in _named:
        _named[name] = Decoder()
    return _named[name]


def texture(path):
    tex = _cache.get(path)
    if tex is not None:
        _order.remove(path)
        _order.append(path)
        return tex
    tex = load_texture(path)
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
