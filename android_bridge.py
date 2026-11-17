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


# ---------------------------------------------------------------------- фото з телефону
REQUEST_IMAGE = 202
PHOTO_MAX = 1920
_img_cb = [None]


def pick_image(dest_dir, callback):
    """Вибір фото з Галереї. Фото зменшується (до 1920 px), повертається з урахуванням EXIF
    і зберігається як JPEG у dest_dir. callback(ім'я файлу або None) — у головному потоці."""
    from kivy.clock import Clock
    if not IS_ANDROID:
        Clock.schedule_once(lambda dt: callback(None), 0)
        return
    from android import activity
    _img_cb[0] = (dest_dir, callback)
    activity.bind(on_activity_result=_on_image)
    intent = Intent(Intent.ACTION_GET_CONTENT)
    intent.setType("image/*")
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    _act().startActivityForResult(intent, REQUEST_IMAGE)


def _on_image(request, result, intent):
    if request != REQUEST_IMAGE:
        return
    import threading
    import time
    from android import activity
    from kivy.clock import Clock
    activity.unbind(on_activity_result=_on_image)
    if _img_cb[0] is None:
        return
    dest_dir, cb = _img_cb[0]
    _img_cb[0] = None
    uri = intent.getData() if (result == -1 and intent is not None) else None
    if uri is None:
        Clock.schedule_once(lambda dt: cb(None), 0)
        return
    os.makedirs(dest_dir, exist_ok=True)
    name = time.strftime("photo_%Y%m%d_%H%M%S.jpg")
    tmp = os.path.join(dest_dir, name + ".src")
    try:
        resolver = _act().getContentResolver()
        pfd = resolver.openFileDescriptor(uri, "r")
        with os.fdopen(pfd.detachFd(), "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
    except Exception:
        Clock.schedule_once(lambda dt: cb(None), 0)
        return

    def work():
        ok = False
        try:
            _shrink_photo(tmp, os.path.join(dest_dir, name))
            ok = True
        except Exception:
            ok = False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
            try:
                from jnius import detach
                detach()
            except Exception:
                pass
        Clock.schedule_once(lambda dt: cb(name if ok else None), 0)
    threading.Thread(target=work, daemon=True).start()


def _shrink_photo(src, dst):
    BitmapFactory = autoclass("android.graphics.BitmapFactory")
    Options = autoclass("android.graphics.BitmapFactory$Options")
    Bitmap = autoclass("android.graphics.Bitmap")
    CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
    Matrix = autoclass("android.graphics.Matrix")
    FileOutputStream = autoclass("java.io.FileOutputStream")
    opts = Options()
    opts.inJustDecodeBounds = True
    BitmapFactory.decodeFile(src, opts)
    w, h = opts.outWidth, opts.outHeight
    if w <= 0 or h <= 0:
        raise IOError("Це не картинка")
    sample = 1
    while max(w, h) / (sample * 2) >= PHOTO_MAX:
        sample *= 2
    opts2 = Options()
    opts2.inSampleSize = sample
    bmp = BitmapFactory.decodeFile(src, opts2)
    if bmp is None:
        raise IOError("Не вдалося прочитати фото")
    deg = 0
    try:
        Exif = autoclass("android.media.ExifInterface")
        o = Exif(src).getAttributeInt("Orientation", 1)
        deg = {6: 90, 3: 180, 8: 270}.get(o, 0)
    except Exception:
        deg = 0
    bw, bh = bmp.getWidth(), bmp.getHeight()
    k = min(1.0, PHOTO_MAX / float(max(bw, bh)))
    if deg or k < 1.0:
        m = Matrix()
        if k < 1.0:
            m.postScale(k, k)
        if deg:
            m.postRotate(float(deg))
        out = Bitmap.createBitmap(bmp, 0, 0, bw, bh, m, True)
        if not out.equals(bmp):
            bmp.recycle()
        bmp = out
    fos = FileOutputStream(dst + ".tmp")
    try:
        bmp.compress(CompressFormat.JPEG, 90, fos)
    finally:
        fos.close()
        bmp.recycle()
    os.replace(dst + ".tmp", dst)
