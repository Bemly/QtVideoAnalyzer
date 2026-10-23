# AVC/H.264 profile / 采样 / 码率控制速查

数据模块: `qt_analyzer/rc_avc.py`（纯标准库，永不抛错）。
口径来源：本机 `ffmpeg -h encoder=libx264` / `-h encoder=mpeg4` +
`x264 --fullhelp`（ffmpeg 9.0.2，x264 core:165 r3222）。

## 0. 本机终端证据（关键行原文）

```text
$ ffmpeg -hide_banner -h encoder=libx264
Encoder libx264 [libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10]:
    Supported pixel formats: yuv420p yuvj420p yuv422p yuvj422p yuv444p yuvj444p nv12 nv16 nv21 yuv420p10le yuv422p10le yuv444p10le nv20le gray gray10le
  -preset  <string>  Set the encoding preset (cf. x264 --fullhelp) (default "medium")
  -tune    <string>  Tune the encoding params (cf. x264 --fullhelp)
  -profile <string>  Set profile restrictions (cf. x264 --fullhelp)
  -level   <string>  Specify level (as defined by Annex A)
  -crf     <float>   Select the quality for constant quality mode (from -1 to FLT_MAX) (default -1)
  -qp      <int>     Constant quantization parameter rate control method (from -1 to INT_MAX) (default -1)
  -nal-hrd <int>     Signal HRD information (requires vbv-bufsize; cbr not allowed in .mp4)

$ ffmpeg -hide_banner -h encoder=mpeg4
Encoder mpeg4 [MPEG-4 part 2]:
    Supported pixel formats: yuv420p        # <-- 注意: mpeg4 是 MPEG-4 Part 2，不是 AVC，本机仅 420
```

```text
$ ffmpeg -hide_banner -h full | grep -E "maxrate|bufsize|minrate"
  -maxrate  <int64>  maximum bitrate (in bits/s). Used for VBV together with bufsize. (default 0)
  -minrate  <int64>  minimum bitrate (in bits/s). Most useful in setting up a CBR encode.
  -bufsize  <int>    set ratecontrol buffer size (in bits)

$ x264 --fullhelp  (profile 节原文)
  --profile <string>  Force the limits of an H.264 profile
    - baseline:  --no-8x8dct --bframes 0 --no-cabac --cqm flat --weightp 0 / No interlaced / No lossless
    - main:      --no-8x8dct --cqm flat / No lossless
    - high:      No lossless
    - high10:    No lossless / Support for bit depth 8-10
    - high422:   No lossless / Support 8-10bit / 4:2:0/4:2:2 chroma
    - high444:   Support 8-10bit / 4:2:0/4:2:2/4:4:4 chroma
  Output bit depth: 8/10     # <-- 本机构建无 12-bit
```

## 1. profile × chroma/位深矩阵

| profile | 采样 | 位深（规范 / 本机 x264） | 8x8DCT | CABAC | B 帧 | 本机可用 | 典型用途 |
|---|---|---|---|---|---|---|---|
| Baseline | 420 | 8 / 8 | — | — | —（`--bframes 0`） | `--profile baseline` ✅ | 可视电话/旧移动端 |
| Constrained Baseline | 420 | 8 / 8 | — | — | — | ✅（baseline 子集） | WebRTC/兼容档 |
| Main | 420 | 8 / 8 | — | ✅ | ✅ | `--profile main` ✅ | 广播/DVD 时代主流 |
| Extended | 420 | 8 / 8 | — | ✅ | ✅（+SI/SP、容错） | 规范有，x264 无此 `--profile` | 流媒体容错（实际少用） |
| High | 420 | 8 / 8 | ✅ | ✅ | ✅ | `--profile high` ✅（默认档） | **存档/点播默认** |
| High10 | 420 | 8–10 / 8–10 | ✅ | ✅ | ✅ | `--profile high10` ✅（需 10-bit 构建） | 10-bit 存档/动漫压制 |
| High422 | 420/422 | 8–10 / 8–10 | ✅ | ✅ | ✅ | `--profile high422` ✅ | 演播室/采集 Intra |
| High444 | 420/422/444 | 8–10（规范至 14) / 8–10 | ✅ | ✅ | ✅ | `--profile high444` ✅ | 高质量 CG/无损附近 |
| High444 Predictive | 420/422/444 | 8–14 / 8–10（本机封顶 10） | ✅ | ✅ | ✅（+预测增强/无损） | 规范名；x264 按 high444 处理 | 无损/专业制作 |

注：

- 本机 `libx264` 像素格式：`yuv420p/422p/444p` + `yuv420p10le/422p10le/444p10le` + `gray(10le)`；**无 12-bit**（`--output-depth` 仅 8/10）。
- `mpeg4` 编码器是 MPEG-4 Part 2（ASP），不是 AVC，仅 `yuv420p`，勿与 libx264 混淆。

## 2. levels 简表（Annex A，主流档）

Max 码率为 Baseline/Main 口径；High 系列约 ×1.25。Max FS 单位：宏块（16x16）。

| level | Max FS（MB数） | Max MB/s | Max 码率 | 够用的典型规格 |
|---|---|---|---|---|
| 3.0 | 1620 | 40500 | 10 Mbps | 720x480@30 / 720p@30 入门 |
| 3.1 | 3600 | 108000 | 14 Mbps | **720p@30**（3600=1280x720 正好顶格） |
| 4.0 | 8192 | 245760 | 20 Mbps | **1080p@30**（8160 MBs） |
| 4.1 | 8192 | 245760 | 50 Mbps | 1080p@60 / 高码率 1080p |
| 5.0 | 22080 | 589824 | 135 Mbps | 1440p / 4K@30 入门 |
| 5.1 | 36864 | 983040 | 240 Mbps | **4K@30**（32400 MBs） |

`recommend()` 按分辨率自动选 level：360p→3.0，720p→3.1，1080p→4.0，1440p→5.0，4K→5.1。

## 3. RC 模式对照（x264 实现）

| 模式 | ffmpeg/x264 开关 | 码率行为 | 适用场景 | 命令片段 |
|---|---|---|---|---|
| CRF（质量恒定） | `-crf 18~23`（默认 23，越小越好） | VBR，按内容分配 bits | **存档/点播默认** | `ffmpeg -i in.mp4 -c:v libx264 -preset slow -crf 21 out.mp4` |
| CQP（量化恒定） | `-qp N`（0=无损，x264 `--qp`） | 无自适应，每 MB 同 QP | 算法对比/压测 | `ffmpeg -i in.mp4 -c:v libx264 -qp 22 out.mp4` |
| ABR（平均码率，2-pass） | `-b:v X -pass 1/2` | 体积可预期，两遍分配 | 点播转码/定体积 | `ffmpeg -i in.mp4 -c:v libx264 -b:v 10000k -pass 2 out.mp4` |
| CBR+VBV（直播封顶） | `-b:v X -maxrate X -bufsize 2X`（真 CBR 再加 `-minrate X -nal-hrd cbr`，注意 cbr 不允许进 .mp4） | 削峰填谷，延迟换平稳 | **直播/低延迟** | `ffmpeg -i in.mp4 -c:v libx264 -preset veryfast -tune zerolatency -b:v 10000k -maxrate 10000k -bufsize 20000k out.mp4` |

补充：

- `CRF+VBV`（`-crf 21 -maxrate X -bufsize 2X`）= 质量优先但封顶，点播防爆发的常用折中。
- `-crf_max`：CRF+VBV 时防止 VBV 把质量压得过低的下限。
- 通用码率三件套是**编码器无关**的 AVCodecContext 选项（`ffmpeg -h full`）：`-b/-minrate/-maxrate/-bufsize`；`-crf/-qp` 才是各编码器私有选项（libx264 有，mpeg4 无 crf）。

## 4. preset / tune 矩阵（`x264 --fullhelp` 原文口径）

preset（速度←→压缩率，默认 `medium`）：

| preset | 要点 | 适用 |
|---|---|---|
| ultrafast | 无 CABAC/去块/B 帧，`--ref 1 --subme 0` | 极速预览/连通性测试 |
| superfast / veryfast | 关 mixed-refs/mbtree，lookahead 0/10 | **直播常用 veryfast** |
| faster / fast | lookahead 20/30，ref 2 | 实时偏质量 |
| medium | 默认 | 通用 |
| slow / slower / veryslow | ref 5→16，subme 8→10，trellis 2 | **存档常用 slow** |
| placebo | bframes 16，esa/tesa 全开，returns 递减 | 压测/对比用 |

tune（按片源微调，可逗号叠加，psy 类一次只用一个）：

| tune | 要点 |
|---|---|
| film | `--deblock -1:-1 --psy-rd :0.15`，真人实拍 |
| animation | bframes+2，deblock 1:1，AQ 0.6，动漫 |
| grain | 留颗粒（no-dct-decimate，qcomp 0.8） |
| stillimage | `--aq-strength 1.2 --deblock -3:-3`，幻灯片/屏录 |
| psnr / ssim | 关 psy（`--no-psy`），纯指标对比 |
| fastdecode | 去 CABAC/去块/weightp，弱机种解码 |
| zerolatency | **无 B 帧**、无 mbtree、lookahead 0，直播低延迟 |

## 5. 码率速查（H.264 流媒体口径，30fps；60fps ×1.5）

| 规格 | 分辨率 | 直播 CBR | 存档 CRF | level |
|---|---|---|---|---|
| 360p | 640x360 | ~1 Mbps | 23 | 3.0 |
| 480p | 854x480 | ~2 Mbps | 22 | 3.0 |
| 720p | 1280x720 | ~5 Mbps | 22 | 3.1 |
| 1080p | 1920x1080 | **8~12 Mbps（中 10M）** | 21 | 4.0 |
| 1440p | 2560x1440 | ~16 Mbps | 21 | 5.0 |
| 4K | 3840x2160 | **35~45 Mbps（中 40M）** | 20 | 5.1 |

`rc_avc.recommend(1920,1080,30)` 默认返回 1080p 直播档：`bitrate_kbps=10000`，
`ffmpeg_args="ffmpeg -i in.mp4 -c:v libx264 -profile:v high -level 4.0
-pix_fmt yuv420p -preset veryfast -tune zerolatency
-b:v 10000k -maxrate 10000k -bufsize 20000k -g 60 -bf 3 out_avc.mp4"`。

## 6. 在本工具的联动（看图判 RC）

- **QP 行看 CRF 档位**：存档 CRF 片（`describe()` 口径：CABAC + 4x4 整数变换）
  同类帧 QP 方差小 → **QP 泳道带宽窄**、I<P<B 阶梯清晰 = 此 CRF 档率失真好；
  CRF 过大（≥28）则带宽变宽、台阶糊成一片。
- **BITRATE 行看 CBR 平顶**：直播 CBR+VBV 片（maxrate=bufsize/2 限幅器）
  大动态场景下 **BITRATE 泳道顶部被削平**（平顶 = 限幅器起作用），
  同时 QP 泳道在平顶处上翘（限幅靠抬 QP 实现）。
- `paint_hint()` 文案：`AVC: High@L4.0·420 8-bit·存档 CRF 18~23 /
  直播 CBR+VBV; QP 泳道带宽窄=CRF 档好, BITRATE 平顶=CBR 限幅起作用。`
