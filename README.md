# QtVideoAnalyzer

**A cross-platform, frame-level video stream analyser** — it decodes a file, builds a per-frame
record of the encoded stream, and plots that record as a stack of synchronised graphs, so
compression and mastering problems can be seen at a glance.

A Qt (PySide6) rewrite of [VideoAnalyzer](https://github.com/z13660/VideoAnalyzer)
(WPF, Windows-only): same analysis pipeline and B/I/P frame record, now running on
**Windows / macOS / Linux** from one Python codebase. Analysis goes through **ffmpeg**;
playback and graphs are pure Qt.

**English** | [简体中文](README.zh-CN.md)

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-0078D4)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![Qt](https://img.shields.io/badge/Qt-PySide6-41CD52)
![ffmpeg](https://img.shields.io/badge/ffmpeg-required-2E7D32)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## What it is

A video file is a stream of decisions an encoder made: how many bits each frame got, which
frames are key frames, where it spent its quantiser, which blocks it predicted from where.
Those decisions are invisible when you just watch the picture, and they are what you have to
look at when the picture is wrong.

QtVideoAnalyzer makes them visible. Pick a file and it decodes it in stages — container, packet
table, picture types, quantiser, motion — publishing each stage the moment it has it.
The transport opens as soon as the packet table is in and you can play while the rest of the
analysis continues; the graphs fill in underneath as it goes.

Everything goes through ffmpeg, so a file ffmpeg can read is a file this can analyse.
No native bindings: PySide6 + numpy + opencv (motion fallback) + ffmpeg/ffprobe subprocesses.

---

## Features

| | |
|---|---|
| **Six synchronised graphs** | Bitrate, picture type, QP, motion, GOP position and reorder distance, all on one timeline under one playhead |
| **Scrub = preview, release = seek** | Dragging shows an instant filmstrip thumbnail; exactly one real seek runs on release, the playhead never fights you |
| **Frame-accurate playback** | Decoded through an ffmpeg `rawvideo` pipe into a `QImage`: exact frame stepping, no media-element limits |
| **Codec layer auto-follow** | The overlay switches itself to the file's format: AVC partitions, H.263 GOBs, HEVC CTU quad-tree, VVC MTT, AVS3 LCU, VP segmentation, AV1 superblocks, ProRes slices, Theora dots, AltRef stars |
| **CodecDNA panel** | Family badge, 3 strength bullets, mini GOP strip (I red / P blue / B green / AltRef gold), and "where to look" hints per codec |
| **B/I/P picture-type analysis** | Per-type counts, byte share, avg size/QP/motion, GOP structure string for every supported codec |
| **Analyser overlays** | Motion vectors, macroblock grid, block-noise dots, drawn over the picture |
| **Sample browser + import** | 50+ bundled samples one click away, or import your own video (dialog or drag & drop) |
| **Range analysis** | Mark or type a range and only that stretch is re-decoded; the timeline follows the range |
| **Live progress** | Stage + percent in the status bar and progress bar while QP/motion decode |
| **Part of a clip, stoppable** | Same semantics as the original: ranges accumulate, passes can be cancelled keeping partial results |

### The graph stack

| Row | What it shows |
|---|---|
| **BITRATE** | Bits per frame on a log₂ scale, with the clip average; key frames drawn brighter |
| **FRAME TYPE** | One lane per picture type (I / P / B), key frames marked as vertical lines |
| **QP** | Quantiser: the average as a line, the per-frame min–max as a band (`est.` when decoder-exact values are unavailable) |
| **MOTION** | Mean motion-vector length per frame, forward / backward share |
| **GOP** | Frames since the last key frame — the shape of each GOP |
| **REORDER** | PTS−DTS in frames, with corrupt / discard / interlace / repeat flags on the baseline |

### Codec coverage (13 formats)

| Family | Formats | Notes |
|---|---|---|
| MPEG | AVC (H.264), HEVC (H.265), MPEG-2, H.263 | Native `-debug qp` types+QP; B-frames on AVC/HEVC/MPEG-2 |
| Open | Theora, AV1, VP6, VP8, VP9, AV2 (descriptive) | Estimator fallback; AltRef stars for VP8/VP9; AV2 has no encoder yet |
| Next-gen | VVC (H.266), AVS3 | VVC parses natively; AVS3 decodes via bundled-reference `uavs3dec` + H.264 proxy playback |
| Mezzanine | ProRes (all 6 profiles) | All-intra: red I lane, flat GOP/reorder, high flat bitrate |

Per-format profile / chroma (420/422/444) / rate-control (CRF/CQP/CBR/ABR/VBR) matrices and tuning
guides live in `docs/rates/<format>.md`; per-family algorithm notes in `docs/codec-*.md`.

---

## Analysis pipeline

Each stage publishes as soon as it has results, so the app is usable long before it is finished.

| Stage | Feeds |
|---|---|
| 1. Probe | `ffprobe -show_format -show_streams`: container, codec, resolution, frame rate, colour tags, SAR/DAR, audio layout |
| 2. Packet scan | `ffprobe -show_packets`: packet table without decoding — size, pts, dts, key / discard / corrupt flags; timestamp-less raw streams (`.bit`) get synthesised `i/fps` stamps |
| 3. Picture types + QP | One `ffmpeg -debug qp` decode yields both picture type and real per-macroblock quantiser (AVC/MPEG-2/H.263); elsewhere `ffprobe -show_frames` headers; elsewhere a bits-per-pixel estimate flagged `(est.)`; AVS3 uses the `uavs3dec` frame log |
| 4. Motion | `-debug mv` vectors when the decoder provides them, otherwise a built-in Farneback/block estimator on a 320 px greyscale stream (AVS3 pixels come from `uavs3dec`) |

Stages 3 and 4 run at the same time. Both publish as they go, so the graphs fill in while the
analysis is still running. Cancellation is quiet: superseded workers exit without error dialogs.

Playback of formats ffmpeg cannot decode (AVS3) uses an automatically built H.264 proxy
(`tools/samples/.avs3proxy/`, git-ignored) while all analysis stays on the original stream.

---

## Requirements

* **Windows 10 / 11, macOS 12+, or desktop Linux** (x64 or arm64)
* **Python 3.10+** with `pip install -r requirements.txt` (PySide6, numpy, opencv-python-headless)
* **ffmpeg and ffprobe**, any recent build — looked up via `FFMPEG_HOME`, `tools/ffmpeg/bin/`,
  `PATH`, then well-known install locations
* **uavs3dec** (optional, AVS3 only): `tools/avs3bin/uavs3dec` — build from
  [uavs3d](https://github.com/uavs3/uavs3d); without it AVS3 still analyses, only playback
  waits for the proxy

---

## Getting started

```bash
git clone https://github.com/Bemly/QtVideoAnalyzer.git
cd QtVideoAnalyzer
pip install -r requirements.txt
python -m qt_analyzer.main [video]   # no arg => file dialog; videos can be dropped on the window
```

One-command checks (headless-safe):

```bash
QT_QPA_PLATFORM=offscreen python -m qt_analyzer.main --selftest
python tests/test_codecs.py
```

Sample clips (URLs only — the repo ships no binaries, `tools/samples/` is git-ignored):

```bash
cat docs/samples/README.md          # master source index + licences
./tools/make_test_videos.sh         # regenerate the core 7 test clips
./tools/retranscode_from_sintel.sh  # rebuild profile/RC variants from the Sintel trailer
```

---

## Controls

| Key | Effect |
|---|---|
| `Ctrl+O` | Open a video (or drop one on the window, or pass it as an argument) |
| `Space` | Play / pause |
| `←` / `→` | Previous / next frame |
| `Ctrl+←` / `Ctrl+→` | Previous / next key frame |
| `Esc` | Leave full screen |

| Mouse | Effect |
|---|---|
| Click a graph or the timeline | Seek to the point clicked |
| Drag a graph or the timeline | Scrub — thumbnail preview follows the cursor, one real seek on release |
| Right-click the timeline | Mark an analysis range; type it precisely in 起/止 and press 分析范围 |
| Wheel over a graph or the timeline | Zoom around the cursor |
| Double-click the picture | Full screen; double-click again (or `Esc`) to leave |

---

## Layout

```
qt_analyzer/
  main.py              entry point (+ --selftest)
  main_window.py       layout, transport, scrub state machine, range view, workers
  models.py            MediaInfo, FrameInfo, AnalysisResult (mirrors the C# models)
  probe.py             container / stream metadata (+ AVS3 size/fps via uavs3dec)
  packets.py           packet-table sweep, timestamp synthesis for raw streams
  pipeline.py          progressive orchestration (probe -> packets -> deep)
  deep_qp.py           picture types + QP (native / show_frames / estimate / uavs3dec log)
  motion.py            motion vectors (native mv / Farneback fallback / uavs3dec pixels)
  block.py             blockiness/activity (overlays + brain flag)
  playback.py          rawvideo pipe engine (seekable + timestamp-less modes)
  audio.py             PCM through QAudioSink
  filmstrip.py         thumbnail strip for scrub preview
  graphs.py            6-row synchronised graph widget (press/move/release scrub signals)
  video_widget.py      picture + overlays + codec layers
  codec_insight.py     codec normalisation + CodecDNA summaries (13 formats)
  codec_panel.py       CodecDNA panel widget
  codec_avc_h263.py / codec_hevc.py / codec_vp.py / codec_theora_av1.py
  codec_next.py (VVC/AV2) / codec_avs3.py / codec_prores.py
  rc_<format>.py × 13  profile/chroma/RC matrices + recommend()
  ffmpeg_locator.py    finds the toolchain
tools/
  make_test_videos.sh         core 7 clips (testsrc-based)
  retranscode_from_sintel.sh  profile/RC variants from real footage
  samples/                   git-ignored local clips + .avs3proxy/
  avs3bin/                   git-ignored local uavs3dec
docs/
  codec-*.md      per-family algorithm notes (what to look at)
  rates/<format>.md   profile × chroma × RC matrices + tuning
  samples/        per-format source URLs + measured tables (binaries not vendored)
tests/test_codecs.py  probe/packets regression over the bundled clips
```

## Notes on the design

* **Scrub previews, release seeks.** A seek restarts the decoder, so dragging only moves the
  playhead over filmstrip thumbnails; the real (frame-accurate) seek happens once, on release.
  While scrubbing, the play timer is paused so it never fights the cursor.
* **Timestamp-less streams are first-class.** Raw `.bit`/Annex-B inputs get synthesised
  `pts=dts=i/fps`, the engine drops `-ss`/`passthrough` and skips by frame count.
* **Progress is always visible.** Every deep pass reports stage + percent to the status bar and
  the ANALYSIS progress bar; cancellation is silent by design.
* **Proxies never touch analysis.** The AVS3 H.264 proxy exists only so the picture can move;
  every graph, stat and overlay is computed from the original stream (or its real decode).
* **Samples are referenced, not vendored.** `docs/samples/` records a URL or an exact ffmpeg
  command per clip; nothing under `tools/samples/` is committed.

## Known limitations

* QP is decoder-exact only where ffmpeg's `-debug qp` supports the codec; otherwise it is an
  estimate, flagged in the UI.
* The built-in motion estimator is a real block matcher, not the encoder's own decisions, so on
  flat synthetic footage the vectors are legitimately near zero.
* VP/AV1 alt-ref frames report as P (their hidden-reference structure is shown as AltRef stars
  instead of B lanes).
* AVS3 packet timestamps from the demuxer are partial (many `N/A`); GOP/reorder rows for AVS3
  are approximate while types/motion come from the real decode.
* VVC multilayer streams parse but the bundled ffmpeg decoder reports `Not yet implemented`;
  playback waits for a capable decoder build.

## License

MIT — see [LICENSE](LICENSE). Original WPF application © its authors; this Qt rewrite is a
separate implementation sharing only the analysis approach.
