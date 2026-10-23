# AVC / H.263 算法要点与看图指南（一页）

适用测试片：`tools/samples/test_avc.mp4`（libx264, 640x360, `-g 30 -bf 2`）
与 `tools/samples/test_h263.mov`（h263p, 640x360）。实现见
`qt_analyzer/codec_avc_h263.py`（仅 PySide6 + numpy + 标准库）。

## 1. 算法要点（`describe()` 口径）

| 维度 | AVC (H.264) | H.263 |
|---|---|---|
| 块划分 `block_sizes` | 16x16 MB，可分 16x8 / 8x16 / 8x8 / 8x4 / 4x8 / 4x4 | 16x16 MB + 8x8 块（DCT），无 4x4 |
| B 帧 `bframes` | 有，B 金字塔分层双向预测 | 基线无 B 帧（Annex O 可选项除外） |
| 熵编码 `entropy` | CAVLC / CABAC（4x4 整数变换） | VLC 变长码（Annex D/E/F/J 可选增强） |
| 参考 `refs` | 多参考帧（≤16）+ 环路去块滤波 + 1/4 像素 MV | 单前向参考 + 半像素 MV（Annex F 可选重叠块补偿） |
| 同步 `strengths` | 无 GOB，全靠 slice/IDR | GOB 行条：每 3 行 MB（48 px）一组重同步 |
| QP 指纹 | 原生可用；CABAC 下**同类帧 QP 方差小** | 原生可用但**范围粗**（步长翻倍档，台阶跳变） |

## 2. 在本工具哪张图看什么

- **FRAME TYPE 泳道（B/I/P 面板 + 第 2 行 GRAPH）**：AVC 见 `IBBPBB…`，
  B 排密集（150 帧约 88 个 B）；H.263 只有 I/P 两排，B 排恒空。
  对应 `reference_arcs()`：AVC 的 B 出前后两条边（`fwd`+`bwd`），
  H.263 只有 P 的前向边。
- **REORDER 泳道（第 6 行，pts−dts）**：AVC 呈**锯齿**（B 帧 pts 超前、
  dts 滞后，重排深度 > 0）；H.263 为 **0 直线**（pts==dts，无重排）。
- **QP 泳道（第 3 行）**：AVC **带宽窄**（同类帧 QP 聚拢，I<P<B 阶梯清晰
  = 率失真优）；H.263 呈**宽台阶**（量化档粗，P 帧随运动抖动大）。
  旁注文案见 `qp_signature_note()`。
- **块划分 overlay（`partition_overlay()`，按当前帧类型过滤 style）**：
  AVC 画 16x16 MB 网格（`mb`）+ P 横中线 16x8（`p`）/ B 十字 8x8（`b`）——
  I 只看 `mb`，P 看 `mb+p`，B 看 `mb+b`；
  H.263 画 GOB 行条（`gob`，每 48 px 一条）+ 8x8 块网格（`blk`）。

## 3. 一句话判读

> B 排有东西 + REORDER 锯齿 + QP 带窄 = AVC；
> 无 B + REORDER 零线 + QP 宽台阶 + GOB 行条 = H.263。
