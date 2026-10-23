# TrueMotion 家族可视化 (VP6 / VP8 / VP9)

> 模块：`qt_analyzer/codec_vp.py`（仅 PySide6 + numpy + 标准库）。
> 测试片：`tools/samples/test_vp8.webm`、`test_vp9.webm`（`tools/make_test_videos.sh` 生成，
> 640x360 30fps 5s，`libvpx -g 30 -auto-alt-ref 1 -lag-in-frames 25`）。
> VP6 无开源编码器（上游已移除 `vp6f`），`test_vp6.flv` 缺失属预期——`describe("vp6")` 照常可用。

## 1. Golden / AltRef 进化史

| | VP6 (On2, ~2003, FLV) | VP8 (On2/Google, 2008, WebM) | VP9 (Google, 2013, WebM) |
|---|---|---|---|
| 参考帧 | 单 **Golden**（key=Golden：关键帧即 Golden） | **Last + Golden + AltRef** | Last + Golden + AltRef + **compound** |
| AltRef | 无 | 有：滞后未来帧合成的**不可见替代参考**，不显示，只做预测 | 有，且可参与 compound 双参考 |
| B 帧 | **无**（只有 I/P） | **无**（Golden/AltRef 都报 P） | **无**（AltRef/compound 仍报 P，`-bf 3` 实为 AltRef 机制） |
| 分段 | 无 | **4 segmentation**（seg 0..3，QP 偏移 -6/0/+6/+12） | **8 段分割**（工具覆盖层量化到 4 档同色显示） |
| 块 | 16x16 宏块 | 16x16 宏块（16 网格） | **SuperBlock 64x64**（64 粗网格 + 段色） |
| 滤波 | 简单去块 | **in-loop 滤波分段强度**（去块强度按段独立配） | 沿用分段强度，段数扩到 8 |
| 熵编码 | Huffman 系 token | **bool coder**（二元算术） | bool coder（VP9 系） |
| 并行 | 无 | 无 | **tile 并行**（多 tile 列/行并行解码） |

一句话：VP6 只有 Golden；VP8 加出“看不见的未来帧”AltRef + 4 段 + bool coder；
VP9 把块放大到 64 SuperBlock、段扩到 8、帧可切 tile，
并允许**同时踩两只参考帧**（compound，形似 B 但不重排）。

## 2. 在本工具看什么

1. **无 B 排**：B/I/P 表与 GOP 条全片只有 I/P。
   实测 `test_vp8.webm: I=7 P=143 B=0`，`test_vp9.webm: I=5 P=145 B=0`。
   `GOP STRUCTURE` 形如 `IPPP…`，场景红闪处多一个 I（scenecut）。
2. **周期性 P 大包 = AltRef**：BITRATE 图上每 ~10–30 帧一个显著高柱，
   对应 `altref_markers()` 判出的 `altref`（`packet_size > 1.8×P均值`）。
   实测 vp8 9 个、vp9 8 个（key 另计 7/5）。悬停看 SIZE/BITRATE 可验证。
3. **REORDER 平坦**：`reorder_delta = pts-dts ≈ 0` 全片贴零线——
   无 B 帧重排的直接证据（与 avc/hevc/mpeg2 的锯齿对比看）。
4. **seg 覆盖层色块**：`segmentation_overlay()` 确定性伪分段——
   vp8 按 16 网格 4 色（蓝 -6 / 绿 0 / 黄 +6 / 红 +12），
   vp9 按 64 SuperBlock 粗网格同色系，vp6 全 seg0（不分段）。
   640x360 下 vp8 920 块（40×23），vp9 60 块（10×6）。

## 3. 函数速查

```python
from qt_analyzer.codec_vp import (family_of, describe, altref_markers,
                                  segmentation_overlay, compound_note)
family_of("libvpx-vp9")          # -> "TrueMotion"
describe("vp8")["segmentation"]  # -> "4 segmentation …"
describe("vp9")["block"]         # -> "SuperBlock 64x64 …"
altref_markers(frames)                    # vp8/vp9 默认：[(idx,"key"),(idx,"altref"),…]
altref_markers(frames, codec="vp6")       # 仅 [(idx,"key"),…]
segmentation_overlay(640, 360, frame, "vp8")  # 16 网格 4 段
segmentation_overlay(640, 360, frame, "vp9")  # 64 粗网格 4 段
segmentation_overlay(640, 360, frame, "vp6")  # 全 seg0
compound_note("vp9")  # Last+Golden/AltRef 双参考；motion 图 fwd/bwd 混现即 compound 痕迹
```

`frame` 可传 `FrameInfo` / `index int` / `None`（种子 = `index + int(qp_avg)`，
同帧同编码调用结果稳定）。`altref_markers` 的帧可传 `FrameInfo` 或
`{"index","key_frame","packet_size"}` 字典，空列表返回 `[]`。

## 4. 复现

```bash
python3 tests/test_codecs.py                       # 全编码器回归（含 vp8/vp9 I/P/B）
python3 -c "
from qt_analyzer.pipeline import run_analysis
from qt_analyzer.codec_vp import altref_markers, segmentation_overlay
for f in ['tools/samples/test_vp8.webm','tools/samples/test_vp9.webm']:
    r = run_analysis(f)
    print(f, 'I=',r.i_stats.count,'P=',r.p_stats.count,'B=',r.b_stats.count)
    print(' altref:', len([m for m in altref_markers(r.frames) if m[1]=='altref']),
          'seg8:', len(segmentation_overlay(640,360,r.frames[0],'vp8')))
"
```
