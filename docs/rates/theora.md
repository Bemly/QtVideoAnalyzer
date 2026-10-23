# Theora quality / 采样 / 码率

> 状态: **纯文献调研** —— 本机 ffmpeg 无 `libtheora` 编码器
> (`ffmpeg -encoders | grep theora` 无输出, `-h encoder=libtheora` 报
> `not recognized`; 只有 theora **解码器**), 以下参数未经本机实测,
> 依据为 ffmpeg 官方文档 §9.15 + Xiph/Theora 公开资料 + 开源视频社区口径.
> 数据模块见 `qt_analyzer/rc_theora.py`.

## 1. 无 profile 体系 (VP3 血统)

Theora 没有 H.264/HEVC 那样的 Baseline/Main/High profile 体系,
原因在血统里: 它是 On2 TrueMotion **VP3.2** 于 2001 年捐给 Xiph、
改写成的开放格式 (Theora I 规范 2004, 1.0 版 2008, Thusnelda 1.1 版 2009).
VP3 本来就是单一档位的流媒体 codec, Theora 继承了这一点:

- 块结构固定: 16x16 宏块 + 8x8 DCT (见 `codec_theora_av1.py` `describe("theora")`);
- 无 B 帧 (只有 I/P), 无帧内递归细分, 无标准化环路滤波;
- 所以调参只有两维: **quality 档** 或 **目标码率**, 没有 profile/level 组合拳.
- 本工具 `profiles()` 返回 `["(no profiles: VP3-based)"]` 即为此意.

## 2. quality 0~10 档 (VBR 恒定质量 targeting)

ffmpeg 映射 (`-q:v N` CLI / `global_quality` 库接口, 文档 §9.15):

- `N` clip 到 [0,10], 再 **×6.3 → libtheora native [0,63]**, 值越大质量越高;
- 开启条件是 `flags +qscale`; 一旦进入 VBR 模式, `-b:v` **被忽略**;
- 另有 `g` (GOP 长度) 可配, `flags pass1/pass2` 做 2-pass.

档位对照 (社区常用口径, native = 档×6.3):

| 档 | native | 定位 |
|----|--------|------|
| 0–2 | 0–12.6 | 极低: 缩略图/预览, 块效应明显 |
| 3–4 | 18.9–25.2 | 低: 360p 流媒体下限 |
| 5 | 31.5 | **通用均衡**: 480p/720p 起点, 本工具 `recommend` 默认 |
| 6 | 37.8 | 高: 720p 存档 |
| 7–8 | 44.1–50.4 | 很高: 母带/中间片 |
| 9–10 | 56.7–63 | 接近无损: 测试与比对用, 体积大 (`-q:v 10` 为官方示例的最大质量写法) |

命令示例 (ffmpeg 官方文档 §9.15.2 原样):

```sh
ffmpeg -i INPUT -codec:v libtheora -q:v 10 OUTPUT.ogg   # 最大恒定质量 VBR
ffmpeg -i INPUT -codec:v libtheora -b:v 1000k OUTPUT.ogg  # CBR 1000 kbps
```

## 3. bitrate targeting 模式

- **软目标 (1-pass `-b:v`)**: 长期均值目标, 自带 reservoir,
  复杂场景允许上冲、简单场景省码, 实际均值≈目标但峰值会超.
  适合文件存档/点播.
- **收紧 (2-pass)**: `-pass 1` 跑统计 + `-pass 2` 落码,
  均值贴合更好, 峰值仍可能超.
- **硬 CBR**: `-b:v N -minrate N -maxrate N -bufsize M` 做 VBV 整形,
  每个窗口都合规, 适合固定带宽推流; 代价是量化器抽动、画质让路.
  注意: libtheora 包装原生只认 `b/quality` 两档目标
  (官方文档列出的映射仅 `b/flags/g/global_quality/q`),
  硬 CBR 属上层 ffmpeg 通用 VBV 语义, 本机无编码器**未经实测**, 按文献口径使用.
- 本工具 `rc_modes()` 返回 `["VBR-quality", "CBR-target"]`;
  `recommend(..., use="streaming")` 默认走 CBR-target,
  `use="archive"/"quality"/"vbr"` 走 VBR-quality.

## 4. chroma 仅 420

- Theora 码流头 PFI 虽定义了 420/422/444 三种采样,
  但 ffmpeg `libtheora` 包装的像素格式**只支持 `yuv420p`**
  (转码前先 `-vf format=yuv420p`).
- 本工具 `chroma_modes()` 返回 `["420"]` 即按编码路径口径;
  8bit、Ogg 封装 (`.ogv`), 见 `codec_theora_av1.py` 的算法卡.

## 5. 典型码率速查 (360p~720p, 开源视频口径)

Theora 效率约为 H.264 的 2/3 (同观感约需 1.3–1.5× 码率),
下表为 30fps 起点估计, 高帧率按 `fps/30` 上浮 (封顶 1.5×);
均为**文献/经验口径, 未经本机实测**:

| 分辨率 | CBR 起点 | VBR 质量档 | 备注 |
|--------|----------|------------|------|
| 360p (640x360) | 700k (600–800k) | q4 | 流媒体下限 |
| 480p (640x480 / 854x480) | **1000k** (900–1200k) | q5 | 与官方示例 1000k 一致 |
| 720p (1280x720) | 2600k (2200–3200k) | q5–6 | 存档建议 q6 |
| >720p | 不推荐 | — | 超出舒适区, 换 VP9/AV1 |

bpp 验算: 640x480@30 + 1000k → ≈0.108; 720p + 2600k → ≈0.09,
量级自洽 (Theora 无环路滤波, 低 bpp 糊块更快, 故起点偏保守).

## 6. 本工具联动

- **QP 全估计**: Theora 无原生 QP 读数 (`-debug qp` 无输出),
  本工具走 bpp 估计 QP; I/P 台阶状 (I 一档、P 一档, 帧内几乎无抖动,
  见 `theora_qmatrix_note()`).
- **MOTION 全回退**: 无原生 MV 输出, 走 Farneback 光流估计
  (`motion.py`); Theora 无 B 帧, I/P/B 栏 B 恒 0 属正常.
- **看质量波动找糊帧**: 无标准化环路滤波 → 8x8 块边界误差直接残留,
  brain 判定收紧到 `blockiness > 1.12`
  (`THEORA_BRAIN_THRESHOLD`, `codec_theora_av1.py:43`);
  质量波动段 (I→P 台阶跳变、糊块簇) 即优先排查位.
- **overlay**: `theora-dots` 8x8 点阵
  (`superblock_overlay(..., codec="theora")`, `paint_hint()`),
  色彩/抽样见 `paint_superblock_overlay` (`codec_theora_av1.py:412`).

## 7. 文献来源

- ffmpeg 官方文档 `ffmpeg-codecs.html` §9.15 libtheora
  (Options: `b` CBR / `flags +qscale/pass1/pass2` / `g` /
  `global_quality` 与 `q` 的 [0-10]→×6.3→[0-63] 换算; Examples 两条命令).
- Xiph.org Theora 规范与 encoder 文档 (VP3.2 血统、无 profile、B 帧缺席、PFI 采样定义).
- 本机证据见主线程终端记录: `libtheora` 编码器缺失, 仅解码器存在;
  `recommend(640,480,30)` 输出见 `rc_theora.py` 自测.
