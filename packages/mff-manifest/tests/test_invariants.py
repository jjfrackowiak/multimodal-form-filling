"""Provenance is an invariant, not a score.

Every `source_span` must be a verbatim substring of `raw`, and `ordinal ==
raw.index(source_span)`. A violation is a hard failure — the parser raises, it never
returns a `Manifest` carrying a bad span, and it never just scores lower.
"""

from __future__ import annotations

import pytest
from fakes import ScriptedExtractor
from golden import GOLDEN_REQUIREMENTS, RAW, unresolved

from mff_manifest import ManifestParseError, parse_manifest


async def test_every_source_span_is_verbatim_in_raw() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    assert manifest.requirements  # the invariant is vacuous, and therefore untested, on []
    for req in manifest.requirements:
        assert req.source_span in manifest.raw
        if req.constraint is not None:
            assert req.constraint.source_span in manifest.raw


async def test_every_ordinal_equals_raw_index_of_its_span() -> None:
    extractor = ScriptedExtractor(script=[unresolved()])
    manifest = await parse_manifest(RAW, extractor=extractor)

    assert manifest.requirements
    for req in manifest.requirements:
        assert req.ordinal == manifest.raw.index(req.source_span)


async def test_a_non_verbatim_requirement_span_is_a_hard_failure_after_retries_exhaust() -> None:
    bad = GOLDEN_REQUIREMENTS[0].model_copy(update={"source_span": "this text is not in raw"})
    extractor = ScriptedExtractor(script=[[bad], [bad], [bad]])

    with pytest.raises(ManifestParseError):
        await parse_manifest(RAW, extractor=extractor)

    # It re-asked, rather than failing on the first bad response.
    assert len(extractor.calls) == 3


async def test_a_non_verbatim_constraint_span_is_also_a_hard_failure() -> None:
    bad_constraint = GOLDEN_REQUIREMENTS[3].constraint
    assert bad_constraint is not None
    bad = GOLDEN_REQUIREMENTS[3].model_copy(
        update={"constraint": bad_constraint.model_copy(update={"source_span": "not in raw"})}
    )
    extractor = ScriptedExtractor(script=[[bad], [bad], [bad]])

    with pytest.raises(ManifestParseError):
        await parse_manifest(RAW, extractor=extractor)


async def test_never_returns_a_silently_truncated_list() -> None:
    """A chunk that partially fails must not just drop the offending requirement and
    return the rest — the caller gets a raised error or the full, valid `Manifest`."""
    bad = GOLDEN_REQUIREMENTS[0].model_copy(update={"source_span": "does not exist in raw"})
    good = GOLDEN_REQUIREMENTS[1]
    extractor = ScriptedExtractor(script=[[good, bad], [good, bad], [good, bad]])

    with pytest.raises(ManifestParseError):
        await parse_manifest(RAW, extractor=extractor)
