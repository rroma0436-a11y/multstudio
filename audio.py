"""Звук: запис голосу, вибір файлу з телефону, прослуховування, декодування й змішування.

Усе через вбудовані засоби Android (MediaRecorder, MediaPlayer, MediaExtractor, MediaCodec).
На комп'ютері звук вимкнено (функції повертають None або нічого не роблять).
"""
import os
import shutil
import time

from kivy.utils import platform

IS_ANDROID = platform == "android"
RATE = 44100
REQUEST_AUDIO = 201

if IS_ANDROID:
    from jnius import autoclass, detach
    from android import activity as _activity
    from android.permissions import check_permission, request_permissions

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    MediaRecorder = autoclass("android.media.MediaRecorder")
    MediaPlayer = autoclass("android.media.MediaPlayer")
    MediaExtractor = autoclass("android.media.MediaExtractor")
    MediaCodec = autoclass("android.media.MediaCodec")
    BufferInfo = autoclass("android.media.MediaCodec$BufferInfo")
    ByteBuffer = autoclass("java.nio.ByteBuffer")
    Retriever = autoclass("android.media.MediaMetadataRetriever")


def available():
    return IS_ANDROID


# ---------------------------------------------------------------------- дозвіл на мікрофон
def has_mic_permission():
    return (not IS_ANDROID) or check_permission("android.permission.RECORD_AUDIO")


def request_mic_permission(callback):
    """callback(granted) — з іншого потоку."""
    request_permissions(["android.permission.RECORD_AUDIO"],
                        lambda p, g: callback(bool(g) and all(g)))


# ---------------------------------------------------------------------- запис голосу
class Recorder:
    def __init__(self):
        self.rec = None
        self.path = None
        self.t0 = 0

    def start(self, path):
        if not IS_ANDROID:
            raise RuntimeError("Запис голосу працює лише на телефоні")
        rec = MediaRecorder()
        rec.setAudioSource(1)          # MIC
        rec.setOutputFormat(2)         # MPEG_4
        rec.setAudioEncoder(3)         # AAC
        rec.setAudioChannels(1)
        rec.setAudioSamplingRate(RATE)
        rec.setAudioEncodingBitRate(96000)
        rec.setOutputFile(path)
        rec.prepare()
        rec.start()
        self.rec, self.path, self.t0 = rec, path, time.time()

    def stop(self):
        """Повертає тривалість (с) або None, якщо запис закороткий."""
        rec, self.rec = self.rec, None
        if rec is None:
            return None
        dur = time.time() - self.t0
        try:
            rec.stop()
        except Exception:
            dur = 0
        rec.release()
        if dur < 0.4:
            try:
                os.remove(self.path)
            except OSError:
                pass
            return None
        return duration(self.path) or dur

    @property
    def active(self):
        return self.rec is not None


def duration(path):
    if not IS_ANDROID:
        return None
    r = Retriever()
    try:
        r.setDataSource(path)
        ms = r.extractMetadata(9)      # METADATA_KEY_DURATION
        return int(ms) / 1000.0 if ms else None
    except Exception:
        return None
    finally:
        r.release()


# ---------------------------------------------------------------------- вибір файлу
_pick_cb = [None]


def pick_audio(dest_dir, callback):
    """Відкриває вибір звуку. callback(шлях до копії файлу або None) — у головному потоці."""
    if not IS_ANDROID:
        callback(None)
        return
    _pick_cb[0] = (dest_dir, callback)
    _activity.bind(on_activity_result=_on_result)
    intent = Intent(Intent.ACTION_GET_CONTENT)
    intent.setType("audio/*")
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    PythonActivity.mActivity.startActivityForResult(intent, REQUEST_AUDIO)


def _on_result(request, result, intent):
    if request != REQUEST_AUDIO:
        return
    _activity.unbind(on_activity_result=_on_result)
    dest_dir, cb = _pick_cb[0]
    _pick_cb[0] = None
    path = None
    if result == -1 and intent is not None and intent.getData() is not None:
        try:
            uri = intent.getData()
            resolver = PythonActivity.mActivity.getContentResolver()
            mime = resolver.getType(uri) or ""
            ext = {"audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/x-wav": ".wav", "audio/wav": ".wav",
                   "audio/ogg": ".ogg", "audio/aac": ".aac", "audio/flac": ".flac"}.get(mime, ".audio")
            os.makedirs(dest_dir, exist_ok=True)
            path = os.path.join(dest_dir, time.strftime("music_%Y%m%d_%H%M%S") + ext)
            pfd = resolver.openFileDescriptor(uri, "r")
            with os.fdopen(pfd.detachFd(), "rb") as src, open(path, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
        except Exception:
            path = None
    from kivy.clock import Clock
    Clock.schedule_once(lambda dt: cb(path), 0)


# ---------------------------------------------------------------------- прослуховування
class Playback:
    """Відтворює голоси, звуки, атмосферу й музику синхронно з переглядом мультика."""

    def __init__(self):
        self.players = []
        self.events = []      # [(час, шлях, гучність)]
        self.loops = []       # [(початок, кінець, шлях, гучність)]
        self.started = set()
        self.loop_players = {}
        self.pool = None
        self.pool_ids = {}

    def _pool_load(self, paths):
        """Короткі звуки (кроки, ефекти) — через SoundPool: без затримок і без зайвих плеєрів."""
        if not IS_ANDROID or not paths:
            return
        try:
            if self.pool is None:
                Builder = autoclass("android.media.SoundPool$Builder")
                self.pool = Builder().setMaxStreams(10).build()
            for p in paths:
                if p not in self.pool_ids and os.path.exists(p):
                    self.pool_ids[p] = self.pool.load(p, 1)
        except Exception:
            self.pool = None
            self.pool_ids = {}

    def _fire(self, path, offset, vol):
        sid = self.pool_ids.get(path)
        if sid and self.pool is not None and offset < 0.05:
            try:
                self.pool.play(sid, float(vol), float(vol), 1, 0, 1.0)
                return
            except Exception:
                pass
        self._play(path, offset, vol)

    def _play(self, path, offset=0.0, volume=1.0, loop=False):
        if not IS_ANDROID or not path or not os.path.exists(path):
            return None
        try:
            mp = MediaPlayer()
            mp.setDataSource(path)
            mp.prepare()
            if offset > 0:
                mp.seekTo(int(offset * 1000))
            mp.setVolume(float(volume), float(volume))
            mp.setLooping(bool(loop))
            mp.start()
            self.players.append(mp)
            return mp
        except Exception:
            return None

    def start(self, events, music, t0, loops=()):
        """events: [(час, шлях, гучність)], loops: [(початок, кінець, шлях, гучність)],
        music: (шлях, гучність) або None; t0 — з якого моменту."""
        self.stop()
        self.events = sorted(events, key=lambda e: e[0])
        self.loops = list(loops)
        self._pool_load({p for _, p, _ in self.events if "/assets/sounds/" in p.replace("\\", "/")})
        self.started = set()
        self.loop_players = {}
        if music and music[0]:
            mdur = duration(music[0]) or 0
            off = (t0 % mdur) if mdur > 0 else 0
            self._play(music[0], off, music[1], loop=True)
        for k, (t, path, vol) in enumerate(self.events):
            if t < t0:
                d = duration(path) or 0
                if t + d > t0:
                    self._play(path, t0 - t, vol)
                self.started.add(k)
        self.update(t0)

    def update(self, t):
        for k, (st, path, vol) in enumerate(self.events):
            if k not in self.started and st <= t:
                self.started.add(k)
                if t - st < 0.5:
                    self._fire(path, max(0.0, t - st), vol)
        for k, (a, b, path, vol) in enumerate(self.loops):
            mp = self.loop_players.get(k)
            if a <= t < b and mp is None:
                d = duration(path) or 0
                off = ((t - a) % d) if d > 0 else 0
                self.loop_players[k] = self._play(path, off, vol, loop=True) or False
            elif (t >= b or t < a) and mp:
                try:
                    mp.stop()
                except Exception:
                    pass
                self.loop_players[k] = False

    def stop(self):
        for mp in self.players:
            try:
                mp.stop()
            except Exception:
                pass
            try:
                mp.release()
            except Exception:
                pass
        self.players = []
        self.loop_players = {}

    def release(self):
        self.stop()
        if self.pool is not None:
            try:
                self.pool.release()
            except Exception:
                pass
        self.pool = None
        self.pool_ids = {}


def play_once(path):
    """Прослухати один файл (наприклад, щойно записаний голос)."""
    pb = Playback()
    pb._play(path)
    return pb


# ---------------------------------------------------------------------- декодування й змішування
def _to_bytes(arr):
    """Java byte[] (як його повертає pyjnius) -> bytes."""
    if isinstance(arr, (bytes, bytearray)):
        return bytes(arr)
    if hasattr(arr, "tostring"):
        try:
            return arr.tostring()
        except Exception:
            pass
    try:
        return bytes(arr)
    except Exception:
        return bytes((x & 0xFF) for x in arr)


def decode_pcm(path, rate=RATE):
    """Файл -> numpy int16 моно з частотою rate. Виконувати у фоновому потоці."""
    import numpy as np
    ex = MediaExtractor()
    ex.setDataSource(path)
    track, fmt = -1, None
    for i in range(ex.getTrackCount()):
        f = ex.getTrackFormat(i)
        if f.getString("mime").startswith("audio/"):
            track, fmt = i, f
            break
    if track < 0:
        ex.release()
        raise IOError("У файлі немає звуку")
    ex.selectTrack(track)
    src_rate = fmt.getInteger("sample-rate")
    channels = fmt.getInteger("channel-count")
    dec = MediaCodec.createDecoderByType(fmt.getString("mime"))
    dec.configure(fmt, None, None, 0)
    dec.start()
    info = BufferInfo()
    chunks = []
    eos_in = False
    idle = 0
    try:
        while True:
            if not eos_in:
                ii = dec.dequeueInputBuffer(10000)
                if ii >= 0:
                    buf = dec.getInputBuffer(ii)
                    n = ex.readSampleData(buf, 0)
                    if n < 0:
                        dec.queueInputBuffer(ii, 0, 0, 0, 4)
                        eos_in = True
                    else:
                        dec.queueInputBuffer(ii, 0, n, ex.getSampleTime(), 0)
                        ex.advance()
            oi = dec.dequeueOutputBuffer(info, 10000)
            if oi >= 0:
                idle = 0
                if info.size > 0:
                    ob = dec.getOutputBuffer(oi)
                    ob.position(info.offset)
                    ob.limit(info.offset + info.size)
                    tmp = ByteBuffer.allocate(info.size)
                    tmp.put(ob)
                    chunks.append(_to_bytes(tmp.array()))
                dec.releaseOutputBuffer(oi, False)
                if info.flags & 4:
                    break
            elif oi == -2:
                of = dec.getOutputFormat()
                src_rate = of.getInteger("sample-rate")
                channels = of.getInteger("channel-count")
            else:
                idle += 1
                if eos_in and idle > 300:
                    break
    finally:
        dec.stop()
        dec.release()
        ex.release()
    data = np.frombuffer(b"".join(chunks), dtype="<i2").astype(np.float32)
    if channels > 1:
        data = data[: len(data) // channels * channels].reshape(-1, channels).mean(axis=1)
    if src_rate != rate and len(data) > 1:
        n_out = int(len(data) * rate / float(src_rate))
        data = np.interp(np.linspace(0, len(data) - 1, n_out), np.arange(len(data)), data)
    return data.astype(np.float32)


def mix_track(events, music, total, rate=RATE, progress=None, loops=()):
    """Змішує голоси, звуки, атмосферу й музику в один моно-трек float32 (-32768..32767).

    events: [(час, шлях, гучність)], loops: [(початок, кінець, шлях, гучність)],
    music: (шлях, гучність) або None. Виконувати у фоновому потоці."""
    import numpy as np
    n = int(total * rate) + 1
    out = np.zeros(n, dtype=np.float32)
    cache = {}

    def pcm(path):
        if path not in cache:
            cache[path] = decode_pcm(path, rate)
        return cache[path]
    steps = len(events) + len(loops) + (1 if music else 0)
    done = [0]

    def tick():
        done[0] += 1
        if progress:
            progress(done[0] / float(max(1, steps)))
    try:
        if music and music[0] and os.path.exists(music[0]):
            m = pcm(music[0])
            if len(m):
                reps = int(np.ceil(n / float(len(m))))
                m = np.tile(m, reps)[:n] * float(music[1])
                fade = min(n, rate)
                m[-fade:] *= np.linspace(1, 0, fade)
                out += m
            tick()
        for a_t, b_t, path, vol in loops:
            if os.path.exists(path):
                v = pcm(path)
                a, b = int(a_t * rate), min(n, int(b_t * rate))
                if len(v) and b > a:
                    reps = int(np.ceil((b - a) / float(len(v))))
                    seg = np.tile(v, reps)[: b - a] * float(vol)
                    f = min(len(seg), int(0.4 * rate))
                    seg[:f] *= np.linspace(0, 1, f)
                    seg[-f:] *= np.linspace(1, 0, f)
                    out[a:b] += seg
            tick()
        for t, path, vol in events:
            if os.path.exists(path):
                v = pcm(path)
                a = int(t * rate)
                b = min(n, a + len(v))
                if b > a:
                    out[a:b] += v[: b - a] * float(vol)
            tick()
    finally:
        try:
            detach()
        except Exception:
            pass
    peak = float(np.abs(out).max()) if n else 0
    if peak > 32000:
        out *= 32000.0 / peak
    return out
