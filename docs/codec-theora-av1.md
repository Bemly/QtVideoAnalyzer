# Theora × AV1：最老开放格式 vs 最新开放格式

算法可视化模块：`qt_analyzer/codec_theora_av1.py`（仅 PySide6 + numpy + 标准库）。
Theora 无测试片（本机 ffmpeg 9 无 `libtheora` 编码器），overlay 用
`test_vp8.webm` 代跑——同为**无 B 帧 + 小块风格**（VP8 16x16 宏块 / Theora 16x16
宏块 + 8x8 DCT），以下标 ★ 处注明代跑。

## 1. 两端对比（一行一特性）

| | Theora（最老开放，2004） | AV1（最新开放，2018） |
|---|---|---|
| 血统 | VP3：On2 VP3.2 → Xiph | VP9/VP10 系：Daala/Thor 合流 → AOM |
| 变换 | 前向 DCT 8x8 | 4x4~64x64 DCT/DST/ADST/identity 组合 |
| 分块 | 固定 16x16 宏块（内含 8x8 系数块） | SB 128x128 → 递归 4 分 + 矩形/AB，最小 4x4 |
| B 帧 | 无（I/P 而已） | 名义无：Key/Inter/Alt-Ref，ffprobe 全报 P（B 恒 0 正常） |
| 容器 | Ogg 映射（.ogv） | mp4/webm/ivf（测试片 mp4 + libsvtav1） |
| 量化 | 自适应：逐帧 Q 索引×(DC/AC 分开步长)，见 `theora_qmatrix_note()` | Q 索引 0~255，残差量化后仍保主观细节 |
| 环路滤波 | 无标准化环路滤波（块边界原样保留） | CDEF + LoopRestoration（边界抹柔），见 `obmc_vs_cdef()` |
| 位深 / 并行 | 8bit / 基本无帧内并行 | 8/10/12bit / tile + row-mt |
| 胶片颗粒 | 无（颗粒只能进残差） | 帧头参数表 + 解码端合成，**不占残差码率**，见 `grain_table_note()` |
| 专利 | VP3 开放 + Xiph 免版税 | AOM 专利池免版税 |
| 本工具 QP/MV | ✘/✘（`-debug qp/mv` 无输出，走 bpp 估计 + Farneback 估计） | ✘/✘（同左） |
| overlay | ★ `theora-dots`：8x8 点阵（block-noise 点风格） | `av1-sb`：128 网格，I 整块 / P 按 motion 细分 128→64→32 |
| brain 阈值 | **1.12**（收紧：块效应重） | **1.30**（放宽：CDEF 后边界柔；默认回退 1.18 居中） |

## 2. 在本工具看三数（同片源 `testsrc2` + 红闪，640x360，不跨片比绝对值）

| 读法 | AV1（`test_av1.mp4` 实测，I=5/P=145/B=0） | Theora（★`test_vp8.webm` 代跑，I=7/P=143/B=0） |
|---|---|---|
| QP 带宽窄程度 | 帧间 band 49.86（CRF 大小帧方差经 bpp 估计放大；**估计值，非编码器真 QP**），帧内 spread 均值 10.9（钳位所致，名义窗口 I=22/P=18）→ “CDEF 后 QP 带更平”指真机行为，本工具只看台阶形状：I 一档 / P 一档 | ★帧间 band 9.47（CBR 大小均匀），帧内 spread 均值 13.9 → 台阶状平台更典型（I/P 各一档、帧内无抖动），符合 `theora_qmatrix_note()` |
| MOTION 均值 | 1.711（max 48.22，红闪帧） | ★1.547（max 46.01，同场景）→ 同运动下均值接近，AV1 复合预测不抬均值 |
| block-noise 密度 | 实解帧 blockiness@8=**2.160**：theora 阈值判 brain，av1 阈值亦判 brain（`testsrc2` 合成锐边，149/150 帧 @1.18 皆 brain——这是片源特性，非编码器故障） | ★实解帧 blockiness@8=**2.111**，148/150 帧 @1.18；theora 视角 1.12 下更敏感，多出的即“重块效应”档 |

SB 数学（与帧内容无关）：640x360/128 → **5x3=15**（I 帧 overlay 恰 15 块）；
P 帧平均 90.4 块、细分率 5.026，最热 P（idx=114）81 块、率 4.400。
Theora 点阵：640x360/8 → **80x45=3600** 点（帧类型无关，I/P 同数）。

正确读法（grain）：BITRATE 低但主观细节多时，先想 grain 合成——颗粒由帧头
参数表在 CDEF/LoopRestore **之后**补回，不占残差码率（见 `grain_table_note()`），
不要误判为“抹平”或估计错误；本工具 ffprobe 读不到 grain 表。

## 3. 复现

```bash
python3 tests/test_codecs.py   # I/P/B 分布（av1: 5/145/0，vp8: 7/143/0）
# 全链 + overlay（见本文件第 2 节数字来源）：
python3 -c "import sys; sys.path.insert(0,'.'); from qt_analyzer.pipeline import run_analysis; ..."
QT_QPA_PLATFORM=offscreen python3 -m qt_analyzer.main --selftest  # 不碰 overlay（合成数据）
```

终端输出（粘贴）：

```text
[av1] tools/samples/test_av1.mp4: 640x360 codec=av1 n=150 I=5 P=145 B=0 qp_est=True mot_est=True
  QP: avg=25.60 band=49.86 intraspread_mean=10.9 | MOTION: avg=1.711 max=48.22 | brain=149/150@1.18
[vp8→theora代跑] tools/samples/test_vp8.webm: 640x360 codec=vp8 n=150 I=7 P=143 B=0 qp_est=True mot_est=True
  QP: avg=3.88 band=9.47 intraspread_mean=13.9 | MOTION: avg=1.547 max=46.01 | brain=148/150@1.18
SB 640x360/128 -> 5 x 3 = 15
theora 640x360/8 -> 80 x 45 = 3600
[paint] av1 boxes=15 theora dots~3600->drawn nonzero=True
SELFTEST PASS
```
