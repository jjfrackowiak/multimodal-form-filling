"""Fractional ordering for `Entry.order` — req 14 (surgical, no full regeneration).

`Entry.order` is a string, compared lexicographically. Minting a key for a new entry must
never touch any sibling's key — that is the entire reason the field is a string rather
than an integer index. This is the LexoRank/Figma approach: treat each key as the digits
of a base-36 fraction, and find a key whose value sits strictly between two bounds by
walking digit by digit, extending the string only where two keys are "adjacent" (their
digits leave no room for a midpoint).

`None` stands for an open bound: no lower bound (before everything) or no upper bound
(after everything, the common case — appending after the last entry in a section).
"""

from __future__ import annotations

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_BASE = len(_ALPHABET)  # 36
# One past the last real digit — stands in for "no upper bound" while walking digits, so
# the open-ended case (`hi is None`) and the bounded case share one loop.
_OPEN = _BASE
# A hard ceiling on how many digits key_between will walk before giving up. Every key this
# package mints is canonical (no key is value-equal to a shorter prefix of itself padded
# with zero digits — see `key_between`'s docstring), so real usage never approaches this;
# it exists so a caller who breaks that invariant gets a ValueError, not a frozen process.
_MAX_DIGITS = 1000


def _digit_at(key: str, index: int) -> int:
    """The digit `key` has at `index`, treating a key as a base-36 fraction with an
    implicit infinite run of zero digits past its own length (so "5" == "50" == "500")."""
    if index >= len(key):
        return 0
    return _ALPHABET.index(key[index])


def key_between(lo: str | None, hi: str | None) -> str:
    """Mint a key whose value is strictly between `lo` and `hi`.

    `lo=None` means "no lower bound", `hi=None` means "no upper bound". Caller must ensure
    `lo` has strictly smaller *value* than `hi` when both are given — every key this
    package mints satisfies that against its siblings, so this holds for real `order`
    strings. It is not the same as `lo < hi` as raw strings: `"5"` and `"50"` compare `<`
    as strings but are the same fraction, which is exactly the malformed input the
    iteration cap below turns into a `ValueError` instead of an infinite loop.
    """
    lo_key = lo or ""
    hi_key = hi or ""  # only read when hi_open is False, at which point hi is not None
    hi_open = hi is None  # once true, stays true: the upper bound became unconstrained
    digits: list[str] = []
    index = 0
    while True:
        if index >= _MAX_DIGITS:
            raise ValueError(f"key_between: no midpoint between lo={lo!r} and hi={hi!r}")
        lo_digit = _digit_at(lo_key, index)
        hi_digit = _OPEN if hi_open else _digit_at(hi_key, index)
        if hi_digit - lo_digit > 1:
            mid = lo_digit + (hi_digit - lo_digit) // 2
            digits.append(_ALPHABET[mid])
            return "".join(digits)
        # No room at this digit: copy lo's digit through unchanged and go deeper. Once
        # the two bounds were merely adjacent here (not equal), every deeper digit of hi
        # is unconstrained, because the prefix so far already sorts below hi's.
        if hi_digit - lo_digit == 1:
            hi_open = True
        digits.append(_ALPHABET[lo_digit])
        index += 1


def key_after(lo: str | None) -> str:
    """Mint a key that sorts after `lo` (or as the first key, if `lo` is None)."""
    return key_between(lo, None)


def key_before(hi: str | None) -> str:
    """Mint a key that sorts before `hi` (or as the first key, if `hi` is None)."""
    return key_between(None, hi)
