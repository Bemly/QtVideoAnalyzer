"""CodecDNA 面板：家族徽章 + 3 bullet + mini GOP 条 + 去哪看。只 PySide6+numpy。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class GopMiniBar(QWidget):
    """mini GOP 条：I红高块/P蓝中/B绿矮/altref 金星标，高 48。永不抛错。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setMinimumWidth(120)
        self._letters: list[str] = []
        self._altref: set[int] = set()

    def set_frames(self, letters, altref: set[int] | list[int] | None = None) -> None:
        try:
            self._letters = [str(x) for x in (letters or [])][:128]
        except Exception:
            self._letters = []
        try:
            self._altref = set(int(i) for i in (altref or []))
        except Exception:
            self._altref = set()
        self.update()

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor(0x10, 0x14, 0x1A))
            n = len(self._letters)
            if not n:
                p.setPen(QColor(0x5A, 0x60, 0x66))
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "no GOP")
                return
            W, H = float(self.width()), float(self.height())
            bw = max(2.0, W / max(1, n))
            for i, t in enumerate(self._letters):
                x = i * bw
                w = max(1, int(bw - 1))
                if t == "I":
                    c = QColor(0xF2, 0x2B, 0x2B)
                    h = H - 8
                elif t == "P":
                    c = QColor(0x4C, 0x8B, 0xE8)
                    h = (H - 8) * 0.55
                elif t == "B":
                    c = QColor(0x35, 0xC7, 0x59)
                    h = (H - 8) * 0.32
                else:
                    c = QColor(0x88, 0x88, 0x88)
                    h = (H - 8) * 0.32
                y = H - 4 - h
                p.fillRect(int(x), int(y), w, int(h), c)
                if i in self._altref:
                    p.setPen(QColor(0xE8, 0xC0, 0x50))
                    p.drawText(int(x), 12, "★")
            p.setPen(QPen(QColor(0x22, 0x26, 0x2C), 1))
            p.drawRect(0, 0, int(W) - 1, int(H) - 1)
        except Exception:
            pass
        finally:
            try:
                p.end()
            except Exception:
                pass


class CodecPanel(QWidget):
    """右侧 CODEC DNA 面板。set_result(result) 永不抛错。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.badge = QLabel("—", self)
        try:
            f = self.badge.font()
            f.setPointSize(18)
            f.setBold(True)
            self.badge.setFont(f)
        except Exception:
            pass
        self.meta = QLabel("-", self)
        self.meta.setWordWrap(True)
        self.b1 = QLabel("-", self)
        self.b2 = QLabel("-", self)
        self.b3 = QLabel("-", self)
        for b in (self.b1, self.b2, self.b3):
            b.setWordWrap(True)
        self.bar = GopMiniBar(self)
        self.where = QLabel("-", self)
        self.where.setWordWrap(True)
        self.where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.badge)
        lay.addWidget(self.meta)
        lay.addWidget(self.b1)
        lay.addWidget(self.b2)
        lay.addWidget(self.b3)
        lay.addWidget(self.bar)
        lay.addWidget(self.where)

    def set_result(self, result) -> None:
        try:
            from .codec_insight import codec_key, describe, summarize, where_to_look
        except Exception:
            return
        try:
            s = summarize(result)
        except Exception:
            return
        try:
            fam = str(s.get("family", "UNKNOWN"))
            codec = str(s.get("codec", "unknown"))
            self.badge.setText(fam)
            # 徽章色：AVC红/HEVC蓝/VP绿/AV1紫，其余灰
            col = {"AVC": "#F22B2B", "HEVC": "#4C8BE8", "VP6": "#35C759",
                   "VP8": "#35C759", "VP9": "#35C759", "AV1": "#B46BE8"}.get(fam, "#E4E7EA")
            try:
                self.badge.setStyleSheet(f"color: {col};")
            except Exception:
                pass
            bframes = "B✓" if s.get("bframes") else "B✗"
            try:
                ki = float(s.get("key_interval", 0) or 0)
                ag = float(s.get("avg_gop", 0) or 0)
            except Exception:
                ki = ag = 0.0
            self.meta.setText(
                f"{codec} · I={s.get('i',0)} P={s.get('p',0)} B={s.get('b',0)} {bframes} "
                f"· key~{ki:.0f} avgGOP~{ag:.0f} · AltRef≈{s.get('altref_count',0)} "
                f"· {s.get('ctu_or_sb','-')} · {s.get('entropy_hint','?')} "
                f"· QP原生={'是' if s.get('qp_native') else '否'}")
        except Exception:
            pass
        try:
            bullets = describe(str(s.get("codec", "")), s)
            if not bullets:
                bullets = []
            txts = list(bullets)[:3] + ["-"] * 3
            self.b1.setText("• " + str(txts[0]))
            self.b2.setText("• " + str(txts[1]))
            self.b3.setText("• " + str(txts[2]))
        except Exception:
            pass
        try:
            self.where.setText(where_to_look(str(s.get("codec", ""))))
        except Exception:
            pass
        # mini GOP 条：前 64 帧字母 + altref 大P标星
        try:
            frames = list(getattr(result, "frames", None) or [])[:64]
            letters = []
            for f in frames:
                try:
                    letters.append(str(getattr(getattr(f, "type", None), "letter", "?")))
                except Exception:
                    letters.append("?")
            # altref 候选：P 中偏大者标星（与 summarize 同阈值）
            alt = set()
            try:
                p_sizes = sorted(int(getattr(f, "packet_size", 0) or 0) for f in frames
                                 if str(getattr(getattr(f, "type", None), "letter", "?")) == "P")
                if p_sizes:
                    mid = p_sizes[len(p_sizes) // 2]
                    if mid > 0:
                        thr = mid * 1.5
                        for i, f in enumerate(frames):
                            try:
                                if (str(getattr(getattr(f, "type", None), "letter", "?")) == "P"
                                        and int(getattr(f, "packet_size", 0) or 0) >= thr):
                                    alt.add(i)
                            except Exception:
                                continue
            except Exception:
                alt = set()
            self.bar.set_frames(letters, alt)
        except Exception:
            try:
                self.bar.set_frames([], set())
            except Exception:
                pass
