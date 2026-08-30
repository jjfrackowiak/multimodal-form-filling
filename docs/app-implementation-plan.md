# Email Form Validation — AI Editor + Email Service

## Context

`multimodal-form-filling/email-form-validation-requirements.pdf` (17 numbered requirements + 3 open concerns) specifies an email-driven form validation app. Our scope is **Part 1 (email server layer)** and **Part 2 (AI editor)** — GCP deployment is someone else's, but every service we ship must be containerised so they can take it.

The repo is currently empty (README + PDF only). This plan lays down a scaffold plus a set of **branch-sized tasks that Sonnet subagents can execute in parallel and raise PRs from**.

Decisions locked with the user:

| Question | Decision |
|---|---|
| Email transport | IMAP poll (inbound) + SMTP send (outbound) |
| Locked/editable regions | Agent-derived on the first run, stored in artifact state |
| Service boundary | Two services over HTTP, frozen contracts package between them |
| Word comments | `python-docx` native comments (`document.add_comment`) |

Not in scope for v1: image tooling (req 13) ships as a **stubbed interface only** — the real cropping/understanding module comes later; OCR/PDF input (D1); job status polling (D2); cross-requirement conflict detection (D3).

## Framework grounding (verified against current docs)

- **Programmatic hand-off** (req 11) is a Pydantic AI documented pattern: agents called in succession from *plain Python*, each run scoped to its own requirement slice, context carried by `message_history=` and shared `deps`/`usage`. There is no graph DSL needed — the "state machine" is our own explicit loop.
- **Shared state** (req 12) = a `deps` dataclass holding the `Artifact` python object. Tools mutate it in place; it outlives every run.
- **Gemini**: `GoogleModel(<model-id>, provider=GoogleProvider(api_key=...))`, plus `HttpRetryOptions` for transport-level retry and `UsageLimits` per slice.
- **Validation/retry** (reqs 16–17): `@agent.output_validator` raising `ModelRetry` handles cheap in-run structural fixes; the **3-attempt cap and the mark-unverified terminal state live in our outer loop**, because req 17 requires a durable terminal outcome, not an exception.
- **Evals**: `pydantic-evals` ships with Pydantic AI — `Case`/`Dataset`/`Evaluator`, plus built-in `LLMJudge`, `IsInstance`, `Contains` and **`MaxDuration(seconds=...)`**. `EvaluatorContext` exposes `ctx.duration`, `ctx.metrics` and `ctx.span_tree`, so correctness, latency and token cost all come out of a single run. Agents are `pydantic-ai`; evals are `pydantic-evals`.
- **Comments**: `document.add_comment(runs=..., text=..., author=..., initials=...)` and `document.comments` are supported in `python-docx` ≥ 1.2.

## Architecture

### Email layer (`email-service`)

```mermaid
flowchart TD
    IMAP["inbound IMAP"] --> ES["email-service"]
    ES --> IV{"intake validation<br/>req 6"}
    IV -->|invalid| BAD["SMTP reply:<br/>exactly what is missing<br/>req 8"]
    IV -->|valid| JOB["POST /jobs<br/>manifest_raw + forms"]
    JOB --> ED["editor-service parses the manifest<br/>req 5"]
    ED --> ACC["202 Accepted<br/>returns Requirement[]"]
    ACC --> ACK["SMTP reply: handed over<br/>+ that exact requirement list<br/>req 7"]
    ACC --> RUN["job continues async"]
    RUN -.-> CB["editor calls back on completion"]
    CB --> DEL["SMTP reply: reviewed documents<br/>+ pass/fail summary + unverified<br/>req 10"]
```

### The email service has two roles, not one

This is easy to under-plan, and the first draft of this document did exactly that —
it stopped at the confirmation and never delivered anything back.

**Role 1 — intake, synchronous.** Receive, validate, hand off, confirm. Everything above.

**Role 2 — delivery, asynchronous.** The job finishes minutes later in another service.
Something has to put the reviewed Word documents in front of the client, and req 10
says that output *is* the product. Without this leg the system does nothing useful.

The two roles have almost nothing in common: different triggers (an inbound message vs.
a completed job), different failure modes, different idempotency keys. They share only
the transport. That is why delivery is its own branch (**B13**) rather than more surface
area on intake.

**How delivery is triggered.** The editor calls back to the email service on completion,
and the email service *also* sweeps for jobs that have been in flight too long. Callback
alone loses jobs whenever the email service is restarting; polling alone adds latency to
every job. The sweep costs little because `JobRecord` already exists for D2, and it makes
a dropped callback recoverable instead of fatal.

**What the delivery email must carry**, beyond the attachments:

- a pass/fail summary, so the client knows the outcome without opening the documents
- **any requirement marked `unverified`**, called out explicitly. This is where req 17
  becomes visible to a human: the system gave up after three attempts and the client
  must be told which checks were never completed rather than left to infer it.
- on outright failure, a message saying so — which is most of concern **D2** answered
  almost for free, once this leg exists at all.

**Threading.** The delivery reply sets `In-Reply-To` / `References` against the
**original client message**, not against the confirmation, so request → confirmation →
results reads as one conversation.

**Attachment size is a real constraint, not a detail.** The fleet fixture's single
reviewed document is 2.8 MB with 17 embedded photos. A request carrying several forms
clears typical limits quickly — Gmail refuses at 25 MB and many corporate servers at 10.
Delivery therefore attaches below a configured threshold and otherwise sends a signed
link to the object in the bucket. The documents already live in GCS as `BlobRef`s, so the
link costs nothing extra.

**Idempotency.** A callback that fires twice, or a callback plus the sweep catching the
same job, must not send the client two copies. Keyed on `job_id`, with delivery recorded
on the job record before the send is acknowledged.

**The manifest is parsed exactly once, by the editor, and the list travels back.**
That ordering is forced by req 7: the confirmation reply has to contain the parsed
requirements, so the email service cannot send it until the parse exists.

The tempting alternative — the email service parses for the reply, the editor parses
again for the run — is a **silent correctness bug**. The parser has a model in it
(see below), so it is not deterministic: two parses of the same manifest can yield
different requirement sets. The client would then be shown one list while the document
is graded against another, destroying the exact thing req 7 exists to provide. Parse
once, return it, store it, never re-derive.

Keeping the parse in the editor also keeps **all model credentials in one service**.
The email layer never talks to Gemini.

### Orchestration layer

The `email-service` is not only a mail gateway — it is the **orchestrator**. It owns the
job, plans the slices, fans them out to editor instances running in parallel, collects
and validates what comes back, and applies the results to one document.

```mermaid
flowchart TD
    P["PARSE_MANIFEST → Requirement[]"] --> PLAN["PLAN SLICES<br/>disjoint requirement sets"]
    PLAN --> SEED["SEED ARTIFACT<br/>parse docx, or generate scaffold"]
    SEED --> F1["editor instance<br/>slice A"]
    SEED --> F2["editor instance<br/>slice B"]
    SEED --> F3["editor instance<br/>slice C"]
    F1 --> COL["collect SliceReports"]
    F2 --> COL
    F3 --> COL
    COL --> V{"validate each report<br/>req 16"}
    V -->|"fail, attempt &lt; 3"| PLAN
    V -->|"fail, attempt = 3"| U["mark unverified<br/>req 17"]
    V -->|ok| AP["APPLY SERIALLY<br/>in slice order · conflict detection"]
    U --> AP
    AP --> RND["RENDER_DOCX + comments"]
    RND --> DEL["delivery reply — req 10"]
```

**Reasoning happens in parallel; writing happens in one place, in one order.** That
split is the whole design, and each half earns its keep for a different reason.

### Why the writes are serialised

Every editor instance receives a **read-only snapshot** of the artifact plus its own
slice, and returns a `SliceReport` of *proposed* edits and comments. No instance writes
to the document, or to the store.

That removes the hard problem rather than solving it. The alternative — N agents
mutating one shared artifact under optimistic concurrency — means version conflicts
under exactly the load the parallelism was introduced to handle, and a retry storm as
each loser re-runs a model call that already cost money.

Two properties follow that are worth more than the contention they avoid:

- **The output is deterministic in application order.** Proposals are applied in **slice
  order, never completion order**. Whichever instance finishes first, the resulting
  document is byte-identical. Apply on arrival instead and the document quietly changes
  between runs on the same input, which would make the golden fixture meaningless.
- **Conflicts become visible.** The applier holds *every* proposal before it writes
  anything, so two slices targeting the same `line_id` is a detectable event rather than
  a silent last-write-wins.

That second one is a real gain against concern **D3**. Contradictory requirements were
previously invisible by construction — each agent saw only its own slice and nothing
compared them. Fan-in gives us the one moment where all proposals coexist, which is the
only place a cross-slice contradiction *can* be caught. It does not solve D3 (two
requirements can conflict in meaning while touching different lines) but it converts the
line-level case from undetectable to detectable.

Req 12 still holds: each run gets a live `Artifact` object it may mutate freely at any
point. It is a snapshot, and the orchestrator merges the resulting edit list.

### The editor becomes a worker

`editor-service` no longer owns a state machine or a loop. It exposes essentially one
operation:

```
POST /slices:run   SliceRequest → SliceReport
```

Stateless, horizontally scalable, and testable without any job lifecycle around it.
The lifecycle — retries, the three-attempt cap, the unverified terminal, apply, render,
deliver — belongs to the orchestrator, which is also where `JobRecord` already lives.

**Tools are scoped per instance.** A slice runner is handed a toolset bounded to its own
requirements and the regions they govern. A proposal targeting a line outside that scope
is rejected by the applier deterministically — slice isolation is enforced by the tool
layer and the applier, never by asking the prompt nicely.

**Concurrency is bounded.** A semaphore caps simultaneous slices; `UsageLimits` caps each
one. Unbounded fan-out on a 40-requirement manifest is how you discover your Gemini rate
limit in production.

### A note on the name

A service that does mail I/O *and* orchestration is doing two jobs, and the name only
mentions one. Internally it splits `orchestrator/` from `mail/`, with the mail transport
as an adapter and orchestration as the core — so the day it wants to be its own service,
or grow a second front door, the seam is already there.

### Do the two modes still differ?

Mostly no, and the orchestration change makes that clearer. They diverge at **SEED
ARTIFACT** and nowhere else: derivative parses the client's `.docx`, net-new generates a
scaffold. Slice planning, fan-out, validation, retry, apply, render and delivery are
shared.

Both modes still have regions; they differ only in who decides them. Derivative has an
agent classify the client's existing content. Net-new has the generator declare them as
it emits — structure locked, slots editable.

The runners stay separate for one reason, and it is not structural: **authority**. A
derivative run may not write; a net-new run must. A client sending a form for validation
wants to be told it is wrong, not handed a silently corrected version. Locked regions are
the enforcement; separate runners keep the enforcement meaningful.

## How the manifest becomes requirements

Req 5 calls this "a simple parsing / normalisation step". The fleet fixture shows it
is not simple, and it is worth being concrete about why — this stage is the single
highest-risk artefact in the system, because every downstream verdict is graded
against its output.

The client's manifest, verbatim:

```
16 zdjęć,
Pod maską
4x fotele i 2 przekatne pojazdu
2x podsufitka,
Pod maską,
Przednia szyba że środka i zewnątrz
Bieżnik opony
zdjęcie bagażnika + wyposażenia pod klapą
i zegary
Podsufitka trzeba spomiędzy forteli zrobić
```

Ten lines, and every one of the four hard cases below is in there.

### Stage 1 — deterministic pre-split (no model)

Break on line boundaries and list markers into candidate chunks. Cheap, reproducible,
and it establishes the character offsets that provenance depends on. It cannot finish
the job, for the reasons below.

### Stage 2 — extraction pass (small model call)

Candidate chunks become discrete `Requirement` objects. Four things make this the
part that needs judgement:

**One line, two requirements.** `Przednia szyba że środka i zewnątrz` is a single line
naming two separately checkable things — the windscreen from inside (R-05) and from
outside (R-06). Same with `bagażnika + wyposażenia pod klapą` → R-08 and R-09. A
line-per-requirement parser silently under-counts.

**Counts are not repetitions.** `4x fotele` is one requirement with `expected_count: 4`,
not four requirements. Getting this wrong inflates the requirement set and produces
four near-identical review comments.

**A constraint stranded from its subject.** Line 10, `Podsufitka trzeba spomiędzy
forteli zrobić`, qualifies `2x podsufitka` on line 4 — six lines away. Attach it to the
wrong requirement and the wrong photo gets rejected; drop it and R-04 passes when it
should fail. This is the case that makes a pure line-by-line split insufficient, and
it is why there is a model here at all.

**Genuine ambiguity, to be surfaced rather than guessed.** `Pod maską` appears twice.
One reading gives 15 photos, the other 16 — and the client wrote 16 on line 1. The
parser records the ambiguity on the requirement rather than silently picking; the
client sees the resolution in the confirmation reply and can correct it.

Note also that the input is misspelled throughout — `że` for `ze`, `forteli` for
`foteli`, `przekatne` missing its diacritic. Normalising the text before parsing would
be the obvious move and it is **forbidden**, because of the next stage.

### Stage 3 — provenance binding

Every `Requirement` carries a `source_span` that is a **verbatim substring of the raw
manifest**. Asserted as an invariant, not scored:

> every `source_span` appears character-for-character in `manifest.txt`

That is what makes the parse auditable — the client can see exactly which of their own
words produced each requirement, typos and all. It is also what catches a parser that
has started inventing requirements rather than extracting them, which is the failure
mode that matters most here: L1 requires recall ≥ 0.95 but **precision 1.0**. Missing a
requirement is recoverable, since the client sees the list and says so. Inventing one
means the client is told their document fails a rule they never wrote.

### Stage 4 — slicing

Requirements are grouped by `scope` into the slices each agent run will own (req 11).
The fixture yields `exterior_mechanical`, `interior`, `glass`, `tyres`, `boot`.

Slice boundaries are a real design decision, not bookkeeping: an agent only ever sees
its own slice, so two requirements that contradict each other land in different runs
and neither notices. That is concern **D3**, and slicing is where it is created.

### Why req 7 matters more than it looks

Because there is a model in stage 2, the requirement list is generated, not derived.
Sending it back to the client in the confirmation reply is the cheapest correction
point in the entire system — it costs one paragraph of email and catches a misparse
before a single comment has been written against it.

Which is also why the parse must happen **once**. See the email layer above.

## Citations must quote, not point

A reference like `manifest.txt → R-04` tells the client nothing. They did not write
`R-04`; they wrote `2x podsufitka`. A justification is only auditable if it carries the
words that actually drove the decision, so `ReviewComment.citations` holds verbatim
quotes with their line numbers, and the fixture asserts three things about them:

- **every quote is a literal substring of the manifest.** A citation the client cannot
  find in their own words is worse than no citation — it looks like evidence and isn't.
- **the cited line number is where that quote actually appears.**
- **the required spans are all present**, not just one of them.

That last point is the substantive one. Two requirements in the fixture need **two
citations each**:

| Req | Must cite | Why both |
|---|---|---|
| R-01 | `16 zdjęć` + `Pod maską` | The repeated line is why two are expected; the client's own stated total of 16 is why that reading wins |
| R-04 | `2x podsufitka` + `Podsufitka trzeba spomiędzy forteli zrobić` | Cite only the first and the client cannot see why two supplied photos failed |

Cite one span where two were needed and the comment becomes unanswerable. The evaluator
enforces this — dropping R-04's constraint citation, paraphrasing it instead of quoting,
or citing it against the wrong line number all fail the fixture.

## In net-new, everything arrives as an edit

Req 14 says edits are line-targeted and there is no full regeneration. That constrains
net-new more than it first appears: the scaffold generator does **not** get to emit
finished content.

The generator emits **structure only** — headings, field labels, empty content slots —
and declares its own regions as it goes: structure locked, slots editable. Every piece
of actual content then arrives through the same `Edit(line_id, new_text, requirement_id)`
path that derivative uses. Nothing is written directly into the document.

Three things fall out of that, and they are the reason to insist on it:

- **Provenance is total.** `Artifact.edits` becomes the complete account of how the
  document came to exist, with every line traceable to the requirement that caused it.
  Req 10 asks net-new comments to show how each requirement was realised — this is what
  makes that answerable rather than asserted.
- **One apply path.** `APPLY_EDITS` is identical in both modes, so locked-region
  enforcement is exercised by both and cannot rot in the mode that "doesn't need it".
- **The invariant is checkable:** in net-new output, every character outside the
  generated scaffold must be attributable to an `Edit` carrying a `requirement_id`.
  Content that appears with no edit behind it is a bug, however good it reads.

## Service structure

Nine agents building in parallel will each invent their own layout unless one is
written down. Both services use the same shape:

```
services/<name>/src/<pkg>/
  main.py           app factory + lifespan; nothing else
  api/
    routers/        thin HTTP layer, one module per resource
    deps.py         FastAPI Depends providers — settings, repos, clients
    schemas.py      HTTP request/response shapes (NOT the wire contracts)
  services/         business logic
  <domain>/         machine/, agents/, llm/, store/, transport/ …
```

Four rules, the first two enforced by import-linter rather than review:

1. **`services/` must not import `fastapi`.** This is the load-bearing rule. It is what
   lets the state machine be driven from a test, the eval harness or a CLI with no HTTP
   anywhere, and it is why the whole Tier-A suite runs without starting a server.
2. **Routers hold no business logic.** Parse, delegate, shape the response. A router
   containing a domain `if` is in the wrong file.
3. **Dependencies arrive through `Depends`**, never module-level singletons — that is
   how a test injects the in-memory repository and the fake transport.
4. **`mff-contracts` models are the wire contract between services; `api/schemas.py` is
   for HTTP concerns only.** Do not leak one into the other, or the frozen package stops
   being frozen in practice.

## Image understanding is a third service

Req 13's image tools are **owned separately** (`AGENTS.md`) and arrive as their own
service, not a library. That is now wired end to end with a placeholder in its place:

```
POST /v1/describe        ImageRef               → ImageAnalysis
POST /v1/describe:batch  list[ImageRef]         → list[ImageAnalysis]
POST /v1/crop            ImageRef + BoundingBox → ImageRef
```

`packages/mff-vision` holds the `VisionTool` Protocol, an `HttpVisionTool` client, and
`InventoryVisionTool` — a stand-in answering from the fixture's labelled inventory.
`services/vision-stub` serves the same routes so the wiring is real rather than
imagined. The editor depends on the Protocol only, so the real service is a
configuration change.

**The stand-in is a lookup, not a constant.** Keyed by filename, so each image gets its
own label — and the two headliner photographs return **different `shot_from` values**,
which is precisely what lets a derivative run fail R-04 for the right reason rather than
by luck. Collapse it to one answer and the fixture stops testing what it exists to test.

It also cannot be wrong, which makes it useless for measuring vision quality and ideal
for everything else: the editor, the applier and every eval become fully deterministic,
so a red test means the editor is broken rather than that a model had an off day. When
the real service lands, the same `inventory.yaml` becomes the answer key it is scored
against.

**Two distinctions the API insists on.** *Unidentifiable* is not *unavailable*: an image
the service examined and could not place returns `depicts == "unknown"` with zero
confidence — evidence the editor must reason about — while an unreachable service raises
`VisionUnavailable`, which is infrastructure failure and must never be written into a
comment about the client's photographs. And `depicts` and `shot_from` are separate
fields, because "what is this a picture of" and "where was it taken from" are separate
questions; merging them loses R-04 entirely.

### Two things to settle with the owner

The shapes in `mff_vision.models` were written from what the *editor* needs, not from
what a CV pipeline naturally emits. They are a proposal, not a decision:

1. **The payload shapes**, before anything is built against them on the other side.
2. **Whether `shot_from` is a closed vocabulary.** The fixture uses
   `between_front_seats` and `beside_seat`. Left as free text, the editor has to
   interpret strings it has never seen and R-04 stops being decidable.

## Dependency pinning

**Never depend on `pydantic-ai`.** The meta-package resolves to:

```
pydantic-ai-slim[openai,anthropic,google,cli,mcp,evals,web,retries,logfire]
```

which ships the OpenAI *and* Anthropic SDKs, an MCP client and a CLI into every image
so we can talk to Gemini. Use the slim package with only the extras we actually call:

```toml
# services/editor-service — the only service that talks to a model
dependencies = [
  "pydantic-ai-slim[google,evals]",   # GoogleModel/GoogleProvider + pydantic-evals
  "mff-contracts", "mff-docmodel", "mff-vision",
]
```

Notes for whoever writes these files:

- **`[google]`** brings `google-genai`, which is where `HttpRetryOptions` lives — so the
  transport-level retry in the plan needs no further extra. The separate `[retries]`
  extra is for Pydantic AI's *own* tenacity transport; add it only if we adopt that
  instead.
- **`[evals]`** is how `pydantic-evals` arrives. It is a real dependency of the eval
  suites, not a dev convenience, because the structural evaluators import it.
- **`[logfire]`** stays out by default. Observability is worth having, but it should be
  a deliberate opt-in per environment rather than weight in every image.
- **`email-service` and `vision-stub` get no model extras at all.** The orchestrator
  never calls a model — parsing happens in the editor — and the vision placeholder
  processes nothing. If either grows a `pydantic-ai` dependency, something has moved to
  the wrong service.

Image weight is a deployment concern and deployment is not ours, which is exactly why
this belongs in the plan: we are the ones who decide what goes in the image, and the
people who pay for it are not in this repo.

## The mailbox

### Locally — GreenMail, not Mailpit

An earlier draft of this plan said Mailpit. That was wrong: **Mailpit is SMTP-only for
receiving and speaks no IMAP**, so the inbound poller — the entire receiving half of the
email service — cannot be developed against it. GreenMail serves both.

```bash
docker compose -f docker/compose.dev.yaml up -d
python scripts/verify_mailbox.py
```

| Protocol | Port |
|---|---|
| SMTP | 3025 |
| IMAP | 3143 |
| SMTPS / IMAPS | 3465 / 3993 |
| REST API | 8080 |

GreenMail's standard +3000 offset means nothing collides with a real mail client or a
system MTA on the same machine. Auth is disabled in the dev compose, so any
user/password authenticates and the mailbox is created on first use — no account setup,
and obviously never anywhere near a real deployment.

`scripts/verify_mailbox.py` sends a message with an attachment and retrieves it over
IMAP, asserting that both the attachment and the Polish characters survive. Run it
before debugging the email service: it separates "our code is wrong" from "the mailbox
is not up", which are otherwise easy to confuse and expensive to conflate.

### Who receives the results

There is no recipient setting, and there must never be one. **Replies go to the sender of
the incoming request**, read off its `From` / `Reply-To` headers. The configured mailbox
is the address clients *write to*; each client gets results back at whatever address they
wrote from.

That is what lets a person use their ordinary everyday address as a client while the
service polls a separate, dedicated mailbox it fully owns. The two are never the same
account, and the poller never touches anyone's personal inbox.

It also means the service will reply to **anyone** who emails it. Two guards, both cheap
and both belonging to B3:

- **`ALLOWED_SENDERS`** — an allowlist. Left empty the service is an open robot that
  answers spam and, worse, can bounce-loop with another autoresponder: it replies, the
  other side auto-replies, and neither stops. An allowlist ends that in one line.
- **A per-sender rate cap**, for the same reason at lower cost than reasoning about
  loops.

Standard practice applies too: never auto-reply to a message carrying
`Auto-Submitted: auto-*` or `List-Id`, or to a null return path. That is the rule that
keeps two robots from talking to each other forever.

### What actually needs a real mailbox

Almost nothing. The `MailTransport` Protocol (B4) ships an in-memory fake, so intake
rules, reply templates, delivery, threading and idempotency are all testable with no
mail server at all. GreenMail exists for **E1 only** — the end-to-end run that proves
the real IMAP and SMTP code paths work against something that speaks the actual
protocols.

That ordering matters for the branch plan: B3, B13 and the orchestrator never need a
mailbox, so none of them wait on one.

### What no test mailbox can tell you

It is genuinely true that the whole pipeline — intake, validation, replies, job
tracking, delivery, threading, idempotency — works with no mail server at all, because
email is just bytes and the transport Protocol is the only part that touches a network.
That is the design paying off, and it is why almost no branch waits on infrastructure.

It is also the trap. Two classes of failure are invisible to both the fake and
GreenMail, and both bite in production:

**Deliverability.** A test server accepts everything. It cannot tell you whether a real
recipient's provider puts our reply in spam, or drops it silently. SPF, DKIM and DMARC
on the sending domain decide that, and no amount of green tests substitutes for one real
message to a real inbox. Worth doing early — the failure mode is a client who says "I
never got anything" while every log says delivered.

**Real client MIME is far messier than ours.** Every message in our fixtures is one we
generated, so it is exactly as well-formed as our own assumptions. Real requests arrive
from Outlook, from Gmail on a phone, forwarded through three people, with inline images
that should have been attachments, `Content-Disposition` headers that disagree with the
filename, and Polish text in whatever encoding the sender's client felt like. Intake
(B3) is where that lands, and its rule matrix will be wrong in ways no synthetic fixture
reveals.

The cheap mitigation: once a real mailbox exists, **keep every message that fails intake
as a new fixture case**. Real malformed mail is the most valuable test data available
and it cannot be invented — the fleet fixture is only as good as it is because it came
from an actual submission rather than from imagination.

### Running against a real mailbox from a container

It works, and it needs no inbound ports — the poller makes an outbound connection to the
provider, so there is nothing to expose and nothing to forward. But five things are
easy to get wrong.

**Port 25 is blocked on GCP, permanently and with no exceptions.** Ports 587 and 465 are
unrestricted. Our SMTP config uses 587, so this is fine — the rule is simply that there
must never be a fallback to port 25, because it will work locally and fail silently the
moment it is deployed. Worth passing to whoever owns deployment; it is the single most
common way a working mail integration dies on GCP.

**A first login from a datacenter IP can be challenged.** Google may treat the initial
sign-in from an unfamiliar cloud address as suspicious and block it pending manual
approval. App Passwords are more tolerant than plain password auth, but not immune. The
practical order is: get the credentials working from your own machine first, so that when
the container fails you know it is the environment and not the password.

**Gmail caps sending.** Roughly 500 messages a day on a free account, 2000 on Workspace.
Irrelevant for a demo, and worth remembering before anyone points a load test at it.

**IMAP connections do not stay up.** Gmail drops idle ones, and IMAP `IDLE` has to be
re-issued well before the ~29 minute limit. **B4 must reconnect rather than assume a
durable connection** — a poller that works for twenty minutes and then quietly stops is
the failure this causes, and it looks exactly like "no mail arrived".

**Credentials are injected, never baked.** The App Password arrives as an environment
variable or a mounted secret at runtime. An image with a working password inside it is a
credential leak wearing a Dockerfile.

### In production

A Gmail account with an **App Password** is the quickest real mailbox: enable 2-Step
Verification, generate an app password, and use it as `IMAP_PASSWORD` / `SMTP_PASSWORD`
against `imap.gmail.com:993` and `smtp.gmail.com:587`. Plain account passwords stopped
working when Google withdrew "less secure app access", so the app password is not
optional.

Two caveats worth knowing before committing to Gmail:

- **Gmail refuses attachments over 25 MB.** The fixture's single reviewed document is
  2.8 MB, so a multi-form job clears that quickly — which is why delivery (B13) falls
  back to a signed link above a threshold rather than treating attachment as the only
  path.
- **Gmail's IMAP folders are labels, not folders**, and `\Seen` semantics differ subtly
  from a conventional server. The poller's idempotency is keyed on `Message-ID` rather
  than on read state precisely so this does not matter.

A dedicated provider (Fastmail, Zoho, Migadu) avoids both quirks and is worth it if this
outlives the hackathon.

## State & persistence

Req 12 says the artifact lives "outside any single agent run". In-process that's a Python object — but across an HTTP boundary, a retry, a crash, or a second replica, an in-process object is gone. It needs a store, and that store is also what finally gives **D2** (job status after confirmation) something to report.

**Yes — a Firestore-backed store with async `save`/`load`. But it goes behind an interface, not into the flows.**

```python
# mff-contracts — frozen alongside the models
class ArtifactRepository(Protocol):
    async def save(self, artifact: Artifact, *, expected_version: int) -> int: ...
    async def load(self, job_id: str) -> tuple[Artifact, int]: ...

class JobRepository(Protocol):
    async def put(self, record: JobRecord) -> None: ...
    async def get(self, job_id: str) -> JobRecord | None: ...
```

Two implementations: `InMemoryRepository` (tests, evals, local dev) and `FirestoreRepository` (GCP, via `google.cloud.firestore.AsyncClient`, which is natively async). The state machine only ever sees the Protocol.

That indirection is not ceremony — it is what lets **CI and the whole Tier-A eval suite run with no GCP credentials and no emulator**. Provisioning Firestore is the deployment owner's job; the client code is ours.

### Four things a naive `save`/`load` gets wrong

**1 · Firestore's 1 MiB document cap.** An `Artifact` carrying every `Line` of a 50-page form plus a comment per requirement can approach it, and the `.docx` bytes blow straight past it. So: **Firestore holds the JSON state, GCS holds the documents**, referenced by path. Getting this wrong surfaces as a hard write failure on exactly the large documents the product exists to handle.

**2 · The job record is not the artifact.** `JobRecord` — status, mode, current slice, attempts used, unverified ids, timestamps — is a separate small document that is cheap to poll. That is the D2 answer, and it stays readable even when the artifact is mid-write.

**3 · Optimistic concurrency.** The artifact is mutated across many slice runs. Carry a `version` int and check it on write. v1 runs slices sequentially so it should never fire — but if it ever does, a lost update means silently dropped review comments, which is the worst possible failure here because the output still looks complete.

**4 · Checkpoint per slice, not per job.** Save after each slice completes. That makes a crashed job resumable rather than restartable, and gives the job record real progress to report instead of a binary running/done.

### The blob pointer

Firestore stores the run's *shape*; the bucket stores its *weight*. One reference type covers both directions:

```python
class BlobRef(BaseModel):
    uri: str            # gs://<bucket>/jobs/<job_id>/<kind>/<sha256>
    content_type: str
    size_bytes: int
    sha256: str
```

It carries the client's source `.docx`, the rendered output, and **every image extracted from a form**. Content-addressing by `sha256` means a retried job re-points at the existing object instead of writing a second copy — which matters, because req 17 retries up to three times and a naive path scheme would triple-write on every recovery.

This is also the seam the deferred image module (**B11**) picks up: it reads `BlobRef`s already sitting on the artifact and returns crops as new ones. No schema change when it lands — which is the whole reason for stubbing the interface now rather than leaving a hole.

## Layout

```
pyproject.toml
packages/
  mff-contracts/
  mff-docmodel/
  mff-manifest/
services/
  email-service/
  editor-service/
fixtures/fleet-vehicle-return/
docker/
```

| Path | Purpose |
|---|---|
| `pyproject.toml` | uv workspace, ruff + pytest + mypy |
| `packages/mff-contracts` | **FROZEN** shared models — the seam that makes parallelism safe |
| `packages/mff-docmodel` | docx ⇄ line-addressable `Artifact`, regions, comment writer |
| `packages/mff-manifest` | free-text manifest → discrete `Requirement[]` |
| `services/email-service` | Orchestrator + mail adapter: IMAP poller, SMTP sender |
| `services/editor-service` | FastAPI worker: `POST /slices:run`, Pydantic AI agents (Gemini) |
| `fixtures/fleet-vehicle-return` | the illustrative example, as golden test data |
| `docker/` | one Dockerfile per service + compose for local dev |

## The contract to freeze first (`mff-contracts`)

Everything else is written against these. **No branch may edit this package** — a change request goes back through the layer-0 owner.

```python
class Requirement(BaseModel):
    id: str                    # "R-03"
    text: str                  # one normalised, individually checkable statement (req 5)
    source_span: str           # verbatim manifest text it was derived from
    scope: str                 # slice key — which agent run owns it (req 11)
    applies_to: list[str]      # form ids; empty = all forms

class Manifest(BaseModel):
    raw: str
    requirements: list[Requirement]
    def slices(self) -> dict[str, list[Requirement]]: ...

class Line(BaseModel):         # the addressable unit edits target (req 14)
    id: str                    # stable: "p12", "t3.r2.c1.p0"
    text: str

class Region(BaseModel):
    id: str
    line_ids: list[str]
    locked: bool
    rationale: str             # why the first run classified it this way

class Edit(BaseModel):
    line_id: str; new_text: str; requirement_id: str

class Citation(BaseModel):         # the client's own words, not a pointer
    requirement_id: str
    quote: str                     # VERBATIM substring of manifest_raw
    line: int                      # 1-indexed line it appears on
    start: int; end: int           # char offsets; manifest_raw[start:end] == quote

class ReviewComment(BaseModel):
    line_id: str
    requirement_id: str
    verdict: Literal["pass", "fail", "realised", "unverified"]
    justification: str                 # req 16: every answer justified
    suggestion: str | None             # required when verdict == "fail" (req 10)
    citations: list[Citation]          # req 16 — plural, and quoted; see below

class Artifact(BaseModel):     # req 12 — lives outside any single agent run
    doc_id: str
    lines: list[Line]
    regions: list[Region]
    edits: list[Edit]
    comments: list[ReviewComment]

class Mode(StrEnum): DERIVATIVE = "derivative"; NET_NEW = "net_new"
class JobRequest(BaseModel):   # email-service → editor-service
    job_id: str; mode: Mode; manifest_raw: str
    forms: list[FormPayload]; client_inputs: dict[str, Any]
class SliceRequest(BaseModel):   # orchestrator → one editor instance
    job_id: str; slice_id: str; mode: Mode
    requirements: list[Requirement]   # this slice only
    artifact: Artifact                # READ-ONLY snapshot
    editable_line_ids: list[str]      # the scope bound; anything else is rejected

class SliceReport(BaseModel):    # editor instance → orchestrator
    slice_id: str; attempt: int
    edits: list[Edit]                 # PROPOSED; the orchestrator applies them
    comments: list[ReviewComment]
    unanswered: list[str]             # requirement ids this run could not decide

class JobAccepted(BaseModel):  # 202 response — what the confirmation reply quotes
    job_id: str
    requirements: list[Requirement]   # parsed once, here; req 7 sends exactly this
class JobResult(BaseModel):   # editor-service → email-service, on completion
    job_id: str; status: Literal["done", "failed"]
    documents: list[DocumentPayload]      # BlobRefs; attached or linked by size
    unverified: list[str]                 # req 17 — named explicitly in the reply
    summary: dict[str, int]               # {"pass": 8, "fail": 2, "unverified": 0}
    failure_detail: str | None = None     # populated when status == "failed"

class IntakeProblem(BaseModel): code: str; detail: str     # req 8: what to add/change
class IntakeVerdict(BaseModel): valid: bool; problems: list[IntakeProblem]
```

## Parallel branch tasks

Directory ownership is **disjoint per branch** — that is what keeps 7 concurrent PRs from conflicting.

### Layer 0 — blocking, one PR, must merge before anything else

**B0 · scaffold + contracts** — `pyproject.toml`, `packages/mff-contracts/**`, `Makefile`, CI workflow (ruff + mypy + pytest), empty package/service skeletons so later branches only add files. Ships the frozen models above with full unit tests on the validators (`suggestion` required when `verdict=="fail"`, etc.).

### Layer 1 — 10 PRs in parallel, all branch from B0

| ID | Branch | Owns | Deliverable |
|----|--------|------|-------------|
| **B14** | `feat/applier` | `packages/mff-applier/**` | The serial applier: order proposals by **slice id, not arrival**; detect two slices targeting one `line_id`; reject any edit outside its slice's `editable_line_ids`; enforce locked regions. Pure functions over `SliceReport[]` → `Artifact`. No I/O, no model, fully deterministic — the easiest thing in the repo to test exhaustively, and the one most worth testing. |
| **B1** | `feat/docmodel` | `packages/mff-docmodel/**` | `.docx → Artifact` (stable line ids incl. table cells), `apply_edits()` surgical line replace with **locked-region enforcement** (raises on a locked target), `attach_comments()` via `python-docx` `add_comment`, `Artifact → .docx`. No AI. Round-trip tests on fixture docs. |
| **B2** | `feat/manifest` | `packages/mff-manifest/**` | Free text → `Requirement[]` (req 5): deterministic pre-split + one small Gemini extraction agent, stable ids, `source_span` provenance, `slices()` grouping strategy. Tested with `FunctionModel` — no live API in CI. |
| **B3** | `feat/intake` | `services/email-service/src/**/{intake,replies}.py` | Req 6/7/8: MIME parse, attachment extraction, mode inference (derivative needs supplied forms — req 3), `IntakeVerdict` rules, and both reply templates — the valid one **quotes the `Requirement[]` returned in the 202** (req 7 *Recommended*) — it must never parse the manifest itself. |
| **B4** | `feat/mail-transport` | `services/email-service/src/**/transport/**` | `MailTransport` Protocol + IMAP poller (IDLE/poll, seen-state, idempotency by Message-ID) + SMTP sender with threaded replies (`In-Reply-To`/`References`), **plus an in-memory fake** every other branch tests against. |
| **B5** | `feat/orchestrator` | `services/email-service/src/**/orchestrator/**` | Slice planning, **bounded-concurrency fan-out**, fan-in, the `SliceReport` validator (req 16), 3-attempt cap with the error fed back, then `unverified` (req 17). Owns the job lifecycle. Dispatches through a `SliceRunner` Protocol, so it is tested end-to-end with a fake runner and no editor service running at all. |
| **B8** | `feat/llm-config` | `services/editor-service/src/**/llm/**`, `settings.py` | `GoogleModel` + `GoogleProvider` wiring, pinned model id in settings, `HttpRetryOptions`, per-slice `UsageLimits`, shared `RunUsage` accounting, structured logging. One `build_agent()` factory both flows call. |
| **B10** | `feat/docker` | `docker/**`, `compose.yaml` | Multi-stage Dockerfile per service (non-root, uv-installed deps, healthcheck), compose bringing up both services + `mailpit` for a local mailbox. No GCP, no Terraform. |

| **B12** | `feat/state-store` | `packages/mff-store/**` | `ArtifactRepository` + `JobRepository`: the in-memory adapter every other branch tests against, and the Firestore + GCS adapter for GCP. Versioned writes, per-slice checkpointing, no credentials needed for the in-memory path. |

| **B13** | `feat/delivery` | `services/email-service/src/**/delivery.py` | **Role 2.** The completion callback endpoint, the stale-job sweep, the results email (summary + unverified called out + failure detail), attach-or-link by size threshold, threading against the original message, and idempotency on `job_id`. Built against the frozen `JobResult` and the in-memory transport, so it needs neither the editor nor a mailbox to develop. |

### Layer 2 — 3 PRs in parallel, need B1/B5 (+B8)

| ID | Branch | Owns | Deliverable |
|----|--------|------|-------------|
| **B6** | `feat/flow-derivative` | `services/editor-service/src/**/flows/derivative.py`, `agents/derivative/**` | The `CLASSIFY_REGIONS` first run (locked vs editable + rationale, per the locked decision) and the per-slice validation agent: reads the artifact, emits **one comment per requirement per form** with pass/fail + justification + suggestion (req 10). Refuses edits into locked regions. |
| **B7** | `feat/flow-netnew` | `services/editor-service/src/**/flows/netnew.py`, `agents/netnew/**` | **The scaffold generator** (`Requirement[]` + client inputs → a document skeleton, declaring its own locked/editable regions as it emits) plus the authoring runner. Comments show **how each requirement was realised**, with justification + source reference (req 10). |
| **B11** | *(landed)* | `packages/mff-vision/**`, `services/vision-stub/**` | **Done.** The `VisionTool` Protocol, an HTTP client, a deterministic stand-in answering from the fixture inventory, and a placeholder FastAPI service behind the same routes the real one will serve. 13 tests including a client↔service round trip. Editor branches can call image understanding today. |

### Layer 3 — after Layer 2

**B9 · fleet-vehicle-return example + e2e** — `fixtures/fleet-vehicle-return/**` (manifest free-text, a supplied Word form for derivative, client inputs for net-new, golden expected comments) and an end-to-end test that drives a real email through the fake transport into both modes. This is the demo.

## Evals & latency budgets

**Every branch ships an eval suite. A PR without one does not merge.** "It works" is not a claim any subagent gets to make on its own recognisance — each stage must produce a number.

We use **`pydantic-evals`** (ships with Pydantic AI, same ecosystem): `Case` / `Dataset` / `Evaluator`, the built-in `IsInstance`, `Contains`, `LLMJudge`, and — directly answering the latency requirement — **`MaxDuration(seconds=...)`** as a first-class assertion. `EvaluatorContext` exposes `ctx.duration`, `ctx.metrics` and `ctx.span_tree`, so correctness, latency and token cost come out of one run.

### Two tiers

**Tier A — deterministic components** (no model anywhere): docmodel, intake rules, transport, contracts, the store. Golden assertions plus a wall-clock budget. Runs in CI on every push.

**Tier B — pipeline evals**: the system under test calls a live model, so it costs money and runs nightly or on demand rather than on every push. CI substitutes `TestModel`.

**The scorer is structural in both tiers.** No LLM-as-judge anywhere. The pipeline is non-deterministic; whether its output is complete is not:

> non-deterministic system + deterministic scorer = a repeatable number

A judge would be the wrong instrument here anyway. The question is not "is this justification well written" but "does every requirement have a verdict, does every failure carry a suggestion, does every reference resolve, and are the verdicts *right*" — all decidable by reading the document. Scoring is a **violation count against a spec**, threshold zero, not a similarity or a rubric score.

Deliberately **not** a text-similarity comparison against the golden output document either: that fails on harmless wording differences in a justification while happily passing a document with the wrong verdicts. The golden `.docx` is a reference for humans to eyeball; the spec file is what the evaluator asserts.

### Invariants vs. scores — the important distinction

Some things are **contract violations, not quality signals**, and are asserted at `1.0` with no tolerance:

- every requirement in the slice has an answer (req 16)
- every answer has a non-empty justification (req 16)
- every `source_reference` resolves to a real `Requirement` or `Line` (req 16)
- every `verdict == "fail"` carries a non-empty `suggestion` (req 10)
- no edit ever lands in a locked region

Everything else is scored with a threshold. Mixing the two is how eval suites end up green while the product is broken.

### Budgets and thresholds

| # | Stage | Owner | p95 latency | Quality gate |
|---|---|---|---|---|
| A1 | `docx → Artifact → docx` round-trip (50pp) | B1 | **800 ms** | byte-stable on no-op; line ids stable across reload |
| A2 | `apply_edits` + `attach_comments` (100 comments) | B1 | **1.5 s** | opens clean in Word; comment count exact |
| A3 | MIME parse → `IntakeVerdict` | B3 | **200 ms** | 100% on the intake rule matrix (req 6/8) |
| A4 | SMTP send (incl. attachments) | B4 | **3 s** | threading headers correct; idempotent on retry |
| A5 | IMAP arrival → confirmation reply sent | B3+B4 | **30 s** | poll interval dominates; no double-send on redelivery |
| L1 | manifest → `Requirement[]` | B2 | **8 s** | recall ≥ 0.95, **precision 1.0** (zero invented reqs), every `source_span` verbatim in raw |
| L2 | `CLASSIFY_REGIONS` (1 form) | B6 | **15 s** | accuracy ≥ 0.90, **zero false-editable** on client-identity regions |
| L3 | one slice run (5 reqs) | B6 | **20 s** | invariants 1.0; verdict set matches golden exactly |
| L4 | net-new slice run | B7 | **20 s** | structural spec violations = 0; reference-resolution 1.0 |
| A6 | artifact `save` → `load` round-trip | B12 | **300 ms** | version conflict detected; GCS blob pointer resolves |
| A7 | job complete → results email sent | B13 | **20 s** | exactly one send per `job_id`; unverified listed; threaded on the original |
| A8 | apply 5 `SliceReport`s serially | B14 | **400 ms** | deterministic byte-for-byte across arrival orders |
| E1 | full derivative job (10 reqs, 1 form) | B9 | **35 s** | slowest slice + apply, not the sum |
| E2 | full net-new job (10 reqs) | B9 | **45 s** | end-to-end on the fleet fixture |

Treat these as **calibration targets, not measurements** — B0 lands the harness, and the first branch to run each stage records the real baseline in its PR. If a budget turns out to be wrong, the PR moves the number and says why; what's not allowed is shipping without one.

Note the asymmetry in **L2**: a region wrongly marked *editable* means we overwrite the client's own content, which is far worse than a region wrongly marked *locked* (we merely decline to help). The eval weights those errors differently on purpose.

### What a branch's eval dir looks like

```
packages/mff-manifest/evals/
  cases.yaml          the dataset — inputs + expected, reviewable in a PR diff
  structure.yaml      the structural spec this stage's output must satisfy
  evaluators.py       custom Evaluator subclasses; assert the spec, never judge
  test_evals.py       Tier A: runs under pytest in CI with TestModel
  README.md           recorded baseline: violations, p95, tokens, model id, date
```

**Mutation-test the evaluator.** An evaluator that has only ever seen correct output is worthless — it may be asserting nothing. Each branch must break its own golden output in at least three ways and show the evaluator catching each. This is not optional: the fixture's reference checker had a real bug (a field extractor that swallowed the rest of the comment, so a one-character justification passed a length check) and only mutation testing found it.

## Code quality bar

Seven agents writing in parallel is exactly how a codebase turns to mud. The defence is machine-enforced, not review-enforced — a human reviewer will not reliably catch architectural drift across 12 concurrent PRs.

**Enforced in CI (B0 ships the config; every branch must pass):**

- **ruff** lint + format, one shared config, zero per-package overrides.
- **mypy `--strict`** across the workspace. A `# type: ignore` needs a specific error code and a comment saying why.
- **import-linter** contracts pinning the dependency direction: `services → packages → mff-contracts`, never sideways, never upward. This is the single most valuable gate here — it's what stops B6 from reaching into B4's internals at 2am.
- **`mff-contracts` has no third-party dependency but `pydantic`.** It's the seam; it stays boring.
- **Per-package coverage ≥ 85%**, measured per package, not globally — a global number lets one well-tested package hide four untested ones.
- **No model call outside `llm/` and `agents/`.** Enforced by import-linter.

**Conventions (in the PR template, checked by review):**

- Prompts live in versioned files under `agents/<name>/prompts/`, never inline f-strings. They're the highest-churn, highest-impact artefact in the repo and they need a diff history.
- Each package declares its public API in `__init__.py` via `__all__`; everything else is private and may change without notice.
- Structured logging only (`structlog`), with `job_id` and `slice` bound on every line. Print statements fail lint.
- Any decision worth arguing about gets an ADR in `docs/adr/NNN-title.md`. Cheap to write, and it stops the same debate recurring in three PRs.
- Domain language matches the spec: `Requirement`, `Artifact`, `Line`, `Region`, `slice`, `verdict`. No synonyms.

## Spec template for each subagent PR

Each Sonnet agent gets a brief containing, verbatim:

1. **Requirement ids from the PDF it must satisfy** (e.g. B1 → reqs 14, 15; B5 → reqs 11, 12, 16, 17).
2. **The exact directories it owns** and the instruction that touching anything else — especially `mff-contracts` — is out of bounds; raise it in the PR description instead.
3. **The frozen contract signatures** it consumes and produces.
4. **Test requirements**: unit tests in its own package; no live Gemini calls in CI (`TestModel`/`FunctionModel` only); `make check` green.
5. **Eval requirements**: the `evals/` dir for its stage, the invariant assertions at 1.0, and the **recorded baseline** (score, p95 latency, tokens, model id, date) pasted into the PR description. A branch that cannot state its numbers is not done.
6. **PR discipline**: branch from `main` after B0, one PR, description lists requirement ids covered and any contract change it wants.

## Verification

- `make check` — ruff, mypy, pytest across the workspace; no network.
- `packages/mff-docmodel`: round-trip a fixture docx, assert line ids stable, assert a locked-region edit raises, open the output in Word and confirm comments land in the review pane.
- `services/editor-service`: `TestModel`-driven machine tests — force a validator failure three times and assert the requirement comes back `unverified` rather than raising.
- `services/editor-service`: one **live** Gemini smoke test behind an env flag, run manually, not in CI.
- End-to-end (B9): `docker compose up`, drop the fleet-vehicle-return email into mailpit, assert (a) confirmation reply contains the parsed requirement list, (b) the returned .docx has one comment per requirement, (c) net-new mode produces a document from client inputs alone.

## Open, carried forward

D1 (PDF/OCR input), D2 (job status after confirmation — largely answered now that B13 exists: the client is told on completion *and* on failure; what remains is status **on demand**, mid-run), D3 (cross-requirement conflicts — the line-level case is now **detectable** at fan-in, since every proposal coexists before anything is written; the semantic case, where two requirements contradict while touching different lines, is still open). None blocks v1.
