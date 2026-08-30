# Subagent briefs

One brief per branch. Each is the complete specification for one agent working in an
isolated worktree, and each names the directories it owns so ten can run without colliding.

`docs/app-implementation-plan.md` is the design; these are the work orders.

## Order

**Layer 0 — must merge before anything else**

| | Branch | Owns |
|---|---|---|
| [B0](B0-scaffold-contracts.md) | `feat/scaffold-contracts` | workspace, CI, **frozen `mff-contracts`** |

**Layer 1 — all ten branch from B0 and run in parallel**

| | Branch | Owns | Needs a key? |
|---|---|---|---|
| [B14](B14-applier.md) | `feat/applier` | `mff-applier` — pure functions | no |
| [B1](B1-docmodel.md) | `feat/docmodel` | `mff-docmodel` — docx ⇄ our types | no |
| [B12](B12-state-store.md) | `feat/state-store` | `mff-store` — in-memory + Firestore/GCS | no |
| [B2](B2-manifest.md) | `feat/manifest` | `mff-manifest` — text → `Requirement[]` | live eval only |
| [B4](B4-mail-transport.md) | `feat/mail-transport` | IMAP/SMTP + the in-memory fake | no |
| [B3](B3-intake.md) | `feat/intake` | intake rules, both reply templates | no |
| [B5](B5-orchestrator.md) | `feat/orchestrator` | the runner, sequencing, the barrier | no |
| [B13](B13-delivery.md) | `feat/delivery` | the results email | no |
| [B8](B8-llm-config.md) | `feat/llm-config` | Gemini wiring, `/slices:run`, the retry loop | smoke test only |
| [B10](B10-docker.md) | `feat/docker` | images and compose | no |

**Layer 2 — needs B1, B14, B8**

B6 `feat/flow-derivative`, B7 `feat/flow-netnew` — the two agents. Briefs to follow.

**Layer 3** — B9 `feat/fleet-example`, the end-to-end demo.

## Rules every brief inherits

**`mff-contracts` is frozen.** No branch edits it. A change request goes in the PR
description and comes back through the layer-0 owner. Ten branches depend on that shape.

**Own your directories, nothing else.** The disjoint-ownership table is what makes ten
concurrent PRs safe. Worktree isolation handles the filesystem; this handles the merge.

**No live model calls in CI.** `TestModel` or `FunctionModel`. Live evals go behind an env
flag and run manually, with their baseline recorded in the package README.

**No LLM-as-judge.** `pydantic_evals.evaluators.LLMJudge` is banned by a ruff rule, and it
will fail lint rather than review. Every evaluator here is structural: the pipeline is
non-deterministic, whether its output is complete is not.

**Mutation-test your evaluator.** An evaluator that has only seen correct output may be
asserting nothing. Break your own golden output in at least three ways and show each being
caught. This is not hypothetical — it has already found three checkers in this repo that
silently asserted nothing, including one in the fixture's own suite.

**Report what the spec got wrong.** A brief that seemed ambiguous, a contract that could
not express what you needed, an instruction that turned out to be unimplementable. B0's
report caught an `import-linter` rule of mine that would have blocked every eval suite in
the repo. That is worth more than a clean report.
