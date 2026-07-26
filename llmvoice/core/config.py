from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from llmvoice.core.exceptions import ConfigurationError
from llmvoice.core.paths import AppPaths

VALID_DEVICES = {"auto", "cuda", "cpu"}
MIN_SPEED = 0.5
MAX_SPEED = 2.0


@dataclass(frozen=True)
class AppConfig:
    default_voice: str | None = None
    default_language: str = "tr"
    default_speed: float = 1.0
    output_format: str = "mp3"
    device: str = "auto"
    engine: str = "xtts"
    chunk_size: int = 220

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "AppConfig":
        known = {field: values[field] for field in cls.__dataclass_fields__ if field in values}
        try:
            config = cls(**known)
        except TypeError as exc:
            raise ConfigurationError(f"Invalid config fields: {exc}") from exc
        config.validate()
        return config

    def validate(self) -> None:
        if self.default_voice is not None and not isinstance(self.default_voice, str):
            raise ConfigurationError("Config 'default_voice' must be a string or null.")
        if not isinstance(self.default_language, str):
            raise ConfigurationError("Config 'default_language' must be a string.")
        if not isinstance(self.default_speed, (int, float)) or isinstance(
            self.default_speed, bool
        ):
            raise ConfigurationError("Config 'default_speed' must be a number.")
        if not isinstance(self.chunk_size, int) or isinstance(self.chunk_size, bool):
            raise ConfigurationError("Config 'chunk_size' must be an integer.")
        if not isinstance(self.device, str):
            raise ConfigurationError("Config 'device' must be a string.")
        if self.device not in VALID_DEVICES:
            raise ConfigurationError("Config 'device' must be one of: auto, cuda, cpu.")
        if not MIN_SPEED <= self.default_speed <= MAX_SPEED:
            raise ConfigurationError(
                f"Config 'default_speed' must be between {MIN_SPEED} and {MAX_SPEED}."
            )
        if self.output_format != "mp3":
            raise ConfigurationError("Only 'mp3' output is currently supported.")
        if not 80 <= self.chunk_size <= 400:
            raise ConfigurationError("Config 'chunk_size' must be between 80 and 400.")
        if not self.default_language.strip():
            raise ConfigurationError("Config 'default_language' cannot be empty.")


class ConfigStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def load(self) -> AppConfig:
        self.paths.ensure()
        if not self.paths.config_file.exists():
            config = AppConfig()
            self.save(config)
            return config
        try:
            raw = json.loads(self.paths.config_file.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Could not read config: {self.paths.config_file}"
            ) from exc
        if not isinstance(raw, dict):
            raise ConfigurationError("Config root must be a JSON object.")
        return AppConfig.from_dict(raw)

    def save(self, config: AppConfig) -> None:
        config.validate()
        self.paths.ensure()
        temporary = self.paths.root / f".config-{uuid4().hex}.tmp"
        try:
            temporary.write_text(
                json.dumps(asdict(config), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.paths.config_file)
        except OSError as exc:
            raise ConfigurationError(
                f"Could not write config: {self.paths.config_file}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
