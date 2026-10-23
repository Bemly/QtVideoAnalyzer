# Apple ProRes (中间码/剪辑格式) · 一页纸

> 口径：ProRes 是**中间码**——为剪辑而生，不为分发。全 I 帧 intra-only，
> slice 并行、10bit 422、DCT + 类 JPEG 熵编码；代价是高码率
> （~150Mbps@1080p HQ 口径量级；本工具 640×360 测试片即 ~14.7Mbps，
> 约为同分辨率 AVC 的数倍）。本工具内所有数字均为实测包大小统计，
> 不是码流真值解析。

## 三板斧（为什么适合剪辑）

1. **全 I 帧 intra-only（无 P/B、无重排）**
   每一帧独立编解码，没有时间预测——任意帧都是随机访问点/剪辑点，
   解码不需要等参考帧，seek/倒放/逐帧 stepping 零延迟。代价：没有
   P/B 分摊冗余，文件天然大数倍。
2. **Slice 并行（帧内分条，多核吃满）**
   一帧按宽度切成多个 slice 独立编解码（本工具以 **8 横条**示意，
   `slice_overlay` 前 8 项），解码端各核各解一条，延迟随核数下降。
   这是"剪辑流畅"的工程来源：压缩率换并行度。
3. **10bit 422 + DCT/类 JPEG 熵编码（调色余量）**
   `yuv422p10le`：色度半分辨率但 10bit 量化，调色/抠像不断层；
   帧内空域预测后 DCT（本工具以 **16×16 网格**示意）量化，
   熵编码与 Motion-JPEG 同源——画质随码率线性涨，没有 CABAC 那类
   跨帧上下文，算力可预测。

另有 **profile 档**（本工具测试片 `prores_ks -profile:v 2 Standard`，
HQ 口径）：Proxy/LT/Standard/HQ 只是量化步长档位，算法骨架不变。

## 在本工具里看 ProRes

| 看哪里 | ProRes 长什么样 | 对照 AVC |
|---|---|---|
| FRAME TYPE 条 | **全红 I 排**：90/90 帧全 I，P=B=0 | I 稀 P/B 密，B 占比常 >50% |
| GOP 结构 | **平直 0 线**：每帧 `gop_position == 0`（`all_intra_stats` 的 `max_gop == 0`；共享 `AnalysisResult.max_gop` 有钳位下限 1，显示为 1） | GOP ~30，锯齿周期明显 |
| REORDER 图 | **零线**：`max_reorder == 0`，pts==dts，无 B 重排 | 含 B 即有重排台阶 |
| BITRATE 图 | **高而平**：均值高（~14.7Mbps@360p）、帧间波动小（CV 小），I 峰即基线 | 低而尖：I 峰高、B 谷深 |
| QP 行 | 方差小：帧内量化逐帧独立，同场景 QP 几乎一条直线 | P/B QP 随参考距离起伏 |

```python
from qt_analyzer import codec_prores
codec_prores.describe()              # 七键口径 dict
codec_prores.slice_overlay(640, 360) # [(x0,y0,x1,y1,kind,index)] 8 slice + DCT 网格
codec_prores.slice_color(3)          # 第 3 条 slice 覆盖色
codec_prores.all_intra_stats(frames) # I占比/GOP/重排/包大小 vs AVC 倍数 + verdict
```

slice/DCT 覆盖是示意（8 横条为并行解码示意、16×16 为 DCT 网格示意），
不是码流真值；真 slice 分布需解析码流，当前用"横条并行"的统计规律代替。
