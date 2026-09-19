from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.status import Status

from llmvoice import __version__
from llmvoice.audio.ffmpeg import require_ffmpeg
from llmvoice.audio.metadata import probe_audio
from llmvoice.audio.quality import MIN_USABLE_REFERENCE_SCORE, inspect_audio
from llmvoice.audio.recording import list_audio_devices, record_audio
from llmvoice.cli_output import (
    details_table,
    render_created,
    render_start_summary,
    render_voice_added,
    render_voice_info,
    render_voice_list,
    status_symbol,
)
from llmvoice.core.config import MAX_SPEED, MIN_SPEED, VALID_QUALITY_PROFILES, ConfigStore
from llmvoice.core.exceptions import LLMVoiceError, VoiceError
from llmvoice.core.paths import AppPaths
from llmvoice.core.storage import check_synthesis_disk_space, estimate_speech_seconds
from llmvoice.doctor import run_diagnostics
from llmvoice.service import (
    SynthesisRequest,
    VoiceService,
    ensure_output_available,
    output_path_for,
    read_and_plan,
)
from llmvoice.tts.device import resolve_device
from llmvoice.tts.factory import create_engine, engine_display_name
from llmvoice.tts.xtts import XTTS_MODEL
from llmvoice.voices.manager import RECOMMENDED_MAX_SECONDS, VoiceManager

console = Console()
error_console = Console(stderr=True)

CLI_CONTRACT_SCHEMA = 1
CLI_EVENT_PROTOCOL = "llmvoice.ndjson.v1"
SUPPORTED_OUTPUT_FORMATS = ("mp3", "wav")


def _voice_to_dict(voice) -> dict[str, object]:
    """Return stable, path-safe data for automation clients."""
    return {
        "name": voice.name,
        "path": str(voice.path),
        "duration_seconds": voice.metadata.duration_seconds,
        "sample_rate": voice.metadata.sample_rate,
        "channels": voice.metadata.channels,
        "codec": voice.metadata.codec,
        "format": voice.metadata.format_name,
        "reference_count": len(voice.reference_paths) or 1,
    }


def _print_json(value: object, *, indent: int | None = None) -> None:
    """Write JSON without Rich wrapping it for narrow terminals."""
    console.print(
        json.dumps(value, indent=indent, ensure_ascii=False),
        markup=False,
        soft_wrap=True,
        no_wrap=True,
    )

HELP_TEXT = """Local long-form voice cloning CLI.

Quick start:

1. Add a voice:
   llmvoice voice add friday reference.wav

2. Generate speech:
   llmvoice start transcript.txt --voice friday
"""

app = typer.Typer(
    name="llmvoice",
    help=HELP_TEXT,
    no_args_is_help=True,
    rich_markup_mode=None,
)
voice_app = typer.Typer(help="Manage stored voices.", no_args_is_help=True)
config_app = typer.Typer(help="Inspect and update configuration.", no_args_is_help=True)
model_app = typer.Typer(help="Manage local TTS models.", no_args_is_help=True)
audio_app = typer.Typer(help="Inspect and record audio inputs.", no_args_is_help=True)
app.add_typer(voice_app, name="voice")
app.add_typer(config_app, name="config")
app.add_typer(model_app, name="model")
app.add_typer(audio_app, name="audio")


@app.command("capabilities")
def capabilities(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Show the stable CLI contract exposed to desktop clients."""
    payload = {
        "schema_version": CLI_CONTRACT_SCHEMA,
        "version": __version__,
        "output_formats": list(SUPPORTED_OUTPUT_FORMATS),
        "quality_profiles": sorted(VALID_QUALITY_PROFILES),
        "event_protocol": CLI_EVENT_PROTOCOL,
    }
    if json_output:
        _print_json(payload)
        return
    console.print("\n[bold]LLMVoice capabilities[/bold]\n")
    console.print(details_table([(key, str(value)) for key, value in payload.items()]))


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"LLMVoice {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Generate speech locally without cloud APIs or telemetry."""


def _run_safely(
    action: Callable[[], None],
    debug: bool = False,
    json_output: bool = False,
) -> None:
    try:
        action()
    except KeyboardInterrupt:
        if json_output:
            _print_json({"ok": False, "error": "cancelled", "message": "Generation cancelled."})
            raise typer.Exit(code=130) from None
        error_console.print(
            "\nGeneration cancelled.\n\nTemporary files were cleaned up.",
            markup=False,
        )
        raise typer.Exit(code=130) from None
    except LLMVoiceError as exc:
        if json_output:
            _print_json(
                {
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
            )
            raise typer.Exit(code=1) from None
        if debug:
            error_console.print_exception(show_locals=False)
        else:
            error_console.print(f"Error: {exc}", markup=False)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        if json_output:
            _print_json(
                {
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
            )
            raise typer.Exit(code=1) from None
        if debug:
            error_console.print_exception(show_locals=False)
        else:
            error_console.print(
                f"Error: Unexpected failure: {exc}\n\n"
                "Run the same command with --debug for a stack trace.",
                markup=False,
            )
        raise typer.Exit(code=1) from None


@model_app.command("status")
def model_status(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Show whether the configured local TTS model is installed."""

    def action() -> None:
        paths = AppPaths.discover()
        config = ConfigStore(paths).load()
        engine = create_engine(config.engine, "cpu", paths)
        installed = bool(getattr(engine, "is_model_installed", False))
        payload = {
            "installed": installed,
            "engine": engine_display_name(config.engine),
            "model": XTTS_MODEL if config.engine == "xtts" else config.engine,
            "models_dir": str(paths.models_dir),
        }
        if json_output:
            _print_json(payload)
        else:
            console.print("\n[bold]LLMVoice Model[/bold]\n")
            console.print(
                details_table(
                    [
                        ("Engine", str(payload["engine"])),
                        ("Model", str(payload["model"])),
                        ("Status", "Installed" if installed else "Not installed"),
                        ("Directory", str(payload["models_dir"])),
                    ]
                )
            )
            if not installed:
                console.print("\nDownload it with: llmvoice model download")

    _run_safely(action, json_output=json_output)


@model_app.command("download")
def model_download(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print one machine-readable JSON result.")
    ] = False,
) -> None:
    """Download and validate the configured local TTS model."""

    def action() -> None:
        paths = AppPaths.discover()
        config = ConfigStore(paths).load()
        device = resolve_device(config.device)
        engine = create_engine(config.engine, device.kind, paths)
        if not json_output:
            console.print(
                f"Downloading/loading {engine.display_name} on {device.label}.\n"
                "This may take several minutes on the first run."
            )
        engine.load()
        payload = {
            "ok": True,
            "installed": bool(getattr(engine, "is_model_installed", False)),
            "engine": engine.display_name,
            "models_dir": str(paths.models_dir),
            "device": device.label,
        }
        if json_output:
            _print_json(payload)
        else:
            console.print("\n[green]Model is ready for offline use.[/green]")

    _run_safely(action, json_output=json_output)


@app.command()
def start(
    input_file: Annotated[Path, typer.Argument(help="UTF-8 .txt transcript.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Destination .mp3 path.")
    ] = None,
    voice: Annotated[
        str | None, typer.Option("--voice", help="Stored voice name or audio file path.")
    ] = None,
    speed: Annotated[
        float | None, typer.Option("--speed", min=MIN_SPEED, max=MAX_SPEED)
    ] = None,
    language: Annotated[
        str | None, typer.Option("--language", help="Language code (tr, en, ...) or auto.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing output file.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the synthesis plan without generating audio.")
    ] = False,
    debug: Annotated[
        bool, typer.Option("--debug", help="Show debug logs and stack traces.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print one machine-readable JSON result.")
    ] = False,
    resume: Annotated[
        bool,
        typer.Option(
            "--resume",
            help="Reuse completed chunks from an interrupted synthesis job.",
        ),
    ] = False,
    denoise_model: Annotated[
        Path | None,
        typer.Option(
            "--denoise-model",
            help="Optional FFmpeg RNNoise .model file for the voice reference.",
        ),
    ] = None,
    quality: Annotated[
        str | None,
        typer.Option(
            "--quality",
            help="XTTS quality profile: natural, balanced, or stable.",
        ),
    ] = None,
    strict_reference_quality: Annotated[
        bool,
        typer.Option(
            "--strict-reference-quality",
            help="Use only references scoring at least 60/100.",
        ),
    ] = False,
) -> None:
    """Convert a transcript into a cloned-voice MP3."""

    def action() -> None:
        logging.basicConfig(
            level=logging.DEBUG if debug else logging.WARNING,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        paths = AppPaths.discover()
        config = ConfigStore(paths).load()
        manager = VoiceManager(paths)
        input_path = input_file.expanduser().resolve()
        requested_language = language or config.default_language
        plan = read_and_plan(input_path, requested_language, config.chunk_size)

        selected_voice = voice or config.default_voice
        if not selected_voice:
            raise VoiceError(
                "No voice selected.\n\n"
                "Use:\n\n"
                "llmvoice start transcript.txt --voice friday\n\n"
                "or set a default:\n\n"
                "llmvoice config set default_voice friday"
            )
        voice_is_default = voice is None and config.default_voice is not None
        voice_paths = manager.resolve_references(selected_voice)
        reference_reports = []
        if strict_reference_quality and not dry_run:
            reference_reports = [(path, inspect_audio(path)) for path in voice_paths]
            voice_paths = tuple(
                path
                for path, report in reference_reports
                if report.score >= MIN_USABLE_REFERENCE_SCORE
            )
            if not voice_paths:
                raise VoiceError(
                    "No usable voice references remain after quality filtering.\n\n"
                    "Run 'llmvoice voice references' to review the profile, or "
                    "omit --strict-reference-quality."
                )
        voice_path = voice_paths[0]

        destination = output_path_for(input_path, output)
        if destination.suffix.casefold() != ".mp3":
            raise LLMVoiceError("Output path must end with .mp3.")
        if not dry_run:
            ensure_output_available(destination, force)

        selected_speed = speed if speed is not None else config.default_speed
        selected_quality = quality or config.quality_profile
        if selected_quality not in VALID_QUALITY_PROFILES:
            raise LLMVoiceError(
                "Quality profile must be one of: natural, balanced, stable."
            )
        selected_denoise_model = (
            denoise_model.expanduser().resolve() if denoise_model is not None else None
        )
        if selected_denoise_model is not None and not selected_denoise_model.is_file():
            raise LLMVoiceError(f"RNNoise model not found: {selected_denoise_model}")
        device = resolve_device(config.device)
        estimated_seconds = estimate_speech_seconds(plan.text)

        engine_name = engine_display_name(config.engine)
        if not json_output:
            render_start_summary(
                console,
                version=__version__,
                input_path=input_path,
                voice=selected_voice,
                voice_is_default=voice_is_default,
                language=plan.language,
                auto_detected=plan.auto_detected,
                device=device.label,
                engine=engine_name,
                output_path=destination,
                characters=len(plan.text),
                chunks=len(plan.chunks),
                estimated_seconds=estimated_seconds,
                dry_run=dry_run,
            )
        if device.kind == "cpu" and config.device == "auto" and not json_output:
            console.print(
                "[yellow]Warning:[/yellow] CUDA was not detected. "
                "Long-form generation may be significantly slower.\n"
            )
        if dry_run:
            if json_output:
                _print_json(
                    {
                        "ok": True,
                        "dry_run": True,
                        "input": str(input_path),
                        "output": str(destination),
                        "voice": selected_voice,
                        "language": plan.language,
                        "auto_detected": plan.auto_detected,
                        "device": device.label,
                        "engine": engine_name,
                        "resume": resume,
                        "denoise_model": str(selected_denoise_model) if selected_denoise_model else None,
                        "reference_count": len(voice_paths),
                        "strict_reference_quality": strict_reference_quality,
                        "quality": selected_quality,
                        "characters": len(plan.text),
                        "chunks": len(plan.chunks),
                        "estimated_seconds": estimated_seconds,
                    }
                )
            else:
                console.print("No audio was generated.")
            return

        if resume and not json_output:
            console.print("Resume mode enabled; completed chunks will be reused if available.\n")

        require_ffmpeg()
        engine = create_engine(config.engine, device.kind, paths)
        check_synthesis_disk_space(paths.cache_dir, destination, estimated_seconds)
        if not getattr(engine, "is_model_installed", True) and not json_output:
            console.print(
                "XTTS-v2 model is not installed locally.\n"
                "The model may be downloaded during this run.\n"
                "After installation, synthesis can run offline.\n"
            )

        progress = Progress(
            TextColumn("[bold]{task.description}[/bold]"),
            BarColumn(bar_width=28),
            TaskProgressColumn(),
            TextColumn("{task.completed:.0f} / {task.total:.0f} chunks"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        task_id: int | None = None
        active_status: Status | None = None

        def stop_status() -> None:
            nonlocal active_status
            if active_status is not None:
                active_status.stop()
                active_status = None

        def stage(name: str) -> None:
            nonlocal active_status
            if json_output:
                return
            ready = f"[green]{status_symbol(console, 'ok')}[/green]"
            if name == "preparing_reference":
                stop_status()
                active_status = console.status("Preparing voice...", spinner="dots")
                active_status.start()
                return
            if name == "loading_model":
                stop_status()
                active_status = console.status("Loading XTTS-v2...", spinner="dots")
                active_status.start()
                return
            if name in {"reference_ready", "model_ready"}:
                stop_status()
            labels = {
                "reference_ready": f"{ready} Voice ready",
                "model_ready": f"{ready} Model ready",
                "merging": "Merging audio...",
                "merge_done": f"{ready} Done",
                "encoding": "Encoding MP3...",
                "encoding_done": f"{ready} Done",
            }
            console.print(labels[name])

        def on_progress(current: int, total: int) -> None:
            nonlocal task_id
            if json_output:
                return
            if task_id is None:
                progress.start()
                task_id = progress.add_task("Generating speech", total=total)
            progress.update(task_id, completed=current)
            if current == total:
                progress.stop()

        service = VoiceService(engine=engine, paths=paths, config=config)
        try:
            service.run(
                SynthesisRequest(
                    input_path=input_path,
                    output_path=destination,
                    voice_path=voice_path,
                    voice_paths=voice_paths,
                    language=plan.language,
                    speed=selected_speed,
                    denoise_model=selected_denoise_model,
                    quality_profile=selected_quality,
                ),
                plan=plan,
                progress=on_progress,
                stage=stage,
                resume=resume,
            )
        finally:
            stop_status()
            if task_id is not None:
                progress.stop()
        metadata = probe_audio(destination)
        if json_output:
            _print_json(
                {
                    "ok": True,
                    "dry_run": False,
                    "input": str(input_path),
                    "output": str(destination),
                    "voice": selected_voice,
                    "language": plan.language,
                    "auto_detected": plan.auto_detected,
                    "device": device.label,
                    "engine": engine_name,
                    "resume": resume,
                    "denoise_model": str(selected_denoise_model) if selected_denoise_model else None,
                    "reference_count": len(voice_paths),
                    "strict_reference_quality": strict_reference_quality,
                    "quality": selected_quality,
                    "characters": len(plan.text),
                    "chunks": len(plan.chunks),
                    "estimated_seconds": estimated_seconds,
                    "duration_seconds": metadata.duration_seconds,
                    "size_bytes": destination.stat().st_size,
                }
            )
        else:
            render_created(console, destination, metadata)

    _run_safely(action, debug=debug, json_output=json_output)


@app.command()
def compare(
    input_file: Annotated[Path, typer.Argument(help="UTF-8 .txt transcript.")],
    voice: Annotated[str | None, typer.Option("--voice", help="Stored voice name or audio path.")] = None,
    output_dir: Annotated[Path, typer.Option("--output-dir", help="Directory for comparison files.")] = Path("compare"),
    language: Annotated[str | None, typer.Option("--language", help="Language code or auto.")] = None,
    speed: Annotated[float | None, typer.Option("--speed", min=MIN_SPEED, max=MAX_SPEED)] = None,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug logs and stack traces.")] = False,
) -> None:
    """Generate natural, balanced, and stable outputs for A/B listening."""

    def action() -> None:
        destination_dir = output_dir.expanduser().resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)
        for profile in ("natural", "balanced", "stable"):
            destination = destination_dir / f"{input_file.stem}-{profile}.mp3"
            start(
                input_file=input_file,
                output=destination,
                voice=voice,
                speed=speed,
                language=language,
                force=True,
                dry_run=False,
                debug=debug,
                json_output=False,
                resume=False,
                denoise_model=None,
                quality=profile,
            )

    _run_safely(action, debug=debug)


@voice_app.command("add")
def voice_add(
    name: Annotated[str, typer.Argument(help="Name used by --voice.")],
    audio_file: Annotated[Path, typer.Argument(help="Reference audio file.")],
    references: Annotated[
        list[Path] | None,
        typer.Option(
            "--reference",
            help="Additional recordings of the same speaker. May be repeated.",
        ),
    ] = None,
) -> None:
    def action() -> None:
        stored = VoiceManager(AppPaths.discover()).add(
            name,
            audio_file,
            tuple(references or ()),
        )
        render_voice_added(console, stored)
        if stored.metadata.duration_seconds > RECOMMENDED_MAX_SECONDS:
            console.print(
                "\n[yellow]Warning:[/yellow] Long reference audio detected.\n"
                "Recommended reference length is approximately 6–30 seconds."
            )

    _run_safely(action)


@voice_app.command("list")
def voice_list(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    def action() -> None:
        voices = VoiceManager(AppPaths.discover()).list()
        if json_output:
            _print_json([_voice_to_dict(voice) for voice in voices])
        else:
            render_voice_list(console, voices)

    _run_safely(action)


@voice_app.command("info")
def voice_info(
    name: Annotated[str, typer.Argument(help="Stored voice name.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    def action() -> None:
        voice = VoiceManager(AppPaths.discover()).info(name)
        if json_output:
            _print_json(_voice_to_dict(voice))
        else:
            render_voice_info(console, voice)

    _run_safely(action)


@voice_app.command("inspect")
def voice_inspect(
    audio_file: Annotated[Path, typer.Argument(help="Audio file to inspect.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Report reference quality without modifying the audio file."""

    def action() -> None:
        report = inspect_audio(audio_file.expanduser().resolve())
        if json_output:
            _print_json(report.as_dict(), indent=2)
            return
        console.print("\n[bold]Voice Quality Report[/bold]\n")
        console.print(
            details_table(
                [
                    ("Quality", report.quality.upper()),
                    ("Duration", f"{report.duration_seconds:.1f} sec"),
                    ("Sample rate", f"{report.sample_rate} Hz"),
                    ("Channels", str(report.channels)),
                    ("Mean volume", f"{report.mean_volume_db:.1f} dB" if report.mean_volume_db is not None else "Unknown"),
                        ("Peak volume", f"{report.max_volume_db:.1f} dB" if report.max_volume_db is not None else "Unknown"),
                        ("Quality score", f"{report.score}/100"),
                        ("Silence ratio", f"{report.silence_ratio:.0%}"),
                        ("Clipping risk", "Yes" if report.clipping_risk else "No"),
                ]
            )
        )
        for recommendation in report.recommendations:
            console.print(f"  [yellow]![/yellow] {recommendation}")

    _run_safely(action, json_output=json_output)


@voice_app.command("references")
def voice_references(
    name: Annotated[str, typer.Argument(help="Stored voice profile name.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Show quality information for every reference in a voice profile."""

    def action() -> None:
        voice = VoiceManager(AppPaths.discover()).info(name)
        reports = []
        for path in voice.reference_paths:
            report = inspect_audio(path)
            reports.append(
                {
                    "path": str(path),
                    "score": report.score,
                    "quality": report.quality,
                    "duration_seconds": report.duration_seconds,
                    "silence_ratio": report.silence_ratio,
                    "clipping_risk": report.clipping_risk,
                    "recommendations": report.recommendations,
                }
            )
        if json_output:
            _print_json({"voice": name, "references": reports}, indent=2)
            return
        console.print(f"\n[bold]References: {name}[/bold]\n")
        for report in reports:
            score_style = "green" if report["score"] >= 80 else "yellow" if report["score"] >= MIN_USABLE_REFERENCE_SCORE else "red"
            console.print(
                details_table(
                    [
                        ("File", Path(report["path"]).name),
                        ("Score", f"[{score_style}]{report['score']}/100[/{score_style}]"),
                        ("Quality", str(report["quality"])),
                        ("Silence", f"{report['silence_ratio']:.0%}"),
                        ("Clipping", "Yes" if report["clipping_risk"] else "No"),
                    ]
                )
            )
            for recommendation in report["recommendations"]:
                console.print(f"  [yellow]![/yellow] {recommendation}")
            console.print()

    _run_safely(action, json_output=json_output)


@voice_app.command("remove")
def voice_remove(
    name: Annotated[str, typer.Argument(help="Stored voice name.")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Remove without confirmation.")
    ] = False,
) -> None:
    def action() -> None:
        manager = VoiceManager(AppPaths.discover())
        manager.info(name)
        if not yes and not typer.confirm(f"Remove voice '{name}'?", default=False):
            console.print("Voice was not removed.")
            return
        manager.remove(name)
        console.print(f"Voice '{name}' removed.")

    _run_safely(action)


@audio_app.command("devices")
def audio_devices() -> None:
    """List Windows microphone inputs detected by FFmpeg."""

    def action() -> None:
        devices = list_audio_devices()
        if not devices:
            console.print("No audio input devices found.")
            return
        console.print("\n[bold]Audio input devices[/bold]\n")
        for index, device in enumerate(devices, start=1):
            console.print(f"  {index}. {device}")

    _run_safely(action)


@voice_app.command("record")
def voice_record(
    name: Annotated[str, typer.Argument(help="Voice profile name to create or update.")],
    duration: Annotated[
        float, typer.Option("--duration", min=1.0, max=3600.0, help="Recording length in seconds.")
    ] = 10.0,
    device: Annotated[
        str | None, typer.Option("--device", help="Exact FFmpeg microphone device name.")
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Save without confirmation.")
    ] = False,
) -> None:
    """Record a microphone reference and create or extend a voice profile."""

    def action() -> None:
        paths = AppPaths.discover()
        paths.ensure()
        temporary = paths.cache_dir / "recordings" / f"{name}.wav"
        console.print(
            f"Recording {duration:.1f} seconds from {device or 'the default microphone'}..."
        )
        record_audio(temporary, duration, device)
        report = inspect_audio(temporary)
        score_style = "green" if report.score >= 80 else "yellow" if report.score >= MIN_USABLE_REFERENCE_SCORE else "red"
        console.print(
            details_table(
                [
                    ("Quality", f"[{score_style}]{report.score}/100[/{score_style}]"),
                    ("Duration", f"{report.duration_seconds:.1f} sec"),
                    ("Silence", f"{report.silence_ratio:.0%}"),
                    ("Clipping", "Yes" if report.clipping_risk else "No"),
                ]
            )
        )
        for recommendation in report.recommendations:
            console.print(f"  [yellow]![/yellow] {recommendation}")
        if report.score < MIN_USABLE_REFERENCE_SCORE:
            temporary.unlink(missing_ok=True)
            raise VoiceError(
                f"Recording quality is too low ({report.score}/100). "
                "Adjust the microphone and try again."
            )
        existing = None
        try:
            existing = VoiceManager(paths).info(name)
        except VoiceError:
            pass
        if not yes and not typer.confirm(
            f"Save this recording to voice '{name}'" + (" as an additional reference" if existing else "") + "?",
            default=True,
        ):
            temporary.unlink(missing_ok=True)
            console.print("Recording was not saved.")
            return
        manager = VoiceManager(paths)
        stored = manager.add_reference(name, temporary) if existing else manager.add(name, temporary)
        temporary.unlink(missing_ok=True)
        console.print(
            f"[green]Recording saved.[/green] {stored.name} now has "
            f"{len(stored.reference_paths)} reference(s)."
        )

    _run_safely(action)


@config_app.command("show")
def config_show(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    def action() -> None:
        paths = AppPaths.discover()
        config = ConfigStore(paths).load()
        payload = asdict(config)
        if json_output:
            payload["config_file"] = str(paths.config_file)
            _print_json(payload, indent=2)
        else:
            console.print(json.dumps(payload, indent=2, ensure_ascii=False))
            console.print(f"\nConfig: {paths.config_file}")

    _run_safely(action)


@config_app.command("get")
def config_get(
    field: Annotated[str, typer.Argument(help="Configuration field name.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    def action() -> None:
        value = ConfigStore(AppPaths.discover()).get(field)
        if json_output:
            _print_json({"field": field, "value": value})
        else:
            console.print("null" if value is None else str(value))

    _run_safely(action)


@config_app.command("set")
def config_set(
    field: Annotated[str, typer.Argument(help="Configuration field name.")],
    value: Annotated[str, typer.Argument(help="New configuration value.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    def action() -> None:
        paths = AppPaths.discover()
        if field == "default_voice" and value.casefold() not in {"none", "null", ""}:
            VoiceManager(paths).info(value)
        config = ConfigStore(paths).set(field, value)
        current = getattr(config, field)
        if json_output:
            _print_json({"field": field, "value": current})
        else:
            console.print(f"{field} = {current}")

    _run_safely(action)


@app.command()
def doctor(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
) -> None:
    """Check local dependencies without downloading a model."""
    needs_attention = False

    def action() -> None:
        nonlocal needs_attention
        checks = run_diagnostics(AppPaths.discover())
        ready = not any(check.status == "error" for check in checks)
        needs_attention = not ready
        if json_output:
            _print_json({"ready": ready, "checks": [asdict(check) for check in checks]})
            return
        console.print("\n[bold]LLMVoice Doctor[/bold]\n")
        styles = {"ok": "green", "warning": "yellow", "error": "red"}
        for check in checks:
            symbol = status_symbol(console, check.status)
            styled_symbol = f"[{styles[check.status]}]{symbol}[/{styles[check.status]}]"
            console.print(
                details_table(
                    [(check.name, f"{styled_symbol} {check.detail}")]
                )
            )
            if check.hint:
                console.print(f"  [dim]{check.hint}[/dim]")
        console.print("\n[green]System ready.[/green]" if ready else "\nSystem needs attention.")

    _run_safely(action)
    if needs_attention:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
