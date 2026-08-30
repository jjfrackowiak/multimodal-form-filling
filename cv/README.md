# CV service — inventory from **manifest + photos**

Cropping is out of scope.

Inputs:

1. Client **manifest** (what to look for) — raw text or already-parsed requirements YAML
2. Photo folder

Output: `inventory.yaml` — each file tagged with **requirement ids**, plus citable
observations (km, warnings, plate, pose). Duplicates via sha256.

The 11 `depicts` labels from the Qashqai fixture are **not** the API. If the
manifest changes, parse it again; do not edit a frozen enum.

Standalone CLI still parses `manifest.txt` with Vertex. When Janek’s L1 parser
exists, pass `--requirements` and skip that step.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project linen-badge-507111-r6

cv/.venv/bin/python cv/generate_inventory.py fixtures/fleet-vehicle-return/images \
    --manifest fixtures/fleet-vehicle-return/manifest.txt \
    --out cv/inventory.generated.yaml

# or, once requirements are parsed elsewhere:
cv/.venv/bin/python cv/generate_inventory.py fixtures/fleet-vehicle-return/images \
    --requirements fixtures/fleet-vehicle-return/expected_requirements.yaml \
    --out cv/inventory.generated.yaml

cv/.venv/bin/python cv/eval_inventory.py cv/inventory.generated.yaml \
    --review fixtures/fleet-vehicle-return/expected_output/review.yaml \
    --pairs fixtures/fleet-vehicle-return/inventory.yaml
```
