# Theora 真实示例片清单

> 本机 ffmpeg 9 无 `libtheora` 编码器（`ffmpeg -encoders | grep theora` 无输出），
> 无法自制 Theora 测试片，故下载真实 `.ogv` 存 `tools/samples/`（该目录已 gitignore）。
> 三档按实测 overall 码率命名，全部 `theora + yuv420p`，单个 <30MB。

## 1. 清单

| 文件 | 来源 | 分辨率/帧率 | 时长 | 大小 | 实测码率 overall |
|---|---|---|---|---|---|
| `test_theora_600k.ogv` | Wikimedia Commons：农场筒仓 640x480 低质量版 | 640x480 @30fps | 254s | 17.93MB | 592 kbps |
| `test_theora_1M.ogv` | Wikimedia Commons：Big Buck Bunny 预告片 400p | 720x400 @25fps | 33s | 4.16MB | 1057 kbps |
| `test_theora_3M.ogv` | Xiph 官方测试集：stockholm VFR | 1280x720（VFR） | 5.0s | 1.79MB | 3011 kbps（纯视频，无音频轨） |

下载 URL（直链）：

- `test_theora_600k.ogv` ← https://upload.wikimedia.org/wikipedia/commons/4/42/Silo_filling_640x480_VidQual-0.ogv
  （说明页 https://commons.wikimedia.org/wiki/File:Silo_filling_640x480_VidQual-0.ogv ，CC BY-SA 3.0）
- `test_theora_1M.ogv` ← https://upload.wikimedia.org/wikipedia/commons/b/b3/Big_Buck_Bunny_Trailer_400p.ogv
  （说明页 https://commons.wikimedia.org/wiki/File:Big_Buck_Bunny_Trailer_400p.ogv ，Blender Foundation，CC BY 3.0）
- `test_theora_3M.ogv` ← https://media.xiph.org/video/tests/theora/stockholm-vfr.ogg
  （目录索引 https://media.xiph.org/video/tests/theora/ ，Xiph.org Test Media）

复现下载：

```sh
cd tools/samples
curl -sL -o test_theora_600k.ogv "https://upload.wikimedia.org/wikipedia/commons/4/42/Silo_filling_640x480_VidQual-0.ogv"
curl -sL -o test_theora_1M.ogv "https://upload.wikimedia.org/wikipedia/commons/b/b3/Big_Buck_Bunny_Trailer_400p.ogv"
curl -sL -o test_theora_3M.ogv "https://media.xiph.org/video/tests/theora/stockholm-vfr.ogg"
```

备选（已验证 theora+yuv420p，同约 0.5M 档，与 600k 档位重复故未收录）：
`https://media.xiph.org/video/tests/theora/320x240.ogv`（320x240，590 kbps，0.3MB）、
`https://media.xiph.org/video/tests/theora/sign_irene_cif-3qi-b.ogg`（352x288，503 kbps，1.3MB）。
`ducks_take_off_444_720p25.ogg` 为 4:4:4，不符合 420 口径，未选。
archive.org 的 Theora 衍生片（ElephantsDream `ed_hd.ogv` 45MB、Sintel 69MB、BBB 全片 >150MB）
均超 30MB 上限，未选。

## 2. ffprobe 实测（codec / pix_fmt / 码率）

```text
===== tools/samples/test_theora_600k.ogv
codec_name=theora
width=640
height=480
pix_fmt=yuv420p
avg_frame_rate=30/1
duration=254.066667
format_name=ogg
duration=254.118957
size=18804765
bit_rate=591998
===== tools/samples/test_theora_1M.ogv
codec_name=theora
width=720
height=400
pix_fmt=yuv420p
avg_frame_rate=25/1
duration=32.520000
format_name=ogg
duration=32.996875
size=4360399
bit_rate=1057166
===== tools/samples/test_theora_3M.ogv
codec_name=theora
width=1280
height=720
pix_fmt=yuv420p
avg_frame_rate=120/1
duration=4.975000
format_name=ogg
duration=4.975000
size=1872564
bit_rate=3011158
```

命令：

```sh
for f in tools/samples/test_theora_600k.ogv tools/samples/test_theora_1M.ogv tools/samples/test_theora_3M.ogv; do
  ffprobe -hide_banner -v error -select_streams v:0 \
    -show_entries stream=codec_name,pix_fmt,width,height,avg_frame_rate,duration \
    -of default=noprint_wrappers=1 "$f"
  ffprobe -hide_banner -v error \
    -show_entries format=format_name,bit_rate,duration,size \
    -of default=noprint_wrappers=1 "$f"
done
ffmpeg -hide_banner -v error -i tools/samples/test_theora_600k.ogv -map 0:v:0 -f null - && echo DECODE_OK
ffmpeg -hide_banner -v error -i tools/samples/test_theora_1M.ogv -map 0:v:0 -f null - && echo DECODE_OK
ffmpeg -hide_banner -v error -i tools/samples/test_theora_3M.ogv -map 0:v:0 -f null - && echo DECODE_OK
# 三个均输出 DECODE_OK
```

结论：三片视频轨均为 `codec_name=theora`、`pix_fmt=yuv420p`，容器 `ogg`，
码率三档 0.6M / 1.1M / 3.0M 互不重叠，可作低/中/高三档测试片。
