# 示例视频来源总表（Sample Sources）

> 本仓库**不入库任何视频文件**（`tools/samples/`、`tools/avs3bin/` 已 gitignore）。
> 下表只记**来源地址 + 本地生成命令**，clone 后按需自取/自转。
> 各格式明细见同目录 `<格式>.md`（含 ffprobe 实测 + 终端证据）。

复现本地变体：各 `<格式>.md` §生成命令逐条可跑；旧 7 片一键脚本见 `tools/make_test_videos.sh`。

| 格式 | 真实片来源（URL） | 许可 | 本地生成源 |
|---|---|---|---|
| AVC | Sintel 预告片 https://media.w3.org/2010/05/sintel/trailer.mp4（Blender/CC-BY） | CC-BY | testsrc2 → 待改用 Sintel 重转（见下） |
| HEVC | Jellyfish http://www.jell.yfish.us/ · Jellyfin 4K https://syd1.mirror.jellyfin.org/test-videos/SDR/HEVC%2010bit/Test%20Jellyfin%204K%20HEVC%2010bit%2040M.mp4 · test-videos.co.uk | 免费测试 | 同上 |
| MPEG-2 | 真实 DVD VOB https://samples.ffmpeg.org/MPEG-VOB/VTS_06_0.VOB | 样片库 | 同上 |
| Theora | Wikimedia 筒仓/BBB 预告片（commons）、Xiph 官方集 https://media.xiph.org/video/tests/theora/ | CC 混杂 | 无（本机无编码器） |
| AV1 | Netflix Spark/Chimera https://opencontent.netflix.com/ · AOM CTC https://media.xiph.org/video/aomctc/test_set/ | 开放内容 | SVT-AV1 |
| H.263 | Sony K750i 实拍 https://samples.ffmpeg.org/mobileVideo_3gp/MOV00001_sonyk750i.3gp | 样片库 | h263/h263p |
| VP6 | Flash 预告片 https://samples.ffmpeg.org/FLV/flash8/（harrypotter/mrandmrssmith） | 样片库 | 无（本机无编码器） |
| VP8 | ToS 低码率测试 https://upload.wikimedia.org/wikipedia/commons/c/ca/VP8_low_bitrate_test_ToS.webm | CC-BY 3.0 | libvpx |
| VP9 | BBB alt.webm（Commons）、COSTA RICA 4K（YouTube LXb3EKWsInQ，仅记 URL）、testfiles.dev sample-3s | CC-BY/页面 | libvpx-vp9 |
| ProRes | Apple 只给白皮书、无官方样片（随摄影机厂商走） | — | prores_ks（proxy/LT/Standard/HQ/4444/4444XQ 六档） |
| VVC | PhotoPrism 样片 https://dl.photoprism.app/samples/Formats/Video/H.266-VVC/ · Elecard https://elecard.com/videos · JVET bitstream_exchange（见 vvc.md） | 样片库 | 无（本机无编码器） |
| AV2 | 无现成码流（AVM 仓库只有 y4m 源，`av2-interop-private` 私有） | — | 无 |
| AVS3 | uavs3 真流 github.com/uavs3/avs3stream（City/Basketball/ParkWalk，见 avs3.md） | 开源测试流 | 无（用 uavs3dec，tools/avs3bin/ 不入仓） |

## 真实内容重转计划（进行中）

`testsrc2` 合成的本地变体（avc/hevc/mpeg2/av1/h263/vp8/vp9/prores）将统一用
Sintel 预告片（`tools/samples/test_avc_sintel_trailer.mp4`，52s 3D 运镜）重转，
同 profile×chroma×RC 设置、只换像素源；转完更新各 `<格式>.md` 生成命令并单独 commit。
