from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from llmvoice.core.exceptions import ConfigurationError
from llmvoice.core.paths import AppPaths
from llmvoice.text.languages import SUPPORTED_LANGUAGES

VALID_DEVICES = {"auto", "cuda", "cpu"}
VALID_ENGINES = {"xtts"}
VALID_QUALITY_PROFILES = {"natural", "balanced", "stable", "expressive"}
VALID_OUTPUT_FORMATS = {"mp3", "wav"}
MIN_SPEED = 0.5
MAX_SPEED = 2.0
MIN_CHUNK_PAUSE_MS = 0
MAX_CHUNK_PAUSE_MS = 500
MIN_CROSSFADE_MS = 0
MAX_CROSSFADE_MS = 100


@dataclass(frozen=True)
class AppConfig:
    default_voice: str | None = None
    default_language: str = "tr"
    default_speed: float = 1.0
    output_format: str = "mp3"
    device: str = "auto"
    engine: str = "xtts"
    chunk_size: int = 220
    chunk_pause_ms: int = 20
    crossfade_ms: int = 0
    quality_profile: str = "balanced"

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "AppConfig":
        unknown = sorted(set(values) - set(cls.__dataclass_fields__))
        if unknown:
            raise ConfigurationError(
                "Unknown config field(s): " + ", ".join(unknown)
            )
        try:
            config = cls(**values)
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
        if not isinstance(self.chunk_pause_ms, int) or isinstance(
            self.chunk_pause_ms, bool
        ):
            raise ConfigurationError("Config 'chunk_pause_ms' must be an integer.")
        if not isinstance(self.crossfade_ms, int) or isinstance(self.crossfade_ms, bool):
            raise ConfigurationError("Config 'crossfade_ms' must be an integer.")
        if not isinstance(self.device, str):
            raise ConfigurationError("Config 'device' must be a string.")
        if not isinstance(self.engine, str) or self.engine not in VALID_ENGINES:
            raise ConfigurationError("Config 'engine' must be one of: xtts.")
        if not isinstance(self.output_format, str):
            raise ConfigurationError("Config 'output_format' must be a string.")
        if not isinstance(self.quality_profile, str) or self.quality_profile not in VALID_QUALITY_PROFILES:
            raise ConfigurationError(
                "Config 'quality_profile' must be one of: natural, balanced, stable, expressive."
            )
        if self.device not in VALID_DEVICES:
            raise ConfigurationError("Config 'device' must be one of: auto, cuda, cpu.")
        if not MIN_SPEED <= self.default_speed <= MAX_SPEED:
            raise ConfigurationError(
                f"Config 'default_speed' must be between {MIN_SPEED} and {MAX_SPEED}."
            )
        if self.output_format not in VALID_OUTPUT_FORMATS:
            raise ConfigurationError("Config 'output_format' must be one of: mp3, wav.")
        if not 80 <= self.chunk_size <= 400:
            raise ConfigurationError("Config 'chunk_size' must be between 80 and 400.")
        if not MIN_CHUNK_PAUSE_MS <= self.chunk_pause_ms <= MAX_CHUNK_PAUSE_MS:
            raise ConfigurationError(
                f"Config 'chunk_pause_ms' must be between "
                f"{MIN_CHUNK_PAUSE_MS} and {MAX_CHUNK_PAUSE_MS}."
            )
        if not MIN_CROSSFADE_MS <= self.crossfade_ms <= MAX_CROSSFADE_MS:
            raise ConfigurationError(
                f"Config 'crossfade_ms' must be between "
                f"{MIN_CROSSFADE_MS} and {MAX_CROSSFADE_MS}."
            )
        if self.default_language.casefold() not in SUPPORTED_LANGUAGES:
            raise ConfigurationError(
                "Config 'default_language' must be a supported language code."
            )


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

    def get(self, field: str) -> Any:
        """Return one validated configuration field."""
        self._validate_field(field)
        return getattr(self.load(), field)

    def set(self, field: str, raw_value: str) -> AppConfig:
        """Parse, validate, and persist one configuration field."""
        self._validate_field(field)
        current = self.load()
        value = self._parse_value(field, raw_value, current)
        updated = replace(current, **{field: value})
        updated.validate()
        self.save(updated)
        return updated

    @staticmethod
    def _validate_field(field: str) -> None:
        if field not in AppConfig.__dataclass_fields__:
            allowed = ", ".join(AppConfig.__dataclass_fields__)
            raise ConfigurationError(
                f"Unknown config field '{field}'.\n\nAvailable fields:\n{allowed}"
            )

    @staticmethod
    def _parse_value(field: str, raw_value: str, current: AppConfig) -> Any:
        existing = getattr(current, field)
        if field == "default_voice":
            return None if raw_value.casefold() in {"none", "null", ""} else raw_value
        if isinstance(existing, bool):
            lowered = raw_value.casefold()
            if lowered not in {"true", "false"}:
                raise ConfigurationError(f"Config '{field}' must be true or false.")
            return lowered == "true"
        if isinstance(existing, int) and not isinstance(existing, bool):
            try:
                return int(raw_value)
            except ValueError as exc:
                raise ConfigurationError(f"Config '{field}' must be an integer.") from exc
        if isinstance(existing, float):
            try:
                return float(raw_value)
            except ValueError as exc:
                raise ConfigurationError(f"Config '{field}' must be a number.") from exc
        return raw_value
