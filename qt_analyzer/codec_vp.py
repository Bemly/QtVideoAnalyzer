"""TrueMotion 家族 (VP6/VP8/VP9) 算法特点可视化。

只许 PySide6 + numpy + 标准库（无 cv2/ffmpeg 调用），纯函数 + 确定性映射，
供 main_window / graphs / video_widget 复用。

约定：
* ``family_of`` 归一 ``vp6/vp6f/vp6a/vp8/libvpx/vp9/libvpx-vp9`` 等写法。
* ``altref_markers`` 返回 ``[(index, kind)]``，``kind`` ∈ ``{"key","altref","golden"}``，
  其中 ``key`` 即 Golden（关键帧同时充当 Golden 参考，故不再另发 ``golden``；
  ``golden`` 保留为 ``key`` 的别名，历史调用方按 ``key`` 处理即可）。
* ``segmentation_overlay`` 返回 ``[(x0,y0,x1,y1,seg)]``，``seg`` ∈ ``0..3``，
  对应 ``SEG_QP_OFFSET = {0:-6, 1:0, 2:+6, 3:+12}``。
"""
from __future__ import annotations

import numpy as np

try:  # 颜色仅用于 UI Tip；无 Qt 环境也不影响纯函数
    from PySide6.QtGui import QColor  # type: ignore
except Exception:  # pragma: no cover
    QColor = None  # type: ignore

# 段 -> QP 偏移（VP8 手册口径；VP9 工具内同样量化到 4 档以便同色系对比，
# 完整 8 段见 describe("vp9") 说明）。
SEG_QP_OFFSET = {0: -6, 1: 0, 2: 6, 3: 12}

# 段 -> 展示色（RGB，与 video_widget 叠加层同色系：蓝/绿/黄/红由弱到强）。
SEG_COLORS = {
    0: (76, 139, 232),    # 蓝：qp -6（更精细）
    1: (53, 199, 89),     # 绿：qp +0（基准）
    2: (232, 192, 80),    # 黄：qp +6
    3: (242, 43, 43),     # 红：qp +12（最粗）
}

_ALTREF_RATIO = 1.8  # P 大包判定：packet_size > 1.8 * P 均值


# ------------------------------------------------------------------ 归一化

def _norm(codec: object) -> str:
    c = str(codec or "").strip().lower().replace("_", "-").replace(" ", "")
    if c in ("vp6", "vp6f", "vp6a", "vp6s", "true-motion-vp6", "on2-vp6"):
        return "vp6"
    if c in ("vp8", "libvpx", "vp8o", "on2-vp8", "google-vp8", "v_vp8", "avc-vp8"):
        # "libvpx" 默认指 VP8（VP9 显式写 libvpx-vp9）
        return "vp8"
    if c in ("vp9", "libvpx-vp9", "libvpx-vp9-enc", "vp9o", "google-vp9",
             "v_vp9", "avc-vp9"):
        return "vp9"
    if "vp9" in c:
        return "vp9"
    if "vp8" in c or c == "libvpx":
        return "vp8"
    if "vp6" in c:
        return "vp6"
    return c


def family_of(codec: object) -> str:
    """VP6/VP8/VP9 统归 ``"TrueMotion"``；未知返回 ``"unknown"``。"""
    if _norm(codec) in ("vp6", "vp8", "vp9"):
        return "TrueMotion"
    return "unknown"


def describe(codec: object) -> dict:
    """返回该编码的算法特点字典（大小写/别名不敏感）。

    保证关键字（供 UI 与回归检查子串）：
    * vp6：``Golden``、无 B 帧、``flv``
    * vp8：``Golden+AltRef``、``4`` 段 ``segmentation``、``in-loop`` 滤波分段强度、``bool coder``
    * vp9：``SuperBlock 64``、``8`` 段分割、``tile`` 并行、``compound`` AltRef
    """
    n = _norm(codec)
    if n == "vp6":
        return {
            "codec": "vp6",
            "family": "TrueMotion",
            "full_name": "On2 TrueMotion VP6 (Flash 时代)",
            "container": "flv（Flash Video，VP6F 四字符码）",
            "references": ["Golden（key=Golden：关键帧即 Golden 参考）"],
            "b_frames": False,
            "b_note": "无B帧：只有 I/P，Golden 帧报 I、其余报 P",
            "golden": True,
            "altref": False,
            "segmentation": "无 segmentation（不分段，全 seg0）",
            "block": "16x16 宏块 MacroBlock",
            "loop_filter": "环路滤波弱（VP6 时代简单去块）",
            "entropy": "可变长 Huffman 系 token 编码（非 VP8 式 bool coder）",
            "tiles": False,
            "compound": False,
            "notes": "TrueMotion Golden帧起点：单 Golden 参考 + 无B帧 + flv 容器；"
                     "本工具中 key 帧即 Golden，REORDER 平坦。",
        }
    if n == "vp8":
        return {
            "codec": "vp8",
            "family": "TrueMotion",
            "full_name": "On2/Google VP8 (WebM, RFC 6386)",
            "container": "webm（libvpx，-auto-alt-ref 1 -lag-in-frames 25）",
            "references": ["Last", "Golden", "AltRef（不可见替代参考）"],
            "ref_note": "Golden+AltRef：Golden 存长时参考，AltRef 由滞后未来帧合成、不显示",
            "b_frames": False,
            "b_note": "无B帧：Golden/AltRef 都报 P（ffprobe 全片 I/P，无 B 排）",
            "golden": True,
            "altref": True,
            "segmentation": "4 segmentation（segment 0..3）",
            "seg_qp_offset": dict(SEG_QP_OFFSET),
            "block": "16x16 宏块 MacroBlock（16 网格覆盖层）",
            "loop_filter": "in-loop 滤波分段强度：去块强度按段独立配置",
            "entropy": "bool coder（二元算术编码，VP8 bool coder）",
            "tiles": False,
            "compound": False,
            "notes": "Golden+AltRef + 4 segmentation + in-loop 滤波分段强度 + bool coder；"
                     "周期性 P 大包即 AltRef 痕迹。",
        }
    if n == "vp9":
        return {
            "codec": "vp9",
            "family": "TrueMotion",
            "full_name": "Google VP9 (WebM)",
            "container": "webm（libvpx-vp9，-bf 3 实为 AltRef 机制）",
            "references": ["Last", "Golden", "AltRef", "compound AltRef（双参考复合预测）"],
            "ref_note": "compound AltRef：当前帧可同时参考 Last+Golden/AltRef",
            "b_frames": False,
            "b_note": "无B帧：AltRef/compound 帧仍报 P（全片 I/P，无 B 排）",
            "golden": True,
            "altref": True,
            "segmentation": "8 段分割（segment 0..7；本工具覆盖层量化到 4 档同色显示）",
            "seg_qp_offset": dict(SEG_QP_OFFSET),
            "block": "SuperBlock 64x64（64 SuperBlock 粗网格 + 段色）",
            "loop_filter": "in-loop 滤波分段强度（沿用 VP8 思路，段数扩到 8）",
            "entropy": "bool coder（二元算术编码，VP9 系）",
            "tiles": True,
            "tile_note": "tile 并行：帧切分为多 tile 列/行并行解码",
            "compound": True,
            "compound_note": compound_note("vp9"),
            "notes": "SuperBlock 64 + 8 段分割 + tile 并行 + compound AltRef；"
                     "motion 图 fwd/bwd 双向混出现即 compound 痕迹。",
        }
    return {
        "codec": str(codec or "unknown"),
        "family": "unknown",
        "full_name": f"unknown ({codec})",
        "container": "unknown",
        "references": [],
        "b_frames": False,
        "golden": False,
        "altref": False,
        "segmentation": "unknown",
        "block": "unknown",
        "loop_filter": "unknown",
        "entropy": "unknown",
        "tiles": False,
        "compound": False,
        "notes": "unknown codec：仅支持 vp6/vp8/vp9",
    }


# ------------------------------------------------------------------ AltRef

def _frame_index(f, fallback: int) -> int:
    try:
        return int(getattr(f, "index", fallback))
    except Exception:
        pass
    try:
        return int(f.get("index", fallback))  # type: ignore[union-attr]
    except Exception:
        return fallback


def _is_key(f) -> bool:
    try:
        if bool(getattr(f, "key_frame", False)):
            return True
    except Exception:
        pass
    try:
        return bool(f.get("key_frame", False))  # type: ignore[union-attr]
    except Exception:
        return False


def _pkt_size(f) -> int:
    try:
        return int(getattr(f, "packet_size", 0) or 0)
    except Exception:
        pass
    try:
        return int(f.get("packet_size", 0) or 0)  # type: ignore[union-attr]
    except Exception:
        return 0


def altref_markers(frames, codec: object = "vp8") -> list:
    """返回 ``[(index, kind)]``（按 index 升序）。

    * ``key``：关键帧（``key_frame``），即 Golden（``key=Golden``）；
      ``"golden"`` 为其别名，本函数统一 emits ``"key"``。
    * ``altref``：VP8/VP9 的周期性 P 大包帧（``packet_size > 1.8 * P均值``，
      P 均值取全部非 key 帧包大小均值；``~30 帧`` 周期由编码器
      ``-g 30 -lag-in-frames 25`` 自然形成，此处只按大小阈值判定）。
    * VP6（``codec="vp6"``）：仅返回 ``key`` 标记，不做大包判定。
    """
    if not frames:
        return []
    seq = list(frames)
    n = _norm(codec)
    out: list = []
    for i, f in enumerate(seq):
        if _is_key(f):
            out.append((_frame_index(f, i), "key"))
    if n == "vp6":
        out.sort(key=lambda e: e[0])
        return out
    # VP8/VP9（含未知默认走 VP8 路径）：大 P 包 -> altref
    sizes = np.asarray([float(_pkt_size(f)) for f in seq if not _is_key(f)],
                       dtype=np.float64)
    if sizes.size == 0:
        out.sort(key=lambda e: e[0])
        return out
    mean = float(sizes.mean()) if sizes.size else 0.0
    if not (mean > 0):
        out.sort(key=lambda e: e[0])
        return out
    thresh = mean * _ALTREF_RATIO
    for i, f in enumerate(seq):
        if _is_key(f):
            continue
        if float(_pkt_size(f)) > thresh:
            out.append((_frame_index(f, i), "altref"))
    out.sort(key=lambda e: e[0])
    return out


# ------------------------------------------------------------------ segmentation

def _frame_seed(frame) -> int:
    """确定性种子：index + qp_avg（frame 可为 FrameInfo/int/None/dict）。"""
    idx = 0
    qp = 0
    if frame is None:
        return 0
    if isinstance(frame, (int, np.integer)):
        return int(frame)
    try:
        idx = int(getattr(frame, "index", 0) or 0)
    except Exception:
        try:
            idx = int(frame.get("index", 0) or 0)  # type: ignore[union-attr]
        except Exception:
            idx = 0
    try:
        q = getattr(frame, "qp_avg", None)
        if q is not None:
            qp = int(float(q))
    except Exception:
        qp = 0
    if qp == 0:
        try:
            q = frame.get("qp_avg", None)  # type: ignore[union-attr]
            if q is not None:
                qp = int(float(q))
        except Exception:
            qp = 0
    return idx + qp


def segmentation_overlay(w, h, frame=None, codec: object = "vp8") -> list:
    """返回 ``[(x0,y0,x1,y1,seg)]``（``seg`` ∈ 0..3），左闭右开像素坐标。

    * vp6：不分段，全 ``seg0``（仍按 16 网格返回，块数 = ceil 网格数）。
    * vp8：16x16 宏块网格，4 类 seg（``qp_offset -6/0/+6/+12``），
      ``seg = (bx*3 + by*7 + seed*5) % 4`` 确定性伪分段。
    * vp9：64x64 SuperBlock 粗网格 + 段色（同 4 档；真实 8 段见 ``describe``），
      ``seg = (sbx*5 + sby*11 + seed*3) % 4``。
    * ``w/h <= 0`` 返回 ``[]``；右下边缘按 ``w/h`` 裁剪。
    """
    try:
        w = int(w)
        h = int(h)
    except Exception:
        return []
    if w <= 0 or h <= 0:
        return []
    n = _norm(codec)
    seed = _frame_seed(frame)
    out: list = []
    if n == "vp6":
        cell = 16
        cols = (w + cell - 1) // cell
        rows = (h + cell - 1) // cell
        for by in range(rows):
            for bx in range(cols):
                x0, y0 = bx * cell, by * cell
                out.append((x0, y0, min(w, x0 + cell), min(h, y0 + cell), 0))
        return out
    if n == "vp9":
        cell = 64
        cols = (w + cell - 1) // cell
        rows = (h + cell - 1) // cell
        for sby in range(rows):
            for sbx in range(cols):
                seg = (sbx * 5 + sby * 11 + seed * 3) % 4
                x0, y0 = sbx * cell, sby * cell
                out.append((x0, y0, min(w, x0 + cell), min(h, y0 + cell), int(seg)))
        return out
    # vp8（含未知默认）：16 网格
    cell = 16
    cols = (w + cell - 1) // cell
    rows = (h + cell - 1) // cell
    for by in range(rows):
        for bx in range(cols):
            seg = (bx * 3 + by * 7 + seed * 5) % 4
            x0, y0 = bx * cell, by * cell
            out.append((x0, y0, min(w, x0 + cell), min(h, y0 + cell), int(seg)))
    return out


def seg_qp_offset(seg: int) -> int:
    """段 -> QP 偏移（``{0:-6, 1:0, 2:+6, 3:+12}``，越界钳制到 0..3）。"""
    try:
        s = int(seg) % 4
    except Exception:
        s = 1
    return SEG_QP_OFFSET[s]


def seg_color(seg: int):
    """段 -> ``QColor``（无 Qt 时返回 RGB 元组）。"""
    try:
        s = int(seg) % 4
    except Exception:
        s = 1
    rgb = SEG_COLORS[s]
    if QColor is None:
        return rgb
    try:
        return QColor(*rgb)
    except Exception:
        return rgb


# ------------------------------------------------------------------ compound

def compound_note(codec: object = "vp9") -> str:
    """VP9 compound 预测一句话解释（vp6/vp8 返回“不支持”版）。"""
    n = _norm(codec)
    if n == "vp9":
        return ("VP9 compound 预测：同一 inter 块可同时参考两帧（如 Last+Golden / "
                "Last+AltRef），在压缩域做双向加权平均——形似 B 帧双向预测，"
                "但不引入显示序重排（ffprobe 仍报 P，REORDER 平坦）。"
                "在本工具 motion 图上：同一 P 帧内 fwd（绿）与 bwd（品红）矢量混现，"
                "即 compound 痕迹；周期性 P 大包多为 AltRef/compound 参考帧。")
    if n == "vp8":
        return ("VP8 无 compound：每块只单参考（Last / Golden / AltRef 三选一），"
                "motion 图以 fwd（绿）为主；AltRef 仍通过周期性 P 大包体现。")
    if n == "vp6":
        return ("VP6 无 compound/AltRef：单 Golden 参考、无 B 帧、无分段；"
                "关键帧即 Golden，motion 图仅 fwd 痕迹。")
    return f"unknown codec ({codec})：compound 解释仅适用于 vp9。"
