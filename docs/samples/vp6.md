# VP6 真实示例视频（Flash 时代，下载片）

> 测试片：`tools/samples/harrypotter-480x272-450-vp6.flv`、
> `tools/samples/mrandmrssmith_320x176_200.flv`
> （网上下载的真实 Flash 时代 VP6 片，`tools/samples/` 已 gitignore，不入库）。
> 本机 FFmpeg **无 VP6 编码器**（`ffmpeg -encoders | grep vp6` 无输出，
> 上游已移除 `vp6f` 编码器），只能下载、不能自造；解码器为 `vp6 / vp6a / vp6f`。
> 本机：ffmpeg 9.0.2（`ffmpeg -codecs | grep vp6` 见 §4）。

## 1. 清单（本地 2 片：450kbps / 200kbps 各一）

| 文件 | 来源 URL | 大小 | 视频（实测） | 音频（实测） | 时长/尺寸/帧率 |
|---|---|---|---|---|---|
| `harrypotter-480x272-450-vp6.flv` | `https://samples.ffmpeg.org/FLV/flash8/harrypotter-480x272-450-vp6.flv` | 6046241 B（5.77MB） | `vp6f`（On2 VP6 Flash version），视频码率 460800（~450k），总码率 557045 | mp3，22050Hz 立体声 | 86.833s / 480x272@24，yuv420p |
| `mrandmrssmith_320x176_200.flv` | `https://samples.ffmpeg.org/FLV/flash8/mrandmrssmith_320x176_200.flv` | 4922344 B（4.69MB） | `vp6f`（On2 VP6 Flash version），视频码率 204800（~200k），总码率 260570 | mp3，22050Hz 立体声 | 151.125s / 320x176@24，yuv420p |

来源：FFmpeg 官方样片库 `samples.ffmpeg.org/FLV/flash8/`（Flash 8 时代电影预告片，
文件名自带码率：`450` / `200` 即视频目标码率 kbps，与实测 `bit_rate` 一致）。
单片均 <20MB ✓；两档码率（~450k / ~200k）各一 ✓。

## 2. 实测：I/P/B（`run_analysis`）

| 文件 | I / P / B |
|---|---|
| `harrypotter-480x272-450-vp6.flv` | 45 / 2040 / 0 |
| `mrandmrssmith_320x176_200.flv` | 198 / 3430 / 0 |

说明：全片无 B（VP6 只有 I/P，单 Golden 参考，关键帧即 Golden，
与 `docs/codec-vp.md` / `docs/rates/vp6.md` 一致）；
`altref_markers(frames, codec="vp6")` 只返回 `key` 标记（无 AltRef/compound 判定）。

## 3. 搜过的来源 + 排除项

1. `https://samples.ffmpeg.org/FLV/`：`zelda.flv`（587K）、`zeldaHQ.flv`（4.7M）
   实测为 `flv1`（Sorenson Spark），**非 VP6，已排除**。
2. 同目录 `flash_with_alpha/`、`flash_video_5/`、`myspace/`、`IFTlhxwwkKE.flv`
   （早期 YouTube 风格备份）等多为 flv1/H.263 或 H.264，未采用。
3. 备用同源 VP6：`https://samples.ffmpeg.org/FLV/flash8/artifacts-vp6.flv`
   （2.0M，实测 `vp6f` 512x384@~30fps，未入库，按需自取）。
4. 接入前检查过 `tools/samples/`：当时无任何 VP6 文件（只有自造的
   vp8/vp9/theora/av1/avc/hevc/h263/mpeg2/prores/avs3 片），故本次为新增下载。
5. archive.org 的 Flash 存档、Blender 旧 flv 版：URL 多为整站镜像/种子，
   无稳定单文件直链且体积普遍 >20MB，未采用（ffmpeg 样片库直链更稳定可验）。

## 4. 终端证据（粘贴）

```text
$ ffmpeg -hide_banner -codecs 2>/dev/null | grep -i vp6
 D.V.L. vp6                  On2 VP6
 D.V.L. vp6a                 On2 VP6 (Flash version, with alpha channel)
 D.V.L. vp6f                 On2 VP6 (Flash version)
$ ffmpeg -hide_banner -encoders 2>/dev/null | grep -i vp6
#（无输出：本机无 VP6 编码器，只能下载）

===== tools/samples/harrypotter-480x272-450-vp6.flv =====
6046241 tools/samples/harrypotter-480x272-450-vp6.flv
codec_name=vp6f
codec_long_name=On2 VP6 (Flash version)
width=480
height=272
pix_fmt=yuv420p
avg_frame_rate=24/1
bit_rate=460800
duration=86.833000
size=6046241
bit_rate=557045
===== tools/samples/mrandmrssmith_320x176_200.flv =====
4922344 tools/samples/mrandmrssmith_320x176_200.flv
codec_name=vp6f
codec_long_name=On2 VP6 (Flash version)
width=320
height=176
pix_fmt=yuv420p
avg_frame_rate=24/1
bit_rate=204800
duration=151.125000
size=4922344
bit_rate=260570

tools/samples/harrypotter-480x272-450-vp6.flv I= 45 P= 2040 B= 0
tools/samples/mrandmrssmith_320x176_200.flv I= 198 P= 3430 B= 0
```

下载复现（`tools/samples/` 已 gitignore，不入库）：

```bash
curl -sL -o tools/samples/harrypotter-480x272-450-vp6.flv \
  https://samples.ffmpeg.org/FLV/flash8/harrypotter-480x272-450-vp6.flv
curl -sL -o tools/samples/mrandmrssmith_320x176_200.flv \
  https://samples.ffmpeg.org/FLV/flash8/mrandmrssmith_320x176_200.flv
ffprobe -hide_banner -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,avg_frame_rate,bit_rate \
  -of default=nw=1 tools/samples/harrypotter-480x272-450-vp6.flv \
  tools/samples/mrandmrssmith_320x176_200.flv
```
