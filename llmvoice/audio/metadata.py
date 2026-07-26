from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from llmvoice.audio.ffmpeg import require_ffmpeg
from llmvoice.core.exceptions import AudioToolError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioMetadata:
    """Metadata for the first readable audio stream in a media file."""

    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str
    format_name: str

    @property
    def channel_label(self) -> str:
        if self.channels == 1:
            return "Mono"
        if self.channels == 2:
            return "Stereo"
        return f"{self.channels} channels"


def probe_audio(path: Path) -> AudioMetadata:
    """Inspect an audio file with FFprobe and return normalized metadata."""
    _, ffprobe = require_ffmpeg()
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels,duration:"
                "format=duration,format_name",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except OSError as exc:
        raise AudioToolError(f"Could not inspect audio file:\n{path}") from exc
    if result.returncode != 0:
        logger.debug("FFprobe stderr for %s:\n%s", path, result.stderr)
        raise _unreadable_audio(path)
    try:
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []
        stream = streams[0]
        container = payload.get("format") or {}
        duration_raw = container.get("duration") or stream.get("duration")
        duration = float(duration_raw)
        sample_rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
        codec = str(stream["codec_name"])
        format_name = str(container.get("format_name") or path.suffix.lstrip("."))
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.debug("Unexpected FFprobe output for %s: %s", path, result.stdout)
        raise _unreadable_audio(path) from exc
    if duration <= 0 or sample_rate <= 0 or channels <= 0:
        raise _unreadable_audio(path)
    return AudioMetadata(
        duration_seconds=duration,
        sample_rate=sample_rate,
        channels=channels,
        codec=codec,
        format_name=format_name,
    )


def _unreadable_audio(path: Path) -> AudioToolError:
    return AudioToolError(
        "The selected file does not contain a readable audio stream.\n\n"
        f"File:\n{path}"
    )
