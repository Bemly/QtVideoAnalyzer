# MPEG-2 profile / 码率速查

> 口径: MPEG-2 (ISO/IEC 13818-2) 是 DVD / 数字广播时代的交付码。
> 本页 = profile×level 矩阵 + CBR/VBR 对照 + DVD/广播码率速查 + 本工具联动。
> 数据模块: `qt_analyzer/rc_mpeg2.py` (无第三方依赖, 永不抛错)。

## 0. 本机证据 (`ffmpeg 9.0.2`)

```bash
$ ffmpeg -hide_banner -h encoder=mpeg2video
Encoder mpeg2video [MPEG-2 video]:
    General capabilities: dr1 delay threads reorderedopaque
    Threading capabilities: slice
    Supported framerates: 1/1 ... 60000/1001
    Supported pixel formats: yuv420p yuv422p
# 全 81 行无 -profile / -level 开关 (grep profile|level|pix_fmt 只命中 pixel formats 行)
```

结论: **profile×level 是规范层约束, 不是本机编码器旋钮**;
采样经 `-pix_fmt` 选择 (420 主力 / 422P 演播室);
码控经 `-b:v` / `-minrate` / `-maxrate` / `-bufsize` (CBR/VBR) 或 `-q:v` (CQP)。

## 1. profile×level 矩阵

profile 行 (括号为 `profiles()` 返回 token):

| profile | 采样/工具 | LL | ML | H14 | HL |
|---|---|---|---|---|---|
| Simple (SP) | 420, 无 B | ○ | ●低延迟 | — | — |
| Main (MP) | 420 IBBP, **主力** | ○ | ● **DVD** | ○ | ○ HD 广播 |
| SNR Scalable | 信噪分级 | ○ | ○ | — | — |
| Spatial Scalable | 空域分级 | — | ○ | ○ | ○ |
| High (HighP) | 420 + 全部可分级 | — | ○ | ● | ● |
| 422P (4:2:2) | **422 + Main 工具**, 演播室 | — | ● 采集 | ○ | ● 母带 |

● 主力/常用, ○ 规范允许但少见, — 规范未定义。`HighP` = High 的常见缩写,
与 `High` 同义 (并列仅为覆盖工具口径)。

level 上限 (分辨率/帧率/码率天花板):

| level | 典型帧尺寸 | 上限码率 |
|---|---|---|
| LL (Low) | 352×288 | ~4Mbps |
| ML (Main) | 720×576/480 (DVD) | ~15Mbps |
| H14 (High-1440) | 1440×1152 | ~60Mbps |
| HL (High) | 1920×1152 (1080 广播) | ~80Mbps |

4K 超出 HL 定义域: `recommend()` 钳位 50Mbps 并提示换 AVC/HEVC。

## 2. CBR / VBR / CQP 对照

| 模式 | ffmpeg 写法 | 行为 | 适用 |
|---|---|---|---|
| CBR | `-b:v X -minrate X -maxrate X -bufsize B` (三者锁死) | VBV 平顶: 高动态只抬 QP 不抬码率, BITRATE 图一条直线 | **DVD** (总线 ~9.8Mbps)、广播直录/垫播 |
| VBR | `-b:v T -maxrate 1.5T -bufsize 2T` (+ `-qmin/-qmax` 护栏) | 峰谷分明: I 峰高 B 谷深, 复杂场景吃满 maxrate | **广播 15~50M**、档案/转码 |
| CQP | `-q:v N` (定量化器, 如 `-q:v 3`) | 码率随内容自由漂, 无 VBV 约束 | 算法分析/测试, 不用于交付 |

DVD 的 `B` 取 VBV 余量 (DVD VBV ~1.8Mbit, 实务 `-bufsize 1835k`);
广播 VBR 取目标 1.5~2 倍 (`-bufsize` ≈ 2×目标)。

## 3. 码率速查

| 场景 | 分辨率 | 推荐 | 说明 |
|---|---|---|---|
| DVD SP | 720×576/480 | **4~6Mbps** CBR | 单层盘 1~2h, VBV 1835k |
| DVD 双层/高质 | 720×576/480 | **7~9Mbps** CBR | 触 9.8M 总线 ceiling, 音频须留 ~0.2M (mp2) |
| 广播 SD/档案 | 720×576 | ~8~10Mbps VBR | 低于 HD 15M 下限属正常 |
| 广播 720p | 1280×720 | **15Mbps** VBR | 50/60fps 上浮 ~1.5~2× |
| 广播 1080i/p | 1920×1080 | **15~25Mbps** VBR | 本模块 1080p25 取 20Mbps |
| 演播室 422P | 1920×1080 422 | **30~50Mbps** | `yuv422p`, 母带/后期口袋 |
| HL 天花板 | 1920×1152 | ≤80Mbps | 规范硬顶, 实务少用满 |

50/60fps 相对 25fps 系数: `min(2.0, max(0.5, fps/25))`。

## 4. GOP IBBP 与码率关系

本工具测试片: `-c:v mpeg2video -pix_fmt yuv420p -g 12 -bf 2 -b:v 2M`
→ 150 帧中 **13 I / 38 P / 99 B** (`docs/codec-matrix.md` 第 2 节)。
典型 GOP(12): `IBBPBBPBBPBB` —— I 峰 (帧内全量) > P 腰 (前向预测)
> B 谷 (双向插值, 常仅为 I 的 1/5~1/3), BITRATE 图呈 **12 帧周期**的
峰-腰-谷波形; `-bf 0` (SP/全 I-P) 则波形变平但码率涨 ~30~50%。

## 5. 本工具联动 (6 联图)

- **GOP 节奏**: FRAME TYPE 条红(I)稀疏、蓝(P)/绿(B)密集, 周期 12;
  `g=12` + 首帧 ⇒ 150 帧约 13 个 I (12×12=144 + 尾帧 1)。
- **REORDER 锯齿**: 含 B 即有解码重排, 包 pts 按文件序非单调**属正常**
  (回归测试只断言 dts 单调 + pts 显示序单调, 见 `tests/test_codecs.py`)。
- **CBR 平顶**: CBR 盘/直录片 BITRATE 高位拉平、QP 行反向起伏
  (码率被 VBV 钳住, 量化器背锅); VBR 片才有真峰谷。
  一句话版: `rc_mpeg2.paint_hint()`。

```python
from qt_analyzer.rc_mpeg2 import profiles, chroma_modes, rc_modes, recommend, paint_hint
profiles()      # ['Simple','Main','SNR','Spatial','High','422P','HighP']
chroma_modes()  # ['420','422']
rc_modes()      # ['CBR','VBR','CQP']
recommend(1920, 1080, 25)
# {'use': 'broadcast', 'width': 1920, 'height': 1080, 'fps': 25.0,
#  'profile': 'Main', 'level': 'HL', 'chroma': '420', 'rc': 'VBR',
#  'bitrate_kbps': 20000,
#  'ffmpeg_args': ['-c:v', 'mpeg2video', '-pix_fmt', 'yuv420p', '-b:v', '20000k',
#                  '-maxrate', '30000k', '-bufsize', '40000k', '-g', '12', '-bf', '2'],
#  'notes': '广播口径 VBR 目标 20000kbps (峰值 30000kbps, ...)'}
recommend(720, 576, 25, "dvd")["bitrate_kbps"]  # 5000 (CBR, min=max=b, bufsize 钳 VBV)
```
