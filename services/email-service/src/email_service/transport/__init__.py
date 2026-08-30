"""Mail transport. B4 owns the protocol and its implementations."""

from .messages import Attachment, InboundMessage, OutboundMessage

__all__ = ["Attachment", "InboundMessage", "OutboundMessage"]
