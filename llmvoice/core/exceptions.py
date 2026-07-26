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

