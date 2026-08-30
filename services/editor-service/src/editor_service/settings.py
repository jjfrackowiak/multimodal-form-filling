"""Settings — the one place this service reads environment variables from.

Deliberately free of `google.adk` / `google.genai` imports: reading and validating strings
is free, constructing a model client is not. `/healthz` (see `api/routers/health.py`)
depends only on this module, never on `llm.model`, which is what keeps a health check from
ever costing a token or failing on a bad credential.

Auth is Application Default Credentials — see `.env.example`'s ADC section and the B8
brief. `google-genai` resolves credentials itself, in order: `GOOGLE_APPLICATION_CREDENTIALS`,
the gcloud ADC file, then the metadata server. Nothing here branches on which one wins, and
nothing here reads `GOOGLE_API_KEY` — that stale, blocked key is exactly the two-auth-path
problem the repo removed. `test_settings.py` asserts both of those as an invariant, not a
convention.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

__all__ = ["Settings", "SettingsError", "get_settings"]

# Pinned explicitly, never an alias — see the brief: an upstream default change would
# silently move every eval baseline, and under ADK it now moves a capability too.
_DEFAULT_EDITOR_MODEL_ID = "gemini-2.5-flash"
_DEFAULT_PARSER_MODEL_ID = "gemma-4-26b-a4b-it-maas"
_DEFAULT_LOCATION = "global"  # regional (us-central1) 404s for both models, verified live
_DEFAULT_SLICE_MAX_ATTEMPTS = 3
_DEFAULT_SLICE_TOKEN_BUDGET = 200_000  # generous placeholder; D5 (a per-job ceiling) is deferred


class SettingsError(ValueError):
    """Settings failed to construct — a missing/invalid value, never a network problem.

    Raised eagerly from `Settings.from_env()` so a missing `GOOGLE_CLOUD_PROJECT` fails
    loudly at construction (startup), not on the first model call three requests later.
    """


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything model construction needs, resolved once from the environment.

    Carries `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` for `google-genai` to read
    when it resolves ADC — this object never constructs a client itself, it only holds the
    values one will eventually need. See `llm.model.build_editor_model`.
    """

    google_cloud_project: str
    google_cloud_location: str = _DEFAULT_LOCATION
    google_genai_use_enterprise: bool = True
    editor_model_id: str = _DEFAULT_EDITOR_MODEL_ID
    parser_model_id: str = _DEFAULT_PARSER_MODEL_ID
    slice_max_attempts: int = _DEFAULT_SLICE_MAX_ATTEMPTS
    slice_token_budget: int = _DEFAULT_SLICE_TOKEN_BUDGET

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from `env` (defaults to `os.environ`).

        Validates only what can be validated without a network call: that a project id is
        present. It cannot check that ADC will actually resolve — that failure surfaces on
        the first model call, which is exactly why `/healthz` must never trigger one.
        """
        source: Mapping[str, str] = env if env is not None else os.environ

        project = source.get("GOOGLE_CLOUD_PROJECT", "").strip()
        if not project:
            raise SettingsError(
                "GOOGLE_CLOUD_PROJECT is not set. ADC needs a project to route requests "
                "to; see .env.example's ADC section. This must fail now, at settings "
                "construction, not later on the first model call."
            )

        location = source.get("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION).strip() or _DEFAULT_LOCATION
        use_enterprise = _parse_bool(
            source.get("GOOGLE_GENAI_USE_ENTERPRISE"), default=True
        )
        editor_model_id = source.get("EDITOR_MODEL_ID", "").strip() or _DEFAULT_EDITOR_MODEL_ID
        parser_model_id = source.get("PARSER_MODEL_ID", "").strip() or _DEFAULT_PARSER_MODEL_ID

        return cls(
            google_cloud_project=project,
            google_cloud_location=location,
            google_genai_use_enterprise=use_enterprise,
            editor_model_id=editor_model_id,
            parser_model_id=parser_model_id,
        )


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, resolved once. Cached because construction is pure and cheap
    (string parsing only) — never because it is expensive."""
    return Settings.from_env()
