# docker/

One image per service, built from the repo root so each Dockerfile can reach the uv
workspace (root `pyproject.toml` + `uv.lock`) and its own workspace dependencies.

```
docker/
  email-service.Dockerfile
  editor-service.Dockerfile
  cv.Dockerfile        # real vision service — Vertex, POST /v1/inventory
  compose.dev.yaml     # GreenMail + Firestore/GCS emulators
```

`compose.yaml` at the repo root is the full stack: it `include`s `compose.dev.yaml` and
adds CV, editor, and email. The editor calls CV at slice time (`CV_URL`).

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

## Port map

| Service | Container port | Host port | Notes |
|---|---|---|---|
| `email-service` | 8080 | 8000 | IMAP poller; never calls CV |
| `editor-service` | 8080 | 8001 | calls CV at slice time |
| `cv` | 8080 | 8002 | `CV_URL`; Vertex via ADC |
| GreenMail SMTP | 3025 | 3025 | never 25 — see `compose.yaml` header |
| GreenMail IMAP | 3143 | 3143 | |

Inside the compose network, services reach each other by service name and container
port (e.g. `http://cv:8080`), not the host-mapped port. GCP: `infra/`.
