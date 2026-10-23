# MPEG-2 示例视频集

目录：`tools/samples/`（gitignore，本地按需生成/下载）。环境：ffmpeg / ffprobe **9.0.2**
（`/opt/homebrew/bin`）。本地生成片均为 PAL 尺寸 **720x576 / 25fps / 4s（100 帧）**，
`testsrc2` 运动 + 每 2.5s 一次整帧红闪充当场景切换（与 `tools/make_test_videos.sh` 同套路）。

## 1. 清单（ffprobe 实测）

| 文件 | 大小 | 时长 | 分辨率/帧率 | profile | pix_fmt | field_order | 帧级交错 | I/P/B | 来源 |
|---|---|---|---|---|---|---|---|---|---|
| `test_mpeg2_main_420_cbr.mpg` | 3041280 B (2.9MB) | 4.0s | 720x576 @25 | Main | yuv420p | progressive | 100/100 progressive | 9 / 25 / 66 | 本地生成，CBR 6M |
| `test_mpeg2_422_vbr.mpg` | 3883008 B (3.7MB) | 4.0s | 720x576 @25 | 4:2:2 | yuv422p | progressive | 100/100 progressive | 9 / 25 / 66 | 本地生成，VBR 8M |
| `test_mpeg2_main_interlaced.mpg` | 2990080 B (2.9MB) | 4.0s | 720x576 @25 | Main | yuv420p | **tt** | **100/100 interlaced, top_field_first=1** | 9 / 25 / 66 | 本地生成，`-flags +ildct+ilme` |
| `test_mpeg2_dvd_vts06.vob` | 7128912 B (6.8MB) | 38.7s | 720x480 @29.97 | Main | yuv420p | **tt** | 89/89 interlaced (全 I，DVD 菜单静帧) | 89 / 0 / 0 | 真实 DVD（见第 3 节） |

单个均 < 12MB。CBR/VBR 区分证据：CBR 片流 `bit_rate=6000000`（钳位生效）；
VBR 片流 `bit_rate=N/A`（`-b:v` 仅作目标）；视频包大小离散度 CBR
（mean 29595 / stdev 9437）小于同内容 VBR 422（mean 38061 / stdev 12807，
含 422 像素格式本身码率更高）。

## 2. 本地生成命令

```bash
# 公共素材（4s, 720x576, 25fps；VF1=CBR/422 共用，VF2=交错片多一级 setfield）
VF="testsrc2=size=720x576:rate=25:duration=4,drawbox=c=red:t=fill:enable='lt(mod(t+1.25,2.5),0.034)':x=0:y=0:w=iw:h=ih"
AF="sine=frequency=440:duration=4:sample_rate=44100"

# (1) Main + 420 + CBR 6M
ffmpeg -hide_banner -y -f lavfi -i "$VF,format=yuv420p" -f lavfi -i "$AF" \
  -t 4 -r 25 -c:v mpeg2video -pix_fmt yuv420p -g 12 -bf 2 \
  -b:v 6M -minrate 6M -maxrate 6M -bufsize 2M -c:a mp2 -b:a 128k \
  tools/samples/test_mpeg2_main_420_cbr.mpg

# (2) 4:2:2 + VBR 8M（422 profile 由 -pix_fmt yuv422p 自动触发，无需 -profile）
ffmpeg -hide_banner -y -f lavfi -i "$VF,format=yuv422p" -f lavfi -i "$AF" \
  -t 4 -r 25 -c:v mpeg2video -pix_fmt yuv422p -g 12 -bf 2 \
  -b:v 8M -maxrate 9M -bufsize 2M -c:a mp2 -b:a 128k \
  tools/samples/test_mpeg2_422_vbr.mpg

# (3) Main + 交错（-flags +ildct+ilme；lavfi 源是逐行，需 setfield=tff 标记，
#     否则即使加 flags 流仍报 progressive。ffmpeg 9 已无 -top 编码选项，
#     用 setfield 滤镜代替）
ffmpeg -hide_banner -y -f lavfi -i "$VF,format=yuv420p,setfield=tff" -f lavfi -i "$AF" \
  -t 4 -r 25 -flags +ildct+ilme -c:v mpeg2video -pix_fmt yuv420p -g 12 -bf 2 \
  -b:v 6M -maxrate 9M -bufsize 2M -c:a mp2 -b:a 128k \
  tools/samples/test_mpeg2_main_interlaced.mpg
```

注意：

- `-bufsize` 不能单独给（mpeg2video 要求与 `-maxrate` 同给或同不给），
  否则报 `Either both buffer size and max rate or neither must be specified`。
- 交错片曾用 `-top 1` 尝试，ffmpeg 9 报错
  `Codec AVOption top (top field first) is not a encoding option`，改用 `setfield=tff` 后解决。

## 3. 真实广播/DVD 片段

- URL：<https://samples.ffmpeg.org/MPEG-VOB/VTS_06_0.VOB>
  （索引页 <https://samples.ffmpeg.org/MPEG-VOB/>，说明文件
  [`VTS_06_0.VOB.txt`](https://samples.ffmpeg.org/MPEG-VOB/VTS_06_0.VOB.txt)：
  "libmpeg2 reinit's on this file"，源自 mplayer bug 318 的真实 DVD VOB）。
- 本地已下载验证（`curl -sL -o tools/samples/test_mpeg2_dvd_vts06.vob <URL>`，
  7128912 B）：NTSC DVD **720x480 @30000/1001**，Main / yuv420p /
  **field_order=tt**，另含 `dvd_nav_packet` 数据流 + ac3 192k 音频；
  解出 89 帧全为 I（内容为 DVD 菜单静帧，时长 38.7s 系静帧延续），帧级
  `interlaced_frame=1, top_field_first=1`。
- 备选（未下载）：同站 `MPEG-VOB/interlaced/` 下 `lasvegas-vts_01_1.vob`
  （6.3M）、`V.VOB`（10M，场编码交错，说明见 `V.VOB.txt`）。

## 4. 终端证据（ffprobe，含 field_order）

```bash
$ for f in tools/samples/test_mpeg2_main_420_cbr.mpg \
           tools/samples/test_mpeg2_422_vbr.mpg \
           tools/samples/test_mpeg2_main_interlaced.mpg \
           tools/samples/test_mpeg2_dvd_vts06.vob; do
    echo "--- $f"
    ffprobe -hide_banner -v error -select_streams v:0 \
      -show_entries stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate,field_order,bit_rate,duration \
      -of default=noprint_wrappers=1 "$f"
  done
```

```text
--- tools/samples/test_mpeg2_main_420_cbr.mpg
codec_name=mpeg2video
profile=Main
width=720
height=576
pix_fmt=yuv420p
field_order=progressive
avg_frame_rate=25/1
duration=4.000000
bit_rate=6000000
--- tools/samples/test_mpeg2_422_vbr.mpg
codec_name=mpeg2video
profile=4:2:2
width=720
height=576
pix_fmt=yuv422p
field_order=progressive
avg_frame_rate=25/1
duration=4.000000
bit_rate=N/A
--- tools/samples/test_mpeg2_main_interlaced.mpg
codec_name=mpeg2video
profile=Main
width=720
height=576
pix_fmt=yuv420p
field_order=tt
avg_frame_rate=25/1
duration=4.000000
bit_rate=N/A
--- tools/samples/test_mpeg2_dvd_vts06.vob
codec_name=mpeg2video
profile=Main
width=720
height=480
pix_fmt=yuv420p
field_order=tt
avg_frame_rate=30000/1001
duration=38.738700
bit_rate=N/A
```

帧级交错 / 帧类型（`ffprobe -show_entries frame=... -of csv` 后 `sort | uniq -c`）：

```text
test_mpeg2_main_420_cbr.mpg:  100 frame,0,0  (全逐行)； 9 I / 25 P / 66 B
test_mpeg2_422_vbr.mpg:       100 frame,0,0  (全逐行)； 9 I / 25 P / 66 B
test_mpeg2_main_interlaced.mpg: 100 frame,1,1 (全交错+tff)； 9 I / 25 P / 66 B
test_mpeg2_dvd_vts06.vob:       89 frame,I,1,1 (全 I 交错+tff)
```

## 真实内容重转

本目录下 testsrc2 合成的本地变体已用 Sintel 预告片（`tools/samples/test_avc_sintel_trailer.mp4`
第 5~10 秒，真 3D 运镜）重转：`tools/retranscode_from_sintel.sh`，profile×chroma×RC 设置不变，
只换像素源。ffprobe 实测 profile/pix_fmt 与命名一致，分析 I/P/B 正常。
