"""The first six golden requirements from
`fixtures/fleet-vehicle-return/expected_requirements.yaml`, mirrored by hand — see
`packages/mff-manifest/tests/golden.py` for the precedent (all ten) and its rationale for
mirroring rather than parsing the yaml at test time.

Six is not an arbitrary slice: `Manifest.slices()` (mff_contracts.requirements) chunks in
groups of at most 6, so R-01..R-06 is exactly the first `SlicePlan` the fixture would
produce — one real `SliceRequest`, per the B8 brief, "rather than inventing one."
"""

from __future__ import annotations

from mff_contracts import (
    Anchor,
    BlobRef,
    Constraint,
    DerivativeArtifact,
    Mode,
    Node,
    Requirement,
    ReviewComment,
    SliceRequest,
)

JOB_ID = "job-fleet-vehicle-return"
SLICE_ID = "slice-01"
FORM_ID = "form_supplied.docx"

GOLDEN_REQUIREMENTS: list[Requirement] = [
    Requirement(
        id="R-01",
        ordinal=11,
        source_line=2,
        text="A photograph of the engine bay, taken with the bonnet open.",
        source_span="Pod maską",
        expected_count=2,
        ambiguity="repeated_verbatim_in_manifest",
    ),
    Requirement(
        id="R-02",
        ordinal=22,
        source_line=3,
        text="Four photographs of the seats.",
        source_span="4x fotele",
        expected_count=4,
    ),
    Requirement(
        id="R-03",
        ordinal=34,
        source_line=3,
        text="Two photographs of the vehicle taken on the diagonal.",
        source_span="2 przekatne pojazdu",
        expected_count=2,
    ),
    Requirement(
        id="R-04",
        ordinal=56,
        source_line=4,
        text=("Two photographs of the headliner. Each must be taken from between the front seats."),
        source_span="2x podsufitka",
        expected_count=2,
        constraint=Constraint(
            kind="camera_position",
            value="between_front_seats",
            source_span="Podsufitka trzeba spomiędzy forteli zrobić",
            source_line=10,
            note="'forteli' is a typo for 'foteli' (seats) in the client's original.",
        ),
    ),
    Requirement(
        id="R-05",
        ordinal=84,
        source_line=6,
        text="A photograph of the windscreen taken from inside the cabin.",
        source_span="Przednia szyba że środka i zewnątrz",
        expected_count=1,
    ),
    Requirement(
        id="R-06",
        ordinal=84,
        source_line=6,
        text="A photograph of the windscreen taken from outside the vehicle.",
        source_span="Przednia szyba że środka i zewnątrz",
        expected_count=1,
    ),
]


def node_id(requirement_id: str) -> str:
    """The (synthetic, test-only) node this fixture pretends satisfies `requirement_id`."""
    return f"node-{requirement_id}"


def golden_artifact(*, job_id: str = JOB_ID, form_id: str = FORM_ID) -> DerivativeArtifact:
    """A minimal but real `DerivativeArtifact`: one node per golden requirement, so
    `validate`'s anchor-resolution check has real ids to resolve against."""
    nodes = [
        Node(id=node_id(r.id), kind="paragraph", text=r.text, parent_id=None)
        for r in GOLDEN_REQUIREMENTS
    ]
    return DerivativeArtifact(
        job_id=job_id,
        form_id=form_id,
        source=BlobRef(
            uri=f"gs://mff-local/jobs/{job_id}/source/{'0' * 64}",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=2_800_000,
            sha256="0" * 64,
        ),
        nodes=nodes,
    )


def golden_slice_request(
    *,
    requirements: list[Requirement] | None = None,
    job_id: str = JOB_ID,
    slice_id: str = SLICE_ID,
) -> SliceRequest:
    reqs = GOLDEN_REQUIREMENTS if requirements is None else requirements
    return SliceRequest(
        job_id=job_id,
        slice_id=slice_id,
        mode=Mode.DERIVATIVE,
        requirements=reqs,
        artifact=golden_artifact(job_id=job_id),
    )


def make_comment(
    requirement_id: str,
    *,
    verdict: str = "pass",
    justification: str = "Requirement satisfied by the supplied photograph.",
    suggestion: str | None = None,
    target_id: str | None = None,
) -> ReviewComment:
    """A well-formed `ReviewComment` anchored at `node_id(requirement_id)` unless a
    different `target_id` is given (e.g. to script an unresolvable anchor)."""
    return ReviewComment(
        requirement_id=requirement_id,
        anchor=Anchor(kind="node", target_id=target_id or node_id(requirement_id)),
        verdict=verdict,
        justification=justification,
        suggestion=suggestion,
    )
