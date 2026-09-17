from __future__ import annotations

import logging
import hashlib
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from llmvoice.audio.merge import encode_mp3, encode_wav, merge_wav_files, pause_after_text
from llmvoice.audio.reference import prepare_reference
from llmvoice.core.config import AppConfig
from llmvoice.core.exceptions import (
    EngineError,
    InputFileError,
    OutputExistsError,
    JobBusyError,
    SpeechGenerationError,
)
from llmvoice.core.paths import AppPaths
from llmvoice.text.chunker import chunk_text
from llmvoice.text.language import resolve_language
from llmvoice.text.normalizer import normalize_speech_text, normalize_text
from llmvoice.tts.base import TTSEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SynthesisRequest:
    input_path: Path
    output_path: Path
    voice_path: Path
    language: str
    speed: float
    denoise_model: Path | None = None
    quality_profile: str = "balanced"
    voice_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class SynthesisPlan:
    text: str
    chunks: list[str]
    language: str
    auto_detected: bool = False


ProgressCallback = Callable[[int, int], None]
StageCallback = Callable[[str], None]


def _checkpoint_key(request: SynthesisRequest, plan: SynthesisPlan, config: AppConfig) -> str:
    """Create a stable identity for one synthesis configuration."""
    input_stat = request.input_path.stat()
    voice_paths = request.voice_paths or (request.voice_path,)
    denoise_model = request.denoise_model
    denoise_identity = None
    if denoise_model is not None:
        model_stat = denoise_model.stat()
        denoise_identity = {
            "path": str(denoise_model.resolve()),
            "size": model_stat.st_size,
            "mtime_ns": model_stat.st_mtime_ns,
        }
    payload = {
        "input": str(request.input_path.resolve()),
        "input_size": input_stat.st_size,
        "input_mtime_ns": input_stat.st_mtime_ns,
        "output": str(request.output_path.resolve()),
        "voices": [
            {
                "path": str(path.resolve()),
                "size": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
            }
            for path in voice_paths
        ],
        "language": plan.language,
        "speed": request.speed,
        "quality_profile": request.quality_profile,
        "denoise_model": denoise_identity,
        "chunk_pause_ms": config.chunk_pause_ms,
        "crossfade_ms": config.crossfade_ms,
        "engine": config.engine,
        "device": config.device,
        "chunks": plan.chunks,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _write_checkpoint(path: Path, chunks: list[str], completed: list[int]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"version": 1, "chunks": chunks, "completed": completed},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_checkpoint(path: Path, chunks: list[str]) -> list[int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1 or payload.get("chunks") != chunks:
            return []
        completed = payload.get("completed", [])
        if not isinstance(completed, list):
            return []
        if any(
            not isinstance(index, int) or index < 1 or index > len(chunks)
            for index in completed
        ):
            return []
        if len(set(completed)) != len(completed):
            return []
        return sorted(completed)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []


def output_path_for(input_path: Path, output: Path | None, output_format: str = "mp3") -> Path:
    if output is None:
        return input_path.with_suffix(f".{output_format}")
    return output.expanduser().resolve()


def ensure_output_available(output_path: Path, force: bool) -> None:
    """Prevent accidental overwrites unless the caller explicitly opts in."""
    if output_path.exists() and not force:
        raise OutputExistsError(
            "Output file already exists:\n\n"
            f"{output_path}\n\n"
            "Use --force to overwrite it."
        )


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
    speech_text = normalize_speech_text(text, resolved_language)
    return SynthesisPlan(
        text=speech_text,
        chunks=chunk_text(
            speech_text,
            max_chars=chunk_size,
            min_chars=min(80, chunk_size),
        ),
        language=resolved_language,
        auto_detected=language.strip().casefold() == "auto",
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

    @staticmethod
    @contextmanager
    def _job_lock(path: Path):
        lock_path = path.with_name(f".{path.name}.llmvoice-lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError as exc:
                try:
                    stale = time.time() - lock_path.stat().st_mtime > 24 * 60 * 60
                except OSError:
                    stale = False
                if stale:
                    lock_path.unlink(missing_ok=True)
                    continue
                raise JobBusyError(
                    "This synthesis job is already running. Wait for it to finish "
                    "or remove the stale lock after confirming no job is active."
                ) from exc
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            yield
        finally:
            lock_path.unlink(missing_ok=True)

    def run(
        self,
        request: SynthesisRequest,
        plan: SynthesisPlan,
        progress: ProgressCallback,
        stage: StageCallback,
        resume: bool = False,
    ) -> None:
        with self._job_lock(request.output_path):
            self._run_locked(request, plan, progress, stage, resume)

    def _run_locked(
        self,
        request: SynthesisRequest,
        plan: SynthesisPlan,
        progress: ProgressCallback,
        stage: StageCallback,
        resume: bool = False,
    ) -> None:
        stage("preparing_reference")
        source_paths = request.voice_paths or (request.voice_path,)
        if request.denoise_model is None:
            references = [
                prepare_reference(source, self.paths.cache_dir)
                for source in source_paths
            ]
        else:
            references = [
                prepare_reference(
                    source,
                    self.paths.cache_dir,
                    denoise_model=request.denoise_model,
                )
                for source in source_paths
            ]
        reference: Path | list[Path] = references[0] if len(references) == 1 else references
        stage("reference_ready")
        stage("loading_model")
        set_quality_profile = getattr(self.engine, "set_quality_profile", None)
        if set_quality_profile is not None:
            set_quality_profile(request.quality_profile)
        self.engine.load()
        stage("model_ready")

        self.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_dir: Path | None = None
        if resume:
            checkpoint_dir = self.paths.cache_dir / "checkpoints" / _checkpoint_key(request, plan, self.config)
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            manifest = checkpoint_dir / "manifest.json"
            completed = _load_checkpoint(manifest, plan.chunks) if manifest.exists() else []
            completed = [
                index
                for index in completed
                if (checkpoint_dir / f"chunk-{index:05d}.wav").is_file()
            ]
            _write_checkpoint(manifest, plan.chunks, completed)
            working_dir = checkpoint_dir
        else:
            completed = []
            working_dir = Path(tempfile.mkdtemp(prefix="job-", dir=self.paths.cache_dir))
        try:
            generated: list[Path] = []
            total = len(plan.chunks)
            for index, text in enumerate(plan.chunks, start=1):
                chunk_path = working_dir / f"chunk-{index:05d}.wav"
                if index in completed:
                    generated.append(chunk_path)
                    progress(index, total)
                    continue
                logger.debug("Synthesizing chunk %d/%d (%d chars)", index, total, len(text))
                temporary_chunk = working_dir / f".chunk-{index:05d}.tmp.wav"
                try:
                    self.engine.synthesize(
                        text=text,
                        voice_path=reference,
                        language=plan.language,
                        output_path=temporary_chunk,
                    )
                except EngineError as exc:
                    temporary_chunk.unlink(missing_ok=True)
                    raise SpeechGenerationError(index, total) from exc
                temporary_chunk.replace(chunk_path)
                generated.append(chunk_path)
                completed.append(index)
                if checkpoint_dir is not None:
                    _write_checkpoint(checkpoint_dir / "manifest.json", plan.chunks, completed)
                progress(index, total)
            stage("merging")
            merged = working_dir / "merged.wav"
            merge_wav_files(
                generated,
                merged,
                pause_ms=[
                    pause_after_text(chunk, self.config.chunk_pause_ms)
                    for chunk in plan.chunks[:-1]
                ],
                crossfade_ms=self.config.crossfade_ms,
            )
            stage("merge_done")
            stage("encoding")
            encode_source = generated[0] if len(generated) == 1 else merged
            logger.debug(
                "Encoding source: %s (exists=%s, size=%s)",
                encode_source,
                encode_source.is_file(),
                encode_source.stat().st_size if encode_source.is_file() else None,
            )
            if request.output_path.suffix.casefold() == ".wav":
                encode_wav(encode_source, request.output_path, request.speed)
            else:
                encode_mp3(encode_source, request.output_path, request.speed)
            stage("encoding_done")
            if checkpoint_dir is not None:
                shutil.rmtree(checkpoint_dir, ignore_errors=True)
        finally:
            if not resume:
                shutil.rmtree(working_dir, ignore_errors=True)
