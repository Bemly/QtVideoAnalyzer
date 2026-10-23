# VideoAnalyzer-Qt

Qt (PySide6) 跨平台重写：Windows / macOS / Linux 通吃，基于 ffmpeg 子进程，无第三方私有库绑定。

原版 `VideoAnalyzer` 是 `net8.0-windows + WPF`，只能在 Windows 跑。
本项目用 Qt Widgets + QPainter 重画 6 联图，用 `QAudioSink` 播 PCM，
用 `ffmpeg / ffprobe` 子进程做全部分析，可在 Mac/Linux/Windows 直接跑。

支持的编码器（全量 B/I/P 分析）：AVC(H.264) / HEVC(H.265) / MPEG-2 /
Theora / AV1 / H.263 / VP6 / VP8 / VP9。

## 运行

```bash
cd VideoAnalyzer-Qt
pip install -r requirements.txt
python -m qt_analyzer.main <video>
# 无参数则弹文件选择框；也支持拖拽
```

需要 `ffmpeg` + `ffprobe` 在 PATH 或 `FFMPEG_HOME` 里（`ffmpeg -version` 能跑就行）。

## 分析管线（与原版对齐）

1. Probe: `ffprobe -show_format -show_streams`
2. Packet scan: `ffprobe -show_packets` -> size/pts/dts/flags -> bitrate/GOP/reorder，key=K 标 I
3. Type+QP: `ffmpeg -debug qp` 原生则解析，否则按 bits-per-pixel 估计（标 est.）
4. Motion: `ffmpeg -debug mv` 原生则统计，否则内置 Farneback+块匹配回退（320px 灰度，8x8 块）

6 联图：BITRATE / FRAME TYPE(I/P/B) / QP / MOTION / GOP / REORDER，同一时间轴+中央 playhead。
右侧 B/I/P 面板：I/P/B/Other 的计数、占比、字节、平均大小、平均 QP、平均 motion、GOP 结构。
覆盖层：motion vectors / 16x16 macroblock grid / block-noise dots。

## 目录

```
qt_analyzer/
  models.py          FrameInfo/MediaInfo/AnalysisResult（对齐原版 FrameInfo.cs/AnalysisResult.cs）
  ffmpeg_locator.py  找 ffmpeg/ffprobe
  probe.py           容器/流元数据
  packets.py         包表扫描 -> bitrate/GOP/reorder
  deep_qp.py         picture type + QP（原生+估计，各编码器适配）
  motion.py          motion 原生 mv + 回退估计，各编码器适配
  block.py           blockiness/activity（macroblock grid/block-noise 用）
  pipeline.py        编排 1->4，流式发布
  playback.py        rawvideo rgb24 管道 + 定时拉帧
  audio.py           pcm s16le 48k 立体声 -> QAudioSink
  filmstrip.py       缩略图带（scrub 预览用）
  graphs.py          6 联图 QWidget
  video_widget.py    视频显示 + overlays
  main_window.py     主窗口 + B/I/P 面板 + 传输控制
  main.py            入口
tools/make_test_videos.sh  一键生成 8 编码器测试片
tests/test_codecs.py       8 编码器回归（probe/packets/qp/motion 全跑通）
```
