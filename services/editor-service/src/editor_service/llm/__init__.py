"""ADK wiring — the only place in the repo that constructs a model client (B8).

`build_agent` + `run_slice` is what B6 (derivative review) and B7 (net-new composition)
call; `EditorDeps` is what they pass between them. `flows/` and `agents/` — the actual
prompts and per-mode tool factories — belong to those branches, not this one.
"""

from __future__ import annotations

from editor_service.llm.agent import build_agent
from editor_service.llm.deps import DEFAULT_SLICE_TOKEN_BUDGET, EditorDeps
from editor_service.llm.model import build_editor_model
from editor_service.llm.output import SliceTurnOutput
from editor_service.llm.plugins import UsagePlugin
from editor_service.llm.run import MAX_ATTEMPTS, run_slice

__all__ = [
    "DEFAULT_SLICE_TOKEN_BUDGET",
    "MAX_ATTEMPTS",
    "EditorDeps",
    "SliceTurnOutput",
    "UsagePlugin",
    "build_agent",
    "build_editor_model",
    "run_slice",
]
