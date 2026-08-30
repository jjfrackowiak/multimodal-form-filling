# Fixture — fleet vehicle return condition

A real photo submission for a vehicle return inspection, with a real client-written
manifest, used as golden data for the L1, L2, L3 and E1 evals.

**Vehicle:** Nissan Qashqai, 59 650 km. Photographed at a filling station, 30 Aug 2026.

## Files

```
manifest.txt                        THE EMAIL BODY — the client's text, verbatim
inventory.yaml                      human labels; stands in for vision until the real service
expected_requirements.yaml          L1 ground truth — the golden manifest parse

input/
  derivative/form_supplied.docx     one DERIVATIVE job — photos embedded in the .docx
  netnew/WN-7020U/                  one NET-NEW job — the folder IS the set of inputs
    dane-pojazdu.txt                  }  ClientInputs.texts
    uwagi.txt                         }
    *.jpg                             17 files, 15 distinct — JobRequest.images

expected_output/
  report_reviewed.docx              the golden OUTPUT — 10 real Word comments
  delivery.txt                      the results email — where provenance lives
  review.yaml                       the review layer, as data
  structure.yaml                    THE EVAL TARGET

check_output.py                     the reference evaluator — deterministic, offline
```

## The two modes, as a client actually sends them

The **manifest is the email body**, never an attachment. Attachments are work items:

| | Derivative | Net-new |
|---|---|---|
| Arrives as | a `.docx`, in a `derivative.zip` | a **folder**, in a `net-new.zip` |
| Photos | embedded in the document | loose in the folder |
| Text | in the document | `.txt` files in the folder |
| `form_id` | the filename | **the folder name** — the client's own label |

`WN-7020U` is the registration, because that is what a person would name the folder.

**Containment is how a client says what belongs to what.** An image in `WN-7020U/` belongs
to the `WN-7020U` job — no naming convention, no metadata file.

An earlier version of this fixture had `client_inputs.yaml`, a single structured file with
`vehicle:` and `notes:` keys. It was invented before the real shape was known and described
something no client would send. Replaced.

## One output, two inputs

The two modes take **different inputs and converge on the same output**:

| | Derivative | Net-new |
|---|---|---|
| Input | `form_supplied.docx` | `client_inputs.yaml` |
| Artifact seeded by | parsing the client's document | generating a scaffold |
| Verdict vocabulary | `pass` / `fail` | `realised` / `shortfall` |
| Output | ← the same document, same 10 comments, same 2 failures → |

The body coincides here **by construction** — the golden output was generated from the
same section layout as the submitted form, so the scaffold and the client's form have
the same shape. In the wild a client's document will not match our scaffold, and
derivative must preserve their body verbatim while net-new authors ours. What is
invariant across modes in every case is the **review layer**: the same ten
requirements, the same two failures, the same justifications and suggestions.

## Comments cite numbers; the delivery explains them

Comments carry `[R-04]` and nothing more. An earlier version repeated verbatim manifest
spans inside every comment, on the argument that a bare requirement id tells the client
nothing — which holds only if the id is never explained.

`delivery.txt` explains them. It carries every requirement's text alongside the manifest
span and line it was read from, including R-04's constraint six lines from its subject and
R-01's recorded ambiguity. Stated once, rather than repeated in ten comments.

The evaluator asserts both halves, and **a comment containing a verbatim citation now
fails** — otherwise the fixture would go on quietly asserting the superseded rule.

## The evaluator is structural, not a judge

`expected_output/structure.yaml` is what the eval actually asserts — not similarity
against `report_reviewed.docx`. A text comparison would fail on a harmlessly reworded
justification while passing a document with the wrong verdicts.

```
$ python check_output.py expected_output/report_reviewed.docx      # needs python-docx>=1.2
PASS  156/156 checks passed
```

156 assertions, no API key, no model. They cover the document, the review layer, inline
anchoring, the computed slice ordinals, and the delivery email. The pipeline that produces the document is
non-deterministic; whether the document is complete in every aspect is not.

### The checker is mutation-tested

An evaluator that has only ever seen correct output may be asserting nothing at all.
Five deliberate regressions, all caught:

| Mutation | Result |
|---|---|
| A comment carries a verbatim citation *(the old contract)* | caught |
| `R-04` flipped `fail` → `pass` | caught |
| A failing requirement loses its suggestion | caught |
| `R-04`'s ordinal no longer matches its manifest offset | caught |
| A delivery quote paraphrased instead of quoted | caught |
| A requirement dropped from the delivery list | caught |
| *golden output (control)* | **passes — 156/156** |

**Two of these originally passed**, and both were real holes in the checker.

An earlier round: the field extractor split on `Uzasadnienie:` and took everything to the
end of the comment, so a one-character justification still measured over ten. Fixed by
bounding each field at the next marker.

This round: the delivery check tested whether a requirement id appeared *anywhere* in the
email — and every id also appears in the pass/fail summary, so dropping one from the
requirement list still passed. Now scoped to the list section, and each entry must carry
the manifest span it was read from.

> **`python-docx` must be pinned `>=1.2`.** Verified here: 1.1.0 has no comment support
> at all, and 1.2.0 provides `Document.add_comment(runs, text, author, initials)` and an
> iterable `Document.comments`. There is **no** `Run.add_comment` — that appears in the
> project's design notes as a proposal, not as shipped API. B1 should not plan around it.

## Why this fixture is worth keeping

It was not constructed to be tidy, and every defect in it is one a real submission
produces. Four things make it hard in useful ways.

### 1. The headliner case — the reason this fixture exists

The manifest asks for `2x podsufitka` (two headliner photographs) on line 4, and
then adds the qualifier on line 10: `Podsufitka trzeba spomiędzy forteli zrobić` —
*the headliner has to be shot from between the seats*.

Two headliner photographs were supplied. One satisfies the constraint, one does not:

- `1000040420.jpg` — **correct.** Taken from between the front seats: both front
  headrests are in frame, the overhead console is visible, and the whole headliner
  sweeps back to the rear window.
- `IMG_20260830_132755 (5).jpg` — **incorrect.** Taken from beside a seat; only the
  rear section of the headliner is framed.

The requirement is therefore **superficially met and substantively failed**. Any
checker that counts photographs per category passes this submission. That is the
defect class this fixture exists to catch, and it is the primary L2/L3 case.

Note also *where* the constraint sits: six lines away from the item it qualifies.
A parser that splits the manifest line-by-line will attach it to the wrong
requirement or drop it entirely.

### 2. A genuine ambiguity in the manifest

`Pod maską` appears **twice**, on lines 2 and 5. Read as one repeated item the list
totals 15 photographs; read as two distinct shots it totals 16 — which is the number
the client themselves wrote on line 1.

The golden data commits to the second reading (two engine-bay photos required, one
supplied, so `R-01` fails). This is a judgement call, and it is recorded as one in
`expected_requirements.yaml` rather than hidden. If the client later says otherwise,
that file changes and the eval follows.

### 3. Typos and inflection, preserved

`że środka` (for `ze środka`), `forteli` (for `foteli`), `przekatne` (missing
diacritic). Do not clean these up. Real manifests arrive like this, and the L1 eval
asserts that every `source_span` is a **verbatim** substring of `manifest.txt` — so
normalising the input would quietly invalidate the provenance check.

### 4. Duplicate files

17 files were delivered; only **15 are distinct**. Two pairs are byte-identical:

- `1000040429.jpg` = `IMG_20260830_132755 (8).jpg`
- `IMG_20260830_132603.jpg` = `IMG_20260830_132755 (7).jpg`

Content-addressing `BlobRef` by `sha256` collapses these on ingest, so they should
never reach an agent as separate images. That is a cheap deterministic assertion and
`expected_verdicts.yaml` records it as one.

## Coverage

The submission maps to the manifest as follows — 10 requirements, **2 failing**:

| Req | Item | Verdict |
|---|---|---|
| R-01 | engine bay ×2 | **fail** — only one supplied |
| R-02 | seats ×4 | pass |
| R-03 | vehicle diagonals ×2 | pass |
| R-04 | headliner ×2, from between the seats | **fail** — one shot from the wrong position |
| R-05 | windscreen, interior | pass |
| R-06 | windscreen, exterior | pass |
| R-07 | tyre tread | pass |
| R-08 | boot | pass |
| R-09 | equipment under the boot floor | pass |
| R-10 | instrument cluster | pass |

## Two things to decide before this repo goes public

1. **The number plate is legible** in several frames (`IMG_20260830_132755 (10).jpg`,
   `IMG_20260830_132755 (9).jpg`). Redact, or keep the repository private.
2. **A person is identifiable** through the glass in `IMG_20260830_132754 (1).jpg`.

Neither affects the fixture's usefulness — both can be blurred without touching any
of the graded criteria, since no verdict depends on either region.

## Using it before the vision module exists

Image understanding (req 13) is stubbed until **B11**. Until then `inventory.yaml`
stands in for the model's eyes: the derivative flow is evaluated against the human
labels rather than against pixels. That keeps L3 runnable now, and when B11 lands the
same file becomes the answer key the vision module itself is scored against.

## Maintaining this fixture

The generators that produced `form_supplied.docx` and `report_reviewed.docx` have been
removed — the fixture is data now, not a build. Two consequences worth knowing:

- `review.yaml` and `report_reviewed.docx` are no longer mechanically linked. If you
  change a verdict in `review.yaml`, the golden `.docx` will **not** follow, and the
  two will drift apart silently. Change both, or regenerate the document.
- `structure.yaml` is the file the evaluator actually reads. It is the one to edit when
  the expected outcome changes; the `.docx` is a human reference.
