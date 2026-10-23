# 编码器差异矩阵 (Codec Matrix)

测试片来源: `tools/make_test_videos.sh` 一键生成（约 5s, 640x360, 30fps,
`testsrc2` 运动 + 每 2.5s 一次整帧红闪充当场景切换，便于观察 I/P/B 行为）。
本机环境: ffmpeg / ffprobe **9.0.2** (`/opt/homebrew/bin`, Apple Silicon,
`--enable-libx264 --enable-libx265 --enable-libvpx --enable-libsvtav1`)。

生成结果: **7 个成功，2 个跳过**(本机无编码器），0 失败。

## 1. 总览（一编码器一行）

| 测试片 | 容器 | 编码器名 | 是否有 B 帧 | flags K 可用 | qp 原生 | mv 原生 | 备注 |
|---|---|---|---|---|---|---|---|
| test_avc.mp4 | mp4 | libx264 (h264) | 有 (88 B) | ✔ (6 K / 150 包) | ✔ | ✔ | 场景闪切触发 x264 scenecut，加出 1 个 IDR (g=30 本应 5 个 I) |
| test_hevc.mp4 | mp4 | libx265 (hevc) | 有 (99 B) | ✔ (5 K / 150 包) | ✘ | ✘ | 原生 hevc 解码器不支持 `-debug qp` dump，也不支持 `export_mvs` |
| test_mpeg2.mpg | mpeg-PS | mpeg2video | 有 (99 B) | ✔ (13 K / 150 包) | ✔ | ✔ | `-g 12` → 13 个 I；音频须用 mp2 (mpg 容器限制) |
| test_theora.ogv | — | libtheora | — | — | — | — | **未生成**: 本机 ffmpeg 无 `libtheora` 编码器（只有解码器） |
| test_av1.mp4 | mp4 | libsvtav1 (av1) | 无 (AV1 无 B 帧概念，ffprobe 全报 P) | ✔ (5 K / 150 包) | ✘ | ✘ | 本机无 `libaom-av1`，自动降级 `libsvtav1` (`-preset 8`) |
| test_h263.mov | mov | h263p (H.263+) | 无 (标准 H.263 无 B 帧) | ✔ (16 K / 150 包) | ✔ | ✔ | baseline `h263` 只支持固定尺寸 (如 352x288)，640x360 须用 `h263p`；mov 容器报 `MS style video codec tag` 警告但可正常解码 |
| test_vp6.flv | — | vp6f | — | — | — | — | **未生成**: 上游 ffmpeg 已无 vp6 系列编码器（只有 `vp6/vp6a/vp6f` 解码器） |
| test_vp8.webm | webm | libvpx (vp8) | 无 (金帧/alt-ref 都报 P) | ✔ (7 K / 150 包) | ✘ | ✘ | scenecut 使关键帧 5→7；音频 `libopus` |
| test_vp9.webm | webm | libvpx-vp9 (vp9) | 无 (alt-ref 帧报 P) | ✔ (5 K / 150 包) | ✘ | ✘ | `-bf 3` 对 vp9 实为 alt-ref 机制；音频 `libopus` |

图例: ✔ = 该编码器/解码器组合原生支持；✘ = 不支持（见第 3 节方法说明）。

## 2. 帧类型分布（`ffprobe -show_frames pict_type`，150 帧/片）

| 测试片 | I | P | B |
|---|---|---|---|
| test_avc.mp4 | 6 | 56 | 88 |
| test_hevc.mp4 | 5 | 46 | 99 |
| test_mpeg2.mpg | 13 | 38 | 99 |
| test_av1.mp4 | 5 | 145 | 0 |
| test_h263.mov | 16 | 134 | 0 |
| test_vp8.webm | 7 | 143 | 0 |
| test_vp9.webm | 5 | 145 | 0 |

注：`nb_frames` 字段 mpeg2/vp8/vp9 报 `N/A`（容器不写帧数），以 packet/frame 实际计数 150 为准。

## 3. 探测方法（可复现）

```bash
S=tools/samples/test_avc.mp4
# 流信息
ffprobe -hide_banner -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,nb_frames,avg_frame_rate,pix_fmt -of default=noprint_wrappers=1 $S
# 包 flags (K=关键帧; 本批均为干净编码，无 D/C)
ffprobe -hide_banner -v error -select_streams v:0 -show_entries packet=flags -of csv $S | sort | uniq -c
# 帧类型分布
ffprobe -hide_banner -v error -select_streams v:0 -show_entries frame=pict_type -of csv $S | sort | uniq -c
# qp 原生: 解码器文本 dump 是否含 "New frame, type:"
ffmpeg -hide_banner -v debug -debug qp -i $S -t 1 -an -f null - 2>&1 | grep -c "New frame, type:"
# mv 原生: 见下
```

### 关于 `-debug mv`（重要：ffmpeg 9 已移除该 flag）

`ffmpeg -v debug -debug mv` 在 ffmpeg 9 对**所有**解码器报
`[Eval] Undefined constant or missing '(' in 'mv'` —— `mv` 已不是合法的
`-debug` flag 名（可用 `pict`、`mb_type` 等仍合法），故该命令无法作为 mv
判定依据。现代等价物是 `-flags2 +export_mvs`（帧 side data）：

```bash
ffprobe -hide_banner -v error -flags2 +export_mvs -select_streams v:0 -show_frames -of json $S | grep -c "Motion vectors"
```

实测：h264 / mpeg2video / h263 系解码器对 P/B 帧导出 `Motion vectors`
side data（avc 144 帧、mpeg2 136 帧、h263 134 帧 ≈ 全部非 I 帧）；
**hevc / av1 / vp8 / vp9 原生解码器不支持 mv 导出（0 帧）**。
上表 “mv 原生” 列即按此口径填写。

## 4. 自动化回归

`tests/test_codecs.py`（仅标准库 + subprocess，无 pytest 也可跑）遍历
`tools/samples/` 下已存在的视频，断言：总帧数 > 0、至少 1 个关键帧、
包 dts 单调、pts 无重复；并打印每片 I/P/B 分布：

```bash
python3 tests/test_codecs.py        # 或: pytest tests/test_codecs.py -v
```
