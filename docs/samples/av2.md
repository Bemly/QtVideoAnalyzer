# AV2 样片现状（一页纸，2026-10-23）

> 结论先行：**本机无 AV2 样片、无 AV2 编解码器**。AV2 已于 2026-05-28
> 发布 v1.0.0 规范 + AVM v1.0.0 参考软件，但 ffmpeg 9.0.2 仍无 AV2
> 编解码支持；公开渠道只有 **YUV 源（.y4m）**，没有现成的可下载 AV2
> 码流，只能用 AVM 本地编码自制。本页只记录找过的来源和实测证据，
> 不虚构样片。

## 1. AV2 码流长什么样（已确认）

- 规范：`AV2 Bitstream & Decoding Process Specification v1.0.0`
  - 在线：<https://av2.aomedia.org/v1.0.0/index.html>
  - 源码仓：<https://github.com/AOMediaCodec/av2-spec>（`release/v1.0.0` 分支）
- 传输形态（与 AV1 同构，内容是 AV2 OBU）：
  - 实验容器：**IVF（`.ivf`）**，`Codec ID = AV02`（AV1 为 `AV01`）。
    来源：CNX Software 2026-02-03 用 AVM `examples/simple_encoder`
    编出 `desktop.ivf`，`mediainfo` 显示 `Format: IVF / Video Format: AV02`。
  - 裸流：OBU 序列（open-bitstream-unit framing，同 AV1 的 Low Overhead
    Bitstream Format 思路，细节见规范 §4–§8）。
  - MP4/ISOBMFF：由 STF 工作组 `av2-isobmff` 规范 + `av2-tools` 的
    `av2_mux` / `av2_demux` 实现（本机未构建，未验证 fourcc）。
- 能否用 AVM 解码器解：**能（设计上）**。AVM 即 AV2 参考软件，
  `examples/simple_decoder <in.ivf> <out.yuv>` 为配套解码器；
  但 CNX 实测曾报 `Failed to decode frame.: Invalid parameter`
  （疑为早期 tag 的 bug 或编码参数问题），且 AVM 编码极慢
  （320×180 / 30 帧 ≈ 18 分 37 秒，约 31 s/帧），参考实现不追求速度。

## 2. 解码器构建方式（未在本机构建，只记官方步骤）

AVM（参考编解码）：

```sh
git clone https://github.com/AOMediaCodec/avm.git
# v1.0.0 tag 存在（git ls-remote 已验证见 §4）：
#   2a79e6ce349271e916469f601be249fcd371a6cd  refs/tags/v1.0.0
mkdir avm_build && cd avm_build
cmake ../avm && make -j16
make -j16 testdata   # 下载单元测试用小 YUV（见下，非 AV2 码流）
./examples/simple_encoder av2 <w> <h> <in.yuv> <out.ivf> <kf-interval> <err-resilient> <n-frames>
./examples/simple_decoder <in.ivf> <out.yuv>
```

第三方快速解码器 dav2d（VideoLAN，早期）：

- 仓库：<https://code.videolan.org/videolan/dav2d>（2026-10-23 curl -I 返回 HTTP/2 200）
- 状态（jbkempf 2026-05-31《Let dav2d be》）：相对 AVM v15 功能完整，
  支持 8/10-bit，已有 x86 AVX2 / AArch64 NEON / RISC-V 初步优化；
  但仍是早期工程，“should not be used in production”，且跟踪的是
  v15 时刻的 AVM，不等于 v1.0.0 终版一致性保证。
- ffmpeg/dav1d 式集成：尚无（ffmpeg 无 `dav2d`/`av2` 解码器，见 §4）。

`av2-tools`（码流解析/统计/MP4 打包，与解码无关但有用）：

- 仓库：<https://github.com/AOMediaCodec/av2-tools>
- 构建：`cmake .. -DBUILD_CONTAINER_TOOLS=ON -DBUILD_EXAMPLES=ON && make -j`
- 工具：`av2_obu_tool`（解析/dump/JSON/统计）、`av2_mux`/`av2_demux`
  （ISOBMFF 互转）、`av2_obu_switcher`、`av2_obu_channel_sim`。

## 3. 样片来源（找过、可复查，均无现成 AV2 码流）

| # | 来源 | 结果 |
|---|------|------|
| 1 | AVM 仓 `make testdata`（28 个小 YUV，CNX 列出：`Debugging_480x270p3000_yuv420p_20frames.yuv` 3.8M、`desktop1.320_180.yuv` 65M、`hantro_collage_w352h288.yuv` 53M 等） | **编码器输入 YUV，不是 AV2 码流**；本机未执行构建 |
| 2 | AV2 CTC 测试集 <https://media.xiph.org/video/aomctc/test_set/>（AVM README 指明的官方序列源；CTC 文档 <https://aomedia.org/docs/CWG-G082_AV2_CTC_v9.pdf>，HEAD 200 确认存在） | **只有 `.y4m` 源**（如 `a5_270p/FourPeople_480x270_60.y4m` 24M；4K 的 `a1_4k/*.y4m` 单个 3.0G）。13 个 zip：`a1_4k.zip`(12G)…`hdr2_2k.zip`(2.3G)，最小 `a5_270p.zip`(74M)。无 `.ivf`/`.obu` AV2 码流 |
| 3 | `av2-interop-private`（av2-tools README 提及的互操作码流配方仓） | 私有仓，无公开可下载码流 |
| 4 | 公网搜索 “AV2 sample .ivf / AV2 test bitstream download” | 无可下载 AV2 码流；只有上面的 YUV 源 + 规范 + 参考软件 |

YUV 源可用（注明非码流）：最小可操作的是 `a5_270p.zip`（74M，
含 4 个 ≤60 帧的 270p `.y4m`）；`make testdata` 的小 YUV 需先构建 AVM。
本机均未下载（AVM 构建+编码成本高，且任务要求尽力即可）。

## 4. 终端证据（2026-10-23 本机实测，可重跑）

```sh
$ ffmpeg -hide_banner -encoders 2>&1 | grep -i -E "av2|avm|dav2d"
 A....D wmav2   Windows Media Audio 2     # ← 音频，误命中，无视频 AV2 编码器

$ ffmpeg -hide_banner -decoders 2>&1 | grep -i -E "av2|avm|dav2d|vvc"
 V....D vvc     VVC (Versatile Video Coding)  # ← 仅 VVC，无 AV2
 A....D wmav2   Windows Media Audio 2

$ git ls-remote --tags https://github.com/AOMediaCodec/avm.git | grep "v1.0.0"
2a79e6ce349271e916469f60…  refs/tags/v1.0.0   # ← AVM v1.0.0 tag 存在

$ curl -sL https://media.xiph.org/video/aomctc/test_set/ | grep -oE 'href="[^"]+\.zip"'
href="a1_4k.zip"  href="a2_2k.zip"  …  href="hdr2_2k.zip"   # 共 13 个，全是源 zip

$ curl -sL https://media.xiph.org/video/aomctc/test_set/a5_270p/
… <a href="FourPeople_480x270_60.y4m"> … 24M
… <a href="ParkJoy_480x270_50.y4m">      … 24M   # ← .y4m 源，无 .ivf/.obu

$ curl -sI https://aomedia.org/docs/CWG-G082_AV2_CTC_v9.pdf
HTTP/2 200  content-type: application/pdf
$ curl -sI https://av2.aomedia.org/v1.0.0/index.html
HTTP/2 200  content-type: text/html; charset=utf-8
$ curl -sI --max-time 15 https://code.videolan.org/videolan/dav2d
HTTP/2 200   # ← dav2d 仓可达，未克隆构建
```

搜过的 URL 列表（找过但无码流）：

- <https://github.com/AOMediaCodec/avm>
- <https://github.com/AOMediaCodec/av2-spec>
- <https://github.com/AOMediaCodec/av2-tools>
- <https://av2.aomedia.org/v1.0.0/index.html>
- <https://aomedia.org/docs/CWG-G082_AV2_CTC_v9.pdf>
- <https://media.xiph.org/video/aomctc/test_set/>（及 `a5_270p/`、`a1_4k/` 子目录）
- <https://code.videolan.org/videolan/dav2d>，<https://jbkempf.com/blog/2026/dav2d/>
- <https://www.cnx-software.com/2026/02/03/aomedia-av2-video-codec-draft-specification-release-and-a-quick-try-at-the-reference-implementation/>

## 5. 对本工具的含义

- `tools/samples/` 下无 AV2 样片（gitignore，本机也无）；`ffmpeg`/`ffprobe`
  解析路径对 AV2 不可用，后续拿到 AVM 自编码 `.ivf` 后才能验证
  `av2_obu_tool` 或 AVM 解码器输出。
- 若以后要补样片：推荐路径 = 下载 `a5_270p` 任一 `.y4m`（24M，最小）→
  按 §2 构建 AVM v1.0.0 → `simple_encoder` 压几帧 270p → 得 `AV02` IVF；
  预期耗时分钟级（参考 320×180/30 帧 ≈ 18min），CI 不宜常跑。
