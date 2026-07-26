from __future__ import annotations

import shutil
from pathlib import Path

from llmvoice.core.exceptions import DiskSpaceError

MIN_DISK_RESERVE_BYTES = 256 * 1024 * 1024
PCM_BYTES_PER_SECOND = 48_000
TEMPORARY_AUDIO_COPIES = 3


def estimate_speech_seconds(text: str, words_per_minute: int = 150) -> float:
    """Estimate spoken duration using a transparent word-rate heuristic."""
    words = len(text.split())
    return max(1.0, words / words_per_minute * 60.0)


def required_disk_bytes(estimated_seconds: float) -> int:
    """Estimate conservative temporary storage plus a safety reserve."""
    audio_bytes = estimated_seconds * PCM_BYTES_PER_SECOND * TEMPORARY_AUDIO_COPIES
    return int(MIN_DISK_RESERVE_BYTES + audio_bytes)


def check_disk_space(output_path: Path, estimated_seconds: float) -> tuple[int, int]:
    """Raise when the output drive cannot safely hold temporary audio."""
    existing_parent = output_path.parent
    while not existing_parent.exists() and existing_parent != existing_parent.parent:
        existing_parent = existing_parent.parent
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
