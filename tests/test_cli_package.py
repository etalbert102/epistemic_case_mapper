from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from epistemic_case_mapper import cli_package
from epistemic_case_mapper.cli_package import _run


def test_run_uses_validation_script_from_supplied_repo_root(
    tmp_path: Path, monkeypatch,
) -> None:
    script = tmp_path / "scripts" / "validate_submission_manifest.py"
    script.parent.mkdir()
    script.write_text("raise SystemExit(0)\n", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = _run(
        tmp_path,
        ["scripts/validate_submission_manifest.py", "--check"],
        "package.yaml",
    )

    assert result == 0
    assert observed["command"] == [
        sys.executable,
        str(script),
        "--check",
        "--repo-root",
        str(tmp_path),
        "--manifest",
        "package.yaml",
    ]
    assert observed["cwd"] == tmp_path
    assert str(tmp_path / "src") in observed["env"]["PYTHONPATH"]  # type: ignore[index]


def test_run_fails_clearly_when_repo_validation_script_is_missing(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    monkeypatch.setattr(cli_package, "ENGINE_ROOT", tmp_path / "missing_engine")
    result = _run(
        tmp_path,
        ["scripts/validate_submission_manifest.py"],
        "package.yaml",
    )

    assert result == 2
    diagnostic = capsys.readouterr().err
    assert "package_command_unavailable" in diagnostic
    assert "missing_target_script" in diagnostic
    assert "missing_engine_script" in diagnostic
