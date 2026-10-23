# AV1 示例视频集（profile × bitdepth × RC）

本机：`ffmpeg 9.0.2` + `SVT-AV1 v4.2.0`（Apple Silicon，`--enable-libsvtav1`；
本机无 `libaom-av1`，全部走 `libsvtav1`，`preset 8`）。
片源统一：`testsrc2` 运动 + 每 3s 片内 1 次整帧红闪（`drawbox` 充当场景切换，
便于观察 I/P 分布），`640x360@30fps`，`~3s`（90 帧），音频 `sine 440Hz + aac 64k`。

详细 RC 语义见 `docs/rates/av1.md` §3（CRF/VBR/CBR 映射与 CBR 必须 low-delay 的原因）。

## 1. 清单

| 文件（`tools/samples/`，gitignore） | profile × 位深 × RC | 分辨率/时长/帧 | 实测 `pix_fmt` / `profile` | 大小 | 来源 |
|---|---|---|---|---|---|
| `test_av1_main8_crf.mp4` | Main 420 8bit × CRF | 640x360@30，3.0s，90 帧 | `yuv420p` / `Main` | 348784 B（~341 KiB） | 本地生成（命令见 §2.1） |
| `test_av1_main10_vbr.mp4` | Main 420 10bit × VBR | 640x360@30，3.0s，90 帧 | `yuv420p10le` / `Main` | 370568 B（~362 KiB） | 本地生成（命令见 §2.2） |
| `test_av1_cbr_ld.mp4` | Main 420 8bit × CBR 低延迟 | 640x360@30，3.0s，90 帧 | `yuv420p` / `Main` | 335960 B（~328 KiB） | 本地生成（命令见 §2.3；注意踩坑 §2.4） |
| `test_av1_netflix_spark270p.mp4` | Main 420 8bit × VBR（专业压制） | 480x270@59.94，229.8s | `yuv420p` / `Main` | 8029782 B（7.66 MiB） | 网上真片：Netflix `Spark` 8-bit CMAF（URL 见 §3） |

三路本地片均 `<8MB`；AV1 无 B 帧概念，ffprobe 帧类型全报 I/P（B 恒 0 正常）。

## 2. 本地生成命令（实测通过，原样粘贴可用）

公共变量：

```bash
VF="testsrc2=size=640x360:rate=30:duration=3,drawbox=c=red:t=fill:enable='lt(mod(t+1.5,3.0),0.034)':x=0:y=0:w=iw:h=ih,format=yuv420p"
AF="sine=frequency=440:duration=3:sample_rate=44100"
```

### 2.1 Main 8bit CRF（点播默认）

```bash
ffmpeg -hide_banner -y -v warning -stats \
  -f lavfi -i "$VF" -f lavfi -i "$AF" -t 3 -r 30 \
  -c:v libsvtav1 -pix_fmt yuv420p -preset 8 -crf 32 -g 30 \
  -c:a aac -b:a 64k tools/samples/test_av1_main8_crf.mp4
# SVT 回显关键行：BRC mode / rate factor : CRF / 32.00；pred struct : random access
```

### 2.2 Main10 VBR（10bit HDR 链）

```bash
VF10="testsrc2=size=640x360:rate=30:duration=3,drawbox=c=red:t=fill:enable='lt(mod(t+1.5,3.0),0.034)':x=0:y=0:w=iw:h=ih,format=yuv420p10le"
ffmpeg -hide_banner -y -v warning -stats \
  -f lavfi -i "$VF10" -f lavfi -i "$AF" -t 3 -r 30 \
  -c:v libsvtav1 -pix_fmt yuv420p10le -preset 8 -b:v 800k -g 30 \
  -c:a aac -b:a 64k tools/samples/test_av1_main10_vbr.mp4
# SVT 回显关键行：bit-depth / color format : 10 / YUV420；BRC mode : VBR / 800
```

### 2.3 CBR 低延迟（直播档；必须带 `pred-struct=1:rc=2`）

```bash
ffmpeg -hide_banner -y -v warning -stats \
  -f lavfi -i "$VF" -f lavfi -i "$AF" -t 3 -r 30 \
  -c:v libsvtav1 -pix_fmt yuv420p -preset 8 \
  -b:v 800k -maxrate 800k -bufsize 800k -g 30 \
  -svtav1-params pred-struct=1:rc=2 \
  -c:a aac -b:a 64k tools/samples/test_av1_cbr_ld.mp4
# SVT 回显关键行：pred struct : low delay；BRC mode : CBR / 800
# 另有两行无害警告：Maximum bit rate only supported with tpl on / TPL is disabled in low delay applications.
```

### 2.4 踩过的坑（CBR + 默认随机接入直接失败）

只给 `rc=2` 而不切 `pred-struct=1` 时编码器拒绝启动：

```text
Svt[error]: CBR Rate control is currently not supported for RANDOM_ACCESS/ALL_INTRA, use VBR mode
[libsvtav1 @ ...] Error setting encoder parameters: bad parameter (0x80001005)
```

复现（预期失败，不产出文件）：

```bash
ffmpeg -hide_banner -y -v warning \
  -f lavfi -i "testsrc2=size=160x120:rate=30:duration=1,format=yuv420p" \
  -t 1 -r 30 -c:v libsvtav1 -preset 8 -b:v 800k -maxrate 800k -bufsize 800k \
  -svtav1-params rc=2 -an /tmp/smoke_cbr_fail.mp4
```

结论：ffmpeg wrapper 下 CBR 必须写全 `-svtav1-params pred-struct=1:rc=2`
（与 `docs/rates/av1.md` §3b 一致；`SvtAv1EncApp --help` 中
`--pred-struct [1: low delay frames, 2: random access]`）。

## 3. 网上真实 AV1 片（1 个已下载验证 + 大文件只记 URL）

已下载验证（存 `tools/samples/test_av1_netflix_spark270p.mp4`）：

- **Netflix `Spark` 8-bit CMAF，270p**（`Spark` 短片，59.94fps，AV1 8-bit SDR）：
  `http://download.opencontent.netflix.com.s3.amazonaws.com/AV1/cmaf/spark-8b-59.94fps/spark_276kbps_270p.mp4`
  （8029782 B；同目录另有 `spark_390kbps_342p` / `spark_606kbps_432p`，见 S3 列表
  `?prefix=AV1/cmaf/spark-8b-59.94fps/`； portal：`https://opencontent.netflix.com/`）
- 同 bucket 的 **10-bit `Cosmos`**（24fps，10-bit，最小 `cosmos_98kbps_270p.mp4` 9256775 B，
  大文件未下载，只记 URL 前缀 `…/AV1/cmaf/cosmos-10b-24fps/`）。

大文件只记 URL（未下载，来源可靠、内容为真实电影/剧集实拍）：

- **Netflix `Chimera` AV1 全套**（2014 短片，实拍 + 特效；Old 目录含 8/10bit × 270p~1080p 的
  `.mp4` / `.ivf` / fragmented（含 cbcs 加密变体），单文件 24MB~313MB）：
  - 列表：`http://download.opencontent.netflix.com/?prefix=AV1/Chimera/Old/`
    （S3 API：`http://download.opencontent.netflix.com.s3.amazonaws.com/?prefix=AV1/Chimera/Old/&max-keys=30`）
  - 例（10bit 720p，110686423 B）：`…/AV1/Chimera/Old/Chimera-AV1-10bit-1280x720-2380kbps.mp4`
  - 例（8bit 1080p，313490236 B）：`…/AV1/Chimera/Old/Chimera-AV1-8bit-1920x1080-6736kbps.mp4`
  - 例（8bit 270p，25598028 B）：`…/AV1/Chimera/Old/Chimera-AV1-8bit-480x270-552kbps.mp4`
- **AOM CTC 原始测试集**（编码器比测标准片源，多为 YUV 未压缩，大包只记 URL）：
  `https://media.xiph.org/video/aomctc/test_set/`
  （如 `a4_360p/` 180MB、`a3_720p.zip` 938MB、`a1_4k.zip` 12GB；AV1 anchor 即用此类片源压制）
- Blender 备注：Big Buck Bunny / Tears of Steel 等 Blender 开放电影是常用压制母源，
  但官网直供多为 H.264/ProRes，AV1 版需自压或走 YouTube-AV1 拉流，不如 Netflix 开放内容
  给出现成 AV1 码流直接可验，故本次真片选 Netflix `Spark`。

## 4. ffprobe 确认（终端证据粘贴）

```bash
for f in tools/samples/test_av1_main8_crf.mp4 tools/samples/test_av1_main10_vbr.mp4 \
         tools/samples/test_av1_cbr_ld.mp4 tools/samples/test_av1_netflix_spark270p.mp4; do
  echo "===== $f ====="
  ffprobe -hide_banner -v error -select_streams v:0 \
    -show_entries stream=codec_name,profile,width,height,pix_fmt,avg_frame_rate,duration,bit_rate \
    -of default=noprint_wrappers=1 "$f"
  ffprobe -hide_banner -v error -select_streams v:0 \
    -show_entries frame=pict_type -of csv "$f" | sort | uniq -c
done
ls -l tools/samples/test_av1_*.mp4
```

实测输出（2026-10-23，本机）：

```text
===== tools/samples/test_av1_main8_crf.mp4 =====
codec_name=av1
profile=Main
width=640
height=360
pix_fmt=yuv420p
avg_frame_rate=30/1
duration=3.000000
bit_rate=853965
      3 frame,I
     87 frame,P
===== tools/samples/test_av1_main10_vbr.mp4 =====
codec_name=av1
profile=Main
width=640
height=360
pix_fmt=yuv420p10le
avg_frame_rate=30/1
duration=3.000000
bit_rate=912056
      3 frame,I
     87 frame,P
===== tools/samples/test_av1_cbr_ld.mp4 =====
codec_name=av1
profile=Main
width=640
height=360
pix_fmt=yuv420p
avg_frame_rate=30/1
duration=3.000000
bit_rate=819768
      3 frame,I
     87 frame,P
===== tools/samples/test_av1_netflix_spark270p.mp4 =====
codec_name=av1
profile=Main
width=480
height=270
pix_fmt=yuv420p
avg_frame_rate=60000/1001
duration=229.812917
bit_rate=275498
     41 frame,I
  13734 frame,P
```

文件大小：

```text
-rw-r--r--  335960 test_av1_cbr_ld.mp4
-rw-r--r--  370568 test_av1_main10_vbr.mp4
-rw-r--r--  348784 test_av1_main8_crf.mp4
-rw-r--r-- 8029782 test_av1_netflix_spark270p.mp4
```

三路本地片各 90 帧（`ffprobe -show_frames` 实计数）且 I=3/P=87/B=0：
初始 1 个 I + 红闪场景切换触发 2 个额外 I，其余全 P——AV1 无 B 帧，B=0 为正常。
真片 `Spark` 共 13775 帧，I=41/P=13734/B=0，同为 AV1 典型分布。
