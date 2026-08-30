"""Makes `tests/delivery` a package so its `conftest.py` gets a distinct module name
under mypy (`delivery.conftest`) rather than colliding with `tests/transport/conftest.py`
(both are bare top-level `conftest` without this, and mypy type-checks a service's whole
`tests/` tree in one run — see `pyproject.toml`, `[tool.mypy]`). Pytest handles a
package-style test directory identically to a package-less one; nothing else changes.
"""

from __future__ import annotations
