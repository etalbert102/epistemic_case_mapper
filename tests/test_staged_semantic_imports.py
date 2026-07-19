from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_claim_relation_module_imports_first_in_fresh_process() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import epistemic_case_mapper.pipeline.map.staged_semantic_claims_relations as module; print(module.__name__)",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("staged_semantic_claims_relations")
