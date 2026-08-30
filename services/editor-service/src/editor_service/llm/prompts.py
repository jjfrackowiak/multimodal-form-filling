"""The per-turn user message the retry loop sends — mechanical templating, not agent
instruction. The agent's persona and how to judge a requirement are B6/B7's `instruction`
string passed to `build_agent`; this module only ever restates *what* is still outstanding
and *why* the previous attempt did not settle it. Out of scope, deliberately: any text that
would need to change if the review policy changed.
"""

from __future__ import annotations

from mff_contracts import SliceRequest

__all__ = ["initial_prompt", "retry_prompt"]


def initial_prompt(req: SliceRequest) -> str:
    lines = [
        f"Answer the following {len(req.requirements)} requirement(s) for this slice. "
        "Every requirement must get exactly one comment: id, anchor, verdict, "
        "justification, and (only when the verdict is 'fail') a suggestion.",
    ]
    for requirement in req.requirements:
        constraint = (
            f"; constraint={requirement.constraint.kind}:{requirement.constraint.value}"
            if requirement.constraint is not None
            else ""
        )
        lines.append(
            f"- {requirement.id}: {requirement.text}; "
            f"expected_count={requirement.expected_count}{constraint}"
        )
    return "\n".join(lines)


def retry_prompt(pending: list[str], errors: dict[str, str]) -> str:
    lines = [
        "The previous attempt did not settle every requirement. Answer these again, "
        "fixing the problem noted for each:",
    ]
    for requirement_id in pending:
        detail = errors.get(requirement_id, "no comment was returned for this requirement")
        lines.append(f"- {requirement_id}: {detail}")
    return "\n".join(lines)
