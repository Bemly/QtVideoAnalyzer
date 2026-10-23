"""AV1 profile / chroma / rate-control data module (Qt port).

Reusable, dependency-free lookup + recommendation helper for AV1
(SVT-AV1 via ffmpeg ``libsvtav1``). Only stdlib; every public function
is total -- invalid inputs yield safe defaults, never raise.

Spec anchors (checked against this box, ffmpeg 9.0.2 + SVT-AV1 v4.2.0):

* profiles: Main (0) / High (1) / Professional (2), ``--profile``.
* levels: 2.0 - 7.3, ``--level`` (0 = autodetect from input).
* chroma x bitdepth -> profile matrix: see docs/rates/av1.md.
* RC modes: 0 = CRF/CQP, 1 = VBR, 2 = CBR (``SvtAv1EncApp --help``).
* ffmpeg mapping: ``-crf N`` (CRF), ``-b:v X`` (single-pass VBR),
  CBR needs low-delay (``-svtav1-params pred-struct=1:rc=2`` +
  ``-b:v X -maxrate X -bufsize X``); plain ``-b:v`` + ``-maxrate``
  under random-access fails with "CBR ... not supported for
  RANDOM_ACCESS" on this build (verified by probe encode).
* presets: 0 (slowest) - 13 (fastest); ffmpeg wrapper accepts -2..13
  (-2 = default/unset, app default preset 8).
* tune: 0 VQ / 1 PSNR / 2 SSIM / 3 IQ / 4 MS_SSIM / 5 VMAF.
"""

from __future__ import annotations

__all__ = [
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
]

_PROFILES = ("Main", "High", "Professional")

# Spec-level (chroma x bitdepth), 9 combos; profile mapping in docs.
_CHROMA_MODES = (
    "420/8bit",
    "420/10bit",
    "420/12bit",
    "422/8bit",
    "422/10bit",
    "422/12bit",
    "444/8bit",
    "444/10bit",
    "444/12bit",
)

_RC_MODES = ("CRF", "CBR", "VBR")


def profiles() -> list[str]:
    """AV1 profiles: Main / High / Professional."""
    try:
        return list(_PROFILES)
    except Exception:
        return ["Main", "High", "Professional"]


def chroma_modes() -> list[str]:
    """Spec-level chroma/bitdepth combos (profile mapping: see doc)."""
    try:
        return list(_CHROMA_MODES)
    except Exception:
        return ["420/8bit", "420/10bit"]


def rc_modes() -> list[str]:
    """Rate-control modes supported by SVT-AV1."""
    try:
        return list(_RC_MODES)
    except Exception:
        return ["CRF", "CBR", "VBR"]


def _num(x, default: float) -> float:
    try:
        v = float(x)
        if v != v or v in (float("inf"), float("-inf")):  # NaN/inf
            return default
        return v
    except Exception:
        return default


def recommend(width, height, fps=30, use: str = "streaming") -> dict:
    """Bitrate/CRF recommendation + ready ffmpeg args. Never raises.

    ``use``: "streaming" (default, single-pass CRF) | "vod"/"archive"/
    "file" (slower preset, lower CRF) | "live"/"rtc"/"lowdelay"/"cbr"
    (low-delay CBR) | "vbr"/"capped" (single-pass VBR target).
    Unknown ``use`` falls back to "streaming".
    """
    try:
        w = _num(width, 1920.0)
        h = _num(height, 1080.0)
        f = _num(fps, 30.0)
        w = min(16384.0, max(16.0, w))
        h = min(8704.0, max(16.0, h))
        f = min(120.0, max(1.0, f))
        u = str(use or "streaming").strip().lower()
    except Exception:
        w, h, f, u = 1920.0, 1080.0, 30.0, "streaming"
    try:
        px = w * h
        px_s = px * f  # pixels per second

        # --- bit-per-pixel ladder: big frames compress better per pixel.
        if px >= 3840 * 2160:      # 4K+
            bpp = 0.050
        elif px >= 1920 * 1080:    # 1080p+
            bpp = 0.075
        elif px >= 1280 * 720:     # 720p+
            bpp = 0.090
        else:                      # SD / testsrc2 class
            bpp = 0.110
        target_kbps = px_s * bpp / 1000.0
        # fps scaling beyond 30 (60p ~1.6x, not 2x: temporal reuse).
        if f > 30.0:
            target_kbps *= 1.0 + 0.6 * min(1.0, (f - 30.0) / 30.0)
        target_kbps = max(150.0, min(80000.0, target_kbps))

        preset = 8
        crf: int | None = 32
        mode = "CRF"
        pix_fmt = "yuv420p"
        if px > 1280 * 720 or f > 30.0:
            pix_fmt = "yuv420p"  # 10bit only if HDR chain; keep 8bit default
        extra_params: list[str] = []

        if u in ("vod", "archive", "file", "hq"):
            preset, crf, mode = 5, 28, "CRF"
        elif u in ("live", "rtc", "lowdelay", "cbr", "ultralow"):
            preset, crf, mode = 10, None, "CBR"
            target_kbps = max(400.0, target_kbps)
            extra_params = ["pred-struct=1:rc=2"]
        elif u in ("vbr", "capped", "capped-crf", "streaming-vbr"):
            preset, crf, mode = 8, None, "VBR"
        else:  # streaming default
            u = "streaming"
            preset, crf, mode = 8, 32, "CRF"
            if px >= 3840 * 2160:
                crf = 30

        bitrate_kbps = int(round(target_kbps))
        if mode == "CRF":
            args = ["-c:v", "libsvtav1", "-preset", str(preset),
                    "-crf", str(int(crf or 32)), "-pix_fmt", pix_fmt]
            notes = (
                f"单遍 CRF {crf} + preset {preset}（VOD/点播默认）；"
                f"同画质约比 HEVC 省 ~30%（VMAF 对齐口径，见 docs/rates/av1.md）；"
                f"参考目标 {bitrate_kbps} kbps（仅估算，不钳制）。"
                "CBR 在本机 SVT 需 low-delay（见 live 用法），默认随机接入下"
                " -maxrate 会报 CBR-not-supported。"
            )
        elif mode == "CBR":
            args = ["-c:v", "libsvtav1", "-preset", str(preset),
                    "-b:v", f"{bitrate_kbps}k",
                    "-maxrate", f"{bitrate_kbps}k",
                    "-bufsize", f"{bitrate_kbps}k",
                    "-pix_fmt", pix_fmt]
            if extra_params:
                args += ["-svtav1-params", ":".join(extra_params)]
            notes = (
                f"低延迟 CBR {bitrate_kbps} kbps + preset {preset}（直播/RTC）；"
                "必须 pred-struct=1，否则本机 SVT 拒绝 CBR（RANDOM_ACCESS 不支持）。"
                "画质波动大，点播优先用 CRF。"
            )
        else:  # VBR
            args = ["-c:v", "libsvtav1", "-preset", str(preset),
                    "-b:v", f"{bitrate_kbps}k", "-pix_fmt", pix_fmt]
            notes = (
                f"单遍 VBR 目标 {bitrate_kbps} kbps + preset {preset}；"
                "要峰值可再加 -maxrate（<=2x 目标）；多遍 VBR 需 SvtAv1EncApp。"
            )

        return {
            "use": u,
            "mode": mode,
            "width": int(w),
            "height": int(h),
            "fps": float(f),
            "preset": int(preset),
            "crf": (int(crf) if crf is not None else None),
            "bitrate_kbps": int(bitrate_kbps),
            "maxrate_kbps": (int(bitrate_kbps) if mode == "CBR" else None),
            "pix_fmt": pix_fmt,
            "ffmpeg_args": list(args),
            "notes": notes,
        }
    except Exception:
        return {
            "use": "streaming",
            "mode": "CRF",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "preset": 8,
            "crf": 32,
            "bitrate_kbps": 5000,
            "maxrate_kbps": None,
            "pix_fmt": "yuv420p",
            "ffmpeg_args": ["-c:v", "libsvtav1", "-preset", "8",
                            "-crf", "32", "-pix_fmt", "yuv420p"],
            "notes": "fallback 默认（输入异常）：1080p CRF 32。",
        }


def paint_hint() -> str:
    """One-line overlay hint for the Qt video widget."""
    try:
        return (
            "av1-sb：128x128 SB 网格（I 整块 / P 按 motion 细分 128->64->32）；"
            "BITRATE 偏低先看 film-grain 合成（颗粒在帧头，不占残差码率），"
            "B 恒 0 属正常（Key/Inter 全报 P）。"
        )
    except Exception:
        return "av1-sb overlay"
