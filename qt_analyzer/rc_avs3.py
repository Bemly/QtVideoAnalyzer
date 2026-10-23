"""AVS3 profile / 采样 / 码率控制速查数据模块（纯数据 + 规则，无第三方依赖，永不抛错）。

文献口径（公开资料，详见 docs/rates/avs3.md）：
- GB/T 33475.2-2024《信息技术 高效多媒体编码 第2部分：视频》（国家标准全文库可查）
- HPM 参考软件（AVS3 CTC：Random Access / Low Delay 两套配置，CQP 常用 QP 22/27/32/37）
- uavs3e 开源编码器（AVS3-P2 baseline profile，默认 8bit，cmake -DCOMPILE_10BIT=1 开 10bit，
  以 encode_RA.cfg 为起点 + 命令行覆盖）
- 广播侧：4K=3840x2160@50p 4:2:0 10bit / level 6.0.60；
  8K=7680x4320@50p 4:2:0 10bit / level 8.0.60，解码端最大码率不低于 120Mbps
  （T/UWA 005.3-5-2022 引用的 4K/8K 码流格式要求表）
- 中国 4K 广播 AVS3 典型口径：4K@50p 约 30~40Mbps（常用 36M 量级），8K 上限看 120M 解码能力。

本机 brew ffmpeg 9.0.2 无 AVS3 编/解码器（仅 AVS1/cavs），故 recommend() 的
ffmpeg_args 为占位字符串：给出 uavs3e 等效命令草稿，不可直接执行。
"""
from __future__ import annotations

CODEC = "avs3"
LCU = 128  # 与 codec_avs3.LCU_SIZE 一致：AVS3 最大 LCU 128x128

# HPM CTC / uavs3e 常用 CQP 锚点（亮度 QP，I 帧基准）
CTC_QP_POINTS = (22, 27, 32, 37)

# CBR 起点口径（50/60p 广播贡献质量，单位 Mbps；帧率减半约按 0.7 折算）
# 依据：UWA 8K 解码 >=120M + 行业 4K 30~40M 口径 + 本模块保守取整
_CBR_TABLE = (
    # (像素上限, fps 基准, 建议码率 Mbps, QP 建议)
    (2_100_000, 30, (4, 8), (27, 32)),      # <=1080p
    (2_100_000, 60, (8, 12), (27, 32)),     # <=1080p 高帧率
    (9_000_000, 30, (18, 25), (27, 32)),    # 4K 低帧率
    (9_000_000, 60, (30, 40), (27, 32)),    # 4K@50/60p 广播主力
    (36_000_000, 60, (80, 120), (27, 32)),  # 8K
)


def profiles() -> list:
    """AVS3 可用 profile 名（短标识，详情见 docs/rates/avs3.md）。"""
    try:
        return ["Main", "Main10", "High"]
    except Exception:
        return []


def chroma_modes() -> list:
    """广播基线支持的采样：4:2:0 主力；4:2:2 不在 P2 baseline 广播档内。"""
    try:
        return ["4:2:0"]
    except Exception:
        return []


def rc_modes() -> list:
    """码率控制模式：CQP（质量/仿真锚点）+ CBR（广播播出）。"""
    try:
        return ["CQP", "CBR"]
    except Exception:
        return []


def _safe_num(v, default):
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return f
    except Exception:
        return default


def recommend(width, height, fps, use="broadcast") -> dict:
    """按分辨率/帧率给出 AVS3 配置建议。永不抛错，非法输入回落 4K@50p 广播档。

    返回键：codec/profile/chroma/rc/ctc_qp/lowdelay/randomaccess/
    cbr_mbps/ffmpeg_args/notes。
    """
    try:
        w = _safe_num(width, 3840.0)
        h = _safe_num(height, 2160.0)
        f = _safe_num(fps, 50.0)
        w = min(max(int(w), 160), 7680)
        h = min(max(int(h), 120), 4320)
        f = min(max(int(f), 1), 120)
        use = str(use or "broadcast").strip().lower() or "broadcast"

        pixels = w * h
        if pixels <= 2_100_000:
            tier = "1080p"
            profile = "Main10" if use == "broadcast" else "Main"
            cbr = (8, 12) if f > 30 else (4, 8)
        elif pixels <= 9_000_000:
            tier = "4K"
            profile = "Main10"
            cbr = (30, 40) if f > 30 else (18, 25)
        else:
            tier = "8K"
            profile = "Main10"
            cbr = (80, 120)

        qp_hi, qp_lo = 27, 32  # 好 -> 差方向：QP 越小码率越高
        gop_ra = 32 if f <= 30 else 64
        intra_ra = max(gop_ra * 2, int(f * 2))  # 随机接入 ~2s 一个 CRA/IDR
        lowdelay = {
            "name": "lowdelay (HPM-LD / 低延时直播)",
            "gop": 4,
            "intra_period": int(f),       # ~1s 一个 I，抗误码 + 快加入
            "b_frames": 0,                # LD-P 零结构时延；要 B 可设 1~2（LD-B）
            "qp": qp_hi,
            "cbr_mbps": cbr[1],           # 低延时取区间上限，补偿无 B 结构的效率损失
            "latency": "零结构时延（仅前向参考），交互/直播用",
        }
        randomaccess = {
            "name": "randomaccess (HPM-RA / 点播/存储/广播编码)",
            "gop": gop_ra,
            "intra_period": intra_ra,
            "b_frames": 3,                # 分层 B，效率最高，REORDER 锯齿来源
            "qp": qp_lo,
            "cbr_mbps": cbr[0],
            "latency": f"结构时延约 {gop_ra} 帧（{gop_ra / max(f, 1):.1f}s@{f}fps），效率优先",
        }
        ffmpeg_args = [
            "# 占位：本机 ffmpeg 9.0.2 无 AVS3 编码器（仅 AVS1/cavs 解码），不可直接执行",
            "# 等效 uavs3e 草稿（二选一）：",
            f"#   uavs3e --config encode_RA.cfg -w {w} -h {h} --fps {f} "
            f"--qp {qp_lo} -o out_ra.avs3   # randomaccess/CQP",
            f"#   uavs3e --config encode_LD.cfg -w {w} -h {h} --fps {f} "
            f"--qp {qp_hi} -o out_ld.avs3   # lowdelay/CQP",
            f"# 广播 CBR 起点：{cbr[0]}~{cbr[1]} Mbps（{tier}@{f}fps，50/60p 取上限）",
        ]
        notes = [
            f"{tier}@{f}fps 广播建议 profile={profile} + 4:2:0 10bit（4K level 6.0.60 / 8K level 8.0.60）。",
            "CQP 锚点取 HPM CTC QP 22/27/32/37；画 BD-rate 曲线至少打 4 个点。",
            "lowdelay 比 randomaccess 同 QP 码率高约 10~20%，预算不足优先把 intra_period 拉长而不是加 QP。",
            "本工具联动：GOP 条看 IBB 节奏（有 B 即 RA 真身）；开 AVS3 LCU 层看 128 网格深浅（I 浅 / P/B 深）。",
        ]
        return {
            "codec": CODEC,
            "tier": tier,
            "width": w,
            "height": h,
            "fps": f,
            "use": use,
            "profile": profile,
            "chroma": "4:2:0",
            "bit_depth": 10 if profile in ("Main10", "High") else 8,
            "rc": ["CQP", "CBR"],
            "ctc_qp": list(CTC_QP_POINTS),
            "cbr_mbps": list(cbr),
            "lowdelay": lowdelay,
            "randomaccess": randomaccess,
            "ffmpeg_args": ffmpeg_args,
            "notes": notes,
        }
    except Exception:
        return {
            "codec": "avs3", "tier": "4K", "width": 3840, "height": 2160,
            "fps": 50, "use": "broadcast", "profile": "Main10",
            "chroma": "4:2:0", "bit_depth": 10, "rc": ["CQP", "CBR"],
            "ctc_qp": [22, 27, 32, 37], "cbr_mbps": [30, 40],
            "lowdelay": {"name": "lowdelay"}, "randomaccess": {"name": "randomaccess"},
            "ffmpeg_args": ["# AVS3 占位：本机无编码器"], "notes": ["fallback"],
        }


def paint_hint() -> str:
    """分析面板一句话提示（中文）。"""
    try:
        return ("AVS3 看两处：GOP 条 IBB 节奏（有 B 即 RA 真身）＋ LCU 128 网格深浅"
                "（I 浅蓝绿大块 / P、B 橙红碎块）；码率先看 CBR 区间，再用 CQP 四点打曲线。")
    except Exception:
        return ""
