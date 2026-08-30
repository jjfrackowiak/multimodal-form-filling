# CV service — inventory labels

Cropping is **out of scope** for now.

Photos in → `inventory.yaml` out (same shape as
`fixtures/fleet-vehicle-return/inventory.yaml`):

- `depicts` from a closed taxonomy
- `shot_from` only for headliner (`between_front_seats` | `beside_seat`)
- `exact_duplicate_pairs` via **sha256**, not the model

**Model: Vertex Gemini** on project `linen-badge-507111-r6`
(`all-things-agentic-google`). Org policy **disallows API keys** — use
Application Default Credentials, not Agent Platform API keys.

The editor calls this later over HTTP. Nothing here lives inside `editor-service`.

## Auth (ADC)

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project linen-badge-507111-r6
```

Do not create an API key. The console will reject it.

Env (defaults shown):

```bash
export GOOGLE_CLOUD_PROJECT=linen-badge-507111-r6
export GOOGLE_CLOUD_LOCATION=global          # Vertex Gemini
export CV_MODEL=gemini-2.5-flash             # or gemini-2.5-pro
```

## Generate

```bash
python3 -m venv cv/.venv && cv/.venv/bin/pip install -r cv/requirements.txt
cv/.venv/bin/python cv/generate_inventory.py fixtures/fleet-vehicle-return/images \
    --out /tmp/inventory.generated.yaml
```

## Eval (no model)

```bash
cv/.venv/bin/python cv/eval_inventory.py /tmp/inventory.generated.yaml \
    fixtures/fleet-vehicle-return/inventory.yaml
```

Pass = every golden file has the same `depicts` (and headliner `shot_from`),
and the same duplicate pairs. Notes are ignored.
