from __future__ import annotations

import tempfile
from pathlib import Path

from llmvoice.audio.ffmpeg import require_ffmpeg, run_tool


def _concat_line(path: Path) -> str:
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def merge_wav_files(chunks: list[Path], destination: Path) -> None:
    if not chunks:
        raise ValueError("At least one audio chunk is required.")
    ffmpeg, _ = require_ffmpeg()
    manifest = destination.parent / "concat.txt"
    manifest.write_text("\n".join(_concat_line(path) for path in chunks) + "\n", encoding="utf-8")
    run_tool(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(manifest),
            "-vn", "-c:a", "pcm_s16le", str(destination),
        ],
        "merging audio chunks",
    )


def encode_mp3(source: Path, destination: Path, speed: float) -> None:
    ffmpeg, _ = require_ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}.llmvoice-",
        suffix=".mp3",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    temporary.unlink(missing_ok=True)
    arguments = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vn",
    ]
    if abs(speed - 1.0) > 0.001:
        arguments.extend(["-filter:a", f"atempo={speed:.4f}"])
    arguments.extend(["-c:a", "libmp3lame", "-q:a", "2", str(temporary)])
    try:
        run_tool(arguments, "encoding MP3")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
