"""Pixel-domain helpers: blockiness / activity / blocking ratios (numpy).

Mirrors VideoAnalyzer/Services/BlockAnalysis.cs. Only numpy is used here
so the UI overlay and the motion fallback share one implementation.
"""
from __future__ import annotations

import numpy as np


def blockiness(gray: np.ndarray, block: int) -> float:
    """Mean gradient across block boundaries / mean gradient inside blocks.

    ``gray`` is a 2D uint8 image, ``block`` the block edge in pixels.
    Compression blocking pushes the ratio above 1 (C# BlockAnalysis.Blockiness
    uses horizontal gradients only; replicated here exactly).
    """
    if block < 2:
        return 1.0
    if not isinstance(gray, np.ndarray) or gray.ndim != 2 or gray.size == 0:
        return 1.0
    h, w = gray.shape
    if w < 3 or h < 1:
        return 1.0
    g = gray.astype(np.int16)
    # horizontal gradient at x for x = 1..w-1, then drop x = w-1 to match
    # the C# loop (x = 1 .. w-2).
    d = np.abs(g[:, 1:] - g[:, :-1])[:, :-1]
    xs = np.arange(1, w - 1)  # x value of each column in d
    mask = (xs % block) == 0
    if not np.any(mask) or not np.any(~mask):
        return 1.0
    b = float(d[:, mask].sum()) / float(d[:, mask].size)
    inner = float(d[:, ~mask].sum()) / float(d[:, ~mask].size)
    if inner <= 0.0001:
        return 1.0
    return b / inner


def activity_map(gray: np.ndarray, block: int) -> np.ndarray:
    """Per-block mean absolute gradient, normalised to 0..1.

    Returns a 2D float32 array of shape (rows, cols) that can drive the
    overlay opacity directly (C# BlockAnalysis.Activity).
    """
    block = max(2, int(block))
    if not isinstance(gray, np.ndarray) or gray.ndim != 2 or gray.size == 0:
        return np.zeros((1, 1), dtype=np.float32)
    h, w = gray.shape
    cols = max(1, w // block)
    rows = max(1, h // block)
    g = gray.astype(np.int16)
    gx = np.abs(g[:, 1:] - g[:, :-1])  # h x (w-1)
    gy = np.abs(g[1:, :] - g[:-1, :])  # (h-1) x w
    out = np.zeros((rows, cols), dtype=np.float32)
    peak = 0.0
    for by in range(rows):
        y0 = by * block
        y1 = min(h - 1, y0 + block)
        if y1 <= y0:
            continue
        for bx in range(cols):
            x0 = bx * block
            x1 = min(w - 1, x0 + block)
            if x1 <= x0:
                continue
            s = float(gx[y0:y1, x0:x1].sum()) + float(gy[y0:y1, x0:x1].sum())
            n = 2 * (y1 - y0) * (x1 - x0)
            v = s / n if n > 0 else 0.0
            out[by, bx] = v
            if v > peak:
                peak = v
    if peak > 0:
        out /= peak
    return out


def _to_gray(bgr: np.ndarray) -> np.ndarray:
    """BGR(A) -> BT.601 luma, integer math like C# BlockAnalysis.Luma."""
    if bgr.ndim == 2:
        return np.ascontiguousarray(bgr, dtype=np.uint8)
    h, w = bgr.shape[:2]
    if bgr.shape[2] >= 3:
        b = bgr[:, :, 0].astype(np.int32)
        g = bgr[:, :, 1].astype(np.int32)
        r = bgr[:, :, 2].astype(np.int32)
        return (((r * 77 + g * 150 + b * 29) >> 8).astype(np.uint8))
    return np.ascontiguousarray(bgr[:, :, 0], dtype=np.uint8)


def blocking_ratios(bgr: np.ndarray, cell: int) -> np.ndarray:
    """Per-cell edge/interior gradient ratio (macroblock grid highlight).

    Simplified gray version of C# BlockAnalysis.BlockingRatios: the mean
    gradient across each cell's top/left edges over the mean gradient inside
    it. Returns a 2D float32 array of shape (rows, cols); cells with no
    interior detail yield 0.
    """
    cell = max(2, int(cell))
    gray = _to_gray(bgr)
    h, w = gray.shape
    cols = max(1, w // cell)
    rows = max(1, h // cell)
    g = gray.astype(np.int16)
    gx = np.abs(g[:, 1:] - g[:, :-1])  # h x (w-1)
    gy = np.abs(g[1:, :] - g[:-1, :])  # (h-1) x w
    out = np.zeros((rows, cols), dtype=np.float32)
    for by in range(rows):
        y0 = by * cell
        y1 = min(h - 1, y0 + cell)
        if y1 <= y0:
            continue
        for bx in range(cols):
            x0 = bx * cell
            x1 = min(w - 1, x0 + cell)
            if x1 <= x0:
                continue
            patch = gx[y0:y1, x0:x1].astype(np.int32) + gy[y0:y1, x0:x1].astype(np.int32)
            if patch.size == 0:
                continue
            edge = float(patch[0, :].sum() + (patch[1:, 0].sum() if patch.shape[0] > 1 else 0.0))
            total = float(patch.sum())
            n_edge = (x1 - x0) + (y1 - y0 - 1)
            n_inner = patch.size - n_edge
            if n_edge <= 0 or n_inner <= 0 or total - edge <= 0:
                out[by, bx] = 0.0
                continue
            out[by, bx] = (edge / (2.0 * n_edge)) / ((total - edge) / (2.0 * n_inner))
    return out
