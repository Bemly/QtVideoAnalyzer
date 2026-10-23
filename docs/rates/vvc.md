# VVC/H.266 profile / 采样 / 码率控制速查

> 口径：ITU-T H.266 | ISO/IEC 23090-3（2020 定稿，v3 2023-09）+
> Fraunhofer VVenC 文档口径（`Usage` + `FFmpeg-Integration` wiki，
> VVenC ≥ v1.9/v1.12 行为）。本机 **无 VVC 编码器**（ffmpeg 9.0.2 纯文献
> 调研，见 §0），所有码率/节省数字均为文献范围（`estimated`），非实测。
> 数据模块：`qt_analyzer/rc_vvc.py`（纯标准库，永不抛错）。

## 0. 本机终端证据（ffmpeg 9.0.2，2026-10-23）

```bash
$ ffmpeg -hide_banner -encoders | grep -i -E "vvc|266|vvenc|hevc"
 V....D libx265              libx265 H.265 / HEVC (codec hevc)
 V....D hevc_videotoolbox    VideoToolbox H.265 Encoder (codec hevc)
# 无 vvc / vvenc / 266 行 → 无 VVC 编码器

$ ffmpeg -h encoder=libvvenc
Codec 'libvvenc' is not recognized by FFmpeg.

$ which vvencapp vvencFFapp
vvencapp not found / vvencFFapp not found
```

结论：**无 `libvvenc` / `vvencapp` / `vvencFFapp`**，不可本地生成
`tools/samples/test_vvc.mp4`；`rc_vvc.recommend()` 的 `ffmpeg_args` /
`vvencapp_cmd` 是“装好 `--enable-libvvenc` 的 ffmpeg 才能跑”的前瞻写法，
本机仅做参数自检（不调用编码器）。vvc **解码器**（原生 `vvc` decoder）
与 `show_frames` 状态见 `docs/codec-next.md` §“本机编码器实测状态”。

## 1. profile × chroma/位深矩阵

VVC v1 共 6 个 profile（DASH-IF HLS overview 口径；v2+ 另有 Main 12 /
12 Intra / 4:4:4 12/16 等扩展档，不在 `profiles()` 返回内）：

| profile（`profiles()` token） | 采样 | 位深 | 层 | 典型用途 |
|---|---|---|---|---|
| Main 10 | 单色 + 4:2:0 | 8–10 | 单层 | **流媒体/广播主力**（本模块 `recommend()` 默认） |
| Main 10 Still Picture | 同 Main 10 | 8–10 | 单图 | 静帧/封面 |
| Main 10 4:4:4 | 单色 + 4:2:0/4:2:2/**4:4:4** | 8–10 | 单层 | 演播室/CG/屏显（444 高保真） |
| Main 10 4:4:4 Still Picture | 同 444 | 8–10 | 单图 | 444 静帧 |
| Multilayer Main 10 | 4:2:0 可分级 | 8–10 | ≥1 层 | 空域/SNR 可分级 + RPR 自适应流 |
| Multilayer Main 10 4:4:4 | 444 可分级 | 8–10 | ≥1 层 | 分级 × 444（少见） |

`chroma_modes()` 返回 4 档（label + ffmpeg pix_fmt 提示）：

| `chroma_modes()` | 采样 × 位深 | 对应 profile | ffmpeg/libvvenc 写法 |
|---|---|---|---|
| 420 8-bit (yuv420p) | 4:2:0 × 8 | Main 10 | `-pix_fmt yuv420p` → 库内转 10-bit（`InternalBitDepth=8`，≥v1.9.1） |
| 420 10-bit (yuv420p10le) | 4:2:0 × 10 | Main 10 | `-pix_fmt yuv420p10le`（**libvvenc 唯一原生像素格式**） |
| 444 8-bit (yuv444p) | 4:4:4 × 8 | Main 10 4:4:4 | vvencapp `--format` / 专家模式对应配置 |
| 444 10-bit (yuv444p10le) | 4:4:4 × 10 | Main 10 4:4:4 | 同上（444 档） |

注：vvencapp `--format yuv420 / yuv420_10` 即 420 8/10-bit；ffmpeg 侧
`ffmpeg -h encoder=libvvenc` 显示 `Supported pixel formats: yuv420p10le`
（8-bit 经 `InternalBitDepth=8` 转换，HDR/SDR 经 `Sdr=`/`Hdr=`  signalling）。

levels / tiers（Annex A；DASH-IF 互操作点口径）：共 13 级
1.0/2.0/2.1/3.0/3.1/4.0/4.1/5.0/5.1/5.2/6.0/6.1/6.2（v3 +6.3）。
**Tier** 只有 Main / High 两档：同 level 的 MaxLumaPs/Sr 相同，
MaxBR/CPB 不同（High 面向高码率苛刻应用，仅 L4+ 有意义）。

| level | 互操作点（Main tier） | `recommend()` 映射 |
|---|---|---|
| 3.1 | 1280×720@30 | 720p@≤33fps |
| 4.0 / 4.1 | 2048×1080@30 / 60 | 1080p@≤33 → 4.0，否则 4.1 |
| 5.0 / 5.1 / 5.2 | 4096×2160@30 / 60 / 120 | 4K@≤33 → 5.0，≤66 → 5.1，否则 5.2 |
| 6.0 / 6.1 / 6.2 | 8192×4320@30 / 60 / 120 | 8K@≤33 → 6.0，≤66 → 6.1，否则 6.2 |

`tier` 一律取 `main`（High 仅苛刻档案用，不做默认）。

## 2. VVenC RC 对照（`Usage` + `FFmpeg-Integration` 口径）

`rc_modes()` = `["QP", "CBR", "VBR"]`。注意 VVenC 没有独立 `--cbr`
开关：下表的 CBR 行 = “target + 紧 maxrate 帽”的约束 VBR 用法
（社区/文档对 CBR 字面的通常理解），VBR 行 = 文档具名的平均码率模式。

| 模式 | vvencapp 开关 | ffmpeg（libvvenc）写法 | 码率行为 | 适用 |
|---|---|---|---|---|
| QP（定 QP / CQP） | `-q/--qp 0..63`（默认 32，好值 21–47）；`--bitrate 0` = 关 RC | `-qp 25`（不给 `-b:v` 即 fix-QP） | 无自适应，同 QP 全片；`--qpa 1` 只做感知 QP 微调 | 算法对比/压测 |
| CQF（QP + 封顶） | `-q 27 --qpa 1 -m 5M`（≥v1.12） | `-qp 25 -maxrate 10M` | 质量优先、削峰顶 | 点播防爆发折中 |
| VBR（平均码率） | `-b 2M -m 5M -p 1`（1-pass）/ `-p 2`（2-pass，默认；`--pass 1/2 + --rcstatsfile` 可拆跑） | `-b:v 2M -maxrate 3M`（maxrate ≥ 1.5×target）；2-pass：`-pass 1 … -f null /dev/null && -pass 2 …`（` -passlogfile` 多实例隔离） | 平均命中 target，按内容分配，maxrate 防峰 | **点播/VOD 默认（2-pass）**，直播用 1-pass |
| CBR（约束口） | `-b X -m ~X` 紧帽 + `--qpa 0/1` | `-b:v X -maxrate X`（紧帽近似） | 削峰填谷，复杂场景抬 QP 保码率 | 低延迟直播/垫播（VVenC 文档以 VBR 为主述，CBR 按此理解用） |

RC 通用规则（文档原文）：
`--bitrate 0` = 关 RC（fix-QP）；RC **必须给对帧率**
（`--framerate/--fps`）；`--maxrate` 为 0 = 不封顶纯 VBR；
`--qpa 1`（默认）= 主观优化（MS-SSIM 向好），`--qpa 0` = PSNR/VMAF 向好；
`--refreshsec`（默认 1s）+ `--refreshtype cra|cra_cre|idr`
（DASH 用 `cra_cre` + `MaxPicSize` 约束，见 chunk 示例）。

## 3. preset 对照（faster … slower，5 档 Pareto 集）

| preset | ffmpeg 取值 | 定位 | 适用（`recommend()` 映射） |
|---|---|---|---|
| faster | 0 | 最快，约为 slow 的 ~1/9 时间、~98% VMAF（SLC 单测，非普适承诺） | **realtime/低延迟**（`use=realtime`） |
| fast | 1 | 快，4K/8K 可行档 | **streaming 且 4K/8K** |
| medium | 2（默认） | 默认平衡 | **streaming 且 ≤1080p**；`use=qp` |
| slow | 3 | 高压缩，明显更慢 | **archive**（≤4K） |
| slower | 4 | 最高压缩，构建级耗时 | 仅 `use=best` 且 ≤1080p（8K 不给 slower） |

专家模式对照：`randomaccess_[faster…slower].cfg` + `qpa.cfg` /
`rc1p.cfg` / `rc2p.cfg`；`--additional "k=v:k=v"` 可透传全部
vvencFFapp 参数（如 `intraperiod=64:decodingrefreshtype=idr`）。

## 4. 相对 HEVC 省码率口径 + 典型码率速查（estimated）

| 口径来源 | VVC vs HEVC |
|---|---|
| JVET 设计目标（Fraunhofer HHI） | **~50%**（同等主观质量） |
| VTM vs HM 参考软件（Sullivan DCC'21） | HD/UHD 约 **41%** PSNR BD-rate（JEM 早期 ~34%） |
| VVenC 生产实测（preset/内容相关） | 约 **30–50%**（faster 贴近 x265 最慢档仍省 ~50%，见 ACM 文） |
| 8K 论文抽查（preprints/MDPI） | vs HEVC 约 **46%**（8K，PSNR BD-rate） |

速查（VBR target，30fps；60fps ×1.5 Advent；maxrate 取 2×，
满足 ≥1.5× 规则；`estimated`，≈ HEVC 阶梯 ×0.5–0.6）：

| 规格 | 分辨率 | VBR target | maxrate | level | HEVC 对照 |
|---|---|---|---|---|---|
| 720p30 | 1280×720 | ~1.5 Mbps | ~3 Mbps | 3.1 | HEVC ~2.5–3M |
| 1080p30 | 1920×1080 | **~3 Mbps**（DASH 例 2M 偏进取，安全端 4M） | ~6 Mbps | 4.0 | HEVC ~5–8M |
| 1080p60 | 1920×1080 | ~4.5 Mbps | ~9 Mbps | 4.1 | HEVC ~8–12M |
| 4K30 | 3840×2160 | **~8 Mbps**（DASH 例 4M 偏进取，安全端 9M） | ~16 Mbps | 5.0 | HEVC ~12–20M |
| 4K60 | 3840×2160 | ~12 Mbps | ~24 Mbps | 5.1 | HEVC ~20–30M |
| 8K30 | 7680×4320 | ~28 Mbps | ~56 Mbps | 6.0 | HEVC ~40–60M |

`recommend(3840,2160,30)` 默认（streaming）返回 4K 档：
`bitrate_bps=8000000`，`ffmpeg_args=[-c:v libvvenc -preset fast
-b:v 8000000 -maxrate 16000000 -pix_fmt yuv420p10le -level 5.0 -tier main]`，
见 §6 自检输出。

## 5. 本工具联动（128 CTU 层 · 大 GOP · B 密排）

- **128 CTU 层**：切 VVC MTT 层（`codec_next.mtt_overlay`，CTU 128，
  深度 0..4 五档配色）：I 帧浅（蓝/绿大块，QT 为主），P/B 帧深
  （橙/红小块，MTT 二/三分主导）。VVC 相对 HEVC（CTU 64 + 纯四叉）
  的核心增益即在此多叉树上。
- **大 GOP**：VVC 随机接入默认 `--refreshsec 1`（秒级 GOP，可拉长到
  DASH chunk 4s 如 `cra_cre + rs 4`）；GOP 拉长 + 双向预测摊薄 I 成本，
  与 HEVC 同理但 128 CTU 下大块 I 更便宜。
- **B 密排**：B 占比常 >60%（HEVC 测试片 99/150 的同类结构在 VVC 下
  保持）；BITRATE 图呈“I 峰尖而稀、B 海洋又密又矮”，B 海洋即省码率
  本体。REORDER/pts 文件序非单调属正常（含 B 即重排）。
- 一句话版：`rc_vvc.paint_hint()`。

```python
from qt_analyzer.rc_vvc import profiles, chroma_modes, rc_modes, recommend, paint_hint
profiles()      # ['Main 10', 'Main 10 4:4:4', 'Multilayer Main 10']
chroma_modes()  # ['420 8-bit (yuv420p)', '420 10-bit (yuv420p10le)', ...]
rc_modes()      # ['QP', 'CBR', 'VBR']
recommend(3840, 2160, 30)
# {'preset': 'fast', 'res_class': '4K', 'profile': 'Main 10', 'level': '5.0', ...,
#  'bitrate_bps': 8000000, 'maxrate_bps': 16000000, 'passes': 1,
#  'ffmpeg_args': ['-c:v', 'libvvenc', '-preset', 'fast', '-b:v', '8000000',
#                  '-maxrate', '16000000', '-pix_fmt', 'yuv420p10le',
#                  '-level', '5.0', '-tier', 'main'],
#  'vvencapp_cmd': 'vvencapp --preset fast -s 3840x2160 -r 30 ...',
#  'notes': '4K@30 streaming: VBR target ~8 Mbps ... estimated ...'}
print(paint_hint())
```

## 6. 本机自检（无编码器 → 文献模式）

```text
$ ffmpeg -encoders | grep -i vvc; echo exit=$?
exit=1   # 无输出：无 VVC 编码器（纯文献调研，已注明）

$ python3 -c "from qt_analyzer.rc_vvc import recommend; import json; print(json.dumps(recommend(3840,2160,30), ensure_ascii=False, indent=1))"
{
 "preset": "fast",
 "ffmpeg_args": ["-c:v", "libvvenc", "-preset", "fast", "-b:v", "8000000",
                 "-maxrate", "16000000", "-pix_fmt", "yuv420p10le",
                 "-level", "5.0", "-tier", "main"],
 ...
}
```
