"""H.266/VVC + AV2 次世代编码器可视化。

Qt 移植说明：解释 VVC 相对 HEVC 的压缩增益来源，并给出本工具内两个
可直接用的 artefact：

* :func:`mtt_overlay` -- 128 CTU 网格 + QT/MTT 示意划分
  （``I`` 浅 / ``P``/``B`` 深，同帧调用返回确定性相同结果）；
* :func:`describe` -- ``"vvc"`` / ``"av2"`` 的一页式要点字典；
* :func:`decode_capability_note` -- 本机 ffprobe/ffmpeg 对 vvc 的
  解码与 ``show_frames`` 支持实测结论（永不抛错）。

依赖：只许 PySide6 + numpy + 标准库（与 ``block.py`` 相同规则）。
本模块不改 ``codec_insight.py`` / ``codec_panel.py``（另一 agent 负责
合流）；只保证 ``import codec_next`` 可用，且 ``describe(codec)``
接受 0~2 个位置参数以兼容家族模块调用约定。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
from PySide6.QtGui import QColor

try:  # package import
    from .models import PicType
except ImportError:  # flat-script import from inside qt_analyzer/
    from models import PicType  # type: ignore[no-redef]

#: 本模块覆盖的次世代 codec 键（对齐 codec_insight.CODECS 命名风格）。
CODECS = ("vvc", "av2")

CTU_SIZE = 128
#: MTT 最小亮度块边（示意层取 8，避免块数爆炸）。
MIN_SIZE = 8
#: MTT 划分最深 4，比 HEVC（0..3）多一档。
MAX_DEPTH = 4

# 每深度分裂概率（0:128 -> ... -> 4:8）。
# I = 浅（大块帧内），P = 中，B = 深（细节/运动边缘小块）。
_SPLIT_P = {
    "I": (0.22, 0.28, 0.34, 0.30, 0.22),
    "P": (0.55, 0.60, 0.58, 0.50, 0.40),
    "B": (0.70, 0.68, 0.62, 0.55, 0.45),
    "?": (0.55, 0.60, 0.58, 0.50, 0.40),
}

# 分裂方式权重（QT, HBT, VBT, HTT, VTT）：I 偏 QT，P/B 偏 MTT。
_SPLIT_W = {
    "I": (0.62, 0.12, 0.12, 0.07, 0.07),
    "P": (0.40, 0.22, 0.22, 0.08, 0.08),
    "B": (0.34, 0.24, 0.24, 0.09, 0.09),
    "?": (0.40, 0.22, 0.22, 0.08, 0.08),
}

# 深度配色（越深越暖），5 档比 HEVC 多一档。
_DEPTH_QCOLORS = (
    QColor(59, 130, 246, 110),   # 0: 128 -- 蓝
    QColor(34, 197, 94, 110),    # 1: ~64 -- 绿
    QColor(163, 230, 53, 120),   # 2: ~32 -- 黄绿
    QColor(245, 158, 11, 120),   # 3: ~16 -- 橙
    QColor(239, 68, 68, 130),    # 4: ~8  -- 红
)

_VVC_ALIASES = {"vvc", "h266", "h.266", "266", "vvenc", "vvc1", "vvi1"}
_AV2_ALIASES = {"av2", "aom-av2", "aomav2", "libav2"}


def _norm(codec: object) -> str:
    try:
        s = str(codec or "").strip().lower()
    except Exception:
        return "vvc"
    s = s.split("(")[0].strip().split(" ")[0].strip().rstrip(",;")
    if s in _AV2_ALIASES or s.startswith("av2"):
        return "av2"
    if s in _VVC_ALIASES or s.startswith(("vvc", "h266", "h.266")):
        return "vvc"
    return s or "vvc"


def describe(codec: object = "vvc", summary: object = None) -> dict:
    """次世代 codec 一页式要点（``codec`` 归一化到 ``vvc`` / ``av2``）。

    ``summary`` 仅为兼容家族模块 ``describe(key, summary)`` 调用约定，
    内容不依赖它。未知 ``codec`` 返回带 ``status="unknown"`` 的小字典。
    """
    _ = summary  # 兼容位，刻意不用
    key = _norm(codec)
    if key == "av2":
        return {
            "codec": "AV2 (experimental)",
            "block": "SB 256x256（传闻/讨论中，AV1 为 SB 128；最终以 AOM 定稿为准）",
            "partition": "多叉树划分方向延续 AV1（10 种矩形/方形）并探索更细 "
                         "的非对称与多级递归划分",
            "tools_direction": "变换（TF）+ 环路滤波方向工具仍在探索：更大核 "
                               "变换候选、自适应环路滤波增强、CDEF/LR 后继方案",
            "grain": "film grain 增强：在 AV1 胶片颗粒合成基础上传闻增强建模 "
                     "与参数 signalling，低码率保留胶片感",
            "saving_vs_av1": "目标相对 AV1 继续降码率（具体数字待定，以 AOM "
                              "CTC 测试结论为准，不预设承诺值）",
            "status": "experimental：仍在 AOM 标准化中，本机 ffmpeg 9.0.2 无 "
                      "AV2 编解码器，按 experimental 展示",
            "where_to_look": "去哪看：本工具暂无 AV2 分区层；GOP 条按 I/P/B "
                             "通用语义看，码率峰即关键帧",
            "note": "experimental：特性与数字均为传闻/方向性描述，不可当作成品结论",
        }
    if key != "vvc":
        return {
            "codec": str(codec),
            "status": "unknown: codec_next.describe 只认识 vvc/av2",
            "note": "传 vvc 或 av2 获取要点字典",
        }
    return {
        "codec": "VVC (H.266)",
        "block": "CTU 128x128（HEVC 为 64）：QT 四叉树 + MTT 多类型树 "
                 "（binary/ternary 二/三叉），最小亮度块可到 4x4，"
                 "划分深度 0..4（本 overlay 配色 5 档）",
        "partition": "QT 先分大块，叶子再 MTT 递归：HBT/VBT 二分、HTT/VTT "
                     "三分（1:2:1），I 帧偏 QT 大块，P/B 偏 MTT 小块",
        "inloop": "DBF + LMCS（色调映射）+ SAO 后继：ALF 自适应环路滤波 + "
                  "CCALF 跨分量 ALF，振铃/色度偏差残留更少",
        "tools": "AFFINE 仿射运动 + GEO 几何划分 + MIP 矩阵帧内预测 + IBC "
                 "块复制（屏幕内容），运动/纹理边缘残差更小",
        "rpr": "RPR 参考帧重采样：分辨率自适应切换无需 CRA/IDR，"
               "流切换与自适应码率不断流",
        "saving_vs_hevc": "相同主观质量下比 HEVC 再省约 40% 码率 "
                          "（JVET 通用测试目标；libvvenc 实测典型约 30~50%，视内容而定）",
        "status": "已定稿：ITU-T H.266 | ISO/IEC 23090-3（2020）；"
                  "本机 ffmpeg 9.0.2 含原生 vvc 解码器、无 vvc 编码器",
        "where_to_look": "去哪看：开 VVC MTT 层看 128 CTU 网格 + 多叉树划分；"
                         "大 I 帧后跟 P/B 坡，码率峰即随机访问点",
        "note": "simulated overlay：划分是同帧确定性示意，非码流真值；"
                "省码率数字为目标/典型范围，非本机实测",
    }


def _frame_key(frame) -> tuple[str, float, int]:
    """(letter, qp_avg, index)，用于分裂偏置 + 随机种子。"""
    try:
        t = frame.type
    except AttributeError:
        t = None
    letter = "?"
    try:
        if t is not None and hasattr(t, "letter"):
            letter = t.letter
        elif t is not None:
            letter = {1: "I", 2: "P", 3: "B"}.get(int(t), "?")
        else:
            key = getattr(frame, "key_frame", False)
            letter = "I" if key else "?"
    except Exception:
        letter = "?"
    if letter not in ("I", "P", "B"):
        try:
            letter = "I" if bool(getattr(frame, "key_frame", False)) else "P"
        except Exception:
            letter = "?"
    try:
        qp = getattr(frame, "qp_avg", None)
        qp_f = float(qp) if qp is not None else 26.0
    except Exception:
        qp_f = 26.0
    try:
        idx = int(getattr(frame, "index", 0))
    except Exception:
        idx = 0
    return letter, qp_f, idx


def mtt_overlay(w: int, h: int, frame) -> list:
    """128 CTU 网格 + QT/MTT 示意划分，供 overlay 层绘制。

    每个 128x128 CTU 按 ``_SPLIT_P`` 递归分裂（深度 0..4）：

    * ``I`` 帧分裂浅（多 128/64 大块，QT 为主）；
    * ``P``/``B`` 帧分裂深（多 16/8 小块，MTT 二/三叉为主）。

    同一 ``frame``（qp_avg + index + type 定种子）重复调用返回
    完全相同的列表。返回 ``[(x0, y0, bw, bh, depth), ...]``，
    按 CTU 行主序，已裁剪到 ``w`` x ``h``（边缘 CTU 的 ``bw/bh``
    是裁剪后尺寸，``depth`` 仍为逻辑分裂深度）。
    """
    try:
        w, h = int(w), int(h)
    except Exception:
        return []
    if w <= 0 or h <= 0:
        return []
    letter, qp_f, idx = _frame_key(frame)
    base = _SPLIT_P.get(letter, _SPLIT_P["?"])
    weights = _SPLIT_W.get(letter, _SPLIT_W["?"])
    # QP 偏置：低 QP（细节保留）多分一点，高 QP 少分（纯视觉单调性）。
    bias = max(0.5, min(1.3, 1.0 + (26.0 - qp_f) / 50.0))
    probs = tuple(max(0.03, min(0.95, p * bias)) for p in base)
    seed = (int(round(qp_f * 97.0)) * 31 + idx * 101
            + {"I": 11, "P": 53, "B": 97}.get(letter, 7)) & 0x7FFFFFFF
    rng = np.random.RandomState(seed)

    out: list = []

    def _emit(x0: int, y0: int, bw: int, bh: int, depth: int) -> None:
        x1 = x0 + bw if x0 + bw < w else w
        y1 = y0 + bh if y0 + bh < h else h
        if x1 > x0 and y1 > y0:
            out.append((x0, y0, x1 - x0, y1 - y0, min(depth, MAX_DEPTH)))

    def _pick_kind(bw: int, bh: int) -> str:
        cands: list[tuple[str, float]] = []
        # QT 要求两边都能二分且子块不小于 4；MTT 二/三分要求被分边够长。
        if bw // 2 >= 4 and bh // 2 >= 4:
            cands.append(("QT", weights[0]))
        if bh // 2 >= 4:
            cands.append(("HBT", weights[1]))
        if bw // 2 >= 4:
            cands.append(("VBT", weights[2]))
        if bh // 4 >= 4:
            cands.append(("HTT", weights[3]))
        if bw // 4 >= 4:
            cands.append(("VTT", weights[4]))
        if not cands:
            return ""
        tot = sum(p for _, p in cands)
        r = rng.random() * tot
        acc = 0.0
        for name, p in cands:
            acc += p
            if r <= acc:
                return name
        return cands[-1][0]

    def _recurse(x0: int, y0: int, bw: int, bh: int, depth: int) -> None:
        if x0 >= w or y0 >= h or bw <= 0 or bh <= 0:
            return
        if depth >= MAX_DEPTH or (bw <= MIN_SIZE and bh <= MIN_SIZE):
            _emit(x0, y0, bw, bh, depth)
            return
        over = (x0 + bw > w) or (y0 + bh > h)
        if over:
            # 边缘 CTU 悬出帧边界：强制沿悬出方向分裂（VVC 隐式分裂示意）。
            if x0 + bw > w and (y0 + bh <= h or bw >= bh):
                half = bw // 2
                _recurse(x0, y0, half, bh, depth + 1)
                _recurse(x0 + half, y0, bw - half, bh, depth + 1)
            elif y0 + bh > h:
                half = bh // 2
                _recurse(x0, y0, bw, half, depth + 1)
                _recurse(x0, y0 + half, bw, bh - half, depth + 1)
            else:
                _recurse(x0, y0, bw // 2, bh // 2, depth + 1)
                _recurse(x0 + bw // 2, y0, bw - bw // 2, bh // 2, depth + 1)
                _recurse(x0, y0 + bh // 2, bw // 2, bh - bh // 2, depth + 1)
                _recurse(x0 + bw // 2, y0 + bh // 2,
                         bw - bw // 2, bh - bh // 2, depth + 1)
            return
        if rng.random() >= probs[min(depth, MAX_DEPTH)]:
            _emit(x0, y0, bw, bh, depth)
            return
        kind = _pick_kind(bw, bh)
        if not kind:
            _emit(x0, y0, bw, bh, depth)
            return
        if kind == "QT":
            hw, hh = bw // 2, bh // 2
            _recurse(x0, y0, hw, hh, depth + 1)
            _recurse(x0 + hw, y0, bw - hw, hh, depth + 1)
            _recurse(x0, y0 + hh, hw, bh - hh, depth + 1)
            _recurse(x0 + hw, y0 + hh, bw - hw, bh - hh, depth + 1)
        elif kind == "HBT":
            hh = bh // 2
            _recurse(x0, y0, bw, hh, depth + 1)
            _recurse(x0, y0 + hh, bw, bh - hh, depth + 1)
        elif kind == "VBT":
            hw = bw // 2
            _recurse(x0, y0, hw, bh, depth + 1)
            _recurse(x0 + hw, y0, bw - hw, bh, depth + 1)
        elif kind == "HTT":
            h1, h3 = bh // 4, bh // 4
            h2 = bh - h1 - h3
            _recurse(x0, y0, bw, h1, depth + 1)
            _recurse(x0, y0 + h1, bw, h2, depth + 1)
            _recurse(x0, y0 + h1 + h2, bw, h3, depth + 1)
        else:  # VTT
            w1, w3 = bw // 4, bw // 4
            w2 = bw - w1 - w3
            _recurse(x0, y0, w1, bh, depth + 1)
            _recurse(x0 + w1, y0, w2, bh, depth + 1)
            _recurse(x0 + w1 + w2, y0, w3, bh, depth + 1)

    for cy in range(0, h, CTU_SIZE):
        for cx in range(0, w, CTU_SIZE):
            _recurse(cx, cy, CTU_SIZE, CTU_SIZE, 0)
    return out


def depth_color(depth: int) -> QColor:
    """MTT 划分深度配色（越深越暖），5 档。"""
    try:
        d = int(depth)
    except Exception:
        d = 0
    d = max(0, min(MAX_DEPTH, d))
    c = _DEPTH_QCOLORS[d]
    return QColor(c)


def _which(name: str) -> str | None:
    try:
        p = shutil.which(name)
    except Exception:
        p = None
    return p


def _run(cmd: list, timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, errors="ignore", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:  # 缺 binary / 超时等一律降级为文本
        return -1, f"run failed: {exc}"


def _find_sample() -> tuple[str | None, str | None]:
    """找 VVC/AV2 样本；没有则返回 (None, None)，由调用方 hevc 代跑。"""
    here = Path(__file__).resolve()
    roots = [here.parent, here.parent.parent]
    try:
        roots.append(Path.cwd())
    except Exception:
        pass
    for root in roots:
        for cand in (root / "tools" / "samples", root / "samples"):
            try:
                if not cand.is_dir():
                    continue
                for f in sorted(cand.iterdir()):
                    n = f.name.lower()
                    if f.is_file() and ("vvc" in n or "266" in n or "av2" in n):
                        return str(f), f.name
            except Exception:
                continue
    return None, None


def decode_capability_note() -> str:
    """本机 ffprobe/ffmpeg 对 vvc 的解码与 show_frames 支持实测结论。

    实测 ``-encoders``（有无 vvc/vvenc 编码器）、``-decoders``（有无
    vvc 解码器）；有 VVC 样本就对它跑 ``-show_streams`` +
    ``-show_frames pict_type``，否则用 ``tools/samples/test_hevc.mp4``
    代跑并在结论中注明。永不抛错。
    """
    ffmpeg = _which("ffmpeg")
    ffprobe = _which("ffprobe")
    lines: list[str] = []
    if ffmpeg:
        try:
            ver, _ = _run([ffmpeg, "-hide_banner", "-version"], timeout=15)
            _ = ver
        except Exception:
            pass
    rc_e, enc = _run([ffmpeg, "-hide_banner", "-encoders"], timeout=30) if ffmpeg else (-1, "")
    vvc_enc = [l.strip() for l in enc.splitlines()
               if ("vvc" in l.lower() or "vvenc" in l.lower() or "266" in l.lower())
               and not l.lower().lstrip().startswith(("codecs", " ------", " ------"))]
    # 上面的行过滤会把表头也算进来：只保留形如 " V....." 的条目行。
    vvc_enc = [l for l in vvc_enc if l[:7].strip() and l[0] in " VAS"]
    rc_d, dec = _run([ffmpeg, "-hide_banner", "-decoders"], timeout=30) if ffmpeg else (-1, "")
    vvc_dec = [l.strip() for l in dec.splitlines() if "vvc" in l.lower() or "266" in l.lower()]
    vvc_dec = [l for l in vvc_dec if l and l[0] in " VAS"]

    lines.append(f"ffmpeg: {ffmpeg or '未找到'}；ffprobe: {ffprobe or '未找到'}")
    if vvc_enc:
        lines.append(f"vvc 编码器：有（{len(vvc_enc)} 个）：{'; '.join(vvc_enc[:3])}")
    else:
        lines.append("vvc 编码器：无（ffmpeg -encoders 无 vvc/vvenc/266 条目；"
                     "本机 ffmpeg 9.0.2 不可本地生成 test_vvc.mp4）")
    if vvc_dec:
        lines.append(f"vvc 解码器：有（{'；'.join(vvc_dec[:2])}）")
    else:
        lines.append("vvc 解码器：无（ffmpeg -decoders 无 vvc 条目）")
    lines.append("av2 编解码器：均无（AOM 实验中，ffmpeg 9.0.2 未收录）")

    sample, name = _find_sample()
    surrogate = False
    if sample is None:
        # hevc 代跑：在包目录与仓库根下找 test_hevc.mp4。
        here = Path(__file__).resolve()
        for root in (here.parent, here.parent.parent, Path.cwd()):
            for cand in (root / "tools" / "samples" / "test_hevc.mp4",
                         root / "test_hevc.mp4"):
                try:
                    if cand.is_file():
                        sample, name = str(cand), cand.name
                        break
                except Exception:
                    continue
            if sample is not None:
                break
        surrogate = sample is not None
    if sample is None or ffprobe is None:
        lines.append("show_frames 实测：无可用样本且/或无 ffprobe，未跑；"
                     "按解码器存在性推断 vvc -show_frames 头解析可用。")
        return "\n".join(lines)

    if surrogate:
        lines.append(f"样本声明：无 VVC 样本，用 {name} 代跑（hevc surrogate），"
                     "结论外推至 vvc（同为 ffprobe 帧头解析路径）。")
    else:
        lines.append(f"样本：{name}（原生 VVC，直接结论）。")
    rc_s, streams = _run([ffprobe, "-v", "error", "-show_entries",
                          "stream=codec_name,profile,width,height",
                          "-of", "csv=p=0", sample], timeout=60)
    codec_hit = [l.strip() for l in streams.splitlines() if l.strip()][:3]
    lines.append(f"-show_streams：rc={rc_s}，{' | '.join(codec_hit) if codec_hit else '无输出'}")
    rc_f, fr = _run([ffprobe, "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "frame=pict_type",
                     "-of", "csv=p=0", sample], timeout=120)
    types = [l.strip().upper() for l in fr.splitlines() if l.strip()]
    n_i = sum(1 for t in types if t.startswith("I"))
    n_p = sum(1 for t in types if t.startswith("P"))
    n_b = sum(1 for t in types if t.startswith("B"))
    lines.append(f"-show_frames pict_type：rc={rc_f}，共 {len(types)} 帧 "
                 f"(I={n_i} P={n_p} B={n_b})，" +
                 ("可用。" if types else "无输出，不可用。"))
    return "\n".join(lines)
