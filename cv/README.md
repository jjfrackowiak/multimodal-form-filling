# CV tool

In-process tool for the AI editor: checklist + photos → inventory.

```
from cv import build_inventory
inv = build_inventory(images=dir, requirements=yaml_path)
```

CLI (from repo root):

```bash
python -m cv fixtures/fleet-vehicle-return/images \
  --requirements fixtures/fleet-vehicle-return/expected_requirements.yaml \
  --out /tmp/inventory.yaml \
  --workers 6
```

`--manifest` only if the yaml lacks `id` or `source_span` on a requirement.

Vertex Gemini (`gemini-2.5-flash`, ADC). Images are downscaled before the call.
Labels run **in parallel** (`CV_CONCURRENCY` or `--workers`).

Offline checks: `python -m cv.test_offline`
