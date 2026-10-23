"""Container / stream metadata via ffprobe.

Mirrors ``MediaProbeService.cs`` (``ProbeAsync``): runs
``ffprobe -show_format -show_streams`` and maps the JSON ``format`` object,
the first video stream and the first audio stream onto :class:`MediaInfo`.

Standard library + subprocess only (no Qt), so unit tests import it freely.
"""
from __future__ import annotations

import json
import os
import subprocess

try:  # imported as part of the qt_analyzer package
    from .ffmpeg_locator import ffprobe_path
    from .models import MediaInfo
except ImportError:  # imported standalone with the package dir on sys.path
    from ffmpeg_locator import ffprobe_path  # type: ignore[no-redef]
    from models import MediaInfo  # type: ignore[no-redef]


def _str(obj: dict, key: str, fallback: str = "") -> str:
    v = obj.get(key, fallback)
    return v if isinstance(v, str) else fallback


def _float(obj: dict, key: str) -> float:
    try:
        v = obj.get(key, "")
        if v is None:
            return 0.0
        text = str(v).strip()
        return float(text) if text else 0.0
    except (TypeError, ValueError):
        return 0.0


def _int(obj: dict, key: str) -> int:
    try:
        v = obj.get(key, "")
        if v is None:
            return 0
        text = str(v).strip()
        if not text:
            return 0
        return int(float(text))  # tolerates "90.0"; rejects "N/A" -> 0
    except (TypeError, ValueError):
        return 0


def _ratio(text: object) -> float:
    """Parse "30000/1001" or a plain float string; 0.0 when unparseable."""
    try:
        t = str(text).strip()
        if not t:
            return 0.0
        if "/" in t:
            num, _, den = t.partition("/")
            d = float(den)
            if d == 0:
                return 0.0
            return float(num) / d
        return float(t)
    except (TypeError, ValueError):
        return 0.0


def probe(file_path: str) -> MediaInfo:
    """Probe *file_path* with ffprobe and return its :class:`MediaInfo`.

    Missing JSON fields never raise -- numeric fields default to 0 and text
    fields to ``"unknown"``. Raises :class:`FileNotFoundError` for a missing
    file and :class:`RuntimeError` when ffprobe itself is unavailable/fails.
    """
    info = MediaInfo(file_path=file_path, file_name=os.path.basename(file_path))

    exe = ffprobe_path()
    if not exe:
        raise RuntimeError("ffprobe was not found. Configure the ffmpeg tool folder first.")
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"file not found: {file_path}")

    try:
        proc = subprocess.run(
            [exe, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", file_path],
            capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ffprobe timed out probing {file_path}") from exc
    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(f"ffprobe failed for {file_path}: {proc.stderr.strip()[:300]}")

    try:
        root = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        root = {}
    if not isinstance(root, dict):
        root = {}

    fmt = root.get("format")
    if not isinstance(fmt, dict):
        fmt = {}
    info.format_name = _str(fmt, "format_name", "unknown") or "unknown"
    info.format_long_name = _str(fmt, "format_long_name", "unknown") or "unknown"
    info.container_bit_rate = _int(fmt, "bit_rate")
    info.duration = _float(fmt, "duration")
    info.file_size_bytes = _int(fmt, "size")
    if info.file_size_bytes <= 0:
        try:
            info.file_size_bytes = os.path.getsize(file_path)
        except OSError:
            pass

    streams = root.get("streams") or []
    video: dict | None = None
    audio: dict | None = None
    if isinstance(streams, list):
        for s in streams:
            if not isinstance(s, dict):
                continue
            kind = s.get("codec_type", "")
            if kind == "video" and video is None:
                video = s
            elif kind == "audio" and audio is None:
                audio = s

    if video is not None:
        info.video_codec = _str(video, "codec_name", "unknown") or "unknown"
        info.video_profile = _str(video, "profile", "unknown") or "unknown"
        info.video_level = _str(video, "level", "")
        info.width = _int(video, "width")
        info.height = _int(video, "height")
        info.pix_fmt = _str(video, "pix_fmt", "unknown") or "unknown"
        info.nb_frames = _int(video, "nb_frames")
        info.video_bit_rate = _int(video, "bit_rate")
        info.color_range = _str(video, "color_range", "unknown") or "unknown"
        info.color_space = _str(video, "color_space", "unknown") or "unknown"
        info.color_primaries = _str(video, "color_primaries", "unknown") or "unknown"
        info.color_transfer = _str(video, "color_transfer", "unknown") or "unknown"
        info.field_order = _str(video, "field_order", "unknown") or "unknown"
        info.codec_tag = _str(video, "codec_tag_string", "")
        try:
            info.tbr = _ratio(video.get("r_frame_rate", "0/0"))
        except Exception:
            info.tbr = 0.0
        sar = str(video.get("sample_aspect_ratio", "1:1"))
        if "/" in sar:
            try:
                n, _, d = sar.partition("/")
                info.sar_num, info.sar_den = int(n), int(d)
                if info.sar_den == 0:
                    info.sar_num, info.sar_den = 1, 1
            except ValueError:
                info.sar_num, info.sar_den = 1, 1
        fps = _ratio(video.get("avg_frame_rate", "0/0"))
        if fps <= 0:
            fps = _ratio(video.get("r_frame_rate", "0/0"))
        info.fps = fps
        if info.duration <= 0:
            info.duration = _float(video, "duration")

    if audio is not None:
        info.has_audio = True
        info.audio_codec = _str(audio, "codec_name", "unknown") or "unknown"
        info.sample_rate = _int(audio, "sample_rate")
        info.channels = _int(audio, "channels")
        info.sample_format = _str(audio, "sample_fmt", "unknown") or "unknown"
        info.channel_layout = _str(audio, "channel_layout", "unknown") or "unknown"
        info.audio_bit_rate = _int(audio, "bit_rate")

    if info.fps <= 0:
        info.fps = 25.0
    if info.duration <= 0 and info.nb_frames > 0:
        info.duration = info.nb_frames / info.fps
    _fix_avs3(info)
    return info


def _uavs3dec_path() -> str | None:
    """Locate the AVS3 reference decoder (tools/avs3bin, else PATH)."""
    try:
        import shutil
        here = os.path.dirname(os.path.abspath(__file__))
        for cand in (os.path.normpath(os.path.join(here, "..", "tools", "avs3bin", "uavs3dec")),
                     os.path.join(os.path.dirname(here), "avs3bin", "uavs3dec")):
            try:
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    return cand
            except OSError:
                continue
        w = shutil.which("uavs3dec")
        if w:
            return w
    except Exception:
        pass
    return None


def _fix_avs3(info: MediaInfo) -> None:
    """AVS3: ffprobe gives no dimensions; decode 2 frames with uavs3dec.

    Fills width/height from the sequence header log and fps from tbr
    (the AVS3 demuxer parses frame_rate_code into tbr). No decoder ->
    fields stay 0 and playback reports it instead of failing silently.
    """
    try:
        codec = str(info.video_codec or "").lower()
    except Exception:
        return
    if codec not in ("avs3", "avs", "avs3-p2"):
        return
    try:
        if 1.0 <= float(info.tbr or 0) <= 240.0:
            info.fps = float(info.tbr)
    except Exception:
        pass
    if (info.width or 0) > 0 and (info.height or 0) > 0:
        return
    exe = _uavs3dec_path()
    if not exe:
        return
    import re as _re
    import tempfile as _tf
    tmp = None
    try:
        fd, tmp = _tf.mkstemp(suffix=".yuv")
        os.close(fd)
        p = subprocess.run([exe, "-i", info.file_path, "-o", tmp,
                            "-f", "2", "-l", "2"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors="ignore", timeout=180)
        out = p.stdout or ""
        m = _re.search(r"Resolution\s*=\s*(\d+)\s*x\s*(\d+)", out)
        if m:
            info.width, info.height = int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    finally:
        try:
            if tmp and os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass
