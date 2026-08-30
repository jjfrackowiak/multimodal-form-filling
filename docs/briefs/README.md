# Subagent briefs

One brief per branch. Each is the complete specification for one agent working in an
isolated worktree, and each names the directories it owns so ten can run without colliding.

`docs/app-implementation-plan.md` is the design; these are the work orders.
**[`CONTEXT.md`](CONTEXT.md)** is the shared preamble every brief assumes — read it once.

## Order

**Layer 0 — must merge before anything else**

| | Branch | Owns |
|---|---|---|
| [B0](B0-scaffold-contracts.md) | `feat/scaffold-contracts` | workspace, CI, **frozen `mff-contracts`** |

**Layer 0.5 — one small PR, blocks every branch that touches a model**

| | Branch | Owns |
|---|---|---|
| [B15](B15-fakes.md) | `feat/fakes` | `mff-fakes` — `FakeLlm`, the ADK test double |

Pydantic AI shipped `TestModel`/`FunctionModel`; ADK ships no supported equivalent, so we
own one. B2, B6, B7 and B8 all need it, and four private copies is exactly the drift the
ownership table exists to prevent.

**Layer 1 — ten branches, but not ten-wide. See the dependency note below.**

| | Branch | Owns | Needs a key? |
|---|---|---|---|
| [B14](B14-applier.md) | `feat/applier` | `mff-applier` — pure functions | no |
| [B1](B1-docmodel.md) | `feat/docmodel` | `mff-docmodel` — docx ⇄ our types | no |
| [B12](B12-state-store.md) | `feat/state-store` | `mff-store` — in-memory + Firestore/GCS | no |
| [B2](B2-manifest.md) | `feat/manifest` | `mff-manifest` — text → `Requirement[]` (needs B15) | live eval only |
| [B4](B4-mail-transport.md) | `feat/mail-transport` | IMAP/SMTP + the in-memory fake | no |
| [B3](B3-intake.md) | `feat/intake` | intake rules, both reply templates | no |
| [B5](B5-orchestrator.md) | `feat/orchestrator` | the runner, sequencing, the barrier | no |
| [B13](B13-delivery.md) | `feat/delivery` | the results email | no |
| [B8](B8-llm-config.md) | `feat/llm-config` | ADK + Gemini wiring, `/slices:run`, the retry loop (needs B15) | smoke test only |
| [B10](B10-docker.md) | `feat/docker` | images and compose | no |

### Dispatch order

An earlier version of this page called Layer 1 "fully parallel". That was wrong, and two
couplings are real:

**`InboundMessage` / `OutboundMessage` are defined in B4**, and both B3 and B13 consume
them. Starting those before B4 lands means two branches inventing the same types.

**`services/email-service/pyproject.toml` is one file that B3, B4, B5 and B13 all need to
edit** to add their dependencies. That conflict is unavoidable; keep each edit to one line.

```
wave 0   B15                           the ADK test double, ~60 lines; unblocks B2 and B8
wave 1   B14  B1  B12  B2  B10        genuinely independent — own package only
wave 2   B4                            defines the transport types
wave 3   B3  B13  B5                   consume them; B5 also wants B12/B14/B1 stubs
```

B5 can start in wave 1 against Protocols alone if you want it early — it is designed to
test with a fake runner and no other service — but its integration tests want the real
adapters.

**Layer 2 — needs B1, B14, B8**

B6 `feat/flow-derivative`, B7 `feat/flow-netnew` — the two agents. Briefs to follow.

**Layer 3** — B9 `feat/fleet-example`, the end-to-end demo.

## Rules every brief inherits

**`mff-contracts` is frozen.** No branch edits it. A change request goes in the PR
description and comes back through the layer-0 owner. Ten branches depend on that shape.

**Own your directories, nothing else.** The disjoint-ownership table is what makes ten
concurrent PRs safe. Worktree isolation handles the filesystem; this handles the merge.

**No live model calls in CI.** `FakeLlm` from `mff-fakes` (B15). Live evals go behind an
env flag and run manually, with their baseline recorded in the package README.

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
