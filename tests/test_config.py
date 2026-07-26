import json

import pytest

from llmvoice.core.config import AppConfig, ConfigStore
from llmvoice.core.exceptions import ConfigurationError
from llmvoice.core.paths import AppPaths


def test_creates_default_config(tmp_path) -> None:
    store = ConfigStore(AppPaths(tmp_path / "data"))
    config = store.load()
    assert config.default_language == "tr"
    assert config.default_speed == 1.0
    assert store.paths.config_file.exists()


def test_loads_config_and_ignores_future_fields(tmp_path) -> None:
    paths = AppPaths(tmp_path / "data")
    paths.ensure()
    paths.config_file.write_text(
        json.dumps({"default_voice": "friday", "device": "cpu", "future": True}),
        encoding="utf-8",
    )
    config = ConfigStore(paths).load()
    assert config.default_voice == "friday"
    assert config.device == "cpu"


def test_rejects_invalid_config(tmp_path) -> None:
    paths = AppPaths(tmp_path / "data")
    paths.ensure()
    paths.config_file.write_text('{"device": "quantum"}', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="device"):
        ConfigStore(paths).load()


def test_rejects_invalid_speed() -> None:
    with pytest.raises(ConfigurationError, match="default_speed"):
        AppConfig(default_speed=5.0).validate()


def test_rejects_wrong_config_type(tmp_path) -> None:
    paths = AppPaths(tmp_path / "data")
    paths.ensure()
    paths.config_file.write_text('{"default_speed": "fast"}', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="default_speed"):
        ConfigStore(paths).load()


def test_config_store_get_set_and_reject_unknown(tmp_path) -> None:
    store = ConfigStore(AppPaths(tmp_path / "data"))
    updated = store.set("chunk_pause_ms", "120")
    assert updated.chunk_pause_ms == 120
    assert store.get("chunk_pause_ms") == 120
    with pytest.raises(ConfigurationError, match="Unknown config field"):
        store.set("missing", "1")
