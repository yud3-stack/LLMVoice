from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSEngine(ABC):
    @property
    @abstractmethod
    def display_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def load(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_path: Path,
        language: str,
        output_path: Path,
    ) -> None:
        raise NotImplementedError

