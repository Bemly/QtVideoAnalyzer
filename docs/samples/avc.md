# AVC/H.264 示例视频集（profile × chroma × RC）

目录：`tools/samples/`（已 gitignore，不入仓）。本机 ffmpeg 9.0.2 + libx264（x264 core:165）。

| 文件 | 大小 | 时长 | 实测 profile + pix_fmt + RC 痕迹 | 来源 |
|---|---|---|---|---|
| `test_avc_baseline_420.mp4` | 805014 B | 5.00s | `Constrained Baseline` + `yuv420p` + CBR 痕迹：video `bit_rate=1152742`≈目标 1M，`has_b_frames=0`，帧类型 6I/143P/**0B**，pkt CV=0.41 | 本地生成（命令见 §1） |
| `test_avc_main_420_crf.mp4` | 567356 B | 5.00s | `Main` + `yuv420p` + CRF23 痕迹：video `bit_rate=771096`（内容驱动 VBR），`has_b_frames=2`，帧类型 5I/56P/88B，pkt CV=0.49 | 本地生成（命令见 §1） |
| `test_avc_high_422.mp4` | 921022 B | 5.00s | `High 4:2:2` + `yuv422p` + CRF20 痕迹：video `bit_rate=1336912`（422 采样点多，同 CRF 码率高于 420），`has_b_frames=2`，帧类型 5I/57P/87B，pkt CV=0.41 | 本地生成（命令见 §1） |
| `test_avc_sintel_trailer.mp4` | 4372373 B | 52.21s | `High` + `yuv420p` + 真实片 VBR 痕迹：video `bit_rate=537875`，854x480@24，1253 帧，pkt CV=1.28（真实内容摆动大） | https://media.w3.org/2010/05/sintel/trailer.mp4（Blender Sintel 预告片，W3C 托管） |

## 1. 生成命令（在仓库根目录执行）

公共素材：`testsrc2` 640x360@30 5s + 每 2.5s 整帧红闪（场景切换）+ 440Hz 正弦音频（同 `tools/make_test_videos.sh` 配方）：

```bash
VF='testsrc2=size=640x360:rate=30:duration=5,drawbox=c=red:t=fill:enable='"'"'lt(mod(t+1.25,2.5),0.034)'"'"':x=0:y=0:w=iw:h=ih'
AF='sine=frequency=440:duration=5:sample_rate=44100'
OUT=tools/samples

# baseline 420 CBR 1M（-bf 不传：baseline 强制 bframes 0）
ffmpeg -y -f lavfi -i "${VF},format=yuv420p" -f lavfi -i "$AF" -t 5 -r 30 \
  -c:v libx264 -pix_fmt yuv420p -profile:v baseline -preset veryfast -g 30 \
  -b:v 1M -maxrate 1M -bufsize 2M -c:a aac -b:a 128k $OUT/test_avc_baseline_420.mp4

# main 420 CRF 23
ffmpeg -y -f lavfi -i "${VF},format=yuv420p" -f lavfi -i "$AF" -t 5 -r 30 \
  -c:v libx264 -pix_fmt yuv420p -profile:v main -preset veryfast -g 30 -bf 2 \
  -crf 23 -c:a aac -b:a 128k $OUT/test_avc_main_420_crf.mp4

# high422 422 CRF 20（注意末端 format=yuv422p）
ffmpeg -y -f lavfi -i "${VF},format=yuv422p" -f lavfi -i "$AF" -t 5 -r 30 \
  -c:v libx264 -pix_fmt yuv422p -profile:v high422 -preset veryfast -g 30 -bf 2 \
  -crf 20 -c:a aac -b:a 128k $OUT/test_avc_high_422.mp4

# 真实片
curl -sL -o $OUT/test_avc_sintel_trailer.mp4 https://media.w3.org/2010/05/sintel/trailer.mp4
```

## 2. 终端证据（`ffprobe -show_streams` 关键行原文 + 校验统计）

```text
$ for f in test_avc_baseline_420.mp4 test_avc_main_420_crf.mp4 test_avc_high_422.mp4 test_avc_sintel_trailer.mp4; do
>   stat -f%z $f; ffprobe -v error -select_streams v:0 \
>     -show_entries stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate,level,bit_rate,nb_frames \
>     -of default=noprint_wrappers=1 $f; done
805014
codec_name=h264
profile=Constrained Baseline
width=640
height=360
pix_fmt=yuv420p
level=30
avg_frame_rate=30/1
bit_rate=1152742
nb_frames=150
567356
codec_name=h264
profile=Main
width=640
height=360
pix_fmt=yuv420p
level=30
avg_frame_rate=30/1
bit_rate=771096
nb_frames=150
921022
codec_name=h264
profile=High 4:2:2
width=640
height=360
pix_fmt=yuv422p
level=30
avg_frame_rate=30/1
bit_rate=1336912
nb_frames=150
4372373
codec_name=h264
profile=High
width=854
height=480
pix_fmt=yuv420p
level=30
avg_frame_rate=24/1
bit_rate=537875
nb_frames=1253
```

```text
$ ffprobe 帧类型计数 / has_b_frames / 包大小变异系数（RC 痕迹）
test_avc_baseline_420.mp4:  6 I / 143 P / 0 B, has_b_frames=0, pkt n=150 mean=4803B cv=0.41
test_avc_main_420_crf.mp4:   5 I / 56 P / 88 B, has_b_frames=2, pkt n=150 mean=3213B cv=0.49
test_avc_high_422.mp4:       5 I / 57 P / 87 B, has_b_frames=2, pkt n=150 mean=5570B cv=0.41
test_avc_sintel_trailer.mp4: has_b_frames=2, pkt n=1253 mean=2801B cv=1.28
```

注：

- `-profile:v baseline` 实际打出 Constrained Baseline 约束标志（baseline 的约束超集），
  ffprobe 显示 `Constrained Baseline` 属正常；`--bframes 0` 由 profile 强制，无 B 帧即 profile 限制生效的证据。
- RC 痕迹口径：`bit_rate` 取 video stream 项；CV = 视频包大小总体标准差/均值
 （`ffprobe -show_entries packet=size`）；5s 合成片内容单一，CBR/CRF 的 CV 差异不如真实片明显，
  故 CBR 以"码率≈目标 + maxrate/bufsize 限幅设定"为判据，CRF 以"内容驱动码率 + B 帧占比"为判据。
