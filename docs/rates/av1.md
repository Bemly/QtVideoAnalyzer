# AV1 码率 / profile / RC 速查（libsvtav1，本机实测）

数据模块：`qt_analyzer/rc_av1.py`（仅标准库，永不抛错）：
`profiles()` / `chroma_modes()` / `rc_modes()` / `recommend(w,h,fps,use)` / `paint_hint()`。
算法侧（SB 覆盖层 / grain 说明）：`qt_analyzer/codec_theora_av1.py`。

## 1. 本机可用性（ffmpeg 9.0.2 + SVT-AV1 v4.2.0，Apple Silicon）

| 项 | 实测结论 |
|---|---|
| `libsvtav1` | ✔ 有（`--enable-libsvtav1`，`Encoder libsvtav1 [SVT-AV1…]`） |
| `libaom-av1` | ✘ 无（`Codec 'libaom-av1' is not recognized`） |
| wrapper 暴露选项 | 仅 5 项：`-preset(-2~13,默认-2)` / `-crf(0~63)` / `-qp(0~63)` / `-svtav1-params` / `-dolbyvision`；RC 其余靠通用 `-b:v/-maxrate/-bufsize` + `SvtAv1EncApp --help` 的 `--rc/--tbr/--crf/--cqp/--mbr` 语义 |
| wrapper 像素格式 | 仅 `yuv420p` + `yuv420p10le`；`-pix_fmt yuv444p` 会被自动降采样（`Incompatible pixel format … auto-selecting yuv420p`），**不是真 444 编码**；`SvtAv1EncApp` 明示 `color-format … only yuv420 is supported at this time` |
| 解码 | `libdav1d` + 原生 `av1` 解码器；容器 `mp4/webm/ivf/matroska` 均可 |

## 2. profile × chroma × bitdepth 矩阵（AV1 规范；`--profile 0/1/2`）

| profile | 420 8bit | 420 10bit | 420 12bit | 422 全位深 | 444 8/10bit | 444 12bit |
|---|---|---|---|---|---|---|
| Main (0) | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| High (1) | ✔ | ✔ | ✔ | ✘ | ✔ | ✔ |
| Professional (2) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

`chroma_modes()` 返回 9 种 `420/422/444 × 8/10/12bit` 规范组合；**本机链路实际只能编其中 2 种**
（`420/8bit=yuv420p`、`420/10bit=yuv420p10le`），其余是规范能力、待编码器支持。
HDR 链用 10bit（`yuv420p10le`）；8K/HDR 高端看 Professional，但本机 SVT 走不到。

level：`--level 0`=按输入自动检测；范围 **2.0–7.3**（A.3），决定最大分辨率/码率/DPB，
点播一般不用手设，超限时编码器报错再显式升 level。

## 3. preset / RC / tune 对照

### 3a. preset 速度档（数字越大越快，画质递减）

| preset | 定位 | 建议用途 |
|---|---|---|
| 0–3 | 最慢归档档（边际收益小，机器烧） | 母带/一次性压制 |
| **4–6** | 慢速高质量（`recommend(use="vod")`=5） | VOD 点播/存档 |
| **7–9** | 均衡（app 默认 **8**，测试片即 preset 8；`recommend()` 默认 8） | 默认点播/`streaming` |
| 10–12 | 快速（`recommend(use="live")`=10；M10+ 报 `meant for automation tooling`，可能有可见 artifact） | 直播/低延迟 |
| 13 | 最快（单帧 smoke 用过，可出流） | 预览/冒烟测试 |
| -2/-1 | ffmpeg wrapper 默认（-2=未设）/ SVT 调试档 | 别显式用 -1 |

ffmpeg wrapper 的 `-preset` 直接透给 SVT `--preset`；tune 经 `-svtav1-params tune=N`：
`0=VQ（人眼默认推荐）/ 1=PSNR（app 默认）/ 2=SSIM / 3=IQ / 4=MS_SSIM / 5=VMAF`。
ffmpeg 默认 tune=PSNR（实测 `preset / tune … : 8 / PSNR`），点播主观向建议显式 `tune=0`。

### 3b. RC（`SvtAv1EncApp --rc` 口径 → ffmpeg 映射，本机逐条验证）

| SVT RC | 语义 | ffmpeg 写法 | 本机验证 |
|---|---|---|---|
| `0` CRF（默认，`--crf 35`，可 1–70/0.25 步进；ffmpeg `-crf 0–63` 取整） | 单遍恒质量，点播默认 | `-c:v libsvtav1 -preset 8 -crf 32` | ✔ `BRC mode … : CRF / 32.00` |
| `0` CQP 变体（`--aq-mode 0` + `--cqp`） | 恒定量化，波动大 | `-qp N`（wrapper 直透） | 参数接受（画质研究用） |
| `1` VBR（`--tbr kbps`） | 单遍目标码率 | `-b:v 800k`（即 VBR，无需 maxrate） | ✔ `BRC mode … : VBR / 800` |
| capped CRF（`--mbr` 封顶） | CRF + 峰值钳 | `-crf 32 -b:v 5M` 组合（wrapper 把 `b:v` 当上限提示） | 接受；要严格封顶用 App |
| `2` CBR（`--tbr` + `--buf-sz*`） | 恒码率直播 | `-b:v X -maxrate X -bufsize X -svtav1-params pred-struct=1:rc=2` | ✔ low-delay 下 `CBR / 800`；**随机接入默认结构下直接失败**：`CBR Rate control is currently not supported for RANDOM_ACCESS` |
| 2-pass VBR（`--passes 2 --pass 1/2 --stats`） | 二遍压制 | 仅 `SvtAv1EncApp`，ffmpeg wrapper 无二遍接口 | —（母带用 App） |

另：`--keyint` 默认 `-2`（≈5s 一个 GOP）；`--film-grain 0`=关，`1–50`=去噪强度
（开后经 `-svtav1-params film-grain=N[:film-grain-denoise=1]` 进帧头参数表，见 §6）。

## 4. 码率速查（SDR VOD，30fps；60p ×~1.6）

`recommend()` 按像素/秒 × bpp 梯度估算（4K+ 0.050 / 1080p+ 0.075 / 720p+ 0.090 / SD 0.110，
60p 再 ×1.6 封顶 80M），与下表典型值对齐：

| 分辨率 | AV1 典型（VBR/CBR 目标） | CRF 档（SVT，0–63/70 尺度，注意 ≠x264 的 0–51） | 同条件 HEVC 参考 |
|---|---|---|---|
| 1080p30 | **~4.7 Mbps**（区间 4–8M；`recommend(1920,1080,30)` = 4666k） | **32**（区间 28–35；`streaming`=32 / `vod`=28 / 4K 用 30） | ~6–10M |
| 1080p60 | ~7–12M | 32–34 | ~10–16M |
| 4K30 | ~12–20M | 30（大帧 bpp 效率高，CRF 可低 2 档） | ~18–30M |
| 4K60 | ~20–35M | 30–33 | ~30–50M |
| 720p30 | ~2–4M | 32–34 | ~3–6M |

相对 HEVC 省码率口径（必须带限定，否则数字无意义）：**同 VMAF（±2 分）对齐、
同片源类别、点播随机接入结构下，SVT-AV1（preset 5–8）比 x265（medium–veryslow）
省约 25–35%，中值报 ~30%**（AOM/MSU/Netflix 公开对比口径；preset 不对等时差距可放大或反转，
例 SVT preset 12 vs x265 veryslow 会抹掉优势）。`rc_av1.notes` 里即按此口径写 "~30%"。

## 5. 本工具联动（正确读法）

* **SB 层**：overlay 按 `codec_theora_av1.superblock_overlay` 画 128 SB 网格
  （I 整块 / P 按 motion 细分 128→64→32），`paint_hint()` 返回的就是这句 + 下两条。
* **grain 合成致 BITRATE 低估**：film-grain 参数在帧头 OBU（<100 字节量级），
  解码器在 CDEF + LoopRestoration **之后**合成颗粒——残差只编“去噪后的干净底”，
  所以**包字节小 + 画面糙 ≠ 抹平/估计错**，先怀疑 grain（`grain_table_note()`）。
  本工具 ffprobe 读不到 grain 表；MOTION/QP 正常但主观糙 = 典型 grain 征。
* **B 恒 0 正常**：AV1 无 B 帧概念（Key/Inter/alt-ref 全报 P），I/P/B 面板 B 列恒 0。
* **QP/MV 均为估计**：`-debug qp` 无原生输出（走 bpp 估计，标 est.），
  ffprobe `export_mvs` 对 av1 无输出（走 Farneback 回退）；CRF 大小帧方差经 bpp 放大后
  band 偏大（如测试片 band 49.86）是估计特性，不是编码器真 QP。

## 6. 复现（终端证据，本机）

```bash
ffmpeg -hide_banner -h encoder=libsvtav1        # 仅 5 选项 + 2 像素格式
ffmpeg -hide_banner -h encoder=libaom-av1       # Codec 'libaom-av1' is not recognized
ffmpeg -hide_banner -encoders | grep -i av1     # 仅 libsvtav1（编）+ libdav1d/av1（解）
SvtAv1EncApp --help | grep -E "preset|tune|rc |film-grain|color-format"  # §3 口径来源
SvtAv1EncApp --version                          # SVT-AV1 v4.2.0
python3 -c "import sys; sys.path.insert(0,'.'); from qt_analyzer.rc_av1 import *; \
  print(profiles(), chroma_modes(), rc_modes()); \
  import json; print(json.dumps(recommend(1920,1080,30), ensure_ascii=False, indent=1))"
```

关键行粘贴：

```text
Encoder libsvtav1 [SVT-AV1(Scalable Video Technology for AV1) encoder]:
    Supported pixel formats: yuv420p yuv420p10le
libsvtav1 AVOptions:
  -preset            <int>        E..V....... Encoding preset (from -2 to 13) (default -2)
  -crf               <int>        E..V....... Constant Rate Factor value (from 0 to 63) (default 0)
  -qp                <int>        E..V....... Initial Quantizer level value (from 0 to 63) (default 0)
Codec 'libaom-av1' is not recognized by FFmpeg.
      --preset                     Encoder preset, presets < 0 are for debugging. … default is 8 [-1-13]
      --rc                         Rate control mode, default is 0 [0: CRF or CQP (if `--aq-mode` is 0), 1: VBR, 2: CBR]
      --tune                       Optimize the encoding process … [0 = VQ, 1 = PSNR, 2 = SSIM, 3 = IQ, 4 = MS_SSIM, 5 = VMAF]
Svt[error]: CBR Rate control is currently not supported for RANDOM_ACCESS/ALL_INTRA, use VBR mode
Incompatible pixel format 'yuv444p' for codec 'libsvtav1', auto-selecting format 'yuv420p'
```

`recommend(1920,1080,30)` 输出（`use="streaming"` 默认）：

```text
{"use": "streaming", "mode": "CRF", "width": 1920, "height": 1080, "fps": 30.0,
 "preset": 8, "crf": 32, "bitrate_kbps": 4666, "maxrate_kbps": null,
 "pix_fmt": "yuv420p",
 "ffmpeg_args": ["-c:v", "libsvtav1", "-preset", "8", "-crf", "32", "-pix_fmt", "yuv420p"],
 "notes": "单遍 CRF 32 + preset 8（VOD/点播默认）；同画质约比 HEVC 省 ~30%（VMAF 对齐口径…）；参考目标 4666 kbps（仅估算，不钳制）。CBR 在本机 SVT 需 low-delay（见 live 用法），默认随机接入下 -maxrate 会报 CBR-not-supported。"}
```

三路冒烟（640x360 testsrc2，1s）：CRF（`-preset 8 -crf 32`）→ `BRC mode … : CRF / 32.00`；
VBR（`-b:v 800k`）→ `VBR / 800`；CBR（`+ -maxrate/-bufsize + pred-struct=1:rc=2`）→ `CBR / 800 / low delay`。
