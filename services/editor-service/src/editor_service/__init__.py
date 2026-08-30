"""editor-service — the only service that constructs a model client (req 13's counterpart
on the review side; see docs/briefs/CONTEXT.md).

B8 (this branch) wires ADK: `llm.build_agent` + `llm.run_slice`, `settings.Settings`, and
the `/slices:run` / `/healthz` HTTP surface. `flows/` and `agents/` — the actual review and
composition prompts — belong to B6 and B7.
"""

from __future__ import annotations

__all__: list[str] = []
