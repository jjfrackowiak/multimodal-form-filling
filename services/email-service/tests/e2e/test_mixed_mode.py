from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_mixed_mode_demo_exercises_complete_offline_pipeline(repo_root: Path) -> None:
    script = repo_root / "scripts" / "e2e_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "B9 e2e demo: PASS" in completed.stdout
    assert "RequestResult status: done" in completed.stdout
    assert "jobs done: 2; attachments: 2" in completed.stdout
    assert "PASS  156/156 checks passed" in completed.stdout
    for requirement_id in (f"R-{index:02d}" for index in range(1, 11)):
        assert requirement_id in completed.stdout
