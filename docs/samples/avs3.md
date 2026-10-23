# AVS3 示例视频集（RA 配置 × 分辨率）

目录：`tools/samples/`（已 gitignore，不入仓）。本机 brew ffmpeg 9.0.2 只能解析
avs3 码流（无解码器），真解码靠 `tools/avs3bin/uavs3dec`（uavs3d
`libuavs3d(8) 1.2.1_release`，macOS arm64，`COMPILE_10BIT=0` 构建）。

| 文件 | 大小 | 时长 | 实测分辨率 + 帧率 + 帧类型（解码器日志真值） | 来源 |
|---|---|---|---|---|
| `test_avs3_city.avs3`（已有） | 2038889 B | 10.00s | 1280x720@60，600 帧，帧类型 10I/0P/**590B**，I 位于 poc 0,64,…,576 | `uavs3/avs3stream` `ES/City_1280x720_60_ra/test.avs3` |
| `test_avs3_basketball.avs3`（新增） | 4612905 B | 10.00s | 1920x1080@50，500 帧，帧类型 8I/0P/**492B**，I 位于 poc 0,64,…,448 | `uavs3/avs3stream` `ES/BasketballDrive_1920x1080_50_ra/test.avs3` |
| `test_avs3_parkwalk.avs3`（新增 4K） | 1996115 B | 3.00s | 3840x2160@50，150 帧，帧类型 3I/0P/**147B**，I 位于 poc 0,64,128 | `uavs3/avs3stream` `ES/pku_parkwalk_3840x2160_50_ra/test.avs3` |
| LD（lowdelay）流 | 缺失（原因见 §3；已有 City + 新增两 RA 保底，不算失败） | – | – | `uavs3/avs3stream` 全仓无 LD 流 |

## 1. 下载 + 解码命令（在仓库根目录执行）

```bash
OUT=tools/samples
curl -sL -o $OUT/test_avs3_basketball.avs3 \
  https://raw.githubusercontent.com/uavs3/avs3stream/master/ES/BasketballDrive_1920x1080_50_ra/test.avs3
curl -sL -o $OUT/test_avs3_parkwalk.avs3 \
  https://raw.githubusercontent.com/uavs3/avs3stream/master/ES/pku_parkwalk_3840x2160_50_ra/test.avs3

# 解码验证（日志第 1~2 列 = poc + 帧类型；-o /dev/null 亦可只统计类型，exit=0）
tools/avs3bin/uavs3dec -i $OUT/test_avs3_basketball.avs3 -o /tmp/basketball.yuv -l 2 -t 8
tools/avs3bin/uavs3dec -i $OUT/test_avs3_parkwalk.avs3   -o /tmp/parkwalk.yuv   -l 2 -t 8
# I/P/B 计数：grep -c "(I)" / "(P)" / "(B)" <log>
```

## 2. 终端证据（解码帧数/分辨率 + ffprobe codec_name + md5）

```text
$ tools/avs3bin/uavs3dec -i tools/samples/test_avs3_basketball.avs3 -o /tmp/basketball.yuv -l 2 -t 8 | tail -4
 Resolution               = 1920 x 1080 (Coding: 1920 x 1080)
 Average bits per frame   = 73806
 Decoded frame count      = 500
 Total decoding time      = 3866 msec, fps = 129.3
$ tools/avs3bin/uavs3dec -i tools/samples/test_avs3_parkwalk.avs3 -o /tmp/parkwalk.yuv -l 2 -t 8 | tail -4
 Resolution               = 3840 x 2160 (Coding: 3840 x 2160)
 Average bits per frame   = 106459
 Decoded frame count      = 150
 Total decoding time      = 3735 msec, fps = 40.2
```

```text
$ grep -c "(I)" / "(P)" / "(B)" <各解码日志>（I/P/B 计数）
test_avs3_city.avs3:        10 I / 0 P / 590 B（合计 600）
test_avs3_basketball.avs3:   8 I / 0 P / 492 B（合计 500）
test_avs3_parkwalk.avs3:     3 I / 0 P / 147 B（合计 150）
```

```text
$ for f in test_avs3_city.avs3 test_avs3_basketball.avs3 test_avs3_parkwalk.avs3; do
>   stat -f%z $f; ffprobe -v error -select_streams v:0 \
>     -show_entries stream=codec_name,codec_long_name,width,height,has_b_frames,r_frame_rate,avg_frame_rate,pix_fmt \
>     -of default=noprint_wrappers=1 $f; done
2038889
codec_name=avs3
codec_long_name=AVS3-P2/IEEE1857.10
width=0
height=0
has_b_frames=1
pix_fmt=yuv420p
r_frame_rate=60/1
avg_frame_rate=25/1
4612905
codec_name=avs3
codec_long_name=AVS3-P2/IEEE1857.10
width=0
height=0
has_b_frames=1
pix_fmt=yuv420p
r_frame_rate=50/1
avg_frame_rate=25/1
1996115
codec_name=avs3
codec_long_name=AVS3-P2/IEEE1857.10
width=0
height=0
has_b_frames=1
pix_fmt=yuv420p
r_frame_rate=50/1
avg_frame_rate=25/1
```

```text
$ md5 码流 + 重建 YUV（均与各目录官方 md5.txt 一致，解码逐字节 bit-exact）
test_avs3_basketball.avs3  码流 6e709497babd77c0590183caa8414bd8 / YUV 8a06971ac96c60f38fb4dd9ef57d72d8
test_avs3_parkwalk.avs3    码流 375b421f5573dce07c27580c9d73bda8 / YUV 58927b0d8fdc7b2804cf1c10ce6e4b0d
test_avs3_city.avs3        码流 ce35f65e549f091f042f6a19b8d3da39 / YUV df6fff020f1e3e906237ee278c7db069
$ YUV 字节数校验（宽×高×1.5×帧数）
basketball: 1920x1080x1.5x500 = 1555200000 ✓ / parkwalk: 3840x2160x1.5x150 = 1866240000 ✓
```

## 3. RA / LD 对照

三流全部是 **RA（random access）配置，GOP=64**：一个 I 后跟 63 个 B，
B 带 L0+L1 双向参考表（如 `493 (B) [L0 492 488] [L1 494 496]`），
demuxer pts 重排（`has_b_frames=1`，裸流 pts 缺失/错标，显示序以解码器输出为准）。

**LD（lowdelay）流没拿到，原因：**

- 对 `uavs3/avs3stream` 全仓递归审计（`git/trees/master?recursive=1`，共 39 个 path）：
  ES 与 TS 下各只有 6 个目录，**全部以 `_ra` 结尾，无任何 `ld`/`lowdelay` 流**
  （`ld` 字符串命中仅为 `BasketballDrive` 子串误报）。
  其余候选：`Traffic_2560x1600_30_ra`（3.6MB）、`PartyScene_832x480_50_ra`（2.4MB）
  仍是 RA；`MarketPlace_1920x1080_60_10bit_ra`（6.9MB）是 10bit，
  本机解码器 `COMPILE_10BIT=0` 不支持，故未下载。
- 编码器仓 `uavs3/uavs3e` 内无任何 `.cfg` 预设（全仓 109 个 path，无 cfg），
  没有可直接引用的官方 LD 配置，自编码 LD 需要试错 encoder CLI，不在本任务内。

| | RA（本仓三流实测） | LD（理论预期，**未实测**，待流到位后补） |
|---|---|---|
| 参考结构 | I + 双向 B（L0+L1），GOP=64 | 前向 P/单向 B 链，无未来参考 |
| `has_b_frames` | 1 | 预期 0（或小） |
| 重排/pts | 有（RA 层次 B 典型前导） | 预期无，decode 序 = 显示序 |
| 时延 | 整 GOP 缓冲（广播/VOD 适用） | 低时延（会议/直播适用） |

注：

- ffprobe 对裸 `.avs3` ES 流的宽高/帧率不完整是三流共性：
  `width=0 height=0`（需解码器真值修正：720p/1080p/4K），
  `avg_frame_rate=25/1` 为猜测值，真帧率看 `r_frame_rate`（60/50/50，与文件名一致）。
- 解码器 `-s 1`（check_md5）在本构建无可见 md5 回显，且 `End of file` 后的
  `Failed: -6` 只是 reader EOF 返回码（flush 后继续解出尾部 B 帧，City 亦同），
  非解码失败；bit-exact 结论以本机 `md5` 重算 YUV 为准（见 §2）。
- 平均码率：city 1.63Mbps / basketball 3.69Mbps / parkwalk 5.32Mbps
 （码流字节×8÷时长）。
