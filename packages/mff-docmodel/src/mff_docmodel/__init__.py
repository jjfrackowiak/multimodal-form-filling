"""mff-docmodel — every conversion between Word documents and our types.

Both directions (`.docx` → types, types → `.docx`), both modes (derivative, net-new). No
AI, no network, no mutation of a client's document — see `compile_derivative` for the
promise that makes derivative mode honest, and `attach_comments` for the one place Word
comments are actually written.
"""

from __future__ import annotations

from .comments import attach_comments
from .compile import compile_derivative, compile_netnew
from .parse import parse_docx
from .scaffold import SCAFFOLD_SECTIONS, netnew_scaffold

__all__ = [
    "SCAFFOLD_SECTIONS",
    "attach_comments",
    "compile_derivative",
    "compile_netnew",
    "netnew_scaffold",
    "parse_docx",
]
