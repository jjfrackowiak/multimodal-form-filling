"""Package imports cleanly and exposes the applier's public surface."""

from __future__ import annotations

import mff_applier


def test_package_exports_the_applier_surface() -> None:
    assert set(mff_applier.__all__) == {
        "ApplyResult",
        "Overwrite",
        "Rejection",
        "apply_slice",
        "key_after",
        "key_before",
        "key_between",
    }
