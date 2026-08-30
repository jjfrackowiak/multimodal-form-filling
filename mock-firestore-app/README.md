# Mock: Cloud Run (2 kontenery) + Firestore + bucket

Lokalny szkielet tego, o czym była mowa w czacie:

- **kontener `api`** — HTTP, upload pliku, zapis dokumentu w Firestore
- **kontener `worker`** — szuka jobów `queued`, czyta ścieżkę pliku z Firestore, „przetwarza” plik z bucketa
- **Firestore** — trzyma rekordy i **wskaźniki** `gs://...`, nie zawartość plików
- **bucket** — trzyma bajty

Na GCP: API → Cloud Run **service**, worker → Cloud Run **worker pool** (albo service z `min-instances=1`), baza → **Firestore**, pliki → **Cloud Storage**.

## 1. Uruchom lokalnie

Potrzebujesz Dockera.

```bash
cd mock-firestore-app
docker compose up --build
```

Czekaj aż emulator Firestore wstanie (log: `Dev App Server is now running`). Compose czeka na healthcheck — bez tego worker potrafi zawiesić pierwsze query i job zostaje na `queued`.

## 2. Przepływ

```bash
# wrzuć plik → dostaniesz job id
curl -F "file=@README.md" http://localhost:8081/files

# uruchom proces (status: queued)
curl -X POST http://localhost:8081/jobs/JOB_ID/start

# poczekaj 2–3 s, worker podniesie status
curl http://localhost:8081/jobs/JOB_ID
```

Oczekiwany dokument:

```json
{
  "id": "...",
  "status": "done",
  "file": {
    "bucket": "mock-files",
    "path": "uploads/.../README.md",
    "gsUri": "gs://mock-files/uploads/.../README.md",
    "originalName": "README.md",
    "sizeBytes": 1234
  },
  "result": { "bytes": 1234, "preview": "..." }
}
```

## 3. Co jest w którym pliku

| Plik | Rola |
|---|---|
| `api/` | obraz HTTP |
| `worker/` | obraz pętli |
| `docker-compose.yml` | 4 serwisy: firestore emulator, fake GCS, api, worker |
| `gcp/SCHEMA.md` | jak wygląda dokument i co przenieść na prawdziwy projekt |

## 4. Co z tym zrobić na prawdziwym GCP

Projekt z screena: `all-things-agentic-google` / `linen-badge-507111-r6`.

1. W konsoli: **Firestore** → utwórz bazę (Native mode, region np. `europe-central2`).
2. **Cloud Storage** → bucket np. `linen-badge-files`.
3. Zbuduj i wypchnij oba obrazy do Artifact Registry.
4. Wdróż `api` jako Cloud Run service, `worker` jako drugi service (min instances 1) albo worker pool.
5. Env: `GCP_PROJECT`, `FIRESTORE_COLLECTION=jobs`, `BUCKET=...`
6. IAM: Cloud Run SA dostaje `roles/datastore.user` + `roles/storage.objectAdmin`.
7. Znajomego dodajesz w **IAM & Admin** (nie przez ten czat — Grok nie jest zalogowany do Twojego GCP).

Szczegóły poleceń: `gcp/DEPLOY.md`.
