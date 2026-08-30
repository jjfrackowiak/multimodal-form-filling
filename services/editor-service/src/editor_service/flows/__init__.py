"""Mode-specific editor flows."""

from __future__ import annotations

from editor_service.flows.derivative import DERIVATIVE_INSTRUCTION, review_derivative
from .netnew import NET_NEW_INSTRUCTION, compose_netnew

__all__ = [
	"DERIVATIVE_INSTRUCTION",
	"NET_NEW_INSTRUCTION",
	"compose_netnew",
	"review_derivative",
]
