from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn

from llmvoice import __version__
from llmvoice.audio.ffmpeg import require_ffmpeg
from llmvoice.core.config import MAX_SPEED, MIN_SPEED, ConfigStore
from llmvoice.core.exceptions import LLMVoiceError, VoiceError
from llmvoice.core.paths import AppPaths
from llmvoice.service import SynthesisRequest, VoiceService, output_path_for, read_and_plan
from llmvoice.tts.device import resolve_device
from llmvoice.tts.factory import create_engine
from llmvoice.voices.manager import VoiceManager

console = Console()
error_console = Console(stderr=True)
app = typer.Typer(
    name="llmvoice",
    help="Fully local/offline long-form voice cloning.",
    no_args_is_help=True,
    rich_markup_mode=None,
)
voice_app = typer.Typer(help="Manage stored voice references.", no_args_is_help=True)
config_app = typer.Typer(help="Inspect LLMVoice configuration.", no_args_is_help=True)
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
    except LLMVoiceError as exc:
        if debug:
            raise
        error_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from None
    except Exception as exc:
        if debug:
            raise
        error_console.print(
            f"[bold red]Error:[/bold red] Unexpected failure: {exc}\n"
            "Run the same command with --debug for a stack trace."
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
    debug: Annotated[bool, typer.Option("--debug", help="Show debug logs and stack traces.")] = False,
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
        selected_language = language or config.default_language
        plan = read_and_plan(input_path, selected_language, config.chunk_size)

        selected_voice = voice or config.default_voice
        if not selected_voice:
            raise VoiceError(
                "No voice was selected and 'default_voice' is not configured.\n\n"
                "Run:\nllmvoice voice list"
            )

        destination = output_path_for(input_path, output)
        if destination.suffix.casefold() != ".mp3":
            raise LLMVoiceError("Output path must end with .mp3.")
        selected_speed = speed if speed is not None else config.default_speed
        voice_path = manager.resolve(selected_voice)
        require_ffmpeg()
        device = resolve_device(config.device)
        engine = create_engine(config.engine, device.kind, paths)

        console.print(f"\n[bold]LLMVoice v{__version__}[/bold]\n")
        console.print(f"Input     : {input_path}")
        console.print(f"Voice     : {selected_voice}")
        console.print(f"Language  : {plan.language}")
        console.print(f"Device    : {device.label}")
        console.print(f"Engine    : {engine.display_name}")
        console.print(f"Output    : {destination}\n")
        console.print(f"Text      : {len(plan.text):,} characters")
        console.print(f"Chunks    : {len(plan.chunks)}\n")

        progress_bar = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        )
        task_id: int | None = None

        def stage(name: str) -> None:
            labels = {
                "preparing_reference": "Preparing voice reference...",
                "loading_model": "Loading voice model (first run may download it)...",
                "model_loaded": "Voice model loaded.",
                "merging": "Merging audio...",
                "encoding": "Encoding MP3...",
            }
            console.print(labels[name])

        def on_progress(current: int, total: int) -> None:
            nonlocal task_id
            if task_id is None:
                progress_bar.start()
                task_id = progress_bar.add_task("Generating", total=total)
            progress_bar.update(task_id, completed=current)
            if current == total:
                progress_bar.stop()

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
            if task_id is not None:
                progress_bar.stop()
        console.print(f"\n[bold green]Done.[/bold green]\n\nOutput:\n{destination}")

    _run_safely(action, debug=debug)


@voice_app.command("add")
def voice_add(
    name: Annotated[str, typer.Argument(help="Name used by --voice.")],
    audio_file: Annotated[Path, typer.Argument(help="Reference audio file.")],
) -> None:
    def action() -> None:
        destination = VoiceManager(AppPaths.discover()).add(name, audio_file)
        console.print(f"Voice '{name}' added.\n{destination}")

    _run_safely(action)


@voice_app.command("list")
def voice_list() -> None:
    def action() -> None:
        voices = VoiceManager(AppPaths.discover()).list()
        console.print("Available voices:\n")
        console.print("\n".join(voices) if voices else "(none)")

    _run_safely(action)


@voice_app.command("remove")
def voice_remove(
    name: Annotated[str, typer.Argument(help="Stored voice name.")],
) -> None:
    def action() -> None:
        VoiceManager(AppPaths.discover()).remove(name)
        console.print(f"Voice '{name}' removed.")

    _run_safely(action)


@config_app.command("show")
def config_show() -> None:
    def action() -> None:
        paths = AppPaths.discover()
        config = ConfigStore(paths).load()
        from dataclasses import asdict

        console.print(json.dumps(asdict(config), indent=2, ensure_ascii=False))
        console.print(f"\nConfig: {paths.config_file}")

    _run_safely(action)


if __name__ == "__main__":
    app()
