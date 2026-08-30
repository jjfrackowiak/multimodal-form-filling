# CV service — inventory from **manifest.txt + photos**

Cropping is out of scope.

**Only two inputs:**

1. `manifest.txt` — raw client text (look-fors)
2. photo folder

There is no `expected_requirements.yaml` in this path. CV parses the manifest itself.

Output: `inventory.yaml` — files tagged with requirement ids from that parse, plus
citable observations. Duplicates via sha256.

```bash
cv/.venv/bin/python cv/generate_inventory.py fixtures/fleet-vehicle-return/images \
    --manifest fixtures/fleet-vehicle-return/manifest.txt \
    --out cv/inventory.generated.yaml
```
