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
    "areverse,atrim=duration=15"
)
REFERENCE_LOUDNORM = "loudnorm=I=-20:TP=-1.5:LRA=11"
REFERENCE_PROCESSING_VERSION = "3"
REFERENCE_MAX_SECONDS = 15.0


def _cache_key(source: Path, denoise_model: Path | None = None) -> str:
    stat = source.stat()
    denoise_identity = ""
    if denoise_model is not None:
        model_stat = denoise_model.stat()
        denoise_identity = (
            f"{denoise_model.resolve()}:{model_stat.st_size}:{model_stat.st_mtime_ns}"
        )
    value = (
        f"{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:"
        f"{REFERENCE_PROCESSING_VERSION}:{denoise_identity}"
    ).encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:24]


def prepare_reference(
    source: Path,
    cache_dir: Path,
    denoise_model: Path | None = None,
) -> Path:
    """Validate and create a trimmed mono 24 kHz WAV without modifying source."""
    probe_audio(source)
    destination_dir = cache_dir / "references"
    destination_dir.mkdir(parents=True, exist_ok=True)
    if denoise_model is not None and not denoise_model.is_file():
        raise AudioToolError(f"RNNoise model not found: {denoise_model}")
    destination = destination_dir / f"{_cache_key(source, denoise_model)}.wav"
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
    filter_chain = ENDPOINT_TRIM_FILTER
    if denoise_model is not None:
        model = str(denoise_model.resolve()).replace("\\", "/").replace(":", r"\:")
        filter_chain += f",arnndn=model='{model}'"
    # Stable reference loudness makes speaker conditioning less sensitive to
    # the recording device and input gain.
    filter_chain += f",{REFERENCE_LOUDNORM}"
    try:
        run_tool(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                "-map", "0:a:0", "-ac", "1", "-ar", "24000",
                 "-af", filter_chain,
                "-c:a", "pcm_s16le", str(temporary),
            ],
            "preparing the voice reference",
        )
        probe_audio(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
