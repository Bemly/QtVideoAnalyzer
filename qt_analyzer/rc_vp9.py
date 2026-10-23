"""VP9 profile / 采样 / 码率控制速查 + 命令拼装（可复用数据模块）。

只用标准库，永不抛错，供 UI / 文档 / 脚本复用。

口径来源：
* 本机 ``ffmpeg -hide_banner -h encoder=libvpx-vp9``（ffmpeg 9.0.2，
  ``--enable-libvpx``）：``-crf`` / ``-auto-alt-ref`` / ``-lag-in-frames`` /
  ``-tile-columns`` / ``-tile-rows`` / ``-row-mt`` / ``-cpu-used`` /
  ``-deadline`` / ``-aq-mode`` / ``-arnr-*`` 俱在；profile 由 pix_fmt
  自动映射（实测见 ``docs/rates/vp9.md``），亦可用通用选项
  ``-profile:v 0..3`` 显式指定。
* VP9 规范 profile 定义：0 = 8bit 4:2:0；1 = 8bit 4:4:4；
  2 = 10/12bit 4:2:0；3 = 10/12bit 4:4:4。
* YouTube 上传推荐码率 SDR/HDR 全表（support.google.com/youtube/answer/1722171，
  2160p/8K 区间取中点做单值，见 ``YOUTUBE_SDR`` / ``YOUTUBE_HDR``）。

统一接口（与其它 ``rc_*`` 模块一致）：
``profiles`` / ``chroma_modes`` / ``rc_modes`` / ``recommend`` / ``paint_hint``。
``recommend`` 返回键在 ``rc_vp8`` 七键
（``mode`` / ``bitrate_kbps`` / ``crf`` / ``cpu_used`` / ``deadline`` /
``ffmpeg_args`` / ``notes``）之外，另加 VP9 特有键
（``tier`` / ``profile`` / ``pix_fmt`` / ``tiles`` / ``altref`` /
``ffmpeg_pass1`` / ``youtube_sdr`` / ``youtube_hdr``）。

与本工具联动：AltRef 开时 ``codec_vp.altref_markers()`` 判出周期性 P 大包
（GOP 条金★）；compound 双参考痕迹解释见
``codec_vp.compound_note("vp9")``。
"""
from __future__ import annotations

__all__ = [
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
    "PROFILE_TABLE",
    "YOUTUBE_SDR",
    "YOUTUBE_HDR",
]

#: VP9 profile 表（规范口径；ffmpeg 侧由 pix_fmt 自动映射，亦可用 -profile:v 指定）。
PROFILE_TABLE = (
    ("0", "8bit 4:2:0", "默认：yuv420p，WebM/SDR 主力，本工具按此口径"),
    ("1", "8bit 4:4:4", "yuv444p，高画质 archival / 屏幕内容"),
    ("2", "10/12bit 4:2:0", "HDR 主力：yuv420p10le，本机实测自动映射 Profile 2"),
    ("3", "10/12bit 4:4:4", "yuv444p10le/yuv444p12le，需 -profile:v 3 或自动映射"),
)

#: YouTube 官方上传推荐码率 SDR（support.google.com/youtube/answer/1722171）。
#: 键为档位；值为 (标准帧率 24/25/30, 高帧率 48/50/60) kbps。
#: 2160p/8K 官方给区间，取中点（2160p: 35-45->40000 / 53-68->60000）。
YOUTUBE_SDR = {
    "360p": (1000, 1500),
    "480p": (2500, 4000),
    "720p": (5000, 7500),
    "1080p": (8000, 12000),
    "1440p": (16000, 24000),
    "2160p": (40000, 60000),
    "4320p": (120000, 180000),
}

#: YouTube 官方上传推荐码率 HDR（同上来源；360p/480p 官方不支持 HDR）。
YOUTUBE_HDR = {
    "360p": (0, 0),
    "480p": (0, 0),
    "720p": (6500, 9500),
    "1080p": (10000, 15000),
    "1440p": (20000, 30000),
    "2160p": (50000, 75000),
    "4320p": (150000, 225000),
}

_TIER_ORDER = ("360p", "480p", "720p", "1080p", "1440p", "2160p", "4320p")


# ------------------------------------------------------------------ 基础表

def profiles() -> list:
    """VP9 profiles（0:420-8bit / 1:444-8bit / 2:420-10bit / 3:444-10/12bit）。永不抛错。"""
    try:
        return [
            "0: 8bit 4:2:0 (default · yuv420p)",
            "1: 8bit 4:4:4 (yuv444p)",
            "2: 10bit 4:2:0 (HDR 主力 · yuv420p10le)",
            "3: 10/12bit 4:4:4 (yuv444p10le / yuv444p12le)",
        ]
    except Exception:
        return ["0: 8bit 4:2:0"]


def chroma_modes() -> list:
    """VP9 采样（420 / 444，各自注明位深 -> profile 映射）。永不抛错。"""
    try:
        return [
            "420: 8bit -> profile 0 / 10-12bit -> profile 2（HDR 主力）",
            "444: 8bit -> profile 1 / 10-12bit -> profile 3",
        ]
    except Exception:
        return ["420", "444"]


def rc_modes() -> list:
    """libvpx-vp9 码率控制三档：CQ（恒质量）/ VBR（变码率）/ CBR（恒码率）。永不抛错。"""
    try:
        return ["CQ", "VBR", "CBR"]
    except Exception:
        return ["CQ", "VBR", "CBR"]


# ------------------------------------------------------------------ 内部换算

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
        u = str(use or "streaming").strip().lower().replace(" ", "").replace("_", "-")
    except Exception:
        return "streaming"
    if u in ("streaming", "live", "realtime", "rt", "webrtc", "cbr", "low-latency",
             "lowlatency"):
        return "streaming"
    if u in ("upload", "vod", "file", "vbr", "2-pass", "2pass", "ondemand", "youtube"):
        return "upload"
    if u in ("archive", "cq", "crf", "quality", "const-quality", "constquality"):
        return "archive"
    return "streaming"  # 未知一律回落 streaming（CBR 最稳妥）


def _tier(height: float) -> str:
    try:
        h = float(height)
    except Exception:
        h = 1080.0
    if not (h > 0):
        h = 1080.0
    if h >= 4320:
        return "4320p"
    if h >= 2160:
        return "2160p"
    if h >= 1440:
        return "1440p"
    if h >= 1080:
        return "1080p"
    if h >= 720:
        return "720p"
    if h >= 480:
        return "480p"
    return "360p"


def _tiles(width: float, height: float) -> tuple:
    """tile 列/行（log2 值）：列按宽度分档，行 tile 只 4K+ 开，两者正交可同开。"""
    try:
        w = float(width)
        h = float(height)
    except Exception:
        return (1, 0)
    cols = 2 if w >= 3840 else (1 if w >= 1280 else 0)
    rows = 1 if h >= 2160 else 0
    return (cols, rows)


# ------------------------------------------------------------------ 推荐

def recommend(width, height, fps, use: str = "streaming") -> dict:
    """按分辨率/帧率给 VP9 码率 + ffmpeg 参数建议。永不抛错。

    ``use``：``"streaming"``（默认，直播/推流 -> CBR 单遍，
    关 AltRef 零前瞻）/ ``"upload"``（点播上传 -> VBR 约束质量 2-pass，
    AltRef 全开）/ ``"archive"``（存档 -> CQ 单遍）。未知取值回落
    ``streaming`` 并在 notes 注明。

    返回键（``rc_vp8`` 七键 + VP9 特有键）：``mode`` / ``bitrate_kbps`` /
    ``crf``（仅 CQ 有值，其余 None）/ ``cpu_used`` / ``deadline`` /
    ``ffmpeg_args`` / ``notes`` / ``tier`` / ``profile`` / ``pix_fmt`` /
    ``tiles`` / ``altref`` / ``ffmpeg_pass1``（仅 VBR 有值）/
    ``youtube_sdr`` / ``youtube_hdr``（kbps）。
    """
    try:
        w = _num(width, 1920.0)
        h = _num(height, 1080.0)
        f = _num(fps, 30.0)
        if not (w > 0):
            w = 1920.0
        if not (h > 0):
            h = 1080.0
        if not (f > 0):
            f = 30.0
        if w > 7680:  # VP9 上限 16383x16383；8K 以上钳制不抛错
            w = 7680.0
        if h > 4320:
            h = 4320.0
        kind = _norm_use(use)

        tier = _tier(h)
        sdr = YOUTUBE_SDR.get(tier, YOUTUBE_SDR["1080p"])
        hdr = YOUTUBE_HDR.get(tier, YOUTUBE_HDR["1080p"])
        bitrate = sdr[1] if f > 30 else sdr[0]
        hdr_rate = hdr[1] if f > 30 else hdr[0]
        cols, rows = _tiles(w, h)
        tiles = {"tile-columns": cols, "tile-rows": rows, "row-mt": 1}

        if kind == "archive":
            # CQ 存档：FFmpeg VP9 wiki 口径 -b:v 0 -crf 30（CRF 越小越好）。
            crf = 30
            args = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-profile:v", "0",
                    "-b:v", "0", "-crf", str(crf),
                    "-deadline", "good", "-cpu-used", "1",
                    "-auto-alt-ref", "1", "-lag-in-frames", "25",
                    "-tile-columns", str(cols), "-tile-rows", str(rows),
                    "-row-mt", "1"]
            return {
                "mode": "CQ", "bitrate_kbps": 0, "crf": crf,
                "cpu_used": 1, "deadline": "good", "ffmpeg_args": args,
                "notes": ("CQ 存档单遍：-b:v 0 -crf %d（0 最好~63 最差，30 为 1080p 通用档，"
                          "4K 可降到 15~28）；码率由内容自适应（talking-head 远低于同档 "
                          "YouTube 口径，高运动可能超出）；-cpu-used 1，0 最慢最优、4/5 大提速大降质。"
                          % crf),
                "tier": tier, "profile": 0, "pix_fmt": "yuv420p",
                "tiles": tiles,
                "altref": {"auto-alt-ref": 1, "lag-in-frames": 25,
                           "note": "AltRef 开（滞后 25 帧合成不可见替代参考，只做预测不显示）"},
                "ffmpeg_pass1": [],
                "youtube_sdr": bitrate, "youtube_hdr": hdr_rate,
            }
        if kind == "upload":
            # VBR 上传：YouTube 口径目标 + -crf 33 封顶单帧质量（FFmpeg wiki 例值）。
            crf = 33
            mx = bitrate * 3 // 2
            mn = max(bitrate // 2, 50)
            buf = bitrate * 2
            common = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-profile:v", "0",
                      "-b:v", "%dk" % bitrate, "-crf", str(crf),
                      "-maxrate", "%dk" % mx, "-minrate", "%dk" % mn,
                      "-bufsize", "%dk" % buf,
                      "-auto-alt-ref", "1", "-lag-in-frames", "25",
                      "-tile-columns", str(cols), "-tile-rows", str(rows),
                      "-row-mt", "1"]
            args2 = common + ["-deadline", "good", "-cpu-used", "1", "-pass", "2"]
            args1 = common + ["-deadline", "good", "-cpu-used", "4", "-pass", "1"]
            hdr_txt = ("HDR 同档约 %.1f 倍码率（本档 HDR %s，10bit 请切 profile 2 + "
                       "yuv420p10le）。" % (_ratio(bitrate, hdr_rate),
                                            ("不支持" if hdr_rate <= 0
                                             else "%dk" % hdr_rate)))
            return {
                "mode": "VBR", "bitrate_kbps": bitrate, "crf": crf,
                "cpu_used": 1, "deadline": "good", "ffmpeg_args": args2,
                "notes": ("VBR 上传：目标 %d kbps（±50%% 窗口 max %d / min %d，buf %d kbps，"
                          "YouTube %s%s SDR 口径）；先跑 -pass 1（-an -f null 只统计）再跑 -pass 2 落盘；"
                          "-auto-alt-ref 1 + -lag-in-frames 25 全开（2-pass 下收益最大）；%s"
                          % (bitrate, mx, mn, buf, tier,
                             "高帧率" if f > 30 else "标准帧率", hdr_txt)),
                "tier": tier, "profile": 0, "pix_fmt": "yuv420p",
                "tiles": tiles,
                "altref": {"auto-alt-ref": 1, "lag-in-frames": 25,
                           "note": "AltRef 全开：BITRATE 图上每 ~10-30 帧一个显著高柱即 AltRef 参考帧"},
                "ffmpeg_pass1": args1,
                "youtube_sdr": bitrate, "youtube_hdr": hdr_rate,
            }
        # streaming / CBR（默认）：三率锁死 + buf 1 秒，关 AltRef 零前瞻（同 rc_vp8 口径）。
        fell_back = False
        try:
            u = str(use if use is not None else "streaming").strip().lower()
            fell_back = _norm_use(use) == "streaming" and u not in (
                "streaming", "live", "realtime", "rt", "webrtc", "cbr",
                "low-latency", "lowlatency", "low_latency")
        except Exception:
            fell_back = True
        args = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-profile:v", "0",
                "-b:v", "%dk" % bitrate,
                "-minrate", "%dk" % bitrate, "-maxrate", "%dk" % bitrate,
                "-bufsize", "%dk" % bitrate,
                "-deadline", "realtime", "-cpu-used", "5",
                "-auto-alt-ref", "0", "-lag-in-frames", "0",
                "-tile-columns", str(cols), "-tile-rows", str(rows),
                "-row-mt", "1"]
        note = ("CBR 推流：三率相等 + buf 1 秒（%d kbps，YouTube %s%s SDR 口径封顶参考），"
                "-deadline realtime -cpu-used 5（rt 下 cpu-used 为占用目标，可放宽到 8~15）；"
                "-auto-alt-ref 0 + -lag-in-frames 0 主动关 AltRef（零前瞻、零额外延迟，"
                "丢包恢复快；此时 BITRATE 图无周期大包属预期）；-row-mt 1 常开与 tile 正交。"
                % (bitrate, tier, "高帧率" if f > 30 else "标准帧率"))
        if fell_back:
            note += "（use=%r 未识别，已回落 streaming。）" % (use,)
        return {
            "mode": "CBR", "bitrate_kbps": bitrate, "crf": None,
            "cpu_used": 5, "deadline": "realtime", "ffmpeg_args": args,
            "notes": note,
            "tier": tier, "profile": 0, "pix_fmt": "yuv420p",
            "tiles": tiles,
            "altref": {"auto-alt-ref": 0, "lag-in-frames": 0,
                       "note": "AltRef 关（低延迟要求零前瞻；要点播收益请用 use='upload'）"},
            "ffmpeg_pass1": [],
            "youtube_sdr": bitrate, "youtube_hdr": hdr_rate,
        }
    except Exception as e:  # 最后一道防线：永不抛错
        try:
            return {
                "mode": "CBR", "bitrate_kbps": 8000, "crf": None,
                "cpu_used": 5, "deadline": "realtime",
                "ffmpeg_args": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p",
                                "-b:v", "8000k", "-minrate", "8000k",
                                "-maxrate", "8000k", "-bufsize", "8000k",
                                "-deadline", "realtime", "-cpu-used", "5",
                                "-auto-alt-ref", "0", "-lag-in-frames", "0"],
                "notes": "参数异常已回落 1080p streaming 默认（%s）。" % e,
                "tier": "1080p", "profile": 0, "pix_fmt": "yuv420p",
                "tiles": {"tile-columns": 1, "tile-rows": 0, "row-mt": 1},
                "altref": {"auto-alt-ref": 0, "lag-in-frames": 0, "note": ""},
                "ffmpeg_pass1": [],
                "youtube_sdr": 8000, "youtube_hdr": 10000,
            }
        except Exception:
            return {"mode": "CBR", "bitrate_kbps": 8000, "crf": None,
                    "cpu_used": 5, "deadline": "realtime", "ffmpeg_args": [],
                    "notes": "fallback",
                    "tier": "1080p", "profile": 0, "pix_fmt": "yuv420p",
                    "tiles": {}, "altref": {}, "ffmpeg_pass1": [],
                    "youtube_sdr": 8000, "youtube_hdr": 10000}


def _ratio(a: int, b: int) -> float:
    """HDR/SDR 码率比（解析失败回 1.25，永不抛错）。"""
    try:
        if a and a > 0 and b and b > 0:
            return round(float(b) / float(a), 2)
        return 1.25
    except Exception:
        return 1.25


def paint_hint() -> str:
    """UI 一句话提示（AltRef 金星标 + compound 痕迹 + 无 B 排）。永不抛错。"""
    try:
        return ("VP9：周期 P 大包=AltRef（金★，-auto-alt-ref 1 的节拍器，CBR 关时无★属预期）；"
                "motion 图绿(fwd)/品红(bwd)混现=compound 双参考；全片应无 B 排（REORDER 平坦）。")
    except Exception:
        return "VP9"
