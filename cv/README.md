# CV service — three inputs

Cropping is out of scope.

| Input | Meaning |
|---|---|
| `expected_requirements.yaml` | Checklist: **what information to extract** from the photos |
| `manifest.txt` | **Which images** the client says they provided |
| `images/` | The photo files |

Output: `inventory.yaml` — each file tagged with requirement ids from the checklist,
plus citable observations. Duplicates via sha256.

```bash
cv/.venv/bin/python cv/generate_inventory.py fixtures/fleet-vehicle-return/images \
    --requirements fixtures/fleet-vehicle-return/expected_requirements.yaml \
    --manifest fixtures/fleet-vehicle-return/manifest.txt \
    --out cv/inventory.generated.yaml
```
