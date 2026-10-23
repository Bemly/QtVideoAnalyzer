# AV2 码率 / profile / 采样方向（一页现状，experimental）

> AV2 尚在 AOM 实验阶段、本机无编解码器、无容器映射。
> 本页纯文献整理，所有方向值均标 **`experimental`**，不可当作成品结论。
> 数据模块：`qt_analyzer/rc_av2.py`（标准库 only，永不抛错）。

## 1. 草案来源（链接 + 日期）

| 项 | 值 |
|---|---|
| 规范现行版 | AV2 Bitstream & Decoding Process Specification **v1.0.0**，**2026-05-28**，https://av2.aomedia.org/ |
| 被取代的工作草案 | working draft **v13**，**2026-01-05**（编号 v13 早于 1.0.0，仅沿革引用），https://av2.aomedia.org/v13-public/index.html |
| 发布公告 | AOMedia press release **2026-06-06**（"AV2 specification … v1.0.0 … coding tools are frozen" 意：工具冻结，后续只加 profile/元数据） |
| 参考软件 | **AVM**（`avmenc`/`avmdec`），与 v1.0.0 对应 tag 为 `v1.0.0`；RC/partition 行为以该 tag 为准 |
| RC 选项整理 | https://encode.wiki/tools/software-encoders/avm（`--end-usage` / `--qp` / `--target-bitrate` 表） |
| 状态综述 | https://encode.wiki/codecs/video/av2（2026-10 口径：只有参考软件，无生产编码器/ffmpeg/浏览器/硬件解码器） |

## 2. 已知方向（都有出处，非实测）

- **Profiles**：v1.0.0 只定义一个工具集 Main，
  `Main_420_10_IP0`（idc 0）/ `IP1`（1）/ `IP2`（2）/
  `Main_422_10_IP1`（3）/ `Main_444_10_IP1`（4）/ `Configurable`（31）。
  IP 是可同时处理的层数约束（0=至多4流×1层，1=至多2层嵌入，2=至多3层），不是速度/质量档。
  出处：规范 Annex A + v13 release notes §5 + encode.wiki profile 表。
- **Chroma × 位深**：`chroma_format_idc` 0=4:2:0 / 1=4:0:0(mono) / 2=4:4:4 / 3=4:2:2；
  `bit_depth_idc` 0=8-bit / 1=10-bit。**v1.0.0 全部 profile 止于 10-bit**，
  `bit_depth_idc > 1` 为未来版本保留（release notes §5.2 明说草案曾误写 12-bit，
  定稿须收紧）。出处：规范 §5.4.11 color_config + v13 release notes §5.2/§5.5。
- **SB 尺寸**：序列级 `use_256x256_superblock` / `use_128x128_superblock` 两 flag；
  256 使能时帧内 SB=128、帧间 SB=256；MFH `sb_size_idx` 0=64 / 1=128 / 2=256 / 3=混合。
  处理单元仍是 64x64（ERP 递归由 256 起向下分）。出处：规范 sequence_partition_config /
  MFH 语法 + ICIP2024《Overview of Coding Tools Under Consideration in AVM》。
- **RC 方向（延续 AV1）**：AVM `avmenc --end-usage=vbr(默认)/cbr/cq/q`，
  `--qp` 0~255 全位深统一标尺（AV1 的 CRF 概念对应 `q`/`cq`，数值不通用），
  `--target-bitrate` 单位 kbit/s，**仅支持单遍**（`--passes` 须为 1），
  VBR 用固定 240000ms buffer 模型。出处：encode.wiki AVM 页实测整理。
- **Film grain 增强**：AV1 帧头参数表 + 解码端合成（不占残差码率）延续；
  AV2 模板仍 64x64、同 LFSR 多项式，但合成块可选 **32x32 或 16x16**（逐帧 signalling）；
  另有 FGS+debanding 研究（Norkin, DCC 2026：在 grain 叠加时加 `Offd` 去带状伪影）。
  已知 bug 类：restricted switch frame 下 QM/FilmGrain 处理未定义（release notes §2.1）。
- **压缩增益口径**：AOM 口径“相对 AV1 省约 **30%**”（CTC 下 AVM 参考编码器 VMAF/PSNR 对比，
  非常慢速设置；不代表生产编码器 vs SVT-AV1/aomenc）。`recommend()` 的 ×0.7 折扣即来于此。

## 3. 未知事项（诚实标注）

1. 12-bit Professional profile 内容与时间表（Video Codec WG 已立项，未定稿）。
2. ISO BMFF / Matroska 容器映射未发布（规划中；测试输出只留 IVF/OBU，不要借用 `av01` 标识）。
3. ffmpeg 支持：上游只有 **PR #23018**（2026-05-05，`libdav2d` 外部解码 wrapper，
  `--enable-libdav2d`，未合入发行版）；`dav2d` 自身 0.0.x 早期开发（8/10-bit 解码已通，优化中）。
4. 生产级编码器、浏览器、硬件解码器：均无时间表。
5. `recommend()` 的 AV1 阶梯 ×0.7 是 UI 占位口径，不是码率承诺；AVM 本身极慢
  （320x180 小片仍远低于 1fps），任何选型结论都须等生产编码器重测。

## 4. 终端证据（本机，2026-10-23，ffmpeg 9.0.2）

```sh
$ ffmpeg -hide_banner -encoders 2>/dev/null | grep -i -E "av2|libavm|dav2d"
 A....D wmav2                Windows Media Audio 2     # ← 只是音频 wmav2，无视频 AV2
$ ffmpeg -hide_banner -decoders 2>/dev/null | grep -i -E "av2|dav2d"
 A....D wmav2                Windows Media Audio 2     # ← 同上
```

```text
profiles: ['Main_420_10_IP0', 'Main_420_10_IP1', 'Main_420_10_IP2',
           'Main_422_10_IP1', 'Main_444_10_IP1', 'Configurable']
chroma: ['4:0:0 8-bit', '4:0:0 10-bit', '4:2:0 8-bit', '4:2:0 10-bit',
         '4:2:2 8-bit', '4:2:2 10-bit', '4:4:4 8-bit', '4:4:4 10-bit',
         '4:2:0 12-bit (future professional, experimental)',
         '4:2:2 12-bit (future professional, experimental)',
         '4:4:4 12-bit (future professional, experimental)']
rc: ['vbr', 'cbr', 'cq', 'q']
recommend(1920,1080,30):
{
 "codec": "av2",
 "experimental": true,
 "status": "experimental：AOM 实验阶段，无 ffmpeg 支持，纯文献方向，不可当作成品结论",
 "spec": "AV2 Bitstream & Decoding Process Specification v1.0.0 (2026-05-28)",
 "width": 1920,
 "height": 1080,
 "fps": 30.0,
 "use": "streaming",
 "profile": "Main_420_10_IP0 (experimental)",
 "chroma": "4:2:0 10-bit (experimental)",
 "rc_mode": "vbr (experimental)",
 "bitrate_mbps": {
  "target": 3.5,
  "low": 2.45,
  "high": 4.55
 },
 "avm_flags": "--end-usage=vbr --target-bitrate=3500 --passes=1  # reference-only, single-pass",
 "sb_size": "256 inter / 128 intra (directional, experimental)",
 "note": "沿用 AV1 口径×0.7（AOM ~30% saving，CTC 参考编码器对比）；AVM 极慢、仅单遍、无容器映射（IVF/OBU），不可用于生产选型。"
}
paint: AV2 (experimental)：SB 256（帧间）/128（帧内）网格示意 + GOP 通用语义；本机无编解码器，码率值为 AV1 口径×0.7 文献估算，不可当作成品结论。
```

复现：`python3 -c "import sys; sys.path.insert(0,'.'); from qt_analyzer.rc_av2 import *; ..."`（见上）。
