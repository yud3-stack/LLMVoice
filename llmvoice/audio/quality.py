from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from llmvoice.audio.ffmpeg import require_ffmpeg
from llmvoice.audio.metadata import probe_audio
from llmvoice.core.exceptions import AudioToolError

_MEAN_VOLUME = re.compile(r"mean_volume:\s*(-?inf|[-+]?\d+(?:\.\d+)?) dB")
_MAX_VOLUME = re.compile(r"max_volume:\s*(-?inf|[-+]?\d+(?:\.\d+)?) dB")
_SILENCE_START = re.compile(r"silence_start:\s*(\d+(?:\.\d+)?)")
_SILENCE_END = re.compile(r"silence_end:\s*(\d+(?:\.\d+)?)")
MIN_USABLE_REFERENCE_SCORE = 60


@dataclass(frozen=True)
class AudioQualityReport:
    duration_seconds: float
    sample_rate: int
    channels: int
    mean_volume_db: float | None
    max_volume_db: float | None
    clipping_risk: bool
    quality: str
    recommendations: list[str]
    silence_ratio: float = 0.0
    score: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _parse_db(pattern: re.Pattern[str], output: str) -> float | None:
    match = pattern.search(output)
    if not match or match.group(1) == "-inf":
        return None
    return float(match.group(1))


def _silence_ratio(output: str, duration: float) -> float:
    if duration <= 0:
        return 0.0
    starts = [float(value) for value in _SILENCE_START.findall(output)]
    ends = [float(value) for value in _SILENCE_END.findall(output)]
    silent_seconds = sum(max(0.0, end - start) for start, end in zip(starts, ends))
    if len(starts) > len(ends):
        silent_seconds += max(0.0, duration - starts[-1])
    return min(1.0, silent_seconds / duration)


def inspect_audio(path: Path) -> AudioQualityReport:
    """Inspect levels and format without modifying the source audio."""
    metadata = probe_audio(path)
    ffmpeg, _ = require_ffmpeg()
    try:
        result = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
                "-af", "volumedetect,silencedetect=noise=-45dB:d=0.1",
                "-f", "null", os.devnull,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except OSError as exc:
        raise AudioToolError(f"Could not inspect audio quality:\n{path}") from exc
    if result.returncode != 0:
        raise AudioToolError(f"Could not inspect audio quality:\n{path}")

    diagnostics = result.stderr
    mean_volume = _parse_db(_MEAN_VOLUME, diagnostics)
    max_volume = _parse_db(_MAX_VOLUME, diagnostics)
    clipping = max_volume is not None and max_volume >= -0.1
    silence_ratio = _silence_ratio(diagnostics, metadata.duration_seconds)
    recommendations: list[str] = []
    if metadata.duration_seconds < 6:
        recommendations.append("Use a reference of at least 6 seconds.")
    elif metadata.duration_seconds > 15:
        recommendations.append("A 6-15 second reference is preferred for stable conditioning.")
    if metadata.channels != 1:
        recommendations.append("Mono reference audio is preferred.")
    if clipping:
        recommendations.append("Recording appears clipped; record again at a lower input level.")
    if mean_volume is not None and mean_volume < -35:
        recommendations.append("Recording level is low; move the microphone closer.")
    if silence_ratio > 0.35:
        recommendations.append("Recording contains a high amount of silence; trim empty sections.")

    score = 100
    if metadata.duration_seconds < 6:
        score -= 25
    elif metadata.duration_seconds > 15:
        score -= 10
    if metadata.channels != 1:
        score -= 15
    if clipping:
        score -= 35
    if mean_volume is None:
        score -= 20
    elif mean_volume < -35:
        score -= 15
    elif mean_volume > -8:
        score -= 10
    if silence_ratio > 0.35:
        score -= 20
    elif silence_ratio > 0.20:
        score -= 10
    score = max(0, min(100, score))
    quality = "good" if score >= 80 else "review" if score >= 60 else "poor"
    return AudioQualityReport(
        duration_seconds=metadata.duration_seconds,
        sample_rate=metadata.sample_rate,
        channels=metadata.channels,
        mean_volume_db=mean_volume,
        max_volume_db=max_volume,
        clipping_risk=clipping,
        quality=quality,
        recommendations=recommendations,
        silence_ratio=silence_ratio,
        score=score,
    )
