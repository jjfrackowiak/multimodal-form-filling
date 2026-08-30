# Firestore vs bucket

Document in collection `jobs/{jobId}`:

```
id            string
status        uploaded | queued | prepared | processing | done | failed
step          null | prepare | process
createdAt     ISO timestamp
updatedAt     ISO timestamp
file.bucket   bucket name
file.path     object in the bucket, e.g. uploads/{jobId}/report.pdf
file.gsUri    gs://bucket/path   ← file reference
file.originalName
file.contentType
file.sizeBytes
result        object or null
error         string or null
```

Rule: **file in Cloud Storage, metadata and status in Firestore.**
Never store a PDF/image as a document field.

CV does not read this collection. The editor calls `POST /v1/inventory` with
`gs://` URIs (see `cv/integration_guide_CV.md`).

`step` is which unit last ran or failed. A crash in CV does not erase the job; it stays `processing`/`failed` until you retry that step.
