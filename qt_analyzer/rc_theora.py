"""Theora quality / sampling / bitrate recommendation data module.

Pure literature research (本机 ffmpeg 无 ``libtheora`` 编码器, 只有解码器,
见 docs/rates/theora.md): 无第三方依赖, 所有公开函数永不抛错
(输入非法时回退到安全默认值).

要点速览 (详见 docs/rates/theora.md):
* 无 profile 体系: VP3 血统 (On2 TrueMotion VP3.2 -> Xiph Theora I),
  不像 MPEG 系分 Baseline/Main/High.
* quality 0~10 档: VBR 恒定质量 targeting (``-q:v N`` / ``flags +qscale``),
  内部 ``N clip[0,10] * 6.3 -> native [0,63]``.
* bitrate targeting: ``-b:v N`` (1-pass 为软目标/长期均值, 2-pass 收紧);
  硬 CBR 靠上层 VBV 整形 (``-minrate=-maxrate`` + ``-bufsize``).
* chroma: ffmpeg ``libtheora`` 包装只认 ``yuv420p`` (码流 PFI 另有
  422/444 定义, 但编码路径按 420 处理).
"""

from __future__ import annotations

__all__ = [
    "ENCODER",
    "CONTAINER",
    "QUALITY_MIN",
    "QUALITY_MAX",
    "NATIVE_SCALE",
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
]

ENCODER = "libtheora"
CONTAINER = ".ogv (Ogg)"

QUALITY_MIN = 0
QUALITY_MAX = 10
#: quality 档 -> libtheora native 范围的换算系数 (ffmpeg 文档 §9.15:
#: clip[0,10] 后 * 6.3 得 [0,63]).
NATIVE_SCALE = 6.3

#: (像素上限, 档位名, CBR 起点 kbps@30fps, VBR quality 档)
_LADDER = (
    (230400, "360p", 700, 4),
    (409920, "480p", 1000, 5),
    (921600, "720p", 2600, 5),
    (2073600, "1080p", 5000, 6),
)


def profiles() -> list:
    """Theora 无 profile 体系 (VP3 血统)."""
    try:
        return ["(no profiles: VP3-based)"]
    except Exception:
        return ["(no profiles: VP3-based)"]


def chroma_modes() -> list:
    """ffmpeg libtheora 编码路径仅 420."""
    try:
        return ["420"]
    except Exception:
        return ["420"]


def rc_modes() -> list:
    """两种目标模式: VBR 恒定质量 / CBR(软目标)码率."""
    try:
        return ["VBR-quality", "CBR-target"]
    except Exception:
        return ["VBR-quality", "CBR-target"]


def _num(value, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
        return default
    return v


def recommend(width, height, fps, use="streaming") -> dict:
    """按分辨率/帧率给出 Theora 编码起点建议 (永不抛错).

    ``use="streaming"`` (默认, 含未知取值回退) -> ``CBR-target``
    (``-b:v`` + notes 给 2-pass/硬 CBR 整形法);
    ``use`` 为 ``archive`` / ``quality`` / ``vbr`` -> ``VBR-quality``
    (``-q:v`` quality 档).
    """
    try:
        w = int(_num(width, 640))
        h = int(_num(height, 480))
        f = _num(fps, 30.0)
        w = max(16, min(8192, w))
        h = max(16, min(8192, h))
        f = max(1.0, min(120.0, f))
        try:
            u = str(use or "streaming").strip().lower()
        except Exception:
            u = "streaming"

        px = w * h
        label, kbps, quality = _LADDER[-1][1], _LADDER[-1][2], _LADDER[-1][3]
        for lim, name, kb, q in _LADDER:
            if px <= lim:
                label, kbps, quality = name, kb, q
                break
        if px > _LADDER[-1][0]:
            label, kbps, quality = ">1080p", 8000, 6

        # 高帧率按比例上浮, 封顶 1.5x; 低帧率不下调 (保单帧质量).
        try:
            factor = min(max(f / 30.0, 1.0), 1.5)
        except Exception:
            factor = 1.0
        kbps = max(100, int(round(kbps * factor / 100.0) * 100))

        if u in ("archive", "quality", "vbr", "vbr-quality"):
            mode = "VBR-quality"
            native = round(quality * NATIVE_SCALE, 1)
            args = ["-c:v", ENCODER, "-q:v", str(quality)]
            notes = (
                "VBR 恒定质量: quality=%d (native %.1f, 即 %d*6.3); "
                "同档位高复杂度场景码率上浮属正常. GOP 用 -g (如 96~128), "
                "音频配 libvorbis. 档位含义见 docs/rates/theora.md."
                % (quality, native, quality)
            )
            bitrate = None
        else:
            if u not in ("streaming", "cbr", "cbr-target"):
                u = "streaming"
            mode = "CBR-target"
            args = ["-c:v", ENCODER, "-b:v", "%dk" % kbps]
            notes = (
                "1-pass -b:v 为软目标 (长期均值, 复杂场景允许上冲); "
                "要收紧做 2-pass (-pass 1/2, 见文档), 硬 CBR 再加 "
                "-minrate=-maxrate + -bufsize 做 VBV 整形 (会以画质为代价). "
                "%s@%g fps 起点 %d kbps; 高帧率已按比例上浮."
                % (label, f, kbps)
            )
            bitrate = kbps
            quality_out = None
            return {
                "codec": "theora",
                "encoder": ENCODER,
                "container": CONTAINER,
                "pixel_format": "yuv420p",
                "mode": mode,
                "use": u,
                "width": w,
                "height": h,
                "fps": f,
                "bucket": label,
                "quality": quality_out,
                "bitrate_kbps": bitrate,
                "ffmpeg_args": args,
                "notes": notes,
            }

        if px > 921600:
            notes += " >720p 已超出 Theora 舒适区 (效率约为 H.264 的 2/3), 存档建议换 VP9/AV1."
        return {
            "codec": "theora",
            "encoder": ENCODER,
            "container": CONTAINER,
            "pixel_format": "yuv420p",
            "mode": mode,
            "use": u,
            "width": w,
            "height": h,
            "fps": f,
            "bucket": label,
            "quality": quality,
            "quality_native": round(quality * NATIVE_SCALE, 1),
            "bitrate_kbps": bitrate,
            "ffmpeg_args": args,
            "notes": notes,
        }
    except Exception as e:  # 永不抛错: 最小可用回退
        try:
            msg = "输入解析失败 (%s), 已回退 480p@30 默认值." % type(e).__name__
        except Exception:
            msg = "fallback defaults."
        return {
            "codec": "theora",
            "encoder": ENCODER,
            "container": CONTAINER,
            "pixel_format": "yuv420p",
            "mode": "CBR-target",
            "use": "streaming",
            "width": 640,
            "height": 480,
            "fps": 30.0,
            "bucket": "480p",
            "quality": None,
            "bitrate_kbps": 1000,
            "ffmpeg_args": ["-c:v", ENCODER, "-b:v", "1000k"],
            "notes": msg,
        }


def paint_hint() -> str:
    """Qt overlay 画法提示 (与 codec_theora_av1 配套)."""
    try:
        return (
            "theora-dots: 8x8 DCT 块点阵 (block-noise 点风格, 橙色点, "
            "超 900 块时抽样绘制; 见 codec_theora_av1.paint_superblock_overlay)."
        )
    except Exception:
        return "theora-dots"
