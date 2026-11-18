[app]
title = Мультстудія
package.name = multstudio
package.domain = org.multstudio
source.dir = .
source.include_exts = py,png,jpg,webp,json,kv,ttf,ogg,bin
source.exclude_dirs = bin,.buildozer,.github,tests
version = 7.1
requirements = python3,kivy==2.3.1,pyjnius,numpy
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.jpg
android.presplash_color = #EFF4FF
orientation = portrait
fullscreen = 0
android.permissions = RECORD_AUDIO, (name=android.permission.WRITE_EXTERNAL_STORAGE;maxSdkVersion=28)
android.api = 34
# без цього Android 11+ «не бачить» синтезу мовлення (озвучка)
android.extra_manifest_xml = ./extra_manifest.xml
# читання кадрів анімації у потоці Android (java/FrameDecoder.java)
android.add_src = ./java
android.minapi = 26
android.accept_sdk_license = True
android.archs = arm64-v8a
android.private_storage = True
android.release_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
