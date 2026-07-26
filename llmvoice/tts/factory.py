from __future__ import annotations

from llmvoice.core.exceptions import ConfigurationError
from llmvoice.core.paths import AppPaths
from llmvoice.tts.base import TTSEngine
from llmvoice.tts.xtts import XTTSEngine


def create_engine(name: str, device: str, paths: AppPaths) -> TTSEngine:
    if name == "xtts":
        return XTTSEngine(device=device, models_dir=paths.models_dir)
    raise ConfigurationError(f"Unknown TTS engine: {name}")

