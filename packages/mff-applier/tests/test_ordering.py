"""Fractional ordering (req 14) — LexoRank/Figma-style midpoint keys.

Every case here checks two things at once: the new key sorts where intended, and it never
requires touching a key that already exists.
"""

from __future__ import annotations

import pytest

from mff_applier import key_after, key_before, key_between


def test_first_key_with_no_bounds_at_all() -> None:
    key = key_between(None, None)
    assert isinstance(key, str) and key


def test_key_after_sorts_after_its_lower_bound() -> None:
    first = key_after(None)
    second = key_after(first)
    assert first < second


def test_key_before_sorts_before_its_upper_bound() -> None:
    last = key_before(None)
    earlier = key_before(last)
    assert earlier < last


def test_key_between_sorts_strictly_between_two_bounds() -> None:
    lo, hi = "a0", "a5"
    mid = key_between(lo, hi)
    assert lo < mid < hi


def test_key_between_with_equal_leading_digits_goes_deeper_without_extending() -> None:
    # "a0" and "a5" share their first digit ('a'), so the midpoint must be found at the
    # second digit rather than the first — this exercises the "still constrained by both
    # bounds, go deeper" branch as distinct from the "bounds just went adjacent" branch.
    mid = key_between("a0", "a5")
    assert mid == "a2"


def test_key_between_adjacent_bounds_extends_the_string() -> None:
    # "8" and "9" are adjacent base-36 digits: there is no character strictly between them,
    # so a correct implementation must extend rather than fail or (worse) reuse one of the
    # bounds.
    mid = key_between("8", "9")
    assert "8" < mid < "9"
    assert len(mid) > 1


def test_repeated_appends_after_the_top_of_the_alphabet_extend_the_string() -> None:
    # Walking key_after forward 80 times forces the "adjacent digit" extension path
    # repeatedly, not just once, and every key produced must still be unique and ordered.
    keys = [key_after(None)]
    for _ in range(80):
        keys.append(key_after(keys[-1]))
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)
    assert max(len(k) for k in keys) > 1


def test_appends_stay_in_insertion_order() -> None:
    keys = [key_after(None)]
    for _ in range(50):
        keys.append(key_after(keys[-1]))
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


def test_key_between_malformed_equal_value_bounds_raises_instead_of_looping() -> None:
    # "5" and "50" compare `<` as raw strings but denote the same base-36 fraction (a
    # trailing zero digit contributes nothing) — the one input shape this function cannot
    # satisfy. It must fail loudly rather than loop forever.
    with pytest.raises(ValueError, match="no midpoint"):
        key_between("5", "50")
