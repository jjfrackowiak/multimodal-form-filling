"""Brief DoD 8: `GOOGLE_API_KEY` is never read, and a missing `GOOGLE_CLOUD_PROJECT` fails
loudly at construction — not on the first model call."""

from __future__ import annotations

import inspect

import pytest

from editor_service import settings as settings_module
from editor_service.settings import Settings, SettingsError, get_settings


def test_missing_project_fails_at_construction() -> None:
    with pytest.raises(SettingsError, match="GOOGLE_CLOUD_PROJECT"):
        Settings.from_env({})


def test_blank_project_also_fails() -> None:
    with pytest.raises(SettingsError):
        Settings.from_env({"GOOGLE_CLOUD_PROJECT": "   "})


def test_google_api_key_is_never_read_even_when_set() -> None:
    """A stale GOOGLE_API_KEY in the environment (see .env.example) must have zero effect:
    no attribute carries it, and settings construction does not fail or change behaviour
    because of it."""
    env = {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_API_KEY": "stale-blocked-key"}
    settings = Settings.from_env(env)
    assert settings.google_cloud_project == "test-project"
    assert not hasattr(settings, "google_api_key")
    assert not hasattr(settings, "api_key")


def test_settings_source_never_reads_google_api_key() -> None:
    """Belt and braces: the module's source never *reads* the variable (a `.get(` call
    naming it), so a future refactor cannot quietly reintroduce it as a fallback. The name
    may still appear in comments/docstrings explaining that it is deliberately not read."""
    source = inspect.getsource(settings_module)
    assert 'get("GOOGLE_API_KEY"' not in source
    assert "get('GOOGLE_API_KEY'" not in source


def test_defaults_are_the_pinned_model_ids_and_global_location() -> None:
    settings = Settings.from_env({"GOOGLE_CLOUD_PROJECT": "test-project"})
    assert settings.editor_model_id == "gemini-2.5-flash"
    assert settings.parser_model_id == "gemma-4-26b-a4b-it-maas"
    assert settings.google_cloud_location == "global"
    assert settings.google_genai_use_enterprise is True


def test_env_overrides_model_ids_and_location() -> None:
    env = {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_LOCATION": "us-central1",
        "EDITOR_MODEL_ID": "gemini-9000",
        "PARSER_MODEL_ID": "gemma-9000",
        "GOOGLE_GENAI_USE_ENTERPRISE": "false",
    }
    settings = Settings.from_env(env)
    assert settings.google_cloud_location == "us-central1"
    assert settings.editor_model_id == "gemini-9000"
    assert settings.parser_model_id == "gemma-9000"
    assert settings.google_genai_use_enterprise is False


def test_get_settings_reads_process_env_and_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "cached-project")
    first = get_settings()
    assert first.google_cloud_project == "cached-project"
    # Cached: changing the environment after the first call has no effect until cleared.
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "different-project")
    assert get_settings() is first
    get_settings.cache_clear()


def test_get_settings_without_project_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(SettingsError):
        get_settings()
    get_settings.cache_clear()
