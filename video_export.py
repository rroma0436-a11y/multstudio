"""Збирання MP4 на телефоні: H.264 відео + AAC звук через MediaCodec і MediaMuxer (без інтернету)."""
from kivy.utils import platform

IS_ANDROID = platform == "android"

if IS_ANDROID:
    from jnius import autoclass

    MediaCodec = autoclass("android.media.MediaCodec")
    MediaFormat = autoclass("android.media.MediaFormat")
    MediaMuxer = autoclass("android.media.MediaMuxer")
    BufferInfo = autoclass("android.media.MediaCodec$BufferInfo")

COLOR_FLEXIBLE = 0x7F420888
COLOR_SEMIPLANAR = 21
FLAG_CODEC_CONFIG = 2
FLAG_EOS = 4
TRY_AGAIN = -1
FORMAT_CHANGED = -2
BUFFERS_CHANGED = -3


def available():
    return IS_ANDROID


def rgba_to_yuv(rgba, w, h):
    """RGBA (рядки знизу вгору, як із Fbo) -> площини Y, U, V (BT.601, обмежений діапазон)."""
    import numpy as np
    a = np.frombuffer(rgba, dtype=np.uint8).reshape(h, w, 4)[::-1]
    rgb = a[..., :3].astype(np.float32)
    y = rgb @ np.array([0.2578, 0.5039, 0.0977], np.float32) + 16.5
    s = rgb.reshape(h // 2, 2, w // 2, 2, 3).mean(axis=(1, 3))
    u = s @ np.array([-0.1484, -0.2891, 0.4375], np.float32) + 128.5
    v = s @ np.array([0.4375, -0.3672, -0.0703], np.float32) + 128.5
    return y.astype(np.uint8), u.astype(np.uint8), v.astype(np.uint8)


def _padded(arr2d, row_stride, limit):
    import numpy as np
    rows, cols = arr2d.shape
    if row_stride == cols:
        data = arr2d.tobytes()
    else:
        tmp = np.zeros((rows, row_stride), dtype=np.uint8)
        tmp[:, :cols] = arr2d
        data = tmp.tobytes()
    return data[:limit]


def _interleave(a, b):
    import numpy as np
    out = np.empty((a.shape[0], a.shape[1] * 2), dtype=np.uint8)
    out[:, 0::2] = a
    out[:, 1::2] = b
    return out


class Mp4Writer:
    def __init__(self, path, width=1280, height=720, fps=24, bitrate=4_000_000,
                 pcm=None, rate=44100):
        self.path = path
        self.w, self.h, self.fps = width, height, fps
        self.bitrate = bitrate
        self.pcm = pcm            # numpy float32 моно або None
        self.rate = rate
        self.frame = 0
        self.info = BufferInfo()
        self.muxer = None
        self.started = False
        self.vtrack = self.atrack = -1
        self.audio_fmt = None
        self.audio_pos = 0
        self.audio_eos_in = False
        self.layout = None        # "planar" | "nv12" | "nv21" | "buffer"

    # ------------------------------------------------------------ запуск
    def start(self):
        fmt = MediaFormat.createVideoFormat("video/avc", self.w, self.h)
        fmt.setInteger("color-format", COLOR_FLEXIBLE)
        fmt.setInteger("bitrate", self.bitrate)
        fmt.setInteger("frame-rate", self.fps)
        fmt.setInteger("i-frame-interval", 1)
        self.venc = MediaCodec.createEncoderByType("video/avc")
        self.venc.configure(fmt, None, None, 1)
        self.venc.start()
        self.muxer = MediaMuxer(self.path, 0)
        self.aenc = None
        if self.pcm is not None and len(self.pcm):
            import numpy as np
            self.pcm16 = np.clip(self.pcm, -32768, 32767).astype("<i2").tobytes()
            afmt = MediaFormat.createAudioFormat("audio/mp4a-latm", self.rate, 1)
            afmt.setInteger("aac-profile", 2)
            afmt.setInteger("bitrate", 128000)
            afmt.setInteger("max-input-size", 16384)
            self.aenc = MediaCodec.createEncoderByType("audio/mp4a-latm")
            self.aenc.configure(afmt, None, None, 1)
            self.aenc.start()
            self._audio_until_format()

    # ------------------------------------------------------------ звук
    def _feed_audio(self, timeout=10000):
        if self.audio_eos_in:
            return
        ii = self.aenc.dequeueInputBuffer(timeout)
        if ii < 0:
            return
        buf = self.aenc.getInputBuffer(ii)
        chunk = 2048 * 2
        part = self.pcm16[self.audio_pos:self.audio_pos + chunk]
        pts = int(self.audio_pos // 2 * 1_000_000 / self.rate)
        if not part:
            self.aenc.queueInputBuffer(ii, 0, 0, pts, FLAG_EOS)
            self.audio_eos_in = True
            return
        buf.clear()
        buf.put(part)
        self.aenc.queueInputBuffer(ii, 0, len(part), pts, 0)
        self.audio_pos += len(part)

    def _audio_until_format(self):
        for _ in range(2000):
            self._feed_audio()
            oi = self.aenc.dequeueOutputBuffer(self.info, 10000)
            if oi == FORMAT_CHANGED:
                self.audio_fmt = self.aenc.getOutputFormat()
                return
            if oi >= 0:
                # дані до формату не очікуються; звільняємо буфер
                self.aenc.releaseOutputBuffer(oi, False)
        raise RuntimeError("Кодек звуку не запустився")

    def _audio_rest(self):
        for _ in range(200000):
            self._feed_audio()
            if self._drain(self.aenc, self.atrack, wait=10000) == "eos":
                return

    # ------------------------------------------------------------ відео
    def _start_muxer(self, vfmt):
        self.vtrack = self.muxer.addTrack(vfmt)
        if self.aenc is not None and self.audio_fmt is not None:
            self.atrack = self.muxer.addTrack(self.audio_fmt)
        self.muxer.start()
        self.started = True
        if self.atrack >= 0:
            self._audio_rest()

    def _drain(self, enc, track, wait=0, until_eos=False):
        tries = 0
        while True:
            oi = enc.dequeueOutputBuffer(self.info, wait)
            if oi == TRY_AGAIN:
                if not until_eos:
                    return None
                tries += 1
                if tries > 500:
                    return "eos"
                continue
            if oi == FORMAT_CHANGED:
                if enc is self.venc and not self.started:
                    self._start_muxer(enc.getOutputFormat())
                continue
            if oi == BUFFERS_CHANGED:
                continue
            if oi >= 0:
                info = self.info
                if info.size > 0 and not (info.flags & FLAG_CODEC_CONFIG) and self.started:
                    buf = enc.getOutputBuffer(oi)
                    buf.position(info.offset)
                    buf.limit(info.offset + info.size)
                    self.muxer.writeSampleData(self.vtrack if enc is self.venc else track, buf, info)
                enc.releaseOutputBuffer(oi, False)
                if info.flags & FLAG_EOS:
                    return "eos"

    def _detect_layout(self, planes):
        p1, p2 = planes[1], planes[2]
        if p1.getPixelStride() == 1:
            return "planar"
        ub, vb = p1.getBuffer(), p2.getBuffer()
        try:
            old = vb.get(0)
            ub.put(1, 55)
            if vb.get(0) == 55:
                vb.put(0, old)
                return "nv12"
        except Exception:
            pass
        return "nv21"

    def add_frame(self, rgba):
        y, u, v = rgba_to_yuv(rgba, self.w, self.h)
        ii = -1
        for _ in range(200):
            ii = self.venc.dequeueInputBuffer(10000)
            if ii >= 0:
                break
            self._drain(self.venc, self.vtrack)
        if ii < 0:
            raise RuntimeError("Кодек відео не відповідає")
        img = None
        if self.layout != "buffer":
            try:
                img = self.venc.getInputImage(ii)
            except Exception:
                img = None
        if img is not None:
            planes = img.getPlanes()
            if self.layout is None:
                self.layout = self._detect_layout(planes)
            yb = planes[0].getBuffer()
            yb.put(_padded(y, planes[0].getRowStride(), yb.remaining()))
            if self.layout == "planar":
                for pl, data in ((planes[1], u), (planes[2], v)):
                    b = pl.getBuffer()
                    b.put(_padded(data, pl.getRowStride(), b.remaining()))
            elif self.layout == "nv12":
                b = planes[1].getBuffer()
                b.put(_padded(_interleave(u, v), planes[1].getRowStride(), b.remaining()))
            else:
                b = planes[2].getBuffer()
                b.put(_padded(_interleave(v, u), planes[2].getRowStride(), b.remaining()))
        else:
            self.layout = "buffer"
            buf = self.venc.getInputBuffer(ii)
            buf.clear()
            data = y.tobytes() + _interleave(u, v).tobytes()
            buf.put(data[:buf.remaining()])
        size = self.w * self.h * 3 // 2
        pts = int(self.frame * 1_000_000 / self.fps)
        self.venc.queueInputBuffer(ii, 0, size, pts, 0)
        self.frame += 1
        self._drain(self.venc, self.vtrack)

    # ------------------------------------------------------------ завершення
    def finish(self):
        ii = -1
        for _ in range(200):
            ii = self.venc.dequeueInputBuffer(10000)
            if ii >= 0:
                break
            self._drain(self.venc, self.vtrack)
        if ii >= 0:
            pts = int(self.frame * 1_000_000 / self.fps)
            self.venc.queueInputBuffer(ii, 0, 0, pts, FLAG_EOS)
        self._drain(self.venc, self.vtrack, wait=10000, until_eos=True)
        self.close()

    def close(self):
        for enc in (getattr(self, "venc", None), getattr(self, "aenc", None)):
            if enc is None:
                continue
            try:
                enc.stop()
            except Exception:
                pass
            try:
                enc.release()
            except Exception:
                pass
        self.venc = self.aenc = None
        if self.muxer is not None:
            try:
                if self.started:
                    self.muxer.stop()
            except Exception:
                pass
            try:
                self.muxer.release()
            except Exception:
                pass
            self.muxer = None
