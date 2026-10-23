# VP9 码率控制速查（profile / 采样 / RC / 码率表）

> 数据模块：`qt_analyzer/rc_vp9.py`（仅标准库，永不抛错；接口与 `rc_vp8.py` 统一）。
> 实测：`ffmpeg 9.0.2`（`--enable-libvpx`），`ffmpeg -hide_banner -h encoder=libvpx-vp9`。
> 关联：`docs/codec-vp.md`（SuperBlock 64 / 8 段 / tile / compound AltRef 可视化），测试片
> `tools/samples/test_vp9.webm`（640x360 30fps 5s，`-g 30 -auto-alt-ref 1 -lag-in-frames 25`）。

## 1. 本机 encoder 关键行（证据）

```
Encoder libvpx-vp9 [libvpx VP9]:
    Supported pixel formats: yuv420p … yuv444p yuv420p10le … yuv444p10le … yuv420p12le … yuv444p12le …
  -lag-in-frames     <int>  … (from -1 to INT_MAX) (default -1)   # AltRef 前瞻（别名 -rc_lookahead，默认 25）
  -auto-alt-ref      <int>  … (from -1 to 6) (default -1)          # 替代参考帧（help 注“2-pass only”）
  -crf               <int>  … (from -1 to 63) (default -1)         # 恒质量 0~63（越小越好）
  -cpu-used          <int>  … (from -8 to 8) (default 1)          # 质量/速度比（常用 0~5）
  -deadline          <int>  … (default good)                      # best / good / realtime
  -tile-columns      <int>  … (from -1 to 6) (default -1)          # tile 列数 log2
  -tile-rows         <int>  … (from -1 to 2) (default -1)          # tile 行数 log2
  -row-mt            <bool> … (default auto)                      # 行级多线程（与 tile 正交）
  -aq-mode           <int>  … none / variance / complexity / cyclic / equator360
  -tune-content      <int>  … default / screen / film             # film 保颗粒
  -arnr-max-frames / -arnr-strength / -arnr-type                 # AltRef 降噪（backward/forward/centered）
```

实测 profile 自动映射（`ffprobe -show_entries stream=profile,pix_fmt`）：

| 输入 pix_fmt | 选项 | 检出 profile |
|---|---|---|
| `yuv420p` | 无 | Profile 0 |
| `yuv420p10le` | 无 | Profile 2 |
| `yuv444p` | 无 | Profile 1 |
| `yuv444p10le` | `-profile:v 3` | Profile 3 |

```python
from qt_analyzer.rc_vp9 import profiles
profiles()  # -> ["0: 8bit 4:2:0 ...", "1: ...", "2: ...", "3: ..."]
```

## 2. profile × chroma × bitdepth 矩阵

| profile | 采样 | 位深 | 常用 pix_fmt | 定位 |
|---|---|---|---|---|
| **0** | 420 | 8 | `yuv420p` | **默认/WebM SDR 主力**，本工具按此口径 |
| 1 | 444 | 8 | `yuv444p` | 高画质 archival / 屏幕内容 |
| 2 | 420 | 10（规范含 12） | `yuv420p10le` | **HDR 主力** |
| 3 | 444 | 10/12 | `yuv444p10le` / `yuv444p12le` | 444 + 高位深 |

```python
chroma_modes()  # -> ["420: 8bit -> profile 0 / ...", "444: 8bit -> profile 1 / ..."]
```

## 3. RC 对照（CQ / VBR / CBR）

| RC | ffmpeg 映射 | pass | AltRef | tile/row-mt | 适用 |
|---|---|---|---|---|---|
| **CQ** 恒质量 | `-b:v 0 -crf 30`（0~63 越小越好；4K 可降到 15~28） | 单遍 | 开（`-lag-in-frames 25`） | 同开 | 母带/归档：码率由内容自适应 |
| **VBR** 变码率 | `-b:v T -crf 33 -maxrate 1.5T -minrate 0.5T -bufsize 2T` | **2-pass**（`-pass 1` 统计 → `-pass 2` 落盘） | **全开**（2-pass 下收益最大） | 同开 | 点播/上传：画质码率最优 |
| **CBR** 恒码率 | `-b:v T -minrate T -maxrate T -bufsize T`（buf≈1s） | 单遍 | **关**（`lag 0`，零前瞻零额外延迟） | 同开 | 直播/推流：播出端码率平稳 |

```python
rc_modes()  # -> ["CQ", "VBR", "CBR"]
```

### 3.1 auto-alt-ref 对码率的影响

* 机制：滞后未来帧合成**不可见替代参考帧**（只做预测、不显示），`lag-in-frames`
  决定往前看几帧（0~25，默认 25）；`-arnr-*` 是 AltRef 的时域降噪强度/类型。
* 码率收益：开 AltRef 后中高运动段同质量可省约一成码率（libvpx 官方 VBR
  指南把 `-auto-alt-ref 1` 列为默认推荐；help 标注“2-pass only”即收益主要来自
  第二遍的参考分配——单遍也可用，如本工具测试片，但不如 2-pass）。
* 可观测性：开 = BITRATE 图每 ~10–30 帧一个显著高柱（`altref_markers()` 判
  `packet_size > 1.8×P均值` 为 `altref`，GOP 条金★）；关（CBR）= 无周期大包属预期。

### 3.2 tile / row-mt（并行与码率的交换）

* `-tile-columns N`（log2，0~6）：帧切 2^N 纵列独立熵编码，并行度↑但列边界
  阻断帧内预测，**同质量码率 +1~3%**；`-tile-rows M`（log2，0~2）同理（行向）。
* `-row-mt 1`：SB 行级多线程，与 tile **正交**（无码率代价，只吃 CPU）。
* `recommend()` 分档：宽 ≥3840 → 列 2 / 高 ≥2160 才开行 1；宽 ≥1280 → 列 1；
  其余 0（`-row-mt 1` 常开）。

### 3.3 速度旋钮：`-deadline` × `-cpu-used`

| deadline | 用法 | cpu-used |
|---|---|---|
| `good` | CQ/VBR 默认 | `1`（0 最慢最优；2 大提速小降质；4/5 关 RDO 大提速大降质） |
| `realtime` | CBR 推流 | `5` 起（可放宽 8 换更低占用，画质再降） |
| `best` | 封存母带 | `0`（约 good 的一半速度） |

别名：`-speed` = `-cpu-used`，`-quality` = `-deadline`。

## 4. YouTube 码率速查（上传口径，音频无关）

来源：support.google.com/youtube/answer/1722171（`recommend()` 取 SDR 列，
`fps > 30` 取高帧率列；2160p/8K 区间取中点）。

SDR：

| 档 | 标准帧率（24/25/30） | 高帧率（48/50/60） |
|---|---|---|
| 360p | 1M | 1.5M |
| 480p | 2.5M | 4M |
| 720p | 5M | 7.5M |
| **1080p** | **8M** | **12M** |
| 1440p | 16M | 24M |
| 2160p (4K) | 35–45M（取 40M） | 53–68M（取 60M） |
| 4320p (8K) | 80–160M（取 120M） | 120–240M（取 180M） |

HDR（≈ SDR ×1.25；360p/480p 官方不支持 HDR）：

| 档 | 标准帧率 | 高帧率 |
|---|---|---|
| 720p | 6.5M | 9.5M |
| 1080p | 10M | 15M |
| 1440p | 20M | 30M |
| 2160p | 44–56M（取 50M） | 66–85M（取 75M） |
| 4320p | 100–200M（取 150M） | 150–300M（取 225M） |

## 5. 本工具联动

* **AltRef 星标**：`codec_vp.altref_markers(frames)` 周期 P 大包判 `altref`，
  GOP 条金★（`key` 即 Golden：关键帧同时充当 Golden 参考，不再另发 `golden`）。
  VBR/CQ 应有 ~10–30 帧一个；CBR（AltRef 关）无★属预期。
* **compound 痕迹**：VP9 独有双参考（Last+Golden/AltRef 同块加权），
  `codec_vp.compound_note("vp9")`；motion 图上同 P 帧内绿 fwd 与品红 bwd
  矢量混现即 compound 痕迹（VP8 无 compound，以 fwd 绿为主）。
* **无 B 排校验**：VP9 全片只报 I/P（AltRef/compound 帧仍报 P），
  REORDER 图 `reorder_delta = pts-dts ≈ 0` 贴零线。
* **seg 层**：`codec_vp.segmentation_overlay(w, h, frame, "vp9")` 64 SuperBlock
  粗网格 4 色（真实 8 段，工具量化到 4 档同色显示）。

## 6. 函数速查

```python
from qt_analyzer.rc_vp9 import profiles, chroma_modes, rc_modes, recommend, paint_hint
profiles()       # ["0: 8bit 4:2:0 ...", "1: ...", "2: ...", "3: ..."]
chroma_modes()   # ["420: ...", "444: ..."]
rc_modes()       # ["CQ", "VBR", "CBR"]
recommend(1920, 1080, 30)                 # 默认 streaming -> CBR 8000k，AltRef 关
recommend(1920, 1080, 30, use="upload")   # -> VBR 2-pass（ffmpeg_pass1 + ffmpeg_args）
recommend(3840, 2160, 60, use="upload")   # -> 60000k，tile-columns 2 / tile-rows 1
recommend(1280, 720, 30, use="archive")   # -> CQ crf 30
paint_hint()     # UI 一句话：金★ + compound 绿/品红混现 + 无 B 排
```

复现：

```bash
ffmpeg -hide_banner -h encoder=libvpx-vp9 | grep -E "pixel formats|auto-alt-ref|lag-in-frames|tile-columns|tile-rows|row-mt|crf |cpu-used|deadline"
python3 -c "from qt_analyzer.rc_vp9 import recommend; import json; print(json.dumps(recommend(1920,1080,30), ensure_ascii=False, indent=1))"
python3 tests/test_codecs.py   # 含 test_vp9.webm 回归（I=5 P=145 B=0 口径）
```
