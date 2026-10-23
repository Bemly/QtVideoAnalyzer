"""Apple ProRes (中间码/剪辑格式)算法特点可视化。

Qt port helper: 解释 ProRes 为什么适合剪辑 (全 I 帧 intra-only、无 P/B、
无重排) 以及它为此付出的代价 (高码率、DCT + 类 JPEG 熵编码、10bit 422)。

只依赖 PySide6 + numpy + 标准库 (与 ``block.py`` 同规则)。

提供的三件套::

    describe()                  # 一 dict 口径: 全 I / slice 并行 / 10bit422 / 高码率 / DCT+熵编码
    slice_overlay(w, h)         # 8 横条 slice + 16x16 DCT 网格, 供 viewer 覆盖层绘制
    all_intra_stats(frames)     # I 占比 / GOP 长 / 重排 / 包大小 vs AVC 倍数 (又大又稳)

``slice_overlay`` 返回扁平 ``list[tuple]``::

    (x0, y0, x1, y1, kind, index)

其中 ``kind`` 为 ``"slice"`` (8 条横带, ProRes slice 并行解码示意) 或
``"dct"`` (16x16 DCT 块网格)。``index`` 为 slice 序号 (0..7) 或 DCT 块
行主序序号。坐标均裁剪到 ``w`` x ``h``。
"""
from __future__ import annotations

import subprocess

import numpy as np
from PySide6.QtGui import QColor

try:  # package import
    from .models import PicType
except ImportError:  # flat-script import from inside qt_analyzer/
    from models import PicType  # type: ignore[no-redef]

# ProRes 一帧按宽度切成若干 slice 独立编解码, 典型实现按 8 横条并行。
N_SLICES = 8
# ProRes 帧内编码块变换尺寸 (亮度 DCT 块)。
DCT_SIZE = 16

# 8 条 slice 的覆盖层颜色 (等距色相, alpha ~90 供叠加绘制)。
_SLICE_QCOLORS = tuple(
    QColor.fromHsv(int(360 * i / N_SLICES), 150, 235, 90) for i in range(N_SLICES)
)


def describe() -> dict:
    """一 dict 口径: ProRes 算法特点 (中间码定位)。"""
    return {
        "codec": "Apple ProRes",
        "prediction": "全 I 帧 intra-only: 每帧独立编解码, 无 P/B、无帧间 "
                      "预测、无重排, 任意帧可做随机访问点/剪辑点",
        "slices_threads": "一帧按宽度切成多个 slice (常以 8 横条示意), "
                          "slice 间独立编解码, 天然多线程并行, 解码延迟低",
        "chroma_bitdepth": "10bit 4:2:2 (yuv422p10le): 色度半分辨率但 10bit "
                           "量化, 调色/抠像余量大, 无 420 的色度锯齿",
        "bitrate": "高码率换质量: 同等观感下数倍于 AVC/H.264, 1080p 量级 "
                   "~150Mbps (HQ 口径), 本工具 640x360 测试片即 ~14.7Mbps",
        "transform_entropy": "DCT (16x16 网格示意) + 类 JPEG 熵编码: 帧内空域 "
                             "预测后 DCT 量化, 熵编码与 Motion-JPEG 同源, "
                             "无 CABAC 那类跨帧上下文",
        "editing_vs_delivery": "适合剪辑不适合分发: 剪辑要求随机访问+低解码 "
                               "成本 (全 I 即得), 分发要求极致压缩 (要靠 P/B "
                               "省码率); ProRes 选了前者, 文件又大又稳",
        "profile": "本工具测试片: prores_ks -profile:v 2 (Standard, HQ 口径), "
                   "640x360/30fps/3s, pix_fmt yuv422p10le",
    }


def slice_overlay(w: int, h: int) -> list:
    """8 横条 slice + 16x16 DCT 网格, 返回 ``(x0,y0,x1,y1,kind,index)`` 列表。

    前 ``N_SLICES`` 项为横向 slice 条带 (ProRes slice 并行解码示意,
    高 ``h // 8``, 末条吃掉余数); 其后为 16x16 DCT 块网格 (边缘块裁剪)。
    输入非法 (``w/h <= 0``) 返回空列表, 永不抛错。
    """
    try:
        w, h = int(w), int(h)
    except Exception:
        return []
    if w <= 0 or h <= 0:
        return []
    out: list = []
    # 8 横条 slice: y 方向等分, 末条吸收余数像素。
    base = h // N_SLICES
    extra = h % N_SLICES
    y0 = 0
    for i in range(N_SLICES):
        hh = base + (1 if i == N_SLICES - 1 else 0) * extra
        # 余数全部并入末条 (常规 h=360: 8x45 整除, extra=0)。
        y1 = min(h, y0 + hh) if i < N_SLICES - 1 else h
        if y1 > y0:
            out.append((0, y0, w, y1, "slice", i))
        y0 = y1
    # 16x16 DCT 网格 (行主序, 边缘块裁剪到帧边界)。
    idx = 0
    for by in range(0, h, DCT_SIZE):
        for bx in range(0, w, DCT_SIZE):
            x1 = min(w, bx + DCT_SIZE)
            y1 = min(h, by + DCT_SIZE)
            out.append((bx, by, x1, y1, "dct", idx))
            idx += 1
    return out


def slice_color(i: int) -> QColor:
    """第 ``i`` 条 slice 的覆盖层颜色 (8 色循环)。"""
    try:
        return QColor(_SLICE_QCOLORS[int(i) % N_SLICES])
    except Exception:
        return QColor(_SLICE_QCOLORS[0])


def _avc_baseline_guess() -> float | None:
    """同目录 ``test_avc.mp4`` (同 640x360) 的平均包字节数, 失败返回 None。

    只在 ``all_intra_stats`` 未显式传入 ``avc_avg_bytes`` 时调用; 纯 stdlib
    subprocess, 超时/缺文件一律吞掉 (import 永不抛错, 调用永不抛错)。
    """
    try:
        import os as _os

        here = _os.path.dirname(_os.path.abspath(__file__))
        cand = _os.path.join(here, "..", "tools", "samples", "test_avc.mp4")
        cand = _os.path.normpath(cand)
        if not _os.path.isfile(cand):
            return None
        from . import ffmpeg_locator as _fl  # type: ignore
    except Exception:
        try:
            import ffmpeg_locator as _fl  # type: ignore
            cand = "tools/samples/test_avc.mp4"
        except Exception:
            return None
    try:
        exe = _fl.ffprobe_path()
        if not exe:
            return None
        p = subprocess.run(
            [exe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "packet=size",
             "-of", "csv=p=0", cand],
            capture_output=True, text=True, timeout=60)
        sizes = [int(s) for s in (p.stdout or "").split() if s.strip().isdigit()]
        if not sizes:
            return None
        return float(sum(sizes) / len(sizes))
    except Exception:
        return None


def all_intra_stats(frames, avc_avg_bytes: float | None = None) -> dict:
    """全 I 帧统计: I 占比 / GOP 长 / 重排 / 包大小 vs AVC 倍数。

    ``frames`` 为 ``FrameInfo`` 列表 (要求 ``.type`` / ``.gop_position`` /
    ``.reorder_delta`` / ``.packet_size`` 字段, 缺字段降级为 0)。``avc_avg_bytes``
    为同分辨率 AVC 平均包字节 (显式传入优先, 否则自动找同目录测试片,
    找不到则相关倍数字段为 None)。永不抛错。
    """
    try:
        fs = list(frames or [])
    except Exception:
        fs = []
    n = len(fs)
    n_i = n_p = n_b = n_o = 0
    sizes: list[float] = []
    max_gop = 0
    max_reorder = 0
    for f in fs:
        try:
            t = f.type
            ti = int(t)
        except Exception:
            ti = 0
        if ti == int(PicType.I):
            n_i += 1
        elif ti == int(PicType.P):
            n_p += 1
        elif ti == int(PicType.B):
            n_b += 1
        else:
            # key_frame 兜底: 包级 K 旗即 I。
            try:
                if bool(getattr(f, "key_frame", False)):
                    n_i += 1
                else:
                    n_o += 1
            except Exception:
                n_o += 1
        try:
            sizes.append(float(getattr(f, "packet_size", 0) or 0))
        except Exception:
            sizes.append(0.0)
        try:
            g = int(getattr(f, "gop_position", 0) or 0)
            if g > max_gop:
                max_gop = g
        except Exception:
            pass
        try:
            r = abs(int(getattr(f, "reorder_delta", 0) or 0))
            if r > max_reorder:
                max_reorder = r
        except Exception:
            pass
    arr = np.asarray(sizes, dtype=np.float64) if sizes else np.zeros((0,))
    avg_size = float(arr.mean()) if arr.size else 0.0
    std_size = float(arr.std()) if arr.size else 0.0
    cv = (std_size / avg_size) if avg_size > 0 else 0.0

    base = avc_avg_bytes
    if base is None:
        try:
            base = _avc_baseline_guess()
        except Exception:
            base = None
    try:
        base_f = float(base) if base else 0.0
    except Exception:
        base_f = 0.0
    ratio = (avg_size / base_f) if base_f > 0 and avg_size > 0 else None

    return {
        "n_frames": int(n),
        "n_i": int(n_i),
        "n_p": int(n_p),
        "n_b": int(n_b),
        "n_other": int(n_o),
        "i_ratio": (n_i / n) if n else 0.0,
        "max_gop": int(max_gop),
        "max_reorder": int(max_reorder),
        "avg_packet_bytes": float(avg_size),
        "std_packet_bytes": float(std_size),
        "cv_packet_bytes": float(cv),
        "min_packet_bytes": float(arr.min()) if arr.size else 0.0,
        "max_packet_bytes": float(arr.max()) if arr.size else 0.0,
        "avc_avg_bytes": float(base_f) if base_f > 0 else None,
        "size_ratio_vs_avc": float(ratio) if ratio is not None else None,
        "verdict": ("又大又稳" if (ratio is not None and ratio > 1.0 and cv < 1.0)
                    else ("大" if (ratio is not None and ratio > 1.0) else "-")),
    }
