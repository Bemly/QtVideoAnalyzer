# AVS3 (GB/T 33475.2) —— 国标广播编码

第二代中国广播标准（AVS3-P2，HPM 参考软件），定位 4K/8K + HDR。
本机 brew ffmpeg 9.0.2 只有 AVS1（cavs）解码、无 AVS3 编解码，
故无本地测试片；overlay 与 describe 照常可用，全链用 hevc 代跑。

## 三板斧

1. **LCU 128 + QT/BTT 多叉树** —— 128×128 最大块，四叉+二叉/三叉混合划分，
   CU/PU/TU 统一，大平坦区一格吞下，纹理区碎到 16。
2. **运动工具箱** —— Affine、UMVE、HMVP、IBC：相机变焦/屏幕内容/滚屏字幕
   都有专用模式；B 帧双向省码率。
3. **三级环路** —— DBF + SAO + ALF/CCALF，振铃与 banding 比 AVC 轻得多，
   brain 阈值取 1.22（AVC 1.18 / HEVC 1.25 之间）。

## 在本工具看什么

| 看点 | 操作 |
|---|---|
| GOP 条 IBB 节奏 | 有 B 即 AVS3 真身（与 ProRes 全 I 正好两端对照） |
| AVS3 LCU 层 | 128 网格：I 浅（蓝/绿大块）、P/B 深（橙/红碎块） |
| QP 行 | I<P<B 阶梯 + band 窄 = 率失真优 |
| REORDER 锯齿 | 有 B 即有锯齿，幅度看重排深度 |

## 复现（hevc 代跑，帧头解析路径相同）

```bash
python3 -c "
from qt_analyzer.probe import probe
from qt_analyzer.packets import scan
from qt_analyzer.models import AnalysisResult
from qt_analyzer import codec_avs3 as A
m = probe('tools/samples/test_hevc.mp4')
r = AnalysisResult(media=m); r.frames.extend(scan(m.file_path, m.fps, m.nb_frames))
print(A.describe()['strengths'][0])
print('lcu blocks:', len(A.lcu_overlay(640, 360, r.frames[3])))
print('arcs:', A.reference_arcs(r.frames)[:4])
"
```
