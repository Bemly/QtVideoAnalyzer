"""编码器测试片回归测试：遍历 tools/samples 下已存在的视频。

最小断言（每片）: 总帧数 > 0、至少 1 个关键帧(K flag)、包 dts 单调、
pts 无缺失重复；并打印 I/P/B 分布。

仅依赖标准库 + subprocess（无 pytest 也可 `python3 tests/test_codecs.py`
直接跑；有 pytest 时 `pytest tests/test_codecs.py -v` 亦可）。
不依赖 PySide6。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "tools" / "samples"

# make_test_videos.sh 期望产出的全集；本机缺编码器的（theora/vp6）会被跳过
EXPECTED = [
    "test_avc.mp4",    # libx264
    "test_hevc.mp4",   # libx265
    "test_mpeg2.mpg",  # mpeg2video
    "test_theora.ogv",  # libtheora（本机 ffmpeg 9 无此编码器，预期缺失）
    "test_av1.mp4",    # libaom-av1 / libsvtav1
    "test_h263.mov",   # h263p
    "test_vp6.flv",    # vp6f（上游已无此编码器，预期缺失）
    "test_vp8.webm",   # libvpx
    "test_vp9.webm",   # libvpx-vp9
]

FFPROBE = "ffprobe"


def run(*args):
    p = subprocess.run(
        [FFPROBE, "-hide_banner", "-v", "error", *args],
        capture_output=True, text=True, timeout=120,
    )
    assert p.returncode == 0, f"ffprobe 失败 {args}: {p.stderr[:500]}"
    return json.loads(p.stdout)


def probe_stream(path):
    d = run("-select_streams", "v:0", "-show_streams", "-of", "json", str(path))
    return d["streams"][0]


def probe_frames(path):
    d = run("-select_streams", "v:0", "-show_frames",
            "-show_entries", "frame=pict_type", "-of", "json", str(path))
    return [f.get("pict_type", "?") for f in d.get("frames", [])]


def probe_packets(path):
    d = run("-select_streams", "v:0", "-show_packets",
            "-show_entries", "packet=pts:packet=dts:packet=flags",
            "-of", "json", str(path))
    return d.get("packets", [])


def check_one(path):
    """单片全断言，返回 I/P/B 分布 dict。"""
    st = probe_stream(path)
    frames = probe_frames(path)
    packets = probe_packets(path)

    n_frames = int(st.get("nb_frames") or 0) or len(frames)
    assert n_frames > 0, f"{path.name}: 总帧数为 0"
    assert len(frames) > 0, f"{path.name}: ffprobe 未读出任何帧"

    keys = [p for p in packets if p.get("flags", "").startswith("K")]
    assert len(packets) > 0, f"{path.name}: 无视频包"
    assert len(keys) >= 1, f"{path.name}: 一个关键帧都没有"

    dts = [int(p["dts"]) for p in packets]
    assert all(b >= a for a, b in zip(dts, dts[1:])), \
        f"{path.name}: 包 dts 非单调（解码序错乱）"

    ts_packets = [p for p in packets if "pts" in p]
    assert len(ts_packets) >= 0.95 * len(packets), \
        f"{path.name}: 带 pts 的包仅 {len(ts_packets)}/{len(packets)}"
    pts = [int(p["pts"]) for p in ts_packets]
    assert len(set(pts)) == len(pts), f"{path.name}: pts 有重复/缺失"
    spts = sorted(pts)
    assert all(b > a for a, b in zip(spts, spts[1:])), \
        f"{path.name}: pts 按显示序非严格单调"
    # 注: 只要求显示序严格单调，不要求固定步长——各容器 timebase 不同
    # (mp4 步长 512、mpeg-PS 步长 3000、webm 因 1000/30 非整除而步长不均)。
    pts_file_order_mono = all(b > a for a, b in zip(pts, pts[1:]))

    dist = {"I": 0, "P": 0, "B": 0, "?": 0}
    for t in frames:
        dist[t if t in dist else "?"] += 1

    print(f"[probe] {path.name}: codec={st.get('codec_name')} "
          f"{st.get('width')}x{st.get('height')} fps={st.get('avg_frame_rate')} "
          f"frames={len(frames)}(nb_frames={st.get('nb_frames')}) "
          f"packets={len(packets)} keyframes={len(keys)} "
          f"dts单调=OK pts显示序单调=OK pts文件序单调={pts_file_order_mono}"
          f"{'（含B帧时为False属正常：包按解码序存放）' if not pts_file_order_mono else ''}")
    print(f"        I/P/B 分布: I={dist['I']} P={dist['P']} B={dist['B']}"
          + (f" 未知={dist['?']}" if dist["?"] else ""))
    return dist


def existing_samples():
    return [SAMPLES / n for n in EXPECTED if (SAMPLES / n).exists()]


def test_samples_dir_not_empty():
    files = existing_samples()
    missing = [n for n in EXPECTED if not (SAMPLES / n).exists()]
    print(f"[info] 存在 {len(files)}/{len(EXPECTED)} 个测试片；"
          f"缺失（无编码器则预期）: {missing or '无'}")
    assert files, f"{SAMPLES} 下一个测试片都没有，先跑 tools/make_test_videos.sh"


def test_each_video():
    for path in existing_samples():
        check_one(path)


def main():
    tests = [("samples_dir_not_empty", test_samples_dir_not_empty),
             ("each_video", test_each_video)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"===== {len(tests) - failed}/{len(tests)} 组通过 =====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
