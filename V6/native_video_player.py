"""
Player de vídeo/áudio nativo (sem VLC).
Decodificação com PyAV (FFmpeg) e áudio com sounddevice.
"""

import queue
import threading
import time

import numpy as np
import av
import sounddevice as sd
from PIL import Image


class NativeVideoPlayer:
    SAMPLE_RATE = 44100
    CHANNELS = 2
    VIDEO_QUEUE_MAX = 90
    AUDIO_QUEUE_MAX = 400

    def __init__(self):
        self.on_finished = None

        self._container = None
        self._vstream = None
        self._astream = None
        self._decode_thread = None
        self._sd_stream = None
        self._resampler = None
        self._demuxer = None

        self._vq = queue.Queue(maxsize=self.VIDEO_QUEUE_MAX)
        self._aq = queue.Queue(maxsize=self.AUDIO_QUEUE_MAX)
        self._lock = threading.RLock()
        self._pending = None
        self._cur_chunk = None

        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()
        self._pause_flag.set()
        self._seek_target = None
        self._decode_done = False

        self._loaded = False
        self._playing = False
        self._paused = False
        self._finished = False

        self._has_audio = False
        self._duration = 0.0
        self._samples_played = 0
        self._vol = 0.8

        self._clock_mode = "video"
        self._v_clock_base = 0.0
        self._v_clock_t0 = 0.0

    # ---------------- estado ----------------

    def is_loaded(self):
        return self._loaded

    def is_playing(self):
        self._check_finished()
        return self._playing and not self._paused and not self._finished

    def is_paused(self):
        self._check_finished()
        return self._playing and self._paused

    def is_finished(self):
        self._check_finished()
        return self._finished

    def get_duration(self):
        return self._duration

    def get_position(self):
        self._check_finished()
        with self._lock:
            if self._finished:
                return self._duration
            if not self._loaded:
                return 0.0

            if self._has_audio and not self._audio_drained():
                self._clock_mode = "audio"
                pos = self._samples_played / float(self.SAMPLE_RATE)
            else:
                if self._clock_mode != "video":
                    if self._has_audio:
                        self._v_clock_base = (
                            self._samples_played / float(self.SAMPLE_RATE)
                        )
                    else:
                        self._v_clock_base = 0.0
                    self._v_clock_t0 = time.monotonic()
                    self._clock_mode = "video"

                if self._paused or not self._playing:
                    pos = self._v_clock_base
                else:
                    pos = self._v_clock_base + (time.monotonic() - self._v_clock_t0)

            if self._duration > 0:
                pos = min(pos, self._duration)
            return pos

    def get_position_fraction(self):
        if self._duration <= 0:
            return 0.0
        return max(0.0, min(1.0, self.get_position() / self._duration))

    def get_volume(self):
        return int(round(self._vol * 100))

    def set_volume(self, volume):
        self._vol = max(0.0, min(100.0, float(volume))) / 100.0

    def _audio_drained(self):
        if not self._decode_done:
            return False
        if not self._aq.empty():
            return False
        return self._cur_chunk is None or len(self._cur_chunk) == 0

    # ---------------- controle ----------------

    def load(self, path):
        self.stop()

        container = av.open(path)
        if not container.streams.video and not container.streams.audio:
            container.close()
            raise ValueError("Arquivo sem streams de vídeo/áudio")

        vstream = None
        astream = None
        if container.streams.video:
            vstream = container.streams.video[0]
            vstream.thread_type = "AUTO"
        if container.streams.audio:
            astream = container.streams.audio[0]
            astream.thread_type = "AUTO"

        duration = 0.0
        if container.duration is not None and container.duration > 0:
            duration = float(container.duration) / float(av.time_base)
        elif vstream is not None and vstream.duration and vstream.time_base:
            duration = float(vstream.duration * vstream.time_base)
        elif astream is not None and astream.duration and astream.time_base:
            duration = float(astream.duration * astream.time_base)

        with self._lock:
            self._container = container
            self._vstream = vstream
            self._astream = astream
            self._has_audio = astream is not None
            self._duration = max(0.0, duration)
            self._samples_played = 0
            self._v_clock_base = 0.0
            self._v_clock_t0 = 0.0
            self._clock_mode = "audio" if astream is not None else "video"
            self._pending = None
            self._cur_chunk = None
            self._loaded = True
            self._playing = False
            self._paused = False
            self._finished = False
            self._decode_done = False

        if self._has_audio:
            self._resampler = av.AudioResampler(
                format="fltp", layout="stereo", rate=self.SAMPLE_RATE
            )

        self._drain_queue(self._vq)
        self._drain_queue(self._aq)

    def play(self):
        if not self._loaded:
            raise RuntimeError("Nenhum vídeo carregado")
        if self._playing and not self._paused:
            return
        if self._finished:
            return

        if self._paused:
            self.resume()
            return

        self._stop_flag.clear()
        self._pause_flag.set()
        self._playing = True
        self._paused = False
        self._decode_done = False
        self._seek_target = None

        if self._has_audio:
            try:
                self._start_audio()
            except Exception:
                self._has_audio = False
                self._astream = None

        with self._lock:
            if self._has_audio:
                self._clock_mode = "audio"
            else:
                self._clock_mode = "video"
                self._v_clock_base = 0.0
                self._v_clock_t0 = time.monotonic()

        self._decode_thread = threading.Thread(
            target=self._decode_loop, name="NativeVideoDecode", daemon=True
        )
        self._decode_thread.start()

    def pause(self):
        if not self._playing or self._paused:
            return
        self._paused = True
        self._pause_flag.clear()
        with self._lock:
            if not self._has_audio and self._clock_mode == "video":
                self._v_clock_base = self._v_clock_base + (
                    time.monotonic() - self._v_clock_t0
                )

    def resume(self):
        if not self._playing or not self._paused:
            return
        self._paused = False
        with self._lock:
            if not self._has_audio and self._clock_mode == "video":
                self._v_clock_t0 = time.monotonic()
        self._pause_flag.set()

    def stop(self):
        self._stop_flag.set()
        self._seek_target = None
        self._pause_flag.set()

        thread = self._decode_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._decode_thread = None

        stream = self._sd_stream
        self._sd_stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

        with self._lock:
            container = self._container
            self._container = None
            self._demuxer = None
            self._pending = None
            self._cur_chunk = None
            self._loaded = False
            self._playing = False
            self._paused = False
            self._finished = False
            self._decode_done = False

        self._drain_queue(self._vq)
        self._drain_queue(self._aq)

        if container is not None:
            try:
                container.close()
            except Exception:
                pass

    def seek_fraction(self, frac):
        if not self._loaded or self._duration <= 0:
            return
        target = max(0.0, min(float(frac), 0.999)) * self._duration
        self._seek_target = target

    # ---------------- frames para a UI ----------------

    def get_ready_frame(self):
        self._check_finished()
        if not self._loaded or self._finished:
            return None
        if self._paused:
            return None

        clock = self.get_position()
        audio_done = self._audio_drained()

        with self._lock:
            while True:
                if self._pending is None:
                    try:
                        self._pending = self._vq.get_nowait()
                    except queue.Empty:
                        return None

                pts, img = self._pending

                if audio_done or pts is None:
                    self._pending = None
                    return img

                if pts > clock + 0.10:
                    return None

                self._pending = None
                if pts < clock - 0.35:
                    continue
                return img

    def _check_finished(self):
        if self._finished or not self._playing or self._paused:
            return
        if not self._decode_done:
            return
        with self._lock:
            v_empty = self._vq.empty() and self._pending is None
            a_empty = not self._has_audio or (
                self._aq.empty()
                and (self._cur_chunk is None or len(self._cur_chunk) == 0)
            )
        if not (v_empty and a_empty):
            return

        self._finished = True
        self._playing = False
        self._paused = False
        callback = self.on_finished
        if callback is not None:
            try:
                callback()
            except Exception:
                pass

    # ---------------- decode ----------------

    def _decode_loop(self):
        try:
            container = self._container
            if container is None:
                return
            demuxer = container.demux()
            eof_reached = False

            while not self._stop_flag.is_set():
                if self._seek_target is not None:
                    target = self._seek_target
                    self._seek_target = None
                    self._apply_seek(target)
                    demuxer = container.demux()
                    eof_reached = False
                    self._decode_done = False
                    continue

                if eof_reached:
                    time.sleep(0.05)
                    continue

                if not self._pause_flag.is_set():
                    time.sleep(0.02)
                    continue

                if self._vq.qsize() >= self.VIDEO_QUEUE_MAX - 2 or (
                    self._has_audio and self._aq.qsize() >= self.AUDIO_QUEUE_MAX - 2
                ):
                    time.sleep(0.02)
                    continue

                try:
                    packet = next(demuxer)
                except StopIteration:
                    eof_reached = True
                    self._decode_done = True
                    continue
                except av.FFmpegError:
                    eof_reached = True
                    self._decode_done = True
                    continue

                if packet is None:
                    continue

                stream = packet.stream
                try:
                    if self._vstream is not None and stream is self._vstream:
                        frames = packet.decode()
                    elif (
                        self._has_audio
                        and self._astream is not None
                        and stream is self._astream
                    ):
                        frames = packet.decode()
                    else:
                        continue
                except av.FFmpegError:
                    continue

                for frame in frames:
                    if self._stop_flag.is_set():
                        return
                    if self._seek_target is not None:
                        break

                    if self._vstream is not None and stream is self._vstream:
                        try:
                            img, pts = self._video_frame_to_image(frame)
                        except Exception:
                            continue
                        if not self._put(self._vq, (pts, img)):
                            break
                    else:
                        try:
                            chunks = self._audio_frame_to_chunks(frame)
                        except Exception:
                            continue
                        for chunk in chunks:
                            if not self._put(self._aq, chunk):
                                break
        except Exception:
            pass
        finally:
            self._decode_done = True

    def _put(self, q, item):
        while not self._stop_flag.is_set():
            if self._seek_target is not None:
                return False
            try:
                q.put(item, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def _apply_seek(self, target):
        with self._lock:
            self._drain_queue(self._vq)
            self._drain_queue(self._aq)
            self._pending = None
            self._cur_chunk = None

        container = self._container
        if container is None:
            return

        offset = int(target * float(av.time_base))
        try:
            container.seek(offset)
        except Exception:
            pass

        for stream in (self._vstream, self._astream):
            if stream is None:
                continue
            try:
                stream.codec_context.flush_buffers()
            except Exception:
                pass

        if self._has_audio:
            self._resampler = av.AudioResampler(
                format="fltp", layout="stereo", rate=self.SAMPLE_RATE
            )
            with self._lock:
                self._samples_played = int(target * self.SAMPLE_RATE)
                self._clock_mode = "audio"
        else:
            with self._lock:
                self._v_clock_base = target
                self._v_clock_t0 = time.monotonic()
                self._clock_mode = "video"

    def _video_frame_to_image(self, frame):
        pts = None
        if frame.pts is not None and frame.time_base is not None:
            pts = float(frame.pts * frame.time_base)
        elif frame.pts is not None and self._vstream is not None:
            pts = float(frame.pts * self._vstream.time_base)

        rgb = frame.reformat(format="rgb24")
        arr = rgb.to_ndarray()
        return Image.fromarray(arr), pts

    def _audio_frame_to_chunks(self, frame):
        resampled = self._resampler.resample(frame)
        if resampled is None:
            return []
        if isinstance(resampled, av.AudioFrame):
            resampled = [resampled]

        chunks = []
        for nf in resampled:
            arr = nf.to_ndarray()
            if getattr(nf.format, "is_planar", False):
                arr = arr.T
            if arr.ndim == 1:
                arr = arr.reshape(-1, self.CHANNELS)
            if arr.dtype != np.float32:
                arr = arr.astype(np.float32, copy=False)
            if arr.shape[1] == 1:
                arr = np.repeat(arr, self.CHANNELS, axis=1)
            elif arr.shape[1] != self.CHANNELS:
                arr = arr[:, : self.CHANNELS]
            if arr.size:
                chunks.append(np.ascontiguousarray(arr))
        return chunks

    # ---------------- áudio ----------------

    def _start_audio(self):
        self._sd_stream = sd.OutputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype="float32",
            callback=self._audio_callback,
            blocksize=1024,
        )
        self._sd_stream.start()

    def _audio_callback(self, outdata, frames, time_info, status):
        try:
            outdata.fill(0)
            if self._paused or not self._playing:
                return
            filled = 0
            with self._lock:
                while filled < frames:
                    if self._cur_chunk is None or len(self._cur_chunk) == 0:
                        try:
                            self._cur_chunk = self._aq.get_nowait()
                        except queue.Empty:
                            self._cur_chunk = None
                            break
                    take = min(len(self._cur_chunk), frames - filled)
                    outdata[:take] = self._cur_chunk[:take]
                    self._cur_chunk = self._cur_chunk[take:]
                    filled += take
                self._samples_played += filled
                vol = self._vol
            if filled and vol != 1.0:
                outdata[:filled] *= vol
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass

    @staticmethod
    def _drain_queue(q):
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                break
