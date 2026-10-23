# VP6 码率速查（profile / 采样 / RC）

> 数据模块：`qt_analyzer/rc_vp6.py`（仅标准库，无第三方依赖，永不抛错）。
> 编码器现状：本机 FFmpeg **无 VP6 编码器**（`ffmpeg -encoders | grep vp6` 无输出，
> `ffmpeg -h encoder=vp6` 报 no encoders；解码器仅 `vp6 / vp6a / vp6f`，
> 上游已移除 `vp6f` 编码器）。以下均为**文献口径**（Zencoder VP6 Settings /
> MultimediaWiki / EE Times），非本机实测；`test_vp6.flv` 缺失属预期
> （`tests/test_codecs.py` 已将其列为“无编码器则预期缺失”）。

## 1. profile 对照

| 本模块 | 上游写法 | 定位（Zencoder 原话意译） | alpha |
|---|---|---|---|
| `VP6-S` | `vp6s` | Simple：高分辨率/高码率时**降低解码复杂度**，适配弱解码机 | 无 |
| `VP6-E` | `vp6e`（默认） | Extra/通用档：常规用途默认选它 | 有（`alpha_transparency=true` 即切到 **VP6A** 编码，ffmpeg 侧由 `vp6a` 解码） |

采样：只有 **4:2:0**（`chroma_modes() -> ["420"]`，yuv420p 为主）。
容器：FLV（Flash Video，`VP6F` 四字符码）。

RC 模式（`rc_modes() -> ["VBR", "CBR"]`）：

| 模式 | 遍数 | 文献要点 |
|---|---|---|
| **VBR**（推荐落盘） | 两遍 | `vp6_2pass_min_section` 默认 **40%**（再简单的段也不低于 40% 目标码率，防难段偷光简单段的码）；`vp6_2pass_max_section` 默认 **400%**（单段峰值上限 4x） |
| **CBR**（仅推流） | 单遍 | `constant_bitrate`：Zencoder 明确“**同码率明显不如 VBR，非必须不用**”；需配 `video_bitrate`（不能走 quality 自选）；`vp6_stream_prebuffer`（默认 6s）/ `vp6_stream_max_buffer` 只在 CBR 有效；**CBR 下 temporal resampling 被强制打开** |

bpp 经验式（Zencoder 文献，可直接验算）：

```text
bpp = video_bitrate_bps / (width * height * fps)
bpp < 0.07 即默认打开 temporal resampling（低 bpp 靠掉帧保码率）
例：600kbps @ 640x480x30 = 600000 / 9216000 ≈ 0.065 -> 开
```

`vp6_undershoot_pct` 默认 90（目标压低一档留缓冲给难段）；
`vp6_temporal_down_watermark` 默认 20（buffer 剩余低于此百分比才允许掉帧）；
压缩档 `vp6_compression_mode`: `good`（速度质量均衡）/ `best`（`speed` 1~2 时用，更慢更好压）。

Golden 帧与码率：VP6 只有 **I/P，无 B 帧**，参考结构是**单 Golden**
（关键帧即 Golden，`codec_vp.describe("vp6")` 的 `key=Golden`）。
Golden/关键帧是帧内编码的大包 → **码率峰即关键帧**；
Golden 间隔拉长省码率但伤 seek/伤错误恢复，CBR 强约束下频繁 Golden 会顶穿 buffer
（靠 temporal resampling 掉帧兜底）。

## 2. 码率速查（30fps，`recommend()` 同公式：streaming bpp 0.10 / vod bpp 0.085）

| 分辨率 | streaming(CBR 单遍) | vod(VBR 两遍) | 落位 |
|---|---|---|---|
| 320x240 | ~230kbps | ~196kbps | 低于 Flash 口径，下限档 |
| 640x480 | ~922kbps | ~783kbps | **Flash 主力 400~1500kbps 内** |
| 720x480 | ~1037kbps | ~881kbps | 同上 |
| 1280x720 | ~2765kbps（→ profile 切 VP6-S） | ~2350kbps（→ VP6-S） | 高清档，实际按 VP6-S 低复杂度解码 |
| 1920x1080 | ~6221kbps（→ VP6-S） | ~5288kbps（→ VP6-S） | 超出 Flash 口径，仅归档参考 |

```python
from qt_analyzer.rc_vp6 import profiles, chroma_modes, rc_modes, recommend, paint_hint
profiles()      # ["VP6-S", "VP6-E"]
chroma_modes()  # ["420"]
rc_modes()      # ["VBR", "CBR"]
recommend(640, 480, 30)                    # streaming/CBR 单遍，VP6-E，~922kbps
recommend(640, 480, 30, use="vod")         # VBR 两遍，~783kbps
recommend(640, 480, 30, use="alpha")       # VP6-E（VP6A 路径），VBR 两遍
recommend(1280, 720, 30)                   # 高像素 -> VP6-S
paint_hint()    # "VP6：IPP 节奏 …"
```

`recommend()` 输入非法（负数/0/字符串/None/NaN）一律钳制回退，永不抛错；
`use` 未知取值回退 `streaming`；`golden_interval ≈ 2s`（`fps*2`，钳制 30~300）。

## 3. 本工具联动

1. **IPP 节奏**：`codec_vp.describe("vp6")` → `无B帧：只有 I/P`；
   `altref_markers(frames, codec="vp6")` 只返回 `key` 标记（不做 P 大包判定，
   VP6 无 AltRef/compound——与 vp8/vp9 对比看）。
2. **码率峰即关键帧**：VP6 下 BITRATE 图的高柱 ≈ `key_frame`（= Golden），
   不像 vp8/vp9 那样还叠一层周期性 AltRef 大 P 包；悬停看 SIZE/BITRATE 验证，
   峰位应与 GOP 条的 I 位对齐。
3. **REORDER 平坦**：无 B 帧 → `reorder_delta = pts-dts ≈ 0` 全片贴零线。
4. **覆盖层**：`segmentation_overlay(w, h, frame, "vp6")` 全 `seg0`（不分段，
   16 网格，640x360 下 920 块）——见 `docs/codec-vp.md §2.4`。

## 4. 复现（终端证据）

```bash
ffmpeg -hide_banner -encoders 2>&1 | grep -i vp6; echo "EXIT:$?"
# 预期：无输出，EXIT:1（无编码器）；解码器侧见 vp6/vp6a/vp6f
ffmpeg -hide_banner -decoders 2>&1 | grep -i vp6
python3 -c "from qt_analyzer.rc_vp6 import recommend; print(recommend(640,480,30))"
```

来源：Zencoder《VP6 Settings》（`vp6_profile / constant_bitrate / alpha_transparency /
vp6_2pass_min|max_section / vp6_temporal_resampling(bpp<0.07) / undershoot_pct(90) /
stream_prebuffer(6)》`；MultimediaWiki《On2 VP6》；
EE Times《The On2 VP6 codec: how it works》。
