"""Stage 2 of manifest parsing: the model-backed extractor.

`mff_manifest` owns the deterministic scaffolding — pre-split, span validation, retry,
canonical ordering — and depends on this Protocol for the one non-deterministic step:
turning a chunk of free text into the discrete requirements it names. The implementation
(an ADK agent prompting Gemma for JSON — Gemma has no native structured-output mode, so a
real extractor prompts and validates the result itself) lives in the editor service, which
owns all model access. `mff_manifest` imports no agent framework and no model library —
enforced by the workspace import-linter contract and by
`tests/test_import_boundary.py`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mff_contracts import Requirement

__all__ = ["RequirementExtractor"]


@runtime_checkable
class RequirementExtractor(Protocol):
    """Turns one chunk of manifest text into the requirements it names.

    `offset` is the chunk's character position within the manifest's raw text. An
    extractor may use it, but nothing downstream depends on it being right:
    `parse_manifest` never trusts a returned `ordinal`, `source_line` or `id` — it
    recomputes all three from `source_span` against the full raw text. That is also why
    the only thing worth re-asking about is a `source_span` that turns out not to be
    verbatim; everything else recovers deterministically.

    May raise on failure (a bad JSON response, an unreachable model). `parse_manifest`
    retries only its own concern — a non-verbatim `source_span` — and lets any other
    exception propagate to the caller.
    """

    async def extract(self, chunk: str, *, offset: int) -> list[Requirement]: ...
