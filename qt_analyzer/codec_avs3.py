"""AVS3 (GB/T 33475.2, second-gen Chinese broadcast codec) algorithm highlights.

Local decode is real: uavs3dec (uavs3d, libuavs3d 1.2.1_release, 8-bit build,
macOS arm64, cmake-built into tools/avs3bin/) decodes AVS3-P2 baseline streams
bit-exactly. describe() always works; overlays are stable per frame; the
full-chain selftest runs on a genuine AVS3 stream
(tools/samples/test_avs3_city.avs3, uavs3/avs3stream City_1280x720_60_ra),
NOT an hevc surrogate.

Deps: numpy (optional, pure-python fallback) + stdlib. PySide6 only inside
the paint helper.
"""
from __future__ import annotations

import hashlib
import math

CODECS = ("avs3",)
LCU_SIZE = 128          # AVS3 max LCU, GB/T 33475.2-2024
BRAIN_THRESHOLD = 1.22  # between AVC 1.18 and HEVC 1.25: DBF+SAO+ALF clean edges


def _stable01(*parts: object) -> float:
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:4], "little") / 0xFFFFFFFF


def describe(codec: str = "avs3", summary=None) -> dict:
    """Card for the CodecDNA panel. Never raises for avs3; ValueError otherwise."""
    if str(codec or "").strip().lower() not in ("avs3", "avs", "avs3-p2", "hpm"):
        raise ValueError("codec_avs3.describe only knows avs3")
    return {
        "codec": "avs3",
        "family": "AVS3",
        "full_name": "AVS3-P2 (GB/T 33475.2, HPM reference)",
        "status": "local-decode: uavs3dec (libuavs3d 1.2.1, 8-bit, arm64) "
                    "解出 1280x720 真流，md5 与官方重建 YUV 逐字节一致",
        "decoder": "uavs3d uavs3dec (libuavs3d(8) 1.2.1_release) @ tools/avs3bin/",
        "decode_cmd": "uavs3dec -i in.avs3 -o out.yuv -l 2 -t 8 [-s 1]",
        "verified_sample": "test_avs3_city.avs3 (City_1280x720_60_ra, 600f, "
                           "I=10/P=0/B=590, GOP64 RA)",
        "block": "LCU 128x128",
        "partition": "QT + BTT (binary/ternary) multi-type tree, CU/PU/TU unified",
        "entropy": "binary arithmetic coding (CABAC-class)",
        "refs": "multi-ref + B frames + affine/UMVE/HMVP + IBC",
        "inloop": "DBF + SAO + ALF/CCALF",
        "transform": "DCT-II/VIII/DST-VII multi-core + 16/32/64 sizes",
        "strengths": [
            "LCU 128 + QT/BTT 多叉树，4K/8K 广播为本（GB/T 国家标准）",
            "Affine/UMVE/HMVP + IBC，运动与屏幕内容双优",
            "DBF+SAO+ALF 三级环路，B 帧双向省码率",
        ],
        "note": "brain 阈值取 1.22（AVC 1.18 / HEVC 1.25 之间），环路强但 DCT 基底仍留缝",
        "where_to_look": "去哪看：GOP 条看 IBB 节奏（有 B 即 AVS3 真身）；开 AVS3 LCU 层看 128 网格深浅",
    }


def lcu_overlay(w: int, h: int, frame=None) -> list:
    """Deterministic LCU partition demo: (x0, y0, size, depth).

    I frames shallow (more 128/64), P/B deeper (more 64/32/16).
    Same frame (index+type+qp) always yields the same split.
    """
    if w <= 0 or h <= 0:
        return []
    try:
        idx = int(getattr(frame, "index", 0) or 0)
    except Exception:
        idx = 0
    try:
        letter = str(getattr(getattr(frame, "type", None), "letter", "P"))
    except Exception:
        letter = "P"
    try:
        qp = float(getattr(frame, "qp_avg", 26.0) or 26.0)
    except Exception:
        qp = 26.0
    if letter == "I":
        probs = (0.55, 0.25, 0.12, 0.08)  # depth 0..3
    elif letter == "B":
        probs = (0.10, 0.22, 0.33, 0.35)
    else:
        probs = (0.18, 0.27, 0.30, 0.25)
    out: list = []
    step = LCU_SIZE
    for gy in range(0, h, step):
        for gx in range(0, w, step):
            r = _stable01(gx, gy, idx, letter, round(qp, 1))
            depth = 0
            acc = 0.0
            for d, p in enumerate(probs):
                acc += p
                if r <= acc:
                    depth = d
                    break
            size = max(16, step // (2 ** depth))
            # subdivide the LCU cell into size-blocks for the visible grid
            for yy in range(gy, min(gy + step, h), size):
                for xx in range(gx, min(gx + step, w), size):
                    out.append((xx, yy, min(size, w - xx), min(size, h - yy), depth))
    return out


def depth_color(depth: int):
    """0 steel-blue -> 1 green -> 2 amber -> 3 red (alpha for overlay)."""
    try:
        from PySide6.QtGui import QColor  # type: ignore
    except Exception:
        return (70 + depth * 50, 140 - depth * 20, 200 - depth * 40)
    return [
        QColor(70, 130, 200, 110),
        QColor(80, 180, 120, 110),
        QColor(230, 170, 60, 120),
        QColor(220, 80, 70, 130),
    ][max(0, min(3, int(depth)))]


def reference_arcs(frames, limit: int = 24) -> list:
    """P -> one fwd arc; B -> fwd + bwd pair; I -> none. Caps at limit."""
    arcs: list = []
    try:
        n = len(frames)
    except Exception:
        return arcs
    for i, f in enumerate(frames):
        if len(arcs) >= limit:
            break
        try:
            letter = str(getattr(getattr(f, "type", None), "letter", "?"))
        except Exception:
            continue
        if letter == "P" and i > 0:
            arcs.append((i, i - 1, "fwd"))
        elif letter == "B":
            if i > 0:
                arcs.append((i, i - 1, "fwd"))
            if i + 1 < n:
                arcs.append((i, i + 1, "bwd"))
    return arcs


def decode_capability_note() -> str:
    return ("真解码器 uavs3dec @ tools/avs3bin/（uavs3d, libuavs3d(8) "
            "1.2.1_release, macOS arm64 cmake 构建，AVS3-P2 baseline）;"
            " `uavs3dec -i in.avs3 -o out.yuv -l 2 -t 8` 解出 1280x720/600 帧，"
            "md5=df6fff020f1e3e906237ee278c7db069 与官方重建 YUV 一致。"
            "本机 ffmpeg 9.0.2 仅能解析 avs3（codec_name=avs3, has_b_frames=1）"
            "而无解码器：-debug qp/mv 与 -show_frames 均为空，QP/运动走估算分支"
            "（运动测的是真解码像素经无损转封装后的 Farneback 流场）。")
