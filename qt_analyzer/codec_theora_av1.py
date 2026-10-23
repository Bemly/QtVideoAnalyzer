"""Theora + AV1 algorithm visualisation helpers. Qt port notes, no C# twin.

Only deps: PySide6 + numpy + stdlib (no cv2/scipy), so unit tests and the
Qt overlay import it freely.

Covers the two open-format ends:

* Theora -- oldest open video codec in this tool (VP3 lineage, 2004).
* AV1     -- newest open video codec in this tool (AOM, 2018).

The overlay entry point is :func:`superblock_overlay`, which returns plain
``(x0, y0, size)`` boxes the Qt layer can paint without knowing the codec.
"""
from __future__ import annotations

import math

import numpy as np

__all__ = [
    "SUPPORTED",
    "THEORA_BRAIN_THRESHOLD",
    "AV1_BRAIN_THRESHOLD",
    "DEFAULT_BRAIN_THRESHOLD",
    "AV1_SB",
    "THEORA_BLOCK",
    "describe",
    "theora_qmatrix_note",
    "obmc_vs_cdef",
    "superblock_overlay",
    "overlay_stats",
    "grain_table_note",
    "paint_superblock_overlay",
]

SUPPORTED = ("theora", "av1")

#: pixel-domain brain thresholds used by this tool. The shared motion
#: fallback flags ``brain`` at ``blockiness > 1.18`` (:mod:`motion`); the
#: codec views tighten/relax it: Theora 8x8 DCT has no normative loop
#: filter so edges stay sharp -> tighter; AV1 CDEF+LoopRestoration soften
#: boundaries -> relaxed.
THEORA_BRAIN_THRESHOLD = 1.12
AV1_BRAIN_THRESHOLD = 1.30
DEFAULT_BRAIN_THRESHOLD = 1.18

AV1_SB = 128
THEORA_BLOCK = 8


# ---------------------------------------------------------------- describe

def _key(codec: str) -> str:
    c = (codec or "").strip().lower()
    if c in ("theora", "theo", "ogv", "vp3", "libtheora"):
        return "theora"
    if c in ("av1", "aom", "aomav1", "libaom-av1", "libsvtav1", "svtav1", "av01"):
        return "av1"
    raise ValueError(f"unknown codec for this module: {codec!r} (want theora/av1)")


def describe(codec: str) -> dict:
    """Return the algorithm card for ``theora`` or ``av1``.

    Keys are stable for the doc table + UI tooltip. Raises
    :class:`ValueError` on anything else (this module only owns the two
    open-format ends).
    """
    k = _key(codec)
    if k == "theora":
        return {
            "codec": "theora",
            "full_name": "Theora (Xiph.org, VP3 lineage, 2004)",
            "era": "最老开放格式：On2 VP3.2 开放捐赠 -> Xiph Theora",
            "lineage": "VP3 血统：On2 TrueMotion VP3.2 -> Xiph Theora I (2004)",
            "transform": "前向 DCT 8x8（浮点/定点前向变换，逆变换近似即可解码）",
            "block": "8x8 DCT 块；宏块 16x16（4x 8x8 亮度 + 色度），无更小递归",
            "partitions": "固定 16x16 宏块 + 块内 8x8 系数编码，无递归/矩形细分",
            "prediction": "帧内预测极简（DC 预测为主），帧间为整/半像素块匹配",
            "bframes": False,
            "bframes_note": "无 B 帧：只有 I（关键帧）/ P（帧间），无双向/重排序",
            "container": "Ogg 映射（.ogv，Ogg Skeleton 逻辑流复用）",
            "quant": "自适应量化：逐帧 Q 矩阵缩放 + DC/AC 分开量化，16 级 Q 索引",
            "loop_filter": "无标准化环路滤波（仅可选非标准 deringing 后滤波）",
            "bitdepth": "8bit（yuv420p 为主）",
            "parallel": "基本无帧内并行（Ogg 页顺序解码）",
            "grain": "无 film grain 合成（胶片颗粒只能进残差）",
            "patent": "免费专利 lineage：VP3 专利开放 + Xiph 免版税承诺",
            "qp_native": False,
            "mv_native": False,
            "overlay_style": "theora-dots：8x8 DCT 块点阵（block-noise 点风格）",
            "brain_threshold": THEORA_BRAIN_THRESHOLD,
            "tool_note": "本工具：-debug qp/mv 无输出，走 bpp 估计 QP + Farneback 估计 motion",
        }
    return {
        "codec": "av1",
        "full_name": "AV1 (AOMedia Video 1, 2018)",
        "era": "最新开放格式：AOM（Google/Mozilla/Cisco/Netflix…）VP9/VP10 系",
        "lineage": "VP9/VP10 血统：Google VP10 实验分支合并 Daala/Thor/X Thor",
        "transform": "混合变换：4x4~64x64 DCT/DST/ADST/identity/flip 组合可选",
        "block": "Superblock 128x128 起点，递归 4 分 + 10 种矩形/AB 分区到 4x4",
        "partitions": "SB 128x128 -> 64 -> 32 -> … 最小 4x4，楔形/compound 可再分",
        "prediction": "帧内 56 种方向 + CFL/调色板；帧间 7 参考帧 compound 统一预测",
        "compound_note": "compound 单双向统一：单向/双向都是 compound 预测的子集，"
                         "ffprobe 无 B 帧概念（alt-ref/双向帧仍报 P）",
        "bframes": False,
        "bframes_note": "名义无 B 帧：AOM 不分 I/P/B，只有 Key/Inter/Alt-Ref；"
                        "ffprobe 全报 P，本工具 I/P/B 栏 B 恒 0",
        "container": "mp4/webm/ivf 均可（测试片为 mp4 + libsvtav1）",
        "quant": "Q 索引 0~255（配合 CDEF/LoopRestore，残差量化后仍保主观细节）",
        "loop_filter": "CDEF（方向约束去块）+ LoopRestoration（Wiener/self-guided）",
        "bitdepth": "8/10/12bit（HDR 主流 10bit；测试片 yuv420p 8bit）",
        "parallel": "tile + row-mt 并行（SB 行级多线程，测试片 preset 8 开）",
        "grain": "film grain 合成（帧头参数表，见 grain_table_note）",
        "patent": "免费专利 lineage：AOM 专利池免版税（W3C/Alliance for Open Media）",
        "qp_native": False,
        "mv_native": False,
        "overlay_style": "av1-sb：128 SB 网格（I 整块，P 按 motion 强度 128->64->32 示意细分）",
        "brain_threshold": AV1_BRAIN_THRESHOLD,
        "tool_note": "本工具：-debug qp/mv 无输出，走 bpp 估计 QP + Farneback 估计 motion；"
                     "B 恒 0 属正常",
    }


# ------------------------------------------------------- qmatrix / filters

def theora_qmatrix_note() -> str:
    """One-paragraph Theora quantisation note (UI tooltip / doc)."""
    return (
        "Theora 自适应量化：每帧带一组 Q 缩放索引（共 16 档），同一帧内 DC 与 AC "
        "用不同量化步长——DC 步长小保亮度基线，AC 高频步长大省码率；质量字（quality) "
        "整体缩放两套基矩阵。无 B 帧双向加权、无 MB 级 delta-QP（不像 H.264），"
        "所以本工具的 QP 曲线呈“台阶状平台”：I 帧一档、P 帧一档，帧内几乎无抖动。"
        "块效应重的原因：8x8 前向 DCT + 无标准化环路滤波，量化误差直接留在块边界上，"
        "故 brain 判定收紧到 blockiness > 1.12（比默认 1.18 更敏感）。"
    )


def _to_gray(frame) -> np.ndarray | None:
    try:
        a = np.asarray(frame)
    except Exception:
        return None
    if a.size == 0:
        return None
    try:
        if a.ndim == 2:
            return np.ascontiguousarray(a, dtype=np.uint8)
        if a.ndim == 3 and a.shape[2] >= 3:
            b = a[:, :, 0].astype(np.int32)
            g = a[:, :, 1].astype(np.int32)
            r = a[:, :, 2].astype(np.int32)
            return (((r * 77 + g * 150 + b * 29) >> 8)).astype(np.uint8)
        return None
    except Exception:
        return None


def _blockiness(gray: np.ndarray, block: int) -> float:
    """Local copy of block.Blockiness (keeps this module numpy-only)."""
    if block < 2 or gray.ndim != 2 or gray.size == 0:
        return 1.0
    h, w = gray.shape
    if w < 3 or h < 1:
        return 1.0
    g = gray.astype(np.int16)
    d = np.abs(g[:, 1:] - g[:, :-1])[:, :-1]
    xs = np.arange(1, w - 1)
    mask = (xs % block) == 0
    if not np.any(mask) or not np.any(~mask):
        return 1.0
    b = float(d[:, mask].sum()) / float(d[:, mask].size)
    inner = float(d[:, ~mask].sum()) / float(d[:, ~mask].size)
    if inner <= 0.0001:
        return 1.0
    return b / inner


def obmc_vs_cdef(frame=None) -> str:
    """Explain Theora-blocky vs AV1-CDEF-soft for *frame*.

    *frame* may be a BGR/gray ``numpy`` image, a ``FrameInfo``-like (uses
    ``qp_min/qp_max/brain``), or ``None``. Always returns the teaching
    paragraph; when pixels are given the measured ``blockiness@8`` plus
    both threshold verdicts are appended.
    """
    head = (
        "老式块运动补偿（Theora/VP3 系，无 OBMC/CDEF 平滑、无标准化环路滤波）"
        "把 8x8 DCT 量化误差直接留在块边界上：边界梯度 / 内部梯度（blockiness@8）"
        "稍一抬头就是真块效应，所以阈值收紧到 1.12。"
        "AV1 则相反：CDEF 按块方向做约束滤波 + LoopRestoration 做 Wiener/self-guided "
        "恢复，边界被抹柔、内部纹理被拉回，同样 blockiness 数值下主观块效应轻得多，"
        "所以阈值放宽到 1.30，且残差 QP 带更平（I/P 台阶差小）。"
    )
    # FrameInfo-style input: report its QP spread vs thresholds.
    if frame is not None and not isinstance(frame, np.ndarray):
        try:
            qmin = float(getattr(frame, "qp_min"))
            qmax = float(getattr(frame, "qp_max"))
            letter = str(getattr(getattr(frame, "type", "?"), "letter", "?"))
            brain = bool(getattr(frame, "brain", False))
            spread = qmax - qmin
            return (
                f"{head} 当前帧 {letter}: QP 带 [{qmin:.1f},{qmax:.1f}] "
                f"宽 {spread:.1f}（theora 预期窄台阶、av1 更平），brain={brain:d}。"
            )
        except Exception:
            return head
    if frame is None:
        return head + "（未给像素：给一帧 BGR/gray ndarray 即附实测 blockiness@8 与双阈值 verdict。）"
    gray = _to_gray(frame)
    if gray is None:
        return head
    try:
        b = _blockiness(gray, 8)
    except Exception:
        return head
    t_verdict = "brain 可疑" if b > THEORA_BRAIN_THRESHOLD else "干净"
    a_verdict = "brain 可疑" if b > AV1_BRAIN_THRESHOLD else "干净"
    return (
        f"{head} 实测 blockiness@8={b:.3f}："
        f"按 theora 阈值 1.12 -> {t_verdict}；按 av1 阈值 1.30 -> {a_verdict}。"
        f"（默认回退阈值 1.18 介于两者之间。）"
    )


# ------------------------------------------------------------- overlays

def _letter(frame) -> str:
    try:
        if frame is None:
            return "I"
        t = getattr(frame, "type", None)
        if t is not None:
            letter = getattr(t, "letter", None)
            if callable(letter):
                return str(letter())
            if letter is not None:
                return str(letter)
            s = str(t).upper()
            for c in ("I", "P", "B"):
                if c in s:
                    return c
            return "?"
        if isinstance(frame, dict):
            for k in ("letter", "type", "pic_type", "pict_type"):
                v = frame.get(k)
                if v is not None:
                    s = str(v).upper()
                    if s[:1] in ("I", "P", "B"):
                        return s[:1]
        return "?"
    except Exception:
        return "?"


def _motion_mean(frame) -> float:
    try:
        if frame is None:
            return 0.0
        v = getattr(frame, "motion_mean", None)
        if v is None and isinstance(frame, dict):
            v = frame.get("motion_mean", 0.0)
        return float(v or 0.0)
    except Exception:
        return 0.0


def superblock_overlay(w: int, h: int, frame=None, codec: str = "av1") -> list:
    """Return overlay boxes ``[(x0, y0, size), ...]`` (source pixels).

    * ``av1``: 128x128 SB 网格。I 帧（或 ``frame=None``）整块返回；
      P/B 按 motion 强度示意细分：弱 128 / 中 64（1 变 4）/ 强 32（1 变 16）。
      有 ``frame.motion`` 场时按 SB 局部/全局 motion 比判定，否则按整帧
      ``motion_mean``（<1.0 / <3.0 / 其它）判定。
    * ``theora``: 8x8 DCT 块点阵（``block-noise`` 点风格，画点即可），
      与帧类型/motion 无关。
    """
    k = _key(codec)
    w, h = max(1, int(w)), max(1, int(h))
    if k == "theora":
        out: list = []
        for y in range(0, h, THEORA_BLOCK):
            if y + THEORA_BLOCK > h:
                break
            for x in range(0, w, THEORA_BLOCK):
                if x + THEORA_BLOCK > w:
                    break
                out.append((x, y, THEORA_BLOCK))
        return out
    # ---- av1 SB grid
    sbs: list = []
    for y0 in range(0, h, AV1_SB):
        for x0 in range(0, w, AV1_SB):
            sbs.append((x0, y0))
    letter = _letter(frame)
    if letter == "I":
        return [(x0, y0, AV1_SB) for (x0, y0) in sbs]
    # per-SB split level: 128 / 64 / 32
    field = getattr(frame, "motion", None) if frame is not None else None
    if isinstance(frame, dict):
        field = frame.get("motion", field)
    levels: dict = {}
    try:
        cols = int(getattr(field, "cols", 0))
        rows = int(getattr(field, "rows", 0))
        dx = list(getattr(field, "dx", []))
        dy = list(getattr(field, "dy", []))
        has_field = cols > 0 and rows > 0 and len(dx) >= cols * rows and len(dy) >= cols * rows
    except Exception:
        has_field = False
        cols = rows = 0
    if has_field:
        try:
            mag = np.hypot(np.asarray(dx[: cols * rows], dtype=np.float64),
                           np.asarray(dy[: cols * rows], dtype=np.float64)).reshape(rows, cols)
            glob = float(mag.mean()) if mag.size else 0.0
        except Exception:
            glob = 0.0
            mag = None
        if not (glob > 1e-9):
            for sb in sbs:
                levels[sb] = AV1_SB
        else:
            cw = w / float(cols)
            ch = h / float(rows)
            for (x0, y0) in sbs:
                x1, y1 = min(w, x0 + AV1_SB), min(h, y0 + AV1_SB)
                c0 = max(0, int(x0 / cw))
                c1 = min(cols - 1, int(max(0.0, (x1 - 1e-6) / cw)))
                r0 = max(0, int(y0 / ch))
                r1 = min(rows - 1, int(max(0.0, (y1 - 1e-6) / ch)))
                try:
                    local = float(mag[r0: r1 + 1, c0: c1 + 1].mean())
                except Exception:
                    local = glob
                r = local / (glob + 1e-9)
                if r < 0.75:
                    levels[(x0, y0)] = AV1_SB
                elif r < 1.5:
                    levels[(x0, y0)] = 64
                else:
                    levels[(x0, y0)] = 32
    else:
        m = _motion_mean(frame)
        if m < 1.0:
            lv = AV1_SB
        elif m < 3.0:
            lv = 64
        else:
            lv = 32
        for sb in sbs:
            levels[sb] = lv
    out = []
    for (x0, y0) in sbs:
        lv = levels.get((x0, y0), AV1_SB)
        if lv >= AV1_SB:
            out.append((x0, y0, AV1_SB))
        elif lv == 64:
            for oy in (0, 64):
                for ox in (0, 64):
                    xx, yy = x0 + ox, y0 + oy
                    if xx < w and yy < h:
                        out.append((xx, yy, 64))
        else:
            for oy in range(0, AV1_SB, 32):
                for ox in range(0, AV1_SB, 32):
                    xx, yy = x0 + ox, y0 + oy
                    if xx < w and yy < h:
                        out.append((xx, yy, 32))
    return out


def overlay_stats(w: int, h: int, frame=None, codec: str = "av1") -> dict:
    """Base SB/dot count + subdivision rate for the selftest/doc table."""
    k = _key(codec)
    boxes = superblock_overlay(w, h, frame, codec)
    if k == "theora":
        cols, rows = w // 8, h // 8
        return {"codec": "theora", "base": cols * rows, "total": len(boxes),
                "cols": cols, "rows": rows, "subdiv_rate": 0.0,
                "note": f"{cols}x{rows} 8x8 点阵"}
    base_cols = math.ceil(w / AV1_SB)
    base_rows = math.ceil(h / AV1_SB)
    base = base_cols * base_rows
    total = len(boxes)
    subdiv = sum(1 for b in boxes if b[2] < AV1_SB)
    return {"codec": "av1", "base": base, "total": total,
            "cols": base_cols, "rows": base_rows,
            "subdiv_blocks": subdiv,
            "subdiv_rate": (total - base) / base if base else 0.0,
            "note": f"{base_cols}x{base_rows} SB，细分后 {total} 块"}


# ---------------------------------------------------------------- grain

def grain_table_note() -> str:
    """AV1 film-grain header note: why low BITRATE can still look detailed."""
    return (
        "AV1 film grain 参数存在帧头、不占残差码率：apply_grain / grain_seed / "
        "num_y_points（亮度映射点）/ num_cb/cr_points / scaling_shift 等随每帧 OBU 头 "
        "下发（<100 字节量级），解码器在 CDEF + LoopRestoration 之后按参数合成高斯颗粒 "
        "叠回画面。正确读法：BITRATE 曲线低不等于“抹平/丢细节”——先看本备注：若片源带 "
        "grain（libaom/libsvtav1 默认保留胶片颗粒时），残差只编“去噪后的干净底图”，"
        "颗粒由合成器补回，主观细节多而包字节小。本工具 ffprobe 读不到 grain 表，"
        "故 MOTION/QP 正常但画面偏“糙”时，应优先怀疑 grain 合成而非估计错误。"
    )


# ---------------------------------------------------------------- Qt paint

def paint_superblock_overlay(painter, dx: float, dy: float, dw: float, dh: float,
                             src_w: int, src_h: int, boxes: list,
                             codec: str = "av1") -> None:
    """Paint *boxes* (from :func:`superblock_overlay`) onto a fitted rect.

    av1: 画矩形框（128 粗 / 64 细 / 32 更细）；theora：画 block-noise 点。
    Only PySide6 here; import is local so ``import codec_theora_av1`` never
    needs a QApplication.
    """
    from PySide6.QtGui import QColor, QPen  # noqa: PLC0415
    from PySide6.QtCore import Qt  # noqa: PLC0415

    k = _key(codec)
    if src_w <= 0 or src_h <= 0 or not boxes:
        return
    sx = dw / float(src_w)
    sy = dh / float(src_h)
    if k == "theora":
        painter.setPen(QPen(QColor(0xFF, 0xC0, 0x50, 170), 2))
        for (x0, y0, _s) in boxes[:: max(1, len(boxes) // 900)]:
            painter.drawPoint(int(dx + (x0 + 4) * sx), int(dy + (y0 + 4) * sy))
        return
    for (x0, y0, s) in boxes:
        x = dx + x0 * sx
        y = dy + y0 * sy
        ww = min(s, src_w - x0) * sx
        hh = min(s, src_h - y0) * sy
        if s >= 128:
            painter.setPen(QPen(QColor(0x5B, 0x9B, 0xFF, 200), 2))
        elif s == 64:
            painter.setPen(QPen(QColor(0x5B, 0x9B, 0xFF, 120), 1))
        else:
            painter.setPen(QPen(QColor(0x35, 0xFF, 0x7A, 110), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(int(x), int(y), max(1, int(ww)), max(1, int(hh)))
