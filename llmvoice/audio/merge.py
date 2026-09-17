from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from llmvoice.audio.ffmpeg import require_ffmpeg, run_tool


# Keep generated files at a consistent listening level while leaving headroom
# for peaks.  This is applied after all chunks have been merged.
OUTPUT_LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def _concat_line(path: Path) -> str:
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def _create_pause(destination: Path, pause_ms: int) -> Path:
    ffmpeg, _ = require_ffmpeg()
    pause = destination.parent / f"chunk-pause-{pause_ms}.wav"
    run_tool(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            f"{pause_ms / 1000:.3f}",
            "-c:a",
            "pcm_s16le",
            pause.resolve().as_posix(),
        ],
        "creating the inter-chunk pause",
    )
    return pause


def pause_after_text(text: str, base_ms: int) -> int:
    """Choose a natural pause from the punctuation ending a generated chunk."""
    if base_ms <= 0:
        return 0
    ending = text.rstrip()[-1:] if text.strip() else ""
    if ending in ".!?…":
        return round(base_ms * 1.25)
    if ending in ",;:":
        return round(base_ms * 0.75)
    return round(base_ms * 0.5)


def merge_wav_files(
    chunks: list[Path],
    destination: Path,
    pause_ms: int | list[int] = 0,
    crossfade_ms: int = 0,
) -> None:
    """Merge WAV chunks with optional punctuation pauses and crossfades."""
    if not chunks:
        raise ValueError("At least one audio chunk is required.")
    if len(chunks) == 1 and pause_ms in (0, []):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(chunks[0], destination)
        return
    ffmpeg, _ = require_ffmpeg()
    if isinstance(pause_ms, int):
        pauses = [pause_ms] * (len(chunks) - 1)
    else:
        pauses = list(pause_ms)
        if len(pauses) != len(chunks) - 1:
            raise ValueError("pause_ms must contain one value per chunk boundary.")
    crossfade_ms = max(0, crossfade_ms)
    inputs: list[Path] = []
    for index, chunk in enumerate(chunks):
        inputs.append(chunk)
        if index < len(chunks) - 1 and pauses[index] > 0:
            pause_length = pauses[index] + (4 * crossfade_ms if crossfade_ms else 0)
            inputs.append(_create_pause(destination, pause_length))
    if len(inputs) < 2:
        crossfade_ms = 0

    if crossfade_ms <= 0:
        manifest = destination.parent / "concat.txt"
        manifest.write_text(
            "\n".join(_concat_line(path) for path in inputs) + "\n",
            encoding="utf-8",
        )
        arguments = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", manifest.resolve().as_posix(),
            "-vn", "-c:a", "pcm_s16le", destination.resolve().as_posix(),
        ]
    else:
        arguments = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        for input_path in inputs:
            arguments.extend(["-i", input_path.resolve().as_posix()])
        duration = f"{crossfade_ms / 1000:.3f}"
        labels = [f"{index}:a" for index in range(len(inputs))]
        filters = []
        current = f"[{labels[0]}][{labels[1]}]"
        filters.append(f"{current}acrossfade=d={duration}:c1=tri:c2=tri[x0]")
        for index in range(2, len(labels)):
            filters.append(f"[x{index - 2}][{labels[index]}]acrossfade=d={duration}:c1=tri:c2=tri[x{index - 1}]")
        final_label = f"x{len(labels) - 2}"
        arguments.extend(
            ["-filter_complex", ";".join(filters), "-map", f"[{final_label}]", "-c:a", "pcm_s16le", destination.resolve().as_posix()]
        )
    run_tool(arguments, "merging audio chunks")


def _encode_audio(
    source: Path,
    destination: Path,
    speed: float,
    codec: str,
    temporary_suffix: str,
    purpose: str,
) -> None:
    ffmpeg, _ = require_ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}.llmvoice-",
        suffix=temporary_suffix,
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    temporary.unlink(missing_ok=True)
    arguments = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", source.resolve().as_posix(),
        "-vn",
    ]
    filters = [OUTPUT_LOUDNORM]
    if abs(speed - 1.0) > 0.001:
        filters.insert(0, f"atempo={speed:.4f}")
    arguments.extend(["-filter:a", ",".join(filters)])
    arguments.extend(["-c:a", codec])
    if codec == "libmp3lame":
        arguments.extend(["-q:a", "2"])
    arguments.append(temporary.resolve().as_posix())
    try:
        run_tool(arguments, purpose)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def encode_mp3(source: Path, destination: Path, speed: float) -> None:
    _encode_audio(source, destination, speed, "libmp3lame", ".mp3", "encoding MP3")


def encode_wav(source: Path, destination: Path, speed: float) -> None:
    _encode_audio(source, destination, speed, "pcm_s16le", ".wav", "encoding WAV")


def encode_audio(source: Path, destination: Path, speed: float) -> None:
    if destination.suffix.casefold() == ".mp3":
        encode_mp3(source, destination, speed)
    elif destination.suffix.casefold() == ".wav":
        encode_wav(source, destination, speed)
    else:
        raise ValueError("Output format must be .mp3 or .wav.")
