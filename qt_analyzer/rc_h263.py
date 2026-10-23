"""H.263 profile / 采样 / 码率速查 + 可复用数据模块。

只依赖标准库（无第三方 import），所有公开函数永不抛错：
参数非法时回退默认值，保证调用方（UI / 脚本）无需 try/except。

统一接口（与其它 ``rc_*`` 模块对齐）：

* ``profiles()`` -- ``["Baseline", "H.263+", "H.263++"]``
* ``chroma_modes()`` -- ``["420"]``（H.263 只有 4:2:0，本机两编码器
  ``Supported pixel formats`` 均为 ``yuv420p``）
* ``rc_modes()`` -- ``["CBR", "VBR"]``（CBR 为主，见 ``recommend``）
* ``recommend(width, height, fps, use="videoconf")`` -- 会议口径码率 +
  可直接拼 ``ffmpeg`` 命令的 ``ffmpeg_args`` + ``notes``
* ``paint_hint()`` -- 一句话看图提示（纯前向 arcs / REORDER 零线 /
  QP 宽台阶 / GOB 行条）

实测环境：``ffmpeg 9.0.2``（``-h encoder=h263`` / ``h263p``），
证据见 ``docs/rates/h263.md``。
"""
from __future__ import annotations

__all__ = [
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
    "ANNEX_FLAGS",
    "PICTURE_FORMATS",
]

#: profile 名（Annex X 口径；ffmpeg 本机无 ``-profile`` 开关，
#: 用 ``h263`` = Baseline / ``h263p`` = H.263+ 两个编码器区分）。
_PROFILES = ("Baseline", "H.263+", "H.263++")

#: Annex -> (中文名, 本机 ffmpeg h263p 开关；None = 本机构建未暴露该开关)。
ANNEX_FLAGS = {
    "D": ("无限制运动矢量 UMV", "-umv"),
    "F": ("高级预测（OBMC + 4MV）", "-obmc"),
    "I": ("高级帧内编码 AIC", None),
    "J": ("去块滤波", None),
    "T": ("修正量化（扩展 QP 范围）", None),
    "S": ("替换 inter VLC", "-aiv"),
    "K": ("条带结构", "-structured_slices"),
}

#: Baseline 固定图像格式（``h263`` 编码器硬限制，非标尺寸直接报错；
#: ``h263p`` 任意尺寸。本机实测 640x360 + ``-c:v h263`` 被拒）。
PICTURE_FORMATS = {
    "SQCIF": (128, 96),
    "QCIF": (176, 144),
    "CIF": (352, 288),
    "4CIF": (704, 576),
    "16CIF": (1408, 1152),
}

#: 会议头肩像 bpp（bits per pixel）：CIF 352x288@15 -> ~182k，snap 后 192k。
_BPP = {"videoconf": 0.12, "3g": 0.10}

#: 码率梯子（bps），recommend 按“就高 snap”，档位即常见会议/3G 口径。
_LADDER = (
    24000, 32000, 48000, 64000, 96000, 128000, 192000,
    256000, 384000, 512000, 768000, 1000000,
)

_DEF_W, _DEF_H, _DEF_FPS = 352, 288, 15


# ------------------------------------------------------------------ 公开接口

def profiles() -> list[str]:
    """可用 profile 名。"""
    try:
        return list(_PROFILES)
    except Exception:
        return ["Baseline"]


def chroma_modes() -> list[str]:
    """色度采样：H.263 只有 4:2:0。"""
    try:
        return ["420"]
    except Exception:
        return ["420"]


def rc_modes() -> list[str]:
    """码率控制模式：CBR 为主（会议/3G 固定管道），VBR 为辅。"""
    try:
        return ["CBR", "VBR"]
    except Exception:
        return ["CBR"]


def _num(v, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return default
    return f


def recommend(width, height, fps, use: str = "videoconf") -> dict:
    """给定分辨率/帧率，返回会议口径码率建议（永不抛错）。

    参数非法（非数字/<=0/NaN）时按 ``352x288@15`` 回退；``use`` 未知
    按 ``"videoconf"`` 处理。``use="3g"`` 走 3G-324M 口径（上限 64k）。

    返回 dict 必含 ``bitrate`` (int, bps) / ``ffmpeg_args`` (list[str],
    CBR，可直接拼到 ``ffmpeg`` 命令行) / ``notes`` (list[str])，
    另带 ``rc_mode`` / ``profile`` / ``chroma`` / ``width`` / ``height`` /
    ``fps`` / ``use`` 供调用方展示。
    """
    try:
        w = int(_num(width, _DEF_W))
        h = int(_num(height, _DEF_H))
        f = _num(fps, _DEF_FPS)
        if w <= 0:
            w = _DEF_W
        if h <= 0:
            h = _DEF_H
        if f <= 0:
            f = float(_DEF_FPS)
        w = min(w, 2048)
        h = min(h, 2048)
        f = min(max(f, 1.0), 60.0)

        try:
            u = str(use or "videoconf").strip().lower()
        except Exception:
            u = "videoconf"
        is_3g = "3g" in u or "324" in u
        bpp = _BPP["3g"] if is_3g else _BPP["videoconf"]

        raw = w * h * f * bpp
        if is_3g:
            lo, hi = 24000, 64000
        else:
            lo, hi = 64000, 1000000
        raw = min(max(raw, lo), hi)
        bitrate = hi
        for step in _LADDER:
            if step >= raw and lo <= step <= hi:
                bitrate = step
                break

        kb = max(1, int(round(bitrate / 1000.0)))
        gop = int(max(30, min(300, round(f * 4))))
        args = [
            "-c:v", "h263p", "-pix_fmt", "yuv420p",
            "-b:v", f"{kb}k", "-minrate", f"{kb}k",
            "-maxrate", f"{kb}k", "-bufsize", f"{2 * kb}k",
            "-g", str(gop), "-bf", "0",
        ]
        if is_3g:
            args[1] = "h263" if (w, h) in PICTURE_FORMATS.values() else "h263p"

        notes = [
            f"CBR 为主：目标 {kb}kbps（-b:v/-minrate/-maxrate 同值，"
            f"bufsize {2 * kb}k 吸收 I 帧尖峰）。",
            "无 B 帧：全片只有 I/P，P 帧偏大、I 帧尖峰更陡；"
            "同画质平均码率约 AVC 的 2x，CBR 缓冲要留足。",
            "VBR 备选：去掉 -minrate，改 -qscale:v 2..5（本机已验证可编），"
            "画质稳但管道峰值不可控，会议慎用。",
        ]
        if is_3g:
            notes.append(
                "3G-324M 口径：64k 电路与 AMR 音频共享，视频一般只剩 "
                "~48k，多用 QCIF 10~15fps。"
            )
        else:
            notes.append(
                "会议口径 64kbps~1Mbps：QCIF 取 64k 起，CIF 128~384k，"
                "4CIF 往 1M 顶；超大分辨率会被钳到 1M（H.263 时代上限）。 "
                "注：-bufsize 按 2x 目标给，RTP 可另加 -ps 按 MTU 分片。"
            )
        if (w, h) not in PICTURE_FORMATS.values():
            notes.append(
                f"{w}x{h} 非 Baseline 固定尺寸，必须用 h263p（H.263+）；"
                "ffmpeg -c:v h263 会直接报错。"
            )

        return {
            "bitrate": int(bitrate),
            "ffmpeg_args": args,
            "notes": notes,
            "rc_mode": "CBR",
            "profile": "H.263+",
            "chroma": "420",
            "width": w,
            "height": h,
            "fps": f,
            "use": "3g" if is_3g else "videoconf",
        }
    except Exception:
        return {
            "bitrate": 192000,
            "ffmpeg_args": [
                "-c:v", "h263p", "-pix_fmt", "yuv420p",
                "-b:v", "192k", "-minrate", "192k",
                "-maxrate", "192k", "-bufsize", "384k",
                "-g", "60", "-bf", "0",
            ],
            "notes": ["参数异常，已回退 CIF@15 默认建议（192k CBR）。"],
            "rc_mode": "CBR",
            "profile": "H.263+",
            "chroma": "420",
            "width": _DEF_W,
            "height": _DEF_H,
            "fps": float(_DEF_FPS),
            "use": "videoconf",
        }


def paint_hint() -> str:
    """一句话看图提示（供 overlay / 图例旁注）。"""
    try:
        return (
            "H.263：纯前向 arcs（无 B 帧）+ REORDER 零线（pts==dts）"
            "+ QP 宽台阶（量化档粗）+ GOB 行条 overlay（每 48px 一条）。"
        )
    except Exception:
        return "H.263"
