"""Fast packet-table scan via ffprobe compact output.

Mirrors ``PacketScanService.cs`` (``ScanAsync``): ``ffprobe -show_packets``
reports each packet's size / pts / dts / flags without decoding anything, so a
full clip is scanned in well under a second. Picture type is *not* carried by
packets -- key frames (``K`` flag) are marked ``I`` here and the remaining
types are filled in later by the deep QP pass.

Codec notes (all 8 supported encoders share this one code path):

* avc / hevc / mpeg2 / theora / av1 / h263 / vp6 / vp8 / vp9 all expose the
  same ``packet=pts_time,dts_time,size,flags`` table; no per-codec branching.
* MP4 frame-level ``pkt_dts_time`` equals PTS, which would flatten the reorder
  graph -- the packet table used here carries the real decode timestamps, so
  no correction is needed.
* theora/ogv timestamps may start near 0; sorting by PTS handles that as usual.

Standard library + subprocess only (no Qt), so unit tests import it freely.
"""
from __future__ import annotations

import subprocess
from typing import Callable, Optional

try:  # imported as part of the qt_analyzer package
    from .ffmpeg_locator import ffprobe_path
    from .models import FrameInfo, PicType
except ImportError:  # imported standalone with the package dir on sys.path
    from ffmpeg_locator import ffprobe_path  # type: ignore[no-redef]
    from models import FrameInfo, PicType  # type: ignore[no-redef]


class CancelledError(Exception):
    """Raised when the caller's ``cancel`` event is set mid-scan."""


def _is_cancelled(cancel) -> bool:
    try:
        if cancel is None:
            return False
        is_set = getattr(cancel, "is_set", None)
        if callable(is_set):
            return bool(is_set())
        if callable(cancel):
            return bool(cancel())
        return bool(cancel)
    except Exception:
        return False


def _parse_double(text: str) -> float:
    try:
        return float(text.strip())
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _parse_long(text: str) -> int:
    try:
        return int(text.strip())
    except (TypeError, ValueError, AttributeError):
        return 0


def _parse_line(line: str, decode_index: int) -> Optional[FrameInfo]:
    """Parse one ``k=v|k=v...`` compact line; ``None`` when it has no size."""
    size = 0
    saw_size = False
    pts = 0.0
    dts = 0.0
    key = False
    discard = False
    corrupt = False
    for token in line.split("|"):
        name, sep, value = token.partition("=")
        if not sep:
            continue
        value = value.strip()
        if name == "size":
            size = _parse_long(value)
            saw_size = True
        elif name == "pts_time":
            pts = _parse_double(value)
        elif name == "dts_time":
            dts = _parse_double(value)
        elif name == "flags":
            # K = key frame, D = discardable, C = corrupt
            key = "K" in value
            discard = "D" in value
            corrupt = "C" in value
    if not saw_size:
        return None
    if pts < 0:
        pts = 0.0
    return FrameInfo(
        decode_index=decode_index,
        pts_time=pts,
        dts_time=dts,
        key_frame=key,
        packet_size=size,
        discard=discard,
        corrupt=corrupt,
    )


def _kill(proc: "subprocess.Popen") -> None:
    try:
        proc.kill()
    except Exception:
        pass


def scan(
    file_path: str,
    fps: float = 25.0,
    expected: int = 0,
    progress: Optional[Callable[[float], None]] = None,
    cancel=None,
    mark_result=None,
) -> list[FrameInfo]:
    """Scan the packet table of *file_path*, return frames in PTS order.

    *fps* seeds the fallback frame duration and the reorder-depth scale
    (``<= 0`` means 25). *expected* is the estimated frame count used only to
    scale *progress* reports. *progress* is ``callable(fraction)`` with
    ``fraction`` in ``0..1``. *cancel* is a ``threading.Event`` (or any
    ``is_set()`` duck-type / zero-arg callable); it is checked every 256
    packets and raises :class:`CancelledError` when set.

    Raw streams without timestamps (``pts_time=N/A``, e.g. ``.bit``) get
    synthesized ``pts=dts=index/fps`` and, when *mark_result* (an
    :class:`AnalysisResult`) is given, its ``timestamps_valid`` is set False
    so playback avoids ``-ss``/``passthrough`` on the stream.
    """
    exe = ffprobe_path()
    if not exe:
        raise RuntimeError("ffprobe was not found. Configure the ffmpeg tool folder first.")

    fps_eff = fps if isinstance(fps, (int, float)) and fps > 0 else 25.0
    fallback = 1.0 / fps_eff
    try:
        exp = float(expected or 0)
    except (TypeError, ValueError):
        exp = 0.0

    args = [exe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "packet=pts_time,dts_time,size,flags",
            "-of", "compact=p=0", "-i", file_path]

    frames: list[FrameInfo] = []
    decode_index = 0
    proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if _is_cancelled(cancel):
                _kill(proc)
                raise CancelledError("packet scan cancelled")
            line = raw.strip()
            if not line or "=" not in line:
                continue
            frame = _parse_line(line, decode_index)
            if frame is None:
                continue
            frame.duration_ms = fallback * 1000.0
            frames.append(frame)
            decode_index += 1
            if decode_index % 256 == 0 and _is_cancelled(cancel):
                _kill(proc)
                raise CancelledError("packet scan cancelled")
            if progress is not None and exp > 0 and decode_index % 512 == 0:
                try:
                    progress(min(1.0, decode_index / exp))
                except Exception:
                    pass
    finally:
        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            _kill(proc)

    if _is_cancelled(cancel):
        raise CancelledError("packet scan cancelled")
    if progress is not None:
        try:
            progress(1.0)
        except Exception:
            pass
    if not frames:
        return frames

    # ---- presentation order -------------------------------------------
    # The packet table is in decode order; graphs and transport need PTS
    # order, so sort while keeping the decode position for passes that
    # report in decode order.
    frames.sort(key=lambda f: f.pts_time)
    for i, f in enumerate(frames):
        f.index = i

    # ---- timestamp-less raw streams (.bit etc.): pts/dts all N/A -> 0 ----
    # Without this the whole clip collapses to one frame duration and ffmpeg
    # input seeking + passthrough output break. Synthesize i/fps instead.
    try:
        _span = max(f.pts_time for f in frames) - min(f.pts_time for f in frames)
    except Exception:
        _span = 0.0
    if len(frames) > 1 and _span <= 1e-6:
        for i, f in enumerate(frames):
            f.pts_time = i * fallback
            f.dts_time = i * fallback
        if mark_result is not None:
            try:
                mark_result.timestamps_valid = False
            except Exception:
                pass

    # ---- derived per-frame values --------------------------------------
    since_key = 0
    for i, f in enumerate(frames):
        if i + 1 < len(frames):
            delta = frames[i + 1].pts_time - f.pts_time
            if 0 < delta < 1.0:
                f.duration_ms = delta * 1000.0
        seconds = f.duration_ms / 1000.0
        if seconds <= 0:
            seconds = fallback
        f.bitrate_kbps = f.packet_size * 8.0 / seconds / 1000.0
        if f.key_frame:
            since_key = 0
            f.type = PicType.I  # a key frame is an intra frame
        f.gop_position = since_key
        since_key += 1
        f.reorder_delta = round((f.pts_time - f.dts_time) * fps_eff)

    return frames
