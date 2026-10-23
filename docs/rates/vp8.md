# VP8 码率控制速查（profile / 采样 / RC / 码率表）

> 数据模块：`qt_analyzer/rc_vp8.py`（仅标准库，永不抛错）。
> 实测：`ffmpeg 9.0.2`（`--enable-libvpx`），`ffmpeg -hide_banner -h encoder=libvpx`。
> 关联：`docs/codec-vp.md`（Golden+AltRef / seg 可视化），测试片
> `tools/samples/test_vp8.webm`（640x360 30fps 5s，`-g 30 -auto-alt-ref 1 -lag-in-frames 25`）。

## 1. 本机 encoder 关键行（证据）

```
Encoder libvpx [libvpx VP8]:
    Supported pixel formats: yuv420p yuva420p        # 仅 420（alpha 版仍是 420 子采样）
  -lag-in-frames     <int>  … (from -1 to INT_MAX) (default -1)   # AltRef 前瞻（别名 -rc_lookahead，默认 25）
  -auto-alt-ref      <int>  … (from -1 to 2) (default -1)          # 2-pass 下开 AltRef
  -cpu-used          <int>  … (from -16 to 16) (default 1)         # 质量/速度比（VP8 有效 0~5，rt 下 0~15）
  -deadline          <int>  … (default good)                      # best / good / realtime
  -crf               <int>  … (from -1 to 63) (default -1)         # 恒质量 0~63（越小越好）
  -undershoot-pct / -overshoot-pct                               # VBR min/max section 对应旋钮
  -arnr-max-frames / -arnr-strength / -arnr-type                 # AltRef 降噪（forward/centered）
```

注意：`libvpx`（VP8）**没有 `-profile` 选项**（`grep -i profile` 零命中）——
profile 是 RFC 6386 码流头里的 2 bit，ffmpeg 侧不用传。

## 2. profile 表（0~3，WebM 用 profile 0）

| profile | 定位 | 说明 |
|---|---|---|
| 0 | **WebM 默认/推荐** | 全功能：6 抽头子像素 + 完整 in-loop 滤波；本工具按此口径 |
| 1 | 低复杂度 | 只用双线性子像素 + 简化环路滤波，低功耗设备用，质量下降 |
| 2 | 更低复杂度 | 在 1 档上继续降解码复杂度，质量再降 |
| 3 | 最低复杂度/保留 | 实现定义，兼容性最差，按 0 处理即可 |

来源：WebM《VP8 Encode Parameter Guide》`--profile (0-3: default and recommended value = 0)`；
非 0 档“为低功耗播放降复杂度，代价是编码质量”。

```python
from qt_analyzer.rc_vp8 import profiles
profiles()  # -> ["0", "1", "2", "3"]
```

## 3. 采样：仅 420

VP8 按 `420 / 8bit / 逐行` 设计（RFC 6386，最大 16383x16383）；
ffmpeg 侧只接受 `yuv420p / yuva420p`，其它 pix_fmt 直接报错。
本工具所有 `ffmpeg_args` 统一带 `-pix_fmt yuv420p`。

```python
chroma_modes()  # -> ["420"]
```

## 4. RC 对照（CQ / VBR / CBR）

| RC | ffmpeg 映射 | pass | AltRef | 适用 |
|---|---|---|---|---|
| **CQ** 恒质量 | `-b:v 0 -crf N`（N=10~12 起点，0~63 越小越好） | 单遍 | 开（`-lag-in-frames 25` 照常生效） | 母带/归档，画质优先、码率不封顶 |
| **VBR** 变码率 | `-b:v T -maxrate 1.5T -minrate 0.5T -bufsize 2T` | **2-pass**（先 `-pass 1` 再 `-pass 2`） | 开（`-lag-in-frames 25 -auto-alt-ref 1`） | 点播/文件，画质码率最优 |
| **CBR** 恒码率 | `-b:v T -minrate T -maxrate T -bufsize T`（buf≈1s） | 单遍 | **关**（`-lag-in-frames 0 -auto-alt-ref 0`，零前瞻零额外延迟） | WebRTC/低延迟直播，丢包恢复快 |

```python
rc_modes()  # -> ["CQ", "VBR", "CBR"]
```

### 4.1 速度旋钮：`-deadline` × `-cpu-used`

| deadline | cpu-used 有效范围 | 建议 |
|---|---|---|
| `good`（点播/CQ） | 0~5（0 最慢最优，接近 `--best` 两倍速；1~2 大提速小降质；4/5 关 RDO 大提速大降质） | VBR/CQ 用 `1` |
| `realtime`（直播） | 0~15，含义变为 cpu 占用目标 `100*(16-N)/16%` | CBR 用 `5`（可放宽 8~15 换更低占用） |

`ffmpeg` 里 `-speed` 是 `-cpu-used` 别名，`-quality` 是 `-deadline` 别名。

### 4.2 `-lag-in-frames` 与 AltRef 关系

* `lag-in-frames` = 为选 AltRef 往前看几帧（0~25，默认 25；ffmpeg 别名 `-rc_lookahead`）。
* AltRef 生效三条件：**2-pass** + `-auto-alt-ref 1` + `lag > 0`（滞后未来帧合成不可见参考帧，只做预测不显示）。
* 实时/CBR：`lag 0 + auto-alt-ref 0` 主动关闭（零前瞻、零额外延迟）——此时 BITRATE 图上**没有**周期 P 大包是正常的。
* 点播/VBR：`lag 25 + auto-alt-ref 1` 打开——BITRATE 图上每 ~10–30 帧一个显著高柱即 AltRef。

## 5. 码率速查（30fps 基准，60fps ×~1.5，上限 2x）

| 高度 | 档 | 实时 CBR 起点 | 点播 VBR 目标 |
|---|---|---|---|
| ≤270p | 400k | 400k | 400k |
| 360p | 800k | 800k | 800k |
| 480p | 1200k | 1200k | 1200k |
| **720p** | **2500k** | **2500k** | 2500k（max 3750 / min 1250 / buf 5000） |
| 1080p | 4500k | 4500k | 4500k |
| 1440p | 9000k | 9000k | 9000k |
| 2160p | 16000k | 16000k | 16000k |

WebRTC 经验口径：360p ~0.5–1M，720p30 ~1–2.5M，1080p30 ~2.5–4M+；
`recommend()` 取各档上限附近，保证弱网可再往下压。音频另加 Opus 32–96k。

## 6. 本工具联动

* **周期大 P = AltRef 金星标**：`codec_vp.altref_markers(frames)` 判
  `packet_size > 1.8×P均值` 为 `altref`，GOP 条按金★标出（`key` 即 Golden，
  关键帧同时充当 Golden 参考，故不再另发 `golden`）。
  CBR/实时流（AltRef 关）无金★属预期；VBR/CQ 应有 ~10–30 帧一个。
* **seg 层**：`codec_vp.segmentation_overlay(w, h, frame, "vp8")` 16x16 网格 4 色
  （蓝 seg0 QP-6 / 绿 seg1 +0 / 黄 seg2 +6 / 红 seg3 +12），右下边缘按 w/h 裁剪。
* **无 B 排校验**：VP8 全片只报 I/P（Golden/AltRef 都报 P），REORDER 图
  `reorder_delta = pts-dts ≈ 0` 贴零线；若出现 B 即容器/探针异常。

## 7. 函数速查

```python
from qt_analyzer.rc_vp8 import profiles, chroma_modes, rc_modes, recommend, paint_hint
profiles()       # ["0", "1", "2", "3"]
chroma_modes()   # ["420"]
rc_modes()       # ["CQ", "VBR", "CBR"]
recommend(1280, 720, 30)                  # 默认 realtime -> CBR 2500k
recommend(1280, 720, 30, use="vod")       # -> VBR 2-pass，AltRef 开
recommend(1920, 1080, 30, use="cq")       # -> CQ crf 10
paint_hint()     # UI 一句话：金★ + seg 四色 + 无 B 排
```

复现：

```bash
ffmpeg -hide_banner -h encoder=libvpx | grep -E "pixel formats|lag-in-frames|auto-alt-ref|cpu-used|deadline|crf"
python3 -c "from qt_analyzer.rc_vp8 import recommend; import json; print(json.dumps(recommend(1280,720,30), ensure_ascii=False, indent=1))"
python3 tests/test_codecs.py   # 含 test_vp8.webm 回归（I=7 P=143 B=0 口径）
```
