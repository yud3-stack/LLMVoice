from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from llmvoice.audio.merge import encode_mp3, merge_wav_files
from llmvoice.audio.reference import prepare_reference
from llmvoice.core.config import AppConfig
from llmvoice.core.exceptions import InputFileError
from llmvoice.core.paths import AppPaths
from llmvoice.text.chunker import chunk_text
from llmvoice.text.language import resolve_language
from llmvoice.text.normalizer import normalize_text
from llmvoice.tts.base import TTSEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SynthesisRequest:
    input_path: Path
    output_path: Path
    voice_path: Path
    language: str
    speed: float


@dataclass(frozen=True)
class SynthesisPlan:
    text: str
    chunks: list[str]
    language: str


ProgressCallback = Callable[[int, int], None]
StageCallback = Callable[[str], None]


def output_path_for(input_path: Path, output: Path | None) -> Path:
    if output is None:
        return input_path.with_suffix(".mp3")
    return output.expanduser().resolve()


def read_and_plan(input_path: Path, language: str, chunk_size: int) -> SynthesisPlan:
    if not input_path.is_file():
        raise InputFileError(f"Input file not found: {input_path}")
    if input_path.suffix.casefold() != ".txt":
        raise InputFileError(f"Input must be a .txt file: {input_path}")
    try:
        raw = input_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise InputFileError(f"Input file is not valid readable UTF-8: {input_path}") from exc
    text = normalize_text(raw)
    if not text:
        raise InputFileError(f"Input file contains no text: {input_path}")
    resolved_language = resolve_language(language, text)
    return SynthesisPlan(
        text=text,
        chunks=chunk_text(text, max_chars=chunk_size),
        language=resolved_language,
    )


class VoiceService:
    def __init__(
        self,
        engine: TTSEngine,
        paths: AppPaths,
        config: AppConfig,
    ) -> None:
        self.engine = engine
        self.paths = paths
        self.config = config

    def run(
        self,
        request: SynthesisRequest,
        plan: SynthesisPlan,
        progress: ProgressCallback,
        stage: StageCallback,
    ) -> None:
        stage("preparing_reference")
        reference = prepare_reference(request.voice_path, self.paths.cache_dir)
        stage("loading_model")
        self.engine.load()
        stage("model_loaded")

        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary_dir = Path(tempfile.mkdtemp(prefix="job-", dir=self.paths.cache_dir))
        try:
            generated: list[Path] = []
            total = len(plan.chunks)
            for index, text in enumerate(plan.chunks, start=1):
                chunk_path = temporary_dir / f"chunk-{index:05d}.wav"
                logger.debug("Synthesizing chunk %d/%d (%d chars)", index, total, len(text))
                self.engine.synthesize(
                    text=text,
                    voice_path=reference,
                    language=plan.language,
                    output_path=chunk_path,
                )
                generated.append(chunk_path)
                progress(index, total)
            stage("merging")
            merged = temporary_dir / "merged.wav"
            merge_wav_files(generated, merged)
            stage("encoding")
            encode_mp3(merged, request.output_path, request.speed)
        finally:
            shutil.rmtree(temporary_dir, ignore_errors=True)

