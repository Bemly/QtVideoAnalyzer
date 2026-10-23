# 次世代编码器：VVC (H.266) + AV2

> 一页纸：要点 + 在本工具看什么 + 本机实测状态。overlay 划分为同帧确定性**示意**，
> 非码流真值；省码率数字为标准目标/典型范围。

## VVC (H.266) 要点

- **CTU 128×128 + QT/MTT 多叉树**：QT 先分大块，叶子再 MTT 递归
  （HBT/VBT 二分、HTT/VTT 三分 1:2:1），最小亮度块可到 4×4；
  I 帧偏 QT 大块，P/B 偏 MTT 小块。相对 HEVC（CTU 64 + 纯四叉树）是核心增益来源。
- **环路滤波 ALF + CCALF**：DBF + LMCS 之后再做自适应环路滤波与跨分量 ALF，
  振铃/色度偏差残留更少，同等 QP 下残差更便宜。
- **工具**：AFFINE 仿射运动、GEO 几何划分、MIP 矩阵帧内预测、IBC 块复制
  （屏幕内容），运动/纹理边缘残差更小。
- **RPR 参考帧重采样**：分辨率自适应切换无需 CRA/IDR，流切换与 ABR 不断流。
- **省码率**：相同主观质量下比 HEVC 再省约 **40%**（JVET 通用测试目标；
  编码器实测典型约 30~50%，视内容与配置而定）。

## AV2 要点（experimental）

- **SB 256×256（传闻）**：AV1 为 SB 128，AV2 讨论中传闻翻倍，最终以 AOM 定稿为准。
- **TF/环路滤波工具方向**：更大核变换候选、自适应环路滤波增强、CDEF/LR 后继方案，
  均在探索，不可当作成品结论。
- **film grain 增强**：在 AV1 胶片颗粒合成基础上传闻增强建模与参数 signalling，
  低码率保留胶片感。
- **状态**：仍在 AOM 标准化中，标 **`experimental`**；本机无 AV2 编解码器，
  本工具暂无 AV2 分区层。

## 在本工具看什么

- 切 VVC MTT 层：看 128 CTU 网格 + 多叉树划分（I 浅蓝绿大块 / P、B 深橙红小块）。
- GOP 条通用语义：I 红高 / P 蓝中 / B 绿矮，码率峰即随机访问点；
  AV2 暂用同一套 GOP + QP 视角看。
- `describe("vvc")` / `describe("av2")` 返回本页要点的字典形式（含 `where_to_look`）；
  `decode_capability_note()` 返回本机实测结论（永不抛错）。

## 本机编码器实测状态（ffmpeg 9.0.2，2026-10-23）

```sh
ffmpeg -hide_banner -encoders | grep -i -E "vvc|vvenc|av2"   # 无输出（exit 1）
ffmpeg -hide_banner -decoders | grep -i -E "vvc|vvenc|266"   # V....D vvc  VVC 解码器
```

- **vvc/vvenc 编码器：无** → 不可本地生成 `tools/samples/test_vvc.mp4`
  （`libvvenc`、`hevc_videotoolbox` 式 VVC 项均不存在；`ffmpeg -h encoder=libvvenc`
  报 not recognized）。
- **vvc 解码器：有**（原生 `vvc` decoder，`dr1 delay threads`）。
- **AV2 编解码器：均无**（AOM 实验中，未收录）。
- **VVC 样本：无**（本地 + 公网试拉 Elecard 样本 404），
  `show_frames pict_type` 实测用 `tools/samples/test_hevc.mp4` **代跑并注明**：
  `-show_streams` / `-show_frames` 在 hevc 上均可用（同为 ffprobe 帧头解析路径，
  结论外推至 vvc）；拿到原生 VVC 样本后直接重跑即可。
