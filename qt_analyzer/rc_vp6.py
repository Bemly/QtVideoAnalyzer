"""VP6 码率 / profile 速查数据模块（纯文献口径，无第三方依赖，永不抛错）。

文献依据（本机无 VP6 编码器，见下“编码器现状”；数值均为文献值，非实测）：
* profile：Zencoder VP6 Settings `vp6_profile`：``vp6s / vp6e``（默认 vp6e 通用；
  vp6s 针对高分辨率/高码率降低解码复杂度，适配弱解码机）。
  本模块按任务口径写作 ``VP6-S`` / ``VP6-E``。
* alpha：Zencoder `alpha_transparency=true` 切到 VP6A 编码（ffmpeg 侧解码器
  ``vp6a`` 即“带 alpha 的 VP6”）；本模块把 alpha 路径归入 ``VP6-E``。
* 采样：4:2:0（yuv420p 为主）。
* RC：VBR 两遍（`vp6_2pass_min_section` 默认 40%，`vp6_2pass_max_section`
  默认 400%）/ CBR 单遍（`constant_bitrate`，Zencoder 明确“同码率明显不如
  VBR，非必须不用”，且 CBR 下 temporal resampling 被强制打开）。
* bpp 经验式：``bpp = video_bitrate / (w*h*fps)``；Zencoder 以 bpp < 0.07
  为界默认打开 temporal resampling（600kbps @640x480x30 = 0.065 即开）。
* Flash 时代常用口径 400~1500kbps（SD 主力区间）。
* 参考结构：只有 I/P，无 B 帧；单 Golden 参考，关键帧即 Golden
 （见 ``codec_vp.describe("vp6")``）。

编码器现状（2026-10-23 本机实测）：``ffmpeg -encoders | grep vp6`` 无输出，
``ffmpeg -h encoder=vp6`` 报“no encoders”；解码器仅 ``vp6 / vp6a / vp6f``。
上游 FFmpeg 已移除 vp6f 编码器，故本模块为纯数据模块，不做任何编码调用。
"""

from __future__ import annotations

__all__ = [
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
]

# 目标 bpp（文献经验）：streaming/CBR 取 0.10 强约束；VOD/VBR 两遍效率高取 0.085。
_BPP = {"streaming": 0.10, "vod": 0.085}
# Flash 时代 SD 主力口径（文献区间，仅用于 doc/note，不做硬钳制）。
_FLASH_RANGE_KBPS = (400, 1500)


def profiles() -> list:
    """返回 ``["VP6-S", "VP6-E"]``。永不抛错。"""
    try:
        return ["VP6-S", "VP6-E"]
    except Exception:
        return ["VP6-S", "VP6-E"]


def chroma_modes() -> list:
    """返回 ``["420"]``（VP6 只有 4:2:0）。永不抛错。"""
    try:
        return ["420"]
    except Exception:
        return ["420"]


def rc_modes() -> list:
    """返回 ``["VBR", "CBR"]``。永不抛错。"""
    try:
        return ["VBR", "CBR"]
    except Exception:
        return ["VBR", "CBR"]


def _num(x, default):
    try:
        v = float(x)
        if v != v or v in (float("inf"), float("-inf")):  # NaN/Inf
            return default
        return v
    except Exception:
        return default


def recommend(width, height, fps, use="streaming") -> dict:
    """给定分辨率/帧率返回推荐码率字典。任何输入都不抛错。

    ``use``：``"streaming"``（默认，CBR 单遍，FLV 渐进/推送口）/
    ``"vod"``/``"archive"``/``"file"``（VBR 两遍，落盘点播）/
    ``"alpha"``（带透明通道，走 VP6-E/VP6A 路径，VBR 两遍）。
    未知取值回退为 ``"streaming"``。
    """
    try:
        w = _num(width, 640.0)
        h = _num(height, 480.0)
        f = _num(fps, 30.0)
        w = min(8192.0, max(16.0, w))
        h = min(8192.0, max(16.0, h))
        f = min(120.0, max(1.0, f))
        try:
            u = str(use or "streaming").strip().lower()
        except Exception:
            u = "streaming"
        if u in ("vod", "archive", "file", "vbr", "2pass", "two-pass"):
            key, rc, passes = "vod", "VBR", 2
        elif u in ("alpha", "vp6a", "transparency"):
            key, rc, passes = "vod", "VBR", 2
        else:  # streaming / live / cbr / 未知 -> streaming
            key, rc, passes = "streaming", "CBR", 1

        bpp = _BPP[key]
        bitrate = int(round(bpp * w * h * f / 1000.0))
        bitrate = min(8000, max(64, bitrate))
        if rc == "VBR":
            maxrate = int(round(bitrate * 2.0))  # 峰值按 2x 估（两遍 max_section 上限 400%）
            gmin = 30
        else:
            maxrate = int(round(bitrate * 1.15))  # CBR 强约束，峰值贴目标
            gmin = 30
        golden = int(round(f * 2.0))  # Golden/关键帧间隔 ~2s
        golden = min(300, max(gmin, golden))

        # profile：高分辨率或高码率走 VP6-S（降解码复杂度），alpha/通用走 VP6-E。
        if u in ("alpha", "vp6a", "transparency"):
            profile = "VP6-E"
        elif (w * h >= 1280 * 720) or (bitrate >= 1200):
            profile = "VP6-S"
        else:
            profile = "VP6-E"

        lo, hi = _FLASH_RANGE_KBPS
        if rc == "VBR":
            note = (f"VBR 两遍（min_section 40% / max_section 400%，Zencoder 默认）；"
                    f"bpp≈{bpp}；Flash SD 口径 {lo}~{hi}kbps 供参考。")
        else:
            note = (f"CBR 单遍（temporal resampling 被强制打开，低 bpp 会掉帧保码率）；"
                    f"bpp≈{bpp}；Flash SD 口径 {lo}~{hi}kbps 供参考。")
        if profile == "VP6-E" and u in ("alpha", "vp6a", "transparency"):
            note += "alpha 路径实际编码为 VP6A（ffprobe/vp6a 解码）。"
        return {
            "profile": profile,
            "chroma": "420",
            "rc": rc,
            "bitrate_kbps": bitrate,
            "max_bitrate_kbps": maxrate,
            "passes": passes,
            "golden_interval": golden,
            "gop": golden,
            "b_frames": False,
            "note": note,
        }
    except Exception:
        return {
            "profile": "VP6-E",
            "chroma": "420",
            "rc": "CBR",
            "bitrate_kbps": 922,
            "max_bitrate_kbps": 1060,
            "passes": 1,
            "golden_interval": 60,
            "gop": 60,
            "b_frames": False,
            "note": "fallback（输入异常）：640x480x30 streaming 档。",
        }


def paint_hint() -> str:
    """返回 UI 叠加层一句话提示。永不抛错。"""
    try:
        return ("VP6：IPP 节奏（无 B 帧，REORDER 平坦），BITRATE 峰即关键帧"
                "（key=Golden，单 Golden 参考）；VBR 两遍峰更尖，CBR 单遍更平。")
    except Exception:
        return "VP6"
