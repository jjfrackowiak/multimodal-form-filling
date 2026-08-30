# Firestore vs bucket

Document in collection `jobs/{jobId}`:

```
id            string
status        uploaded | queued | running | done | failed
createdAt     ISO timestamp
updatedAt     ISO timestamp
file.bucket   bucket name
file.path     object in the bucket, e.g. uploads/{jobId}/report.pdf
file.gsUri    gs://bucket/path   ← this is the file reference
file.originalName
file.contentType
file.sizeBytes
result        object or null
error         string or null
```

Rule: **file in Cloud Storage, metadata and status in Firestore.**
Never store a PDF/image as a document field.

Index: the worker query `status == queued` needs a composite/single-field index
(the emulator creates it; in production Firestore will suggest a link on the first query).
