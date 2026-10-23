"""Sequential raw-video playback engine fed by an ffmpeg pipe.

Mirrors ``VideoPlaybackEngine.cs`` from the original WPF app: ffmpeg decodes the
clip into a raw ``rgb24`` pipe, a background reader thread fills a small pool of
reusable buffers, and the UI pulls frames on a timer. This keeps frame stepping
exact and lets the caller draw overlays on top of the picture, which a media
widget would not allow.

Seeking restarts ffmpeg with an input ``-ss``: ffmpeg seeks to the preceding key
frame and then discards up to the requested timestamp, so seeks stay fast even
in long files.

The command is codec-agnostic (theora / vp6 / vp8 / vp9 / av1 / hevc / avc /
mpeg2 / h263 all just swap the decoder inside ffmpeg). This module only emits
frames in decode order -- mapping them to frame numbers via pts is the caller's
job.
"""
from __future__ import annotations

import queue
import subprocess
import threading

import numpy as np
from PySide6.QtCore import QObject, Signal

try:  # package import (`python -m qt_analyzer...`) vs bare-script import
    from .ffmpeg_locator import ffmpeg_path
except ImportError:  # pragma: no cover
    from ffmpeg_locator import ffmpeg_path  # type: ignore[no-redef]

_POOL_SIZE = 32
_READY_CAPACITY = 24

__all__ = ["PlaybackEngine"]


def _recycle(free: queue.Queue | None, buf: bytearray) -> None:
    if free is None:
        return
    try:
        free.put_nowait(buf)
    except queue.Full:
        pass


def _read_exact(stream, buf: bytearray, n: int) -> int:
    """Fill ``buf`` with up to ``n`` bytes. Returns bytes actually read."""
    mv = memoryview(buf)
    read = 0
    while read < n:
        try:
            chunk = stream.read(n - read)
        except Exception:
            break
        if not chunk:
            break
        mv[read:read + len(chunk)] = chunk
        read += len(chunk)
    return read


class PlaybackEngine(QObject):
    """Decodes ``file`` to fixed-size rgb24 frames on a background thread.

    Usage: ``start(...)`` then poll :meth:`try_get_frame` on a UI timer.
    Buffers are auto-recycled; :meth:`return_buffer` exists only for API
    compatibility with the C# ``ReturnBuffer`` and is a no-op for the
    ``np.ndarray`` values returned here.
    """

    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gate = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._err_thread: threading.Thread | None = None
        self._free: queue.Queue | None = None
        self._ready: queue.Queue | None = None
        self._stop = threading.Event()
        self._eof = threading.Event()
        self._stderr_text = ""
        self._skip = 0
        self.width = 0
        self.height = 0
        self.start_index = 0

    @property
    def stride(self) -> int:
        return self.width * self.height * 3

    @property
    def is_running(self) -> bool:
        t = self._reader
        return t is not None and t.is_alive()

    @property
    def ended(self) -> bool:
        """True once the decoder delivered everything and the queue drained.

        The caller cannot infer this from the frame index alone: a container's
        packet table can list more frames than the decoder emits (truncated
        tail, packets carrying no picture), so "index reached the end" may
        never become true.
        """
        ready = self._ready
        return self._eof.is_set() and (ready is None or ready.empty())

    def start(self, file: str, width: int, height: int,
              start_s: float, start_index: int, seekable: bool = True) -> None:
        self.stop()

        # Decoders need even dimensions; round down like the C# version.
        w = max(2, int(width) - int(width) % 2)
        h = max(2, int(height) - int(height) % 2)
        stride = w * h * 3

        exe = ffmpeg_path()
        if not exe:
            self.failed.emit("ffmpeg was not found.")
            return

        free: queue.Queue = queue.Queue(maxsize=_POOL_SIZE)
        ready: queue.Queue = queue.Queue(maxsize=_READY_CAPACITY)
        for _ in range(_POOL_SIZE):
            free.put(bytearray(stride))

        if seekable:
            # Normal path: input seek + passthrough timestamps.
            args = [
                exe, "-v", "error", "-hide_banner",
                "-ss", f"{max(0.0, float(start_s)):.3f}",
                "-i", str(file), "-an",
                "-vf", f"scale={w}:{h}:flags=bilinear",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-fps_mode", "passthrough", "pipe:1",
            ]
            skip = 0
        else:
            # Timestamp-less raw streams (.bit etc.): -ss breaks demuxing and
            # passthrough drops every frame (no pts). Decode from 0 and skip
            # to start_index in the reader instead.
            args = [
                exe, "-v", "error", "-hide_banner",
                "-i", str(file), "-an",
                "-vf", f"scale={w}:{h}:flags=bilinear",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "pipe:1",
            ]
            try:
                skip = max(0, int(start_index))
            except Exception:
                skip = 0
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as ex:
            self.failed.emit(f"could not start ffmpeg: {ex}")
            return

        self._stop.clear()
        with self._gate:
            self.width = w
            self.height = h
            self.start_index = max(0, int(start_index))
            self._skip = skip
            self._eof.clear()
            self._stderr_text = ""
            self._proc = proc
            self._free = free
            self._ready = ready
            self._reader = threading.Thread(
                target=self._read_loop, args=(proc,),
                daemon=True, name="video-decode")
            self._err_thread = threading.Thread(
                target=self._drain_stderr, args=(proc,),
                daemon=True, name="video-stderr")
            self._err_thread.start()
            self._reader.start()

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        # A full stderr pipe would block ffmpeg and stall the feed, so it must
        # always be drained; the tail is kept for failure reports.
        try:
            assert proc.stderr is not None
            data = proc.stderr.read()
            self._stderr_text = data.decode("utf-8", "replace")[-4096:]
        except Exception:
            pass

    def _read_loop(self, proc: subprocess.Popen) -> None:
        free = self._free
        ready = self._ready
        assert free is not None and ready is not None
        assert proc.stdout is not None
        stream = proc.stdout
        stride = self.width * self.height * 3
        delivered = 0
        try:
            # Timestamp-less mode: drop the first _skip frames (input -ss
            # cannot address them), then serve sequentially from there.
            try:
                skip = max(0, int(getattr(self, "_skip", 0) or 0))
            except Exception:
                skip = 0
            self._skip = 0
            drop = bytearray(stride)
            while skip > 0 and not self._stop.is_set():
                if _read_exact(stream, drop, stride) < stride:
                    break
                skip -= 1
            while not self._stop.is_set():
                try:
                    buf = free.get(timeout=0.2)
                except queue.Empty:
                    continue
                if self._stop.is_set():
                    _recycle(free, buf)
                    break
                n = _read_exact(stream, buf, stride)
                if n < stride:
                    _recycle(free, buf)
                    # Only the live reader may report end-of-stream: a reader
                    # that was stopped exits through this same path (its
                    # process is killed and the read returns nothing), and
                    # claiming the new stream had finished would stop the
                    # transport the moment a seek restarted it.
                    if not self._stop.is_set():
                        if delivered == 0:
                            msg = self._stderr_text.strip()
                            if not msg:
                                msg = ("ffmpeg exited without decoding any "
                                       f"frame (code {proc.poll()})")
                            self.failed.emit(msg)
                        self._eof.set()
                    break
                delivered += 1
                while not self._stop.is_set():
                    try:
                        ready.put(buf, timeout=0.2)
                        break
                    except queue.Full:
                        continue
                else:
                    _recycle(free, buf)
        except Exception as ex:
            if not self._stop.is_set():
                try:
                    self.failed.emit(str(ex))
                except Exception:
                    pass

    def try_get_frame(self) -> np.ndarray | None:
        """Next decoded frame as an ``(H, W, 3)`` rgb24 ``uint8`` array, or None.

        Returns a copy; the internal buffer is recycled automatically.
        """
        ready = self._ready
        if ready is None:
            return None
        try:
            buf = ready.get_nowait()
        except queue.Empty:
            return None
        try:
            return np.frombuffer(buf, dtype=np.uint8).reshape(
                self.height, self.width, 3).copy()
        except Exception:
            return None
        finally:
            _recycle(self._free, buf)

    def return_buffer(self, buffer=None) -> None:
        """Compatibility no-op: buffers are auto-recycled in try_get_frame.

        Accepts a raw ``bytearray`` of stride length (recycled best-effort) so
        callers ported from the C# ``ReturnBuffer`` still compile; the
        ``np.ndarray`` values returned by :meth:`try_get_frame` are already
        copies and need no handling.
        """
        if isinstance(buffer, bytearray):
            if len(buffer) == self.stride and self.stride > 0:
                _recycle(self._free, buffer)

    def stop(self) -> None:
        with self._gate:
            proc = self._proc
            reader = self._reader
            err = self._err_thread
            self._proc = None
            self._reader = None
            self._err_thread = None
            self._free = None
            self._ready = None
        self._stop.set()
        me = threading.current_thread()
        if proc is not None:
            try:
                proc.kill()  # unblocks a reader stuck in stream.read()
            except Exception:
                pass
        for t in (reader, err):
            if t is not None and t.is_alive() and t is not me:
                try:
                    t.join(timeout=2.0)
                except Exception:
                    pass
        if proc is not None:
            try:
                if proc.stdout is not None:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                if proc.stderr is not None:
                    proc.stderr.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass

    def dispose(self) -> None:
        self.stop()
