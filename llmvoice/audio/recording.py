from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from llmvoice.audio.ffmpeg import require_ffmpeg
from llmvoice.core.exceptions import AudioToolError

_AUDIO_DEVICE = re.compile(r'\s*"([^"]+)"\s+\(audio\)')


def list_audio_devices() -> list[str]:
    """Return Windows DirectShow audio input names known by FFmpeg."""
    ffmpeg, _ = require_ffmpeg()
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except OSError as exc:
        raise AudioToolError("Could not list Windows audio devices.") from exc
    return list(dict.fromkeys(_AUDIO_DEVICE.findall(result.stderr)))


def record_audio(destination: Path, duration_seconds: float, device: str | None = None) -> None:
    """Record a mono 24 kHz PCM WAV from a Windows DirectShow microphone."""
    if duration_seconds <= 0 or duration_seconds > 3600:
        raise AudioToolError("Recording duration must be between 0 and 3600 seconds.")
    devices = list_audio_devices()
    selected = device or (devices[0] if devices else None)
    if selected is None:
        raise AudioToolError(
            "No Windows audio input was found. Check the microphone and run "
            "'llmvoice audio devices'."
        )
    ffmpeg, _ = require_ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}.llmvoice-",
        suffix=".wav",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    try:
        result = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "dshow", "-i", f"audio={selected}",
                "-t", f"{duration_seconds:.3f}", "-ac", "1", "-ar", "24000",
                "-c:a", "pcm_s16le", str(temporary),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
            raise AudioToolError(f"Microphone recording failed: {detail}")
        temporary.replace(destination)
    except OSError as exc:
        raise AudioToolError("Could not start microphone recording.") from exc
    finally:
        temporary.unlink(missing_ok=True)
