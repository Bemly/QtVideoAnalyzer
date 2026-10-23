"""HEVC (H.265) profile / 采样 / 码率控制速查 + 推荐参数（可复用数据模块）。

只依赖标准库（无第三方依赖），所有公开函数永不抛错（内部 try/except，
非法输入回退安全默认值）。

本机证据（2026-10-23，ffmpeg 9.0.2 / x265 4.3+1-e9b8812，8bit+10bit+12bit）::

    ffmpeg -hide_banner -h encoder=libx265
      Supported pixel formats: yuv420p yuvj420p yuv422p yuvj422p yuv444p
        yuvj444p gbrp yuv420p10le yuv422p10le yuv444p10le gbrp10le
        yuv420p12le yuv422p12le yuv444p12le gbrp12le gray gray10le
        gray12le yuva420p yuva420p10le
      -crf <float>  set the x265 crf (default -1; x265 内部默认 28.0)
      -qp  <int>    set the x265 qp  (CQP 模式 P 帧 QP)
      -preset <string> / -tune <string> / -profile <string>
      -x265-params <dictionary>  :-分隔 key=value 直通 x265
    x265 --help
      -P/--profile: main, main10, mainstillpicture（本机构建强制档）
      -p/--preset: ultrafast superfast veryfast faster fast medium
                   slow slower veryslow placebo（默认 medium）
      -t/--tune: psnr ssim grain zerolatency fastdecode
      RC: --bitrate (ABR kbps) / --crf 0-51 (默认 28.0) /
          -q/--qp (CQP) / --vbv-maxrate/--vbv-bufsize/--vbv-init /
          --strict-cbr / --pass 1/2/3 / --qpmin/--qpmax/--qpstep /
          --qcomp / --ipratio 1.40 / --pbratio 1.30 / --aq-mode / --cutree

公开接口（与 rc_avc / rc_av1 等统一）::

    profiles() -> list[str]
    chroma_modes() -> list[str]
    rc_modes() -> list[str]            # ["CRF","CQP","ABR","CBR"]
    recommend(w,h,fps,use="streaming") -> dict   # bitrate_kbps/crf + ffmpeg_args + notes
    paint_hint() -> str
"""

from __future__ import annotations

__all__ = [
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
]

# ---------------------------------------------------------------------------
# 静态表（HEVC 标准全集；本机 x265 构建 --profile 仅强制 main/main10/
# mainstillpicture，其余靠 -pix_fmt/-output-depth 间接落到对应档）

_PROFILES = [
    "Main",
    "Main10",
    "Main12",
    "Main422-10",
    "Main422-12",
    "Main444-8",
    "Main444-10",
    "Main444-12",
    "Main444-16 Intra",
    "MainStillPicture",
]

# pix_fmt 名即 ffmpeg -pix_fmt 可直接用的值；9 宫格 420/422/444 x 8/10/12。
_CHROMA_MODES = [
    "yuv420p",      # 4:2:0 8-bit
    "yuv420p10le",  # 4:2:0 10-bit
    "yuv420p12le",  # 4:2:0 12-bit
    "yuv422p",      # 4:2:2 8-bit
    "yuv422p10le",  # 4:2:2 10-bit
    "yuv422p12le",  # 4:2:2 12-bit
    "yuv444p",      # 4:4:4 8-bit
    "yuv444p10le",  # 4:4:4 10-bit
    "yuv444p12le",  # 4:4:4 12-bit
]

_RC_MODES = ["CRF", "CQP", "ABR", "CBR"]

_PRESETS = [
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow", "placebo",
]

_TUNES = ["psnr", "ssim", "grain", "zerolatency", "fastdecode"]


def profiles() -> list[str]:
    """HEVC profile 全集（标准档；本机构建 --profile 仅强制 main/main10/mainstillpicture）。

    永不抛错。
    """
    try:
        return list(_PROFILES)
    except Exception:
        return ["Main", "Main10"]


def chroma_modes() -> list[str]:
    """chroma 采样 x 位深 9 宫格（值即 ``ffmpeg -pix_fmt`` 名）。

    永不抛错。
    """
    try:
        return list(_CHROMA_MODES)
    except Exception:
        return ["yuv420p"]


def rc_modes() -> list[str]:
    """x265 码率控制四档。永不抛错。"""
    try:
        return list(_RC_MODES)
    except Exception:
        return ["CRF", "CQP", "ABR", "CBR"]


def _safe_float(v, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    try:
        if f != f or f in (float("inf"), float("-inf")):  # NaN / Inf
            return default
    except Exception:
        return default
    return f


def _safe_int(v, default: int) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def recommend(width, height, fps, use: str = "streaming") -> dict:
    """按分辨率/帧率给 HEVC 推荐参数（永不抛错）。

    ``use``（大小写不敏感，前缀匹配即可）：

    * ``streaming``（默认）-- CRF + VBV 上限（兼顾质量与波动）；
    * ``archive`` -- 纯 CRF 高质量（preset slow，无 VBV）；
    * ``realtime`` / ``live`` / ``lowlatency`` / ``cbr`` -- CBR
      （``-b:v = -maxrate`` + ``-bufsize`` + ``tune zerolatency``）；
    * ``abr`` / ``vbr`` -- ABR（``-b:v`` 目标码率）；
    * ``cqp`` / ``qp`` -- CQP 定 QP；
    * ``crf`` -- 纯 CRF（无 VBV）。

    10bit 规则：``width>=3840 或 height>=2160 或像素数>=8M`` 时切
    ``Main10 + yuv420p10le``（notes 注明 ``Main10``），否则
    ``Main + yuv420p``。

    返回 dict 必含 ``bitrate_kbps``（CQP 外）/``crf``（CRF 系）中的
    至少一项 + ``ffmpeg_args`` + ``notes``。
    """
    try:
        w = _safe_int(width, 1920)
        h = _safe_int(height, 1080)
        f = _safe_float(fps, 30.0)
        if w <= 0:
            w = 1920
        if h <= 0:
            h = 1080
        if not (1.0 <= f <= 120.0):
            f = 30.0
        try:
            u = str(use or "streaming").strip().lower()
        except Exception:
            u = "streaming"
        if not u:
            u = "streaming"

        pixels = w * h
        # 10bit/Main10 门限：4K 及以上。
        ten_bit = (w >= 3840) or (h >= 2160) or (pixels >= 3840 * 2160)
        profile = "Main10" if ten_bit else "Main"
        pix_fmt = "yuv420p10le" if ten_bit else "yuv420p"
        bit_depth = 10 if ten_bit else 8
        chroma = "4:2:0"

        # bpp 模型（HEVC streaming 实测口径反推）：
        # 1080p30 ~6Mbps => ~0.10bpp；4K ~20Mbps => ~0.08bpp；8K ~60Mbps => ~0.06bpp。
        if pixels >= 7680 * 4320 // 2:  # ~16M+ 按 8K 口径
            bpp = 0.060
            crf_stream, crf_arch = 21, 19
        elif pixels >= 3840 * 2160 // 2:  # ~4M+ 按 4K 口径
            bpp = 0.075
            crf_stream, crf_arch = 22, 20
        else:  # 1080p 及以下
            bpp = 0.100
            crf_stream, crf_arch = 23, 20

        bitrate = int(round(pixels * f * bpp / 1000.0))
        bitrate = max(500, min(120000, bitrate))

        # VBV：maxrate = 1.5x 目标，bufsize = 2x 目标（约 2 秒窗口）。
        maxrate = int(round(bitrate * 1.5))
        bufsize = int(round(bitrate * 2.0))

        is_cbr = u.startswith(("cbr", "realtime", "real-time", "live", "lowlat", "ull", "rtc"))
        is_abr = u.startswith(("abr", "vbr"))
        is_cqp = u.startswith(("cqp", "qp"))
        is_arch = u.startswith(("arch", "store", "master", "hq"))
        is_crf_plain = u.startswith("crf")

        ffmpeg_args: list[str]
        notes: list[str] = []
        rc: str
        crf = None
        qp = None

        if is_cbr:
            rc = "CBR"
            preset, tune = "veryfast", "zerolatency"
            ffmpeg_args = [
                "-c:v", "libx265",
                "-preset", preset,
                "-tune", tune,
                "-profile:v", profile.lower(),
                "-pix_fmt", pix_fmt,
                "-b:v", f"{bitrate}k",
                "-maxrate", f"{bitrate}k",
                "-bufsize", f"{bufsize}k",
                "-x265-params", f"strict-cbr=1:keyint={int(round(f * 2))}",
            ]
            notes.append(f"CBR 等码率：-b:v=-maxrate={bitrate}k，bufsize={bufsize}k（~2s 窗口）")
            notes.append("本工具痕迹：BITRATE 近平顶 + VBV 满，B 密排但峰谷差小（见 paint_hint）")
        elif is_abr:
            rc = "ABR"
            preset = "medium"
            ffmpeg_args = [
                "-c:v", "libx265",
                "-preset", preset,
                "-profile:v", profile.lower(),
                "-pix_fmt", pix_fmt,
                "-b:v", f"{bitrate}k",
                "-maxrate", f"{maxrate}k",
                "-bufsize", f"{bufsize}k",
            ]
            notes.append(f"ABR 平均码率 {bitrate}k，VBV 上限 maxrate={maxrate}k / bufsize={bufsize}k")
        elif is_cqp:
            rc = "CQP"
            qp = 24 if not ten_bit else 22
            ffmpeg_args = [
                "-c:v", "libx265",
                "-preset", "medium",
                "-profile:v", profile.lower(),
                "-pix_fmt", pix_fmt,
                "-qp", str(qp),
            ]
            notes.append(f"CQP 定 QP={qp}（P 帧；I/B 由 ipratio=1.40/pbratio=1.30 派生）")
            notes.append("本工具痕迹：QP 泳道 I<P<B 阶梯最清晰，BITRATE 随内容大起大落")
        elif is_arch:
            rc = "CRF"
            crf = crf_arch
            ffmpeg_args = [
                "-c:v", "libx265",
                "-preset", "slow",
                "-profile:v", profile.lower(),
                "-pix_fmt", pix_fmt,
                "-crf", str(crf),
            ]
            notes.append(f"存档 CRF {crf} + preset slow（无 VBV，质量优先；参考平均 {bitrate}k）")
        elif is_crf_plain:
            rc = "CRF"
            crf = crf_stream
            ffmpeg_args = [
                "-c:v", "libx265",
                "-preset", "medium",
                "-profile:v", profile.lower(),
                "-pix_fmt", pix_fmt,
                "-crf", str(crf),
            ]
            notes.append(f"纯 CRF {crf}（无 VBV；同画质参考平均 {bitrate}k）")
        else:  # streaming 默认：CRF + VBV 上限
            rc = "CRF"
            crf = crf_stream
            u = "streaming"
            ffmpeg_args = [
                "-c:v", "libx265",
                "-preset", "medium",
                "-profile:v", profile.lower(),
                "-pix_fmt", pix_fmt,
                "-crf", str(crf),
                "-maxrate", f"{maxrate}k",
                "-bufsize", f"{bufsize}k",
            ]
            notes.append(f"点播 CRF {crf} + VBV 上限 maxrate={maxrate}k / bufsize={bufsize}k")
            notes.append(f"同画质约 AVC 码率 60%（省 ~40%；见 docs/rates/hevc.md 速查）")

        if ten_bit:
            notes.append("10bit Main10（yuv420p10le）：4K+ 推荐，banding 更少，HDR 必备")
        else:
            notes.append("8bit Main（yuv420p）：1080p 及以下默认，兼容最广")

        out: dict = {
            "width": w,
            "height": h,
            "fps": f,
            "use": u,
            "rc": rc,
            "profile": profile,
            "pix_fmt": pix_fmt,
            "bit_depth": bit_depth,
            "chroma": chroma,
            "bitrate_kbps": bitrate,
            "maxrate_kbps": maxrate,
            "bufsize_kb": bufsize,
            "preset": ffmpeg_args[ffmpeg_args.index("-preset") + 1] if "-preset" in ffmpeg_args else "medium",
            "ffmpeg_args": ffmpeg_args,
            "notes": notes,
        }
        if crf is not None:
            out["crf"] = crf
        if qp is not None:
            out["qp"] = qp
        if "-tune" in ffmpeg_args:
            try:
                out["tune"] = ffmpeg_args[ffmpeg_args.index("-tune") + 1]
            except Exception:
                pass
        return out
    except Exception:
        # 永不抛错：安全默认值。
        try:
            return {
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "use": "streaming",
                "rc": "CRF",
                "profile": "Main",
                "pix_fmt": "yuv420p",
                "bit_depth": 8,
                "chroma": "4:2:0",
                "bitrate_kbps": 6000,
                "maxrate_kbps": 9000,
                "bufsize_kb": 12000,
                "preset": "medium",
                "crf": 23,
                "ffmpeg_args": ["-c:v", "libx265", "-preset", "medium",
                                "-profile:v", "main", "-pix_fmt", "yuv420p",
                                "-crf", "23", "-maxrate", "9000k",
                                "-bufsize", "12000k"],
                "notes": ["fallback：输入非法时的安全默认值（1080p30 CRF 23）"],
            }
        except Exception:
            return {}


def paint_hint() -> str:
    """本工具内看 HEVC 码控痕迹的一句话（永不抛错）。"""
    try:
        return (
            "HEVC 看 CTU 层：I 帧大片蓝/绿 64/32、P/B 满屏橙/红 16/8 碎块；"
            "QP 泳道 I<P<B 阶梯（CQP 最陡）；B 密排 + BITRATE 矮峰海是 "
            "CRF/ABR 痕迹，近乎平顶 + VBV 常满则是 CBR 痕迹。"
        )
    except Exception:
        return "HEVC"
