"""PCM audio playback through QAudioSink, fed by an ffmpeg pipe.

Mirrors ``AudioPlayer.cs`` from the original WPF app: the picture is decoded
through an ffmpeg pipe rather than by a media engine, so the sound is decoded
the same way -- ffmpeg emits raw 16-bit stereo PCM and a background feeder
thread pushes it to the sound card.

The original used ``waveOut`` with software volume (leaving the system mixer
alone) plus a silence keep-alive so the first Play() would not pay the ~1.5 s
device start-up cost. Here ``QAudioSink`` owns the device and its ``setVolume``
is the software gain; the sink is created in :meth:`start`, so first-play
latency is accepted instead of a keep-alive thread.

Fixed format, like the original: 48 kHz, stereo, signed 16-bit.
A source with no audio track is a silent no-op (no ``failed`` signal).
"""
from __future__ import annotations

import subprocess
import threading
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSink

try:  # package import (`python -m qt_analyzer...`) vs bare-script import
    from .ffmpeg_locator import ffmpeg_path, ffprobe_path
except ImportError:  # pragma: no cover
    from ffmpeg_locator import ffmpeg_path, ffprobe_path  # type: ignore[no-redef]

SAMPLE_RATE = 48000
CHANNELS = 2
_CHUNK_FRAMES = 4096          # ~85 ms of audio per write, mirrors waveOut slots
_CHUNK_BYTES = _CHUNK_FRAMES * CHANNELS * 2

__all__ = ["AudioPlayer"]


class AudioPlayer(QObject):
    """Plays the file's audio track from ``start_s`` seconds."""

    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gate = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._feeder: threading.Thread | None = None
        self._stop = threading.Event()
        self._sink: QAudioSink | None = None
        self._dev = None
        self._volume = 0.8
        self._muted = False
        self._has_audio = False

    @property
    def has_audio(self) -> bool:
        return self._has_audio

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def is_playing(self) -> bool:
        t = self._feeder
        return t is not None and t.is_alive()

    def _probe_says_no_audio(self, file: str) -> bool:
        """True only when ffprobe confidently reports no audio stream."""
        try:
            exe = ffprobe_path()
        except Exception:
            return False
        if not exe:
            return False
        try:
            out = subprocess.run(
                [exe, "-v", "error", "-select_streams", "a:0",
                 "-show_entries", "stream=index", "-of", "csv=p=0",
                 str(file)],
                capture_output=True, text=True, timeout=15)
        except Exception:
            return False
        return out.returncode == 0 and not out.stdout.strip()

    def start(self, file: str, start_s: float) -> None:
        self.stop()

        exe = ffmpeg_path()
        if not exe:
            self.failed.emit("ffmpeg was not found.")
            return

        if self._probe_says_no_audio(str(file)):
            self._has_audio = False
            return  # silent no-op: source has no audio track

        fmt = QAudioFormat()
        fmt.setSampleRate(SAMPLE_RATE)
        fmt.setChannelCount(CHANNELS)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        try:
            sink = QAudioSink(fmt)
        except Exception as ex:
            self.failed.emit(f"could not open audio device: {ex}")
            return
        try:
            sink.setVolume(0.0 if self._muted else self._volume)
        except Exception:
            pass
        try:
            dev = sink.start()
        except Exception as ex:
            self.failed.emit(f"could not start audio output: {ex}")
            try:
                sink.stop()
            except Exception:
                pass
            return
        if dev is None:
            self.failed.emit("could not start audio output.")
            try:
                sink.stop()
            except Exception:
                pass
            return

        args = [
            exe, "-v", "error", "-hide_banner",
            "-ss", f"{max(0.0, float(start_s)):.3f}",
            "-i", str(file), "-vn",
            "-f", "s16le", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
            "-acodec", "pcm_s16le", "pipe:1",
        ]
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as ex:
            self.failed.emit(f"could not start ffmpeg: {ex}")
            try:
                sink.stop()
            except Exception:
                pass
            return

        self._stop.clear()
        with self._gate:
            self._proc = proc
            self._sink = sink
            self._dev = dev
            self._has_audio = True  # tentative; cleared if ffmpeg emits nothing
            self._feeder = threading.Thread(
                target=self._feed_loop, args=(proc, dev),
                daemon=True, name="audio-feed")
            self._feeder.start()

    def _feed_loop(self, proc: subprocess.Popen, dev) -> None:
        assert proc.stdout is not None
        stream = proc.stdout
        delivered = 0
        try:
            while not self._stop.is_set():
                try:
                    chunk = stream.read(_CHUNK_BYTES)
                except Exception:
                    break
                if not chunk:
                    break
                if len(chunk) % (CHANNELS * 2) != 0:
                    chunk = chunk[:len(chunk) - len(chunk) % (CHANNELS * 2)]
                if not chunk:
                    continue
                delivered += len(chunk)
                off = 0
                retries = 0
                while off < len(chunk) and not self._stop.is_set():
                    try:
                        n = dev.write(chunk[off:])
                    except Exception:
                        off = -1
                        break
                    if n is None or n < 0:
                        off = -1
                        break
                    if n == 0:
                        retries += 1
                        if retries > 500:
                            off = -1
                            break
                        time.sleep(0.004)
                        continue
                    off += n
                    retries = 0
                if off == -1:
                    break
            if delivered == 0 and not self._stop.is_set():
                # ffmpeg emitted nothing: the source almost certainly has no
                # audio track (its error went to stderr). Stay silent, like
                # the original Load(path, hasAudio: false) path.
                self._has_audio = False
        except Exception as ex:
            if not self._stop.is_set():
                try:
                    self.failed.emit(str(ex))
                except Exception:
                    pass

    def set_volume(self, value: float) -> None:
        self._volume = min(1.0, max(0.0, float(value)))
        if not self._muted and self._sink is not None:
            try:
                self._sink.setVolume(self._volume)
            except Exception:
                pass

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._sink is not None:
            try:
                self._sink.setVolume(0.0 if self._muted else self._volume)
            except Exception:
                pass

    def stop(self) -> None:
        with self._gate:
            proc = self._proc
            feeder = self._feeder
            sink = self._sink
            self._proc = None
            self._feeder = None
            self._sink = None
            self._dev = None
        self._stop.set()
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        me = threading.current_thread()
        if feeder is not None and feeder.is_alive() and feeder is not me:
            try:
                feeder.join(timeout=1.5)
            except Exception:
                pass
        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass
        if proc is not None:
            try:
                if proc.stdout is not None:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass

    def close(self) -> None:
        self.stop()
