# AVS3 码率 / profile / 配置速查（HPM · uavs3e · 广播口径）

> 数据模块：`qt_analyzer/rc_avs3.py`（`profiles/chroma_modes/rc_modes/recommend/paint_hint`）。
> 本机 brew ffmpeg 9.0.2 无 AVS3 编解码（仅 AVS1/cavs 解码），`ffmpeg_args` 为占位，
> 等效命令以 uavs3e 草稿形式给出。

## 1. profile × level 矩阵

| profile | 位深 | 采样 | 阶段/定位 | 备注 |
|---|---|---|---|---|
| Main | 8bit | 4:2:0 | phase-1（2019 定稿）主力 | uavs3e 默认 `COMPILE_10BIT=0` 即此档 |
| Main10 | 10bit | 4:2:0 | 广播/HDR 主力（phase-1 10bit 系列） | 4K/8K 广播都用它；uavs3e 需 `cmake -DCOMPILE_10BIT=1` |
| High | 10bit | 4:2:0 | phase-2（2021 定稿）扩展工具 | 监控/屏幕内容增强；本工具按 Main10 码率口径套用 |

| level | 分辨率 | 帧率 | 采样/位深 | 解码能力口径 |
|---|---|---|---|---|
| 6.0.60 | 3840×2160 | 50p | 4:2:0 10bit | 中国 4K 广播档（GY/T 368 框架引用） |
| 8.0.60 | 7680×4320 | 50p | 4:2:0 10bit | 8K 档，最大码率支撑不低于 **120Mbps** |

- **chroma 结论：420 是主力且是广播唯一档；422 不在 AVS3-P2 baseline 广播档内**
  （UWA 4K 码流格式表：HEVC 栏写 4:2:2，其余含 AVS3 均为 4:2:0）。
- AVS3 为 DVB 下一代 UHD 标准之一（DVB Steering Board 2022-07-08 批准）；
  对应 IEEE 1857.10《第三代视频编码》。

## 2. 两套配置对照（HPM CTC：RA vs LD）

| | randomaccess（RA） | lowdelay（LD） |
|---|---|---|
| 用途 | 点播 / 存储 / 广播编码（效率优先） | 直播 / 交互（时延优先） |
| 参考结构 | 分层 B，GOP 32（≤30p）/ 64（50/60p） | LD-P：零结构时延，仅前向参考，GOP 4；要 B 可 LD-B（1~2 个 B） |
| Intra 周期 | ~2s 一个 CRA/IDR | ~1s 一个 I（快加入 + 抗误码） |
| CQP 锚点 | QP 22 / 27 / 32 / 37（画 BD-rate 至少 4 点） | 同左，常用 27 起步 |
| CBR 代价 | 基准（区间下限） | 同画质比 RA 高约 10~20%（取区间上限） |
| 本工具痕迹 | GOP 条 IBB 节奏 + REORDER 锯齿 | P 链为主、无/弱锯齿 |
| uavs3e 起点 | `--config encode_RA.cfg` + 命令行覆盖 | 同系列 LD cfg + 命令行覆盖 |

uavs3e 调用形如（占位草稿，以仓库 README 为准）：

```bash
uavs3e --config encode_RA.cfg -w 3840 -h 2160 --fps 50 --qp 32 -o out_ra.avs3
uavs3e --config encode_LD.cfg -w 3840 -h 2160 --fps 50 --qp 27 -o out_ld.avs3
```

## 3. 码率速查（CBR 起点，50/60p 广播贡献质量）

| tier | 帧率 | CBR 区间 | CQP 起点 | 说明 |
|---|---|---|---|---|
| ≤1080p | 25/30p | 4~8 Mbps | QP 27~32 | 基准档 |
| ≤1080p | 50/60p | 8~12 Mbps | QP 27~32 | 帧率翻倍约 ×1.5~2 |
| 4K | 25/30p | 18~25 Mbps | QP 27~32 | 低帧率 4K |
| **4K** | **50p** | **30~40 Mbps（常用 36M 量级）** | **QP 27~32** | **中国 4K 广播主力口径** |
| 8K | 50/60p | 80~120 Mbps | QP 27~32 | 上限看 120M 解码能力 |

> 口径说明：4K 档综合 GY/T 368 框架、UWA 4K/8K 码流表与行业常用值；
> 帧率减半约按 0.7 折算；HDR/高运动取区间上限；最终以播出机构网管为准。

## 4. 本工具联动（LCU 128 层 / IBB 节奏）

- `codec_avs3.LCU_SIZE = 128`：开 AVS3 LCU 层看 128 网格 ——
  I 帧浅（蓝/绿大块，depth 0~1 概率 0.8），P/B 帧深（橙/红碎块）。
- GOP 条看 IBB 节奏：有 B 即 RA 真身（与全 I 的 ProRes 正好两端对照）；
  REORDER 锯齿幅度 ≈ 重排深度，LD-P 下基本消失。
- 脑阈值 `BRAIN_THRESHOLD = 1.22`（AVC 1.18 / HEVC 1.25 之间）：DBF+SAO+ALF 三级环路。
- 全链自测沿用 hevc 代跑（同为 ffprobe 帧头解析路径，type/GOP 逻辑相同），
  `codec_avs3.describe()/lcu_overlay()/reference_arcs()` 照常可用。

## 5. 文献来源

1. 国家标准全文公开系统：GB/T 33475.2-2024《信息技术 高效多媒体编码 第2部分：视频》
   <https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=C23145CA7C18AC718FDE2589AC626D6E>
2. uavs3e（AVS3-P2 baseline，开源编码器，RA cfg + 8/10bit 编译开关）
   <https://github.com/uavs3/uavs3e>
3. AVS3 phase-1 性能与工具（EQT/仿射/多参考；4K 相对 AVS2 省约 30%）
   <http://47.93.196.121/English/AVS3_introduce.asp>
4. AVS3 参考软件 HPM（CTC RA/LD，HPM4.0→HPM15.1 演进；8K 直播链）
   <https://www.hisilicon.com/en/techtalk/avs3>、
   <https://hpc.pku.edu.cn/docs/pdf/a20191230178.pdf>
5. 4K/8K 码流格式要求（level 6.0.60 / 8.0.60，4:2:0 10bit，8K 最大码率 ≥120Mbps）
   T/UWA 005.3-5-2022：
   <https://www.theuwa.com/upload/ueditor/file/20230911/1694425820857353/c8a62dd131d921954222160122c9284b.pdf>
6. AVS 工作组 / DVB 采纳（2022-07-08 DVB SB 批准 AVS3 为下一代 UHD 标准之一）
   <https://www.avs.org.cn/en>
