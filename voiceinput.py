"""Голосовий ввід: дитина каже, що робить песик, — телефон перетворює мову на текст.

Використовується вбудоване розпізнавання мовлення Android (вікно Google «Говоріть»), українською.
Дозвіл на мікрофон програмі не потрібен: слухає застосунок Google.
"""
from kivy.clock import Clock
from kivy.utils import platform

IS_ANDROID = platform == "android"
REQUEST_SPEECH = 303
_cb = [None]

MESSAGES = {
    "none": "На телефоні немає голосового вводу. Встановіть або оновіть застосунок «Google» "
            "і в ньому увімкніть «Голосовий пошук» (українська мова).",
    "failed": "Не вдалося запустити голосовий ввід. Спробуйте ще раз.",
    "empty": "Не почув слів. Натисніть мікрофон і скажіть ще раз.",
    "desktop": "Голосовий ввід працює лише на телефоні.",
}


def _intent(prompt):
    from jnius import autoclass
    Intent = autoclass("android.content.Intent")
    RI = autoclass("android.speech.RecognizerIntent")
    it = Intent(RI.ACTION_RECOGNIZE_SPEECH)
    it.putExtra(RI.EXTRA_LANGUAGE_MODEL, RI.LANGUAGE_MODEL_FREE_FORM)
    it.putExtra(RI.EXTRA_LANGUAGE, "uk-UA")
    it.putExtra("android.speech.extra.LANGUAGE_PREFERENCE", "uk-UA")
    if prompt:
        it.putExtra(RI.EXTRA_PROMPT, prompt)
    return it


def available():
    """Чи є на телефоні, кому розпізнавати мову (None — невідомо)."""
    if not IS_ANDROID:
        return False
    try:
        from jnius import autoclass
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        lst = act.getPackageManager().queryIntentActivities(_intent(""), 0)
        return lst is not None and lst.size() > 0
    except Exception:  # noqa: BLE001
        return None


def listen(on_text, on_error=None, prompt="Скажи, що робить песик"):
    """Відкриває вікно «Говоріть». on_text(текст) / on_error(ключ MESSAGES) — у головному потоці."""
    def err(key):
        if on_error:
            Clock.schedule_once(lambda dt: on_error(key), 0)
    if not IS_ANDROID:
        err("desktop")
        return
    try:
        from android import activity
        from jnius import autoclass
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        _cb[0] = (on_text, err)
        activity.unbind(on_activity_result=_on_result)
        activity.bind(on_activity_result=_on_result)
        act.startActivityForResult(_intent(prompt), REQUEST_SPEECH)
    except Exception as e:  # noqa: BLE001
        _cb[0] = None
        name = type(e).__name__ + str(e)
        err("none" if "ActivityNotFound" in name or "No Activity" in name else "failed")


def _on_result(request, result, data):
    if request != REQUEST_SPEECH:
        return
    try:
        from android import activity
        activity.unbind(on_activity_result=_on_result)
    except Exception:  # noqa: BLE001
        pass
    cb = _cb[0]
    _cb[0] = None
    if cb is None:
        return
    on_text, err = cb
    if result != -1 or data is None:          # RESULT_OK = -1; «Назад» — нічого не робимо
        return
    text = ""
    try:
        from jnius import autoclass
        RI = autoclass("android.speech.RecognizerIntent")
        found = data.getStringArrayListExtra(RI.EXTRA_RESULTS)
        if found is not None and found.size() > 0:
            text = str(found.get(0) or "")
    except Exception:  # noqa: BLE001
        text = ""
    text = tidy(text)
    if not text:
        err("empty")
        return
    Clock.schedule_once(lambda dt: on_text(text), 0)


def tidy(text):
    """Розпізнаний текст → речення: велика літера, крапка в кінці."""
    t = " ".join((text or "").split())
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    if t[-1] not in ".!?…»":
        t += "."
    return t
