from __future__ import annotations

import importlib.util
import logging
import platform
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from llmvoice import __version__
from llmvoice.audio.ffmpeg import require_ffmpeg
from llmvoice.core.exceptions import AudioToolError
from llmvoice.core.paths import AppPaths
from llmvoice.voices.manager import SUPPORTED_AUDIO_EXTENSIONS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: str
    detail: str
    hint: str | None = None


def run_diagnostics(paths: AppPaths) -> list[DiagnosticCheck]:
    """Inspect local dependencies without loading or downloading a TTS model."""
    checks = [
        DiagnosticCheck("LLMVoice", "ok", __version__),
        DiagnosticCheck("Python", "ok", platform.python_version()),
    ]
    try:
        require_ffmpeg()
        checks.extend(
            [
                DiagnosticCheck("FFmpeg", "ok", "Found"),
                DiagnosticCheck("FFprobe", "ok", "Found"),
            ]
        )
    except AudioToolError:
        checks.extend(
            [
                DiagnosticCheck(
                    "FFmpeg",
                    "error",
                    "Not found",
                    "Install: winget install --id Gyan.FFmpeg.Shared",
                ),
                DiagnosticCheck("FFprobe", "error", "Not found"),
            ]
        )

    torch_spec = importlib.util.find_spec("torch")
    if torch_spec is None:
        checks.extend(
            [
                DiagnosticCheck("PyTorch", "error", "Not installed"),
                DiagnosticCheck(
                    "CUDA",
                    "warning",
                    "Not available",
                    "LLMVoice can use CPU after PyTorch is installed, but it will be slower.",
                ),
            ]
        )
    else:
        try:
            import torch

            checks.append(DiagnosticCheck("PyTorch", "ok", torch.__version__))
            if torch.cuda.is_available():
                checks.extend(
                    [
                        DiagnosticCheck("CUDA", "ok", "Available"),
                        DiagnosticCheck("GPU", "ok", torch.cuda.get_device_name(0)),
                    ]
                )
            else:
                checks.append(
                    DiagnosticCheck(
                        "CUDA",
                        "warning",
                        "Not available",
                        "LLMVoice can still use CPU, but generation will be slower.",
                    )
                )
        except Exception:
            logger.debug("PyTorch import failed during diagnostics", exc_info=True)
            checks.extend(
                [
                    DiagnosticCheck("PyTorch", "error", "Installed but could not be loaded"),
                    DiagnosticCheck("CUDA", "warning", "Could not be checked"),
                ]
            )

    try:
        xtts_version = version("coqui-tts")
        checks.append(DiagnosticCheck("XTTS", "ok", f"coqui-tts {xtts_version}"))
    except PackageNotFoundError:
        checks.append(DiagnosticCheck("XTTS", "error", "Not installed"))

    try:
        paths.ensure()
        voice_count = sum(
            1
            for path in paths.voices_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in SUPPORTED_AUDIO_EXTENSIONS
        )
        checks.extend(
            [
                DiagnosticCheck("Data directory", "ok", str(paths.root)),
                DiagnosticCheck("Voices", "ok", f"{voice_count} stored"),
            ]
        )
    except OSError:
        logger.debug("Data directory check failed for %s", paths.root, exc_info=True)
        checks.extend(
            [
                DiagnosticCheck("Data directory", "error", f"Not writable: {paths.root}"),
                DiagnosticCheck("Voices", "warning", "Could not be checked"),
            ]
        )
    return checks
