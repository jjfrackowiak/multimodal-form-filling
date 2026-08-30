"""A local test double for `RequirementExtractor`.

Not `FakeLlm` from `mff-fakes`: that class wraps ADK's `BaseLlm`, and `mff_manifest`
imports no model library — including from its own tests, so that
`tests/test_import_boundary.py` proves something real about the package's `sys.modules`
footprint rather than a footprint that only happened to hold because tests were exempt.
This is what the equivalent looks like on this side of the `RequirementExtractor`
boundary: scripted responses, no model call, no `google` import anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mff_contracts import Requirement

__all__ = ["ScriptedExtractor"]


@dataclass
class ScriptedExtractor:
    """Returns pre-built `Requirement` lists in order, one script entry per `extract` call.

    A script entry may be an `Exception` instead of a list, to exercise the retry loop
    (and the "raise once the cap is exhausted" path) without a network. `calls` records
    every `(chunk, offset)` it was asked about, for assertions.
    """

    script: Sequence[list[Requirement] | Exception]
    calls: list[tuple[str, int]] = field(default_factory=list)
    _next: int = field(default=0, init=False)

    async def extract(self, chunk: str, *, offset: int) -> list[Requirement]:
        self.calls.append((chunk, offset))
        if self._next >= len(self.script):
            raise AssertionError(
                f"ScriptedExtractor script exhausted after {self._next} calls "
                f"(script has {len(self.script)} entries)"
            )
        item = self.script[self._next]
        self._next += 1
        if isinstance(item, Exception):
            raise item
        return item
