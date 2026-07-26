from __future__ import annotations

import re
import shutil
from pathlib import Path

from llmvoice.core.exceptions import VoiceError
from llmvoice.core.paths import AppPaths

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
_VOICE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class VoiceManager:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.paths.ensure()

    def add(self, name: str, source: Path) -> Path:
        self._validate_name(name)
        source = source.expanduser().resolve()
        if not source.is_file():
            raise VoiceError(f"Voice file not found: {source}")
        if source.suffix.casefold() not in SUPPORTED_AUDIO_EXTENSIONS:
            raise VoiceError(
                "Unsupported voice format. Supported: "
                + ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
            )
        existing = self._matches(name)
        if existing:
            raise VoiceError(f"Voice '{name}' already exists. Remove it before replacing it.")
        destination = self.paths.voices_dir / f"{name}{source.suffix.casefold()}"
        try:
            shutil.copy2(source, destination)
        except OSError as exc:
            raise VoiceError(f"Could not store voice '{name}'.") from exc
        return destination

    def list(self) -> list[str]:
        names = {
            path.stem
            for path in self.paths.voices_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in SUPPORTED_AUDIO_EXTENSIONS
        }
        return sorted(names, key=str.casefold)

    def remove(self, name: str) -> None:
        matches = self._matches(name)
        if not matches:
            raise self.not_found(name)
        for path in matches:
            path.unlink()

    def resolve(self, value: str) -> Path:
        candidate = Path(value).expanduser()
        looks_like_path = candidate.is_absolute() or candidate.parent != Path(".")
        if candidate.is_file():
            resolved = candidate.resolve()
            if resolved.suffix.casefold() not in SUPPORTED_AUDIO_EXTENSIONS:
                raise VoiceError(f"Unsupported voice format: {resolved.suffix}")
            return resolved
        if looks_like_path:
            raise VoiceError(f"Voice file not found: {candidate}")
        self._validate_name(value)
        matches = self._matches(value)
        if not matches:
            raise self.not_found(value)
        if len(matches) > 1:
            raise VoiceError(f"Voice '{value}' is ambiguous in the voice directory.")
        return matches[0]

    def _matches(self, name: str) -> list[Path]:
        return [
            path for path in self.paths.voices_dir.glob(f"{name}.*")
            if path.is_file() and path.suffix.casefold() in SUPPORTED_AUDIO_EXTENSIONS
        ]

    @staticmethod
    def _validate_name(name: str) -> None:
        if not _VOICE_NAME.fullmatch(name):
            raise VoiceError(
                "Voice name must be 1-64 characters using letters, numbers, '-' or '_'."
            )

    @staticmethod
    def not_found(name: str) -> VoiceError:
        return VoiceError(f"Voice '{name}' was not found.\n\nRun:\nllmvoice voice list")
