# VP9 示例视频集（profile × RC）

> 测试片：`tools/samples/test_vp9_*.webm`（本地 `libvpx-vp9` 生成，`tools/samples/` 已 gitignore，不入库）。
> 同源：`testsrc2` 640x360 30fps 5s + 每 2.5s 整帧红闪（≈1 帧场景切换）+ `sine` 440Hz 音频，
> 与 `tools/make_test_videos.sh` 同配方（`format` 按 profile 换位深/采样）。
> 本机：ffmpeg 9.0.2 / libvpx（`ffmpeg -h encoder=libvpx-vp9`）。

## 1. 清单（本地 3 片：P0/P1/P2 × CBR/VBR/CQ）

| 文件 | profile（实测） | pix_fmt（实测） | RC | 码率设置 | 时长/尺寸 | 大小 |
|---|---|---|---|---|---|---|
| `test_vp9_p0_cbr.webm` | Profile 0（`vp09.00.21.08`） | yuv420p | CBR 2M | `-b:v 2M -minrate 2M -maxrate 2M -bufsize 4M` | 5.008s / 640x360@30 | 1280500 B（1.22MB） |
| `test_vp9_p2_10bit.webm` | Profile 2（`vp09.02.21.10`） | yuv420p10le | VBR ~2M 上限 | `-b:v 2M`（单遍 VBR，实测均值 1.43M） | 5.008s / 640x360@30 | 896006 B（0.85MB） |
| `test_vp9_p1_444.webm` | Profile 1（`vp09.01.21.08`） | yuv444p | CQ crf30 | `-crf 30 -b:v 0`（恒质量，实测均值 2.55M） | 5.008s / 640x360@30 | 1597209 B（1.52MB） |

profile ↔ 格式对照（`webmproject.org/vp9/profiles`）：P0 = 8bit 4:2:0，
P1 = 8bit 4:2:2/4:4:4，P2 = 10/12bit 4:2:0，P3 = 10/12bit 4:2:2/4:4:4（本次未造 P3）。
单片均 <10MB ✓。

## 2. 实测：I/P/B + AltRef 数（`run_analysis` + `altref_markers(frames,'vp9')`）

| 文件 | I / P / B | key（帧号） | altref（帧号，启发式 `packet_size > 1.8×P均值`） |
|---|---|---|---|
| `test_vp9_p0_cbr.webm` | 5 / 145 / 0 | 5：`[0,30,60,90,120]`（`-g 30`） | **1**：`[39]` |
| `test_vp9_p2_10bit.webm` | 5 / 145 / 0 | 5：`[0,30,60,90,120]` | **5**：`[10,20,40,50,100]` |
| `test_vp9_p1_444.webm` | 5 / 145 / 0 | 5：`[0,30,60,90,120]` | **0**：`[]` |

说明：

1. 全片无 B（VP9 无重排 B 帧，AltRef/compound 仍报 P，与 `docs/codec-vp.md` 一致）。
2. CQ 片 altref=0 是**启发式判出 0**，不是“编码器没用 AltRef”：
   CQ 码率平稳、无显著大 P 包，`>1.8×P均值` 阈值一个不中；
   另单遍 CQ 下 `auto-alt-ref` 本就受限（libvpx 选项注明 2-pass only）。
3. 三片 `-g 30`，key 严格落在 30 帧 GOP 边界；红闪（2.5s≈75帧周期）未触发额外 scenecut I。

## 3. 网上真实 VP9 片（大文件只记 URL，不入库）

1. **YouTube 4K 样片**：`COSTA RICA IN 4K 60fps HDR (ULTRA HD)`（Jacob + Katie Schwarz，
   2018-06-13 重制 HDR 重传，`https://www.youtube.com/watch?v=LXb3EKWsInQ`）。
   YouTube 自 2014-06 起对 4K 频道部署 VP9 承播（YouTube × RED 公告），
   该片 4K 档（itag 313/315/308 系）即 VP9。按需自取（大文件不入库）：
   `yt-dlp -f 'bv*[vcodec^=vp9]' 'https://www.youtube.com/watch?v=LXb3EKWsInQ'`。
2. **WebM 真实片直链**：Wikimedia Commons `File:Big Buck Bunny alt.webm`
   （Blender Foundation CC-BY，VP9 + Opus，1280x720@24，9:57，93MB——大文件只记 URL）：
   `https://upload.wikimedia.org/wikipedia/commons/8/88/Big_Buck_Bunny_alt.webm`
   （文件页：`https://commons.wikimedia.org/wiki/File:Big_Buck_Bunny_alt.webm`，
   API 实测 `video: V_VP9 1280x720 24fps / audio: A_OPUS 48kHz stereo`）。
3. **小型可验证 WebM fixture**（testfiles.dev，2026-07-19 verified，VP9/Opus）：
   `https://assets.testfiles.dev/video/sample-3s.webm`
   （640x360，2.999s，195147 B，sha256 `db93d141…693d`——与发布值逐字节一致，
   本地已 `curl` 到 `/tmp` 验证：`vp9 / Profile 0 / yuv420p`，见 §5）。

## 4. 生成命令（复现）

```bash
DUR=5; W=640; H=360; FPS=30; AF="sine=frequency=440:duration=${DUR}:sample_rate=44100"
mkvf() { echo "testsrc2=size=${W}x${H}:rate=${FPS}:duration=${DUR},drawbox=c=red:t=fill:enable='lt(mod(t+1.25,2.5),0.034)':x=0:y=0:w=iw:h=ih,format=$1"; }
# P0 yuv420p CBR 2M
ffmpeg -hide_banner -y -f lavfi -i "$(mkvf yuv420p)" -f lavfi -i "$AF" -t $DUR -r $FPS \
  -c:v libvpx-vp9 -pix_fmt yuv420p -b:v 2M -minrate 2M -maxrate 2M -bufsize 4M \
  -g 30 -auto-alt-ref 1 -lag-in-frames 25 -cpu-used 4 -c:a libopus -b:a 96k \
  tools/samples/test_vp9_p0_cbr.webm
# P2 yuv420p10le VBR
ffmpeg -hide_banner -y -f lavfi -i "$(mkvf yuv420p10le)" -f lavfi -i "$AF" -t $DUR -r $FPS \
  -c:v libvpx-vp9 -pix_fmt yuv420p10le -b:v 2M \
  -g 30 -auto-alt-ref 1 -lag-in-frames 25 -cpu-used 4 -c:a libopus -b:a 96k \
  tools/samples/test_vp9_p2_10bit.webm
# P1 yuv444p CQ
ffmpeg -hide_banner -y -f lavfi -i "$(mkvf yuv444p)" -f lavfi -i "$AF" -t $DUR -r $FPS \
  -c:v libvpx-vp9 -pix_fmt yuv444p -crf 30 -b:v 0 \
  -g 30 -auto-alt-ref 1 -lag-in-frames 25 -cpu-used 4 -c:a libopus -b:a 96k \
  tools/samples/test_vp9_p1_444.webm
```

## 5. 终端证据（粘贴）

```text
===== tools/samples/test_vp9_p0_cbr.webm =====
size: 1280500 bytes
codec_name=vp9
profile=Profile 0
width=640
height=360
pix_fmt=yuv420p
avg_frame_rate=30/1
duration=5.008000
size=1280500
bit_rate=2045527
===== tools/samples/test_vp9_p2_10bit.webm =====
size: 896006 bytes
codec_name=vp9
profile=Profile 2
width=640
height=360
pix_fmt=yuv420p10le
avg_frame_rate=30/1
duration=5.008000
size=896006
bit_rate=1431319
===== tools/samples/test_vp9_p1_444.webm =====
size: 1597209 bytes
codec_name=vp9
profile=Profile 1
width=640
height=360
pix_fmt=yuv444p
avg_frame_rate=30/1
duration=5.008000
size=1597209
bit_rate=2551452

== tools/samples/test_vp9_p0_cbr.webm
codec_name=vp9
profile=Profile 0
mime_codec_string=vp09.00.21.08
pix_fmt=yuv420p
== tools/samples/test_vp9_p2_10bit.webm
codec_name=vp9
profile=Profile 2
mime_codec_string=vp09.02.21.10
pix_fmt=yuv420p10le
== tools/samples/test_vp9_p1_444.webm
codec_name=vp9
profile=Profile 1
mime_codec_string=vp09.01.21.08
pix_fmt=yuv444p

tools/samples/test_vp9_p0_cbr.webm
  I=5 P=145 B=0
  key: 5 [0, 30, 60, 90, 120]
  altref: 1 [39]
tools/samples/test_vp9_p2_10bit.webm
  I=5 P=145 B=0
  key: 5 [0, 30, 60, 90, 120]
  altref: 5 [10, 20, 40, 50, 100]
tools/samples/test_vp9_p1_444.webm
  I=5 P=145 B=0
  key: 5 [0, 30, 60, 90, 120]
  altref: 0 []

# 网上小 fixture（/tmp 验证，逐字节命中发布 sha256）：
-rw-r--r--  1 bemly  wheel  195147 Oct 23 15:27 net_sample_vp9.webm
codec_name=vp9
profile=Profile 0
width=640
height=360
pix_fmt=yuv420p
avg_frame_rate=0/0
duration=2.999312
size=195147
bit_rate=520511
db93d14148c47a3753a335ba6ff18a51f069531b3b87c6fc9bf5939373ca963d  net_sample_vp9.webm
```
