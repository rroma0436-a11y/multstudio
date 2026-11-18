"""Озвучка тексту синтезом мовлення Android (без інтернету, якщо голос установлено).

speak_to_file(текст, шлях.wav, готово(ok, тривалість|помилка), голос="normal")
Готовий WAV можна ще «перефарбувати» ефектом (мультяшний, писклявий …) — voicefx.

Важливо: з Android 11 програма мусить оголосити в маніфесті, що шукає служби синтезу мовлення
(<queries> … TTS_SERVICE), інакше телефон «не бачить» жодного голосу. Це робить
extra_manifest.xml (див. buildozer.spec → android.extra_manifest_xml).
"""
import os
import threading
import time
import wave

from kivy.clock import Clock
from kivy.utils import platform

import voicefx

IS_ANDROID = platform == "android"
GOOGLE = "com.google.android.tts"

# стан рушія: none → init → ready | failed
_S = {"tts": None, "status": "none", "engine": None, "waiters": [], "keep": [], "done": {},
      "problem": None, "lang": None, "tried_google": False, "n": 0, "timeout": None}

# що сталося, коли озвучка не вийшла (для вікна-підказки)
NO_ENGINE = "no_engine"        # на телефоні немає синтезу мовлення
NO_UKRAINIAN = "no_uk"         # синтез є, але без української мови
NO_DATA = "no_data"            # українська є, але голос ще не завантажено
FAILED = "failed"              # інша помилка


class TtsError(str):
    """Текст помилки + її вид (kind) — щоб показати правильну підказку."""

    def __new__(cls, text, kind=FAILED):
        s = str.__new__(cls, text)
        s.kind = kind
        return s


MESSAGES = {
    NO_ENGINE: "На телефоні не знайдено синтезу мовлення. Встановіть «Синтезатор мовлення Google» "
               "(Speech Services by Google) з Play Маркету.",
    NO_UKRAINIAN: "Синтез мовлення є, але без української мови. Встановіть український голос: "
                  "Налаштування → Мова й введення → Синтез мовлення → Google → Встановити голосові дані → "
                  "Українська.",
    NO_DATA: "Український голос ще не завантажено. Відкрийте «Встановити український голос» і завантажте "
             "його (потрібен інтернет лише один раз).",
    FAILED: "Не вдалося озвучити. Спробуйте ще раз або перевірте голос у налаштуваннях.",
}


def available():
    return IS_ANDROID


def _autoclass(name):
    from jnius import autoclass
    return autoclass(name)


# ---------------------------------------------------------------------- рушій
_classes = {}


def _listener_classes():
    if _classes:
        return _classes["init"], _classes["done"]
    from jnius import PythonJavaClass, java_method

    class _Init(PythonJavaClass):
        __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
        __javacontext__ = "app"

        @java_method("(I)V")
        def onInit(self, status):
            # приходить у головному потоці Android — далі працюємо в потоці Kivy
            Clock.schedule_once(lambda dt: _after_init(int(status)), 0)

    class _Done(PythonJavaClass):
        __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnUtteranceCompletedListener"]
        __javacontext__ = "app"

        @java_method("(Ljava/lang/String;)V")
        def onUtteranceCompleted(self, uid):
            ev = _S["done"].get(str(uid))
            if ev is not None:
                ev.set()

    _classes["init"], _classes["done"] = _Init, _Done
    return _Init, _Done


def _create(engine=None):
    TextToSpeech = _autoclass("android.speech.tts.TextToSpeech")
    act = _autoclass("org.kivy.android.PythonActivity").mActivity
    Init, _Done = _listener_classes()
    lst = Init()
    _S["keep"].append(lst)                    # тримаємо посилання, щоб Java не втратила слухача
    _S["status"] = "init"
    _S["engine"] = engine
    _S["tts"] = TextToSpeech(act, lst, engine) if engine else TextToSpeech(act, lst)
    if _S["timeout"] is not None:
        _S["timeout"].cancel()
    _S["timeout"] = Clock.schedule_once(_init_timeout, 12)


def _init_timeout(dt):
    if _S["status"] == "init":
        _fail(TtsError("Синтез мовлення не відповідає. Перевірте, чи встановлено «Синтезатор мовлення Google».",
                       NO_ENGINE))


def engines():
    """Назви пакетів установлених рушіїв синтезу мовлення."""
    tts = _S["tts"]
    if tts is None:
        return list(_S.get("names") or [])
    try:
        lst = tts.getEngines()
        _S["names"] = [str(lst.get(i).name) for i in range(lst.size())]
    except Exception:
        pass
    return list(_S.get("names") or [])


def _set_language(tts):
    """Увімкнути українську. Повертає код Android: ≥0 — є, -1 — не завантажено, -2 — немає."""
    Locale = _autoclass("java.util.Locale")
    best = -2
    for loc in (Locale("uk", "UA"), Locale("uk")):
        try:
            r = int(tts.isLanguageAvailable(loc))
        except Exception:
            r = -2
        if r >= 0:
            tts.setLanguage(loc)
            return r
        best = max(best, r)
    try:
        r = int(tts.setLanguage(Locale("uk", "UA")))   # деякі рушії відповідають неточно — пробуємо
    except Exception:
        r = -2
    return r if r >= 0 else best


def _after_init(status):
    if _S["status"] != "init":
        return
    tts = _S["tts"]
    names = engines()
    if status != 0:
        if GOOGLE in names and _S["engine"] != GOOGLE and not _S["tried_google"]:
            _S["tried_google"] = True
            _shutdown()
            _create(GOOGLE)
            return
        _fail(TtsError(MESSAGES[NO_ENGINE], NO_ENGINE))
        return
    code = _set_language(tts)
    if code < 0 and GOOGLE in names and _S["engine"] != GOOGLE and not _S["tried_google"]:
        # типовий рушій телефону (наприклад, Xiaomi чи Samsung) без української — пробуємо Google
        _S["tried_google"] = True
        _shutdown()
        _create(GOOGLE)
        return
    if code == -2:
        _fail(TtsError(MESSAGES[NO_UKRAINIAN], NO_UKRAINIAN))
        return
    _S["lang"] = code
    try:
        _Init, Done = _listener_classes()
        d = Done()
        _S["keep"].append(d)
        tts.setOnUtteranceCompletedListener(d)
    except Exception:
        pass                                     # тоді чекаємо, поки файл допишеться
    _S["status"] = "ready"
    _S["problem"] = None
    _flush(True)


def _shutdown():
    try:
        if _S["tts"] is not None:
            _S["tts"].shutdown()
    except Exception:
        pass
    _S["tts"] = None


def _fail(err):
    _S["status"] = "failed"
    _S["problem"] = err
    _shutdown()
    _flush(False)


def _flush(ok):
    ws, _S["waiters"] = _S["waiters"], []
    for w in ws:
        try:
            w(ok)
        except Exception:
            pass


def _ensure(on_ready):
    st = _S["status"]
    if st == "ready" and _S["tts"] is not None:
        on_ready(True)
        return
    _S["waiters"].append(on_ready)
    if st == "init":
        return
    _S["tried_google"] = False
    try:
        _create(None)
    except Exception as e:  # noqa: BLE001
        _fail(TtsError(f"Синтез мовлення недоступний ({e})", NO_ENGINE))


def reset():
    """Почати з нуля (після того, як людина встановила голос)."""
    _shutdown()
    _S["status"] = "none"
    _S["problem"] = None


def problem():
    return _S["problem"]


# ---------------------------------------------------------------------- озвучка у файл
def _clean(text):
    t = text.replace("«", "").replace("»", "").replace("“", "").replace("”", "").replace('"', "")
    return " ".join(t.split())


def speak_to_file(text, path, done, voice="normal", rate=0.95, pitch=1.1):
    """Зробити WAV з тексту. done(True, тривалість) або done(False, TtsError)."""
    text = _clean(text or "")
    if not text:
        Clock.schedule_once(lambda dt: done(False, TtsError("Немає тексту")), 0)
        return
    if not IS_ANDROID:
        Clock.schedule_once(lambda dt: done(False, TtsError("Озвучка працює лише на телефоні")), 0)
        return

    def ready(ok):
        if not ok:
            done(False, _S["problem"] or TtsError(MESSAGES[FAILED]))
            return
        tts = _S["tts"]
        try:
            File = _autoclass("java.io.File")
            Bundle = _autoclass("android.os.Bundle")
            JString = _autoclass("java.lang.String")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".raw.wav"
            if os.path.exists(tmp):
                os.remove(tmp)
            _S["n"] += 1
            uid = f"mult_{int(time.time())}_{_S['n']}"
            ev = threading.Event()
            _S["done"][uid] = ev
            tts.setSpeechRate(float(rate))
            tts.setPitch(float(pitch))
            try:
                res = tts.synthesizeToFile(JString(text), Bundle(), File(tmp), uid)
            except Exception:
                res = tts.synthesizeToFile(text, Bundle(), File(tmp), uid)
        except Exception as e:  # noqa: BLE001
            done(False, TtsError(f"Не вдалося озвучити ({e})"))
            return
        if int(res) != 0:
            kind = NO_DATA if _S["lang"] == -1 else FAILED
            done(False, TtsError(MESSAGES[kind], kind))
            return
        threading.Thread(target=_wait_and_finish, args=(uid, ev, tmp, path, voice, done), daemon=True).start()
    _ensure(ready)


def _header_ok(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"RIFF"
    except OSError:
        return False


def _wait_and_finish(uid, ev, tmp, path, voice, done):
    """Чекаємо сигнал «готово» від Android (або поки файл допишеться), потім накладаємо ефект голосу."""
    t0 = time.time()
    last, stable = -1, 0
    while time.time() - t0 < 30:
        if ev.wait(0.2):
            break
        size = os.path.getsize(tmp) if os.path.exists(tmp) else -1
        if size > 1000 and size == last and _header_ok(tmp):
            stable += 1
            if stable >= 6:            # ~1,2 с без змін і заголовок уже дописано
                break
        else:
            stable = 0
        last = size
    _S["done"].pop(uid, None)
    try:
        if not os.path.exists(tmp) or os.path.getsize(tmp) <= 44:
            kind = NO_DATA if _S["lang"] == -1 else FAILED
            raise ValueError(MESSAGES[kind])
        dur = recolor(tmp, path, voice)
        try:
            os.remove(tmp)
        except OSError:
            pass
        ok, val = True, dur
    except Exception as e:  # noqa: BLE001
        kind = NO_DATA if _S["lang"] == -1 else FAILED
        ok, val = False, TtsError(str(e) if str(e) in MESSAGES.values() else f"{MESSAGES[kind]} ({e})", kind)
    Clock.schedule_once(lambda dt: done(ok, val), 0)


def trim(x, rate, thr=0.02, keep=0.06):
    """Прибрати тишу на початку й у кінці (синтез додає паузи)."""
    import numpy as np
    if len(x) == 0:
        return x
    peak = float(np.max(np.abs(x))) or 1.0
    loud = np.nonzero(np.abs(x) > peak * thr)[0]
    if len(loud) == 0:
        return x
    k = int(rate * keep)
    return x[max(0, loud[0] - k):min(len(x), loud[-1] + k)]


def recolor(src, dst, voice):
    """Прочитати WAV (16 біт), накласти ефект голосу й записати новий WAV. Повертає тривалість."""
    import numpy as np
    with wave.open(src, "rb") as w:
        rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = w.readframes(w.getnframes())
    if sw != 2:
        raise ValueError("непідтримуваний формат звуку")
    x = np.frombuffer(data, dtype="<i2").astype(np.float64)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if len(x) < rate * 0.05:
        raise ValueError("порожній звук")
    x = trim(x, rate)
    y = voicefx.process(x, voice, rate)
    return voicefx.write_wav(dst, y, rate)


# ---------------------------------------------------------------------- допомога людині
def _start(intent):
    act = _autoclass("org.kivy.android.PythonActivity").mActivity
    Intent = _autoclass("android.content.Intent")
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    act.startActivity(intent)


def open_settings():
    """Системні налаштування синтезу мовлення."""
    if not IS_ANDROID:
        return False
    Intent = _autoclass("android.content.Intent")
    for action in ("com.android.settings.TTS_SETTINGS", "android.settings.SETTINGS"):
        try:
            _start(Intent(action))
            return True
        except Exception:
            continue
    return False


def install_voice():
    """Вікно завантаження голосів (у Google — тут і українська)."""
    if not IS_ANDROID:
        return False
    Intent = _autoclass("android.content.Intent")
    try:
        it = Intent("android.speech.tts.engine.INSTALL_TTS_DATA")
        if GOOGLE in engines() or _S["engine"] == GOOGLE:
            it.setPackage(GOOGLE)
        _start(it)
        return True
    except Exception:
        return open_settings()


def open_store():
    """Play Маркет: «Синтезатор мовлення Google»."""
    if not IS_ANDROID:
        return False
    Intent = _autoclass("android.content.Intent")
    Uri = _autoclass("android.net.Uri")
    for url in ("market://details?id=" + GOOGLE, "https://play.google.com/store/apps/details?id=" + GOOGLE):
        try:
            _start(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            return True
        except Exception:
            continue
    return False


def report():
    """Короткий опис стану для вікна перевірки."""
    if not IS_ANDROID:
        return "Озвучка працює лише на телефоні."
    names = engines()
    rows = []
    if names:
        nice = ["Google" if n == GOOGLE else n for n in names]
        rows.append("Рушії синтезу: " + ", ".join(nice))
    st = _S["status"]
    if st == "ready":
        rows.append("Українська мова: є" if (_S["lang"] or 0) >= 0 else "Українська: голос не завантажено")
    elif _S["problem"]:
        rows.append(str(_S["problem"]))
    return "\n".join(rows)
