# Apple ProRes profile / 采样 / 数据率 · 一页纸

> 口径: Apple ProRes White Paper + Apple Support 102207
> (1920x1080@29.97 目标码率行) + 本机 `ffmpeg 9.0.2` encoder help 实测。
> ProRes 码率是 **VBR 目标值** (随内容浮动), **无 CRF / CBR 概念** ——
> 档位即固定量化矩阵, 选 profile 就是选质量/码率。
> 可复用数据模块: `qt_analyzer/rc_prores.py` (标准库 only, 永不抛错)。

## 1. 本机可用项 (实测, ffmpeg 9.0.2, Apple Silicon)

```text
$ ffmpeg -hide_banner -h encoder=prores_ks
Encoder prores_ks [Apple ProRes (iCodec Pro)]:
    Supported pixel formats: yuv422p10le yuv444p10le yuva444p10le
  -profile  (from -1 to 5) (default auto)
     auto -1 / proxy 0 / lt 1 / standard 2 / hq 3 / 4444 4 / 4444xq 5
  -quant_mat  (from -1 to 6) (default auto)
     auto -1 / proxy 0 / lt 2 / standard 3 / hq 4 / default 6
  -bits_per_mb  (from 0 to 8192) (default 0)   # 逐宏块目标比特 (非常用微调)
  -alpha_bits   (from 0 to 16) (default 16)

$ ffmpeg -hide_banner -h encoder=prores_aw
Encoder prores_aw [Apple ProRes]:
    Supported pixel formats: yuv422p10le yuv444p10le yuva444p10le
    # 无 -profile 选项, 仅 -vendor (默认 "fmpg"); 选档用 prores_ks

$ ffmpeg -hide_banner -encoders | grep -i prores
 VF...D prores                Apple ProRes            # 原生 (无 profile 选项)
 VF...D prores_aw             Apple ProRes
 VFS... prores_ks             Apple ProRes (iCodec Pro)   # 选档用它
 V....D prores_videotoolbox   VideoToolbox ProRes Encoder
          # profile: auto -99 / proxy 0 / lt 1 / standard 2 / hq 3 / 4444 4 / xq 5
```

结论: **选档统一用 `prores_ks -profile:v <0..5>`**;
`prores_aw`/原生 `prores` 无档位选项; VideoToolbox 档位名相同
(`xq` 即 `4444xq`, auto 为 -99 按输入格式自动判定)。

## 2. profile × 目标码率官方对照表 (Mbps, VBR 目标值)

白皮书原表 (1920x1080):

| 分辨率/帧率 | Proxy | LT | Standard (422) | HQ | 4444 (no alpha) | 4444 XQ (no alpha) |
|---|---|---|---|---|---|---|
| 1920x1080 @ 29.97 | **45** | **102** | **147** | **220** | **330** | **495** (~500) |
| 1920x1080 @ 25 | **38** | **85** | **122** | **184** | **275** | **415** |
| 3840x2160 @ 29.97 (×4 像素换算) | ~180 | ~408 | ~588 | ~880 | ~1320 | ~1980 |

- 29.97 行: 白皮书柱状图 + Apple Support 102207 原值
  (XQ 文案 "approximately 500 Mbps", 表值 495)。
- 25 行: 白皮书 50i/25p 行原值 (2009 版无 XQ 列, XQ 按帧率比例
  495×25/29.97 ≈ 413, 取转引表 415)。
- 4K 行: 按像素数 ×4 线性换算 (UHD 像素正好 4×1080p),
  与白皮书 4K 表转引值 (182/410/589/884/1326/1989) 偏差 <1%,
  互相印证; 实测 VBR 会上下浮动。
- GB/小时 (小数 GB) = Mbps × 0.45: 45→~20, 147→~66, 220→~99, 330→~148。

## 3. 采样 / 位深 / alpha

| profile | chroma | 标称位深 (Apple) | ffmpeg 本机实际 |
|---|---|---|---|
| Proxy / LT / Standard / HQ | 4:2:2 | 10-bit (`yuv422p10le`) | 同左, 全支持 |
| 4444 | 4:4:4 + alpha | 12-bit video + up to 16-bit alpha | 仅 10-bit (`yuv444p10le`/`yuva444p10le`) |
| 4444 XQ | 4:4:4 + alpha | 12-bit video + up to 16-bit alpha, 动态范围数倍于 Rec.709 | 同上: **profile 标记位, 非真 12-bit**; 真 XQ 需 Apple 原生编码器 |

只有 4444 两档支持 alpha 通道 (交换动态图形/抠像用);
剪辑/调色一般选 422 家族 (HQ 为母版常用档)。

## 4. ProRes 本质: VBR-fixedQP (无 CRF/CBR)

- ProRes 编码 = 帧内空域预测 + DCT + 类 JPEG 熵编码,
  **每帧独立定量化**, 无帧间码率分配 —— 天然 VBR。
- `profile` 即固定量化矩阵档
  (`quant_mat`: proxy 0 / lt 2 / standard 3 / hq 4):
  换档 = 换量化步长, 不是换码率控制模式。
- 因此 **CRF (恒质量因子) / CBR (封顶码率) 对 ProRes 无意义**:
  要恒定码率请用 H.264/HEVC; ProRes 只问 "哪个量化档"。
- 非常用微调 (日常选档不用): `-bits_per_mb` (逐宏块目标比特),
  `-quant_mat`, `-alpha_bits` (0..16, 默认 16)。

profile fmt (ffmpeg 整数, `rc_prores._PROFILE_ID` 同值):

| 名 | prores_ks `-profile:v` | videotoolbox `-profile` | pix_fmt |
|---|---|---|---|
| proxy | 0 | 0 | yuv422p10le |
| lt | 1 | 1 | yuv422p10le |
| standard | 2 | 2 | yuv422p10le |
| hq | 3 | 3 | yuv422p10le |
| 4444 | 4 | 4 | yuva444p10le (无 alpha 可用 yuv444p10le) |
| 4444xq | 5 | 5 (`xq`) | yuva444p10le |

## 5. 本工具联动 (`rc_prores` + 图表口径)

```python
from qt_analyzer import rc_prores
rc_prores.profiles()       # ['proxy','lt','standard','hq','4444','4444xq']
rc_prores.chroma_modes()   # ['422','4444']
rc_prores.rc_modes()       # ['VBR-fixedQP']
rc_prores.recommend(1920, 1080, 25)
# {'profile':'standard','profile_id':2,'chroma':'422','pix_fmt':'yuv422p10le',
#  'rc':'VBR-fixedQP','ref_mbps_1080p29_97':147.0,'est_mbps':122.6,
#  'est_gb_per_hr':55.2,
#  'ffmpeg_args':['-c:v','prores_ks','-profile:v','2','-pix_fmt','yuv422p10le'],
#  'notes':[...]}
rc_prores.paint_hint()     # 全 I 红排 / BITRATE 高而平 / CV 小一句话
```

在本工具里看 ProRes (见 `docs/codec-prores.md`):

| 看哪里 | ProRes 长什么样 |
|---|---|
| FRAME TYPE 条 | **全红 I 排** (90/90 全 I, P=B=0) |
| GOP / REORDER | **平直 0 线 / 零线** (`max_gop==0`, `max_reorder==0`) |
| BITRATE 图 | **高而平**: 均值高 (1080p HQ ~220Mbps; 360p 测试片即 ~14.7Mbps, AVC 数倍), 帧间波动小 |
| 包大小 CV | **CV 小** (`all_intra_stats` verdict "又大又稳": 又大——vs AVC 倍数 >1, 又稳——CV<1) |
| QP 行 | 方差小近直线 (逐帧独立量化, 同场景一条线) |

复现:

```bash
ffmpeg -hide_banner -h encoder=prores_ks | grep -A9 -- "-profile"
python3 -c "from qt_analyzer.rc_prores import recommend; import json; print(json.dumps(recommend(1920,1080,25), ensure_ascii=False, indent=1))"
```
