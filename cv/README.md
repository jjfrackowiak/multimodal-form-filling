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
  --out /tmp/inventory.yaml
```

`--manifest` only if the yaml lacks `id` or `source_span` on a requirement.

Vertex Gemini (`gemini-2.5-flash`, ADC). Images are downscaled before the call.
One Vertex worker per unique image, capped at 12 (`CV_MAX_WORKERS` / `--workers`).

Offline checks: `python -m cv.test_offline`
