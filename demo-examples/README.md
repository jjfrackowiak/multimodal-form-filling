# Demo examples

Ready-to-send inputs for both modes, built from the same real vehicle-return
photo submission as [`fixtures/amendo-demo/`](../fixtures/amendo-demo/) (13
requirements — see that fixture's manifest for the full checklist).

To try it: paste `manifest-email-body.txt` as the email body, attach one or
both of the zips below, and send to the demo mailbox.

```
manifest-email-body.txt   THE EMAIL BODY — paste verbatim, never as an attachment

derivative.zip             DERIVATIVE path — 3 forms, same photos, submitted
  derivative/                 by a different amount of the written info filled in
    Vehicle Return Report - Complete Submission.docx
    Vehicle Return Report - Missing Fuel Level.docx
    Vehicle Return Report - Missing Accessories List.docx

net-new.zip                 NET-NEW path — one folder, no form supplied yet
  net-new/WN-7020U/            17 photos (15 distinct) + 2 text files
```

Sending all 3 derivative forms together is deliberate: they share every
requirement id, so the reply's per-form labelling (which comment belongs to
which of the three filenames) is the thing actually worth watching for.

Regenerate from source: `fixtures/amendo-demo/`.
