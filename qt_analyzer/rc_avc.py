"""AVC/H.264 profile/采样/码率控制数据模块(纯数据,无第三方依赖,永不抛错).

统一接口::

    profiles()      -> ["Baseline", "Main", ...]
    chroma_modes()  -> ["420", "422", "444"]
    rc_modes()      -> ["CRF", "CQP", "ABR", "CBR"]
    recommend(w, h, fps, use="streaming") -> dict  # bitrate_kbps 或 crf + ffmpeg_args + notes
    paint_hint()    -> str  # UI 一行提示

口径来源: ``ffmpeg -h encoder=libx264`` / ``-h encoder=mpeg4`` +
``x264 --fullhelp``(本机实测,见 ``docs/rates/avc.md``)。
只用标准库;任何非法输入都降级为默认值,永不抛错。
"""
from __future__ import annotations

__all__ = [
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
    "level_for",
]

# -- 本机实测 libx264 支持的 profile 名 (x264 --fullhelp "--profile" 节) --
_PROFILES = (
    "Baseline",
    "Main",
    "Extended",
    "High",
    "High10",
    "High422",
    "High444",
    "High444 Predictive",
)

_CHROMA = ("420", "422", "444")

_RC = ("CRF", "CQP", "ABR", "CBR")

# 分辨率档 -> (标签, 基准码率kbps@<=30fps, 存档CRF, 建议level, profile)
# 码率口径: 流媒体 1080p 8~12Mbps / 4K 35~45Mbps (取中 10M/40M);
# 低档按 YouTube/常见 ladder 外推。
_LADDER = (
    # max_h, max_w, label, kbps, crf, level
    (360, 640, "360p", 1000, 23, "3.0"),
    (480, 854, "480p", 2000, 22, "3.0"),
    (720, 1280, "720p", 5000, 22, "3.1"),
    (1080, 1920, "1080p", 10000, 21, "4.0"),
    (1440, 2560, "1440p", 16000, 21, "5.0"),
    (2160, 4096, "4K", 40000, 20, "5.1"),
)


def profiles() -> list[str]:
    """AVC profile 列表(规范口径,含 Predictive 系列)."""
    try:
        return list(_PROFILES)
    except Exception:
        return ["Baseline", "Main", "High"]


def chroma_modes() -> list[str]:
    """采样模式列表(与 pix_fmt yuv420p/422p/444p 对应)."""
    try:
        return list(_CHROMA)
    except Exception:
        return ["420"]


def rc_modes() -> list[str]:
    """码率控制模式列表."""
    try:
        return list(_RC)
    except Exception:
        return ["CRF"]


def level_for(width: int, height: int) -> str:
    """分辨率 -> 建议 H.264 level(Annex A 简表),非法输入回 "4.0"."""
    try:
        w = int(width)
        h = int(height)
    except Exception:
        return "4.0"
    try:
        for max_h, max_w, _label, _kbps, _crf, level in _LADDER:
            if h <= max_h and w <= max_w:
                return level
        return "5.1"
    except Exception:
        return "4.0"


def _ladder_row(width: int, height: int):
    try:
        w = int(width)
        h = int(height)
    except Exception:
        w, h = 1920, 1080
    if w <= 0 or h <= 0:
        w, h = 1920, 1080
    for max_h, max_w, label, kbps, crf, level in _LADDER:
        if h <= max_h and w <= max_w:
            return label, kbps, crf, level
    return "4K+", 40000, 20, "5.1"


def recommend(width, height, fps=30, use: str = "streaming") -> dict:
    """按分辨率/fps 给码率或 CRF 建议,永不抛错.

    ``use``: "streaming"(默认, CBR+VBV,给 ``bitrate_kbps``) /
    "archive"(CRF 存档,给 ``crf``) / 含 "cqp"/"abr"/"vbr" 子串的亦可
    识别,未知取值回退为 streaming。
    返回必含 ``ffmpeg_args``(示例串) 与 ``notes``。
    """
    try:
        use_s = str(use or "streaming").strip().lower()
    except Exception:
        use_s = "streaming"
    try:
        w = int(width)
    except Exception:
        w = 1920
    try:
        h = int(height)
    except Exception:
        h = 1080
    try:
        f = float(fps)
    except Exception:
        f = 30.0
    if w <= 0:
        w = 1920
    if h <= 0:
        h = 1080
    if not (f > 0) or f > 240:
        f = 30.0

    try:
        label, base_kbps, base_crf, level = _ladder_row(w, h)
    except Exception:
        label, base_kbps, base_crf, level = "1080p", 10000, 21, "4.0"

    # 高帧率加成: 30fps x1.0, 60fps x1.5, 上限 x2.0
    try:
        factor = 1.0 if f <= 30 else min(2.0, 1.0 + (f - 30.0) / 60.0)
        kbps = int(round(base_kbps * factor))
    except Exception:
        kbps = base_kbps
        factor = 1.0

    bufsize = kbps * 2  # VBV 常规: bufsize = 2 x maxrate
    gop = 60 if f <= 35 else int(round(f * 2))

    try:
        if "archiv" in use_s or "stor" in use_s or use_s == "crf":
            rc = "CRF"
            args = (
                f"ffmpeg -i in.mp4 -c:v libx264 -profile:v high -level {level} "
                f"-pix_fmt yuv420p -preset slow -crf {base_crf} "
                f"-g 250 -bf 3 out_avc.mp4"
            )
            notes = (
                f"{label}存档: CRF {base_crf}(越小越好,18~23常用), "
                "preset slow 以速度换压缩率; 本工具 QP 泳道带宽窄=I/P/B "
                "阶梯清晰即此档偏好。"
            )
            return {
                "width": w, "height": h, "fps": f, "use": "archive",
                "label": label, "profile": "High", "chroma": "420",
                "rc": rc, "crf": base_crf, "bitrate_kbps": None,
                "level": level, "ffmpeg_args": args, "notes": notes,
            }
        if "cqp" in use_s or use_s == "qp":
            qp = max(0, min(51, base_crf - 1))
            args = (
                f"ffmpeg -i in.mp4 -c:v libx264 -profile:v high -level {level} "
                f"-pix_fmt yuv420p -preset medium -qp {qp} "
                f"-g 250 -bf 3 out_avc.mp4"
            )
            notes = (
                f"{label}恒定 QP={qp}: 每宏块同量化, 无自适应, "
                "仅用于算法对比/压测, 正常存档请用 CRF。"
            )
            return {
                "width": w, "height": h, "fps": f, "use": "cqp",
                "label": label, "profile": "High", "chroma": "420",
                "rc": "CQP", "crf": None, "qp": qp,
                "bitrate_kbps": None, "level": level,
                "ffmpeg_args": args, "notes": notes,
            }
        if "abr" in use_s or "vbr" in use_s or "2pass" in use_s or "pass" in use_s:
            args = (
                f"ffmpeg -i in.mp4 -c:v libx264 -profile:v high -level {level} "
                f"-pix_fmt yuv420p -preset medium -b:v {kbps}k "
                f"-g {gop} -bf 3 -pass 2 out_avc.mp4"
            )
            notes = (
                f"{label}平均码率 {kbps}k(2-pass ABR): 文件体积可预期, "
                "质量波动大于 CRF; 一遍统计+二遍分配, 适合点播转码。"
            )
            return {
                "width": w, "height": h, "fps": f, "use": "abr",
                "label": label, "profile": "High", "chroma": "420",
                "rc": "ABR", "crf": None, "bitrate_kbps": kbps,
                "level": level, "ffmpeg_args": args, "notes": notes,
            }
        # 默认 streaming: CBR + VBV
        args = (
            f"ffmpeg -i in.mp4 -c:v libx264 -profile:v high -level {level} "
            f"-pix_fmt yuv420p -preset veryfast -tune zerolatency "
            f"-b:v {kbps}k -maxrate {kbps}k -bufsize {bufsize}k "
            f"-g {gop} -bf 3 out_avc.mp4"
        )
        notes = (
            f"{label}直播 {kbps}k CBR(VBV maxrate=bufsize/2): "
            "BITRATE 泳道见平顶即限幅器起作用; "
            "zerolatency 关 B 帧/lookahead 以换低延迟, 画质略降。"
        )
        return {
            "width": w, "height": h, "fps": f, "use": "streaming",
            "label": label, "profile": "High", "chroma": "420",
            "rc": "CBR", "crf": None, "bitrate_kbps": kbps,
            "level": level, "ffmpeg_args": args, "notes": notes,
        }
    except Exception:
        # 终极兜底: 绝不抛错
        return {
            "width": 1920, "height": 1080, "fps": 30.0, "use": "streaming",
            "label": "1080p", "profile": "High", "chroma": "420",
            "rc": "CBR", "crf": None, "bitrate_kbps": 10000,
            "level": "4.0",
            "ffmpeg_args": "ffmpeg -i in.mp4 -c:v libx264 -profile:v high "
                           "-pix_fmt yuv420p -preset veryfast -b:v 10000k "
                           "-maxrate 10000k -bufsize 20000k out_avc.mp4",
            "notes": "fallback: 默认 1080p 直播 10Mbps CBR。",
        }


def paint_hint() -> str:
    """UI 一行提示(QP/CBR 联动判读)."""
    try:
        return ("AVC: High@L4.0·420 8-bit·存档 CRF 18~23 / 直播 CBR+VBV; "
                "QP 泳道带宽窄=CRF 档好, BITRATE 平顶=CBR 限幅起作用。")
    except Exception:
        return "AVC"
