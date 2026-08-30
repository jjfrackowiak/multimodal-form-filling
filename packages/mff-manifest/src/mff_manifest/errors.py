"""Errors raised by manifest parsing.

Both are hard failures, never a lower score. `parse_manifest` produces a well-formed
`Manifest` or raises — never a silently truncated requirement list, and never a
requirement whose provenance does not check out.
"""

from __future__ import annotations

__all__ = ["ManifestParseError", "NonVerbatimSpanError"]


class NonVerbatimSpanError(ValueError):
    """A `source_span` — a requirement's or its constraint's — was not a verbatim
    substring of the raw manifest text.

    The one structural failure `parse_manifest` retries on: ADK ships no
    `output_validator`/`ModelRetry` pair, so this is the explicit, plain-Python stand-in
    for that check.
    """

    def __init__(self, span: str) -> None:
        self.span = span
        super().__init__(f"source_span is not verbatim in the manifest: {span!r}")


class ManifestParseError(RuntimeError):
    """The extractor could not be coaxed into a structurally valid response.

    Raised once the retry cap is exhausted. The caller gets this or a well-formed
    `Manifest` — never a partial one and never a silent truncation.
    """
