# docker/

One image per service, built from the repo root so each Dockerfile can reach the uv
workspace (root `pyproject.toml` + `uv.lock`) and its own workspace dependencies.

```
docker/
  email-service.Dockerfile
  editor-service.Dockerfile
  vision-stub.Dockerfile
  cv.Dockerfile        # real vision service (Michal) — Vertex, not the fixture lookup
  compose.dev.yaml     # GreenMail only — B12 may add Firestore/GCS emulators here
```

`compose.yaml` at the repo root is the full stack: it `include`s `compose.dev.yaml` and
adds the three application services on top.

```bash
docker compose up -d
python scripts/verify_mailbox.py     # exercises GreenMail directly, independent of the
                                      # two services below
```

## The shared pattern

Every Dockerfile here is the same shape:

- **Multi-stage.** `builder` resolves and installs with `uv sync --frozen --no-editable
  --package <service>` into `/app/.venv`; `runtime` copies only that venv in, so no
  source tree, no `uv` binary and no wheel cache (a BuildKit cache mount, never a layer)
  ends up in the shipped image.
- **Non-root.** `useradd --uid 10001` in every image; the process runs as `app`, never
  root. Verify with `docker inspect --format '{{.Config.User}}' <image>`.
- **`HEALTHCHECK`** against `GET /healthz`, using stdlib `urllib` — slim has no `curl` and
  this needs no extra dependency to add one.
- **No secret baked in.** Credentials arrive as environment variables at `docker compose
  up` time (see `compose.yaml`), sourced from `.env` / the shell, never `ARG`/`ENV`'d into
  a layer. Verify with `docker history --no-trunc <image>`.
- **An architecture guard**, in `email-service.Dockerfile` and `editor-service.Dockerfile`:
  a `RUN` step lists the installed packages and fails the *build* if `pydantic-ai` shows
  up in email-service, or `python-docx` in editor-service. Both exclusions are load-bearing
  (see `docs/briefs/CONTEXT.md` — "the editor is the only thing that calls a model") and
  this makes drift a build failure, not something a later reviewer has to notice by eye.

## Why `email-service` and `editor-service` build but don't (yet) go healthy

Both services are still B0's empty skeletons — no `main.py`, no `/healthz` route, and (for
`editor-service`) not even `fastapi`/`uvicorn` in `pyproject.toml` yet. Those files are
explicitly owned by later branches (B3/B4/B5/B13 for email-service, B8 for editor-service —
see `docs/briefs/README.md`'s ownership table), so this branch does not add them: doing so
would collide with those branches on the exact files they are about to write.

Concretely, today:

- Both images **build successfully** from a clean checkout.
- `vision-stub` and `greenmail` reach **healthy**.
- `email-service` and `editor-service` containers **start and then fail their
  healthcheck / exit**, because `uvicorn <pkg>.main:app` has no module to import yet.

Nothing needs to change here when that lands — the `CMD` already names the entrypoint the
implementation plan specifies (`docs/app-implementation-plan.md`, "Service structure"), and
the next `docker compose up --build` picks up the real app the moment `main.py` exists.

## vision-stub is the one exception to the `fixtures/` exclusion

`.dockerignore` excludes `fixtures/` (12 MB of photographs) from every build context.
`vision-stub.Dockerfile` is the sole image that reaches back for a single file —
`fixtures/fleet-vehicle-return/inventory.yaml` — copied by explicit path, with
`MFF_VISION_INVENTORY` pointed at it. That is the stand-in's one real dependency on the
fixture, and copying exactly that file (never `COPY fixtures/`) keeps it the clearest
marker of what makes this service a placeholder rather than a silent way for the other
11.9 MB to sneak back in.

## Port map

| Service | Container port | Host port | Notes |
|---|---|---|---|
| `email-service` | 8000 | 8000 | |
| `editor-service` | 8000 | 8001 | matches `.env.example`'s `EDITOR_SERVICE_URL` |
| `vision-stub` | 8000 | 8002 | matches `.env.example`'s `VISION_SERVICE_URL` |
| GreenMail SMTP | 3025 | 3025 | never 25 — see `compose.yaml` header |

Production CV is `docker/cv.Dockerfile` (Cloud Run port 8080). Local compose still
runs **vision-stub** until the editor is wired; do not point `VISION_SERVICE_URL` at
CV in `compose.yaml` yet. GCP: `infra/`.
| GreenMail IMAP | 3143 | 3143 | |

Inside the compose network, services reach each other by service name and container port
(e.g. `http://vision-stub:8000`), not the host-mapped port.
