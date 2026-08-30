"""`FakeLlm` — the ADK test double every model-touching branch uses in CI.

See `mff_fakes.fake_llm` for the design rationale and its trade-off.
"""

from .fake_llm import FakeLlm

__all__ = ["FakeLlm"]
