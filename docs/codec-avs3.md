# AVS3 (GB/T 33475.2) —— 国标广播编码

第二代中国广播标准（AVS3-P2，HPM 参考软件），定位 4K/8K + HDR。
本机已有真解码器：**uavs3dec**（uavs3d, libuavs3d(8) 1.2.1_release，macOS arm64
cmake 构建，AVS3-P2 baseline），二进制在 `tools/avs3bin/`（gitignored，不入仓）；
brew ffmpeg 9.0.2 只能解析 avs3 码流（`codec_name=avs3, has_b_frames=1`）而无解码器。

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
| GOP 条 IBB 节奏 | 真流 RA GOP=64：I 后跟 63 个 B（0 P），与 ProRes 全 I 正好两端对照 |
| AVS3 LCU 层 | 128 网格：I 浅（蓝/绿大块）、B 深（橙/红碎块） |
| QP 行 | I（大包）< B 估算阶梯；估算值见下表 |
| REORDER 锯齿 | 稳态 15 帧前导（I@poc64 在 decode idx49），锯齿深且规律 |

## 实测（真流，非代跑）

解码器：<https://github.com/uavs3/uavs3d>（PKU-VCL 系；HPM 参考软件无公开
官方仓，仅散见第三方镜像，故选 uavs3d 深挖），`cmake -DCOMPILE_10BIT=0` 构建，
`file` 确认 Mach-O arm64。ffmpeg 侧结论：`ffmpeg -decoders` 仅 `avs/cavs`
（AVS1），无 `avs3` 解码（`--enable-libuavs3d` 未开）；但 ffprobe 认得出
`AVS3-P2/IEEE1857.10`、`has_b_frames=1`、`r_frame_rate=60/1`。

样片：<https://github.com/uavs3/avs3stream> `ES/City_1280x720_60_ra/test.avs3`
（2,038,889 字节，md5=`ce35f65e549f091f042f6a19b8d3da39`，与仓内 md5.txt 一致），
存于 `tools/samples/test_avs3_city.avs3`（gitignored，不入仓）。

```bash
tools/avs3bin/uavs3dec -i tools/samples/test_avs3_city.avs3 -o /tmp/city.yuv -l 2 -t 8 [-s 1]
# libuavs3d( 8): 1.2.1_release, 0e20d2c291853f196c68922a264bcd8471d75b68
# Resolution = 1280 x 720, 600 frames, ~155 fps；yuv=829440000 字节
# md5=df6fff020f1e3e906237ee278c7db069 == 官方重建 YUV（逐字节一致）
```

`qt_analyzer` 全链（probe → packets → deep_qp 含 show_frames 兜底 → motion）：

| 环节 | 结果 |
|---|---|
| probe | `codec=avs3`, `has_b_frames=1`（宽高/ffps 需解码器补：1280x720/60，见局限） |
| packets（600 包，解码序） | K 位于 decode idx 0,49,113,…,561（10 个，即 10 个 I）；306/600 包 demuxer 给不出 pts（重排症状） |
| 真实 I/P/B（解码器日志第 1~2 列=poc+类型，无一 P） | **I=10（1.7%，999952 字节）/ P=0 / B=590（98.3%，1038937 字节）**；B 带 L0+L1 双向参考表 |
| deep_qp | `-debug qp` 无输出、show_frames 为空 → QP 600/600 估算（`qp_estimated=True`），类型保持 I=10/P=0/B=590 不变 |
| motion | 真解码像素经 x264 `-qp 0` 无损转封装（framemd5 逐帧一致）后 Farneback：600/600 覆盖，B 均值 1.511px、总体 1.486px、峰值 3.51px；I 位置按设计为 0 |

Reorder 实锤：I@poc64 在 decode idx49（dts 0.8167s，早于其显示时刻 1.0667s
整 15 帧），之后 I@poc128→113 等步调 +64，RA 层次 B 的典型前导；
demuxer 对重排区的 pts 要么 N/A 要么错标（如 decode idx64 的小包 pts 被标成
1.0667s——该时刻真身是 87KB 的 I 帧），故显示序以解码器输出（YUV 显示序）为准。

局限：QP 只能估算（无 ffmpeg avs3 解码器就没有 `-debug qp` 原生 dump）；
ffprobe 对裸 `.avs3` ES 流的宽高/帧率/pts 不完整（宽高=0、avg 25fps 猜测值），
需用解码器真值（1280x720、r_frame_rate/dts cadence 60fps）修正；
10bit 流（MarketPlace 等）需 `-DCOMPILE_10BIT=1` 重编解码器。

## 复现（真 AVS3 流）

```bash
# 1) 解出 YUV（bit-exact，见上）
tools/avs3bin/uavs3dec -i tools/samples/test_avs3_city.avs3 -o /tmp/city.yuv -l 2 -t 1
# 2) 包表 + 解码器类型 + 聚合
python3 -c "
from qt_analyzer.probe import probe
from qt_analyzer.packets import scan
from qt_analyzer.models import AnalysisResult, PicType
from qt_analyzer import codec_avs3 as A
m = probe('tools/samples/test_avs3_city.avs3')
r = AnalysisResult(media=m); r.frames.extend(scan(m.file_path, 60.0, 600))
for f in r.frames: f.type = PicType.I if f.key_frame else PicType.B  # 解码器证无 P
r.media.width, r.media.height, r.media.fps = 1280, 720, 60.0
r.compute_aggregates()
print(A.describe()['decoder'], '|', A.decode_capability_note()[:40], '...')
print('I/P/B:', r.i_stats.count, r.p_stats.count, r.b_stats.count)
print('lcu blocks:', len(A.lcu_overlay(640, 360, r.frames[3])))
print('arcs:', A.reference_arcs(r.frames)[:4])
"
```
