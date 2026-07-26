from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from llmvoice.audio.ffmpeg import require_ffmpeg, run_tool
from llmvoice.audio.metadata import probe_audio
from llmvoice.core.exceptions import AudioToolError

ENDPOINT_TRIM_FILTER = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,"
    "areverse"
)
REFERENCE_PROCESSING_VERSION = "2"


def _cache_key(source: Path) -> str:
    stat = source.stat()
    value = (
        f"{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:"
        f"{REFERENCE_PROCESSING_VERSION}"
    ).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:24]


def prepare_reference(source: Path, cache_dir: Path) -> Path:
    """Validate and create a trimmed mono 24 kHz WAV without modifying source."""
    probe_audio(source)
    destination_dir = cache_dir / "references"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{_cache_key(source)}.wav"
    if destination.exists():
        try:
            probe_audio(destination)
            return destination
        except AudioToolError:
            destination.unlink(missing_ok=True)
    ffmpeg, _ = require_ffmpeg()
    handle = tempfile.NamedTemporaryFile(
        prefix=".reference-",
        suffix=".wav",
        dir=destination_dir,
        delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    temporary.unlink(missing_ok=True)
    try:
        run_tool(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                "-map", "0:a:0", "-ac", "1", "-ar", "24000",
                "-af", ENDPOINT_TRIM_FILTER,
                "-c:a", "pcm_s16le", str(temporary),
            ],
            "preparing the voice reference",
        )
        probe_audio(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
