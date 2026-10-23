"""MPEG-2 profile / 采样 / 码率控制速查 (可复用数据模块)。

口径 (本机实测 ffmpeg 9.0.2, ``ffmpeg -hide_banner -h encoder=mpeg2video``)::

    General capabilities: dr1 delay threads reorderedopaque
    Threading capabilities: slice
    Supported pixel formats: yuv420p yuv422p

关键结论: 原生 ``mpeg2video`` 编码器**无 ``-profile`` / ``-level`` 开关**
(``-h`` 全 81 行无 profile/level 项), profile×level 是 MPEG-2
规范 (ISO/IEC 13818-2) 层的约束概念, 不是本机编码器旋钮; 采样经
``-pix_fmt yuv420p`` (主力) / ``yuv422p`` (422P 演播室) 选择; 码率控制
经 ``-b:v`` / ``-minrate`` / ``-maxrate`` / ``-bufsize`` (CBR/VBR) 或
``-q:v`` (CQP 定量化器) 实现。

统一接口 (无第三方依赖, 永不抛错)::

    profiles()                        # ["Simple","Main","SNR","Spatial","High","422P","HighP"]
    chroma_modes()                    # ["420","422"]
    rc_modes()                        # ["CBR","VBR","CQP"]
    recommend(1920, 1080, 25)         # {"bitrate_kbps":..., "ffmpeg_args":[...], "notes":...}
    paint_hint()                      # 本工具 6 联图联动一句话
"""

from __future__ import annotations

# 规范 profile 全集 ("HighP" 为 High Profile 在部分工具/文档中的缩写,
# 与 "High" 同义, 此处并列是为覆盖任务口径的 7 个 token)。
_PROFILES = ("Simple", "Main", "SNR", "Spatial", "High", "422P", "HighP")

# 采样模式 -> ffmpeg pix_fmt 映射。
_CHROMA_PIX_FMT = {"420": "yuv420p", "422": "yuv422p"}

# DVD 规范上限: 视频+音频+系统总计 ~9.8Mbps, 视频常用 4~8Mbps。
_DVD_CEIL_KBPS = 9000
# MPEG-2 High Level 规范上限 80Mbps; 广播口径取 15~50Mbps。
_HL_CEIL_KBPS = 80000


def profiles() -> list:
    """MPEG-2 profile 名单 (规范层概念, 本机编码器无对应开关)。"""
    try:
        return list(_PROFILES)
    except Exception:
        return ["Main"]


def chroma_modes() -> list:
    """采样模式: ``420`` 主力 / ``422`` (422P 演播室)。"""
    try:
        return ["420", "422"]
    except Exception:
        return ["420"]


def rc_modes() -> list:
    """码率控制模式: CBR / VBR / CQP (定量化器, 分析测试用)。"""
    try:
        return ["CBR", "VBR", "CQP"]
    except Exception:
        return ["CBR"]


def _guess_level(w: int, h: int) -> str:
    """按分辨率估 level: LL/ML/H14/HL (规范上限见 docs/rates/mpeg2.md)。"""
    try:
        px = int(w) * int(h)
    except Exception:
        return "ML"
    if px <= 352 * 288:
        return "LL"
    if px <= 720 * 576:
        return "ML"
    if px <= 1440 * 1152:
        return "H14"
    return "HL"


def recommend(width, height, fps, use: str = "broadcast") -> dict:
    """给定规格推荐码率 + 可直接用的 ffmpeg 参数。永不抛错。

    ``use``: ``"broadcast"`` (广播/演播室口径 15~50Mbps, VBR) 或
    ``"dvd"`` (DVD 口径 4~9Mbps, CBR 锁 VBV)。大小写/前后空格容忍,
    非法值回退 ``"broadcast"``。``fps <= 0`` / 非法输入回退 25fps。
    4K 等超 HL 规格钳位到 50000kbps 并在 notes 注明超规。
    """
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
        f = 25.0
    if w <= 0:
        w = 1920
    if h <= 0:
        h = 1080
    if not (f > 0):
        f = 25.0
    try:
        u = str(use).strip().lower()
    except Exception:
        u = "broadcast"
    if u not in ("broadcast", "dvd"):
        u = "broadcast"

    px = w * h
    # 基准档 (25fps 口径): SD / 720p / 1080 / 超 1080。
    if px <= 720 * 576:
        base_dvd, base_bc = 5000, 10000
        tier = "SD"
    elif px <= 1280 * 720:
        base_dvd, base_bc = 8000, 15000
        tier = "720p"
    elif px <= 1920 * 1152:
        base_dvd, base_bc = _DVD_CEIL_KBPS, 20000
        tier = "1080"
    else:
        base_dvd, base_bc = _DVD_CEIL_KBPS, 40000
        tier = ">1080(超HL)"
    # 帧率缩放: 以 25fps 为基准, 钳位 0.5x~2.0x。
    try:
        scale = min(2.0, max(0.5, f / 25.0))
    except Exception:
        scale = 1.0

    if u == "dvd":
        bitrate = int(round(min(_DVD_CEIL_KBPS, max(4000, base_dvd * scale))))
        rc = "CBR"
        pix_fmt = _CHROMA_PIX_FMT["420"]
        # DVD VBV ~1.8Mbit, bufsize 取码率 1s 与 VBV 较大者? 实务取
        # 1835k 固定; 此处取 max(1835, bitrate) 简单可复现。
        bufsize = max(1835, bitrate)
        gop = "12" if f <= 30 else "15"
        args = [
            "-c:v", "mpeg2video",
            "-pix_fmt", pix_fmt,
            "-b:v", f"{bitrate}k",
            "-minrate", f"{bitrate}k",
            "-maxrate", f"{bitrate}k",
            "-bufsize", f"{bufsize}k",
            "-g", gop,
            "-bf", "2",
        ]
        notes = (
            f"DVD 口径 CBR {bitrate}kbps ({w}x{h}@{f:g}fps, {tier}): "
            "min=max=b 锁死 + bufsize 钳 VBV, 适配 DVD ~9.8Mbps 总线; "
            f"GOP IBBP -g {gop} -bf 2 (本工具测试片同款); "
            "pix_fmt yuv420p (DVD 只有 420)。"
        )
        if bitrate >= _DVD_CEIL_KBPS:
            notes += "已触 DVD 视频上限, 再涨需降分辨率/帧率或转 VBR 档案码。"
    else:
        bitrate = int(round(min(50000, max(8000, base_bc * scale))))
        rc = "VBR"
        pix_fmt = _CHROMA_PIX_FMT["420"]
        maxrate = min(50000, int(round(bitrate * 1.5)))
        bufsize = min(50000, bitrate * 2)
        gop = "12" if f <= 30 else "15"
        args = [
            "-c:v", "mpeg2video",
            "-pix_fmt", pix_fmt,
            "-b:v", f"{bitrate}k",
            "-maxrate", f"{maxrate}k",
            "-bufsize", f"{bufsize}k",
            "-g", gop,
            "-bf", "2",
        ]
        notes = (
            f"广播口径 VBR 目标 {bitrate}kbps (峰值 {maxrate}kbps, "
            f"{w}x{h}@{f:g}fps, {tier}): 15~50Mbps 口径内, 50/60fps 自动上浮; "
            f"GOP IBBP -g {gop} -bf 2; pix_fmt yuv420p 主力, 演播室 422 换 yuv422p。"
        )
        if tier.startswith(">1080"):
            notes += "分辨率超 MPEG-2 HL (1920x1152), 已钳 50Mbps, 建议换 AVC/HEVC。"
        if bitrate < 15000:
            notes += "SD 档低于 HD 广播 15M 下限属正常 (SD 档案/专线口径)。"

    try:
        level = _guess_level(w, h)
    except Exception:
        level = "ML"
    try:
        return {
            "use": u,
            "width": int(w),
            "height": int(h),
            "fps": float(f),
            "profile": "Main",
            "level": level,
            "chroma": "420",
            "rc": rc,
            "bitrate_kbps": int(bitrate),
            "ffmpeg_args": list(args),
            "notes": str(notes),
        }
    except Exception:
        return {
            "use": "broadcast",
            "width": 1920,
            "height": 1080,
            "fps": 25.0,
            "profile": "Main",
            "level": "HL",
            "chroma": "420",
            "rc": "VBR",
            "bitrate_kbps": 20000,
            "ffmpeg_args": ["-c:v", "mpeg2video", "-pix_fmt", "yuv420p",
                            "-b:v", "20000k", "-maxrate", "30000k",
                            "-bufsize", "40000k", "-g", "12", "-bf", "2"],
            "notes": "fallback: 广播口径 VBR 20000kbps (1080p25)。",
        }


def paint_hint() -> str:
    """本工具 6 联图联动一句话 (QPainter 覆盖层/面板提示用)。"""
    try:
        return (
            "MPEG-2 IBBP (-g 12 -bf 2): BITRATE 看 I 峰/P 腰/B 谷的 12 帧周期; "
            "REORDER 看 B 重排锯齿 (pts 文件序非单调属正常); "
            "CBR 看 VBV 平顶 (高动态只抬 QP 不抬码率), VBR 才有真峰谷。"
        )
    except Exception:
        return "MPEG-2 IBBP GOP=12."
