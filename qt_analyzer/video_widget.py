"""Video display widget with analyser overlays. Qt port of VideoSurface.cs (simplified)."""
from __future__ import annotations

import math
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget


class VideoWidget(QWidget):
    """Shows an rgb24 frame + motion/grid/noise overlays. Double-click toggles fullscreen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self.setMouseTracking(True)
        self._arr: np.ndarray | None = None
        self._img: QImage | None = None
        self._img_w: int = 0
        self._img_h: int = 0
        self._field = None          # MotionField
        self._info = None           # FrameInfo
        self.show_vectors: bool = True
        self.show_grid: bool = False
        self.show_noise: bool = True
        self.codec_kind: str = "off"   # 关/ avc/h263/hevc/vpseg/av1sb/altref
        self.codec_data = None         # 各家族 overlay 原始列表

    # ------------------------------------------------------------------ input
    def show_frame(self, arr: np.ndarray | None) -> None:
        if arr is None:
            self._arr = None
            self._img = None
            self.update()
            return
        a = np.ascontiguousarray(arr, dtype=np.uint8)
        if a.ndim != 3 or a.shape[2] != 3:
            return
        h, w = int(a.shape[0]), int(a.shape[1])
        if h <= 0 or w <= 0:
            return
        self._arr = a
        # QImage references the numpy buffer; keep _arr alive.
        self._img = QImage(a.data, w, h, w * 3, QImage.Format.Format_RGB888)
        self._img_w, self._img_h = w, h
        self.update()

    def set_field(self, field) -> None:
        self._field = field
        self.update()

    def set_frame_info(self, info) -> None:
        self._info = info
        # keep field in sync when info carries one
        try:
            if info is not None and getattr(info, "motion", None) is not None:
                self._field = info.motion
        except Exception:
            pass
        self.update()

    def set_codec_overlay(self, kind, data) -> None:
        """Codec 层数据入口（main_window 统一调用）。永不抛错。"""
        try:
            self.codec_kind = str(kind or "off")
        except Exception:
            self.codec_kind = "off"
        try:
            self.codec_data = data
        except Exception:
            self.codec_data = None
        self.update()

    # ------------------------------------------------------------------ paint
    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self._img is None:
            p.setPen(QColor(0x5A, 0x60, 0x66))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "No media — Ctrl+O / drop file here\n无视频：Ctrl+O 打开或拖拽")
            p.end()
            return
        w, h = float(self.width()), float(self.height())
        sw, sh = float(self._img_w), float(self._img_h)
        scale = min(w / max(1.0, sw), h / max(1.0, sh))
        dw, dh = sw * scale, sh * scale
        dx, dy = (w - dw) / 2.0, (h - dh) / 2.0
        p.drawImage(int(dx), int(dy), self._img.scaled(
            int(max(1, dw)), int(max(1, dh)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation))
        # recompute exact fitted rect for overlay math (avoid rounding drift)
        p.save()
        p.setClipRect(int(dx), int(dy), int(dw) + 1, int(dh) + 1)
        if self.show_grid:
            self._draw_grid(p, dx, dy, dw, dh, scale)
        if self.show_noise:
            self._draw_noise(p, dx, dy, dw, dh)
        if self.show_vectors:
            self._draw_vectors(p, dx, dy, dw, dh)
        self._draw_codec_layer(p, dx, dy, dw, dh)
        self._draw_badge(p, dx, dy, dw, dh)
        p.restore()
        p.end()

    def _draw_vectors(self, p: QPainter, dx, dy, dw, dh) -> None:
        f = self._field
        if f is None:
            return
        try:
            cols, rows = int(f.cols), int(f.rows)
        except Exception:
            return
        if cols <= 0 or rows <= 0:
            return
        try:
            n = cols * rows
            dxs = list(f.dx)[:n]
            dys = list(f.dy)[:n]
            refs = list(f.ref)[:n]
        except Exception:
            return
        if len(dxs) < n or len(dys) < n:
            return
        if len(refs) < n:
            refs = [0] * n
        cell_w, cell_h = dw / cols, dh / rows
        peak = 1.0
        for i in range(n):
            try:
                peak = max(peak, math.hypot(float(dxs[i]), float(dys[i])))
            except Exception:
                pass
        gain = (min(cell_w, cell_h) * 0.85) / max(1e-6, peak)
        step = 2  # 每 2 块抽 1
        for r in range(0, rows, step):
            for c in range(0, cols, step):
                i = r * cols + c
                try:
                    vx, vy = float(dxs[i]), float(dys[i])
                except Exception:
                    continue
                if vx == 0 and vy == 0:
                    continue
                cx = dx + (c + 0.5) * cell_w
                cy = dy + (r + 0.5) * cell_h
                ex, ey = cx + vx * gain, cy + vy * gain
                ref = refs[i] if i < len(refs) else 0
                if ref == 2:
                    col = QColor(0xFF, 0x5C, 0xE0)  # bwd 品红
                else:
                    col = QColor(0x35, 0xFF, 0x7A)  # fwd 绿
                p.setPen(QPen(QColor(0, 0, 0, 120), 3))
                p.drawLine(int(cx), int(cy), int(ex), int(ey))
                p.setPen(QPen(col, 1.5))
                p.drawLine(int(cx), int(cy), int(ex), int(ey))
                # arrow head (two short ticks)
                ang = math.atan2(ey - cy, ex - cx)
                hl = max(4.0, cell_w * 0.22)
                for da in (0.44, -0.44):
                    a2 = ang + math.pi + da
                    p.drawLine(int(ex), int(ey),
                               int(ex + hl * math.cos(a2)), int(ey + hl * math.sin(a2)))

    def _draw_grid(self, p: QPainter, dx, dy, dw, dh, scale) -> None:
        # 16x16 源像素 pitch 换算到 widget 坐标；简化：假设显示帧即源
        src_w = float(self._img_w)
        buf_per_src = 1.0
        try:
            if self._info is not None:
                pass
        except Exception:
            pass
        cell_src = 16.0 * buf_per_src
        pitch_src_disp = cell_src * (dw / max(1.0, src_w))
        pitch = max(4.0, pitch_src_disp)
        # blockiness 简化：qp_max-qp_min 大的块高亮 —— 无逐块 qp 时以整帧 spread 决定颜色
        spread = 0.0
        try:
            if self._info is not None and self._info.qp_max is not None and self._info.qp_min is not None:
                spread = float(self._info.qp_max) - float(self._info.qp_min)
        except Exception:
            spread = 0.0
        hot = spread > 8.0
        base = QColor(0xFF, 0x9A, 0x2E, 140) if hot else QColor(0xFF, 0xFF, 0xFF, 48)
        p.setPen(QPen(base, 1))
        x = dx
        k = 0
        while x <= dx + dw + 0.5:
            if k % 4 == 0:
                p.setPen(QPen(base, 1.5))
            else:
                p.setPen(QPen(base, 1))
            p.drawLine(int(x), int(dy), int(x), int(dy + dh))
            x += pitch
            k += 1
        y = dy
        k = 0
        while y <= dy + dh + 0.5:
            if k % 4 == 0:
                p.setPen(QPen(base, 1.5))
            else:
                p.setPen(QPen(base, 1))
            p.drawLine(int(dx), int(y), int(dx + dw), int(y))
            y += pitch
            k += 1
        if hot:
            p.setPen(QPen(QColor(0xFF, 0x9A, 0x2E), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(int(dx) + 1, int(dy) + 1, int(dw) - 2, int(dh) - 2)
            p.setPen(QColor(0xFF, 0xC0, 0x50))
            p.drawText(int(dx) + 6, int(dy) + 16, f"blocky spread {spread:.0f}")

    def _draw_noise(self, p: QPainter, dx, dy, dw, dh) -> None:
        info = self._info
        if info is None:
            return
        try:
            t = str(getattr(info.type, "letter", "?"))
        except Exception:
            t = "?"
        col = {"I": QColor(255, 80, 80), "P": QColor(90, 140, 255),
               "B": QColor(60, 200, 110)}.get(t, QColor(160, 160, 160))
        # I/P/B 不同色小点：按帧 index 确定性散点
        try:
            seed = int(getattr(info, "index", 0))
        except Exception:
            seed = 0
        rng = np.random.default_rng(seed)
        pts = rng.random((60, 2))
        p.setPen(QPen(col, 2))
        for u, v in pts:
            # brain 帧更密由外部 overlay 体现；此处保持稀疏
            x = dx + float(u) * dw
            y = dy + float(v) * dh
            p.drawPoint(int(x), int(y))
        if bool(getattr(info, "brain", False)):
            p.fillRect(int(dx), int(dy), int(dw), int(dh), QColor(255, 40, 40, 26))
            p.setPen(QColor(255, 120, 120))
            p.drawText(int(dx) + 6, int(dy + dh) - 10, "BLOCKY / brain 块噪声可疑帧")

    def _draw_codec_layer(self, p: QPainter, dx, dy, dw, dh) -> None:
        """Codec 层叠加：各家族 overlay 列表 -> widget 坐标。永不抛错。"""
        try:
            kind = str(getattr(self, "codec_kind", "off") or "off")
            data = getattr(self, "codec_data", None)
        except Exception:
            return
        if kind == "off" or not data:
            return
        try:
            src_w = float(self._img_w or 0)
            src_h = float(self._img_h or 0)
        except Exception:
            return
        if src_w <= 0 or src_h <= 0:
            return
        try:
            sx = dw / src_w
            sy = dh / src_h
        except Exception:
            return
        try:
            if kind in ("avc", "h263"):
                # [(x0,y0,x1,y1,style)]
                for e in data[:4000]:
                    try:
                        x0, y0, x1, y1 = float(e[0]), float(e[1]), float(e[2]), float(e[3])
                        st = str(e[4]) if len(e) > 4 else "mb"
                    except Exception:
                        continue
                    if st == "gob":
                        col = QColor(0xF2, 0xA0, 0x33, 220)
                        wid = 2.0
                    elif st in ("p", "b"):
                        col = QColor(0x4C, 0x8B, 0xE8, 120) if st == "p" else QColor(0x35, 0xC7, 0x59, 120)
                        wid = 1.0
                    elif st == "blk":
                        col = QColor(0x8C, 0x93, 0x99, 90)
                        wid = 1.0
                    else:
                        col = QColor(0x5B, 0x9B, 0xFF, 160)
                        wid = 1.0
                    p.setPen(QPen(col, wid))
                    p.drawLine(int(dx + x0 * sx), int(dy + y0 * sy),
                               int(dx + x1 * sx), int(dy + y1 * sy))
                p.setPen(QColor(0xE4, 0xE7, 0xEA))
                p.drawText(int(dx) + 6, int(dy) + 14, f"Codec层:{kind} {len(data)}线")
            elif kind == "hevc":
                # [(x0,y0,size,depth)]
                cols = (QColor(59, 130, 246, 110), QColor(34, 197, 94, 110),
                        QColor(245, 158, 11, 120), QColor(239, 68, 68, 130))
                try:
                    from .codec_hevc import depth_color as _dc  # type: ignore
                except Exception:
                    _dc = None
                for e in data[:3000]:
                    try:
                        x0, y0, sz, dp = float(e[0]), float(e[1]), float(e[2]), int(e[3])
                    except Exception:
                        continue
                    if _dc is not None:
                        try:
                            col = _dc(dp)
                        except Exception:
                            col = cols[max(0, min(3, dp))]
                    else:
                        col = cols[max(0, min(3, dp))]
                    x = dx + x0 * sx
                    y = dy + y0 * sy
                    ww = sz * sx
                    hh = sz * sy
                    p.setPen(QPen(col, 1))
                    p.drawRect(int(x), int(y), max(1, int(ww)), max(1, int(hh)))
                p.setPen(QColor(0xE4, 0xE7, 0xEA))
                p.drawText(int(dx) + 6, int(dy) + 14, f"Codec层:CTU {len(data)}块")
            elif kind == "vpseg":
                # [(x0,y0,x1,y1,seg)]
                segc = {0: QColor(76, 139, 232, 150), 1: QColor(53, 199, 89, 150),
                        2: QColor(232, 192, 80, 150), 3: QColor(242, 43, 43, 150)}
                for e in data[:2000]:
                    try:
                        x0, y0, x1, y1 = float(e[0]), float(e[1]), float(e[2]), float(e[3])
                        sg = int(e[4]) % 4 if len(e) > 4 else 1
                    except Exception:
                        continue
                    p.setPen(QPen(segc.get(sg, QColor(255, 255, 255, 120)), 1))
                    p.drawRect(int(dx + x0 * sx), int(dy + y0 * sy),
                               max(1, int((x1 - x0) * sx)), max(1, int((y1 - y0) * sy)))
                p.setPen(QColor(0xE4, 0xE7, 0xEA))
                p.drawText(int(dx) + 6, int(dy) + 14, f"Codec层:VP分段 {len(data)}块")
            elif kind == "av1sb":
                # [(x0,y0,size)]
                for e in data[:2000]:
                    try:
                        x0, y0, sz = float(e[0]), float(e[1]), float(e[2])
                    except Exception:
                        continue
                    if sz >= 128:
                        col = QColor(0x5B, 0x9B, 0xFF, 200)
                        wid = 2.0
                    elif sz == 64:
                        col = QColor(0x5B, 0x9B, 0xFF, 120)
                        wid = 1.0
                    else:
                        col = QColor(0x35, 0xFF, 0x7A, 110)
                        wid = 1.0
                    p.setPen(QPen(col, wid))
                    p.drawRect(int(dx + x0 * sx), int(dy + y0 * sy),
                               max(1, int(sz * sx)), max(1, int(sz * sy)))
                p.setPen(QColor(0xE4, 0xE7, 0xEA))
                p.drawText(int(dx) + 6, int(dy) + 14, f"Codec层:AV1 SB {len(data)}块")
            elif kind in ("vvc", "avs3"):
                # [(x0,y0,bw,bh,depth)] (vvc mtt / avs3 lcu)
                cols = (QColor(59, 130, 246, 110), QColor(34, 197, 94, 110),
                        QColor(245, 158, 11, 120), QColor(239, 68, 68, 130),
                        QColor(168, 85, 247, 130))
                try:
                    from .codec_next import depth_color as _dc2  # type: ignore
                except Exception:
                    _dc2 = None
                for e in data[:3000]:
                    try:
                        if len(e) >= 5:
                            x0, y0, bw, bh, dp = float(e[0]), float(e[1]), float(e[2]), float(e[3]), int(e[4])
                        else:
                            x0, y0, bw, bh, dp = float(e[0]), float(e[1]), float(e[2]), float(e[2]), int(e[3])
                    except Exception:
                        continue
                    if _dc2 is not None and kind == "vvc":
                        try:
                            col = _dc2(dp)
                        except Exception:
                            col = cols[max(0, min(4, dp))]
                    else:
                        col = cols[max(0, min(4, dp))]
                    p.setPen(QPen(col, 1))
                    p.drawRect(int(dx + x0 * sx), int(dy + y0 * sy),
                               max(1, int(bw * sx)), max(1, int(bh * sy)))
                p.setPen(QColor(0xE4, 0xE7, 0xEA))
                tag = "VVC MTT" if kind == "vvc" else "AVS3 LCU"
                p.drawText(int(dx) + 6, int(dy) + 14, f"Codec层:{tag} {len(data)}块")
            elif kind == "prores":
                # [(x0,y0,x1,y1,kind,index)]: slice 横条 + dct 网格
                for e in data[:3000]:
                    try:
                        x0, y0, x1, y1 = float(e[0]), float(e[1]), float(e[2]), float(e[3])
                        kk = str(e[4]) if len(e) > 4 else "dct"
                    except Exception:
                        continue
                    if kk == "slice":
                        col = QColor(0xE8, 0xC0, 0x50, 200)
                        wid = 2.0
                    else:
                        col = QColor(0x5B, 0x9B, 0xFF, 80)
                        wid = 1.0
                    p.setPen(QPen(col, wid))
                    if kk == "slice":
                        p.drawLine(int(dx + x0 * sx), int(dy + y0 * sy),
                                   int(dx + x1 * sx), int(dy + y0 * sy))
                        p.drawLine(int(dx + x0 * sx), int(dy + y1 * sy),
                                   int(dx + x1 * sx), int(dy + y1 * sy))
                    else:
                        p.drawRect(int(dx + x0 * sx), int(dy + y0 * sy),
                                   max(1, int((x1 - x0) * sx)), max(1, int((y1 - y0) * sy)))
                p.setPen(QColor(0xE4, 0xE7, 0xEA))
                p.drawText(int(dx) + 6, int(dy) + 14, f"Codec层:ProRes slice {len(data)}项")
            elif kind == "theora":
                # [(x,y,size)] 8x8 DCT 点阵
                p.setPen(QPen(QColor(0x35, 0xFF, 0x7A, 160), 1))
                for e in data[:6000]:
                    try:
                        x, y = float(e[0]), float(e[1])
                    except Exception:
                        continue
                    p.drawPoint(int(dx + x * sx), int(dy + y * sy))
                p.setPen(QColor(0xE4, 0xE7, 0xEA))
                p.drawText(int(dx) + 6, int(dy) + 14, f"Codec层:Theora DCT {len(data)}点")
            elif kind == "altref":
                # [(index,kind)] 或 heuristic
                try:
                    n = len(data)
                except Exception:
                    n = 0
                p.setPen(QColor(0xE8, 0xC0, 0x50))
                p.drawText(int(dx) + 6, int(dy) + 14, f"AltRef★ x{n}（周期大P=AltRef，金星标见 CODEC DNA 条）")
        except Exception:
            pass

    def _draw_badge(self, p: QPainter, dx, dy, dw, dh) -> None:
        info = self._info
        if info is None:
            return
        try:
            letter = str(getattr(info.type, "letter", "?"))
        except Exception:
            letter = "?"
        box = {"I": QColor(0xE0, 0x1E, 0x1E), "P": QColor(0x14, 0x4E, 0xC8),
               "B": QColor(0x18, 0x9E, 0x3C)}.get(letter, QColor(0x44, 0x44, 0x44))
        size = max(22.0, dh * 0.13)
        p.fillRect(int(dx + 6), int(dy + dh - size - 6), int(size), int(size), box)
        p.setPen(QColor(0, 0, 0))
        p.drawText(int(dx + 6), int(dy + dh - size - 6), int(size), int(size),
                   Qt.AlignmentFlag.AlignCenter, letter)

    # ------------------------------------------------------------------ input
    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        super().mouseDoubleClickEvent(ev)
