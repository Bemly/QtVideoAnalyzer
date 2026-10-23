"""Low-resolution thumbnail strip covering the whole clip, one ffmpeg pass.

Mirrors ``Filmstrip.cs`` from the original WPF app.

Seeking restarts the decoder, which costs a few hundred milliseconds -- far too
slow to run on every mouse-move while the user drags a playhead. The strip
gives an instant picture for any position, so a drag only previews, and the
real (frame accurate) seek happens once, on release.

The strip is sampled at a fixed target count rather than a fixed rate, so a 30
second clip and a 3 hour clip both cost about the same memory.
"""
from __future__ import annotations

import subprocess
import threading
from typing import Callable, Optional, Union

import numpy as np

try:  # package import (`python -m qt_analyzer...`) vs bare-script import
    from .ffmpeg_locator import ffmpeg_path
except ImportError:  # pragma: no cover
    from ffmpeg_locator import ffmpeg_path  # type: ignore[no-redef]

TARGET_WIDTH = 208
TARGET_COUNT = 240
MAX_FRAMES = TARGET_COUNT + 8  # 248

CancelLike = Optional[Union[threading.Event, Callable[[], bool]]]

__all__ = ["Filmstrip"]


def _cancelled(cancel: CancelLike) -> bool:
    if cancel is None:
        return False
    if isinstance(cancel, threading.Event):
        return cancel.is_set()
    if callable(cancel):
        try:
            return bool(cancel())
        except Exception:
            return True
    is_set = getattr(cancel, "is_set", None)
    if callable(is_set):
        try:
            return bool(is_set())
        except Exception:
            return True
    return False


def _read_frame(stream, stride: int) -> bytes | None:
    """Read one fixed-size frame; None on EOF (a short tail is discarded)."""
    buf = bytearray(stride)
    mv = memoryview(buf)
    read = 0
    while read < stride:
        try:
            chunk = stream.read(stride - read)
        except Exception:
            return None
        if not chunk:
            return None
        mv[read:read + len(chunk)] = chunk
        read += len(chunk)
    return bytes(buf)


class Filmstrip:
    """Thumbnail strip: ``build()`` once, then ``at(seconds)`` is O(1)."""

    def __init__(self):
        self._frames: list[np.ndarray] = []
        self._width = 0
        self._height = 0
        self._seconds_per_thumb = 1.0
        self._duration = 0.0

    @property
    def is_ready(self) -> bool:
        return len(self._frames) > 0

    @property
    def count(self) -> int:
        return len(self._frames)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def seconds_per_thumb(self) -> float:
        """Seconds covered by one thumbnail."""
        return self._seconds_per_thumb

    def clear(self) -> None:
        self._frames = []
        self._width = self._height = 0

    def build(self, file: str, duration: float, src_w: int, src_h: int,
              cancel: CancelLike = None) -> int:
        """Decode up to 248 thumbnails covering the whole clip.

        Returns the thumbnail count (0 when nothing could be decoded).
        ``cancel`` is either ``None``, a ``threading.Event``, or a zero-arg
        callable returning True to abort.
        """
        self.clear()

        rate = 8.0
        if duration and duration > 0:
            rate = min(8.0, max(0.02, TARGET_COUNT / float(duration)))

        # The height has to be derived here rather than left to ffmpeg's "-2",
        # because every frame is read as a fixed-size block: a thumbnail that
        # comes out even slightly shorter than assumed (a 640x352 source gives
        # 114 rows, not 118) shifts every following read and the whole strip
        # turns into skewed garbage.
        w = TARGET_WIDTH
        h = max(2, round(w * max(1, int(src_h)) / max(1, int(src_w))))
        if h % 2 != 0:
            h += 1

        exe = ffmpeg_path()
        if not exe:
            return 0

        # fps resamples to the strip rate, which is what makes the thumbnail
        # index a function of time; the exact scale keeps the byte layout
        # predictable.
        args = [
            exe, "-v", "error", "-hide_banner",
            "-i", str(file), "-an",
            "-vf", f"fps={rate:.4f},scale={w}:{h}:flags=fast_bilinear",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]
        stride = w * h * 3
        frames: list[np.ndarray] = []
        proc = None
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            assert proc.stdout is not None
            stream = proc.stdout
            while len(frames) < MAX_FRAMES:
                if _cancelled(cancel):
                    break
                data = _read_frame(stream, stride)
                if data is None:
                    break
                frames.append(
                    np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3).copy())
        except Exception:
            pass
        finally:
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    if proc.stdout is not None:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass

        if not frames:
            return 0

        self._frames = frames
        self._width = w
        self._height = h
        self._duration = float(duration)
        if duration and duration > 0:
            self._seconds_per_thumb = float(duration) / len(frames)
        return len(frames)

    def at(self, seconds: float) -> np.ndarray | None:
        """Thumbnail covering ``seconds``, or None when not built."""
        if not self._frames:
            return None
        index = int(float(seconds) / max(1e-6, self._seconds_per_thumb))
        index = min(max(index, 0), len(self._frames) - 1)
        return self._frames[index]
