"""Apple ProRes 选档/码率数据模块 (可复用, 无第三方依赖, 永不抛错)。

口径来源: Apple ProRes White Paper / Apple Support 102207
(1920x1080@29.97 目标码率行) + 本机 ``ffmpeg -h encoder=prores_ks`` 实测。
6 profile 的目标码率是 **VBR 目标值** (随内容浮动), ProRes 没有
CRF/CBR 概念 —— 档位即固定量化矩阵 (见 ``notes``)。

统一接口::

    profiles()                  # 6 profile 名
    chroma_modes()              # ["422", "4444"]
    rc_modes()                  # ["VBR-fixedQP"]
    recommend(w, h, fps, use=)  # 选档 + 预估码率 + ffmpeg_args + notes
    paint_hint()                # 本工具联动一句话 (全 I 红排/BITRATE 高而平/CV 小)

所有函数永不抛错: 非法输入降级为默认值 (1920x1080@25, use="editing")。
"""

from __future__ import annotations

# 白皮书锚点: 全宽 1920x1080 @ 29.97fps。
_REF_W = 1920
_REF_H = 1080
_REF_FPS = 29.97
_REF_PIXELS = float(_REF_W * _REF_H)

# 6 profile (ffmpeg prores_ks / videotoolbox 通用名, 小写)。
_PROFILES = ("proxy", "lt", "standard", "hq", "4444", "4444xq")

# ffmpeg prores_ks -profile:v 整数映射 (本机 ffmpeg 9.0.2 help 实测):
# auto -1, proxy 0, lt 1, standard 2, hq 3, 4444 4, 4444xq 5。
_PROFILE_ID = {
    "proxy": 0,
    "lt": 1,
    "standard": 2,
    "hq": 3,
    "4444": 4,
    "4444xq": 5,
}

# 官方目标码率 (Mbps, VBR 目标值) @ 1920x1080 @ 29.97fps:
# Proxy 45 / LT 102 / Standard 147 / HQ 220 / 4444 330 / 4444XQ 495。
# (白皮书柱状图 + Apple Support 102207; XQ 文案约 500Mbps, 表值 495。)
_TARGET_1080P2997 = {
    "proxy": 45.0,
    "lt": 102.0,
    "standard": 147.0,
    "hq": 220.0,
    "4444": 330.0,
    "4444xq": 495.0,
}

# 官方目标码率 (Mbps) @ 1920x1080 @ 25fps (50i/25p 行):
# 38 / 85 / 122 / 184 / 275 / 415 (XQ 为帧率比例推算, 与转引表一致)。
_TARGET_1080P25 = {
    "proxy": 38.0,
    "lt": 85.0,
    "standard": 122.0,
    "hq": 184.0,
    "4444": 275.0,
    "4444xq": 415.0,
}

# chroma 口径: 422 家族全员 4:2:2; 4444 两档 4:4:4 (+alpha)。
_CHROMA = {
    "proxy": "422",
    "lt": "422",
    "standard": "422",
    "hq": "422",
    "4444": "4444",
    "4444xq": "4444",
}

# 规格位深 (Apple 标称) vs ffmpeg 本机实际支持。
_BITDEPTH_SPEC = {
    "proxy": "10-bit",
    "lt": "10-bit",
    "standard": "10-bit",
    "hq": "10-bit",
    "4444": "12-bit video + up to 16-bit alpha",
    "4444xq": "12-bit video + up to 16-bit alpha",
}
# 本机 ffmpeg 9.0.2 prores_ks/aw 仅支持 10-bit pix_fmt (help 实测),
# 4444XQ 经 ffmpeg 编码是 profile 标记位, 非真 12-bit。
_BITDEPTH_FFMPEG = "10-bit (prores_ks/aw: yuv422p10le/yuv444p10le/yuva444p10le)"

# recommend() 默认 pix_fmt: 422 家族 yuv422p10le; 4444 家族含 alpha 用 yuva。
_PIXFMT = {
    "proxy": "yuv422p10le",
    "lt": "yuv422p10le",
    "standard": "yuv422p10le",
    "hq": "yuv422p10le",
    "4444": "yuva444p10le",
    "4444xq": "yuva444p10le",
}

# use 关键字 -> profile (大小写不敏感, 命中任一子串即选档, 兜底 standard)。
_USE_MAP = (
    (("proxy", "offline", "preview", "small", "rough"), "proxy"),
    (("lt", "storage", "economy", "light"), "lt"),
    (("4444xq", "xq", "hdr", "highend", "vfx-max"), "4444xq"),
    (("4444", "gfx", "graphics", "alpha", "comp", "key"), "4444"),
    (("hq", "master", "high", "grade", "finish", "color"), "hq"),
)


def profiles() -> list:
    """6 profile 名 (白皮书口径, 全小写)。永不抛错。"""
    try:
        return list(_PROFILES)
    except Exception:
        return ["proxy", "lt", "standard", "hq", "4444", "4444xq"]


def chroma_modes() -> list:
    """chroma 下采样模式。永不抛错。"""
    try:
        return ["422", "4444"]
    except Exception:
        return ["422", "4444"]


def rc_modes() -> list:
    """码率控制模式: ProRes 只有 VBR-fixedQP (固定量化矩阵档, 无 CRF/CBR)。"""
    try:
        return ["VBR-fixedQP"]
    except Exception:
        return ["VBR-fixedQP"]


def _coerce_profile(use) -> str:
    """use 关键字 -> profile 名, 失败兜底 "standard"。"""
    try:
        u = str(use or "editing").strip().lower()
    except Exception:
        return "standard"
    try:
        for keys, prof in _USE_MAP:
            for k in keys:
                if k in u:
                    return prof
    except Exception:
        pass
    return "standard"


def _scale(ref_mbps: float, w, h, fps) -> float:
    """按像素数×帧率把 1080p29.97 锚点缩放到目标规格。非法输入返回锚点本身。"""
    try:
        base = float(ref_mbps)
    except Exception:
        base = 147.0
    try:
        wi = int(float(w))
        hi = int(float(h))
        fr = float(fps)
    except Exception:
        return base
    if wi <= 0 or hi <= 0 or not (fr > 0):
        return base
    try:
        return base * (wi * hi) / _REF_PIXELS * (fr / _REF_FPS)
    except Exception:
        return base


def recommend(width, height, fps, use: str = "editing") -> dict:
    """选档 + 预估码率 + ffmpeg 参数 + 说明。永不抛错。

    ``use`` 口径: "editing"(默认)->standard; "proxy"/"offline"->proxy;
    "lt"/"storage"->lt; "hq"/"master"/"grade"->hq;
    "4444"/"alpha"/"gfx"->4444; "xq"/"hdr"->4444xq。未知 use 兜底 standard。

    预估码率 = 白皮书 1080p29.97 锚点 × (像素/2073600) × (fps/29.97),
    即 VBR 目标值 (随内容浮动 ±, 非 CBR 承诺)。
    """
    try:
        prof = _coerce_profile(use)
    except Exception:
        prof = "standard"
    if prof not in _TARGET_1080P2997:
        prof = "standard"
    try:
        ref = float(_TARGET_1080P2997[prof])
    except Exception:
        ref = 147.0
    try:
        est = _scale(ref, width, height, fps)
    except Exception:
        est = ref
    try:
        est_r = round(float(est), 1)
    except Exception:
        est_r = ref
    try:
        gbph = round(float(est_r) * 3600.0 / 8.0 / 1000.0, 1)  # 小数 GB/小时
    except Exception:
        gbph = 0.0
    try:
        pid = int(_PROFILE_ID.get(prof, 2))
    except Exception:
        pid = 2
    try:
        pixfmt = _PIXFMT.get(prof, "yuv422p10le")
        chroma = _CHROMA.get(prof, "422")
        spec = _BITDEPTH_SPEC.get(prof, "10-bit")
    except Exception:
        pixfmt, chroma, spec = "yuv422p10le", "422", "10-bit"
    try:
        args = ["-c:v", "prores_ks", "-profile:v", str(pid),
                "-pix_fmt", pixfmt]
    except Exception:
        args = ["-c:v", "prores_ks", "-profile:v", "2",
                "-pix_fmt", "yuv422p10le"]
    try:
        notes = [
            "VBR-fixedQP: profile 即固定量化矩阵档 "
            "(prores_ks quant_mat proxy0/lt2/standard3/hq4), 无 CRF/CBR 概念; "
            "码率为内容相关目标值, 非封顶承诺。",
            "prores_ks 非常用微调: -bits_per_mb (逐宏块目标比特) / "
            "-quant_mat / -alpha_bits(0..16, 默认 16); 日常选档只换 profile。",
            "4444 家族支持 alpha (yuva444p10le); 无 alpha 源可用 yuv444p10le; "
            "ffmpeg 本机仅 10-bit, 4444XQ 真 12-bit 需 Apple 原生编码器。",
            "预估按像素×帧率线性换算; 4K UHD ≈ 1080p×4 "
            "(如 HQ@2160p29.97 ≈ 880Mbps, 与白皮书 4K 表 884 基本一致)。",
        ]
    except Exception:
        notes = ["VBR-fixedQP, 无 CRF/CBR。"]
    try:
        return {
            "use": (str(use) if use is not None else "editing"),
            "profile": prof,
            "profile_id": pid,
            "chroma": chroma,
            "pix_fmt": pixfmt,
            "bit_depth_spec": spec,
            "bit_depth_ffmpeg": _BITDEPTH_FFMPEG,
            "rc": "VBR-fixedQP",
            "ref_mbps_1080p29_97": ref,
            "est_mbps": est_r,
            "est_gb_per_hr": gbph,
            "ffmpeg_args": args,
            "notes": notes,
        }
    except Exception:
        return {
            "use": "editing",
            "profile": "standard",
            "profile_id": 2,
            "chroma": "422",
            "pix_fmt": "yuv422p10le",
            "bit_depth_spec": "10-bit",
            "bit_depth_ffmpeg": _BITDEPTH_FFMPEG,
            "rc": "VBR-fixedQP",
            "ref_mbps_1080p29_97": 147.0,
            "est_mbps": 147.0,
            "est_gb_per_hr": 66.2,
            "ffmpeg_args": ["-c:v", "prores_ks", "-profile:v", "2",
                            "-pix_fmt", "yuv422p10le"],
            "notes": ["VBR-fixedQP, 无 CRF/CBR。"],
        }


def paint_hint() -> str:
    """本工具联动一句话 (FRAME TYPE / BITRATE / CV 口径)。永不抛错。"""
    try:
        return ("ProRes 全 I 帧: FRAME TYPE 全红 I 排 / GOP 平直 0 线 / "
                "REORDER 零线; BITRATE 高而平 (1080p HQ ~220Mbps, "
                "360p 测试片即 ~14.7Mbps, AVC 数倍) 且帧间波动小 CV 小; "
                "QP 方差小近直线 (all_intra_stats verdict'又大又稳')。")
    except Exception:
        return "ProRes: 全 I 红排, BITRATE 高而平, CV 小。"
