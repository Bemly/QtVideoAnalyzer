# VP8 示例视频集（RC × AltRef）

> 测试片：`tools/samples/test_vp8_*.webm`（本地 `libvpx` 生成，`tools/samples/` 已 gitignore，不入库）。
> 同源：`testsrc2` 640x360 30fps 4s + 每 2.5s 整帧红闪（≈1 帧场景切换）+ `sine` 440Hz 音频，
> 与 `tools/make_test_videos.sh` 同配方（`DUR=4`），`format=yuv420p`（VP8 只吃 420，见 `docs/rates/vp8.md`）。
> 本机：ffmpeg 9.0.2 / libvpx v1.17.0（`ffmpeg -h encoder=libvpx`）。
> 另有真实片 `test_vp8_realworld_tos.webm`（Wikimedia 直链下载，见 §3，也放 `tools/samples/`，不入库）。

## 1. 清单（本地 3 片：CBR / VBR 2-pass / CQ × AltRef 开关）

| 文件 | profile（实测） | pix_fmt（实测） | RC | AltRef | 时长/尺寸 | 大小 |
|---|---|---|---|---|---|---|
| `test_vp8_cbr_realtime.webm` | 0 | yuv420p | CBR 1.5M | **关**（`-lag-in-frames 0 -auto-alt-ref 0`） | 4.008s / 640x360@30 | 794164 B（0.76MB） |
| `test_vp8_vbr_2pass.webm` | 0 | yuv420p | VBR 2M 2-pass | **开**（`-lag-in-frames 25 -auto-alt-ref 1`） | 4.008s / 640x360@30 | 884505 B（0.84MB） |
| `test_vp8_cq.webm` | 0 | yuv420p | CQ crf10（`-b:v 0`） | **开**（`-lag-in-frames 25 -auto-alt-ref 1`） | 4.008s / 640x360@30 | 193229 B（0.19MB） |
| `test_vp8_realworld_tos.webm` | 0 | yuv420p | 真实片（libvpx 2-pass ABR，见 §3） | **开**（实测 73 个大 P 痕迹） | 33.2s / 960x400@25 | 855189 B（0.81MB） |

单片均 <8MB ✓。VP8 无 profile 选项（RFC 6386 码流头 2 bit），ffprobe 全报 `profile=0`（WebM 默认）。

## 2. 实测：I/P/B + AltRef 数（`run_analysis` + `altref_markers(frames,'vp8')`）

| 文件 | I / P / B | key（帧号） | altref（帧号，启发式 `packet_size > 1.8×P均值`） |
|---|---|---|---|
| `test_vp8_cbr_realtime.webm` | 4 / 116 / 0（120 包） | 4：`[0,30,60,90]`（`-g 30`，严格 GOP 边界） | **1**：`[114]`（红闪场景大包误触，非真 AltRef，见说明 2） |
| `test_vp8_vbr_2pass.webm` | 4 / 122 / 0（126 包） | 4：`[0,31,63,94]`（≈32 帧 GOP，2-pass 偏移 1 帧） | **4**：`[42,64,95,111]`（周期大 P = AltRef ✓） |
| `test_vp8_cq.webm` | 6 / 114 / 0（120 包） | 6：`[0,30,38,68,98,113]`（`-g 30` + 红闪 scenecut≈38/113） | **13**：`[7,16,25,37,45,52,62,75,84,93,105,112,114]` |
| `test_vp8_realworld_tos.webm` | 11 / 866 / 0（877 包） | 11：`[0,76,178,277,292,316,418,519,593,667,771]` | **73**（约每 15 帧一个，含切换处连判簇如 293–302） |

说明：

1. 全片无 B（VP8 Golden/AltRef 都报 P，无重排 B 帧，与 `docs/codec-vp.md` 一致）。
2. CBR 片 AltRef 已关（`lag 0 + auto-alt-ref 0`），唯一的 `altref=[114]`
   是红闪场景帧包过大触发阈值——**启发式误触**，不是编码器真发了 AltRef。
   反之 VBR/CQ 开 AltRef 的片分别有 4/13 个，开关对照成立。
3. VBR 片 126 包（4s@30 应为 120）：libvpx 2-pass pass2 报
   `Mismatching timestamps` 时间戳 quirk，多出数包，不影响 I/P/B 与 AltRef 结论。
4. 真实 ToS 片本身就是 libvpx 2-pass ABR 编码（§3），73 个大 P 痕迹与“VBR 开 AltRef”一致；
   场景硬切处阈值连判成簇（如 293–302）是本工具启发式的已知行为（只看包大小，不解析码流）。

## 3. 网上真实 VP8 片（小文件已下载到 `tools/samples/`，不入库）

**Wikimedia Commons `File:VP8 low bitrate test ToS.webm`**（Blender Foundation Mango 项目《Tears of Steel》片段，
CC BY 3.0；libvpx 1.5 2-pass ABR ~0.0214 bpp，与 §1 的 VBR 档同类工艺，可对照）：

- 文件页：`https://commons.wikimedia.org/wiki/File:VP8_low_bitrate_test_ToS.webm`
- 直链：`https://upload.wikimedia.org/wikipedia/commons/c/ca/VP8_low_bitrate_test_ToS.webm`
  （855189 B，960x400@25，33.2s，`video/webm`，API 实测见 §5）
- 下载：`curl -sSL -o tools/samples/test_vp8_realworld_tos.webm "<直链>"`
- 同系列另有 VP9 对照版 `File:VP9 low bitrate test ToS.webm`（VP8/VP9 跨档对比可用）。

## 4. 生成命令（复现）

```bash
DUR=4; W=640; H=360; FPS=30; AF="sine=frequency=440:duration=${DUR}:sample_rate=44100"
VF="testsrc2=size=${W}x${H}:rate=${FPS}:duration=${DUR},drawbox=c=red:t=fill:enable='lt(mod(t+1.25,2.5),0.034)':x=0:y=0:w=iw:h=ih,format=yuv420p"
# CBR 1.5M realtime（AltRef 关，零前瞻零额外延迟）
ffmpeg -hide_banner -y -f lavfi -i "$VF" -f lavfi -i "$AF" -t $DUR \
  -c:v libvpx -pix_fmt yuv420p -b:v 1500k -minrate 1500k -maxrate 1500k -bufsize 1500k \
  -g 30 -deadline realtime -cpu-used 5 -lag-in-frames 0 -auto-alt-ref 0 \
  -c:a libopus -b:a 96k tools/samples/test_vp8_cbr_realtime.webm
# VBR 2M 2-pass（AltRef 开；pass1 统计经 -passlogfile 走，见说明）
ffmpeg -hide_banner -y -f lavfi -i "$VF" -f lavfi -i "$AF" -t $DUR \
  -c:v libvpx -pix_fmt yuv420p -b:v 2M -maxrate 3M -minrate 1M -bufsize 4M \
  -g 30 -deadline good -cpu-used 1 -lag-in-frames 25 -auto-alt-ref 1 \
  -pass 1 -passlogfile /tmp/vp8vbr -an -f null /dev/null
ffmpeg -hide_banner -y -f lavfi -i "$VF" -f lavfi -i "$AF" -t $DUR \
  -c:v libvpx -pix_fmt yuv420p -b:v 2M -maxrate 3M -minrate 1M -bufsize 4M \
  -g 30 -deadline good -cpu-used 1 -lag-in-frames 25 -auto-alt-ref 1 \
  -pass 2 -passlogfile /tmp/vp8vbr -c:a libopus -b:a 96k tools/samples/test_vp8_vbr_2pass.webm
# CQ crf10（恒质量，码率不封顶；AltRef 照常开）
ffmpeg -hide_banner -y -f lavfi -i "$VF" -f lavfi -i "$AF" -t $DUR \
  -c:v libvpx -pix_fmt yuv420p -b:v 0 -crf 10 \
  -g 30 -deadline good -cpu-used 1 -lag-in-frames 25 -auto-alt-ref 1 \
  -c:a libopus -b:a 96k tools/samples/test_vp8_cq.webm
```

注：本机 ffmpeg 9.0.2 + libvpx v1.17.0 下 `-pass 1` 进度恒显 `frame=0`、
`Output file is empty, nothing was encoded`，但统计文件正常写入且**内容相关**
（testsrc2/blue 两内容各跑 pass1，统计文件逐字节不同），pass2 正常消费统计并输出
2-pass 码流——属显示层 quirk，2-pass 本体有效。

## 5. 终端证据（粘贴）

```text
--- tools/samples/test_vp8_cbr_realtime.webm
codec_name=vp8
profile=0
width=640
height=360
pix_fmt=yuv420p
avg_frame_rate=30/1
duration=N/A
bit_rate=N/A
nb_frames=N/A
duration=4.008000
size=794164
bit_rate=1585157
--- tools/samples/test_vp8_vbr_2pass.webm
codec_name=vp8
profile=0
width=640
height=360
pix_fmt=yuv420p
avg_frame_rate=30/1
duration=N/A
bit_rate=N/A
nb_frames=N/A
duration=4.008000
size=884505
bit_rate=1765479
--- tools/samples/test_vp8_cq.webm
codec_name=vp8
profile=0
width=640
height=360
pix_fmt=yuv420p
avg_frame_rate=30/1
duration=N/A
bit_rate=N/A
nb_frames=N/A
duration=4.008000
size=193229
bit_rate=385686
--- tools/samples/test_vp8_realworld_tos.webm
codec_name=vp8
profile=0
width=960
height=400
pix_fmt=yuv420p
avg_frame_rate=25/1
duration=N/A
bit_rate=N/A
nb_frames=N/A
duration=33.200000
size=855189
bit_rate=206069

tools/samples/test_vp8_cbr_realtime.webm
  frames=120 I=4 P=116 B=0 pix_fmt=yuv420p
  altref_markers: total=5 key=4 altref=1
  key_idx=[0, 30, 60, 90]
  altref_idx=[114]
tools/samples/test_vp8_vbr_2pass.webm
  frames=126 I=4 P=122 B=0 pix_fmt=yuv420p
  altref_markers: total=8 key=4 altref=4
  key_idx=[0, 31, 63, 94]
  altref_idx=[42, 64, 95, 111]
tools/samples/test_vp8_cq.webm
  frames=120 I=6 P=114 B=0 pix_fmt=yuv420p
  altref_markers: total=19 key=6 altref=13
  key_idx=[0, 30, 38, 68, 98, 113]
  altref_idx=[7, 16, 25, 37, 45, 52, 62, 75, 84, 93, 105, 112, 114]
tools/samples/test_vp8_realworld_tos.webm
  frames=877 I=11 P=866 B=0 pix_fmt=yuv420p
  altref_markers: total=84 key=11 altref=73
  key_idx=[0, 76, 178, 277, 292, 316, 418, 519, 593, 667, 771]
  altref_idx=[1, 16, 31, 46, 77, 92, 107, 122, 137, 152, 179, 194, 209, 235, 240, 242, 244, 245, 247, 250, 251, 255, 260, 265, 270, 293, 294, 295, 296, 297, 298, 299, 300, 302, 317, 332, 347, 361, 364, 365, 366, 367, 368, 371, 384, 399, 419, 434, 449, 464, 479, 494, 520, 535, 550, 565, 594, 609, 624, 639, 719, 720, 726, 733, 741, 749, 757, 791, 797, 827, 840, 841, 848]
```

## 真实内容重转

本目录下 testsrc2 合成的本地变体已用 Sintel 预告片（`tools/samples/test_avc_sintel_trailer.mp4`
第 5~10 秒，真 3D 运镜）重转：`tools/retranscode_from_sintel.sh`，profile×chroma×RC 设置不变，
只换像素源。ffprobe 实测 profile/pix_fmt 与命名一致，分析 I/P/B 正常。
