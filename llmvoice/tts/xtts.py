from __future__ import annotations

import os
import hashlib
from pathlib import Path
from typing import Any

from llmvoice.core.exceptions import EngineError
from llmvoice.tts.base import TTSEngine

XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
XTTS_LANGUAGES = {
    "ar", "cs", "de", "en", "es", "fr", "hi", "hu", "it", "ja",
    "ko", "nl", "pl", "pt", "ru", "tr", "zh-cn",
}


class XTTSEngine(TTSEngine):
    def __init__(self, device: str, models_dir: Path) -> None:
        self.device = device
        self.models_dir = models_dir
        self._model: Any = None
        self._prepared_speakers: set[str] = set()

    @property
    def display_name(self) -> str:
        return "XTTS-v2"

    @property
    def is_model_installed(self) -> bool:
        """Return whether the named XTTS model appears in the local model directory."""
        if not self.models_dir.exists():
            return False
        return any(
            path.is_dir() and "xtts_v2" in path.name.casefold()
            for path in self.models_dir.rglob("*")
        )

    def load(self) -> None:
        if self._model is not None:
            return
        os.environ["TTS_HOME"] = str(self.models_dir)
        try:
            from TTS.api import TTS
        except ImportError as exc:
            missing = getattr(exc, "name", None)
            detail = f" Missing Python module: {missing}." if missing else ""
            raise EngineError(
                "The XTTS engine dependencies are incomplete."
                f"{detail} Run the installation commands in README.md."
            ) from exc
        try:
            self._model = TTS(model_name=XTTS_MODEL, progress_bar=False).to(self.device)
        except Exception as exc:
            raise EngineError(
                "XTTS-v2 could not be loaded. Check the model license prompt, "
                "internet access for the first download, free disk space, and PyTorch/CUDA setup."
            ) from exc

    def synthesize(
        self,
        text: str,
        voice_path: Path,
        language: str,
        output_path: Path,
    ) -> None:
        if language not in XTTS_LANGUAGES:
            raise EngineError(
                f"XTTS-v2 does not support language '{language}'. "
                f"Supported: {', '.join(sorted(XTTS_LANGUAGES))}"
            )
        if self._model is None:
            raise EngineError("XTTS-v2 is not loaded.")
        speaker_id = self._speaker_id(voice_path)
        voice_is_cached = speaker_id in self._prepared_speakers
        try:
            self._model.tts_to_file(
                text=text,
                speaker=speaker_id,
                speaker_wav=None if voice_is_cached else str(voice_path),
                language=language,
                file_path=str(output_path),
                split_sentences=False,
            )
            self._prepared_speakers.add(speaker_id)
        except Exception as exc:
            raise EngineError("XTTS synthesis failed.") from exc

    @staticmethod
    def _speaker_id(voice_path: Path) -> str:
        stat = voice_path.stat()
        identity = (
            f"{voice_path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
        ).encode("utf-8")
        return f"llmvoice-{hashlib.sha256(identity).hexdigest()[:12]}"
