# VVC 真实样片清单（`tools/samples/test_vvc*`）

> 口径：本机 **无 VVC 编码器**（见 `docs/rates/vvc.md` §0），样片全部外网下载，
> 未转码。`tools/samples/` 已 gitignore，只留本地、不入仓。
> 探针：`ffprobe 9.0.2`，`ffmpeg -codecs` 显示 `D.V.L. vvc`（识别 + 解码均支持，
> 但 multilayer/可分级流原生解码器不支持，见样片 2）。
> 时间：2026-10-23。

## 清单（4 个，3 主 + 1 扩展，均 <30MB）

| # | 本地文件 | 内容 | 来源 URL（下载直链） | 大小 | md5 | 覆盖 |
|---|---|---|---|---|---|---|
| 1 | `test_vvc_main10.mp4` | Novosobornaya Square 640x360 60fps 10s，`vvc1` in MP4，yuv420p | 原始出处 `https://elecard.com/videos`（VVC/H.266 · Novosobornaya Square 640x360 档）；本次经镜像直链下载 `https://dl.photoprism.app/samples/Formats/Video/H.266-VVC/NovosobornayaSquare_640x360.mp4` | 642220 B | `f84c25dfd03c5a098aaad45eed7c56d2` | 真实业务封装（MP4 + vvc1） |
| 2 | `test_vvc_multilayer.vvc` | `basketball_2_layers.vvc`：2 空域层（layer0 208x120 / layer1 832x480），10-bit | 镜像直链 `https://dl.photoprism.app/samples/Formats/Video/H.266-VVC/basketball_2_layers.vvc`；原始出处 Chromium `media/test/data`（`README.md` 原文："2 spatial layer VVC video … Used for vvc parser test"） | 15601 B | `4661bf805a7ede80b6799d485ffda198` | **multilayer**/可分级 |
| 3 | `test_vvc_tencent_ibc.bit` | `IBC_B_Tencent_2.bit`：JVET 一致性码流，腾讯贡献（IBC 工具），Main 10 | 直链 `https://fate-suite.ffmpeg.org/vvc-conformance/IBC_B_Tencent_2.bit`；ITU 原址 `http://www.itu.int/wftp3/av-arch/jvet-site/bitstream_exchange/VVC3rdEd/DIS/`（同名 zip 内含 `.bit` + `.md5` + 说明） | 9620 B | `7f3c12dc5b3251e9859330e752c8e09c` | Main 10 + Tencent 来源 |
| 4（扩展） | `test_vvc_444_422.bit` | `10b422_L_5.bit`：JVET 一致性码流，profile `Main 10 4:4:4`，内容 422 10-bit 1080p | 直链 `https://fate-suite.ffmpeg.org/vvc-conformance/10b422_L_5.bit`；ITU 原址同上 | 89839 B | `3da1e341abcd5b2fd2e8ab8b71e22f87` | **444 档**（4:4:4 profile 家族） |

## `ffprobe -show_streams` 实测（关键行）

```text
$ ffprobe -v error -show_streams tools/samples/test_vvc_main10.mp4 | grep -E "^(codec_name|profile|codec_tag_string|width|height|pix_fmt|level|r_frame_rate|avg_frame_rate|nb_frames|duration|bit_rate)"
codec_name=vvc
profile=unknown            # MP4 封装未带可映射的 profile 信号，见注 1
codec_tag_string=vvc1
width=640
height=360
pix_fmt=yuv420p
level=-99                  # 同上，MP4 样本入口无 level 映射
r_frame_rate=60/1
avg_frame_rate=60/1
duration_ts=600
duration=10.000000
bit_rate=506976
nb_frames=600

$ ffprobe -v error -show_streams tools/samples/test_vvc_multilayer.vvc | grep -E "^(codec_name|profile|width|height|pix_fmt|level|avg_frame_rate)"
codec_name=vvc
profile=17                 # general_profile_idc=17 原样显示；ffmpeg 9.0 仅命名 1/3，见注 2
width=208
height=120
pix_fmt=yuv420p10le
level=35                   # = Level 2.1，见注 3
avg_frame_rate=25/1

$ ffprobe -v error -show_streams tools/samples/test_vvc_tencent_ibc.bit | grep -E "^(codec_name|profile|width|height|pix_fmt|level|avg_frame_rate)"
codec_name=vvc
profile=Main 10
width=416
height=240
pix_fmt=yuv420p10le
level=32                   # = Level 2.0
avg_frame_rate=25/1

$ ffprobe -v error -show_streams tools/samples/test_vvc_444_422.bit | grep -E "^(codec_name|profile|width|height|pix_fmt|level|avg_frame_rate)"
codec_name=vvc
profile=Main 10 4:4:4
width=1920
height=1080
pix_fmt=yuv422p10le        # 档名 444，内容为 422（档能力超集，属正常）
level=102                  # = Level 6.2
avg_frame_rate=25/1
```

注 1：MP4 的 `profile=unknown / level=-99` 是封装层未携带 PTL 映射所致，
ES 本体可解（下节 DECODE_OK），属真实业务流常见形态，不视为识别失败。
注 2：`profile=17` 为码流原值；multilayer 身份另由 NALU 证据确认（下节）。
注 3：VVC `general_level_idc = 16×主版本 + 3×次版本`（H.266 Annex A）：
32→2.0，35→2.1，102→6.2。

## 终端证据：识别 + 解码 + 帧型 + multilayer NALU

```text
$ ffprobe -version 2>&1 | head -1; ffmpeg -codecs 2>/dev/null | grep -E " VVC|vvc "
ffprobe version 9.0.2 Copyright (c) 2007-2026 the FFmpeg developers
 D.V.L. vvc                  H.266 / VVC (Versatile Video Coding)

$ for f in tools/samples/test_vvc*; do echo "-- $f";
    ffprobe -v error -select_streams v:0 -show_entries frame=pict_type -of csv "$f" 2>&1 | head -4; done
-- tools/samples/test_vvc_444_422.bit
frame,I
frame,B
frame,B
frame,B
-- tools/samples/test_vvc_main10.mp4
frame,I
frame,B
frame,B
frame,B
-- tools/samples/test_vvc_multilayer.vvc
frame,I
-- tools/samples/test_vvc_tencent_ibc.bit
frame,I
frame,B
frame,B
frame,B

$ ffmpeg -v error -c:v vvc -i tools/samples/test_vvc_main10.mp4 -frames:v 1 -f null - && echo DECODE_OK_mp4
DECODE_OK_mp4
$ ffmpeg -v error -c:v vvc -i tools/samples/test_vvc_tencent_ibc.bit -frames:v 2 -f null - && echo DECODE_OK_tencent
DECODE_OK_tencent
$ ffmpeg -v error -c:v vvc -i tools/samples/test_vvc_444_422.bit -frames:v 2 -f null - && echo DECODE_OK_444
DECODE_OK_444
$ ffmpeg -v error -c:v vvc -i tools/samples/test_vvc_multilayer.vvc -frames:v 2 -f null -
[vist#0:0/vvc] [dec:vvc] Error submitting packet to decoder: Not yet implemented in FFmpeg, patches welcome
[vist#0:0/vvc] [dec:vvc] Decode error rate 0.9 exceeds maximum 0.666667
# ^ multilayer 原生解码不支持（预期内）：识别/解析正常，整帧解码不支持。
# 本工具对该样片应走解析路径（show_streams/show_frames），勿走解码路径。

$ ffprobe -v trace -show_streams tools/samples/test_vvc_multilayer.vvc 2>&1 | grep -oE "nal_unit_type: [0-9]+\([A-Z_0-9]+\), nuh_layer_id: [0-9]+" | sort -u
nal_unit_type: 0(TRAIL_NUT), nuh_layer_id: 0
nal_unit_type: 0(TRAIL_NUT), nuh_layer_id: 1
nal_unit_type: 8(IDR_N_LP), nuh_layer_id: 0
nal_unit_type: 8(IDR_N_LP), nuh_layer_id: 1
nal_unit_type: 14(VPS_NUT), nuh_layer_id: 0
nal_unit_type: 15(SPS_NUT), nuh_layer_id: 0
nal_unit_type: 15(SPS_NUT), nuh_layer_id: 1
nal_unit_type: 16(PPS_NUT), nuh_layer_id: 0
nal_unit_type: 16(PPS_NUT), nuh_layer_id: 1
nal_unit_type: 17(APS_PREFIX), nuh_layer_id: 0
nal_unit_type: 17(APS_PREFIX), nuh_layer_id: 1
nal_unit_type: 20(AUD_NUT), nuh_layer_id: 0
nal_unit_type: 24(SEI_SUFFIX), nuh_layer_id: 0
nal_unit_type: 24(SEI_SUFFIX), nuh_layer_id: 1
# ^ nuh_layer_id=0/1 双层并存 = multilayer 铁证；与 Chromium README
# "layer 0 at 208x120 and layer 1 at 832x480" 互证。
```

## 搜过的来源 + 结论（找不到的也写明）

- **JVET/ITU 一致性码流**（`https://www.itu.int/wftp3/av-arch/jvet-site/bitstream_exchange/VVC3rdEd/DIS/`）：
  有，但按 `xxx_A_2.zip` 分装（含 `.bit` + `.md5` + 说明），单拉麻烦；
  结论：改用 FFmpeg fate-suite 镜像的单文件直链（样片 3、4），ITU 原址备查。
  同一目录另有 `10b444*/12b*` 等 444/高位深 zip，需整包解压，按需再取。
- **Fraunhofer VVenC/VVdeC 发布页**（`https://github.com/fraunhoferhhi/vvenc`、
  `.../vvdec` releases）：只发编解码器二进制，无可直接下载的 `.266` 样片；
  其一致性测试靠构建时 `make enable-bitstream-download=1` 从 ITU 拉流。
  结论：无直链可用，未采用；同源 Chromium 镜像中有 vvencapp 产物
  `bbb_360p.vvc`（57KB，`vvencapp --preset medium` 生成，见 Chromium test-data
  README），按需可取：`https://dl.photoprism.app/samples/Formats/Video/H.266-VVC/bbb_360p.vvc`。
- **Tencent 香农实验室样片**（`https://multimedia.tencent.com/en/resources/vvc-player` +
  O266 解码库/GitHub VLC fork）：只给 decoder lib，无公开裸流样片下载。
  结论：改用腾讯向 JVET 贡献的一致性流 `IBC_B_Tencent_2.bit`（样片 3，文件名即来源）。
- **`https://samples.ffmpeg.org/V-codecs/h266/`**：仅 4 个早期 `.ts`
 （`vvc test 2.ts` 21MB，其余 574MB/791MB/1.5GB），除 21MB 外全超限，
  且为 2020 年旧流；结论：未采用（同等识别价值下优先选小文件 + 新流）。
- **Elecard 样片页**（`https://elecard.com/videos`，Novosobornaya Square 系列
  640x360~3840x2160 VVC/MP4）：原始出处；结论：经 Photoprism 镜像直链落地
  样片 1（640x360 档，与 Elecard 标称 600KB 量级一致）。
