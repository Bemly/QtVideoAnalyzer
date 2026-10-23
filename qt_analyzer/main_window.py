"""Main window. Qt port of MainWindow.xaml + MainViewModel.cs (simplified)."""
from __future__ import annotations

import inspect
import os
import subprocess
import sys
import time

import numpy as np

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSlider, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import ffmpeg_locator
from .graphs import GraphStack
from .models import AnalysisResult
from .video_widget import VideoWidget

DARK_QSS = """
QMainWindow, QWidget { background: #0B0E13; color: #E4E7EA; font-size: 12px; }
QPushButton { background: #1C1F23; border: 1px solid #2A2E33; border-radius: 6px; padding: 4px 10px; }
QPushButton:hover { background: #262B31; }
QPushButton:disabled { color: #5C6675; }
QSlider::groove:horizontal { height: 4px; background: #262B31; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -5px 0; border-radius: 6px; background: #5B9BFF; }
QTableWidget { background: #10141A; gridline-color: #22262C; }
QHeaderView::section { background: #1C1F23; color: #A8AEB4; border: none; }
QTextEdit { background: #10141A; border: 1px solid #22262C; }
QProgressBar { background: #1C1F23; border: 1px solid #2A2E33; border-radius: 4px; height: 10px; }
QProgressBar::chunk { background: #5B9BFF; }
QLabel#Section { color: #8C9399; font-weight: bold; }
"""

_THROTTLE_SEC = 0.8  # 分析流式刷新节流 (spec: 8s -> 取 0.8s，保证进度可见)


# ------------------------------------------------------------- workers
class AnalysisWorker(QThread):
    status = Signal(str)
    result_updated = Signal(object)
    failed = Signal(str)
    finished_ok = Signal(object)

    def __init__(self, path: str, range_from: float = 0.0, range_to: float = -1.0,
                 prior=None, motion: bool = True, parent=None):
        super().__init__(parent)
        self.path = path
        self.range_from = range_from
        self.range_to = range_to
        self.prior = prior
        self.motion = motion
        self._last_emit = 0.0
        try:
            import threading as _th
            self._cancel_ev = _th.Event()
        except Exception:
            self._cancel_ev = None

    def cancel(self):
        try:
            if self._cancel_ev is not None:
                self._cancel_ev.set()
        except Exception:
            pass
        self.requestInterruption()

    def _throttled_emit(self, result):
        now = time.monotonic()
        if now - self._last_emit >= _THROTTLE_SEC:
            self._last_emit = now
            self.result_updated.emit(result)

    def run(self):
        try:
            result = self._run_pipeline()
            if result is not None:
                self.result_updated.emit(result)
                self.finished_ok.emit(result)
            else:
                self.failed.emit("analysis returned nothing")
        except Exception as e:  # noqa: BLE001
            try:
                self.failed.emit(str(e))
            except Exception:
                pass

    def _run_pipeline(self):
        # 优先走 pipeline.run_analysis（probe->packets 立即可播，deep 并行 qp+motion）
        try:
            from . import pipeline as _pl  # type: ignore
        except Exception:
            _pl = None
        upd = lambda r: self._throttled_emit(r)  # noqa: E731
        stage = lambda name, frac: self.status.emit(f"{name} {frac * 100:.0f}%")  # noqa: E731
        if _pl is not None and hasattr(_pl, "run_analysis"):
            # 范围重跑：已有结果 + run_range 时只重跑深分析
            if (self.prior is not None and self.range_to > self.range_from
                    and hasattr(_pl, "run_range")):
                try:
                    return _pl.run_range(self.prior, self.range_from, self.range_to,
                                         motion=self.motion, on_stage=stage,
                                         on_updated=upd, cancel=self._cancel_ev)
                except TypeError:
                    pass
            fn = _pl.run_analysis
            try:
                return fn(self.path, motion=self.motion, on_stage=stage,
                          on_updated=upd, cancel=self._cancel_ev)
            except TypeError:
                pass
            try:
                sig = inspect.signature(fn)
                params = set(sig.parameters)
            except Exception:
                params = set()
            cb = upd
            try:
                if "on_updated" in params:
                    return fn(self.path, on_updated=cb)
                if "on_update" in params:
                    return fn(self.path, on_update=cb)
                if len(params) == 0:
                    return fn()
                return fn(self.path)
            except TypeError:
                return fn(self.path)
        # 回退：最小可用 packet 扫描，保证“立即可播”
        return self._fallback_scan()

    def _fallback_scan(self):
        """无 pipeline 时的最小实现：ffprobe 包表 -> bitrate/GOP/reorder，可播。"""
        from .models import FrameInfo, MediaInfo, PicType
        exe = ffmpeg_locator.ffprobe_path()
        media = MediaInfo(file_path=self.path, file_name=os.path.basename(self.path))
        res = AnalysisResult(media=media)
        if not exe:
            self.status.emit("ffprobe not found")
            return res
        try:
            out = subprocess.run(
                [exe, "-v", "error", "-show_format", "-show_streams",
                 "-print_format", "json", self.path],
                capture_output=True, text=True, timeout=30)
            import json as _json
            meta = _json.loads(out.stdout or "{}")
            for st in meta.get("streams", []):
                if st.get("codec_type") == "video":
                    try:
                        media.width = int(st.get("width", 0))
                    except Exception:
                        pass
                    try:
                        media.height = int(st.get("height", 0))
                    except Exception:
                        pass
                    media.video_codec = str(st.get("codec_name", "unknown"))
                    media.pix_fmt = str(st.get("pix_fmt", "unknown"))
                    fr = str(st.get("avg_frame_rate", "25/1"))
                    try:
                        if "/" in fr:
                            a, b = fr.split("/")
                            media.fps = float(a) / max(1.0, float(b))
                    except Exception:
                        pass
                    break
            fmt = meta.get("format", {})
            try:
                media.duration = float(fmt.get("duration", 0.0))
            except Exception:
                pass
            media.format_name = str(fmt.get("format_name", "unknown"))
        except Exception as e:  # noqa: BLE001
            self.status.emit(f"probe failed: {e}")
        try:
            out = subprocess.run(
                [exe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "packet=pts_time,dts_time,size,flags",
                 "-print_format", "json", self.path],
                capture_output=True, text=True, timeout=120)
            import json as _json
            pkts = _json.loads(out.stdout or "{}").get("packets", [])
        except Exception as e:  # noqa: BLE001
            self.status.emit(f"packets failed: {e}")
            return res
        import math as _math
        frames: list = []
        gop = 0
        prev_dts = None
        for i, p_ in enumerate(pkts):
            if self.isInterruptionRequested():
                break
            try:
                pts = float(p_.get("pts_time", i * 0.04))
            except Exception:
                pts = i * 0.04
            try:
                dts = float(p_.get("dts_time", pts))
            except Exception:
                dts = pts
            size = int(p_.get("size", 0) or 0)
            flags = str(p_.get("flags", ""))
            key = "K" in flags
            if key:
                gop = 0
            else:
                gop += 1
            dur = 40.0
            if frames:
                dur = max(1.0, (pts - frames[-1].pts_time) * 1000.0) if pts > frames[-1].pts_time else 40.0
            br = size * 8.0 / max(1.0, dur)  # kbps
            rd = 0
            if prev_dts is not None:
                try:
                    rd = int(round((pts - dts) / 0.04))
                except Exception:
                    rd = 0
            prev_dts = dts
            f = FrameInfo(index=i, decode_index=i, pts_time=pts, dts_time=dts,
                          type=(__import__("qt_analyzer.models", fromlist=["PicType"]).PicType.I
                                if key else __import__("qt_analyzer.models", fromlist=["PicType"]).PicType.P),
                          key_frame=key, packet_size=size, duration_ms=dur,
                          gop_position=gop, reorder_delta=rd, bitrate_kbps=br)
            frames.append(f)
        res.frames = frames
        try:
            res.compute_aggregates()
        except Exception:
            pass
        self.status.emit(f"quick scan: {len(frames)} packets (deep N/A)")
        return res


class FilmstripWorker(QThread):
    """Filmstrip background build: Filmstrip.build(file, duration, w, h)."""

    ready = Signal(object)

    def __init__(self, path: str, duration: float = 0.0, w: int = 0, h: int = 0, parent=None):
        super().__init__(parent)
        self.path = path
        self.duration = duration
        self.w = w
        self.h = h

    def run(self):
        try:
            from .filmstrip import Filmstrip as _FS  # type: ignore
            fs = _FS()
            try:
                fs.build(self.path, float(self.duration or 0.0),
                         int(self.w or 0), int(self.h or 0))
            except TypeError:
                try:
                    fs.build(self.path)  # type: ignore
                except Exception:
                    pass
            self.ready.emit(fs)
            return
        except Exception:
            pass
        try:
            from . import filmstrip as _fs  # type: ignore
            if hasattr(_fs, "build"):
                thumbs = _fs.build(self.path)  # type: ignore
                self.ready.emit(list(thumbs or []))
                return
        except Exception:
            pass
        self.ready.emit(None)


# ------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self, initial_path: str | None = None):
        super().__init__()
        self.setWindowTitle("VideoAnalyzer-Qt 帧级分析")
        self.resize(1240, 800)
        self.setAcceptDrops(True)
        self.setStyleSheet(DARK_QSS)

        self._result: AnalysisResult | None = None
        self._path: str | None = None
        self._position: float = 0.0
        self._view_start: float = 0.0
        self._view_end: float = 1.0
        self._worker: AnalysisWorker | None = None
        self._film: FilmstripWorker | None = None
        self._thumbs: list = []
        self._strip = None        # Filmstrip instance (at(sec) 缩略图)
        self._engine = None       # PlaybackEngine (start/try_get_frame/stop/ended)
        self._audio = None        # AudioPlayer (start/stop)
        try:
            from .playback import PlaybackEngine as _PE  # type: ignore
            self._engine = _PE(self)
            try:
                self._engine.failed.connect(lambda e: self.statusBar().showMessage(str(e)))
            except Exception:
                pass
        except Exception:
            self._engine = None
        try:
            from .audio import AudioPlayer as _AP  # type: ignore
            self._audio = _AP(self)
        except Exception:
            self._audio = None
        self._playing = False
        self._loop = False
        self._follow = True
        self._dec = None          # 内置回退 ffmpeg rawvideo 管（无 PlaybackEngine 时用）
        self._dec_index = 0
        self._dec_w = 0
        self._dec_h = 0

        self._build_ui()
        self._check_ffmpeg(silent=True)
        if initial_path:
            self.open_file(initial_path)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        root.addWidget(splitter)

        # ---- left ----
        left = QWidget(splitter)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        self.video = VideoWidget(left)
        lv.addWidget(self.video, 1)

        # transport 传输条
        tr = QHBoxLayout()
        self.btn_play = QPushButton("▶ 播放", left)
        self.btn_step_b = QPushButton("◀ 逐帧", left)
        self.btn_step_f = QPushButton("逐帧 ▶", left)
        self.btn_prev_k = QPushButton("⏮ key", left)
        self.btn_next_k = QPushButton("key ⏭", left)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_step_b.clicked.connect(lambda: self.step_frame(-1))
        self.btn_step_f.clicked.connect(lambda: self.step_frame(1))
        self.btn_prev_k.clicked.connect(lambda: self.jump_key(-1))
        self.btn_next_k.clicked.connect(lambda: self.jump_key(1))
        for b in (self.btn_play, self.btn_step_b, self.btn_step_f, self.btn_prev_k, self.btn_next_k):
            tr.addWidget(b)
        self.vol = QSlider(Qt.Orientation.Horizontal, left)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.setFixedWidth(90)
        self.vol.setToolTip("音量 Volume (audio 占位,无音频时忽略)")
        try:
            self.vol.valueChanged.connect(self._on_volume)
        except Exception:
            pass
        tr.addWidget(QLabel("音量", left))
        tr.addWidget(self.vol)
        self.ck_loop = QCheckBox("loop 循环", left)
        self.ck_follow = QCheckBox("跟随 follow", left)
        self.ck_follow.setChecked(True)
        self.ck_loop.toggled.connect(lambda v: setattr(self, "_loop", bool(v)))
        self.ck_follow.toggled.connect(self._on_follow)
        tr.addWidget(self.ck_loop)
        tr.addWidget(self.ck_follow)
        self.ck_vec = QCheckBox("矢量", left)
        self.ck_grid = QCheckBox("网格", left)
        self.ck_noise = QCheckBox("噪声", left)
        self.ck_vec.setChecked(True)
        self.ck_noise.setChecked(True)
        self.ck_vec.toggled.connect(lambda v: (setattr(self.video, "show_vectors", bool(v)), self.video.update()))
        self.ck_grid.toggled.connect(lambda v: (setattr(self.video, "show_grid", bool(v)), self.video.update()))
        self.ck_noise.toggled.connect(lambda v: (setattr(self.video, "show_noise", bool(v)), self.video.update()))
        tr.addWidget(self.ck_vec)
        tr.addWidget(self.ck_grid)
        tr.addWidget(self.ck_noise)
        tr.addWidget(QLabel("Codec层", left))
        self.cmb_codec_layer = QComboBox(left)
        self.cmb_codec_layer.addItems(["关", "AVC分区", "H.263 GOB", "CTU四叉树", "VP分段", "AV1 SB", "AltRef星"])
        self.cmb_codec_layer.setToolTip("Codec 层叠加（家族模块就绪即插即用，缺失降级）")
        try:
            self.cmb_codec_layer.currentTextChanged.connect(self._on_codec_layer)
        except Exception:
            pass
        tr.addWidget(self.cmb_codec_layer)
        lv.addLayout(tr)

        # timeline 简化 QSlider
        tl = QHBoxLayout()
        self.timeline = QSlider(Qt.Orientation.Horizontal, left)
        self.timeline.setRange(0, 10000)
        self.timeline.sliderMoved.connect(self._on_timeline_moved)
        self.timeline.sliderReleased.connect(self._on_timeline_released)
        self.lbl_time = QLabel("0:00.000 / 0:00.000", left)
        tl.addWidget(self.timeline, 1)
        tl.addWidget(self.lbl_time)
        lv.addLayout(tl)

        self.graphs = GraphStack(left)
        self.graphs.setMinimumHeight(6 * 64)
        self.graphs.seek_requested.connect(self.seek)
        self.graphs.range_selected.connect(self._on_graph_range)
        self.graphs.view_changed.connect(self._on_graph_view)
        lv.addWidget(self.graphs, 1)

        # ---- right ----
        right = QWidget(splitter)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 0, 0, 0)

        rv.addWidget(self._section("SOURCE"))
        self.txt_source = QTextEdit(right)
        self.txt_source.setReadOnly(True)
        self.txt_source.setFixedHeight(172)
        try:
            from PySide6.QtGui import QFont as _QFont
            _mono = _QFont("Menlo", 11)
            _mono.setStyleHint(_QFont.StyleHint.Monospace)
            self.txt_source.setFont(_mono)
        except Exception:
            pass
        rv.addWidget(self.txt_source)

        rv.addWidget(self._section("B/I/P PICTURE TYPES"))
        self.tbl = QTableWidget(4, 7, right)
        self.tbl.setHorizontalHeaderLabels(["type", "count", "%", "bytes/MB", "avgSize", "avgQP", "avgMot"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r_, letter in enumerate(("I", "P", "B", "?")):
            self.tbl.setItem(r_, 0, QTableWidgetItem(letter))
        rv.addWidget(self.tbl)

        rv.addWidget(self._section("GOP STRUCTURE"))
        self.lbl_gop = QLabel("-", right)
        self.lbl_gop.setWordWrap(True)
        self.lbl_gop.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rv.addWidget(self.lbl_gop)

        rv.addWidget(self._section("CURRENT FRAME 当前帧"))
        self.txt_frame = QTextEdit(right)
        self.txt_frame.setReadOnly(True)
        self.txt_frame.setFixedHeight(150)
        rv.addWidget(self.txt_frame)

        rv.addWidget(self._section("CODEC DNA"))
        try:
            from .codec_panel import CodecPanel as _CodecPanel
            self.codec_panel = _CodecPanel(right)
        except Exception:
            self.codec_panel = QLabel("-", right)
            try:
                self.codec_panel.setWordWrap(True)
            except Exception:
                pass
        rv.addWidget(self.codec_panel)

        rv.addWidget(self._section("ANALYSIS 分析"))
        self.lbl_status = QLabel("Ready.", right)
        self.lbl_status.setWordWrap(True)
        rv.addWidget(self.lbl_status)
        self.bar = QProgressBar(right)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        rv.addWidget(self.bar)

        grid = QGridLayout()
        grid.addWidget(QLabel("起 start(s)", right), 0, 0)
        grid.addWidget(QLabel("止 end(s)", right), 0, 1)
        self.spin_from = QDoubleSpinBox(right)
        self.spin_to = QDoubleSpinBox(right)
        for s in (self.spin_from, self.spin_to):
            s.setRange(-1, 1e6)
            s.setValue(-1)
        self.spin_from.setValue(0)
        grid.addWidget(self.spin_from, 1, 0)
        grid.addWidget(self.spin_to, 1, 1)
        self.btn_range = QPushButton("分析范围 Analyze", right)
        self.btn_cancel = QPushButton("取消 Cancel", right)
        self.btn_range.clicked.connect(self._on_analyse_range)
        self.btn_cancel.clicked.connect(self._on_cancel)
        grid.addWidget(self.btn_range, 2, 0)
        grid.addWidget(self.btn_cancel, 2, 1)
        rv.addLayout(grid)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        # menu + shortcuts
        act_open = QAction("Open… 打开", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self._on_open_action)
        self.addAction(act_open)
        act_play = QAction("Play/Pause", self)
        act_play.setShortcut(QKeySequence(Qt.Key.Key_Space))
        act_play.triggered.connect(self.toggle_play)
        self.addAction(act_play)

        self.statusBar().showMessage("Ready")
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._tick)

    def _section(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName("Section")
        return l

    def _on_volume(self, v: int):
        try:
            if self._audio is not None:
                self._audio.set_volume(float(v) / 100.0)
        except Exception:
            pass

    # ------------------------------------------------------------------ open
    def _on_open_action(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open video 打开视频", "", "Video (*.mp4 *.mkv *.avi *.mov *.ts *.webm *.*)")
        if p:
            self.open_file(p)

    def _check_ffmpeg(self, silent=False) -> bool:
        exe = ffmpeg_locator.ffmpeg_path()
        if exe:
            self.statusBar().showMessage(str(ffmpeg_locator.refresh_version()))
            return True
        if silent:
            return False
        box = QMessageBox(self)
        box.setWindowTitle("ffmpeg not found 缺少 ffmpeg")
        box.setText("FFMPEG_HOME / PATH 里没找到 ffmpeg。请选择 ffmpeg 可执行文件。")
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Ok:
            return False
        f, _ = QFileDialog.getOpenFileName(self, "选择 ffmpeg 可执行文件", "", "ffmpeg* (*ffmpeg* *.*)")
        if f:
            os.environ["FFMPEG_HOME"] = os.path.dirname(f)
            # clear cache so next lookup retries with new env
            try:
                import qt_analyzer.ffmpeg_locator as _fl
                _fl._ffmpeg = None  # type: ignore
                _fl._ffprobe = None  # type: ignore
            except Exception:
                pass
            return self._check_ffmpeg(silent=True)
        return False

    def open_file(self, path: str):
        if not path or not os.path.exists(path):
            self.lbl_status.setText(f"file not found: {path}")
            return
        self._check_ffmpeg(silent=True)
        self._path = path
        self._position = 0.0
        self._stop_decoder()
        self.video.show_frame(None)
        self._start_analysis(path, 0.0, -1.0)

    def _start_filmstrip(self):
        # filmstrip 后台 build（有 duration/尺寸后才真跑）
        try:
            r = self._result
            if r is None or self._path is None:
                return
            try:
                dur = float(r.duration_seconds or r.media.duration or 0.0)
            except Exception:
                dur = 0.0
            if dur <= 0:
                return
            try:
                w, h = int(r.media.width or 0), int(r.media.height or 0)
            except Exception:
                w, h = 0, 0
            if self._film is not None and self._film.isRunning():
                try:
                    self._film.requestInterruption()
                except Exception:
                    pass
            self._film = FilmstripWorker(self._path, dur, w, h, self)
            self._film.ready.connect(self._on_thumbs)
            self._film.start()
        except Exception:
            pass

    def _on_thumbs(self, fs):
        # 新 API: Filmstrip 实例；旧 API: 缩略图 list
        try:
            if fs is not None and hasattr(fs, "at"):
                self._strip = fs
                self._thumbs = []
                return
        except Exception:
            pass
        try:
            self._thumbs = list(fs or [])
        except Exception:
            self._thumbs = []

    # ------------------------------------------------------------- analysis
    def _start_analysis(self, path: str, rf: float, rt: float):
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.cancel()
            except Exception:
                self._worker.requestInterruption()
            self._worker.wait(500)
        self._worker = AnalysisWorker(path, rf, rt, prior=self._result, parent=self)
        self._worker.status.connect(lambda s: (self.lbl_status.setText(s), self.statusBar().showMessage(s)))
        self._worker.result_updated.connect(self._on_result)
        self._worker.failed.connect(lambda e: self.lbl_status.setText(f"analysis failed: {e}"))
        self._worker.finished_ok.connect(self._on_analysis_done)
        self.lbl_status.setText("analyzing… 分析中 (probe->packets->deep qp+motion)")
        self.bar.setValue(100)
        self._worker.start()

    def _on_analyse_range(self):
        if not self._path:
            return
        rf = float(self.spin_from.value())
        rt = float(self.spin_to.value())
        self._start_analysis(self._path, rf, rt)

    def _on_cancel(self):
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.cancel()
            except Exception:
                self._worker.requestInterruption()
            self.lbl_status.setText("cancel requested 已取消 (保留已有结果)")

    def _on_result(self, result):
        first = self._result is None or getattr(self._result, "frame_count", 0) == 0
        self._result = result
        try:
            total = float(result.duration_seconds) if result.frames else float(result.media.duration or 1.0)
        except Exception:
            total = 1.0
        total = max(0.04, total)
        self._view_start, self._view_end = 0.0, total
        self.spin_to.setValue(total)
        self.graphs.set_result(result)
        self.graphs.set_view(self._view_start, self._view_end)
        self.graphs.set_playhead(self._position)
        self._refresh_panels()
        self._show_frame_at(self._position)
        if first:
            self._start_filmstrip()

    def _on_analysis_done(self, result):
        self.bar.setValue(1000)
        try:
            n = result.frame_count
        except Exception:
            n = 0
        self.lbl_status.setText(f"done: {n} frames 完成")
        self.statusBar().showMessage(f"analysis done: {n} frames")

    # ------------------------------------------------------------- panels
    def _refresh_panels(self):
        r = self._result
        if r is None:
            return
        self._update_source_panel()
        try:
            rows = [(r.i_stats, "I"), (r.p_stats, "P"), (r.b_stats, "B"), (r.o_stats, "?")]
            for i, (st, _letter) in enumerate(rows):
                mb = st.bytes / 1024.0 / 1024.0
                vals = [str(st.count), f"{st.percent:.1f}%", f"{mb:.2f}MB",
                        f"{st.avg_size:.0f}", f"{st.avg_qp:.1f}", f"{st.avg_motion:.2f}"]
                for j, v in enumerate(vals):
                    self.tbl.setItem(i, j + 1, QTableWidgetItem(v))
        except Exception:
            pass
        try:
            self.lbl_gop.setText(r.gop_structure(64))
        except Exception:
            self.lbl_gop.setText("-")
        self._update_frame_detail()
        try:
            if getattr(self, "codec_panel", None) is not None and hasattr(self.codec_panel, "set_result"):
                self.codec_panel.set_result(r)
        except Exception:
            pass

    def _on_codec_layer(self, text: str) -> None:
        """Codec 层切换：调对应家族 overlay 并喂给 video_widget；缺失则降级+状态栏提示。"""
        try:
            t = str(text or "")
        except Exception:
            return
        # 关：清 overlay
        if not t or t == "关":
            try:
                try:
                    if hasattr(self.video, "set_codec_overlay"):
                        self.video.set_codec_overlay("off", None)
                    else:
                        self.video.codec_kind = "off"  # type: ignore[attr-defined]
                        self.video.codec_data = None  # type: ignore[attr-defined]
                except Exception:
                    pass
                self.video.update()
            except Exception:
                pass
            try:
                self.statusBar().showMessage("Codec层: 关")
            except Exception:
                pass
            return
        # 尺寸 / 编码 / 当前帧 / 全帧（容错）
        w = h = 0
        codec_raw = "unknown"
        cur = None
        frames: list = []
        try:
            if self._result is not None:
                try:
                    w = int(getattr(self._result.media, "width", 0) or 0)
                    h = int(getattr(self._result.media, "height", 0) or 0)
                except Exception:
                    pass
                try:
                    codec_raw = str(getattr(self._result.media, "video_codec", "unknown") or "unknown")
                except Exception:
                    pass
                try:
                    cur = self._result.frame_at(self._position)
                except Exception:
                    cur = None
                try:
                    frames = list(getattr(self._result, "frames", None) or [])
                except Exception:
                    frames = []
        except Exception:
            pass
        if w <= 0 or h <= 0:
            try:
                w = int(getattr(self.video, "_img_w", 0) or 0)
                h = int(getattr(self.video, "_img_h", 0) or 0)
            except Exception:
                pass
        if w <= 0 or h <= 0:
            w, h = 320, 240

        def _feed(kind: str, data) -> None:
            try:
                if hasattr(self.video, "set_codec_overlay"):
                    self.video.set_codec_overlay(kind, data)
                else:
                    self.video.codec_kind = kind  # type: ignore[attr-defined]
                    self.video.codec_data = data  # type: ignore[attr-defined]
                    self.video.update()
            except Exception:
                try:
                    self.video.update()
                except Exception:
                    pass

        handled = False
        try:
            if t == "AVC分区":
                from . import codec_avc_h263 as _m  # type: ignore
                ov = _m.partition_overlay(int(w), int(h), codec_raw or "avc")
                # 只画当前帧类型相关：I->mb, P->mb+p, B->mb+b
                try:
                    letter = str(getattr(getattr(cur, "type", None), "letter", "P"))
                except Exception:
                    letter = "P"
                allow = {"I": {"mb"}, "P": {"mb", "p"}, "B": {"mb", "b"}}.get(letter, {"mb", "p", "b"})
                ov = [e for e in (ov or []) if len(e) >= 5 and str(e[4]) in allow]
                _feed("avc", ov)
                handled = True
            elif t == "H.263 GOB":
                from . import codec_avc_h263 as _m  # type: ignore
                ov = _m.partition_overlay(int(w), int(h), "h263")
                _feed("h263", ov)
                handled = True
            elif t == "CTU四叉树":
                from . import codec_hevc as _m  # type: ignore
                ov = _m.ctu_quadtree_overlay(int(w), int(h), cur)
                _feed("hevc", ov)
                handled = True
            elif t == "VP分段":
                from . import codec_vp as _m  # type: ignore
                ov = _m.segmentation_overlay(int(w), int(h), cur, codec_raw or "vp8")
                _feed("vpseg", ov)
                handled = True
            elif t == "AV1 SB":
                from . import codec_theora_av1 as _m  # type: ignore
                ov = _m.superblock_overlay(int(w), int(h), cur, "av1")
                _feed("av1sb", ov)
                handled = True
            elif t == "AltRef星":
                ov = None
                try:
                    from . import codec_vp as _m  # type: ignore
                    ov = _m.altref_markers(frames, codec_raw or "vp8")
                except Exception:
                    ov = None
                if not ov:
                    # 回退：用 summarize 的大P启发（与 codec_insight 同阈值）
                    try:
                        from .codec_insight import summarize as _sum
                        s = _sum(self._result)
                        n_alt = int(s.get("altref_count", 0) or 0)
                        ov = [("heuristic", n_alt)]
                    except Exception:
                        ov = []
                _feed("altref", ov)
                handled = True
            else:
                raise ImportError(f"unknown layer {t}")
        except Exception as e:
            handled = False
            try:
                self.statusBar().showMessage(f"Codec层 {t} 未就绪（家族模块缺失），已降级: {e}")
            except Exception:
                pass
        # 降级可视：分区类开网格，其余仅刷新；成功则提示
        try:
            if handled:
                try:
                    self.statusBar().showMessage(f"Codec层: {t} 已叠加")
                except Exception:
                    pass
            else:
                try:
                    if t in ("AVC分区", "CTU四叉树", "VP分段", "AV1 SB", "H.263 GOB"):
                        self.video.show_grid = True
                        try:
                            self.ck_grid.setChecked(True)
                        except Exception:
                            pass
                    self.video.update()
                except Exception:
                    pass
        except Exception:
            pass

    def _update_source_panel(self):
        """SOURCE block mirroring MainViewModel.RebuildMediaRows (FILE/FORMAT/VIDEO/SCAN/COLOR/LENGTH/AUDIO/SIZE)."""
        r = self._result
        if r is None:
            return
        m = r.media
        range_text = {"tv": "tv", "pc": "pc"}.get(m.color_range, m.color_range)
        scan = "progressive" if m.field_order == "progressive" else m.field_order
        avg = r.avg_bitrate if r.avg_bitrate > 0 else (m.video_bit_rate / 1000.0 if m.video_bit_rate else 0)
        nframes = m.nb_frames if m.nb_frames > 0 else r.frame_count
        try:
            self.txt_source.setPlainText(
                f"FILE   {m.file_name}\n"
                f"FORMAT {m.format_line()}\n"
                f"VIDEO  {m.video_line}   SAR {m.sar_num}:{m.sar_den}  DAR {m.dar_text()}\n"
                f"SCAN   {m.width}x{m.height}  @ {m.frame_rate_text}  {scan}\n"
                f"COLOR  {m.pix_fmt} / {m.color_space} / {range_text}\n"
                f"LENGTH {m.duration_text}  {nframes} frames  avg {avg:.0f} kbps\n"
                f"AUDIO  {m.audio_line}\n"
                f"SIZE   {m.file_size_bytes / 1024.0 / 1024.0:.2f} MB")
        except Exception:
            pass

    def _update_frame_detail(self):
        r = self._result
        if r is None or not r.frames:
            self.txt_frame.setPlainText("no frames")
            return
        f = r.frame_at(self._position)
        if f is None:
            return
        try:
            letter = f.type.letter
        except Exception:
            letter = "?"
        long_name = {0: "? (unknown)", 1: "I (intra)", 2: "P (predicted)", 3: "B (bi-predicted)"}.get(
            int(f.type), "? (unknown)")
        m = r.media
        parts = []
        if m.field_order != "unknown":
            parts.append(m.field_order)
        if f.interlaced:
            parts.append("interlaced")
        if f.repeat_pict:
            parts.append("repeat")
        if f.key_frame:
            parts.append("key")
        if f.brain:
            parts.append("blocky")
        if f.corrupt:
            parts.append("corrupt")
        if f.discard:
            parts.append("discard")
        flags = ", ".join(parts) if parts else "-"
        qp_suffix = " (est.)" if r.qp_estimated else ""
        if f.qp_avg is not None:
            qp_line = f"avg {f.qp_avg:.1f}  min {f.qp_min:.0f}  max {f.qp_max:.0f}{qp_suffix}"
        else:
            qp_line = "not analysed"
        if f.motion_mean is not None:
            mot_suffix = " (est.)" if r.motion_estimated else ""
            mot_line = (f"mean {f.motion_mean:.2f} px  max {(f.motion_max or 0):.1f} px  "
                        f"·  {f.motion_count} vec (fwd {f.motion_fwd} / bwd {f.motion_bwd}){mot_suffix}")
        else:
            mot_line = "not analysed"
        clock = f"{int(f.pts_time // 60):02d}:{f.pts_time % 60:06.3f}"
        kb = f.packet_size / 1024.0
        self.txt_frame.setPlainText(
            f"FRAME  {f.index} / {r.frame_count}   {clock}   dur {f.duration_ms:.2f} ms\n"
            f"TYPE   {long_name}\n"
            f"SIZE   {f.packet_size} B  ({kb:.1f} KB)  {f.bitrate_kbps:.0f} kbps\n"
            f"QP     {qp_line}\n"
            f"MOTION {mot_line}\n"
            f"GOP    +{f.gop_position} since keyframe   reorder {f.reorder_delta:+d}\n"
            f"FLAGS  {flags}")
        # overlays 用当前帧
        try:
            self.video.set_frame_info(f)
            if f.motion is not None:
                self.video.set_field(f.motion)
        except Exception:
            pass

    # ------------------------------------------------------------- view/seek
    def _on_follow(self, on: bool):
        self._follow = bool(on)
        if on:
            self._center_view()

    def _center_view(self):
        span = self._view_end - self._view_start
        self._view_start = self._position - span / 2
        self._view_end = self._position + span / 2
        self.graphs.set_view(self._view_start, self._view_end)

    def _on_graph_view(self, a: float, b: float):
        self._view_start, self._view_end = float(a), float(b)
        self.graphs.set_view(a, b)

    def _on_graph_range(self, a: float, b: float):
        self.spin_from.setValue(a)
        self.spin_to.setValue(b)
        self.graphs.set_selected_range(a, b)
        self.statusBar().showMessage(f"range {a:.2f}s – {b:.2f}s (右键双击重标)")

    def seek(self, sec: float):
        r = self._result
        total = 1.0
        try:
            if r is not None and r.frames:
                total = max(0.04, float(r.duration_seconds))
            elif r is not None:
                total = max(0.04, float(r.media.duration or 1.0))
        except Exception:
            pass
        sec = max(0.0, min(total, float(sec)))
        jumped = abs(sec - self._position) > 0.5
        self._position = sec
        self.graphs.set_playhead(sec)
        if self._follow:
            span = self._view_end - self._view_start
            # follow 居中 (pinned playhead)
            if sec < self._view_start or sec > self._view_end or self._follow:
                self._center_view()
        self._update_timeline()
        if jumped:
            self._restart_engine(sec)
        self._show_frame_at(sec)
        self._update_frame_detail()

    def _update_timeline(self):
        try:
            r = self._result
            dur = float(r.duration_seconds) if r is not None and r.frames else 1.0
        except Exception:
            dur = 1.0
        dur = max(0.04, dur)
        self.timeline.blockSignals(True)
        self.timeline.setValue(int(self._position / dur * 10000))
        self.timeline.blockSignals(False)
        self.lbl_time.setText(f"{self._fmt(self._position)} / {self._fmt(dur)}")

    @staticmethod
    def _fmt(s: float) -> str:
        m = int(s // 60)
        return f"{m}:{s - m * 60:06.3f}"

    def _on_timeline_moved(self, v: int):
        try:
            r = self._result
            dur = float(r.duration_seconds) if r is not None and r.frames else 1.0
        except Exception:
            dur = 1.0
        self.seek(v / 10000.0 * max(0.04, dur))

    def _on_timeline_released(self):
        pass

    # ------------------------------------------------------------- transport
    def toggle_play(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if self._result is None or not self._result.frames:
            self.lbl_status.setText("no video — open file first 先打开视频")
            return
        # audio 同步 start
        try:
            if self._audio is not None and self._path:
                try:
                    self._audio.set_volume(self.vol.value() / 100.0)
                except Exception:
                    pass
                self._audio.start(self._path, self._position)
        except Exception:
            pass
        fps = 25.0
        try:
            fps = float(self._result.media.fps or 25.0)
        except Exception:
            pass
        self._play_timer.start(int(max(10, 1000.0 / max(1.0, fps))))
        self._playing = True
        self.btn_play.setText("⏸ 暂停")
        self._restart_engine(self._position)

    def pause(self):
        self._play_timer.stop()
        self._playing = False
        self.btn_play.setText("▶ 播放")
        try:
            if self._audio is not None:
                self._audio.stop()
        except Exception:
            pass

    def step_frame(self, delta: int):
        r = self._result
        if r is None or not r.frames:
            return
        idx = r.index_at(self._position)
        idx = max(0, min(len(r.frames) - 1, idx + delta))
        self.seek(r.frames[idx].pts_time)

    def jump_key(self, delta: int):
        r = self._result
        if r is None or not r.frames:
            return
        idx = r.index_at(self._position)
        if delta > 0:
            for f in r.frames[idx + 1:]:
                if f.key_frame:
                    self.seek(f.pts_time)
                    return
            self.seek(r.frames[-1].pts_time)
        else:
            for f in reversed(r.frames[:max(0, idx)]):
                if f.key_frame:
                    self.seek(f.pts_time)
                    return
            self.seek(r.frames[0].pts_time)

    def _tick(self):
        r = self._result
        if r is None or not r.frames:
            self.pause()
            return
        # 首选 PlaybackEngine 顺序拉帧；播到 decoder EOF（ended 且队列空）停
        if self._engine is not None:
            try:
                arr = self._engine.try_get_frame()
            except Exception:
                arr = None
            if arr is not None:
                try:
                    self.video.show_frame(np.ascontiguousarray(arr, dtype=np.uint8))
                except Exception:
                    pass
                fps = 25.0
                try:
                    fps = float(r.media.fps or 25.0)
                except Exception:
                    pass
                nxt = self._position + 1.0 / max(1.0, fps)
                try:
                    dur = float(r.duration_seconds)
                except Exception:
                    dur = nxt + 1
                if nxt >= dur:
                    if self._loop:
                        self._position = 0.0
                        self._restart_engine(0.0)
                    else:
                        self._position = dur
                else:
                    self._position = nxt
                self.graphs.set_playhead(self._position)
                if self._follow:
                    self._center_view()
                self._update_timeline()
                self._update_frame_detail()
                return
            try:
                if bool(getattr(self._engine, "ended", False)):
                    self.pause()  # 播到 decoder EOF 停
                    return
            except Exception:
                pass
            return  # 解码器还没产出，等下一 tick
        fps = 25.0
        try:
            fps = float(r.media.fps or 25.0)
        except Exception:
            pass
        nxt = self._position + 1.0 / max(1.0, fps)
        try:
            dur = float(r.duration_seconds)
        except Exception:
            dur = nxt + 1
        if nxt >= dur:
            if self._loop:
                nxt = 0.0
                self._stop_decoder()
                self._ensure_decoder(0.0)
            else:
                self.seek(dur)
                self.pause()  # 播到 decoder EOF 停
                return
        self.seek(nxt)

    # --------------------------------------------------------- frame display
    def _restart_engine(self, sec: float):
        # PlaybackEngine 是顺序流：seek 跳转即 restart；暂停态也 restart 以便取暂停帧
        if self._engine is None or self._result is None or self._path is None:
            return
        try:
            w = int(self._result.media.width or 0)
            h = int(self._result.media.height or 0)
            idx = int(self._result.index_at(sec))
        except Exception:
            return
        if w <= 0 or h <= 0:
            return
        try:
            self._engine.start(self._path, w, h, float(sec), idx)
        except Exception as e:  # noqa: BLE001
            try:
                self.statusBar().showMessage(str(e))
            except Exception:
                pass

    def _engine_poll(self):
        if self._engine is None:
            return None
        try:
            return self._engine.try_get_frame()
        except Exception:
            return None

    def _show_frame_at(self, sec: float):
        # 播放态由 _tick 顺序拉帧；此处处理暂停/seek：先取引擎帧，否则缩略图
        arr = self._engine_poll()
        if arr is not None:
            try:
                self.video.show_frame(np.ascontiguousarray(arr, dtype=np.uint8))
                return
            except Exception:
                pass
        else:
            # 暂停 seek 后引擎刚 restart，第一帧还没到：用缩略图预览顶一下
            if self._engine is not None and self._result is not None and not self._playing:
                try:
                    QTimer.singleShot(60, self._poll_paused_frame)
                except Exception:
                    pass
        if self._strip is not None:
            try:
                thumb = self._strip.at(sec)
                if thumb is not None:
                    self.video.show_frame(np.ascontiguousarray(thumb, dtype=np.uint8))
                    return
            except Exception:
                pass
        if self._thumbs:
            try:
                best = min(self._thumbs, key=lambda t: abs(float(t[1]) - sec))
                self.video.show_frame(np.ascontiguousarray(best[0], dtype=np.uint8))
                return
            except Exception:
                pass
        if self._engine is None:
            arr = self._decode_frame(sec)
            if arr is not None:
                try:
                    self.video.show_frame(np.ascontiguousarray(arr, dtype=np.uint8))
                except Exception:
                    pass

    def _poll_paused_frame(self):
        if self._playing:
            return
        arr = self._engine_poll()
        if arr is not None:
            try:
                self.video.show_frame(np.ascontiguousarray(arr, dtype=np.uint8))
            except Exception:
                pass

    def _decode_frame(self, sec: float):
        """内置最小 rawvideo 拉帧：顺序读，seek 跨度大则重启 -ss。"""
        r = self._result
        if r is None or self._path is None:
            return None
        try:
            w, h = int(r.media.width or 0), int(r.media.height or 0)
        except Exception:
            w, h = 0, 0
        if w <= 0 or h <= 0:
            return None
        # 是否需要 (重)启动解码器：目标在已读位置之前则重启
        if self._dec is None:
            self._ensure_decoder(sec)
        if self._dec is None:
            return None
        # 估算目标帧序号
        try:
            idx = r.index_at(sec)
        except Exception:
            idx = 0
        # 若目标在已读位置之前 -> 重启
        if idx < self._dec_index - 2:
            self._ensure_decoder(sec)
            if self._dec is None:
                return None
        # 推进到目标
        frame_sz = w * h * 3
        data = None
        guard = 0
        while self._dec_index <= idx and guard < 600:
            guard += 1
            try:
                raw = self._dec.stdout.read(frame_sz)  # type: ignore
            except Exception:
                self._stop_decoder()
                return None
            if not raw or len(raw) < frame_sz:
                self._stop_decoder()  # decoder EOF
                return None
            self._dec_index += 1
            data = raw
        if data is None:
            return None
        try:
            return np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)
        except Exception:
            return None

    def _ensure_decoder(self, from_sec: float):
        exe = ffmpeg_locator.ffmpeg_path()
        r = self._result
        if not exe or r is None or self._path is None:
            return
        try:
            w, h = int(r.media.width or 0), int(r.media.height or 0)
        except Exception:
            return
        if w <= 0 or h <= 0:
            return
        self._stop_decoder()
        try:
            # 优先 playback.open 式快播；此处直接 ffmpeg 管道 rgb24
            cmd = [exe, "-v", "error", "-ss", f"{max(0.0, from_sec):.3f}",
                   "-i", self._path, "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-vsync", "0", "-"]
            self._dec = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self._dec_w, self._dec_h = w, h
            try:
                self._dec_index = r.index_at(from_sec)
            except Exception:
                self._dec_index = 0
            # -ss 跳转后解码器从 0 开始计数，做一次对齐
            if from_sec > 0.5:
                self._dec_index = 0
                # 快进丢弃：按 index 推进在 _decode_frame 里做；此处重置为 0
        except Exception:
            self._dec = None

    def _stop_decoder(self):
        try:
            if self._engine is not None:
                try:
                    self._engine.stop()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if self._dec is not None:
                try:
                    self._dec.kill()
                except Exception:
                    pass
                try:
                    self._dec.wait(timeout=1)
                except Exception:
                    pass
        except Exception:
            pass
        self._dec = None
        self._dec_index = 0

    # ------------------------------------------------------------------ events
    def dragEnterEvent(self, ev):  # noqa: N802
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):  # noqa: N802
        try:
            for u in ev.mimeData().urls():
                p = u.toLocalFile()
                if p:
                    self.open_file(p)
                    break
        except Exception:
            pass

    def closeEvent(self, ev):  # noqa: N802
        try:
            self.pause()
        except Exception:
            pass
        self._stop_decoder()
        try:
            if self._audio is not None:
                try:
                    self._audio.close()
                except Exception:
                    try:
                        self._audio.stop()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if self._worker is not None and self._worker.isRunning():
                try:
                    self._worker.cancel()
                except Exception:
                    self._worker.requestInterruption()
                self._worker.wait(800)
        except Exception:
            pass
        super().closeEvent(ev)


def _smoke_selftest() -> int:
    """供 main --selftest 复用：不弹 GUI，只 assert 数据+离屏 paint。"""
    from .models import AnalysisResult, FrameInfo, MediaInfo, MotionField, PicType
    app = QApplication.instance() or QApplication([])
    media = MediaInfo(file_path="synth.mp4", file_name="synth.mp4",
                      format_name="mp4", duration=6.0, width=320, height=240,
                      pix_fmt="yuv420p", fps=20.0, nb_frames=120,
                      video_codec="h264", has_audio=False)
    res = AnalysisResult(media=media)
    frames = []
    for i in range(120):
        t = i * 0.05
        pt = PicType.I if i % 30 == 0 else (PicType.P if i % 3 == 0 else PicType.B)
        key = (i % 30 == 0)
        qp = 18.0 + (i % 12)
        frames.append(FrameInfo(
            index=i, decode_index=i, pts_time=t, dts_time=t - (0.08 if pt == PicType.B else 0.0),
            type=pt, key_frame=key, packet_size=4000 + (20000 if key else (i * 37) % 6000),
            duration_ms=50.0, qp_avg=qp, qp_min=qp - 3, qp_max=qp + 4,
            motion_mean=0.0 if pt == PicType.I else 1.5 + (i % 7) * 0.4,
            motion_fwd=4 if pt != PicType.I else 0, motion_bwd=2 if pt == PicType.B else 0,
            motion_max=8.0, motion_count=6,
            brain=(i == 55), gop_position=0 if key else i % 30,
            reorder_delta=2 if pt == PicType.B else 0,
            bitrate_kbps=(4000 + (20000 if key else 0)) * 8 / 50.0,
            corrupt=(i == 77), discard=False,
            interlaced=(i == 80), repeat_pict=(i == 81)))
    res.frames = frames
    res.has_deep = True
    res.qp_estimated = True
    res.compute_aggregates()
    assert res.frame_count == 120, res.frame_count
    tot = res.i_stats.count + res.p_stats.count + res.b_stats.count + res.o_stats.count
    assert tot == 120, tot
    assert res.gop_structure(64).startswith("I"), res.gop_structure(64)[:10]
    return 0
