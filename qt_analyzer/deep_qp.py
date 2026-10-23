"""Picture-type + QP deep pass. Mirrors DeepAnalysisService.RunTypeAndQpPassAsync.

Native path decodes with ``-debug qp`` and attributes the interleaved dump
via the decoder-instance pointer prefix; when no dump exists (theora / av1 /
h263 / vp6 / vp8 / vp9 usually) it falls back to a bits-per-pixel estimate.
Only numpy is not even needed here; deps are stdlib + ffmpeg binary.
"""
from __future__ import annotations

import asyncio
import re
import subprocess

try:
    from . import ffmpeg_locator
    from .models import AnalysisResult, PicType
except ImportError:  # flat-script import from inside qt_analyzer/
    import ffmpeg_locator  # type: ignore
    from models import AnalysisResult, PicType  # type: ignore

# Encoders whose ffmpeg decoder emits a ``-debug qp`` dump. Everything else
# (theora / av1 / h263 / vp6 / vp8 / vp9, ...) almost never produces one, so
# those files must take the EstimateQp branch without raising.
SUPPORTED_QP_NATIVE = {"avc", "h264", "hevc", "h265", "mpeg2video", "mpeg1video", "mpeg4"}

_NEW_FRAME_RX = re.compile(r"New frame, type:\s*(\w)")
_INT_RX = re.compile(r"-?\d+")
_UPDATE_EVERY = 96

# .NET int.TryParse is 32-bit: tokens that overflow int32 fail to parse and are
# ignored (they neither trigger the >63 header-skip nor get collected). This
# matters because ffmpeg prints the QP table with "%2d" cells, so two adjacent
# double-digit QPs merge into one long digit run (e.g. "2623"); those runs
# overflow int32 and are skipped, while isolated single-digit cells are still
# collected. Emulating this exactly is what makes the port behave like the C#.
_INT32_MIN = -2147483648
_INT32_MAX = 2147483647


def _try_parse_i32(tok: str):
    try:
        v = int(tok)
    except ValueError:
        return None
    if v < _INT32_MIN or v > _INT32_MAX:
        return None
    return v


# ---------------------------------------------------------------- slice

def _slice_of(result: AnalysisResult, from_s: float, to_s: float) -> dict:
    """Copy of DeepAnalysisService.Slice.Of()."""
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


# ------------------------------------------------------- line helpers

def _pointer_of(line: str) -> int:
    """Decoder instance from a ``[h264 @ 0x...]`` prefix (copy of PointerOf)."""
    at = line.find("@ ")
    if at < 0:
        return 0
    close = line.find("]", at + 2)
    if close < 0:
        return 0
    try:
        return int(line[at + 2:close].strip(), 16)
    except ValueError:
        return 0


def _body_of(line: str) -> str:
    """Everything after the ``[component @ address]`` prefix."""
    close = line.find("]")
    if close >= 0 and close + 1 < len(line):
        return line[close + 1:]
    return ""


def _parse_type(s: str) -> PicType:
    if not s:
        return PicType.Other
    c = s[0].upper()
    if c == "I":
        return PicType.I
    if c == "P":
        return PicType.P
    if c == "B":
        return PicType.B
    return PicType.Other


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

def _probe_qp(file_path: str, cancel=None) -> bool:
    """Small ``-t 1`` decode: True when a QP dump is really emitted."""
    exe = ffmpeg_locator.ffmpeg_path()
    if not exe:
        return False
    if _cancelled(cancel):
        raise asyncio.CancelledError()
    try:
        p = subprocess.run(
            [exe, "-v", "debug", "-hide_banner", "-debug", "qp",
             "-i", file_path, "-t", "1", "-an", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, errors="ignore", timeout=60)
        out = p.stderr or ""
        return "New frame, type:" in out
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


# ---------------------------------------------------------------- native pass

def _run_qp_pass(result: AnalysisResult, sl: dict, progress=None, cancel=None) -> None:
    exe = ffmpeg_locator.ffmpeg_path()
    if not exe:
        return
    args = ["-v", "debug", "-hide_banner", "-debug", "qp"]
    if sl["start"] > 0.01:
        args += ["-ss", f"{sl['start']:.3f}"]
    args += ["-i", result.media.file_path]
    if sl["ranged"]:
        args += ["-t", f"{sl['length']:.3f}"]
    args += ["-an", "-f", "null", "-"]

    by_decode = {f.decode_index: f for f in result.frames if f.decode_index >= 0}
    open_frame: dict[int, int] = {}
    values: dict[int, list] = {}
    types: dict[int, PicType] = {}
    decode_index = -1
    since_update = 0
    total = max(1, sl["last"] - sl["first"] + 1)

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
            m = _NEW_FRAME_RX.search(line)
            if m:
                decode_index += 1
                glob = decode_index + sl["decode_offset"]
                if glob < sl["first_decode"]:
                    continue
                types[glob] = _parse_type(m.group(1))
                values[glob] = []
                open_frame[_pointer_of(line)] = glob
                since_update += 1
                if since_update >= _UPDATE_EVERY:
                    since_update = 0
                    _apply(result, by_decode, values, types)
                    _report(progress, "Extracting picture types and QP…",
                            min(1.0, decode_index / total))
                continue
            body = _body_of(line)
            if not body:
                continue
            idx = open_frame.get(_pointer_of(line))
            if idx is None:
                continue
            lst = values.get(idx)
            if lst is None:
                continue
            found = _INT_RX.findall(body)
            if not found:
                continue
            ints: list[int] = []
            header = False
            for tok in found:
                # int32 semantics like C# int.TryParse (see _try_parse_i32):
                # merged "%2d" cells overflow and are ignored.
                v = _try_parse_i32(tok)
                if v is None:
                    continue
                # first line of a dump is the block-x header: values far
                # larger than any quantiser -> skip the whole line
                if v > 63:
                    header = True
                    break
                ints.append(v)
            if header:
                continue
            for v in ints:
                if 1 <= v <= 63:
                    lst.append(v)
    finally:
        try:
            proc.wait(timeout=30)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    _apply(result, by_decode, values, types)
    _fill_qp_gaps(result, sl)
    _report(progress, "Extracting picture types and QP…", 1.0)


def _apply(result: AnalysisResult, by_decode: dict, values: dict, types: dict) -> None:
    for idx, lst in values.items():
        f = by_decode.get(idx)
        if f is None:
            continue
        t = types.get(idx)
        if t is not None and t != PicType.Other:
            f.type = t
        if not lst:
            continue
        f.qp_avg = sum(lst) / len(lst)
        f.qp_min = float(min(lst))
        f.qp_max = float(max(lst))


def _fill_qp_gaps(result: AnalysisResult, sl: dict) -> None:
    """Carry the previous value forward, then fill a leading run backwards."""
    frames = result.frames
    if not frames:
        return
    first = max(0, sl["first"])
    last = min(sl["last"], len(frames) - 1)
    if last < first:
        return
    carry = None
    for i in range(first, last + 1):
        f = frames[i]
        if f.qp_avg is not None:
            carry = f.qp_avg
            continue
        if carry is None:
            continue
        f.qp_avg = carry
        f.qp_min = carry
        f.qp_max = carry
    carry = None
    for i in range(last, first - 1, -1):
        f = frames[i]
        if f.qp_avg is not None:
            carry = f.qp_avg
            continue
        if carry is None:
            continue
        f.qp_avg = carry
        f.qp_min = carry
        f.qp_max = carry


def _infer_missing_types(result: AnalysisResult, sl: dict) -> None:
    frames = result.frames
    if not frames:
        return
    first = max(0, sl["first"])
    last = min(sl["last"], len(frames) - 1)
    if last < first:
        return
    known = first - 1
    for i in range(first, last + 1):
        if frames[i].type != PicType.Other:
            known = i
            continue
        if frames[i].key_frame:
            frames[i].type = PicType.I
            continue
        if known >= 0:
            frames[i].type = frames[known].type
    first_known = -1
    for i in range(first, last + 1):
        if frames[i].type != PicType.Other:
            first_known = i
            break
    if first_known > first:
        for i in range(first, first_known):
            frames[i].type = frames[first_known].type


def _run_show_frames_fallback(result: AnalysisResult, sl: dict) -> int:
    """Universal picture-type fallback via `ffprobe -show_frames`.

    `-debug qp` only exists for a few decoders (avc/mpeg2/h263 on ffmpeg 9);
    hevc/av1/vp8/vp9/theora/h263/vp6 never emit it. ffprobe's frame header
    parse works for all 8 codecs, so when native types are sparse we fill
    the gaps by timestamp matching. Returns filled count.
    """
    try:
        ffprobe = ffmpeg_locator.ffprobe_path()
    except Exception:
        ffprobe = None
    if not ffprobe:
        return 0
    frames = result.frames
    if not frames:
        return 0
    first = max(0, sl["first"])
    last = min(sl["last"], len(frames) - 1)
    if last < first:
        return 0
    # NOTE: no early-out on Other count. After gap inference there may be
    # zero Others left (all propagated to I); the loop below still repairs
    # I-on-nonkey frames via header truth.
    try:
        p = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "frame=pict_type,best_effort_timestamp_time",
             "-of", "csv=p=0", result.media.file_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, errors="ignore", timeout=120)
    except Exception:
        return 0
    entries: list[tuple[float, PicType]] = []
    for line in (p.stdout or "").splitlines():
        line = line.strip().strip(",")
        if not line:
            continue
        pts: float | None = None
        typ = PicType.Other
        for tok in line.split(","):
            t = tok.strip()
            if not t:
                continue
            cu = t.upper()
            if cu in ("I", "P", "B", "S", "SI", "SP", "BI"):
                typ = _parse_type(cu[0])
            else:
                try:
                    pts = float(t)
                except ValueError:
                    continue
        if pts is None or typ == PicType.Other and "I" not in line and "P" not in line and "B" not in line:
            pass
        if pts is None:
            continue
        if typ == PicType.Other:
            continue
        entries.append((pts, typ))
    if not entries:
        return 0
    entries.sort(key=lambda e: e[0])
    filled = 0
    interval = 1.0 / max(1.0, result.media.fps or 25.0)
    for i in range(first, last + 1):
        f = frames[i]
        if f.type != PicType.Other:
            # Native qp dump (avc/mpeg2/h263) is authoritative when present,
            # but a propagated I on a non-key frame is just gap inference:
            # show_frames (true header parse, all 8 codecs) wins there.
            if not (f.type == PicType.I and not f.key_frame):
                continue
        # nearest entry by pts
        best: PicType | None = None
        best_d = interval * 1.5 + 1e-6
        for pts, typ in entries:
            d = abs(pts - f.pts_time)
            if d < best_d:
                best_d = d
                best = typ
                if d == 0:
                    break
        if best is not None and best != PicType.Other:
            # Never demote a true packet-level keyframe away from I.
            if f.key_frame and f.type == PicType.I and best != PicType.I:
                continue
            if f.type != best:
                f.type = best
                filled += 1
    return filled


def _estimate_qp(result: AnalysisResult) -> None:
    """Bits-per-pixel driven estimate (copy of EstimateQp)."""
    m = result.media
    px = max(1, m.width * m.height)
    if not result.frames:
        return
    for f in result.frames:
        bpp = f.packet_size * 8.0 / px
        qp = 34.0 / pow(max(bpp, 1e-5) * 260.0, 1 / 1.6)
        qp = min(51.0, max(1.0, qp))
        if f.type == PicType.I:
            qp *= 0.75
        elif f.type == PicType.B:
            qp *= 1.15
        qp = min(51.0, max(1.0, qp))
        f.qp_avg = qp
        f.qp_min = max(0.0, qp - (12 if f.type == PicType.I else 8))
        f.qp_max = min(51.0, qp + (14 if f.type == PicType.B else 10))


# ---------------------------------------------------------------- entry

def run_type_qp(result: AnalysisResult, progress=None, cancel=None,
                from_s: float = 0.0, to_s: float = -1) -> None:
    """Fill picture types + QP in place (native dump, else estimate)."""
    try:
        if not result.frames:
            return
        sl = _slice_of(result, from_s, to_s)
        if sl["last"] < sl["first"]:
            return
        try:
            qp_available = _probe_qp(result.media.file_path, cancel)
        except asyncio.CancelledError:
            raise
        except Exception:
            qp_available = False
        if qp_available:
            try:
                _run_qp_pass(result, sl, progress, cancel)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
        _infer_missing_types(result, sl)
        # Universal fallback: ffprobe frame headers work for all 8 codecs.
        # Native qp dump covers avc/mpeg2/h263; everything else would otherwise
        # collapse to I/Other via gap inference. Always run: it also repairs
        # propagated I's on non-key frames.
        try:
            _run_show_frames_fallback(result, sl)
            _infer_missing_types(result, sl)
        except Exception:
            pass
        if all(f.qp_avg is None for f in result.frames):
            _estimate_qp(result)
            result.qp_estimated = True
        result.compute_aggregates()
        _report(progress, "Extracting picture types and QP…", 1.0)
    except asyncio.CancelledError:
        raise
    except Exception:
        # last resort: never leave the caller without types/QP
        try:
            if result.frames and all(f.qp_avg is None for f in result.frames):
                _estimate_qp(result)
                result.qp_estimated = True
            try:
                result.compute_aggregates()
            except Exception:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
