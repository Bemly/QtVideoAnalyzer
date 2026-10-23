"""Locate ffmpeg / ffprobe. Mirrors FfmpegLocator.cs search order."""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

_ffmpeg: str | None = None
_ffprobe: str | None = None
version_text: str = "not found"


def _candidates(base: str) -> list[str]:
    return [base, base + ".exe"]


def find_tool(unix_name: str) -> str | None:
    home = os.environ.get("FFMPEG_HOME", "").strip()
    if home:
        for c in (Path(home) / unix_name, Path(home) / "bin" / unix_name,
                  Path(home) / (unix_name + ".exe"), Path(home) / "bin" / (unix_name + ".exe")):
            if c.is_file():
                return str(c)
    here = Path(__file__).resolve()
    for parent in [here.parent, here.parent.parent] + list(here.parents[:6]):
        for c in (parent / "tools" / "ffmpeg" / "bin" / unix_name,
                  parent / "tools" / unix_name,
                  parent / unix_name):
            if c.is_file():
                return str(c)
    w = shutil.which(unix_name) or shutil.which(unix_name + ".exe")
    if w:
        return w
    for c in (Path("/opt/homebrew/bin") / unix_name, Path("/usr/local/bin") / unix_name,
              Path(r"C:\ffmpeg\bin") / (unix_name + ".exe")):
        if c.is_file():
            return str(c)
    return None


def ffmpeg_path() -> str | None:
    global _ffmpeg
    if _ffmpeg is None:
        _ffmpeg = find_tool("ffmpeg")
    return _ffmpeg


def ffprobe_path() -> str | None:
    global _ffprobe
    if _ffprobe is None:
        _ffprobe = find_tool("ffprobe")
    return _ffprobe


def refresh_version() -> str:
    global version_text
    exe = ffmpeg_path()
    if not exe:
        version_text = "not found"
        return version_text
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=10)
        version_text = (out.stdout.splitlines() or ["unknown"])[0].strip()
    except Exception:
        version_text = "unknown"
    return version_text
