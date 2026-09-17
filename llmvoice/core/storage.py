from __future__ import annotations

import os
import shutil
from pathlib import Path

from llmvoice.core.exceptions import DiskSpaceError

CACHE_DISK_RESERVE_BYTES = 256 * 1024 * 1024
OUTPUT_DISK_RESERVE_BYTES = 64 * 1024 * 1024
# Backward-compatible name used by earlier callers and tests.
MIN_DISK_RESERVE_BYTES = CACHE_DISK_RESERVE_BYTES
PCM_BYTES_PER_SECOND = 48_000
TEMPORARY_AUDIO_COPIES = 3
MP3_BYTES_PER_SECOND = 32_000
WAV_BYTES_PER_SECOND = 48_000


def estimate_speech_seconds(text: str, words_per_minute: int = 150) -> float:
    """Estimate spoken duration using a transparent word-rate heuristic."""
    words = len(text.split())
    return max(1.0, words / words_per_minute * 60.0)


def required_disk_bytes(estimated_seconds: float) -> int:
    """Estimate conservative temporary storage plus a safety reserve."""
    audio_bytes = estimated_seconds * PCM_BYTES_PER_SECOND * TEMPORARY_AUDIO_COPIES
    return int(CACHE_DISK_RESERVE_BYTES + audio_bytes)


def required_output_bytes(estimated_seconds: float, output_path: Path | None = None) -> int:
    """Estimate free space needed for the atomically encoded output."""
    bytes_per_second = (
        WAV_BYTES_PER_SECOND
        if output_path is not None and output_path.suffix.casefold() == ".wav"
        else MP3_BYTES_PER_SECOND
    )
    return int(OUTPUT_DISK_RESERVE_BYTES + estimated_seconds * bytes_per_second)


def _nearest_existing_path(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _volume_key(path: Path) -> str | int:
    """Return a stable volume identifier without requiring the target to exist."""
    existing = _nearest_existing_path(path)
    if os.name == "nt":
        return existing.resolve().anchor.casefold()
    return os.stat(existing).st_dev


def _raise_space_error(
    purpose: str,
    location: Path,
    available: int,
    required: int,
    *,
    hint: str | None = None,
) -> None:
    message = (
        f"Not enough free disk space for {purpose}.\n\n"
        f"Location : {location}\n"
        f"Available: {format_bytes(available)}\n"
        f"Required : approximately {format_bytes(required)}"
    )
    if hint:
        message += f"\n\n{hint}"
    raise DiskSpaceError(message)


def check_synthesis_disk_space(
    cache_dir: Path,
    output_path: Path,
    estimated_seconds: float,
) -> tuple[int, int]:
    """Validate cache and output volumes before long-form synthesis starts."""
    cache_location = _nearest_existing_path(cache_dir)
    output_location = _nearest_existing_path(output_path.parent)
    cache_required = required_disk_bytes(estimated_seconds)
    output_required = required_output_bytes(estimated_seconds, output_path)

    if _volume_key(cache_location) == _volume_key(output_location):
        available = shutil.disk_usage(cache_location).free
        combined_required = cache_required + output_required
        if available < combined_required:
            _raise_space_error(
                "temporary audio and output",
                cache_dir,
                available,
                combined_required,
                hint="Free some disk space or change LLMVOICE_DATA_DIR.",
            )
        return available, combined_required

    cache_available = shutil.disk_usage(cache_location).free
    if cache_available < cache_required:
        _raise_space_error(
            "temporary audio",
            cache_dir,
            cache_available,
            cache_required,
            hint="Free some disk space or change LLMVOICE_DATA_DIR.",
        )

    output_available = shutil.disk_usage(output_location).free
    if output_available < output_required:
        _raise_space_error(
            "output",
            output_path.parent,
            output_available,
            output_required,
        )
    return min(cache_available, output_available), cache_required + output_required


def check_disk_space(output_path: Path, estimated_seconds: float) -> tuple[int, int]:
    """Backward-compatible check retained for callers from v0.1.0."""
    existing_parent = _nearest_existing_path(output_path.parent)
    available = shutil.disk_usage(existing_parent).free
    required = required_disk_bytes(estimated_seconds)
    if available < required:
        raise DiskSpaceError(
            "Not enough free disk space.\n\n"
            f"Available: {format_bytes(available)}\n"
            f"Required : approximately {format_bytes(required)}"
        )
    return available, required


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            decimals = 0 if unit in {"B", "KB", "MB"} else 1
            return f"{value:.{decimals}f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
