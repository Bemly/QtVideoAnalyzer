"""AVC(H.264) + H.263 算法特点可视化。

只依赖 PySide6 + numpy + 标准库（不 import 其它 qt_analyzer 模块，
用鸭子类型读 FrameInfo，避免循环导入，单测可独立 import）。

函数总览
--------
* ``family_of(codec)`` -- 编码器名归一化为 ``"AVC"`` / ``"H.263"``。
* ``describe(codec)`` -- 算法要点 dict（block_sizes / bframes / entropy /
  refs / strengths）。
* ``partition_overlay(w, h, codec)`` -- 块划分示意线段
  ``[(x0, y0, x1, y1, style)]``，调用方按当前帧类型过滤 style 即可：
  AVC 下 ``I -> mb``、``P -> mb+p``、``B -> mb+b``；
  H.263 下 GOB 边界 ``gob`` + 8x8 块网格 ``blk``。
* ``reference_arcs(frames, limit=24)`` -- 参考关系箭头
  ``[(i, j, kind)]``，``i`` 为当前帧 ``index``，``j`` 为参考帧 ``index``，
  ``kind`` 为 ``"fwd"``（前向）/ ``"bwd"``（后向）。P 只发前向边，
  B 发前后两条边；H.263 片无 B，自然只有前向边。
* ``qp_signature_note(codec)`` -- QP 指纹一句话。
* ``style_color(style)`` -- overlay 样式 -> QColor（供 video_widget 用）。
"""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QColor

__all__ = [
    "family_of",
    "describe",
    "partition_overlay",
    "reference_arcs",
    "qp_signature_note",
    "style_color",
]

_MB = 16
_GOB_MB_ROWS = 3  # H.263 GOB = 3 行 MB（48 px，最后一组可不足）


# ---------------------------------------------------------------- family

def family_of(codec: str | None) -> str:
    """编码器名 -> ``"AVC"`` / ``"H.263"`` / 原样大写。

    avc / h264 / x264（含 "h.264" 写法）-> ``"AVC"``；
    含 "h263"（h263 / h263p / h.263 / h263+）-> ``"H.263"``；
    其它 -> ``str.upper()``，空串 -> ``"unknown"``。
    """
    s = (codec or "").strip().lower().replace(".", "").replace("-", "").replace("_", "")
    if not s:
        return "unknown"
    if "h263" in s:
        return "H.263"
    if s in ("avc", "h264", "x264") or "h264" in s or "avc" in s:
        return "AVC"
    return (codec or "").strip().upper() or "unknown"


# -------------------------------------------------------------- describe

def describe(codec: str | None) -> dict:
    """算法要点 dict，必含 block_sizes / bframes / entropy / refs / strengths。"""
    fam = family_of(codec)
    if fam == "H.263":
        return {
            "family": "H.263",
            "block_sizes": ["16x16 macroblock", "8x8 block (DCT)"],
            "bframes": False,
            "bframes_note": "基线无 B 帧（H.263+ Annex O 才有可选 B 帧，本工具测试片按无 B 处理）",
            "entropy": "VLC 变长码（Annex D/E/F/J 可选：PB 帧/高级预测/去块滤波/去块…)",
            "entropy_short": "VLC",
            "refs": "单前向参考 + 半像素 MV（Annex F 高级预测/重叠块补偿为可选项）",
            "gob": f"GOB 行条：每 {_GOB_MB_ROWS} 行 MB 一组（48 px）做重同步",
            "strengths": [
                "GOB 重同步：误码/丢包只影响一组行条，适合低码率视频会议",
                "半像素 MV + 8x8 块：P 帧运动补偿粒度 8x8，比 MPEG-1 细一倍",
                "无 B 帧 => 无重排延迟（pts==dts，REORDER 泳道为 0 直线）",
                "基线简单、解码便宜，但压缩率明显弱于 AVC（同画质码率高 ~2x）",
            ],
            "annex": ["Annex D PB 帧", "Annex F 高级预测", "Annex J 去块滤波",
                      "Annex O 可缩放/参考帧增强（含可选 B 帧）"],
        }
    # default AVC (h264/avc/x264，含未知回退：按 AVC 口径描述更易对比)
    return {
        "family": "AVC",
        "block_sizes": ["16x16 macroblock", "16x8 / 8x16", "8x8",
                        "8x4 / 4x8 / 4x4 (sub-macroblock)"],
        "bframes": True,
        "bframes_note": "B 金字塔（分层双向预测），测试片 -bf 2：IBBPBBP…",
        "entropy": "CAVLC / CABAC（4x4 整数变换 + 上下文自适应熵编码）",
        "entropy_short": "CABAC/CAVLC",
        "refs": "多参考帧（最多 16）+ 环路去块滤波 + 1/4 像素 MV",
        "strengths": [
            "4x4 整数变换 + CABAC：同 QP 下码率更低，QP 带内方差小（QP 泳道窄=率失真优）",
            "B 金字塔双向预测：B 帧小而多，FRAME TYPE 泳道 B 排密集",
            "多参考 + 去块滤波：边缘块效应轻，低码率仍保边缘",
            "代价：B 帧引入重排（pts-dts 锯齿，dts 单调而 pts 来回跳）",
        ],
    }


# ------------------------------------------------------ partition overlay

def _grid_lines(w: int, h: int, step: int) -> tuple[list[int], list[int]]:
    """[0, w] / [0, h] 网格坐标（含右/下边界），numpy 生成以满足依赖要求。"""
    xs = [int(v) for v in np.arange(0, w, step).tolist()] + [w]
    ys = [int(v) for v in np.arange(0, h, step).tolist()] + [h]
    return xs, ys


def partition_overlay(w: int, h: int, codec: str | None) -> list[tuple[int, int, int, int, str]]:
    """块划分示意线段 ``[(x0, y0, x1, y1, style)]``（像素坐标，含边界）。

    AVC：16x16 MB 网格（style ``"mb"``）+ 按帧类型细分示意——
    I 用整块（即 ``mb`` 本身，无内线）、P 加横中线 16x8（``"p"``）、
    B 加十字 8x8 四分（``"b"``，横+竖两条）。调用方按当前帧类型过滤：
    I 只画 ``mb``，P 画 ``mb+p``，B 画 ``mb+b``。

    H.263：GOB 行条（每 3 行 MB 一组，style ``"gob"``）+ 8x8 块网格
    （style ``"blk"``）。
    """
    try:
        w, h = int(w), int(h)
    except (TypeError, ValueError):
        return []
    if w <= 0 or h <= 0:
        return []
    fam = family_of(codec)
    out: list[tuple[int, int, int, int, str]] = []
    if fam == "H.263":
        gob_step = _MB * _GOB_MB_ROWS
        gxs, gys = _grid_lines(w, h, 8)
        gob_ys = [int(v) for v in np.arange(0, h, gob_step).tolist()] + [h]
        for y in gob_ys:
            out.append((0, y, w, y, "gob"))
        for x in gxs:
            out.append((x, 0, x, h, "blk"))
        for y in gys:
            out.append((0, y, w, y, "blk"))
        return out
    # ---- AVC ----
    xs, ys = _grid_lines(w, h, _MB)
    for x in xs:
        out.append((x, 0, x, h, "mb"))
    for y in ys:
        out.append((0, y, w, y, "mb"))
    for iy in range(len(ys) - 1):
        y0, y1 = ys[iy], ys[iy + 1]
        ym = (y0 + y1) // 2
        for ix in range(len(xs) - 1):
            x0, x1 = xs[ix], xs[ix + 1]
            xm = (x0 + x1) // 2
            out.append((x0, ym, x1, ym, "p"))   # P: 16x8 横分
            out.append((x0, ym, x1, ym, "b"))   # B: 8x8 四分（横）
            out.append((xm, y0, xm, y1, "b"))   # B: 8x8 四分（竖）
    return out


# --------------------------------------------------------- reference arcs

def _letter_of(frame) -> str:
    """FrameInfo -> 'I' / 'P' / 'B' / '?'（鸭子类型，兼容枚举/字符串/整数）。"""
    t = getattr(frame, "type", None)
    letter = getattr(t, "letter", None)
    if isinstance(letter, str) and letter:
        c = letter.strip().upper()
        if c and c[0] in "IPB":
            return c[0]
        return "?"
    if isinstance(t, str):
        c = t.strip().upper()
        return c[0] if c and c[0] in "IPB" else "?"
    try:
        iv = int(t)  # PicType: Other=0 I=1 P=2 B=3
        return {1: "I", 2: "P", 3: "B"}.get(iv, "?")
    except (TypeError, ValueError):
        pass
    s = str(t).upper()
    for c in ("I", "P", "B"):
        if c in s:
            return c
    return "?"


def _idx_of(frame, fallback: int) -> int:
    try:
        return int(getattr(frame, "index", fallback))
    except (TypeError, ValueError):
        return fallback


def reference_arcs(frames, limit: int = 24) -> list[tuple[int, int, str]]:
    """参考关系箭头 ``[(i, j, kind)]``。

    ``i`` = 当前帧 ``index``，``j`` = 参考帧 ``index``，
    ``kind`` = ``"fwd"`` 前向 / ``"bwd"`` 后向。
    P 向前找最近的 I/P 发一条 ``fwd``；B 向前后各找最近的 I/P，
    发 ``fwd`` + ``bwd`` 两条；I / Other 不发边。
    只看前 ``limit`` 帧（显示序，调用方保证 pts 序）。
    H.263 片无 B，天然只有前向边。
    """
    try:
        n = max(0, int(limit))
    except (TypeError, ValueError):
        n = 24
    seq = list(frames[:n]) if frames else []
    letters = [_letter_of(f) for f in seq]
    out: list[tuple[int, int, str]] = []
    for pos, f in enumerate(seq):
        cur = _idx_of(f, pos)
        L = letters[pos]
        if L == "P":
            for q in range(pos - 1, -1, -1):
                if letters[q] in ("I", "P"):
                    out.append((cur, _idx_of(seq[q], q), "fwd"))
                    break
        elif L == "B":
            for q in range(pos - 1, -1, -1):
                if letters[q] in ("I", "P"):
                    out.append((cur, _idx_of(seq[q], q), "fwd"))
                    break
            for q in range(pos + 1, len(seq)):
                if letters[q] in ("I", "P"):
                    out.append((cur, _idx_of(seq[q], q), "bwd"))
                    break
    return out


# ------------------------------------------------------------------ QP note

def qp_signature_note(codec: str | None) -> str:
    """QP 指纹一句话（供 CURRENT FRAME / QP 泳道旁注）。"""
    fam = family_of(codec)
    if fam == "H.263":
        return ("H.263：qp 原生可用但范围粗（量化步长翻倍档，QP 泳道呈宽台阶跳变；"
                "I 大块均值拉低、P 帧随运动抖动大）。")
    return ("AVC：qp 原生可用；CABAC + 4x4 整数变换使同类型帧 QP 方差小"
            "（QP 泳道带宽窄=率失真优），I < P < B 阶梯清晰。")


# ------------------------------------------------------------ style color

_STYLE_QCOLOR = {
    "mb": QColor(0x5B, 0x9B, 0xFF),   # MB 网格：浅蓝
    "p": QColor(0x4C, 0x8B, 0xE8),    # P 细分：蓝
    "b": QColor(0x35, 0xC7, 0x59),    # B 细分：绿
    "gob": QColor(0xF2, 0xA0, 0x33),  # GOB 行条：橙
    "blk": QColor(0x8C, 0x93, 0x99),  # 8x8 块网格：灰
}


def style_color(style: str) -> QColor:
    """overlay 样式名 -> QColor（未知样式回退白色）。"""
    c = _STYLE_QCOLOR.get((style or "").lower())
    return QColor(c) if c is not None else QColor(0xFF, 0xFF, 0xFF)
