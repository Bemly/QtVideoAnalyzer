"""Motion deep pass: native ``-debug mv`` vectors, else Farneback estimate.

Mirrors DeepAnalysisService.RunMotionPassAsync + MotionEstimator.RunAsync
(simplified to a prev->cur Farneback match; vectors reported in source
pixels, field kept per frame for the overlay). Deps: numpy +
opencv-python-headless + stdlib.
"""
from __future__ import annotations

import asyncio
import math
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from . import ffmpeg_locator
    from .models import AnalysisResult, MotionField, PicType
except ImportError:  # flat-script import from inside qt_analyzer/
    import ffmpeg_locator  # type: ignore
    from models import AnalysisResult, MotionField, PicType  # type: ignore

try:  # package vs. flat-script import
    from .block import blockiness
except ImportError:  # pragma: no cover
    try:
        from qt_analyzer.block import blockiness  # type: ignore
    except ImportError:
        from block import blockiness  # type: ignore

_MV_RX = re.compile(r"mv[^\d-]*(-?\d+)[^\d-]+(-?\d+)", re.IGNORECASE)
_NEW_FRAME_RX = re.compile(r"New frame, type:\s*(\w)")

_SMALL_W = 320
_BLOCK = 8


# ---------------------------------------------------------------- slice (copy of deep_qp helper)

def _slice_of(result: AnalysisResult, from_s: float, to_s: float) -> dict:
    n = len(result.frames)
    if n == 0:
        return {"first": 0, "last": -1, "decode_offset": 0, "first_decode": 0,
                "start": 0.0, "end": 0.0, "ranged": False, "length": 0.0}
    duration = result.duration_seconds
    end = min(to_s, duration) if to_s > 0 else duration
    start = min(max(from_s, 0.0), max(0.0, end - 0.04))
    if end - start < 0.05:
        end = min(duration, start + 0.05)
    last = n - 1
    first = min(max(result.index_at(start), 0), last)
    last_index = min(max(result.index_at(end), first), last)
    key = first
    while key > 0 and not result.frames[key].key_frame:
        key -= 1
    decode_offset = max(0, result.frames[key].decode_index)
    first_decode = max(0, result.frames[first].decode_index)
    ranged = (from_s > 0.01) or (to_s > 0)
    length = max(0.0, end - start)
    return {"first": first, "last": last_index, "decode_offset": decode_offset,
            "first_decode": first_decode, "start": start, "end": end,
            "ranged": ranged, "length": length}


def _report(progress, stage: str, frac: float) -> None:
    if progress is None:
        return
    try:
        progress(stage, frac)
    except TypeError:
        try:
            progress(frac)
        except TypeError:
            pass


def _cancelled(cancel) -> bool:
    if cancel is None:
        return False
    is_set = getattr(cancel, "is_set", None)
    if callable(is_set):
        try:
            return bool(is_set())
        except Exception:
            return False
    if callable(cancel):
        try:
            return bool(cancel())
        except Exception:
            return False
    return False


# ---------------------------------------------------------------- probe

def probe_motion_vectors(file_path: str, cancel=None) -> bool:
    """True only when a real ``mv=x,y``-style vector pair is decoded.

    A plain substring match on "mv" misfires on h264's
    "Undefined constant or missing '(' in 'mv'" error text, hence the regex.
    """
    exe = ffmpeg_locator.ffmpeg_path()
    if not exe:
        return False
    if _cancelled(cancel):
        raise asyncio.CancelledError()
    try:
        p = subprocess.run(
            [exe, "-v", "debug", "-hide_banner", "-debug", "mv",
             "-i", file_path, "-t", "1", "-an", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, errors="ignore", timeout=60)
        for line in (p.stderr or "").splitlines():
            if _MV_RX.search(line):
                return True
        return False
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


# ---------------------------------------------------------------- native pass

def _run_mv_pass(result: AnalysisResult, sl: dict, progress=None, cancel=None) -> bool:
    exe = ffmpeg_locator.ffmpeg_path()
    if not exe:
        return False
    args = ["-v", "debug", "-hide_banner", "-debug", "mv"]
    if sl["start"] > 0.01:
        args += ["-ss", f"{sl['start']:.3f}"]
    args += ["-i", result.media.file_path]
    if sl["ranged"]:
        args += ["-t", f"{sl['length']:.3f}"]
    args += ["-an", "-f", "null", "-"]

    per_frame: list[tuple[float, float, int, int]] = []
    s = 0.0
    mx = 0.0
    fwd = bwd = cnt = 0
    started = False

    proc = subprocess.Popen([exe] + args, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True, errors="ignore",
                            bufsize=1)
    try:
        assert proc.stderr is not None
        for line in proc.stderr:
            if _cancelled(cancel):
                try:
                    proc.kill()
                except Exception:
                    pass
                raise asyncio.CancelledError()
            if _NEW_FRAME_RX.search(line):
                if started:
                    per_frame.append((s / cnt if cnt else 0.0, mx, fwd, bwd))
                started = True
                s = 0.0
                mx = 0.0
                fwd = bwd = cnt = 0
                if len(per_frame) % 32 == 0:
                    total = max(1, len(result.frames))
                    _report(progress, "Extracting motion vectors…",
                            min(0.99, len(per_frame) / total))
                continue
            for mv in _MV_RX.finditer(line):
                try:
                    x = float(mv.group(1))
                    y = float(mv.group(2))
                except ValueError:
                    continue
                ln = math.hypot(x, y)
                s += ln
                cnt += 1
                if ln > mx:
                    mx = ln
                if x >= 0:
                    fwd += 1
                else:
                    bwd += 1
    finally:
        try:
            proc.wait(timeout=30)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if started:
        per_frame.append((s / cnt if cnt else 0.0, mx, fwd, bwd))

    if not per_frame:
        return False
    # per_frame[0] is the key frame the decoder started from; file decode
    # indices are shifted by that much before indexing into it.
    any_written = False
    for f in result.frames:
        local = f.decode_index - sl["decode_offset"]
        if f.decode_index >= 0 and 0 <= local < len(per_frame):
            mean, peak, fw, bw = per_frame[local]
            f.motion_mean = mean
            f.motion_max = peak
            f.motion_fwd = fw
            f.motion_bwd = bw
            f.motion_count = fw + bw
            any_written = True
    return any_written


# ---------------------------------------------------------------- estimate fallback

def _decode_avs3_yuv(media, progress=None, cancel=None) -> str | None:
    """Full uavs3dec pass to a temp yuv420 file. Caller deletes it."""
    import os as _os
    import subprocess as _sp
    import tempfile as _tf
    try:
        from .probe import _uavs3dec_path  # type: ignore
    except ImportError:
        try:
            from probe import _uavs3dec_path  # type: ignore
        except ImportError:
            return None
    exe = _uavs3dec_path()
    if not exe:
        return None
    try:
        w, h = int(media.width or 0), int(media.height or 0)
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    _report(progress, "Decoding AVS3 (uavs3dec)…", 0.02)
    try:
        fd, tmp = _tf.mkstemp(suffix=".yuv")
        _os.close(fd)
    except Exception:
        return None
    try:
        if _cancelled(cancel):
            raise asyncio.CancelledError()
        p = _sp.run([exe, "-i", media.file_path, "-o", tmp, "-l", "0"],
                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, timeout=3600)
        if p.returncode != 0 or not _os.path.isfile(tmp):
            try:
                if _os.path.isfile(tmp):
                    _os.remove(tmp)
            except OSError:
                pass
            return None
        return tmp
    except asyncio.CancelledError:
        try:
            if _os.path.isfile(tmp):
                _os.remove(tmp)
        except OSError:
            pass
        raise
    except Exception:
        try:
            if _os.path.isfile(tmp):
                _os.remove(tmp)
        except OSError:
            pass
        return None


def _run_estimate(result: AnalysisResult, sl: dict, progress=None, cancel=None) -> None:
    import numpy as np

    exe = ffmpeg_locator.ffmpeg_path()
    if not exe:
        return
    media = result.media
    frames = result.frames
    if not frames:
        return
    small_w = _SMALL_W
    small_h = max(2, round(media.height * small_w / max(1, media.width)))
    if small_h % 2 != 0:
        small_h += 1
    scale = media.width / float(small_w) if small_w else 1.0
    if not (scale > 0):
        scale = 1.0
    first = max(0, sl["first"])
    last = min(sl["last"], len(frames) - 1)
    if last < first:
        return

    buf_size = small_w * small_h
    grays: list[bytes] = []
    tmp_yuv: str | None = None
    try:
        codec = str(getattr(media, "video_codec", "") or "").lower()
    except Exception:
        codec = ""
    avs3_src: str | None = None
    if codec in ("avs3", "avs", "avs3-p2"):
        # ffmpeg cannot decode AVS3 at all: full uavs3dec pass to yuv,
        # then the same ffmpeg scale-to-gray pipe reads the yuv file.
        avs3_src = _decode_avs3_yuv(media, progress, cancel)
        if avs3_src is None:
            return
        tmp_yuv = avs3_src

    if avs3_src is not None:
        args = ["-v", "error", "-hide_banner", "-f", "rawvideo",
                "-s", f"{media.width}x{media.height}", "-pix_fmt", "yuv420p",
                "-i", avs3_src, "-an", "-vf",
                f"scale={small_w}:{small_h}:flags=fast_bilinear,format=gray",
                "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    else:
        args = ["-v", "error", "-hide_banner"]
        if sl["start"] > 0.01:
            args += ["-ss", f"{sl['start']:.3f}"]
        args += ["-i", media.file_path]
        if sl["ranged"]:
            args += ["-t", f"{sl['length']:.3f}"]
        args += ["-an", "-vf",
                 f"scale={small_w}:{small_h}:flags=fast_bilinear,format=gray",
                 "-f", "rawvideo", "-pix_fmt", "gray",
                 "-fps_mode", "passthrough", "pipe:1"]

    proc = subprocess.Popen([exe] + args, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=10 * 1024 * 1024)
    try:
        assert proc.stdout is not None
        while True:
            if _cancelled(cancel):
                try:
                    proc.kill()
                except Exception:
                    pass
                raise asyncio.CancelledError()
            buf = proc.stdout.read(buf_size)
            if not buf or len(buf) < buf_size:
                break
            grays.append(buf)
    finally:
        try:
            proc.wait(timeout=60)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            if tmp_yuv and os.path.isfile(tmp_yuv):
                os.remove(tmp_yuv)
        except OSError:
            pass
    if avs3_src is not None and len(grays) > last - first + 1:
        # full decode above; keep only the requested slice (same indexing
        # as the ffmpeg pipe path, which starts at the slice).
        grays = grays[first:last + 1]
    if not grays:
        return

    import cv2  # local import: only the fallback needs it

    cols = max(1, small_w // _BLOCK)
    rows = max(1, small_h // _BLOCK)
    tw, th = cols * _BLOCK, rows * _BLOCK
    brain_block = max(2, round(_BLOCK / scale))

    # first decoded frame (and every I frame) carries no motion
    targets: list[int] = []  # decoded positions k>=1 needing a flow match
    for k in range(len(grays)):
        fi = first + k
        if fi > last or fi >= len(frames):
            break
        if k == 0 or frames[fi].type == PicType.I:
            g = np.frombuffer(grays[k], dtype=np.uint8).reshape(small_h, small_w)
            try:
                b = blockiness(g, brain_block)
            except Exception:
                b = 1.0
            f = frames[fi]
            f.motion_mean = 0.0
            f.motion_max = 0.0
            f.motion_fwd = 0
            f.motion_bwd = 0
            f.motion_count = 0
            f.motion = None
            f.brain = b > 1.18
        else:
            targets.append(k)
    _report(progress, "Estimating motion field…", 0.05 if targets else 1.0)

    def _match(k: int):
        prev = np.frombuffer(grays[k - 1], dtype=np.uint8).reshape(small_h, small_w)
        cur = np.frombuffer(grays[k], dtype=np.uint8).reshape(small_h, small_w)
        flow = cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        crop = flow[:th, :tw, :]
        # mean per 8x8 block, still in small-frame pixels
        means = crop.reshape(rows, _BLOCK, cols, _BLOCK, 2).mean(axis=(1, 3))
        dx_s = means[:, :, 0]
        dy_s = means[:, :, 1]
        lens = np.hypot(dx_s * scale, dy_s * scale)
        mean = float(lens.mean()) if lens.size else 0.0
        peak = float(lens.max()) if lens.size else 0.0
        fwd = int((dx_s >= 0).sum())
        bwd = int(dx_s.size - fwd)
        dx_flat = [int(round(v)) for v in dx_s.ravel().tolist()]
        dy_flat = [int(round(v)) for v in dy_s.ravel().tolist()]
        ref_flat = [1 if v >= 0 else 2 for v in dx_flat]
        try:
            b = blockiness(cur, brain_block)
        except Exception:
            b = 1.0
        return k, mean, peak, fwd, bwd, dx_flat, dy_flat, ref_flat, b

    if targets:
        workers = max(1, (os.cpu_count() or 2) - 1)
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_match, k): k for k in targets}
            for fut in as_completed(futs):
                if _cancelled(cancel):
                    ex.shutdown(wait=False, cancel_futures=True)
                    raise asyncio.CancelledError()
                k, mean, peak, fwd, bwd, dx_flat, dy_flat, ref_flat, b = fut.result()
                fi = first + k
                if 0 <= fi < len(frames):
                    f = frames[fi]
                    f.motion_mean = mean
                    f.motion_max = peak
                    f.motion_fwd = fwd
                    f.motion_bwd = bwd
                    f.motion_count = fwd + bwd
                    f.motion = MotionField(cols=cols, rows=rows,
                                           dx=dx_flat, dy=dy_flat, ref=ref_flat)
                    f.brain = b > 1.18
                done += 1
                _report(progress, "Estimating motion field…",
                        0.05 + 0.95 * done / max(1, len(targets)))
    _report(progress, "Estimating motion field…", 1.0)


# ---------------------------------------------------------------- entry

def run_motion(result: AnalysisResult, progress=None, cancel=None,
               from_s: float = 0.0, to_s: float = -1) -> None:
    """Fill motion vectors/fields in place (native, else Farneback estimate)."""
    try:
        if not result.frames:
            return
        sl = _slice_of(result, from_s, to_s)
        if sl["last"] < sl["first"]:
            return
        try:
            mv_available = probe_motion_vectors(result.media.file_path, cancel)
        except asyncio.CancelledError:
            raise
        except Exception:
            mv_available = False
        if mv_available:
            try:
                if _run_mv_pass(result, sl, progress, cancel):
                    if any(f.motion_mean is not None for f in result.frames):
                        result.compute_aggregates()
                        _report(progress, "Extracting motion vectors…", 1.0)
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
        _run_estimate(result, sl, progress, cancel)
        result.motion_estimated = True
        try:
            result.compute_aggregates()
        except Exception:
            pass
        _report(progress, "Estimating motion field…", 1.0)
    except asyncio.CancelledError:
        raise
    except Exception:
        try:
            result.motion_estimated = True
            try:
                result.compute_aggregates()
            except Exception:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
