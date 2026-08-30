#!/usr/bin/env python3
"""Shim — prefer `python -m cv.eval`."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cv.eval import main

if __name__ == "__main__":
    raise SystemExit(main())
