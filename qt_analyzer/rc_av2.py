"""AV2 profile / 采样 / 码率方向数据模块（纯文献版，experimental）。

AV2 尚在 AOM 实验阶段、本机 ffmpeg 无任何 AV2 编解码器，
本模块**不做本地实测**，只收录公开草案/规范中的方向性结论，
供 UI 提示与文档引用。统一接口（与家族 ``rc_*`` 模块对齐）：

* :func:`profiles` -- profile 名单
* :func:`chroma_modes` -- 采样 × 位深预期
* :func:`rc_modes` -- RC 模式（延续 AV1 口径的 AVM 命名）
* :func:`recommend` -- 给定分辨率/帧率/用途的码率方向建议
* :func:`paint_hint` -- 覆盖层一句话提示

约束：只用标准库；**永不抛错**（任何输入都收敛到安全默认值）；
所有返回值均显式标注 ``experimental``（字段或前后文声明）。
"""
from __future__ import annotations

__all__ = [
    "EXPERIMENTAL",
    "SPEC_NAME",
    "SPEC_VERSION",
    "SPEC_DATE",
    "SPEC_URL",
    "DRAFT_URL",
    "DRAFT_DATE",
    "AVM_RC_DOC_URL",
    "profiles",
    "chroma_modes",
    "rc_modes",
    "recommend",
    "paint_hint",
]

#: 本模块全部内容均为实验性方向描述，不可当作成品结论。
EXPERIMENTAL = True

SPEC_NAME = "AV2 Bitstream & Decoding Process Specification"
SPEC_VERSION = "v1.0.0"
SPEC_DATE = "2026-05-28"
SPEC_URL = "https://av2.aomedia.org/"
#: 被 v1.0.0 取代的工作草案（编号 v13 早于 1.0.0，仅作沿革引用）。
DRAFT_URL = "https://av2.aomedia.org/v13-public/index.html"
DRAFT_DATE = "2026-01-05"
#: AVM 参考软件 RC 选项说明（第三方整理，experimental）。
AVM_RC_DOC_URL = "https://encode.wiki/tools/software-encoders/avm"

_STATUS = "experimental：AOM 实验阶段，无 ffmpeg 支持，纯文献方向，不可当作成品结论"


def profiles() -> list:
    """AV2 profile 名单（v1.0.0 §Annex A / encode.wiki 整理，experimental）。

    v1.0.0 只定义一个工具集 Main，共 5 个具名 profile + Configurable，
    全部止于 10-bit；12-bit Professional profile 另立项中（未定稿）。
    永不抛错。
    """
    try:
        return [
            "Main_420_10_IP0",
            "Main_420_10_IP1",
            "Main_420_10_IP2",
            "Main_422_10_IP1",
            "Main_444_10_IP1",
            "Configurable",
        ]
    except Exception:
        return ["Main_420_10_IP0"]


def chroma_modes() -> list:
    """采样 × 位深预期（v1.0.0 color_config，experimental）。

    ``chroma_format_idc``：0=4:2:0 / 1=4:0:0(mono) / 2=4:4:4 / 3=4:2:2；
    ``bit_depth_idc``：0=8-bit / 1=10-bit（v1.0.0 仅 8/10-bit，
    >1 保留给未来版本）；12-bit 为 Professional 方向，未定稿。
    永不抛错。
    """
    try:
        return [
            "4:0:0 8-bit",
            "4:0:0 10-bit",
            "4:2:0 8-bit",
            "4:2:0 10-bit",
            "4:2:2 8-bit",
            "4:2:2 10-bit",
            "4:4:4 8-bit",
            "4:4:4 10-bit",
            "4:2:0 12-bit (future professional, experimental)",
            "4:2:2 12-bit (future professional, experimental)",
            "4:4:4 12-bit (future professional, experimental)",
        ]
    except Exception:
        return ["4:2:0 8-bit"]


def rc_modes() -> list:
    """RC 模式（AVM ``--end-usage`` 命名，延续 AV1 口径，experimental）。

    AVM 参考编码器：``vbr``（默认）/ ``cbr`` / ``cq``（--qp 上限
    + --target-bitrate 封顶）/ ``q``（恒定质量 --qp，0~255）；
    仅支持单遍（``--passes`` 须为 1）。AV1 的 CRF 概念对应 ``q``/``cq``，
    但数值体系不通用（AVM --qp 为 0~255 全位深统一标尺）。
    永不抛错。
    """
    try:
        return ["vbr", "cbr", "cq", "q"]
    except Exception:
        return ["vbr"]


def _num(value, default):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    try:
        import math

        if not math.isfinite(f) or f <= 0:
            return default
    except Exception:
        return default
    return f


def recommend(width, height, fps, use="streaming") -> dict:
    """码率方向建议（沿用 AV1 口径 ×0.7，experimental）。

    口径：AV1 同分辨率/用途典型值（阶梯表，30fps 基准，fps 线性折算）
    再乘 **0.7** —— 系 AOM 口径“AV2 相对 AV1 省约 30%”（CTC 下参考
    编码器 VMAF/PSNR 对比，非常慢速设置，不代表生产编码器），
    供 UI 占位展示，不可用于选型。SB 取 256（帧间）/128（帧内）方向值。
    任何输入永不抛错，均收敛到 1920x1080@30 streaming 默认。
    """
    try:
        w = _num(width, 1920.0)
        h = _num(height, 1080.0)
        f = _num(fps, 30.0)
        try:
            u = str(use or "streaming").strip().lower() or "streaming"
        except Exception:
            u = "streaming"
        # AV1 口径 30fps 阶梯（Mbps，VOD/点播中档典型值，非本机实测）。
        ladder = (
            (360, 0.8),
            (480, 1.2),
            (720, 2.5),
            (1080, 5.0),
            (1440, 10.0),
            (2160, 20.0),
        )
        base = ladder[-1][1] * (h / 2160.0)
        for hh, mbps in ladder:
            if h <= hh:
                base = mbps
                break
        use_mult = {
            "streaming": 1.0,
            "vod": 1.2,
            "broadcast": 1.3,
            "realtime": 0.8,
            "conferencing": 0.8,
            "archive": 1.5,
        }
        use_mode = {
            "streaming": "vbr",
            "vod": "vbr",
            "broadcast": "cbr",
            "realtime": "cbr",
            "conferencing": "cbr",
            "archive": "q",
        }
        m = use_mult.get(u, 1.0)
        mode = use_mode.get(u, "vbr")
        target = base * m * (f / 30.0) * 0.7  # AV2 方向性折扣，experimental
        target = max(0.2, min(200.0, target))
        if mode == "q":
            avm_flags = "--end-usage=q --qp=120 --passes=1"
        elif mode == "cbr":
            avm_flags = (
                "--end-usage=cbr --target-bitrate=%d --passes=1"
                % max(1, int(round(target * 1000)))
            )
        else:
            avm_flags = (
                "--end-usage=vbr --target-bitrate=%d --passes=1"
                % max(1, int(round(target * 1000)))
            )
        prof = "Main_420_10_IP0"
        try:
            if h > 1080 or u in ("broadcast", "archive"):
                prof = "Main_420_10_IP1"
        except Exception:
            pass
        return {
            "codec": "av2",
            "experimental": True,
            "status": _STATUS,
            "spec": "%s %s (%s)" % (SPEC_NAME, SPEC_VERSION, SPEC_DATE),
            "width": int(w),
            "height": int(h),
            "fps": float(f),
            "use": u,
            "profile": prof + " (experimental)",
            "chroma": "4:2:0 10-bit (experimental)",
            "rc_mode": mode + " (experimental)",
            "bitrate_mbps": {
                "target": round(target, 2),
                "low": round(target * 0.7, 2),
                "high": round(target * 1.3, 2),
            },
            "avm_flags": avm_flags + "  # reference-only, single-pass",
            "sb_size": "256 inter / 128 intra (directional, experimental)",
            "note": "沿用 AV1 口径×0.7（AOM ~30% saving，CTC 参考编码器对比）；"
                    "AVM 极慢、仅单遍、无容器映射（IVF/OBU），不可用于生产选型。",
        }
    except Exception as exc:  # 最后一道防线：固定默认，仍不抛错
        return {
            "codec": "av2",
            "experimental": True,
            "status": _STATUS,
            "spec": "%s %s (%s)" % (SPEC_NAME, SPEC_VERSION, SPEC_DATE),
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "use": "streaming",
            "profile": "Main_420_10_IP0 (experimental)",
            "chroma": "4:2:0 10-bit (experimental)",
            "rc_mode": "vbr (experimental)",
            "bitrate_mbps": {"target": 3.5, "low": 2.45, "high": 4.55},
            "avm_flags": "--end-usage=vbr --target-bitrate=3500 --passes=1"
                         "  # reference-only, single-pass",
            "sb_size": "256 inter / 128 intra (directional, experimental)",
            "note": "fallback 默认（输入异常 %s），experimental。" % type(exc).__name__,
        }


def paint_hint() -> str:
    """覆盖层一句话提示（experimental，永不抛错）。"""
    try:
        return (
            "AV2 (experimental)：SB 256（帧间）/128（帧内）网格示意 + "
            "GOP 通用语义；本机无编解码器，码率值为 AV1 口径×0.7 文献估算，"
            "不可当作成品结论。"
        )
    except Exception:
        return "AV2 (experimental)"
