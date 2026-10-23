"""CodecDNA 统一入口：codec 归一化 + 结果摘要 + 家族描述降级。

等 4 个家族模块就绪即插即用，缺失时用内置 fallback，保证 import 永不抛错。
家族模块（全部可选）:
  codec_avc_h263   -> avc / h263 / mpeg2
  codec_hevc       -> hevc
  codec_vp         -> vp6 / vp8 / vp9
  codec_theora_av1 -> theora / av1
每个家族模块若提供 describe(key, summary) / describe(summary) / describe()
或 BULLETS / DESCRIBE 字典，即优先采用；否则 fallback。
只依赖标准库（+ typing），永不抛错。
"""
from __future__ import annotations

CODECS = ["avc", "hevc", "mpeg2", "theora", "av1", "h263", "vp6", "vp8", "vp9"]

# ---- 可选家族模块：缺失则为 None（import 永不抛错） ----
_m_avc = None
_m_hevc = None
_m_vp = None
_m_tav1 = None
try:
    from . import codec_avc_h263 as _m_avc  # type: ignore
except Exception:
    _m_avc = None
try:
    from . import codec_hevc as _m_hevc  # type: ignore
except Exception:
    _m_hevc = None
try:
    from . import codec_vp as _m_vp  # type: ignore
except Exception:
    _m_vp = None
try:
    from . import codec_theora_av1 as _m_tav1  # type: ignore
except Exception:
    _m_tav1 = None


def codec_key(video_codec: object) -> str:
    """归一化 ffprobe codec_name -> CODECS 键。未知返回小写原串或 'unknown'。"""
    try:
        s = str(video_codec or "").strip().lower()
    except Exception:
        return "unknown"
    if not s:
        return "unknown"
    # 去掉括号后缀如 "h264 (High)" / 前缀空格
    s = s.split("(")[0].strip().split(" ")[0].strip()
    alias = {
        "h264": "avc", "avc": "avc", "avc1": "avc", "x264": "avc",
        "h265": "hevc", "hevc": "hevc", "hvc1": "hevc", "hev1": "hevc",
        "x265": "hevc", "h.265": "hevc", "h.264": "avc",
        "mpeg2": "mpeg2", "mpeg2video": "mpeg2", "mpeg-2": "mpeg2",
        "mpeg1video": "mpeg2", "mpeg1": "mpeg2",
        "theora": "theora",
        "av1": "av1", "av01": "av1", "libaom-av1": "av1", "libaom": "av1",
        "libsvtav1": "av1", "aom": "av1",
        "h263": "h263", "h.263": "h263", "h263p": "h263",
        "vp6": "vp6", "vp6f": "vp6", "vp6s": "vp6",
        "vp8": "vp8", "libvpx": "vp8",
        "vp9": "vp9", "libvpx-vp9": "vp9",
        "mpeg4": "mpeg4", "mp4v": "mpeg4",
    }
    if s in alias:
        return alias[s]
    # 前缀兜底：如 "avc1.640028"
    for pre, dst in (("avc", "avc"), ("h264", "avc"), ("hevc", "hevc"),
                     ("h265", "hevc"), ("hvc", "hevc"), ("vp9", "vp9"),
                     ("vp8", "vp8"), ("vp6", "vp6"), ("av1", "av1"),
                     ("av01", "av1"), ("theora", "theora"), ("mpeg2", "mpeg2")):
        if s.startswith(pre):
            return dst
    return s or "unknown"


def family_of(key: str) -> str:
    """CODECS 键 -> 家族徽章显示名。"""
    try:
        k = str(key or "").strip().lower()
    except Exception:
        return "UNKNOWN"
    m = {
        "avc": "AVC",
        "hevc": "HEVC",
        "mpeg2": "MPEG-2",
        "theora": "Theora",
        "av1": "AV1",
        "h263": "H.263",
        "vp6": "VP6",
        "vp8": "VP8",
        "vp9": "VP9",
    }
    return m.get(k, (k.upper() if k and k != "unknown" else "UNKNOWN"))


def _family_module(key: str):
    k = str(key or "").lower()
    if k in ("avc", "h263", "mpeg2", "mpeg4"):
        return _m_avc
    if k == "hevc":
        return _m_hevc
    if k in ("vp6", "vp8", "vp9"):
        return _m_vp
    if k in ("theora", "av1"):
        return _m_tav1
    return None


# ---- 内置 fallback 描述 / 去哪看 ----
_FALLBACK_BULLETS = {
    "avc": [
        "MB 16×16 + 4×4/8×8 子划分，兼容最广",
        "CABAC/CAVLC 熵编码，码率-质量折中稳",
        "B 帧双向预测省码率，I 帧即随机访问点",
    ],
    "hevc": [
        "CTU 64×64 四叉树 + 35 种帧内方向，压缩率翻倍",
        "SAO/DBF 环路滤波，块效应更少",
        "Tiles/WPP 并行，4K 主力编码",
    ],
    "mpeg2": [
        "MB 16×16 + 帧/场自适应，广播 DVD 基石",
        "固定 VLC 熵编码，解码极简",
        "典型 IBBP GOP，I 间距即频道切换延迟",
    ],
    "theora": [
        "VP3 系开放编码，免专利费",
        "Huffman 熵编码 + 块自适应量化",
        "质量波动大，看 QP 行找糊帧",
    ],
    "av1": [
        "SB 128×128 + 56 种帧内方向，压缩率最高",
        "多符号熵编码 + CDEF/LR 环路滤波",
        "film grain 合成，胶片感低码率保留",
    ],
    "h263": [
        "GOB 层 + 可变块尺寸，低码率会议起源",
        "VLC + 可选算术编码，3G 时代主力",
        "看 GOB 头与 MB 行找误码扩散",
    ],
    "vp6": [
        "TrueMotion VP6，Flash 时代流媒体",
        "算术熵编码前身，低码率尚可",
        "看 I/P 节奏，无 B 帧多为 IPP",
    ],
    "vp8": [
        "VP8 bool 熵编码器，简单高效免专利纠纷后开放",
        "宏块 16×16 + 4×4 子块，环路滤波",
        "无 B 帧，多为 AltRef 替代（周期大P）",
    ],
    "vp9": [
        "SuperBlock 64×64 + AltRef 隐藏帧省码率",
        "bool 熵编码 + 分段量化 segment map",
        "AltRef 不显示，找周期大P即 AltRef",
    ],
}

_WHERE = {
    "avc": "去哪看：开 AVC分区层看 MB 16×16 划分；GOP 条 I红高/P蓝中/B绿矮",
    "hevc": "去哪看：开 CTU 层看四叉树；大 I 帧后跟 P/B 坡",
    "mpeg2": "去哪看：GOP 条看 IBBP 节奏；interlaced 标记看场编码",
    "theora": "去哪看：GOP 条 + QP 行看质量波动；B 帧少多为 IP",
    "av1": "去哪看：开 AV1 SB 层看 128×128 分块；CDEF 后块效应少",
    "h263": "去哪看：开 H.263 GOB 层看 GOB 头与 MB 行",
    "vp6": "去哪看：GOP 条看 IPP 节奏；码率峰即关键帧",
    "vp8": "去哪看：找周期大P=AltRef（金星标）；开 VP分段层看 segment",
    "vp9": "去哪看：找周期大P=AltRef（金星标）；开 VP分段层看 segment map",
}

_ENTROPY = {
    "avc": "CABAC/CAVLC", "hevc": "CABAC", "mpeg2": "VLC",
    "theora": "Huffman(VP3)", "av1": "multi-symbol",
    "h263": "VLC", "vp6": "arithmetic", "vp8": "bool coder",
    "vp9": "bool coder",
}

_CTU = {
    "avc": "MB 16×16", "hevc": "CTU 64×64", "mpeg2": "MB 16×16",
    "theora": "MB 16×16", "av1": "SB 128×128", "h263": "GOB/MB 16×16",
    "vp6": "MB 16×16", "vp8": "MB 16×16", "vp9": "SB 64×64",
}


def where_to_look(key: str) -> str:
    try:
        k = str(key or "").strip().lower()
    except Exception:
        k = ""
    return _WHERE.get(k, "去哪看：GOP 条 I红/P蓝/B绿 + 码率峰看关键帧")


def _try_family_describe(key: str, summary: dict | None):
    """尝试调用家族模块 describe，成功返回 list[str]，否则 None。永不抛错。"""
    try:
        mod = _family_module(key)
        if mod is None:
            return None
        # 候选函数名
        for attr in ("describe", "bullets", "describe_family", "info"):
            try:
                fn = getattr(mod, attr, None)
            except Exception:
                fn = None
            if fn is None:
                continue
            try:
                if callable(fn):
                    import inspect as _insp
                    try:
                        n = len(_insp.signature(fn).parameters)
                    except Exception:
                        n = 2
                    if n == 0:
                        out = fn()
                    elif n == 1:
                        try:
                            out = fn(key)
                        except Exception:
                            out = fn(summary if summary is not None else key)
                    else:
                        try:
                            out = fn(key, summary)
                        except TypeError:
                            out = fn(summary)
                    if isinstance(out, str):
                        lines = [l.strip("- •* \t") for l in out.splitlines() if l.strip()]
                        if len(lines) >= 1:
                            return lines[:3] if len(lines) >= 3 else lines
                    elif isinstance(out, dict):
                        # 家族模块多返回 dict 卡片：优先 strengths / bullets 类列表；
                        # references 这种短名表放最后（不如描述性长句有用）
                        for dk in ("strengths", "bullets", "highlights", "advantages"):
                            try:
                                v = out.get(dk)
                            except Exception:
                                v = None
                            if isinstance(v, (list, tuple)) and v:
                                ls = [str(x) for x in v if str(x).strip()]
                                if ls:
                                    return ls[:3]
                            elif isinstance(v, str) and v.strip():
                                return [v.strip()]
                        # 通用组装：block/partition + entropy + refs/gop/note
                        try:
                            parts: list[str] = []
                            for dk in ("block", "partitions", "block_sizes", "ctu",
                                       "segmentation", "overlay_style"):
                                vv = out.get(dk)
                                if isinstance(vv, (list, tuple)) and vv:
                                    parts.append(" / ".join(str(x) for x in vv[:2]))
                                    break
                                if isinstance(vv, str) and vv.strip():
                                    parts.append(vv.strip())
                                    break
                            for dk in ("entropy", "entropy_short", "loop_filter",
                                       "quant", "transform"):
                                vv = out.get(dk)
                                if isinstance(vv, str) and vv.strip():
                                    parts.append(vv.strip())
                                    break
                            for dk in ("notes", "note", "tool_note", "ref_note",
                                       "bframes_note", "compound_note", "saving_vs_avc",
                                       "full_name"):
                                vv = out.get(dk)
                                if isinstance(vv, str) and vv.strip():
                                    parts.append(vv.strip())
                                    break
                            parts = [p for p in parts if p]
                            if parts:
                                return parts[:3]
                        except Exception:
                            pass
                        for dk in ("refs", "references", "notes"):
                            try:
                                v = out.get(dk)
                            except Exception:
                                v = None
                            if isinstance(v, (list, tuple)) and v:
                                ls = [str(x) for x in v if str(x).strip()]
                                if ls:
                                    return ls[:3]
                            elif isinstance(v, str) and v.strip():
                                return [v.strip()]
                        # dict 本身转一行兜底
                        try:
                            fam = str(out.get("family", out.get("codec", key)))
                            full = str(out.get("full_name", ""))
                            if full:
                                return [f"{fam}：{full}"]
                        except Exception:
                            pass
                    elif isinstance(out, (list, tuple)):
                        ls = [str(x) for x in out if str(x).strip()]
                        if ls:
                            return ls[:3] if len(ls) >= 3 else ls
                elif isinstance(fn, dict):
                    v = fn.get(key) or fn.get(str(key).upper()) or fn.get("default")
                    if isinstance(v, (list, tuple)) and v:
                        return [str(x) for x in v][:3]
                elif isinstance(fn, (list, tuple)) and fn:
                    return [str(x) for x in fn][:3]
            except Exception:
                continue
        # 候选常量名
        for attr in ("BULLETS", "DESCRIBE", "DESCRIPTION"):
            try:
                v = getattr(mod, attr, None)
            except Exception:
                v = None
            if isinstance(v, dict):
                vv = v.get(key) or v.get(str(key).upper())
                if isinstance(vv, (list, tuple)) and vv:
                    return [str(x) for x in vv][:3]
                if isinstance(vv, str) and vv.strip():
                    return [vv.strip()]
            elif isinstance(v, (list, tuple)) and v:
                return [str(x) for x in v][:3]
    except Exception:
        return None
    return None


def describe(key: str, summary: dict | None = None) -> list[str]:
    """3 条优势 bullet：家族模块 describe() 第一优先级，否则 fallback。永不抛错。"""
    try:
        k = str(key or "").strip().lower() or "unknown"
    except Exception:
        k = "unknown"
    try:
        out = _try_family_describe(k, summary)
        if out:
            # 补足 3 条
            fb = _FALLBACK_BULLETS.get(k, _FALLBACK_BULLETS.get("avc", []))
            merged = list(out)
            for b in fb:
                if len(merged) >= 3:
                    break
                if b not in merged:
                    merged.append(b)
            return merged[:3]
    except Exception:
        pass
    try:
        fb = _FALLBACK_BULLETS.get(k)
        if fb:
            return list(fb)
        return [
            "帧类型 / GOP / QP / 运动四维已就绪",
            "GOP 条 I红高/P蓝中/B绿矮，金星=AltRef 候选",
            "切 Codec 层看分区：AVC MB / HEVC CTU / VP 分段 / AV1 SB",
        ]
    except Exception:
        return ["-", "-", "-"]


def summarize(result) -> dict:
    """AnalysisResult -> dict。永不抛错，缺字段降级为 0/False。"""
    try:
        frames = list(getattr(result, "frames", None) or [])
    except Exception:
        frames = []
    try:
        media = getattr(result, "media", None)
        raw = getattr(media, "video_codec", "unknown") if media is not None else "unknown"
    except Exception:
        raw = "unknown"
    try:
        key = codec_key(raw)
    except Exception:
        key = "unknown"
    try:
        fam = family_of(key)
    except Exception:
        fam = "UNKNOWN"
    n = len(frames)
    try:
        i_c = int(getattr(getattr(result, "i_stats", None), "count", 0) or 0)
        p_c = int(getattr(getattr(result, "p_stats", None), "count", 0) or 0)
        b_c = int(getattr(getattr(result, "b_stats", None), "count", 0) or 0)
        if (i_c + p_c + b_c) == 0 and n:
            # 回退：按帧 type 计数
            i_c = p_c = b_c = 0
            for f in frames:
                try:
                    letter = str(getattr(getattr(f, "type", None), "letter", "?"))
                except Exception:
                    letter = "?"
                if letter == "I":
                    i_c += 1
                elif letter == "P":
                    p_c += 1
                elif letter == "B":
                    b_c += 1
    except Exception:
        i_c = p_c = b_c = 0
    try:
        bframes = bool(b_c > 0)
    except Exception:
        bframes = False
    # key 间隔 / avg_gop：关键帧间距均值
    try:
        key_idx = [i for i, f in enumerate(frames) if bool(getattr(f, "key_frame", False))]
        if len(key_idx) >= 2:
            diffs = [b - a for a, b in zip(key_idx, key_idx[1:])]
            key_interval = sum(diffs) / len(diffs) if diffs else float(n or 0)
        elif len(key_idx) == 1:
            key_interval = float(n or 0)
        else:
            key_interval = float(n or 0)
        avg_gop = float(key_interval)
    except Exception:
        key_interval = float(n or 0)
        avg_gop = float(n or 0)
    # altref 候选：P 帧中显著偏大者（>1.5x 中位数）
    try:
        p_sizes = sorted(int(getattr(f, "packet_size", 0) or 0)
                         for f in frames
                         if str(getattr(getattr(f, "type", None), "letter", "?")) == "P")
        altref_count = 0
        if p_sizes:
            mid = p_sizes[len(p_sizes) // 2]
            if mid > 0:
                thr = mid * 1.5
                altref_count = sum(1 for s in p_sizes if s >= thr)
    except Exception:
        altref_count = 0
    try:
        ctu_or_sb = _CTU.get(key, "-")
    except Exception:
        ctu_or_sb = "-"
    try:
        entropy_hint = _ENTROPY.get(key, "unknown")
    except Exception:
        entropy_hint = "unknown"
    try:
        qp_est = bool(getattr(result, "qp_estimated", False))
        has_qp = False
        for f in frames[:64]:
            try:
                if getattr(f, "qp_avg", None) is not None:
                    has_qp = True
                    break
            except Exception:
                continue
        qp_native = bool(has_qp and not qp_est)
    except Exception:
        qp_native = False
    return {
        "family": fam,
        "codec": key,
        "bframes": bool(bframes),
        "i": int(i_c),
        "p": int(p_c),
        "b": int(b_c),
        "key_interval": float(key_interval),
        "avg_gop": float(avg_gop),
        "altref_count": int(altref_count),
        "ctu_or_sb": str(ctu_or_sb),
        "entropy_hint": str(entropy_hint),
        "qp_native": bool(qp_native),
    }
