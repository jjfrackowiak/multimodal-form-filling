"""Pins the constraint that matters most on this branch: intake.py and replies.py must
never import a model library. The parser is non-deterministic (it has a model in it);
if this module produced or re-derived the requirement list, req 7's promise — the list
the client sees is the list their document is graded against — would be silently
false.

`import-linter`'s "no module outside llm/ and agents/ imports a model library" contract
(`pyproject.toml`) already enforces this at the workspace level via `make check imports`
— this test pins it specifically for the two modules this branch owns, and does not
depend on `lint-imports` being run.
"""

from __future__ import annotations

import ast
from pathlib import Path

import email_service.intake
import email_service.replies

_BANNED_TOP_LEVEL_MODULES = {
    "google",  # google.adk (agents) and google.genai (the model SDK underneath it)
    "pydantic_ai",
    "anthropic",
    "openai",
    "vertexai",
    "litellm",
}


def _imported_top_level_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def test_intake_module_imports_no_model_library() -> None:
    source = Path(email_service.intake.__file__).read_text(encoding="utf-8")
    found = _imported_top_level_modules(source) & _BANNED_TOP_LEVEL_MODULES
    assert found == set(), f"intake.py imports a model library: {found}"


def test_replies_module_imports_no_model_library() -> None:
    source = Path(email_service.replies.__file__).read_text(encoding="utf-8")
    found = _imported_top_level_modules(source) & _BANNED_TOP_LEVEL_MODULES
    assert found == set(), f"replies.py imports a model library: {found}"


def test_google_adk_is_not_even_installed_as_a_transitive_dependency_of_this_import() -> None:
    """Belt and braces: after importing both modules, `google.adk` must not have been
    pulled into `sys.modules` by anything in their import graph."""
    import sys

    assert "google.adk" not in sys.modules
    assert "pydantic_ai" not in sys.modules
