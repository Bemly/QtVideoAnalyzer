"""6-row synchronised graph stack. Qt port of FrameGraph.cs + TimelineStrip.cs (simplified)."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

TITLES = (
    "BITRATE kbps / 帧码率",
    "FRAME TYPE I/P/B",
    "QP avg/MinMax",
    "MOTION mean",
    "GOP position",
    "REORDER pts-dts",
)
ROW_H = 64
AXIS_W = 56

C_I = QColor(0xF2, 0x2B, 0x2B)
C_P = QColor(0x4C, 0x8B, 0xE8)
C_B = QColor(0x35, 0xC7, 0x59)
C_OTHER = QColor(0x88, 0x88, 0x88)


class GraphStack(QWidget):
    """Single widget drawing 6 linked rows sharing one time axis."""

    seek_requested = Signal(float)
    range_selected = Signal(float, float)
    view_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(6 * ROW_H)
        self.setMouseTracking(True)
        self._result = None
        self._playhead: float = 0.0
        self._vs: float = 0.0
        self._ve: float = 1.0
        self._sel_a: float = float("nan")
        self._sel_b: float = float("nan")
        self._anchor: float | None = None
        self._dragging = False

    # ------------------------------------------------------------------ API
    def set_result(self, result) -> None:
        self._result = result
        if result is not None and getattr(result, "frame_count", 0) > 0:
            try:
                dur = float(result.duration_seconds)
                if dur > 0:
                    self._vs, self._ve = 0.0, dur
            except Exception:
                pass
        self.update()

    def set_playhead(self, sec: float) -> None:
        self._playhead = float(sec)
        self.update()

    def set_view(self, start: float, end: float) -> None:
        if end <= start:
            end = start + 1e-3
        self._vs, self._ve = float(start), float(end)
        self.update()

    def set_selected_range(self, a: float, b: float) -> None:
        self._sel_a, self._sel_b = float(a), float(b)
        self.update()

    # ------------------------------------------------------------------ geom
    def _plot_w(self) -> float:
        return max(1.0, float(self.width()) - AXIS_W)

    def _t2x(self, t: float) -> float:
        span = max(1e-9, self._ve - self._vs)
        return (t - self._vs) / span * self._plot_w()

    def _x2t(self, x: float) -> float:
        span = self._ve - self._vs
        return self._vs + x / max(1.0, self._plot_w()) * span

    # ------------------------------------------------------------------ paint
    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0x0B, 0x0E, 0x13))
        H = max(1, self.height())
        rh = H / 6.0
        for row in range(6):
            y0 = row * rh
            self._draw_row(p, row, 0.0, y0, self._plot_w(), rh)
            # axis labels
            p.setPen(QColor(0x8C, 0x93, 0x99))
            p.drawText(int(self._plot_w()) + 4, int(y0 + 14), TITLES[row].split(" ")[0][:8])
            # divider
            p.setPen(QPen(QColor(0x22, 0x26, 0x2C), 1))
            p.drawLine(0, int(y0 + rh) - 1, self.width(), int(y0 + rh) - 1)
            # title
            p.setPen(QColor(0xA8, 0xAE, 0xB4))
            p.drawText(6, int(y0 + 13), TITLES[row])
        # selected range shading
        try:
            if self._sel_b > self._sel_a:
                x0 = max(0.0, self._t2x(self._sel_a))
                x1 = min(self._plot_w(), self._t2x(self._sel_b))
                if x1 > x0:
                    p.fillRect(int(x0), 0, int(x1 - x0), H, QColor(0x5B, 0x9B, 0xFF, 40))
                    p.setPen(QPen(QColor(0x5B, 0x9B, 0xFF), 1))
                    p.drawLine(int(x0), 0, int(x0), H)
                    p.drawLine(int(x1), 0, int(x1), H)
        except Exception:
            pass
        # pinned playhead across all rows
        px = self._t2x(self._playhead)
        if 0 <= px <= self._plot_w():
            p.setPen(QPen(QColor(0xFF, 0xFF, 0xFF), 1))
            p.drawLine(int(px), 0, int(px), H)
        p.end()

    def _frames_in_view(self):
        r = self._result
        if r is None or not getattr(r, "frames", None):
            return []
        return r.frames

    def _draw_row(self, p: QPainter, row: int, x0, y0, plot_w, rh) -> None:
        frames = self._frames_in_view()
        top, bot = y0 + 14, y0 + rh - 4
        if not frames:
            p.setPen(QColor(0x55, 0x5B, 0x60))
            p.drawText(int(x0) + 8, int(y0 + rh / 2), "no data")
            return
        span = max(1e-9, self._ve - self._vs)

        def X(t):
            return x0 + (t - self._vs) / span * plot_w

        if row == 0:
            self._row_bitrate(p, frames, X, top, bot, plot_w)
        elif row == 1:
            self._row_ftype(p, frames, X, top, bot, plot_w)
        elif row == 2:
            self._row_qp(p, frames, X, top, bot, plot_w)
        elif row == 3:
            self._row_motion(p, frames, X, top, bot, plot_w)
        elif row == 4:
            self._row_gop(p, frames, X, top, bot, plot_w)
        else:
            self._row_reorder(p, frames, X, top, bot, plot_w, y0, rh)

    # ------------------------------------------------------------- row kinds
    def _row_bitrate(self, p, frames, X, top, bot, plot_w):
        r = self._result
        mx = max(1.0, float(getattr(r, "max_bitrate", 1.0) or 1.0))
        log_max = math.log2(mx + 1)
        avg = float(getattr(r, "avg_bitrate", 0.0) or 0.0)
        y_avg = bot - (math.log2(avg + 1) / log_max) * (bot - top)
        for idx, f in enumerate(frames):
            x = X(f.pts_time)
            if x < -20 or x > plot_w + 20:
                continue
            bw = 3.0
            try:
                if idx < len(frames) - 1:
                    bw = max(1.0, X(frames[idx + 1].pts_time) - x - 0.4)
            except Exception:
                bw = 3.0
            norm = math.log2(max(0.0, float(f.bitrate_kbps or 0.0)) + 1) / log_max
            bh = norm * (bot - top)
            brush = QColor(0xE8, 0xEC, 0xF0) if f.key_frame else QColor(0x55, 0x5B, 0x60)
            p.fillRect(int(x), int(bot - bh), max(1, int(bw)), int(bh), brush)
        p.setPen(QPen(QColor(0xD8, 0xD8, 0xD8), 1, Qt.PenStyle.DashLine))
        p.drawLine(0, int(y_avg), int(plot_w), int(y_avg))

    def _row_ftype(self, p, frames, X, top, bot, plot_w):
        lane = (bot - top) / 3.0
        for f in frames:
            x = X(f.pts_time)
            if x < -20 or x > plot_w + 20:
                continue
            t = str(getattr(f.type, "letter", "?"))
            if t == "I":
                y, c = top, C_I
            elif t == "P":
                y, c = top + lane, C_P
            elif t == "B":
                y, c = top + lane * 2, C_B
            else:
                y, c = top + lane * 2, C_OTHER
            p.fillRect(int(x), int(y), 3, int(lane - 1), c)
            if f.key_frame:
                p.fillRect(int(x), int(top - 2), 1, int(bot - top + 4), QColor(0xEC, 0xEC, 0xEC))

    def _row_qp(self, p, frames, X, top, bot, plot_w):
        r = self._result
        mx = max(1.0, float(getattr(r, "max_qp", 51.0) or 51.0))
        # min-max band polygon
        pts_top, pts_bot = [], []
        for f in frames:
            x = X(f.pts_time)
            if x < -30 or x > plot_w + 30:
                continue
            qmax = f.qp_max if f.qp_max is not None else (f.qp_avg or 0)
            qmin = f.qp_min if f.qp_min is not None else (f.qp_avg or 0)
            pts_top.append((x, bot - float(qmax) / mx * (bot - top)))
            pts_bot.append((x, bot - float(qmin) / mx * (bot - top)))
        if pts_top:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0x7A, 0x74, 0x10, 128))
            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            poly = QPolygonF([QPointF(x, y) for x, y in pts_top] +
                             [QPointF(x, y) for x, y in reversed(pts_bot)])
            p.drawPolygon(poly)
        est = bool(getattr(r, "qp_estimated", False))
        pen = QPen(QColor(0xD9, 0xD2, 0x3A), 1,
                   Qt.PenStyle.DashLine if est else Qt.PenStyle.SolidLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        prev = None
        for f in frames:
            if f.qp_avg is None:
                prev = None
                continue
            x = X(f.pts_time)
            y = bot - float(f.qp_avg) / mx * (bot - top)
            if prev is not None and -30 <= x <= plot_w + 30:
                p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
            prev = (x, y)
        if est:
            p.setPen(QColor(0xE8, 0xC0, 0x50))
            p.drawText(6, int(bot - 4), "qp est. 虚线=估计")

    def _row_motion(self, p, frames, X, top, bot, plot_w):
        r = self._result
        mx = max(1.0, float(getattr(r, "max_motion", 1.0) or 1.0))
        for f in frames:
            x = X(f.pts_time)
            if x < -20 or x > plot_w + 20:
                continue
            v = float(f.motion_mean or 0.0)
            if v <= 0:
                continue
            y = bot - min(1.0, v / mx) * (bot - top)
            fw = int(getattr(f, "motion_fwd", 0) or 0)
            bw = int(getattr(f, "motion_bwd", 0) or 0)
            if fw >= bw and fw > 0:
                c = QColor(0x35, 0xFF, 0x7A)   # fwd 绿
            elif bw > fw:
                c = QColor(0xFF, 0x5C, 0xE0)   # bwd 品红
            else:
                c = QColor(0xE0, 0xB4, 0x24)   # amber
            p.fillRect(int(x), int(y), 3, int(bot - y), c)

    def _row_gop(self, p, frames, X, top, bot, plot_w):
        r = self._result
        mx = max(1, int(getattr(r, "max_gop", 1) or 1))
        for f in frames:
            x = X(f.pts_time)
            if x < -20 or x > plot_w + 20:
                continue
            g = int(getattr(f, "gop_position", 0) or 0)
            if g == 0:
                continue
            y = bot - g / float(mx) * (bot - top)
            p.fillRect(int(x), int(y), 3, int(bot - y), QColor(0x25, 0xC7, 0xC7))

    def _row_reorder(self, p, frames, X, top, bot, plot_w, y0, rh):
        r = self._result
        mx = max(1, int(getattr(r, "max_reorder", 1) or 1))
        mn = min(0, int(getattr(r, "min_reorder", 0) or 0))
        span = max(1, mx - mn)
        mid = bot - (0 - mn) / float(span) * (bot - top)
        p.setPen(QPen(QColor(0x55, 0x5B, 0x60), 1))
        p.drawLine(0, int(mid), int(plot_w), int(mid))
        for f in frames:
            x = X(f.pts_time)
            if x < -20 or x > plot_w + 20:
                continue
            d = int(getattr(f, "reorder_delta", 0) or 0)
            y = bot - (d - mn) / float(span) * (bot - top)
            y1, y2 = (y, mid) if y < mid else (mid, y)
            if abs(y2 - y1) < 1:
                y2 = y1 + 2
            p.fillRect(int(x), int(y1), 3, int(y2 - y1), QColor(0xE8, 0x7A, 0x1E))
            # 基线符号：corrupt/discard/interlace/repeat/brain
            sy = int(mid) + 2
            if f.corrupt:
                p.fillRect(int(x), sy, 4, 3, C_I)
            elif f.discard:
                p.fillRect(int(x), sy, 4, 3, QColor(0xE8, 0x7A, 0x1E))
            elif getattr(f, "interlaced", False):
                p.fillRect(int(x), sy, 3, 3, QColor(0x25, 0xC7, 0xC7))
            elif getattr(f, "repeat_pict", False):
                p.fillRect(int(x), sy, 3, 3, QColor(0xE8, 0xC0, 0x50))
            if getattr(f, "brain", False):
                p.fillRect(int(x), sy + 4, 4, 2, QColor(0xD9, 0xD2, 0x3A))

    # ------------------------------------------------------------------ input
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.seek_requested.emit(max(self._vs, min(self._ve, self._x2t(ev.position().x()))))
        elif ev.button() == Qt.MouseButton.RightButton:
            t = max(self._vs, min(self._ve, self._x2t(ev.position().x())))
            if self._anchor is None:
                self._anchor = t
            else:
                a, b = (self._anchor, t) if self._anchor <= t else (t, self._anchor)
                self._anchor = None
                self.set_selected_range(a, b)
                self.range_selected.emit(a, b)
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._dragging and (ev.buttons() & Qt.MouseButton.LeftButton):
            self.seek_requested.emit(max(self._vs, min(self._ve, self._x2t(ev.position().x()))))
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.seek_requested.emit(max(self._vs, min(self._ve, self._x2t(ev.position().x()))))
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        # 右键双击标 range：以 playhead 为一端、点击处为另一端
        if ev.button() == Qt.MouseButton.RightButton:
            t = max(self._vs, min(self._ve, self._x2t(ev.position().x())))
            a, b = (self._playhead, t) if self._playhead <= t else (t, self._playhead)
            self.set_selected_range(a, b)
            self.range_selected.emit(a, b)
        super().mouseDoubleClickEvent(ev)

    def wheelEvent(self, ev) -> None:  # noqa: N802
        factor = 0.8 if ev.angleDelta().y() > 0 else 1.25
        anchor = self._x2t(ev.position().x())
        span = max(1e-6, self._ve - self._vs)
        total = span
        try:
            if self._result is not None and getattr(self._result, "frame_count", 0) > 0:
                total = max(span, float(self._result.duration_seconds))
        except Exception:
            pass
        new_span = min(max(span * factor, 0.05), max(total, 0.25))
        rel = (anchor - self._vs) / span if span > 0 else 0.5
        rel = max(0.0, min(1.0, rel))
        ns = anchor - rel * new_span
        self.set_view(ns, ns + new_span)
        self.view_changed.emit(self._vs, self._ve)
        ev.accept()
