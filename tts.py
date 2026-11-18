"""Озвучка тексту вбудованим синтезом мовлення Android (без інтернету, якщо голос встановлено).

speak_to_file(текст, шлях.wav, готово(ok, тривалість|помилка), голос="normal")
Готовий WAV можна ще «перефарбувати» ефектом (мультяшний, писклявий …) — voicefx.
"""
import os
import threading
import time
import wave

from kivy.clock import Clock
from kivy.utils import platform

import voicefx

IS_ANDROID = platform == "android"
_tts = [None]
_ready = [False]
_lang_ok = [None]


def available():
    return IS_ANDROID


def _engine(on_ready):
    """Створити (один раз) рушій TextToSpeech і дочекатися, поки він готовий."""
    if _tts[0] is not None and _ready[0]:
        on_ready(True)
        return
    from jnius import PythonJavaClass, autoclass, java_method

    class _Init(PythonJavaClass):
        __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
        __javacontext__ = "app"

        @java_method("(I)V")
        def onInit(self, status):
            _ready[0] = status == 0
            Clock.schedule_once(lambda dt: on_ready(_ready[0]), 0)

    TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
    act = autoclass("org.kivy.android.PythonActivity").mActivity
    _engine.listener = _Init()            # тримаємо посилання, щоб Java не втратила слухача
    _tts[0] = TextToSpeech(act, _engine.listener)


def _set_language(tts):
    Locale = autoclass_safe("java.util.Locale")
    for loc in (Locale("uk", "UA"), Locale("uk")):
        r = tts.isLanguageAvailable(loc)
        if r >= 0:
            tts.setLanguage(loc)
            return True
    return False


def autoclass_safe(name):
    from jnius import autoclass
    return autoclass(name)


def speak_to_file(text, path, done, voice="normal"):
    """Зробити WAV з тексту. done(True, тривалість) або done(False, «чому не вийшло»)."""
    text = (text or "").strip()
    if not text:
        Clock.schedule_once(lambda dt: done(False, "Немає тексту"), 0)
        return
    if not IS_ANDROID:
        Clock.schedule_once(lambda dt: done(False, "Озвучка працює лише на телефоні"), 0)
        return

    def ready(ok):
        if not ok:
            done(False, "Синтез мовлення недоступний на цьому телефоні")
            return
        tts = _tts[0]
        if _lang_ok[0] is None:
            _lang_ok[0] = _set_language(tts)
        if not _lang_ok[0]:
            done(False, "Немає українського голосу. Встановіть його: Налаштування → Мова → Синтез мовлення → "
                        "Google → Встановити голосові дані → Українська")
            return
        File = autoclass_safe("java.io.File")
        Bundle = autoclass_safe("android.os.Bundle")
        tmp = path + ".raw.wav"
        for p in (tmp,):
            if os.path.exists(p):
                os.remove(p)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tts.setSpeechRate(0.95)
        tts.setPitch(1.1)
        res = tts.synthesizeToFile(text, Bundle(), File(tmp), "mult_" + str(int(time.time() * 1000)))
        if res != 0:
            done(False, "Не вдалося озвучити")
            return
        threading.Thread(target=_wait_and_finish, args=(tmp, path, voice, done), daemon=True).start()
    _engine(ready)


def _wait_and_finish(tmp, path, voice, done):
    """Чекаємо, поки Android допише файл (розмір перестане рости), потім накладаємо ефект голосу."""
    t0 = time.time()
    last, stable = -1, 0
    while time.time() - t0 < 20:
        size = os.path.getsize(tmp) if os.path.exists(tmp) else -1
        if size > 44 and size == last:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        last = size
        time.sleep(0.2)
    try:
        dur = recolor(tmp, path, voice)
        os.remove(tmp)
        ok, val = True, dur
    except Exception as e:  # noqa: BLE001
        ok, val = False, f"Не вдалося озвучити ({e})"
    Clock.schedule_once(lambda dt: done(ok, val), 0)


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
    y = voicefx.process(x, voice, rate)
    return voicefx.write_wav(dst, y, rate)
