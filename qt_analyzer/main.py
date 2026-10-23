"""Entry point. `python -m qt_analyzer.main [video]` / `--selftest`."""
from __future__ import annotations

import os
import sys


def _build_synth_result():
    from .models import AnalysisResult, FrameInfo, MediaInfo, MotionField, PicType
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
        cols, rows = 20, 15
        n = cols * rows
        dx = [0] * n
        dy = [0] * n
        ref = [0] * n
        if pt != PicType.I and i % 2 == 0:
            for k in range(0, n, 4):
                dx[k] = (i % 5) - 2
                dy[k] = (k % 3) - 1
                ref[k] = 2 if pt == PicType.B and k % 8 == 0 else 1
        mf = MotionField(cols=cols, rows=rows, dx=dx, dy=dy, ref=ref)
        frames.append(FrameInfo(
            index=i, decode_index=i, pts_time=t, dts_time=t - (0.08 if pt == PicType.B else 0.0),
            type=pt, key_frame=key, packet_size=4000 + (20000 if key else (i * 37) % 6000),
            duration_ms=50.0, qp_avg=qp, qp_min=qp - 3, qp_max=qp + 4,
            motion_mean=0.0 if pt == PicType.I else 1.5 + (i % 7) * 0.4,
            motion_fwd=4 if pt != PicType.I else 0, motion_bwd=2 if pt == PicType.B else 0,
            motion_max=8.0, motion_count=6, motion=mf,
            brain=(i == 55), gop_position=0 if key else i % 30,
            reorder_delta=2 if pt == PicType.B else 0,
            bitrate_kbps=(4000 + (20000 if key else 0)) * 8 / 50.0,
            corrupt=(i == 77), discard=(i == 78),
            interlaced=(i == 80), repeat_pict=(i == 81)))
    res.frames = frames
    res.has_deep = True
    res.qp_estimated = True
    res.motion_estimated = False
    res.compute_aggregates()
    return res


def _selftest() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QSize
    import numpy as np

    app = QApplication.instance() or QApplication([])
    from .graphs import GraphStack
    from .video_widget import VideoWidget

    res = _build_synth_result()
    # ---- B/I/P 表格断言 ----
    tot = res.i_stats.count + res.p_stats.count + res.b_stats.count + res.o_stats.count
    assert tot == res.frame_count == 120, f"counts {tot} != 120"
    assert res.i_stats.count == 4, res.i_stats.count
    assert res.gop_structure(64).startswith("I"), res.gop_structure(64)[:12]
    assert res.max_bitrate > res.avg_bitrate > 0, (res.max_bitrate, res.avg_bitrate)
    assert res.max_qp >= res.min_qp, (res.max_qp, res.min_qp)
    print(f"[selftest] BIP ok: I={res.i_stats.count} P={res.p_stats.count} "
          f"B={res.b_stats.count} O={res.o_stats.count} "
          f"gop='{res.gop_structure(16)}' avg_br={res.avg_bitrate:.0f}kbps "
          f"qp_est={res.qp_estimated} maxmot={res.max_motion:.2f}")

    # ---- graphs 离屏 paint ----
    g = GraphStack()
    g.resize(800, 6 * 64)
    g.set_result(res)
    g.set_view(0.0, res.duration_seconds)
    g.set_playhead(1.25)
    g.set_selected_range(0.5, 2.0)
    g.show()
    app.processEvents()
    img = QImage(g.size(), QImage.Format.Format_RGB32)
    img.fill(0)
    g.render(img)
    # 非黑像素断言（有 bars/线条画出来）
    ptr = img.bits()
    import numpy as _np
    a = _np.frombuffer(ptr, dtype=_np.uint8).reshape(img.height(), img.bytesPerLine())
    assert a.sum() > 0, "graphs paint blank"
    print(f"[selftest] graphs paint ok: size={g.width()}x{g.height()} nonzero={int(a.sum() > 0)}")
    # zoom + scrub 信号冒烟
    got = []
    g.seek_requested.connect(lambda s: got.append(s))
    g.view_changed.connect(lambda a, b: got.append((a, b)))
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt as _Qt, QPoint as _QPoint
    QTest.mouseClick(g, _Qt.MouseButton.LeftButton, pos=_QPoint(400, 100))
    app.processEvents()
    assert got, "seek_requested not emitted"
    print(f"[selftest] graphs input ok: signals={len(got)}")

    # ---- video_widget 离屏 paint ----
    vw = VideoWidget()
    vw.resize(480, 270)
    rng = np.random.default_rng(0)
    arr = (rng.random((270, 480, 3)) * 255).astype(np.uint8)
    vw.show_frame(arr)
    f42 = res.frames[42]
    vw.set_frame_info(f42)
    vw.set_field(f42.motion)
    vw.show_vectors = True
    vw.show_grid = True
    vw.show_noise = True
    vw.show()
    app.processEvents()
    img2 = QImage(vw.size(), QImage.Format.Format_RGB32)
    img2.fill(0)
    vw.render(img2)
    ptr2 = img2.bits()
    a2 = _np.frombuffer(ptr2, dtype=_np.uint8).reshape(img2.height(), img2.bytesPerLine())
    assert a2.sum() > 0, "video paint blank"
    # brain 帧也画一遍
    vw.set_frame_info(res.frames[55])
    vw.repaint()
    app.processEvents()
    print(f"[selftest] video paint ok: frame={arr.shape} field={f42.motion.cols}x{f42.motion.rows}")

    # ---- main_window 表格逻辑冒烟（不 show）----
    from .main_window import MainWindow
    w = MainWindow()
    w._on_result(res)
    assert w.tbl.item(0, 1).text() == str(res.i_stats.count), "I count cell mismatch"
    assert "FRAME" in w.txt_frame.toPlainText(), "frame detail empty"
    assert "FILE" in w.txt_source.toPlainText(), "source panel empty"
    print(f"[selftest] main_window BIP table ok: I cell={w.tbl.item(0,1).text()} "
          f"gop='{w.lbl_gop.text()[:16]}'")
    print("SELFTEST PASS")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    os.environ.setdefault("QT_QPA_PLATFORM", "")
    # 空值会干扰 Qt，删掉
    if os.environ.get("QT_QPA_PLATFORM") == "":
        del os.environ["QT_QPA_PLATFORM"]
    from PySide6.QtWidgets import QApplication
    from .main_window import MainWindow
    app = QApplication(sys.argv)
    path = None
    for a in sys.argv[1:]:
        if not a.startswith("-"):
            path = a
            break
    w = MainWindow(initial_path=path)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
