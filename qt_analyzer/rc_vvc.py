"""VVC (H.266) profile / chroma / rate-control data module.

Pure literature module (VVenC documentation calibre): no third-party
dependencies, stdlib only, never raises. All bitrate / saving numbers are
documented ranges (``estimated``), not local measurements -- this machine
has no ``libvvenc``/``vvencapp`` encoder (``ffmpeg -encoders`` shows no
vvc/vvenc entry), so nothing here is measured on-device.

Literature basis (see ``docs/rates/vvc.md`` for full citations):

* Profiles/levels/tiers: ITU-T H.266 | ISO/IEC 23090-3 Annex A;
  DASH-IF "VVC HLS overview" (6 profiles in v1, 13 levels, Main/High tiers,
  typical interop points L3.1=720p30 ... L6.x=8K).
* VVenC RC/presets: fraunhoferhhi/vvenc wiki ``Usage`` + ``FFmpeg-Integration``
  (vvencapp ``--preset faster..slower``, ``--qp 0..63`` default 32,
  ``--bitrate``/``--maxrate`` (>=1.5x target), ``--passes 1|2`` default 2,
  ``--qpa`` default 1; ffmpeg ``-preset faster..slower``, ``-qp``, ``-qpa``,
  ``-b:v``/``-maxrate``, ``-pass 1|2`` + ``-passlogfile``, ``-period``,
  ``-vvenc-params``; pixel format ``yuv420p10le``).
* Saving vs HEVC: JVET design target ~50%; VTM vs HM ~40-41% PSNR BD-rate
  (Sullivan DCC'21); vvenc production-measured typically ~30-50%.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Profiles / chroma / RC modes
# ---------------------------------------------------------------------------

_PROFILES = (
    "Main 10",
    "Main 10 4:4:4",
    "Multilayer Main 10",
)

_CHROMA_MODES = (
    "420 8-bit (yuv420p)",
    "420 10-bit (yuv420p10le)",
    "444 8-bit (yuv444p)",
    "444 10-bit (yuv444p10le)",
)

_RC_MODES = ("QP", "CBR", "VBR")

_PRESETS = ("faster", "fast", "medium", "slow", "slower")


def profiles() -> list[str]:
    """VVC v1 profile shortlist relevant to streaming tools."""
    try:
        return list(_PROFILES)
    except Exception:
        return ["Main 10"]


def chroma_modes() -> list[str]:
    """Chroma x bit-depth modes (label + ffmpeg pix_fmt hint)."""
    try:
        return list(_CHROMA_MODES)
    except Exception:
        return ["420 10-bit (yuv420p10le)"]


def rc_modes() -> list[str]:
    """Rate-control modes exposed by this module."""
    try:
        return list(_RC_MODES)
    except Exception:
        return ["QP", "CBR", "VBR"]


def presets() -> list[str]:
    """VVenC presets, fast to slow (extra helper, never raises)."""
    try:
        return list(_PRESETS)
    except Exception:
        return ["medium"]


# ---------------------------------------------------------------------------
# recommend()
# ---------------------------------------------------------------------------

def _to_float(value, default: float) -> float:
    try:
        f = float(value)
    except Exception:
        return default
    try:
        import math
        if math.isnan(f) or math.isinf(f) or f <= 0:
            return default
    except Exception:
        if not (f > 0):
            return default
    return f


def _norm_use(use) -> str:
    try:
        s = str(use or "streaming").strip().lower()
    except Exception:
        return "streaming"
    if not s:
        return "streaming"
    for key in ("realtime", "real-time", "live", "lowdelay", "low-delay",
                "ll", "ultrafast"):
        if key in s:
            return "realtime"
    if "stream" in s or "vod" in s or s in ("abr", "dash", "hls"):
        return "streaming"
    if "archiv" in s or "master" in s or "quality" in s or "slow" in s:
        return "archive"
    if "best" in s or "slower" in s or "placebo" in s:
        return "best"
    if "qp" in s or "cqp" in s or "const" in s:
        return "qp"
    return "streaming"


def _res_class(width: float, height: float) -> str:
    try:
        px = float(width) * float(height)
    except Exception:
        return "1080p"
    if px <= 0:
        return "1080p"
    if px <= 1_100_000:
        return "720p"
    if px <= 2_800_000:
        return "1080p"
    if px <= 9_500_000:
        return "4K"
    return "8K"


def _base_target_mbps(res_class: str) -> float:
    # VBR target anchors at 30 fps, SDR 4:2:0 10-bit, medium-ish content.
    # Calibre: VVenC DASH example ladder (720p 1M / 1080p 2M / 2160p 4M,
    # maxrate 2x) is the aggressive end; +50-100% is the safe end.
    # Mid anchors below sit between the two and equal ~0.5-0.6x HEVC ladders.
    try:
        return {"720p": 1.5, "1080p": 3.0, "4K": 8.0, "8K": 28.0}.get(
            res_class, 3.0)
    except Exception:
        return 3.0


def _level_for(width: float, height: float, fps: float) -> str:
    try:
        w, h, f = float(width), float(height), float(fps)
    except Exception:
        return "4.1"
    px = w * h
    try:
        if px <= 1280 * 720 and f <= 33:
            return "3.1"
        if px <= 1920 * 1080:
            return "4.0" if f <= 33 else "4.1"
        if px <= 3840 * 2160:
            if f <= 33:
                return "5.0"
            if f <= 66:
                return "5.1"
            return "5.2"
        if f <= 33:
            return "6.0"
        if f <= 66:
            return "6.1"
        return "6.2"
    except Exception:
        return "5.1"


def _preset_for(res_class: str, use: str) -> str:
    try:
        if use == "realtime":
            return "faster"
        if use == "archive":
            # slow is the sane archive choice; slower reserved for "best".
            return "slow" if res_class in ("720p", "1080p", "4K") else "medium"
        if use == "best":
            return "slower" if res_class in ("720p", "1080p") else "slow"
        if use == "qp":
            return "medium"
        # streaming / default: keep 4K/8K feasible, 1080p and below at medium.
        if res_class in ("4K", "8K"):
            return "fast"
        return "medium"
    except Exception:
        return "medium"


def recommend(width, height, fps, use: str = "streaming") -> dict:
    """Bitrate/preset recommendation (estimated, never raises).

    Returns dict with at least ``preset``, ``ffmpeg_args`` and ``notes``,
    plus ``bitrate_bps``/``maxrate_bps``/``profile``/``level``/``tier``/
    ``passes``/``pix_fmt``/``vvencapp_cmd`` for direct reuse.
    """
    try:
        w = _to_float(width, 1920.0)
        h = _to_float(height, 1080.0)
        f = _to_float(fps, 30.0)
        if f > 240:
            f = 30.0
        if w > 16384 or h > 16384:
            w, h = 1920.0, 1080.0
        use_n = _norm_use(use)
        res = _res_class(w, h)
        base = _base_target_mbps(res)
        # fps scaling: linear vs 30 fps, clamped to [0.5x, 2.5x].
        try:
            scale = min(2.5, max(0.5, f / 30.0))
        except Exception:
            scale = 1.0
        # use adjustments: realtime -25% (cap for latency), archive +25%.
        try:
            adj = {"realtime": 0.75, "archive": 1.25,
                   "best": 1.25}.get(use_n, 1.0)
        except Exception:
            adj = 1.0
        target_m = round(base * scale * adj, 2)
        # clamp to sane bounds per class so garbage in never yields garbage out
        try:
            lo = {"720p": 0.5, "1080p": 1.0, "4K": 3.0, "8K": 12.0}[res]
            hi = {"720p": 6.0, "1080p": 12.0, "4K": 25.0, "8K": 80.0}[res]
            target_m = min(hi, max(lo, target_m))
        except Exception:
            pass
        max_m = round(target_m * 2.0, 2)  # VVenC requires maxrate >= 1.5x
        preset = _preset_for(res, use_n)
        level = _level_for(w, h, f)
        tier = "main"
        passes = 1 if use_n in ("realtime", "streaming") else 2
        bitrate_bps = int(round(target_m * 1_000_000))
        maxrate_bps = int(round(max_m * 1_000_000))
        profile = "Main 10"
        pix_fmt = "yuv420p10le"
        ff_args = [
            "-c:v", "libvvenc",
            "-preset", preset,
            "-b:v", f"{bitrate_bps}",
            "-maxrate", f"{maxrate_bps}",
            "-pix_fmt", pix_fmt,
            "-level", level,
            "-tier", tier,
        ]
        if passes == 2:
            note_pass = ("2-pass VBR (ffmpeg: run -pass 1 then -pass 2 with "
                         "a shared -passlogfile; vvencapp runs both passes "
                         "internally with -p 2 by default)")
        else:
            note_pass = ("1-pass VBR (low-latency default; ffmpeg runs "
                         "single-pass unless -pass 1/2 is given)")
        vv_cmd = (
            f"vvencapp --preset {preset} -s {int(w)}x{int(h)} "
            f"-r {f:g} -b {bitrate_bps} -m {maxrate_bps} -p {passes} "
            f"--qpa 1 -o str.266"
        )
        notes = (
            f"{res}@{f:g} {use_n}: VBR target ~{target_m:g} Mbps "
            f"(max ~{max_m:g} Mbps = 2x, satisfies VVenC >=1.5x rule); "
            f"preset {preset}; profile {profile} level {level} {tier} tier. "
            f"{note_pass}. "
            "No local encoder on this machine (ffmpeg 9.0.2: no libvvenc) "
            "-- values are VVenC-doc-calibre estimates, not measurements; "
            "expect ~40-50% below an HEVC ladder for equal quality. "
            "Set -qpa 0 for PSNR/VMAF tuning, keep -qpa 1 for subjective."
        )
        return {
            "preset": preset,
            "ffmpeg_args": list(ff_args),
            "notes": notes,
            "use": use_n,
            "res_class": res,
            "width": int(w),
            "height": int(h),
            "fps": float(f),
            "bitrate_bps": bitrate_bps,
            "bitrate_mbps": target_m,
            "maxrate_bps": maxrate_bps,
            "maxrate_mbps": max_m,
            "profile": profile,
            "level": level,
            "tier": tier,
            "passes": passes,
            "pix_fmt": pix_fmt,
            "qp_hint": 32 if use_n != "archive" else 27,
            "vvencapp_cmd": vv_cmd,
            "estimated": True,
        }
    except Exception as exc:
        try:
            return {
                "preset": "medium",
                "ffmpeg_args": ["-c:v", "libvvenc", "-preset", "medium",
                                "-b:v", "3000000", "-maxrate", "6000000",
                                "-pix_fmt", "yuv420p10le"],
                "notes": f"fallback 1080p recommendation ({exc})",
                "use": "streaming",
                "res_class": "1080p",
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "bitrate_bps": 3000000,
                "bitrate_mbps": 3.0,
                "maxrate_bps": 6000000,
                "maxrate_mbps": 6.0,
                "profile": "Main 10",
                "level": "4.1",
                "tier": "main",
                "passes": 1,
                "pix_fmt": "yuv420p10le",
                "qp_hint": 32,
                "vvencapp_cmd": ("vvencapp --preset medium -s 1920x1080 "
                                 "-r 30 -b 3000000 -m 6000000 -p 1 -o str.266"),
                "estimated": True,
            }
        except Exception:
            return {"preset": "medium", "ffmpeg_args": [],
                    "notes": "fallback"}


def paint_hint() -> str:
    """One-line viewer linkage hint (never raises)."""
    try:
        return (
            "VVC 视图联动:开 128 CTU 的 MTT 层 "
            "(codec_next.mtt_overlay, I 浅蓝绿大块 / P、B 深橙红小块),"
            "GOP 条看大 GOP + B 密排 (B 占比常 >60%),"
            "BITRATE 图 I 峰尖而稀、B 海洋又密又矮;"
            " profile/chroma/码率口径见 docs/rates/vvc.md,估算值标 estimated."
        )
    except Exception:
        return "VVC: 128 CTU MTT + large GOP + dense B (see docs/rates/vvc.md)."
