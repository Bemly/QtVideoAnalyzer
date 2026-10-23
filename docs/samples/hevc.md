# HEVC/H.265 示例视频集（profile × 位深 × RC）

目录：`tools/samples/`（已 gitignore，不入仓）。本机 ffmpeg 9.0.2 + x265 4.3+1-e9b8812（8bit+10bit+12bit）。

| 文件 | 大小 | 时长 | 实测 profile + pix_fmt + RC 痕迹 | 来源 |
|---|---|---|---|---|
| `test_hevc_main_420.mp4` | 461527 B | 5.00s | `Main` + `yuv420p` + CRF28 痕迹：video `bit_rate=597158`（内容驱动 VBR），`has_b_frames=2`，帧类型 5I/46P/**99B**，pkt CV=0.60 | 本地生成（命令见 §1） |
| `test_hevc_main10_420.mp4` | 458948 B | 5.00s | `Main 10` + `yuv420p10le` + CRF28 痕迹：video `bit_rate=593046`，`has_b_frames=2`，帧类型 5I/46P/**99B**，pkt CV=0.62 | 本地生成（命令见 §1） |
| `test_hevc_main422_10.mp4` | 512751 B | 5.00s | `Rext`（= Main422-10，见注）+ `yuv422p10le` + CRF28 痕迹：video `bit_rate=679134`（422 采样点多，同 CRF 码率高于 420），`has_b_frames=2`，帧类型 5I/46P/**99B**，pkt CV=0.67 | 本地生成（命令见 §1） |
| `test_hevc_main_cbr.mp4` | 1959461 B | 5.00s | `Main` + `yuv420p` + CBR 痕迹：video `bit_rate=2995905`≈目标 3M，`has_b_frames=0`（zerolatency 置零 B 帧），帧类型 5I/145P/**0B**，pkt CV=0.15（削峰填谷，明显平于 CRF 档） | 本地生成（命令见 §1） |
| `test_hevc_jellyfish_1080p.mp4` | 1056268 B | 10.00s | `Main` + `yuv420p` + 真实片 VBR 痕迹：video `bit_rate=839637`，1920x1080@30，300 帧，帧类型 2I/70P/**228B**，pkt CV=1.03（真实内容摆动大） | https://test-videos.co.uk/jellyfish/mp4-h265（Jellyfish H.265 1MB 档，源 http://www.jell.yfish.us/ ） |
| 远程 4K（URL only，147MB > 50MB 不下载） | 147414166 B | 29.95s | `Main 10` + `yuv420p10le`，3840x2160@60，video `bit_rate=39373532` | `https://syd1.mirror.jellyfin.org/test-videos/SDR/HEVC%2010bit/Test%20Jellyfin%204K%20HEVC%2010bit%2040M.mp4`（Jellyfin 官方测试片镜像；同目录另有 50–150M / 8bit 档） |

## 1. 生成命令（在仓库根目录执行）

公共素材：`testsrc2` 640x360@30 5s + 每 2.5s 整帧红闪（场景切换）+ 440Hz 正弦音频（同 `tools/make_test_videos.sh` 配方）：

```bash
VF='testsrc2=size=640x360:rate=30:duration=5,drawbox=c=red:t=fill:enable='"'"'lt(mod(t+1.25,2.5),0.034)'"'"':x=0:y=0:w=iw:h=ih'
AF='sine=frequency=440:duration=5:sample_rate=44100'
OUT=tools/samples

# main 420 8bit CRF 28
ffmpeg -y -f lavfi -i "${VF},format=yuv420p" -f lavfi -i "$AF" -t 5 -r 30 \
  -c:v libx265 -pix_fmt yuv420p -profile:v main -preset veryfast -g 30 -bf 2 \
  -crf 28 -c:a aac -b:a 128k $OUT/test_hevc_main_420.mp4

# main10 420 10bit CRF 28
ffmpeg -y -f lavfi -i "${VF},format=yuv420p" -f lavfi -i "$AF" -t 5 -r 30 \
  -c:v libx265 -pix_fmt yuv420p10le -profile:v main10 -preset veryfast -g 30 -bf 2 \
  -crf 28 -c:a aac -b:a 128k $OUT/test_hevc_main10_420.mp4

# main422-10（-pix_fmt 落档，不加 -profile:v；x265 无此强制档）
ffmpeg -y -f lavfi -i "${VF},format=yuv420p" -f lavfi -i "$AF" -t 5 -r 30 \
  -c:v libx265 -pix_fmt yuv422p10le -preset veryfast -g 30 -bf 2 \
  -crf 28 -c:a aac -b:a 128k $OUT/test_hevc_main422_10.mp4

# main CBR 3M + VBV（直播档；-tune zerolatency 强制 bframes=0，故不加 -bf 2，否则打不开编码器）
ffmpeg -y -f lavfi -i "${VF},format=yuv420p" -f lavfi -i "$AF" -t 5 -r 30 \
  -c:v libx265 -pix_fmt yuv420p -preset veryfast -tune zerolatency \
  -b:v 3M -maxrate 3M -bufsize 6M -x265-params strict-cbr=1 -g 30 \
  -c:a aac -b:a 128k $OUT/test_hevc_main_cbr.mp4

# 真实片（小文件直接下；4K 147MB 只记 URL）
curl -sL -o $OUT/test_hevc_jellyfish_1080p.mp4 \
  https://test-videos.co.uk/vids/jellyfish/mp4/h265/1080/Jellyfish_1080_10s_1MB.mp4
```

## 2. 终端证据（`ffprobe -show_streams` 关键行原文 + 校验统计）

```text
$ for f in test_hevc_main_420.mp4 test_hevc_main10_420.mp4 test_hevc_main422_10.mp4 \
    test_hevc_main_cbr.mp4 test_hevc_jellyfish_1080p.mp4; do
>   stat -f%z $f; ffprobe -v error -select_streams v:0 \
>     -show_entries stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate,level,bit_rate,nb_frames \
>     -of default=noprint_wrappers=1 $f; done
461527
codec_name=hevc
profile=Main
width=640
height=360
pix_fmt=yuv420p
level=63
avg_frame_rate=30/1
bit_rate=597158
nb_frames=150
458948
codec_name=hevc
profile=Main 10
width=640
height=360
pix_fmt=yuv420p10le
level=63
avg_frame_rate=30/1
bit_rate=593046
nb_frames=150
512751
codec_name=hevc
profile=Rext
width=640
height=360
pix_fmt=yuv422p10le
level=63
avg_frame_rate=30/1
bit_rate=679134
nb_frames=150
1959461
codec_name=hevc
profile=Main
width=640
height=360
pix_fmt=yuv420p
level=63
avg_frame_rate=30/1
bit_rate=2995905
nb_frames=150
1056268
codec_name=hevc
profile=Main
width=1920
height=1080
pix_fmt=yuv420p
level=120
avg_frame_rate=30/1
bit_rate=839637
nb_frames=300
```

```text
$ ffprobe 帧类型计数 / has_b_frames / 包大小变异系数（RC 痕迹）
test_hevc_main_420.mp4:      5 I / 46 P / 99 B, has_b_frames=2, pkt n=150 mean=2488B cv=0.60
test_hevc_main10_420.mp4:    5 I / 46 P / 99 B, has_b_frames=2, pkt n=150 mean=2471B cv=0.62
test_hevc_main422_10.mp4:    5 I / 46 P / 99 B, has_b_frames=2, pkt n=150 mean=2830B cv=0.67
test_hevc_main_cbr.mp4:      5 I / 145 P / 0 B, has_b_frames=0, pkt n=150 mean=12483B cv=0.15
test_hevc_jellyfish_1080p.mp4: 2 I / 70 P / 228 B, has_b_frames=2, pkt n=300 mean=3498B cv=1.03
```

```text
$ curl -sI "https://syd1.mirror.jellyfin.org/test-videos/SDR/HEVC%2010bit/Test%20Jellyfin%204K%20HEVC%2010bit%2040M.mp4" \
    | grep -i "HTTP\|content-length"
HTTP/1.1 200 OK
Content-Length: 147414166
$ ffprobe -v error -show_entries stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate \
    -of default=noprint_wrappers=1 "<上址>"   # 仅读头，不下载全片
codec_name=hevc
profile=Main 10
width=3840
height=2160
pix_fmt=yuv420p10le
avg_frame_rate=60/1
bit_rate=39373532
duration=29.950000
size=147414166
```

注：

- ffprobe 对 422/10bit 报 `profile=Rext`（Range Extension 合集档）属正常；
  x265 `--profile` 只支持 `main / main10 / mainstillpicture`，
  422 系靠 `-pix_fmt yuv422p10le` 间接落到 Main422-10（见 `docs/rates/hevc.md` §0–§1）。
- RC 痕迹口径：`bit_rate` 取 video stream 项；CV = 视频包大小总体标准差/均值
  （`ffprobe -show_entries packet=size`）；CBR 以"码率≈目标 + maxrate/bufsize 限幅设定 +
  CV 明显压平"为判据，CRF 以"内容驱动码率 + B 帧占比"为判据。
- CBR 初版同时加了 `-tune zerolatency` 与 `-bf 2`，libx265 报
  `Could not open encoder before EOF (-22)` 且输出 0 字节；
  zerolatency 强制 `bframes=0`，二者互斥，去掉 `-bf 2` 后通过。
- 关于 Blender Tears of Steel：官方 4K 版是 **H.264** `.mov`（6.3GB，
  `https://mango.blender.org/download`），**无官方 HEVC 版**，
  故用 Jellyfin 4K HEVC-10bit（真实 4K HEVC）+ Jellyfish H.265（真实 HEVC 自然内容）代替。
