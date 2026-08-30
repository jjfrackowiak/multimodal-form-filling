"""`mff_manifest` imports no agent framework and no model library.

Extraction sits behind `RequirementExtractor`; the implementation (an ADK agent prompting
Gemma) lives in the editor service, which owns all model access. This proves the boundary
two ways: statically, by parsing every module's AST without executing it (so the check
cannot be fooled by an import that only happens not to run today), and at runtime, by
confirming importing the package never pulls a model library into `sys.modules`. The
workspace `import-linter` contract enforces the same rule across the repo; this test
enforces it for this package specifically and needs no other package's config to pass.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "mff_manifest"

# Mirrors the workspace import-linter contract's forbidden_modules for
# "no module outside llm/ and agents/ imports a model library".
FORBIDDEN_TOP_LEVEL = {"google", "pydantic_ai", "anthropic", "openai", "vertexai", "litellm"}


def _imported_top_level_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_no_source_file_imports_a_model_library() -> None:
    py_files = sorted(SRC.rglob("*.py"))
    assert py_files, "expected source files under src/mff_manifest"

    for path in py_files:
        imported = _imported_top_level_names(path.read_text(encoding="utf-8"))
        offending = imported & FORBIDDEN_TOP_LEVEL
        assert not offending, f"{path.relative_to(SRC.parent.parent)} imports {offending}"


def test_importing_the_package_never_touches_a_model_library_in_sys_modules() -> None:
    # A fresh interpreter, not this process: sys.modules here may already carry pytest's
    # own plugins (and, in this repo, mff-vision's pyyaml et al. from the shared venv),
    # which would make an in-process check meaningless.
    probe = (
        "import sys\n"
        "import mff_manifest\n"
        f"forbidden = {sorted(FORBIDDEN_TOP_LEVEL)!r}\n"
        "hit = sorted(m for m in forbidden if m in sys.modules)\n"
        "assert not hit, hit\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
