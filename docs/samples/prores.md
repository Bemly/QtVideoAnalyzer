# ProRes 示例视频集 · 6 profile 全覆盖

> 口径:本地 `ffmpeg 9.0.2 prores_ks` 自生成 (`tools/samples/`, gitignore, 不入库);
> 内容统一为 `testsrc2 + 整帧红闪` (与 `tools/make_test_videos.sh` 同源),
> 纯视频、无音频, `640x360 @ 30fps, 3s (90 帧)`;
> 码率口径对照:Apple ProRes 白皮书 + Apple Support 102207
> (`1920x1080@29.97` VBR 目标码率行)。
> 上游细节见 `docs/rates/prores.md`,数据模块见 `qt_analyzer/rc_prores.py`。

## 1. 6 profile 清单 (实测)

| # | 文件 | profile (`-profile:v`) | pix_fmt (编码输入) | codec_tag (`profile_tag`) | 大小 | 时长 |
|---|---|---|---|---|---|---|
| 1 | `test_prores_proxy.mov` | Proxy (0) | yuv422p10le | `apco` | 2.07 MB | 3.0s |
| 2 | `test_prores_lt.mov` | LT (1) | yuv422p10le | `apcs` | 4.30 MB | 3.0s |
| 3 | `test_prores.mov` (既有) | Standard (2) | yuv422p10le | `apcn` | 5.53 MB | 3.0s |
| 4 | `test_prores_hq.mov` | HQ (3) | yuv422p10le | `apch` | 6.81 MB | 3.0s |
| 5 | `test_prores_4444.mov` | 4444 (4) | yuv444p10le | `ap4h` | 9.50 MB | 3.0s |
| 6 | `test_prores_4444xq.mov` | XQ (5) | yuv444p10le | `ap4x` | 9.81 MB | 3.0s |

约束达成:proxy/lt 最小;hq/4444 远 <40MB (XQ 同理,9.8MB)。
注意:4444/XQ 经 `prores_ks` 编码只是 **profile 标记位**,
输入仍是 10-bit;ffprobe 解码侧显示 `yuv444p12le`
(4444 码流容器恒为 12-bit 槽位),真 12-bit 需 Apple 原生编码器。

## 2. 实测码率 vs 白皮书比例换算

换算系数 (像素×帧率线性缩放):

```text
scale = (640×360)/(1920×1080) × (30/29.97) = 0.111223
expected = 白皮书 1080p29.97 锚点 × scale
```

| profile | 白皮书锚点 (Mbps) | 换算期望 (Mbps) | 实测 (Mbps) | 偏差 | 以 proxy 为 1 的倍数 (白皮书 / 实测) |
|---|---|---|---|---|---|
| Proxy | 45 | 5.005 | 5.514 | +10.2% | 1.00 / 1.00 |
| LT | 102 | 11.345 | 11.462 | +1.0% | 2.27 / 2.08 |
| Standard | 147 | 16.350 | 14.746 | −9.8% | 3.27 / 2.67 |
| HQ | 220 | 24.469 | 18.173 | −25.7% | 4.89 / 3.30 |
| 4444 | 330 | 36.703 | 25.321 | −31.0% | 7.33 / 4.59 |
| 4444 XQ | 495 (~500) | 55.055 | 26.171 | −52.5% | 11.0 / 4.75 |

解读 (如实记录,不粉饰):

- 档位顺序严格单调 `proxy < lt < standard < hq < 4444 < xq`,定性正确。
- 高档位系统性偏低:ProRes 是 **VBR-fixedQP** (档位=固定量化矩阵,
  无 CBR 承诺),`testsrc2` 合成内容偏"好压",
  高档位在简单内容上花不满目标码率;白皮书锚点是实拍内容的统计目标值。
- XQ 偏差最大另有一半是编码器原因:ffmpeg 只写 `ap4x` 标记,
  并无真 12-bit/XQ 量化增益 (见第 1 节注意)。

## 3. 生成命令 (复现)

```bash
cd /Volumes//Projects/VideoAnalyzer-Qt
VF422="testsrc2=size=640x360:rate=30:duration=3,drawbox=c=red:t=fill:enable='lt(mod(t+1.25,2.5),0.034)':x=0:y=0:w=iw:h=ih,format=yuv422p10le"
VF444="testsrc2=size=640x360:rate=30:duration=3,drawbox=c=red:t=fill:enable='lt(mod(t+1.25,2.5),0.034)':x=0:y=0:w=iw:h=ih,format=yuv444p10le"
OUT=tools/samples
ffmpeg -hide_banner -y -f lavfi -i "$VF422" -t 3 -r 30 -c:v prores_ks -profile:v 0 "$OUT/test_prores_proxy.mov"
ffmpeg -hide_banner -y -f lavfi -i "$VF422" -t 3 -r 30 -c:v prores_ks -profile:v 1 "$OUT/test_prores_lt.mov"
# standard: 既有 test_prores.mov (apcn);重建用 -profile:v 2
ffmpeg -hide_banner -y -f lavfi -i "$VF422" -t 3 -r 30 -c:v prores_ks -profile:v 3 "$OUT/test_prores_hq.mov"
ffmpeg -hide_banner -y -f lavfi -i "$VF444" -t 3 -r 30 -c:v prores_ks -profile:v 4 -pix_fmt yuv444p10le "$OUT/test_prores_4444.mov"
ffmpeg -hide_banner -y -f lavfi -i "$VF444" -t 3 -r 30 -c:v prores_ks -profile:v 5 -pix_fmt yuv444p10le "$OUT/test_prores_4444xq.mov"
```

## 4. Apple 官方样片信息 (网上)

| 来源 | URL | 可否下载样片 | 说明 |
|---|---|---|---|
| Apple ProRes 白皮书 (现行版) | https://www.apple.com/final-cut-pro/docs/Apple_ProRes_White_Paper.pdf | 仅文档可下,**无样片** | 即 `rc_prores.py` 口径来源;历史版曾用 `.../Apple_ProRes.pdf` 同目录 |
| About Apple ProRes (Support 102207) | https://support.apple.com/en-us/102207 | 仅文案,**无样片** | 45/102/147/220/330/~500 Mbps 六档目标码率行 (2025-03-03 修订,已核验) |
| Pro Video Formats 软件包 (Support 106396) | https://support.apple.com/en-us/106396 | 可下,**解码器非样片** | ProRes RAW 播放/解码支持包,无测试视频 |
| 官方可下载样片 | —— | **无** | Apple 从未在官网提供 ProRes 测试片段下载;旧版白皮书只有码率柱状图,无附件。原因:ProRes 是中间码,样片随摄影机厂商/素材商走 (如 ARRI/Atomos/Blackmagic 各自提供),Apple 只给文档 + 系统解码器 |

结论:官方渠道拿不到样片,故本集采用本地 `prores_ks` 自生成;
第三方样片 (MPlayer 样本库 `samples.mplayerhq.hu`、摄影机厂商片段)
内容不可控且版权不明,不采用。

## 5. ffprobe 终端证据 (`profile_tag` 确认)

```bash
$ for f in tools/samples/test_prores*.mov; do echo "== $f";
> ffprobe -hide_banner -v error -select_streams v:0 \
>   -show_entries stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate,codec_tag_string \
>   -of default=noprint_wrappers=1 "$f"; done
```

```text
== tools/samples/test_prores.mov
codec_name=prores
profile=Standard
codec_tag_string=apcn
width=640
height=360
pix_fmt=yuv422p10le
avg_frame_rate=30/1
== tools/samples/test_prores_proxy.mov
codec_name=prores
profile=Proxy
codec_tag_string=apco
width=640
height=360
pix_fmt=yuv422p10le
avg_frame_rate=30/1
== tools/samples/test_prores_lt.mov
codec_name=prores
profile=LT
codec_tag_string=apcs
width=640
height=360
pix_fmt=yuv422p10le
avg_frame_rate=30/1
== tools/samples/test_prores_hq.mov
codec_name=prores
profile=HQ
codec_tag_string=apch
width=640
height=360
pix_fmt=yuv422p10le
avg_frame_rate=30/1
== tools/samples/test_prores_4444.mov
codec_name=prores
profile=4444
codec_tag_string=ap4h
width=640
height=360
pix_fmt=yuv444p12le
avg_frame_rate=30/1
== tools/samples/test_prores_4444xq.mov
codec_name=prores
profile=XQ
codec_tag_string=ap4x
width=640
height=360
pix_fmt=yuv444p12le
avg_frame_rate=30/1
```

```bash
$ for f in tools/samples/test_prores*.mov; do echo "== $f";
> ffprobe -hide_banner -v error \
>   -show_entries format=duration,size,bit_rate \
>   -of default=noprint_wrappers=1 "$f"; done
```

```text
== tools/samples/test_prores.mov
duration=3.000000
size=5529680
bit_rate=14745813
== tools/samples/test_prores_proxy.mov
duration=3.000000
size=2067855
bit_rate=5514280
== tools/samples/test_prores_lt.mov
duration=3.000000
size=4298254
bit_rate=11462010
== tools/samples/test_prores_hq.mov
duration=3.000000
size=6814932
bit_rate=18173152
== tools/samples/test_prores_4444.mov
duration=3.000000
size=9495456
bit_rate=25321216
== tools/samples/test_prores_4444xq.mov
duration=3.000000
size=9814139
bit_rate=26171037
```

tag 对应关系:Proxy=`apco` / LT=`apcs` / Standard=`apcn` /
HQ=`apch` / 4444=`ap4h` / XQ=`ap4x`,与 Apple 四字符码规范一致。

## 真实内容重转

本目录下 testsrc2 合成的本地变体已用 Sintel 预告片（`tools/samples/test_avc_sintel_trailer.mp4`
第 5~10 秒，真 3D 运镜）重转：`tools/retranscode_from_sintel.sh`，profile×chroma×RC 设置不变，
只换像素源。ffprobe 实测 profile/pix_fmt 与命名一致，分析 I/P/B 正常。
