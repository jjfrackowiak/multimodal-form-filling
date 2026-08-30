"""`SliceRunner` — the seam that keeps the editor service (HTTP, the model) out of the
orchestrator's own tests. `protocol.py` declares the shape; `fake.py` is the double
this branch — and B9's end-to-end test — run the orchestrator against instead.
"""

from __future__ import annotations

from .fake import FakeSliceRunner
from .protocol import SliceRunner

__all__ = ["FakeSliceRunner", "SliceRunner"]
