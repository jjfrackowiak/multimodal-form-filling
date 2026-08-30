"""Brief DoD 3: prove the *bare* install worked, rather than assuming it.

This test predates the move to ADK (it was written against `pydantic-ai`'s meta-package)
and is kept verbatim in spirit: `google-adk[extensions]`/`[all]` both bundle `anthropic`
and `openai`, so if either becomes importable in this service's environment, someone
widened `google-adk` to an extra it should not have — see the B8 brief, "Use bare
google-adk — no extras", and `pyproject.toml`'s `dependencies = ["google-adk>=2.8", ...]`.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize("module_name", ["openai", "anthropic"])
def test_banned_sdk_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_google_adk_and_genai_are_importable() -> None:
    """The base install itself must work — a suite full of skips would prove nothing."""
    import google.adk  # noqa: F401
    import google.genai  # noqa: F401
