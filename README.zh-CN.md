# QtVideoAnalyzer

**跨平台的帧级视频流分析器**——解码文件，为编码流建立逐帧记录，再画成一叠同步曲线，
让压缩与母带问题一目了然。

[VideoAnalyzer](https://github.com/z13660/VideoAnalyzer)（WPF，仅 Windows）的 Qt（PySide6）
重写：同样的分析管线与 B/I/P 帧记录，一套 Python 代码跑在 **Windows / macOS / Linux** 上。
分析走 **ffmpeg**，播放与绘图是纯 Qt。

[English](README.md) | **简体中文**

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-0078D4)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![Qt](https://img.shields.io/badge/Qt-PySide6-41CD52)
![ffmpeg](https://img.shields.io/badge/ffmpeg-required-2E7D32)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## 这是什么

视频文件是编码器做的一连串决定的记录：每帧分了多少比特、哪些是关键帧、量化器花在哪、
块从哪里预测。光看画面时这些决定是隐形的，而画面出问题时恰恰要看它们。

QtVideoAnalyzer 让它们可见。选一个文件，它分阶段解码——容器、包表、图像类型、量化器、
运动——每出一阶段就发布一阶段。包表一到即可打开播放，深分析在后台继续，曲线在下面
一边跑一边填。

一切经由 ffmpeg，只要 ffmpeg 能读的文件它都能分析。无私有绑定：PySide6 + numpy +
opencv（运动回退）+ ffmpeg/ffprobe 子进程。

---

## 功能

| | |
|---|---|
| **六联同步图** | 码率、图像类型、QP、运动、GOP 位置、重排距离，同一时间轴、同一 playhead |
| **拖拽=预览，松手=跳转** | 拖动只显示胶片缩略图，松手才做一次真 seek，playhead 不跟你打架 |
| **帧精确播放** | ffmpeg `rawvideo` 管道解进 `QImage`：逐帧步进，不受媒体控件限制 |
| **Codec 层自动跟随** | 按文件格式自动切覆盖层：AVC 分区、H.263 GOB、HEVC CTU 四叉树、VVC MTT、AVS3 LCU、VP 分段、AV1 超块、ProRes slice、Theora 点阵、AltRef 星 |
| **CodecDNA 面板** | 家族徽章、3 条优势、mini GOP 条（I 红/P 蓝/B 绿/AltRef 金）、各编码“去哪看”提示 |
| **B/I/P 图像类型分析** | 13 种格式的计数、字节占比、平均大小/QP/运动、GOP 结构串 |
| **分析覆盖层** | 运动矢量、宏块网格、块噪声点，直接画在画面上 |
| **示例片+导入** | 50+ 内置示例一键切换，或导入自己的视频（对话框/拖拽） |
| **范围分析** | 标一段或手输起止，只重解码这一段；时间轴跟随范围走 |
| **实时进度** | 状态栏+进度条显示阶段与百分比，QP/motion 解码看得见 |
| **可停可续** | 语义与原版一致：范围可累积、分析可取消且保留已有结果 |

### 六联图

| 行 | 内容 |
|---|---|
| **BITRATE** | 每帧比特数，log₂ 刻度 + 全片均值线；关键帧更亮 |
| **FRAME TYPE** | I / P / B 各一条泳道，关键帧画竖线 |
| **QP** | 量化器：均值连线 + 每帧 min–max 带；非解码器精确值标 `(est.)` |
| **MOTION** | 平均运动矢量长度，前向/后向占比 |
| **GOP** | 距上一个关键帧多少帧——每个 GOP 的形状 |
| **REORDER** | PTS−DTS 换算成帧数，基线标 corrupt / discard / 交错 / repeat 旗 |

### 编码覆盖（13 种）

| 家族 | 格式 | 说明 |
|---|---|---|
| MPEG | AVC（H.264）、HEVC（H.265）、MPEG-2、H.263 | 原生 `-debug qp` 出类型+QP；AVC/HEVC/MPEG-2 有 B 帧 |
| 开放 | Theora、AV1、VP6、VP8、VP9、AV2（描述性） | 估计分支兜底；VP8/VP9 用 AltRef 星；AV2 尚无编码器 |
| 次世代 | VVC（H.266）、AVS3 | VVC 原生解析；AVS3 用 `uavs3dec` 解码 + H.264 代理播放 |
| 中间码 | ProRes（6 档全） | 全 I 帧：I 全红排、GOP/REORDER 拉平、码率高而平 |

各格式的 profile / 采样（420/422/444）/ 码率控制（CRF/CQP/CBR/ABR/VBR）矩阵与微调指南在
`docs/rates/<格式>.md`；各家族算法要点在 `docs/codec-*.md`。

---

## 分析管线

每阶段一出结果就发布，所以文件还没分析完窗口就已经可用。

| 阶段 | 内容 |
|---|---|
| 1. Probe | `ffprobe -show_format -show_streams`：容器、编码、分辨率、帧率、色彩标记、SAR/DAR、音频布局 |
| 2. 包表扫描 | `ffprobe -show_packets`：不解码读包表——大小、pts、dts、key / discard / corrupt 旗；无时间戳裸流（`.bit`）按 `i/fps` 合成 |
| 3. 图像类型 + QP | 一次 `ffmpeg -debug qp` 同时出类型与真实宏块 QP（AVC/MPEG-2/H.263）；其余用 `ffprobe -show_frames` 帧头；再没有就按 bits-per-pixel 估计并标 `(est.)`；AVS3 用 `uavs3dec` 帧日志 |
| 4. 运动 | 解码器给了 `-debug mv` 就用真矢量，否则内置 Farneback+块匹配回退（320px 灰度流；AVS3 像素来自 `uavs3dec`） |

3、4 并行跑，各自边出边发布，曲线边分析边填。取消是静默的：被顶掉的旧任务安静退出，不弹错。

ffmpeg 解不了的格式（AVS3）会自动建 H.264 代理播放（`tools/samples/.avs3proxy/`，不入仓），
所有分析始终用原流。

---

## 环境要求

* **Windows 10 / 11、macOS 12+ 或桌面 Linux**（x64 或 arm64）
* **Python 3.10+**，`pip install -r requirements.txt`（PySide6、numpy、opencv-python-headless）
* **ffmpeg 与 ffprobe**（任意近期构建）：按 `FFMPEG_HOME`、`tools/ffmpeg/bin/`、`PATH`、常见安装位顺序找
* **uavs3dec**（可选，仅 AVS3）：放 `tools/avs3bin/uavs3dec`，见
  [uavs3d](https://github.com/uavs3/uavs3d)；没有它 AVS3 照样分析，只是播放要等代理

---

## 上手

```bash
git clone https://github.com/Bemly/QtVideoAnalyzer.git
cd QtVideoAnalyzer
pip install -r requirements.txt
python -m qt_analyzer.main [视频]   # 不带参数弹文件框；也支持往窗口拖文件
```

一键自检（无界面也可跑）：

```bash
QT_QPA_PLATFORM=offscreen python -m qt_analyzer.main --selftest
python tests/test_codecs.py
```

示例片（只记来源地址，仓库不存二进制，`tools/samples/` 已忽略）：

```bash
cat docs/samples/README.md          # 来源总表 + 许可
./tools/make_test_videos.sh         # 生成核心 7 段测试片
./tools/retranscode_from_sintel.sh  # 从 Sintel 预告片重转 profile/RC 变体
```

---

## 操作

| 按键 | 作用 |
|---|---|
| `Ctrl+O` | 打开视频（也可拖文件进窗口，或命令行传参） |
| `Space` | 播放 / 暂停 |
| `←` / `→` | 上一帧 / 下一帧 |
| `Ctrl+←` / `Ctrl+→` | 上/下一个关键帧 |
| `Esc` | 退出全屏 |

| 鼠标 | 作用 |
|---|---|
| 点曲线或时间轴 | 跳到点击处 |
| 拖曲线或时间轴 |  scrub——缩略图跟光标走，松手做一次真跳转 |
| 时间轴右键 | 标分析范围；起/止框手输更精确，点「分析范围」开跑 |
| 曲线/时间轴滚轮 | 以光标为中心缩放 |
| 双击画面 | 全屏；再双击（或 `Esc`）回来 |

---

## 目录

```
qt_analyzer/
  main.py              入口（含 --selftest）
  main_window.py       布局、传输、scrub 状态机、范围视图、工作线程
  models.py            MediaInfo、FrameInfo、AnalysisResult（对齐 C# 模型）
  probe.py             容器/流元数据（AVS3 尺寸/帧率走 uavs3dec 补）
  packets.py           包表扫描、无时间戳裸流合成
  pipeline.py          渐进编排（probe -> 包表 -> 深分析）
  deep_qp.py           类型 + QP（原生 / 帧头 / 估计 / uavs3dec 日志）
  motion.py            运动矢量（原生 mv / Farneback 回退 / uavs3dec 像素）
  block.py             块效应/活性（覆盖层 + brain 旗）
  playback.py          rawvideo 管道引擎（可 seek + 无时间戳两模式）
  audio.py             PCM 经 QAudioSink 播放
  filmstrip.py         scrub 预览缩略图带
  graphs.py            六联同步图（press/move/release 三信号）
  video_widget.py      画面 + 覆盖层 + codec 层
  codec_insight.py     编码归一化 + CodecDNA 摘要（13 种格式）
  codec_panel.py       CodecDNA 面板
  codec_avc_h263.py / codec_hevc.py / codec_vp.py / codec_theora_av1.py
  codec_next.py（VVC/AV2）/ codec_avs3.py / codec_prores.py
  rc_<格式>.py × 13   profile/采样/码率矩阵 + recommend()
  ffmpeg_locator.py    找工具链
tools/
  make_test_videos.sh         核心 7 段（测试条配方）
  retranscode_from_sintel.sh  从真镜头重转 profile/RC 变体
  samples/                   本地片 + .avs3proxy/（不入仓）
  avs3bin/                   本地 uavs3dec（不入仓）
docs/
  codec-*.md      各家族算法要点（看什么）
  rates/<格式>.md   profile × 采样 × 码率矩阵 + 微调
  samples/        各格式来源 URL + 实测表（不存二进制）
tests/test_codecs.py  内置片的 probe/包表回归
```

## 设计说明

* **拖拽只预览，松手才跳转。** seek 要重启解码器，所以拖动只动 playhead 看缩略图，松手做一次帧精确跳转；拖拽中播放计时器暂停，绝不跟光标打架。
* **无时间戳流是一等公民。** 裸 `.bit`/Annex-B 输入按 `pts=dts=i/fps` 合成，引擎去掉 `-ss`/passthrough，按帧数跳播。
* **进度永远可见。** 深分析每段都报阶段+百分比到状态栏和 ANALYSIS 进度条；取消静默是设计如此。
* **代理绝不碰分析。** AVS3 的 H.264 代理只管让画面动起来；所有曲线、统计、覆盖层都算自原流（或其真解码）。
* **示例只记来源，不存片子。** `docs/samples/` 每段片一个 URL 或一条精确的 ffmpeg 命令；`tools/samples/` 下的东西一律不提交。

## 已知限制

* QP 只在 ffmpeg `-debug qp` 支持的编码有解码器精确值；其余是估计，界面会标。
* 内置运动估计是真块匹配，不是编码器自己的决策，平坦合成画面矢量本来就接近零。
* VP/AV1 的 alt-ref 帧报成 P（隐藏参考结构用 AltRef 星展示，不走 B 泳道）。
* AVS3 包级时间戳残缺（大量 `N/A`），GOP/reorder 行是近似的；类型与运动来自真解码。
* VVC multilayer 流能解析，但自带 ffmpeg 解码器报 `Not yet implemented`，播放需等有能力的解码构建。

## License

MIT — 见 [LICENSE](LICENSE)。原 WPF 应用版权归其作者；本 Qt 重写是独立实现，仅共享分析思路。
