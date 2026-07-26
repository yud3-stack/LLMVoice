class LLMVoiceError(Exception):
    """Base exception for expected, user-facing failures."""


class ConfigurationError(LLMVoiceError):
    """Configuration is invalid or cannot be read."""


class InputFileError(LLMVoiceError):
    """Input transcript is missing or invalid."""


class VoiceError(LLMVoiceError):
    """A voice cannot be stored or resolved."""


class EngineError(LLMVoiceError):
    """The TTS engine cannot load or synthesize."""


class AudioToolError(LLMVoiceError):
    """FFmpeg/FFprobe is unavailable or audio processing failed."""


class OutputExistsError(LLMVoiceError):
    """The requested output would overwrite an existing file."""


class DiskSpaceError(LLMVoiceError):
    """There is not enough free disk space for a synthesis job."""


class SpeechGenerationError(LLMVoiceError):
    """A specific speech chunk failed during synthesis."""

    def __init__(self, chunk: int, total: int) -> None:
        self.chunk = chunk
        self.total = total
        super().__init__(
            "Speech generation failed.\n\n"
            f"Chunk: {chunk} / {total}\n\n"
            "Run again with --debug for technical details."
        )
