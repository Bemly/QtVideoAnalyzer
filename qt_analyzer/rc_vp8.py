"""VP8 profile / 采样 / 码率控制速查（可复用数据模块）。

只用标准库，永不抛错，供 UI / 文档 / 脚本复用。

口径来源：
* 本机 ``ffmpeg -hide_banner -h encoder=libvpx``（ffmpeg 9.0.2）：
  ``Supported pixel formats: yuv420p yuva420p``（仅 420 采样），
  无 ``-profile`` 选项（profile 是码流头 2 bit，见 RFC 6386）；
  ``-lag-in-frames`` / ``-auto-alt-ref`` / ``-cpu-used`` /
  ``-deadline`` / ``-crf`` / ``-undershoot-pct`` / ``-overshoot-pct`` 俱在。
* WebM VP8 Encode Parameter Guide（webmproject.org/docs/encoder-parameters）：
  ``--profile`` 0~3，默认/推荐 0；非 0 档为低功耗播放降复杂度（如档 1 只用
  双线性子像素 + 简化环路滤波），代价是编码质量下降。
* RFC 6386：VP8 为 420 / 8bit / 逐行设计（最大 16383x16383）。

统一接口（与其它 ``rc_*`` 模块一致）：
``profiles`` / ``chroma_modes`` / ``rc_modes`` / ``recommend`` / ``paint_hint``。
"""
from __future__ import annotations

__all__ = [
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
    "BITRATE_LADDER_KBPS",
    "PROFILE_TABLE",
]

#: 按高度分档的基准码率（720p30 = 2500k 起点，WebRTC/流媒体常用口径）。
#: 键为高度上限（含），值为该档 30fps 基准视频码率（kbps）。
BITRATE_LADDER_KBPS = (
    (270, 400),
    (360, 800),
    (480, 1200),
    (720, 2500),
    (1080, 4500),
    (1440, 9000),
    (10 ** 9, 16000),
)

#: VP8 profile 表（RFC 6386 码流头 2 bit；WebM 用 profile 0）。
PROFILE_TABLE = (
    ("0", "WebM 默认/推荐", "全功能：6 抽头子像素 + 完整 in-loop 滤波，本工具按此口径"),
    ("1", "低复杂度", "双线性子像素 + 简化环路滤波，低功耗设备用，质量下降"),
    ("2", "更低复杂度", "在 1 档上继续降解码复杂度，质量再降"),
    ("3", "最低复杂度/保留", "实现定义/保留，兼容性最差，按 0 处理即可"),
)


# ------------------------------------------------------------------ 基础表

def profiles() -> list:
    """VP8 profiles（WebM 用 profile 0 口径）。永不抛错。"""
    try:
        return ["0", "1", "2", "3"]
    except Exception:
        return ["0"]


def chroma_modes() -> list:
    """VP8 采样（仅 420：yuv420p / yuva420p，alpha 仍是 420 子采样）。永不抛错。"""
    try:
        return ["420"]
    except Exception:
        return ["420"]


def rc_modes() -> list:
    """libvpx 码率控制三档：CQ（恒质量）/ VBR（变码率）/ CBR（恒码率）。永不抛错。"""
    try:
        return ["CQ", "VBR", "CBR"]
    except Exception:
        return ["CQ", "VBR", "CBR"]


# ------------------------------------------------------------------ 推荐

def _num(x, default: float) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    try:
        if v != v or v in (float("inf"), float("-inf")):  # NaN/Inf
            return default
    except Exception:
        return default
    return v


def _norm_use(use) -> str:
    try:
        u = str(use or "realtime").strip().lower().replace(" ", "").replace("_", "-")
    except Exception:
        return "realtime"
    if u in ("realtime", "rt", "live", "webrtc", "cbr", "low-latency", "lowlatency"):
        return "realtime"
    if u in ("vod", "archive", "file", "good", "vbr", "2-pass", "2pass", "ondemand"):
        return "vod"
    if u in ("cq", "crf", "quality", "const-quality", "constquality"):
        return "cq"
    return "realtime"  # 未知一律回落到实时 CBR（低延迟最安全）


def _ladder_kbps(height: float) -> int:
    try:
        h = float(height)
    except Exception:
        h = 720.0
    if not (h > 0):
        h = 720.0
    for bound, kbps in BITRATE_LADDER_KBPS:
        if h <= bound:
            return kbps
    return 16000


def recommend(width, height, fps, use: str = "realtime") -> dict:
    """按分辨率/帧率给码率 + ffmpeg 参数建议。永不抛错。

    ``use``：``"realtime"``（默认，WebRTC/低延迟直播 -> CBR）/
    ``"vod"``（点播归档 -> VBR 2-pass）/ ``"cq"``（恒质量单遍 -> CQ）。
    未知取值回落 ``realtime`` 并在 notes 注明。

    返回键：``mode`` / ``bitrate_kbps`` / ``crf``（仅 CQ 有值，其余 None）/
    ``cpu_used`` / ``deadline`` / ``ffmpeg_args`` / ``notes``。
    """
    try:
        w = _num(width, 1280.0)
        h = _num(height, 720.0)
        f = _num(fps, 30.0)
        if not (w > 0):
            w = 1280.0
        if not (h > 0):
            h = 720.0
        if not (f > 0):
            f = 30.0
        if w > 16383:
            w = 16383.0
        if h > 16383:
            h = 16383.0
        kind = _norm_use(use)

        base = _ladder_kbps(h)
        # 帧率缩放：以 30fps 为基准，钳制 0.5x~2.0x（60fps 取 1.5x 侧已够用，取整到 50k）。
        factor = min(max(f / 30.0, 0.5), 2.0)
        bitrate = int(round(base * factor / 50.0) * 50)
        if bitrate < 100:
            bitrate = 100

        if kind == "cq":
            crf = 12 if h <= 720 else 10  # VP8 -crf 0~63 越小越好，10~12 为常用起点
            args = ["-c:v", "libvpx", "-pix_fmt", "yuv420p",
                    "-b:v", "0", "-crf", str(crf),
                    "-deadline", "good", "-cpu-used", "1",
                    "-lag-in-frames", "25", "-auto-alt-ref", "1"]
            return {
                "mode": "CQ",
                "bitrate_kbps": 0,
                "crf": crf,
                "cpu_used": 1,
                "deadline": "good",
                "ffmpeg_args": args,
                "notes": ("CQ 单遍恒质量：-b:v 0 + -crf %d（0~63，越小越好）；"
                          "2-pass/AltRef 照常生效（-lag-in-frames 25），画质优先、"
                          "码率不封顶，适合母带/归档。" % crf),
            }
        if kind == "vod":
            mx = int(round(bitrate * 1.5 / 50.0) * 50)
            mn = max(int(round(bitrate * 0.5 / 50.0) * 50), 50)
            buf = bitrate * 2
            args = ["-c:v", "libvpx", "-pix_fmt", "yuv420p",
                    "-b:v", "%dk" % bitrate,
                    "-maxrate", "%dk" % mx, "-minrate", "%dk" % mn,
                    "-bufsize", "%dk" % buf,
                    "-deadline", "good", "-cpu-used", "1",
                    "-lag-in-frames", "25", "-auto-alt-ref", "1",
                    "-pass", "2"]
            return {
                "mode": "VBR",
                "bitrate_kbps": bitrate,
                "crf": None,
                "cpu_used": 1,
                "deadline": "good",
                "ffmpeg_args": args,
                "notes": ("VBR 点播：目标 %d kbps（±50%% 窗口，buf %d kbps），先跑 "
                          "-pass 1 再跑 -pass 2；-lag-in-frames 25 + -auto-alt-ref 1 "
                          "开 AltRef（滞后未来帧合成不可见参考帧），画质/码率最优；"
                          "-cpu-used 1（0 最慢最优，2 更快；4/5 关 RDO 大提速大降质）。 "
                          % (bitrate, buf)),
            }
        # realtime / CBR（默认）
        fell_back = False
        try:
            u = str(use or "realtime").strip().lower()
            fell_back = u not in ("realtime", "rt", "live", "webrtc", "cbr",
                                  "low-latency", "lowlatency", "low_latency")
        except Exception:
            fell_back = True
        args = ["-c:v", "libvpx", "-pix_fmt", "yuv420p",
                "-b:v", "%dk" % bitrate,
                "-minrate", "%dk" % bitrate, "-maxrate", "%dk" % bitrate,
                "-bufsize", "%dk" % bitrate,
                "-deadline", "realtime", "-cpu-used", "5",
                "-lag-in-frames", "0", "-auto-alt-ref", "0"]
        note = ("CBR 低延迟：三率相等 + buf 1 秒（%d kbps），-deadline realtime "
                "-cpu-used 5；-lag-in-frames 0 + -auto-alt-ref 0 主动关 AltRef "
                "（零前瞻、零额外延迟，丢包恢复快；rt 下 -cpu-used 为 cpu 占用目标 "
                "100*(16-N)/16%%，可放宽到 8~15 换更低占用）。"
                % bitrate)
        if fell_back:
            note += "（use=%r 未识别，已回落 realtime。）" % (use,)
        return {
            "mode": "CBR",
            "bitrate_kbps": bitrate,
            "crf": None,
            "cpu_used": 5,
            "deadline": "realtime",
            "ffmpeg_args": args,
            "notes": note,
        }
    except Exception as e:  # 最后一道防线：永不抛错
        try:
            return {
                "mode": "CBR",
                "bitrate_kbps": 2500,
                "crf": None,
                "cpu_used": 5,
                "deadline": "realtime",
                "ffmpeg_args": ["-c:v", "libvpx", "-pix_fmt", "yuv420p",
                                "-b:v", "2500k", "-minrate", "2500k",
                                "-maxrate", "2500k", "-bufsize", "2500k",
                                "-deadline", "realtime", "-cpu-used", "5",
                                "-lag-in-frames", "0", "-auto-alt-ref", "0"],
                "notes": "参数异常已回落 720p realtime 默认（%s）。" % e,
            }
        except Exception:
            return {"mode": "CBR", "bitrate_kbps": 2500, "crf": None,
                    "cpu_used": 5, "deadline": "realtime", "ffmpeg_args": [],
                    "notes": "fallback"}


def paint_hint() -> str:
    """UI 一句话提示（AltRef 金星标 + seg 层 + 无 B 排）。永不抛错。"""
    try:
        return ("VP8：周期 P 大包=AltRef（金★，key 即 Golden）；seg 0..3 四色层"
                "（蓝 -6 / 绿 0 / 黄 +6 / 红 +12）；全片应无 B 排（REORDER 平坦）。")
    except Exception:
        return "VP8"
