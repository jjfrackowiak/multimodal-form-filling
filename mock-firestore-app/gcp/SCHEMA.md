# Firestore vs bucket

Dokument w kolekcji `jobs/{jobId}`:

```
id            string
status        uploaded | queued | running | done | failed
createdAt     ISO timestamp
updatedAt     ISO timestamp
file.bucket   nazwa bucketa
file.path     obiekt w buckecie, np. uploads/{jobId}/raport.pdf
file.gsUri    gs://bucket/path   ← to jest „odniesienie do pliku”
file.originalName
file.contentType
file.sizeBytes
result        obiekt albo null
error         string albo null
```

Zasada: **plik w Cloud Storage, metadane i status w Firestore.**
Nigdy nie wrzucaj PDF/obrazu jako pola dokumentu.

Indeks: query workera `status == queued` wymaga composite/single-field index
(emulator tworzy sam; na produkcji Firestore podpowie link przy pierwszym query).
