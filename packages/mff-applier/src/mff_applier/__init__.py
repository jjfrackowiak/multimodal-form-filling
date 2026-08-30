"""mff-applier — req 14 (surgical edits, no full regeneration), req 15 (apply the edits).

The one place a validated `SliceReport` becomes changes to an `Artifact`. Pure functions
over `(Artifact, SliceReport) -> Artifact`-shaped data: no I/O, no model, no async.
"""

from __future__ import annotations

from .apply import apply_slice
from .models import ApplyResult, Overwrite, Rejection
from .ordering import key_after, key_before, key_between

__all__ = [
    "ApplyResult",
    "Overwrite",
    "Rejection",
    "apply_slice",
    "key_after",
    "key_before",
    "key_between",
]
