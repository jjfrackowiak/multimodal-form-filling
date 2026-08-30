# CV service — inventory labels

Cropping is **out of scope** for now.

This module’s job is to look at a folder of inspection photos and write the same
shape as `fixtures/fleet-vehicle-return/inventory.yaml`:

- `depicts` from a closed taxonomy
- `shot_from` only for headliner (`between_front_seats` | `beside_seat`)
- `exact_duplicate_pairs` via **sha256**, not the model

The editor calls this service later over HTTP. Nothing here lives inside
`editor-service`.

## Generate

Needs `XAI_API_KEY`. Model default `grok-4.6` (override with `CV_MODEL`).

```bash
python3 -m venv .venv && .venv/bin/pip install -r cv/requirements.txt
export XAI_API_KEY=...
.venv/bin/python cv/generate_inventory.py fixtures/fleet-vehicle-return/images \
    --out /tmp/inventory.generated.yaml
```

## Eval (no API)

```bash
.venv/bin/python cv/eval_inventory.py /tmp/inventory.generated.yaml \
    fixtures/fleet-vehicle-return/inventory.yaml
```

Pass = every golden file has the same `depicts` (and headliner `shot_from`),
and the same duplicate pairs. Notes are ignored.

Until this eval is green, L3 still uses the hand-written `inventory.yaml` as
stand-in eyes.
