"""HEVC (H.265) algorithm-advantage visualization.

Qt port helper: explains *why* HEVC saves bits (CTU quad-tree / SAO /
large-GOP) and gives the viewer two concrete artefacts:

* :func:`ctu_quadtree_overlay` -- simulated CTU partition overlay
  (``I`` shallow, ``P``/``B`` deep, deterministic per frame);
* :func:`gop_efficiency` -- B-share / GOP length / bits-per-GOP and a
  weighted saving estimate vs an AVC baseline (marked ``estimated``).

Deps: only PySide6 + numpy + stdlib (same rule as ``block.py``).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QColor

try:  # package import
    from .models import PicType
except ImportError:  # flat-script import from inside qt_analyzer/
    from models import PicType  # type: ignore[no-redef]

CTU_SIZE = 64
MIN_SIZE = 8  # depth 3
MAX_DEPTH = 3  # 64 -> 32 -> 16 -> 8

# Split probability per depth (0:64->32, 1:32->16, 2:16->8).
# I = shallow (large CU), P = medium, B = deep (small CU on detail/motion).
# Calibrated so a 640x360 frame (10x6 = 60 CTUs) yields ~90-130 leaves on
# I (mostly 64/32), ~400 on P and ~800+ on B (mostly 16/8).
_SPLIT_P = {
    "I": (0.12, 0.18, 0.15),
    "P": (0.35, 0.45, 0.40),
    "B": (0.55, 0.60, 0.50),
    "?": (0.35, 0.45, 0.40),
}

# Depth -> color (deeper = warmer). Alpha ~110 for overlay use.
_DEPTH_QCOLORS = (
    QColor(59, 130, 246, 110),   # 0: 64 -- cool blue
    QColor(34, 197, 94, 110),    # 1: 32 -- green
    QColor(245, 158, 11, 120),   # 2: 16 -- orange
    QColor(239, 68, 68, 130),    # 3: 8  -- warm red
)


def describe() -> dict:
    """One-dict summary of the HEVC advantage (CTU/SAO/Tiles/WPP/big-GOP/AMP)."""
    return {
        "codec": "HEVC (H.265)",
        "ctu": "CTU 64x64 (vs AVC macroblock 16x16): quad-tree CU 64/32/16/8, "
               "PU intra 35 modes / inter AMP 2NxN,Nx2N,2NxnU..., TU 32..4 RQT",
        "cu_pu_tu": "CU decide *size* (quad-tree split), PU decide *prediction "
                    "shape (incl. AMP asymmetric), TU decide *residual* transform "
                    "size (RQT, independent of PU)",
        "sao": "SAO (Sample Adaptive Offset, in-loop after deblock): band/edge "
               "offset kills ringing/banding so fewer bits are spent on residuals",
        "tiles_wpp": "Tiles (independent rectangles) + WPP (wavefront rows, "
                     "entropy state carried over): same stream scales over cores",
        "gop": "Large GOP + dense B (hierarchical B-pyramid, GOP 2-4x AVC): "
               "bi-prediction + longer reference distance amortises each I",
        "amp": "AMP asymmetric motion partitions catch object edges, "
               "smaller residuals on moving boundaries",
        "saving_vs_avc": "Same subjective quality at ~40% fewer bits than AVC "
                         "(~50% in the original JCT-VC target tests; ~35-45% "
                         "typical for libx265 vs libx264 on natural content)",
    }


def _frame_key(frame) -> tuple[str, float, int]:
    """(letter, qp_avg, index) used for seeding + split-bias."""
    try:
        t = frame.type
    except AttributeError:
        t = None
    letter = "?"
    try:
        if t is not None and hasattr(t, "letter"):
            letter = t.letter
        elif t is not None:
            letter = {1: "I", 2: "P", 3: "B"}.get(int(t), "?")
        else:
            key = getattr(frame, "key_frame", False)
            letter = "I" if key else "?"
    except Exception:
        letter = "?"
    if letter not in ("I", "P", "B"):
        try:
            letter = "I" if bool(getattr(frame, "key_frame", False)) else "P"
        except Exception:
            letter = "?"
    try:
        qp = getattr(frame, "qp_avg", None)
        qp_f = float(qp) if qp is not None else 26.0
    except Exception:
        qp_f = 26.0
    try:
        idx = int(getattr(frame, "index", 0))
    except Exception:
        idx = 0
    return letter, qp_f, idx


def ctu_quadtree_overlay(w: int, h: int, frame) -> list:
    """Simulated CTU quad-tree partition for overlay painting.

    Each 64x64 CTU is recursively split (64/32/16/8, depth 0..3):

    * ``I`` frames split shallow (mostly 64/32 -- flat intra prediction);
    * ``P``/``B`` frames split deep (mostly 16/8 on motion/detail edges).

    Deterministic per frame: the RNG seed is derived from
    ``frame.qp_avg`` (+ index/type so neighbours differ). Calling twice
    with the same frame object returns an identical list.

    Returns ``[(x0, y0, size, depth), ...]`` in row-major CTU order,
    clipped to ``w`` x ``h`` (edge CTUs keep a clipped ``size`` box but
    the ``depth`` still reflects the logical split level).
    """
    try:
        w, h = int(w), int(h)
    except Exception:
        return []
    if w <= 0 or h <= 0:
        return []
    letter, qp_f, idx = _frame_key(frame)
    base = _SPLIT_P.get(letter, _SPLIT_P["?"])
    # QP bias: low QP (= detail preserved) splits a bit more, high QP less.
    # Purely visual, keeps monotonic behaviour: qp 18 -> x1.10, qp 40 -> x0.82.
    bias = max(0.7, min(1.2, 1.0 + (26.0 - qp_f) / 80.0))
    probs = tuple(max(0.03, min(0.95, p * bias)) for p in base)
    # Stable seed from qp_avg (+ index/type): same frame -> same overlay.
    seed = (int(round(qp_f * 97.0)) * 31 + idx * 101
            + {"I": 11, "P": 53, "B": 97}.get(letter, 7)) & 0x7FFFFFFF
    rng = np.random.RandomState(seed)

    out: list = []

    def _recurse(x0: int, y0: int, size: int, depth: int) -> None:
        if x0 >= w or y0 >= h:
            return
        if depth >= MAX_DEPTH or size <= MIN_SIZE:
            out.append((x0, y0, size, min(depth, MAX_DEPTH)))
            return
        # Edge CTU hanging past the frame border: HEVC pads the picture to
        # the CTU grid, so the edge block is still coded as one unit --
        # emit it as-is (the painter clips to w x h), no forced split.
        if x0 + size > w or y0 + size > h:
            out.append((x0, y0, size, depth))
            return
        if rng.random() < probs[depth]:
            half = size // 2
            _recurse(x0, y0, half, depth + 1)
            _recurse(x0 + half, y0, half, depth + 1)
            _recurse(x0, y0 + half, half, depth + 1)
            _recurse(x0 + half, y0 + half, half, depth + 1)
        else:
            out.append((x0, y0, size, depth))

    for cy in range(0, h, CTU_SIZE):
        for cx in range(0, w, CTU_SIZE):
            _recurse(cx, cy, CTU_SIZE, 0)
    return out


def depth_color(depth: int) -> QColor:
    """Overlay color for a CTU depth (deeper = warmer)."""
    try:
        d = int(depth)
    except Exception:
        d = 0
    d = max(0, min(MAX_DEPTH, d))
    c = _DEPTH_QCOLORS[d]
    return QColor(c)


def gop_efficiency(frames) -> dict:
    """GOP efficiency + weighted saving estimate vs an AVC baseline.

    Saving model (illustrative only): HEVC is assumed to save 0% on I,
    15% on P and 35% on B bytes relative to AVC, i.e. the AVC baseline
    costs ``I + P/0.85 + B/0.65 (+Other/0.85)``. The returned dict always
    carries ``"note": "estimated ..."`` so the UI never presents it as
    measured.
    """
    frames = list(frames or [])
    n = len(frames)
    if n == 0:
        return {"n_frames": 0, "note": "estimated, no frames"}
    n_i = n_p = n_b = n_o = 0
    b_i = b_p = b_b = b_o = 0
    for f in frames:
        try:
            t = f.type
            ti = int(t)
        except Exception:
            ti = 0
        try:
            sz = int(getattr(f, "packet_size", 0) or 0)
        except Exception:
            sz = 0
        if ti == 1:
            n_i += 1
            b_i += sz
        elif ti == 2:
            n_p += 1
            b_p += sz
        elif ti == 3:
            n_b += 1
            b_b += sz
        else:
            n_o += 1
            b_o += sz
    # GOP segmentation: new GOP at each key_frame, else at each I.
    gop_lens: list[int] = []
    cur = 0
    for f in frames:
        try:
            key = bool(getattr(f, "key_frame", False))
        except Exception:
            key = False
        try:
            is_i = int(getattr(f, "type", 0)) == 1
        except Exception:
            is_i = False
        if (key or is_i) and cur > 0:
            gop_lens.append(cur)
            cur = 0
        cur += 1
    if cur > 0:
        gop_lens.append(cur)
    num_gops = len(gop_lens) or 1
    avg_gop = sum(gop_lens) / len(gop_lens) if gop_lens else float(n)
    i_interval = (n / n_i) if n_i else float(n)
    total_bytes = b_i + b_p + b_b + b_o
    bits_per_gop = (total_bytes * 8.0 / num_gops) if num_gops else 0.0
    baseline = b_i + b_p / 0.85 + b_b / 0.65 + b_o / 0.85
    saving = 1.0 - (total_bytes / baseline) if baseline > 0 else 0.0
    return {
        "n_frames": n,
        "n_i": n_i,
        "n_p": n_p,
        "n_b": n_b,
        "n_other": n_o,
        "b_ratio": (n_b / n) if n else 0.0,
        "avg_gop_len": float(avg_gop),
        "i_interval": float(i_interval),
        "num_gops": int(num_gops),
        "gop_lens": list(gop_lens),
        "bytes_total": int(total_bytes),
        "bits_per_gop": float(bits_per_gop),
        "bytes_baseline_avc_est": float(baseline),
        "saving_vs_avc": float(saving),
        "saving_model": "I 0% / P 15% / B 35% weighted by bytes",
        "note": "estimated: illustrative weighting vs AVC baseline, not measured",
    }


def sao_note() -> str:
    """Why SAO lets the blockiness (brain) threshold be relaxed."""
    return (
        "SAO (Sample Adaptive Offset) runs in-loop after deblocking and "
        "corrects band/edge offsets per CTB, removing the ringing/banding "
        "that a plain deblocker leaves behind. Residual block edges are "
        "therefore much weaker at the same QP, so the pixel-domain "
        "blockiness ('brain') detector can use a looser threshold for HEVC "
        "(>1.25) than for AVC/MPEG-2 (>1.18) without extra false positives."
    )
