# CV service

Cropping is out of scope.

| Input | When |
|---|---|
| `expected_requirements.yaml` | Always. Checklist: what to extract. |
| `images/` | Always. The photo files. |
| `manifest.txt` | Only if the checklist does **not** already have an `id` and `source_span` on every requirement. Those spans *are* the relevant bits of the manifest. |

```bash
# Fleet fixture: yaml already has R-01… and source_span — no manifest needed
cv/.venv/bin/python cv/generate_inventory.py fixtures/fleet-vehicle-return/images \
    --requirements fixtures/fleet-vehicle-return/expected_requirements.yaml \
    --out cv/inventory.generated.yaml

# Checklist without spans: pass the raw shot list too
cv/.venv/bin/python cv/generate_inventory.py example_images/test_not_prev_seen \
    --requirements example_images/test_not_prev_seen/expected_requirements.yaml \
    --manifest example_images/test_not_prev_seen/manifest.txt \
    --out example_images/test_not_prev_seen/inventory.generated.yaml
```
