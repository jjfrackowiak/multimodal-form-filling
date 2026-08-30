# B12 · The state store

**Branch:** `feat/state-store` → PR into `main`
**Depends on:** B0 (merged). Nothing else.
**Needs:** no GCP account. The in-memory path needs nothing; the Firestore/GCS path
develops against emulators.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`packages/mff-store` — implementations of the four repository Protocols B0 froze, in two
flavours:

| Adapter | For | Needs |
|---|---|---|
| `InMemory*` | tests, evals, local dev, CI | nothing |
| `Firestore*` / `Gcs*` | GCP | emulators locally, credentials in prod |

```python
ArtifactRepository.save(artifact, cursor, *, expected_version) -> int
ArtifactRepository.load(job_id) -> tuple[Artifact, JobCursor, int]
JobRepository.put/get/for_request
RequestRepository.put/get
BlobStore.put/get/signed_url
```

## Requirements you own

Req 12 (state outliving any run). Partly D2 — `JobRecord` is what makes job status
answerable at all.

## Directories you own

```
packages/mff-store/**
docker/compose.dev.yaml        ← you may ADD the firestore and gcs services
.env.example                   ← you may ADD emulator host variables
```

GreenMail is already in that compose file; leave it alone.

## The atomicity requirement — this is the point of the branch

`save` takes **both** the artifact and the cursor because they must be written in **one
transaction**. As two writes, a crash between them either replays a slice (duplicate
comments) or skips one (silently missing requirements). Both are silent, which is what
makes this worth engineering rather than assuming.

Firestore: use a transaction or a batched write. In-memory: swap both under one lock.

`expected_version` is optimistic concurrency, but be clear about what it is *for*: slices
run sequentially, so it will never fire in normal operation. It exists to catch a
**duplicate runner** — the same job picked up twice after a crash. Do not build a retry
loop around it; a conflict means something is wrong, so raise.

## Firestore holds shape, GCS holds weight

**Firestore caps a document at 1 MiB.** A `DerivativeArtifact` carrying every `Node` of a
50-page form plus a comment per requirement can approach it, and the `.docx` bytes blow
straight past — the fixture's reviewed document is 2.8 MB.

So: Firestore stores the artifact JSON and `JobRecord`/`RequestRecord`; GCS stores every
`.docx` and every image. Getting this backwards surfaces as a hard write failure on
exactly the large documents the product exists to handle.

**`BlobRef` is content-addressed** (`gs://<bucket>/jobs/<job_id>/<kind>/<sha256>`). Two
consequences you must implement: identical bytes deduplicate — the fixture's 17 files
become 15 blobs — and a retried job re-points at an existing object rather than writing a
second copy.

## Two gotchas that will otherwise cost you an afternoon each

**Firestore's `AsyncClient` needs explicit mock credentials against the emulator.** It does
not fall back the way the sync client does:

```python
AsyncClient(project="test", credentials=Mock(spec=google.auth.credentials.Credentials))
```

**`STORAGE_EMULATOR_HOST` support has moved around** in `google-cloud-storage`. Newer
versions may want `api_endpoint` on the client instead. **Verify against the version you
pin** rather than trusting either form.

## Emulators

```yaml
firestore:  google/cloud-sdk:emulators
            gcloud emulators firestore start --host-port=0.0.0.0:8090
gcs:        fsouza/fake-gcs-server   -scheme http -port 4443
```

```
FIRESTORE_EMULATOR_HOST=firestore:8090
STORAGE_EMULATOR_HOST=http://gcs:4443
```

Switch by environment variable only. **No code may branch on "am I local"** — that is the
seam rotting.

## Definition of done

1. `make check` green, coverage ≥ 85%.
2. **The same test suite runs against both adapters**, parametrised. If a test only passes
   in-memory, the Firestore adapter is untested and the Protocol has bought nothing.
3. Atomicity test: simulate a crash between artifact and cursor write, assert neither
   landed.
4. `expected_version` conflict raises rather than retrying.
5. Content-addressing test: store the fixture's 17 images, assert 15 distinct blobs.
6. A round trip of the fixture's 2.8 MB `report_reviewed.docx` through `BlobStore`.
7. `scripts/verify_stack.py` — sibling to `verify_mailbox.py`: writes and reads Firestore,
   uploads and fetches GCS, prints PASS/FAIL. Same principle — separate "our code is wrong"
   from "the stack is not up".
8. CI runs the in-memory suite with **no emulators and no credentials**.

## Out of scope

Deciding *when* to save (B5), the vision service, anything that touches a model, Terraform
or any GCP provisioning — that is the deployment owner's.
