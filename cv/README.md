# CV tool (Cloud Run)

The AI editor calls this over HTTP. Same logic is available in-process.

**Integration:** [`integration_guide_CV.md`](integration_guide_CV.md)  
**Deploy:** [`DEPLOY.md`](DEPLOY.md)

```
POST /v1/inventory
{
  "checklist": { "requirements": [ { "id": "R-01", "text": "...", "source_span": "...", "expected_count": 1 } ] },
  "image_uris": ["gs://bucket/jobs/.../a.jpg"],
  "image_prefix": null,
  "manifest": null
}
```

Photos are `gs://` JPEG/PNG/WebP. Not HEIC. Not bytes in the body.

If every requirement already has `id` + `source_span`, `manifest` is omitted.

```python
from cv import CvClient
resp = CvClient().inventory(checklist, image_prefix="gs://bucket/jobs/abc/images/")
```

## Local CLI

```bash
python -m cv fixtures/fleet-vehicle-return/images \
  --requirements fixtures/fleet-vehicle-return/expected_requirements.yaml \
  --out /tmp/inventory.yaml
```

## In-process (tests / CLI only)

```python
from cv import build_inventory
from cv.checklist import load_checklist
from cv.images import list_images

inv = build_inventory(list_images(dir), load_checklist(yaml_path))
```

Production callers use HTTP so the editor does not embed Vertex.

Offline: `python -m cv.test_offline`
