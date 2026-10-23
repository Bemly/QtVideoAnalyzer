"""Progressive analysis orchestration: probe -> packets -> deep passes.

Mirrors ``AnalysisService.cs`` (``AnalysisPipeline``):

1. probe   (~0.3 s) container / stream metadata -> info panel, playback
2. packets (~0.5 s) size / pts / dts / key flags -> bitrate, GOP, reorder
3. type+QP          picture types and real QP           (``deep_qp`` module)
4. motion           block-matched motion field          (``motion`` module)

Stages 3+4 are owned by other modules (``run_type_qp`` / ``run_motion``);
this file only adapts to them. When either module (or entry point) is
missing, the pass is skipped and the corresponding
``qp_estimated`` / ``motion_estimated`` flag is set.

All functions are synchronous -- the Qt layer runs them on a QThread.
Standard library + subprocess only (no Qt bindings of any kind).
"""
from __future__ import annotations

import importlib
import inspect
from typing import Callable, Optional

try:  # imported as part of the qt_analyzer package
    from .models import AnalysisResult
    from .packets import CancelledError  # class CancelledError(Exception), single source of truth
    from .packets import scan as _scan_packets
    from .probe import probe as _probe_file
except ImportError:  # imported standalone with the package dir on sys.path
    from models import AnalysisResult  # type: ignore[no-redef]
    from packets import CancelledError  # type: ignore[no-redef]
    from packets import scan as _scan_packets  # type: ignore[no-redef]
    from probe import probe as _probe_file  # type: ignore[no-redef]

# Re-exported so ``from pipeline import CancelledError`` is always the same
# object that packet scanning raises.
__all__ = ["CancelledError", "run_analysis", "run_range"]


def _is_cancelled(cancel) -> bool:
    try:
        if cancel is None:
            return False
        is_set = getattr(cancel, "is_set", None)
        if callable(is_set):
            return bool(is_set())
        if callable(cancel):
            return bool(cancel())
        return bool(cancel)
    except Exception:
        return False


def _throw_if_cancelled(cancel) -> None:
    if _is_cancelled(cancel):
        raise CancelledError("analysis cancelled")


def _load_deep_fn(module_base: str, attr: str):
    """Import *attr* from sibling module *module_base*; ``None`` if absent."""
    for name in (f"qt_analyzer.{module_base}", module_base):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        fn = getattr(mod, attr, None)
        if callable(fn):
            return fn
    if __package__:
        try:
            mod = importlib.import_module(f".{module_base}", __package__)
        except ImportError:
            return None
        fn = getattr(mod, attr, None)
        return fn if callable(fn) else None
    return None


def _call_deep(fn, result: AnalysisResult, *, from_s: float, to_s: float,
               on_updated=None, cancel=None, progress=None):
    """Call a deep-pass entry point with whatever signature it supports.

    Preferred contract (documented for the ``deep_qp`` / ``motion`` owners)::

        fn(result, from_s=0.0, to_s=-1.0, on_updated=None, cancel=None, progress=None)

    Legacy ``fn(result, from_s, to_s)`` and minimal ``fn(result)`` shapes are
    accepted as fallbacks. Keyword arguments are filtered through
    :func:`inspect.signature` so unsupported ones are never passed.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(result)

    params = sig.parameters
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

    def takes(*names: str) -> Optional[str]:
        for n in names:
            if n in params:
                return n
        return None

    kwargs: dict = {}
    from_key = takes("from_s", "from_seconds", "start", "start_s")
    to_key = takes("to_s", "to_seconds", "end", "end_s")
    if from_key:
        kwargs[from_key] = from_s
    if to_key:
        kwargs[to_key] = to_s
    for key, value in (("on_updated", on_updated), ("cancel", cancel), ("progress", progress)):
        if key in params or has_var_kw:
            kwargs[key] = value

    positional = [p for p in params.values()
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                inspect.Parameter.POSITIONAL_OR_KEYWORD)]

    try:
        if inspect.iscoroutinefunction(fn):
            import asyncio
            if len(positional) >= 3 and not from_key and not to_key:
                extra = {k: v for k, v in kwargs.items()
                         if k not in ("from_s", "from_seconds", "start", "start_s",
                                      "to_s", "to_seconds", "end", "end_s")}
                return asyncio.run(fn(result, from_s, to_s, **extra))
            return asyncio.run(fn(result, **kwargs))
        if len(positional) >= 3 and not from_key and not to_key:
            # Legacy positional-only shape: fn(result, from_s, to_s).
            return fn(result, from_s, to_s)
        return fn(result, **kwargs)
    except TypeError as exc:
        msg = str(exc)
        if not any(s in msg for s in ("argument", "parameter", "takes",
                                      "missing", "unexpected", "positional")):
            raise
        try:
            return fn(result, from_s, to_s)
        except TypeError:
            return fn(result)


def _run_deep(result: AnalysisResult, *, motion: bool,
              from_s: float = 0.0, to_s: float = -1.0,
              on_stage=None, on_updated=None, cancel=None) -> None:
    """Run the deep passes over ``[from_s, to_s)`` (``to_s < 0`` = EOF)."""
    deep_stage = "Analysing QP and motion…" if motion else "Analysing QP…"
    if on_stage is not None:
        on_stage(deep_stage, 0.20)

    frac = {"v": 0.0}

    def _deep_progress(p) -> None:
        try:
            frac["v"] = max(0.0, min(1.0, float(p)))
        except (TypeError, ValueError):
            return
        if on_stage is not None:
            on_stage(deep_stage, 0.20 + frac["v"] * 0.80)

    qp_fn = _load_deep_fn("deep_qp", "run_type_qp")
    motion_fn = _load_deep_fn("motion", "run_motion") if motion else None

    if qp_fn is not None:
        _throw_if_cancelled(cancel)
        _call_deep(qp_fn, result, from_s=from_s, to_s=to_s,
                   on_updated=on_updated, cancel=cancel, progress=_deep_progress)
        result.has_deep = True
    else:
        result.qp_estimated = True

    if motion:
        if motion_fn is not None:
            _throw_if_cancelled(cancel)
            _call_deep(motion_fn, result, from_s=from_s, to_s=to_s,
                       on_updated=on_updated, cancel=cancel, progress=_deep_progress)
            result.has_deep = True
        else:
            result.motion_estimated = True

    _throw_if_cancelled(cancel)


def run_analysis(
    file_path: str,
    motion: bool = True,
    on_stage: Optional[Callable[[str, float], None]] = None,
    on_updated: Optional[Callable[[AnalysisResult], None]] = None,
    cancel=None,
) -> AnalysisResult:
    """Run the full pipeline for *file_path* and return the result.

    *on_stage(stage, fraction)* reports progress; *on_updated(result)* fires
    after the packet pass and after the deep passes. *cancel* is a
    ``threading.Event`` (or compatible); :class:`CancelledError` is raised
    when it is set.
    """
    def _stage(name: str, frac: float) -> None:
        if on_stage is not None:
            on_stage(name, frac)

    _throw_if_cancelled(cancel)
    _stage("Reading container metadata…", 0.0)
    media = _probe_file(file_path)
    _throw_if_cancelled(cancel)

    result = AnalysisResult(media=media)

    _stage("Scanning packet table…", 0.02)

    def _scan_progress(p) -> None:
        try:
            f = max(0.0, min(1.0, float(p)))
        except (TypeError, ValueError):
            return
        _stage("Scanning packet table…", 0.02 + f * 0.18)

    frames = _scan_packets(media.file_path or file_path, media.fps, media.nb_frames,
                           progress=_scan_progress if on_stage is not None else None,
                           cancel=cancel, mark_result=result)
    _throw_if_cancelled(cancel)

    if frames:
        result.frames.extend(frames)
        result.media.nb_frames = len(frames)
        if result.media.duration <= 0:
            result.media.duration = result.duration_seconds
    result.compute_aggregates()
    if on_updated is not None:
        on_updated(result)

    if not frames:
        _stage("Ready", 1.0)
        return result

    _run_deep(result, motion=motion, on_stage=on_stage,
              on_updated=on_updated, cancel=cancel)

    result.compute_aggregates()
    if on_updated is not None:
        on_updated(result)
    _stage("Ready", 1.0)
    return result


def run_range(
    result: AnalysisResult,
    from_s: float,
    to_s: float,
    motion: bool = True,
    on_stage: Optional[Callable[[str, float], None]] = None,
    on_updated: Optional[Callable[[AnalysisResult], None]] = None,
    cancel=None,
) -> AnalysisResult:
    """Re-run only the deep passes over ``[from_s, to_s)`` of *result*.

    The packet table, transport timings and view state are untouched; parsed
    frames are mapped back onto the existing frame table. Returns *result*.
    """
    _throw_if_cancelled(cancel)
    _run_deep(result, motion=motion, from_s=from_s, to_s=to_s,
              on_stage=on_stage, on_updated=on_updated, cancel=cancel)
    result.compute_aggregates()
    if on_updated is not None:
        on_updated(result)
    if on_stage is not None:
        on_stage("Ready", 1.0)
    return result
