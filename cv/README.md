# CV tool (Cloud Run)

The AI editor calls this over HTTP. Same payload as `mff-vision` / `HttpVisionTool`.

**Integration:** [`integration_guide_CV.md`](integration_guide_CV.md)  
**Deploy:** [`DEPLOY.md`](DEPLOY.md)

```
POST /v1/inventory
{
  "images": [{"uri": "gs://bucket/jobs/.../a.jpg"}],
  "requirements": [{"id": "R-01", "text": "A photograph of the front of the vehicle."}]
}
```

Photos are `gs://` JPEG/PNG/WebP. Not HEIC. Not bytes in the body.
Look-for is `text`. Omit `manifest` when every requirement has `id` + `text`.

```python
from cv import CvClient
resp = CvClient().inventory(
    [{"id": "R-01", "text": "A photograph of the front of the vehicle."}],
    images=["gs://bucket/jobs/abc/front.jpg"],
)
```

## Local CLI

```bash
python -m cv fixtures/fleet-vehicle-return/input/netnew/WN-7020U \
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
