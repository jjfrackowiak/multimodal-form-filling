"""ADK has no `output_validator`/`ModelRetry` pair — this is the explicit, plain-Python
stand-in: validate the returned spans, and re-ask on structural failure, capped."""

from __future__ import annotations

import pytest

from mff_manifest import DEFAULT_MAX_ATTEMPTS, ManifestParseError, parse_manifest

from fakes import ScriptedExtractor
from golden import GOLDEN_REQUIREMENTS, RAW, unresolved


async def test_recovers_on_the_second_attempt() -> None:
    bad = GOLDEN_REQUIREMENTS[0].model_copy(update={"source_span": "not present in raw"})
    extractor = ScriptedExtractor(script=[[bad], unresolved()])

    manifest = await parse_manifest(RAW, extractor=extractor)

    assert len(extractor.calls) == 2
    assert [r.id for r in manifest.requirements] == [f"R-{i:02d}" for i in range(1, 11)]


async def test_the_retry_prompt_names_the_offending_span() -> None:
    bad_span = "not present in raw"
    bad = GOLDEN_REQUIREMENTS[0].model_copy(update={"source_span": bad_span})
    extractor = ScriptedExtractor(script=[[bad], unresolved()])

    await parse_manifest(RAW, extractor=extractor)

    first_chunk, _offset = extractor.calls[0]
    second_chunk, _offset2 = extractor.calls[1]
    assert bad_span not in first_chunk  # the original chunk never contained the bad span
    assert bad_span in second_chunk  # the retry prompt calls it out explicitly
    assert first_chunk in second_chunk  # and still carries the original text


async def test_default_cap_is_three_attempts() -> None:
    bad = GOLDEN_REQUIREMENTS[0].model_copy(update={"source_span": "never in raw"})
    extractor = ScriptedExtractor(script=[[bad]] * DEFAULT_MAX_ATTEMPTS)

    with pytest.raises(ManifestParseError):
        await parse_manifest(RAW, extractor=extractor)

    assert len(extractor.calls) == DEFAULT_MAX_ATTEMPTS


async def test_max_attempts_is_configurable() -> None:
    bad = GOLDEN_REQUIREMENTS[0].model_copy(update={"source_span": "never in raw either"})
    extractor = ScriptedExtractor(script=[[bad]] * 5)

    with pytest.raises(ManifestParseError):
        await parse_manifest(RAW, extractor=extractor, max_attempts=5)

    assert len(extractor.calls) == 5


async def test_caller_always_gets_a_manifest_or_a_raised_error_never_indexerror() -> None:
    # A script shorter than the attempts needed must fail with a clear assertion from the
    # test double, not an opaque IndexError bubbling out of parse_manifest.
    bad = GOLDEN_REQUIREMENTS[0].model_copy(update={"source_span": "absent"})
    extractor = ScriptedExtractor(script=[[bad]])

    with pytest.raises(AssertionError, match="script exhausted"):
        await parse_manifest(RAW, extractor=extractor)
