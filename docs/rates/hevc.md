# HEVC / H.265 profile · 采样 · 码率控制速查

> 本机口径：`ffmpeg 9.0.2 / x265 4.3+1-e9b8812（8bit+10bit+12bit）`。
> 相对 AVC 省码率口径：同等主观质量省约 **40%**（JCT-VC 立项目标 ~50%，
> libx265 vs libx264 自然内容实测 ~35–45%）。工具内"节省"均为加权示意（`estimated`）。

## 0. 本机终端证据

```text
$ ffmpeg -hide_banner -h encoder=libx265
Encoder libx265 [libx265 H.265 / HEVC]:
    General capabilities: dr1 delay threads reorderedopaque
    Threading capabilities: other
    Supported pixel formats: yuv420p yuvj420p yuv422p yuvj422p yuv444p yuvj444p gbrp yuv420p10le yuv422p10le yuv444p10le gbrp10le yuv420p12le yuv422p12le yuv444p12le gbrp12le gray gray10le gray12le yuva420p yuva420p10le
libx265 AVOptions:
  -crf               <float>      E..V....... set the x265 crf (from -1 to FLT_MAX) (default -1)
  -qp                <int>        E..V....... set the x265 qp (from -1 to INT_MAX) (default -1)
  -preset            <string>     E..V....... set the x265 preset
  -tune              <string>     E..V....... set the x265 tune parameter
  -profile           <string>     E..V....... set the x265 profile
  -x265-params       <dictionary> E..V....... set the x265 configuration using a :-separated list of key=value parameters

$ x265 --help | grep -A2 -E "profile|preset|tune"
-P/--profile <string>   Enforce an encode profile: main, main10, mainstillpicture
-p/--preset <string>    Default medium
                        ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, or placebo
-t/--tune <string>      psnr, ssim, grain, zerolatency, fastdecode
```

`--profile` 只强制 `main / main10 / mainstillpicture`（本机构建）；
422/444/12bit 靠 `-pix_fmt` + `--output-depth` 间接落到对应档（见下矩阵）。
x265 内部 CRF 默认 `28.0`（ffmpeg 层 `-crf` 默认 `-1` = 不设 = 走 x265 默认）。

## 1. profile × chroma 矩阵

行 = HEVC 标准档，列 = 采样；单元格 = 位深 + 本机 `ffmpeg -pix_fmt`。

| profile | 4:2:0 | 4:2:2 | 4:4:4 | ffmpeg pix_fmt（本机可用 ✓） |
|---|---|---|---|---|
| Main | 8bit | — | — | `yuv420p` ✓ |
| Main10 | 8/10bit | — | — | `yuv420p` / `yuv420p10le` ✓ |
| Main12 | 8/10/12bit | — | — | `yuv420p` / `yuv420p10le` / `yuv420p12le` ✓ |
| Main422-10 | 8/10bit | 8/10bit | — | + `yuv422p` / `yuv422p10le` ✓ |
| Main422-12 | 8–12bit | 8–12bit | — | + `yuv422p12le` ✓ |
| Main444-8 | 8bit | 8bit | 8bit | + `yuv444p` (+`gbrp`) ✓ |
| Main444-10 | 8/10bit | 8/10bit | 8/10bit | + `yuv444p10le` (+`gbrp10le`) ✓ |
| Main444-12 | 8–12bit | 8–12bit | 8–12bit | + `yuv444p12le` (+`gbrp12le`) ✓ |
| Main444-16 Intra | …16bit 全帧内 | … | … | 制作/存档，`--output-depth` 路径 |
| MainStillPicture | = Main 子集（单帧） | — | — | 封面/截图 |

要点：

- 点播/分发只用前两行：**1080p 及以下 `Main + yuv420p`**，**4K+ `Main10 + yuv420p10le`**
  （10bit 降 banding，HDR 必备；`recommend()` 即按此切换，notes 注明 `Main10`）。
- 422 多见于采集/后期中间片，444 多见于屏幕内容/文字（`tune grain` 另算）。
- Tier：每 Level 分 Main/High 两档（`--level-idc` + `--high-tier`）；
  High tier 放高上限码率，4K/8K 高码率用 High tier。常用 Level：
  L3.1≈1080p30 / L4≈1080p60 / L5≈4K30 / L5.1≈4K60 / L6+≈8K。

`qt_analyzer/rc_hevc.py` 对应：`profiles()` 返回上表 10 档；
`chroma_modes()` 返回 9 宫格 pix_fmt 名（420/422/444 × 8/10/12）。

## 2. RC 对照（x265）

| RC | x265 映射 | ffmpeg 映射 | 适用 | 在本工具里的痕迹 |
|---|---|---|---|---|
| CRF 质量 VBR | `--crf 0–51`（默认 28.0；`--crf-max/min` 封顶/保底） | `-crf 23/22`（+ 可选 `-maxrate/-bufsize` 做 VBV 封顶） | 点播/存档默认 | B 密排 + BITRATE 矮峰海，峰谷差大 |
| CQP 定 QP | `-q/--qp` P 帧 QP，`--ipratio 1.40 / --pbratio 1.30` 派生 I/B | `-qp 24`（10bit 建议 22） | 实验/算法对比 | QP 泳道 I<P<B 阶梯最陡最清晰 |
| ABR 均值 | `--bitrate <kbps>`（+ VBV） | `-b:v <k>` + `-maxrate/-bufsize` | 点播定带宽 | 均值达标，峰仍有起伏 |
| CBR 等码率 | `--bitrate` + `--vbv-maxrate=<bitrate>` + `--vbv-bufsize` + `--strict-cbr` | `-b:v = -maxrate` + `-bufsize` + `-tune zerolatency` | 直播/低延迟/RTC | BITRATE 近平顶 + VBV 常满，峰谷差小 |
| VBV（附加） | `--vbv-maxrate/--vbv-bufsize/--vbv-init`（`--const-vbv` 随 grain） | `-maxrate/-bufsize` | CRF 封顶防爆 | 峰被"削顶" |
| 2-pass（附加） | `--pass 1/2/3` + `--stats`，`--multi-pass-opt-*` | 两遍 `-pass 1/2` | 离线压到最优 | 同 ABR，更贴目标 |

preset / tune：

- preset `ultrafast … placebo`（默认 `medium`）：越慢压缩率越高；
  本模块 `streaming → medium`，`archive → slow`，`realtime/CBR → veryfast`。
- tune `psnr / ssim / grain / zerolatency / fastdecode`：
  直播用 `zerolatency`（短 lookahead `--rc-lookahead`，无 B 重排延迟）；
  噪点片用 `grain`（开 `--rc-grain + --const-vbv` 保颗粒）。
- AQ：`--aq-mode 0–4`（默认 2）+ `--cutree`（默认开）+ `--qpmin/--qpmax/--qpstep/--qcomp`；
  一般不用动，CQP/CRF 指纹分析时保持默认即可。

`rc_modes()` 固定返回 `["CRF","CQP","ABR","CBR"]`。

## 3. 码率速查（HEVC 目标 vs AVC 参照）

bpp 模型：HEVC 点播约 1080p `0.10` / 4K `0.075` / 8K `0.06` bpp；
`recommend()` 即按 `pixels × fps × bpp` 估算。

| 分辨率 | AVC 参照（同画质） | HEVC 目标 | 建议起点 |
|---|---|---|---|
| 1080p30 SDR | 8–12 Mbps | **4–7 Mbps** | CRF 23，`Main/yuv420p`，preset medium |
| 1080p60 SDR | 12–16 Mbps | **6–10 Mbps** | CRF 23，VBV 封顶 1.5x |
| 4K30 SDR/HDR | 30–45 Mbps | **15–25 Mbps** | CRF 22，`Main10/yuv420p10le` |
| 4K60 SDR/HDR | 40–60 Mbps | **20–35 Mbps** | CRF 22，High tier（L5.1） |
| 8K30 | 80–120 Mbps | **50–80 Mbps** | CRF 21，`Main10`，High tier |

CBR 直播按上表取中值再 `maxrate = bitrate`（`bufsize ≈ 2× bitrate`，~2s 窗口）；
存档把 CRF 再降 2–3（20/19）且不用 VBV。

## 4. 本工具联动（CTU 层 + QP 阶梯 + B 密排）

| 看哪里 | CRF/ABR 痕迹 | CBR 痕迹 |
|---|---|---|
| CTU 覆盖层 `codec_hevc.ctu_quadtree_overlay` | I 大片蓝/绿 64/32，P/B 橙/红 16/8 碎块（内容自适应，分化明显） | 同左，但高频细节被削平，碎块略少 |
| QP 泳道（`deep_qp`） | I<P<B 阶梯清晰，随场景起伏（CQP 最陡） | QP 被 VBV 压平，阶梯模糊 |
| FRAME TYPE 泳道 | B 密排（B% 常 >60%，`IBBB…` 长串） | B 仍密，但 I 峰被削 |
| BITRATE 图 | 矮峰海 + I 尖峰（峰/谷比大） | 近乎平顶，峰被 VBV"削顶" |
| GOP 面板 `gop_efficiency` | `saving_vs_avc ≈ 0.25–0.30 (estimated)` | 同左，但 `bits_per_GOP` 方差小 |

```python
from qt_analyzer import codec_hevc
from qt_analyzer.rc_hevc import recommend, paint_hint

rec = recommend(3840, 2160, 30)          # streaming 默认：CRF 22 + Main10
print(rec["ffmpeg_args"], rec["notes"])  # 直贴 ffmpeg 用
print(paint_hint())                      # CTU/QP/B 三看一句话
codec_hevc.ctu_quadtree_overlay(640, 360, frame)  # [(x0,y0,size,depth)]
print(codec_hevc.sao_note())             # 脑阈值 1.25 vs AVC 1.18 的道理
```

实际输出（本机）：

```text
$ python3 -c "from qt_analyzer.rc_hevc import recommend; import json; print(json.dumps(recommend(3840,2160,30), ensure_ascii=False, indent=2))"
{
  "width": 3840, "height": 2160, "fps": 30.0, "use": "streaming",
  "rc": "CRF", "profile": "Main10", "pix_fmt": "yuv420p10le",
  "bit_depth": 10, "chroma": "4:2:0",
  "bitrate_kbps": 18662, "maxrate_kbps": 27993, "bufsize_kb": 37324,
  "preset": "medium", "crf": 22,
  "ffmpeg_args": ["-c:v", "libx265", "-preset", "medium", "-profile:v", "main10",
                  "-pix_fmt", "yuv420p10le", "-crf", "22",
                  "-maxrate", "27993k", "-bufsize", "37324k"],
  "notes": ["点播 CRF 22 + VBV 上限 maxrate=27993k / bufsize=37324k",
            "同画质约 AVC 码率 60%（省 ~40%；见 docs/rates/hevc.md 速查）",
            "10bit Main10（yuv420p10le）：4K+ 推荐，banding 更少，HDR 必备"]
}
```
