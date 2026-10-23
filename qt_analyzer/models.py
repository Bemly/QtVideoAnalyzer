"""Shared data model. Mirrors original C# FrameInfo.cs / AnalysisResult.cs."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List


class PicType(IntEnum):
    Other = 0
    I = 1
    P = 2
    B = 3

    @property
    def letter(self) -> str:
        return {PicType.I: "I", PicType.P: "P", PicType.B: "B"}.get(self, "?")

    @property
    def long_name(self) -> str:
        return {
            PicType.I: "I (intra)",
            PicType.P: "P (predicted)",
            PicType.B: "B (bi-predicted)",
            PicType.Other: "? (unknown)",
        }[self]


@dataclass
class MotionField:
    cols: int
    rows: int
    dx: list  # int per block, small-frame pixels
    dy: list
    ref: list  # 0=unknown, 1=fwd(prev), 2=bwd(next)


@dataclass
class FrameInfo:
    index: int = 0
    decode_index: int = -1
    pts_time: float = 0.0
    dts_time: float = 0.0
    type: PicType = PicType.Other
    key_frame: bool = False
    packet_size: int = 0
    duration_ms: float = 40.0
    qp_avg: Optional[float] = None
    qp_min: Optional[float] = None
    qp_max: Optional[float] = None
    motion_mean: Optional[float] = None
    motion_fwd: int = 0
    motion_bwd: int = 0
    motion_max: Optional[float] = None
    motion_count: int = 0
    motion: Optional[MotionField] = None
    interlaced: bool = False
    repeat_pict: bool = False
    corrupt: bool = False
    discard: bool = False
    brain: bool = False
    gop_position: int = 0
    reorder_delta: int = 0
    bitrate_kbps: float = 0.0


@dataclass
class TypeStats:
    type: PicType
    count: int = 0
    bytes: int = 0
    total_frames: int = 0
    total_bytes: int = 0
    avg_qp: float = 0.0
    avg_motion: float = 0.0
    avg_size: float = 0.0

    @property
    def percent(self) -> float:
        return self.count * 100.0 / self.total_frames if self.total_frames else 0.0


@dataclass
class MediaInfo:
    file_path: str = ""
    file_name: str = ""
    file_size_bytes: int = 0
    format_name: str = "unknown"
    format_long_name: str = "unknown"
    container_bit_rate: int = 0
    duration: float = 0.0
    width: int = 0
    height: int = 0
    pix_fmt: str = "unknown"
    fps: float = 25.0
    nb_frames: int = 0
    # container time-base rate guess (tbr): for codecs whose probe lacks
    # dimensions/fps (AVS3) this carries the sequence-header frame rate.
    tbr: float = 0.0
    video_codec: str = "unknown"
    video_profile: str = "unknown"
    video_level: str = ""
    video_bit_rate: int = 0
    sar_num: int = 1
    sar_den: int = 1
    color_range: str = "unknown"
    color_space: str = "unknown"
    color_primaries: str = "unknown"
    color_transfer: str = "unknown"
    field_order: str = "unknown"
    codec_tag: str = ""
    audio_codec: str = "unknown"
    has_audio: bool = False
    sample_rate: int = 0
    channels: int = 0
    sample_format: str = "unknown"
    channel_layout: str = "unknown"
    audio_bit_rate: int = 0

    @property
    def duration_text(self) -> str:
        t = max(0.0, self.duration)
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int(round((t - int(t)) * 1000))
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
        return f"{m:02d}:{s:02d}.{ms:03d}"

    @property
    def video_line(self) -> str:
        level = f" L{self.video_level}" if self.video_level else ""
        return f"{self.video_codec} ({self.video_profile}{level})"

    @property
    def frame_rate_text(self) -> str:
        return f"{self.fps:.3f} fps" if self.fps > 0 else "unknown fps"

    @property
    def audio_line(self) -> str:
        if not self.has_audio:
            return "none"
        ch = "1 channel" if self.channels == 1 else f"{self.channels} channels"
        return f"{self.audio_codec} {self.sample_rate} Hz {ch} {self.sample_format}"

    def dar_text(self) -> str:
        if self.width <= 0 or self.height <= 0:
            return "?"
        ar = self.width * self.sar_num / (self.height * self.sar_den)
        for w, h in ((16, 9), (4, 3), (3, 2), (1, 1), (21, 9), (2, 1)):
            if abs(ar - w / h) < 0.02:
                return f"{w}:{h}"
        return f"{ar:.2f}"

    def format_line(self) -> str:
        long_name = self.format_long_name.split(",")[0].strip() or self.format_name
        if not long_name or long_name == "unknown":
            long_name = self.format_name
        import os as _os
        ext = _os.path.splitext(self.file_name)[1].lstrip(".").lower()
        if not ext or ext in long_name.lower():
            return long_name
        return f"{long_name}  ·  {ext}"


@dataclass
class AnalysisResult:
    media: MediaInfo = field(default_factory=MediaInfo)
    frames: List[FrameInfo] = field(default_factory=list)
    has_deep: bool = False
    qp_estimated: bool = False
    motion_estimated: bool = False
    # False when packet timestamps were missing (raw .bit etc.) and pts was
    # synthesized as i/fps: seeking must restart-from-0 + skip, and ffmpeg
    # must not use -ss/-fps_mode passthrough on such streams.
    timestamps_valid: bool = True
    max_bitrate: float = 0.0
    avg_bitrate: float = 0.0
    min_bitrate: float = 0.0
    max_qp: float = 51.0
    min_qp: float = 0.0
    max_motion: float = 1.0
    max_gop: int = 1
    max_reorder: int = 1
    min_reorder: int = 0
    i_stats: TypeStats = field(default_factory=lambda: TypeStats(PicType.I))
    p_stats: TypeStats = field(default_factory=lambda: TypeStats(PicType.P))
    b_stats: TypeStats = field(default_factory=lambda: TypeStats(PicType.B))
    o_stats: TypeStats = field(default_factory=lambda: TypeStats(PicType.Other))

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def duration_seconds(self) -> float:
        if not self.frames:
            return self.media.duration
        return self.frames[-1].pts_time + self.frames[-1].duration_ms / 1000.0

    def compute_aggregates(self) -> None:
        if not self.frames:
            return
        total_bytes = sum(f.packet_size for f in self.frames)
        self.avg_bitrate = sum(f.bitrate_kbps for f in self.frames) / len(self.frames)
        self.max_bitrate = max(f.bitrate_kbps for f in self.frames)
        self.min_bitrate = min(f.bitrate_kbps for f in self.frames)
        qps = [f.qp_avg for f in self.frames if f.qp_avg is not None]
        self.max_qp = max(qps) if qps else 51.0
        self.min_qp = min(qps) if qps else 0.0
        mots = [f.motion_mean for f in self.frames if f.motion_mean is not None]
        self.max_motion = max(mots) if mots else 1.0
        self.max_motion = max(self.max_motion, 1.0)
        self.max_gop = max((f.gop_position for f in self.frames), default=1)
        self.max_gop = max(self.max_gop, 1)
        self.max_reorder = max((f.reorder_delta for f in self.frames), default=1)
        self.min_reorder = min((f.reorder_delta for f in self.frames), default=0)
        for pt in (PicType.I, PicType.P, PicType.B, PicType.Other):
            fs = [f for f in self.frames if f.type == pt]
            b = sum(f.packet_size for f in fs)
            q = [f.qp_avg for f in fs if f.qp_avg is not None]
            m = [f.motion_mean for f in fs if f.motion_mean is not None]
            st = TypeStats(
                type=pt, count=len(fs), bytes=b,
                total_frames=len(self.frames), total_bytes=total_bytes,
                avg_qp=sum(q) / len(q) if q else 0.0,
                avg_motion=sum(m) / len(m) if m else 0.0,
                avg_size=b / len(fs) if fs else 0.0,
            )
            if pt == PicType.I:
                self.i_stats = st
            elif pt == PicType.P:
                self.p_stats = st
            elif pt == PicType.B:
                self.b_stats = st
            else:
                self.o_stats = st

    def frame_at(self, seconds: float) -> Optional[FrameInfo]:
        if not self.frames:
            return None
        lo, hi, best = 0, len(self.frames) - 1, 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.frames[mid].pts_time <= seconds:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return self.frames[best]

    def index_at(self, seconds: float) -> int:
        f = self.frame_at(seconds)
        return f.index if f else 0

    def gop_structure(self, limit: int = 64) -> str:
        """First-GOP letters e.g. IBBPBBP..., used by B/I/P panel."""
        out = []
        for f in self.frames[:limit]:
            out.append(f.type.letter)
            if f.key_frame and len(out) > 1:
                break
        return "".join(out) if out else "-"
