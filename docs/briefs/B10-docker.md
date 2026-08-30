# B10 · Containers and compose

**Branch:** `feat/docker` → PR into `main`
**Depends on:** B0 (merged). Works against skeletons if the services are not built yet.
**Needs:** Docker. No GCP account, no credentials.


**Read [`CONTEXT.md`](CONTEXT.md) first** — what the system does, what B0 left on disk,
the contract surface, and the fixture. This brief assumes it.

---

## What you are building

`docker/**` and `compose.yaml` — one image per service, and a local stack that comes up
with one command.

**Deployment is not ours.** We decide what goes in the image; the people who pay for
pulling it are not in this repo. That is exactly why image weight is your concern.

## Requirements you own

None directly. You own whether anyone else can run this.

## Directories you own

```
docker/**
compose.yaml
.dockerignore
```

`docker/compose.dev.yaml` already exists with GreenMail — B12 may add Firestore and GCS to
it. Coordinate rather than overwrite.

## Three images

| Service | Notes |
|---|---|
| `email-service` | orchestrator + mail. **No model library.** Needs `mff-docmodel`, so `python-docx`. |
| `editor-service` | `pydantic-ai-slim[google,evals]`. **No `python-docx`.** |
| `vision-stub` | already has a Dockerfile; bring it under the shared pattern |

**Those exclusions are load-bearing, not cosmetic.** If `python-docx` ends up in the editor
or `pydantic-ai` in the email service, something has moved to the wrong service and the
architecture has quietly drifted. Consider asserting it in a test.

## Requirements for each image

- **Multi-stage**, `uv`-installed dependencies, wheel cache not shipped.
- **Non-root user.** `USER app` with a fixed uid.
- **`HEALTHCHECK`** hitting `/healthz`.
- **Credentials injected at runtime**, never baked. An image with a working App Password
  inside it is a credential leak wearing a Dockerfile.
- `.dockerignore` excluding `.git`, `.venv*`, `fixtures/` (12 MB of photographs),
  `docs/`, `__pycache__`.

**The fixture exclusion matters** — `fixtures/` is 12 MB and belongs in no production
image. The one exception is `vision-stub`, whose stand-in reads `inventory.yaml`; copy that
single file explicitly and let the `MFF_VISION_INVENTORY` env var point at it. It is the
clearest marker of what makes that service a placeholder.

## Compose

`compose.yaml` brings up: `email-service`, `editor-service`, `vision-stub`, **GreenMail**
(SMTP 3025 / IMAP 3143), and whatever B12 adds for Firestore and GCS.

**GreenMail, not Mailpit.** Mailpit is SMTP-only for receiving and speaks no IMAP, so the
inbound poller cannot be developed against it. Verified against Mailpit's own docs.

`depends_on` with `condition: service_healthy`, so `docker compose up` yields a working
stack rather than a race.

## One deployment constraint worth carrying

**GCP blocks outbound port 25 permanently.** 587 and 465 are unrestricted. Nothing in your
config should reference 25, and it is worth a comment saying why — it works locally and
fails silently once deployed, which is the most common way a mail integration dies there.

## Definition of done

1. All three images build from a clean checkout.
2. `docker compose up -d` yields all services healthy.
3. `scripts/verify_mailbox.py` passes against the composed GreenMail.
4. **Image size reported in the PR description**, per service. If the editor image carries
   `python-docx` or the email image carries `pydantic-ai`, that is a bug, not a size
   problem.
5. Every container runs as non-root — assert with `docker inspect`.
6. No secret in any layer. Check with `docker history --no-trunc`.
7. A container restart does not lose an in-flight job — with B12's store, state is external
   and this should just work. Verify rather than assume.
8. `.dockerignore` verified: the built context excludes `fixtures/`, and image size shows
   it.

## Out of scope

GCP, Terraform, Cloud Run configuration, CI/CD pipelines, Kubernetes. Someone else owns
deployment; you own the artefact they deploy.
