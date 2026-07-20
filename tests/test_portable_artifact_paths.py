from __future__ import annotations

import re
from pathlib import Path

from scripts.run_investigator_challenge import _portable_path


HOST_LOCAL_PATH = re.compile(r"(?:/Users/|/home/[^/\s]+/|[A-Za-z]:\\Users\\)")
TEXT_SUFFIXES = {".csv", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}


def test_portable_path_is_relative_to_its_declared_base(tmp_path: Path) -> None:
    base = tmp_path / "run"
    artifact = base / "raw" / "case" / "response.md"

    assert _portable_path(artifact, base) == "raw/case/response.md"


def test_project_controlled_artifacts_have_no_host_local_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for directory in ("docs", "examples", "scripts"):
        for path in (repo_root / directory).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if HOST_LOCAL_PATH.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(repo_root).as_posix())

    assert offenders == []
