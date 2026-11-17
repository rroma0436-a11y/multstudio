"""Робота з Android: збереження картинок у Галерею й надсилання.

На комп'ютері функції працюють у тестовому режимі (файл кладеться в ~/Pictures/Мультстудія).
"""
import os
import shutil

from kivy.utils import platform

IS_ANDROID = platform == "android"
GALLERY_FOLDER = "Мультстудія"

if IS_ANDROID:
    from jnius import autoclass, cast
    from android.permissions import request_permissions, check_permission

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    ContentValues = autoclass("android.content.ContentValues")
    Environment = autoclass("android.os.Environment")
    JFile = autoclass("java.io.File")
    Uri = autoclass("android.net.Uri")
    JString = autoclass("java.lang.String")
    SDK_INT = autoclass("android.os.Build$VERSION").SDK_INT
else:
    SDK_INT = 0


def _act():
    return PythonActivity.mActivity


def cs(text):
    return cast("java.lang.CharSequence", JString(text))


def needs_storage_permission():
    return IS_ANDROID and SDK_INT < 29 and not check_permission(
        "android.permission.WRITE_EXTERNAL_STORAGE")


def request_storage_permission(callback):
    """callback(granted) викликається з іншого потоку."""
    request_permissions(["android.permission.WRITE_EXTERNAL_STORAGE"],
                        lambda perms, grants: callback(bool(grants) and all(grants)))


def save_to_gallery(src_path, display_name, mime="image/png"):
    """Копіює картинку в Pictures/Мультстудія, а відео — в Movies/Мультстудія.
    Повертає Uri (Android) або шлях (ПК)."""
    video = mime.startswith("video/")
    if not IS_ANDROID:
        dest_dir = os.path.join(os.path.expanduser("~"), "Videos" if video else "Pictures", GALLERY_FOLDER)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, display_name)
        shutil.copy2(src_path, dest)
        return dest

    pictures = Environment.DIRECTORY_MOVIES if video else Environment.DIRECTORY_PICTURES
    if SDK_INT >= 29:
        Images = autoclass("android.provider.MediaStore$Video$Media" if video
                           else "android.provider.MediaStore$Images$Media")
        resolver = _act().getContentResolver()
        values = ContentValues()
        values.put("_display_name", display_name)
        values.put("mime_type", mime)
        values.put("relative_path", f"{pictures}/{GALLERY_FOLDER}")
        uri = resolver.insert(Images.EXTERNAL_CONTENT_URI, values)
        if uri is None:
            raise RuntimeError("Не вдалося створити файл у Галереї")
        pfd = resolver.openFileDescriptor(uri, "w")
        fd = pfd.detachFd()
        with open(src_path, "rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        return uri

    base = Environment.getExternalStoragePublicDirectory(pictures).getAbsolutePath()
    dest_dir = os.path.join(base, GALLERY_FOLDER)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, display_name)
    shutil.copy2(src_path, dest)
    # повідомляємо Галерею про новий файл
    try:
        MediaScanner = autoclass("android.media.MediaScannerConnection")
        MediaScanner.scanFile(_act(), [dest], [mime], None)
    except Exception:
        pass
    return dest


def share(target, mime="image/png", title="Надіслати"):
    """target — результат save_to_gallery()."""
    if not IS_ANDROID:
        return
    if isinstance(target, str):
        StrictMode = autoclass("android.os.StrictMode")
        VmPolicyBuilder = autoclass("android.os.StrictMode$VmPolicy$Builder")
        StrictMode.setVmPolicy(VmPolicyBuilder().build())
        uri = Uri.fromFile(JFile(target))
    else:
        uri = target
    intent = Intent(Intent.ACTION_SEND)
    intent.setType(mime)
    intent.putExtra(Intent.EXTRA_STREAM, cast("android.os.Parcelable", uri))
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    _act().startActivity(Intent.createChooser(intent, cs(title)))


def open_video(target):
    """Відкриває відео у вбудованому плеєрі телефону."""
    if not IS_ANDROID:
        return
    if isinstance(target, str):
        StrictMode = autoclass("android.os.StrictMode")
        VmPolicyBuilder = autoclass("android.os.StrictMode$VmPolicy$Builder")
        StrictMode.setVmPolicy(VmPolicyBuilder().build())
        uri = Uri.fromFile(JFile(target))
    else:
        uri = target
    intent = Intent(Intent.ACTION_VIEW)
    intent.setDataAndType(uri, "video/mp4")
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    _act().startActivity(intent)
