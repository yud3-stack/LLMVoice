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
from llmvoice.cli_output import (
    details_table,
    render_created,
    render_start_summary,
    render_voice_added,
    render_voice_info,
    render_voice_list,
    status_symbol,
)
from llmvoice.core.config import MAX_SPEED, MIN_SPEED, ConfigStore
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
from llmvoice.voices.manager import RECOMMENDED_MAX_SECONDS, VoiceManager

console = Console()
error_console = Console(stderr=True)

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
app.add_typer(voice_app, name="voice")
app.add_typer(config_app, name="config")


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


def _run_safely(action: Callable[[], None], debug: bool = False) -> None:
    try:
        action()
    except KeyboardInterrupt:
        error_console.print(
            "\nGeneration cancelled.\n\nTemporary files were cleaned up.",
            markup=False,
        )
        raise typer.Exit(code=130) from None
    except LLMVoiceError as exc:
        if debug:
            error_console.print_exception(show_locals=False)
        else:
            error_console.print(f"Error: {exc}", markup=False)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        if debug:
            error_console.print_exception(show_locals=False)
        else:
            error_console.print(
                f"Error: Unexpected failure: {exc}\n\n"
                "Run the same command with --debug for a stack trace.",
                markup=False,
            )
        raise typer.Exit(code=1) from None


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
        voice_path = manager.resolve(selected_voice)

        destination = output_path_for(input_path, output)
        if destination.suffix.casefold() != ".mp3":
            raise LLMVoiceError("Output path must end with .mp3.")
        if not dry_run:
            ensure_output_available(destination, force)

        selected_speed = speed if speed is not None else config.default_speed
        device = resolve_device(config.device)
        estimated_seconds = estimate_speech_seconds(plan.text)

        render_start_summary(
            console,
            version=__version__,
            input_path=input_path,
            voice=selected_voice,
            voice_is_default=voice_is_default,
            language=plan.language,
            auto_detected=plan.auto_detected,
            device=device.label,
            engine=engine_display_name(config.engine),
            output_path=destination,
            characters=len(plan.text),
            chunks=len(plan.chunks),
            estimated_seconds=estimated_seconds,
            dry_run=dry_run,
        )
        if device.kind == "cpu" and config.device == "auto":
            console.print(
                "[yellow]Warning:[/yellow] CUDA was not detected. "
                "Long-form generation may be significantly slower.\n"
            )
        if dry_run:
            console.print("No audio was generated.")
            return

        require_ffmpeg()
        engine = create_engine(config.engine, device.kind, paths)
        check_synthesis_disk_space(paths.cache_dir, destination, estimated_seconds)
        if not getattr(engine, "is_model_installed", True):
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
                    language=plan.language,
                    speed=selected_speed,
                ),
                plan=plan,
                progress=on_progress,
                stage=stage,
            )
        finally:
            stop_status()
            if task_id is not None:
                progress.stop()
        render_created(console, destination, probe_audio(destination))

    _run_safely(action, debug=debug)


@voice_app.command("add")
def voice_add(
    name: Annotated[str, typer.Argument(help="Name used by --voice.")],
    audio_file: Annotated[Path, typer.Argument(help="Reference audio file.")],
) -> None:
    def action() -> None:
        stored = VoiceManager(AppPaths.discover()).add(name, audio_file)
        render_voice_added(console, stored)
        if stored.metadata.duration_seconds > RECOMMENDED_MAX_SECONDS:
            console.print(
                "\n[yellow]Warning:[/yellow] Long reference audio detected.\n"
                "Recommended reference length is approximately 6–30 seconds."
            )

    _run_safely(action)


@voice_app.command("list")
def voice_list() -> None:
    _run_safely(
        lambda: render_voice_list(
            console,
            VoiceManager(AppPaths.discover()).list(),
        )
    )


@voice_app.command("info")
def voice_info(
    name: Annotated[str, typer.Argument(help="Stored voice name.")],
) -> None:
    _run_safely(
        lambda: render_voice_info(
            console,
            VoiceManager(AppPaths.discover()).info(name),
        )
    )


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


@config_app.command("show")
def config_show() -> None:
    def action() -> None:
        paths = AppPaths.discover()
        config = ConfigStore(paths).load()
        console.print(json.dumps(asdict(config), indent=2, ensure_ascii=False))
        console.print(f"\nConfig: {paths.config_file}")

    _run_safely(action)


@config_app.command("get")
def config_get(
    field: Annotated[str, typer.Argument(help="Configuration field name.")],
) -> None:
    def action() -> None:
        value = ConfigStore(AppPaths.discover()).get(field)
        console.print("null" if value is None else str(value))

    _run_safely(action)


@config_app.command("set")
def config_set(
    field: Annotated[str, typer.Argument(help="Configuration field name.")],
    value: Annotated[str, typer.Argument(help="New configuration value.")],
) -> None:
    def action() -> None:
        paths = AppPaths.discover()
        if field == "default_voice" and value.casefold() not in {"none", "null", ""}:
            VoiceManager(paths).info(value)
        config = ConfigStore(paths).set(field, value)
        console.print(f"{field} = {getattr(config, field)}")

    _run_safely(action)


@app.command()
def doctor() -> None:
    """Check local dependencies without downloading a model."""
    needs_attention = False

    def action() -> None:
        nonlocal needs_attention
        checks = run_diagnostics(AppPaths.discover())
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
        ready = not any(check.status == "error" for check in checks)
        needs_attention = not ready
        console.print("\n[green]System ready.[/green]" if ready else "\nSystem needs attention.")

    _run_safely(action)
    if needs_attention:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
