"""mff-contracts — the frozen wire contract.

Everything else in this repository is written against these models. No branch may edit
this package; a change request goes back through the layer-0 owner. It depends on
**pydantic and nothing else** (enforced by import-linter).

See `docs/app-implementation-plan.md`, "The contract to freeze first (`mff-contracts`)".
"""

from __future__ import annotations

from .artifacts import Artifact, DerivativeArtifact, NetNewArtifact
from .blobs import (
    BlobRef,
    Finding,
    ImageAnalysis,
    JobImage,
    RequirementHit,
    RequirementSpec,
)
from .compiled import CompiledForm, RenderMap, RunSpan
from .docmodel import DraftOp, Entry, FormDraft, Node, Section
from .jobs import (
    ClientInputs,
    IntakeProblem,
    IntakeVerdict,
    JobCursor,
    JobRecord,
    JobRequest,
    Mode,
    RequestAccepted,
    RequestRecord,
    RequestResult,
)
from .repositories import ArtifactRepository, BlobStore, JobRepository, RequestRepository
from .requirements import Constraint, Manifest, Requirement, SlicePlan
from .review import Anchor, ReviewComment
from .slices import SliceReport, SliceRequest

__all__ = [
    "Anchor",
    "Artifact",
    "ArtifactRepository",
    "BlobRef",
    "BlobStore",
    "ClientInputs",
    "CompiledForm",
    "Constraint",
    "DerivativeArtifact",
    "DraftOp",
    "Entry",
    "Finding",
    "FormDraft",
    "ImageAnalysis",
    "IntakeProblem",
    "IntakeVerdict",
    "JobCursor",
    "JobImage",
    "JobRecord",
    "JobRepository",
    "JobRequest",
    "Manifest",
    "Mode",
    "NetNewArtifact",
    "Node",
    "RenderMap",
    "RequestAccepted",
    "RequestRecord",
    "RequestRepository",
    "RequestResult",
    "Requirement",
    "RequirementHit",
    "RequirementSpec",
    "ReviewComment",
    "RunSpan",
    "Section",
    "SlicePlan",
    "SliceReport",
    "SliceRequest",
]
