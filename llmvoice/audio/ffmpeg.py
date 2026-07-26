from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from llmvoice.core.exceptions import AudioToolError

_DLL_DIRECTORY_HANDLES: list[object] = []
_REGISTERED_DLL_DIRECTORIES: set[Path] = set()


def _winget_shared_ffmpeg_dirs() -> list[Path]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []
    packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not packages.is_dir():
        return []
    matches: list[Path] = []
    for package in packages.glob("Gyan.FFmpeg.Shared_*"):
        matches.extend(path for path in package.glob("**/bin") if path.is_dir())
    return sorted(matches, reverse=True)


def _register_dll_directory(directory: Path) -> None:
    resolved = directory.resolve()
    if resolved in _REGISTERED_DLL_DIRECTORIES:
        return
    os.environ["PATH"] = f"{resolved}{os.pathsep}{os.environ.get('PATH', '')}"
    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(resolved)))
    _REGISTERED_DLL_DIRECTORIES.add(resolved)


def _discover_shared_ffmpeg() -> tuple[str, str] | None:
    candidates: list[Path] = []
    current = shutil.which("ffmpeg")
    if current:
        candidates.append(Path(current).resolve().parent)
    candidates.extend(_winget_shared_ffmpeg_dirs())
    for directory in candidates:
        ffmpeg = directory / "ffmpeg.exe"
        ffprobe = directory / "ffprobe.exe"
        if ffmpeg.is_file() and ffprobe.is_file() and any(directory.glob("avcodec-*.dll")):
            _register_dll_directory(directory)
            return str(ffmpeg), str(ffprobe)
    return None


def require_ffmpeg() -> tuple[str, str]:
    shared = _discover_shared_ffmpeg()
    if shared:
        return shared
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise AudioToolError(
            "FFmpeg and FFprobe were not found in PATH. Install FFmpeg, reopen the terminal, "
            "and verify with: ffmpeg -version"
        )
    return ffmpeg, ffprobe


def run_tool(arguments: list[str], purpose: str) -> None:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except OSError as exc:
        raise AudioToolError(f"Could not start FFmpeg while {purpose}.") from exc
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        message = detail[-1] if detail else "Unknown FFmpeg error"
        raise AudioToolError(f"FFmpeg failed while {purpose}: {message}")


def probe_audio(path: Path) -> None:
    _, ffprobe = require_ffmpeg()
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,sample_rate,channels",
                "-of", "default=noprint_wrappers=1", str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except OSError as exc:
        raise AudioToolError(f"Could not inspect reference audio: {path}") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise AudioToolError(f"Reference file does not contain a readable audio stream: {path}")
