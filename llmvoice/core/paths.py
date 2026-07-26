from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def discover(cls) -> "AppPaths":
        override = os.environ.get("LLMVOICE_DATA_DIR")
        root = Path(override).expanduser() if override else user_data_path("LLMVoice", appauthor=False)
        return cls(root=root.resolve())

    @property
    def voices_dir(self) -> Path:
        return self.root / "voices"

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def config_file(self) -> Path:
        return self.root / "config.json"

    def ensure(self) -> None:
        for directory in (self.root, self.voices_dir, self.models_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)

