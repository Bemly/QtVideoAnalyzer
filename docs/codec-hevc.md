# HEVC (H.265) 算法优势 · 一页纸

> 口径：同等主观质量下，HEVC 比 AVC 省约 **40%** 码率（JCT-VC 目标 ~50%，
> libx265 vs libx264 自然内容实测 ~35–45%）。本工具内所有"节省"数字均为
> 加权示意（`estimated`），不是实测值。

## 三板斧

1. **CTU 64×64 四叉树（CU/PU/TU 分离）**
   AVC 是固定 16×16 宏块；HEVC 的 CTU 64×64 可四叉树分裂为
   64/32/16/8 的 CU。CU 只定**尺寸**，PU 定**预测形状**
   （帧内 35 方向、帧间 AMP 非对称划分 2N×N/N×2N/2N×nU…抓运动边缘），
   TU 用 RQT 独立定**残差变换尺寸**（32…4）。大平坦区一个 64×64 CU
   吃掉，细节/运动边界才细分成 16/8 —— 分辨率越高省得越多。
2. **SAO 环路滤波（去块之后再修 edge/band 偏移）**
   Deblock 只能抹块边界；SAO 按 CTB 对 band/edge 两类像素加偏移，
   专杀 ringing/banding。残差更干净 → 同 QP 下块边缘更弱，
   本工具的 blockiness（brain）判定阈值可从 AVC 的 **1.18** 放宽到
   HEVC 的 **1.25**（见 `codec_hevc.sao_note()`）。
3. **大 GOP + 密 B（分层 B 金字塔）**
   GOP 拉长到 AVC 的 2–4 倍，一个 I 摊薄到更多帧；B 占比常 >60%
   （测试片 99/150），双向预测残差最小。I 峰尖而稀，B 排密而矮，
   平均码率被 B 海洋拉下来。

另有 **Tiles / WPP**（分块独立解码、波前行间熵状态传递）：同一码流
多核并行，不属码率三板斧但属工程三板斧之一。

## 在本工具里看 HEVC

| 看哪里 | HEVC 长什么样 | 对照 AVC |
|---|---|---|
| CTU 覆盖层 `ctu_quadtree_overlay` | I 帧大片蓝/绿（64/32），P/B 满屏橙/红碎块（16/8），`depth_color` 越深越暖 | AVC 只有 16/8 两档，颜色跳变少 |
| GOP 结构条 | `IBBB…` 长串，锯齿周期更长（GOP ~30） | GOP 短，I 出现更勤 |
| BITRATE 图 | I 峰**更尖更高**（峰/谷比大），B 排**更密更矮** | 峰群矮胖，P 占比更高 |
| B/I/P 表 | B% ~66%（99/150），`gop_efficiency` 省 ~25–30%（estimated） | B% ~59%（88/150） |
| brain 帧 | 阈值 1.25，误报更少 | 阈值 1.18 |

```python
from qt_analyzer import codec_hevc
codec_hevc.describe()            # 三板斧文字口径
codec_hevc.ctu_quadtree_overlay(640, 360, frame)  # [(x0,y0,size,depth)]
codec_hevc.depth_color(3)        # 越深越暖
codec_hevc.gop_efficiency(frames)  # B占比/平均GOP/I间隔/bits_per_GOP/节省estimated
print(codec_hevc.sao_note())     # 1.25 vs 1.18 的道理
```

模拟划分是示意（`frame.qp_avg` 做随机种子，同帧稳定），不是码流真值；
真 CTU 需解析码流，当前用" I 浅 / P、B 深"的统计规律代替。
