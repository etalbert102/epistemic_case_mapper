from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown


def reader_memo_edit_artifact_paths(artifacts: Path) -> dict[str, Path]:
    return {
        "memo_final_diagnosis": artifacts / "memo_final_diagnosis.json",
        "memo_protected_spans": artifacts / "memo_protected_spans.json",
        "memo_coherence_edits": artifacts / "memo_coherence_edits.json",
        "memo_prose_edits": artifacts / "memo_prose_edits.json",
        "reader_memo_coherence_prompt": artifacts / "reader_memo_coherence_prompt.txt",
        "reader_memo_coherence_raw": artifacts / "reader_memo_coherence_raw.txt",
        "reader_memo_prose_prompt": artifacts / "reader_memo_prose_prompt.txt",
        "reader_memo_prose_raw": artifacts / "reader_memo_prose_raw.txt",
    }


def write_reader_memo_edit_artifacts(rewrite_result: dict[str, Any], paths: dict[str, Path]) -> None:
    write_json(paths["memo_final_diagnosis"], rewrite_result.get("diagnosis", {}))
    write_json(paths["memo_protected_spans"], rewrite_result.get("protected_spans", {}))
    reports_by_pass = _reports_by_pass(rewrite_result)
    write_json(paths["memo_coherence_edits"], reports_by_pass.get("coherence", {}))
    write_json(paths["memo_prose_edits"], reports_by_pass.get("prose", {}))
    prompts = rewrite_result.get("prompts", {}) if isinstance(rewrite_result.get("prompts"), dict) else {}
    raws = rewrite_result.get("raws", {}) if isinstance(rewrite_result.get("raws"), dict) else {}
    _write_optional_markdown(paths["reader_memo_coherence_prompt"], prompts.get("coherence"))
    _write_optional_markdown(paths["reader_memo_coherence_raw"], raws.get("coherence"))
    _write_optional_markdown(paths["reader_memo_prose_prompt"], prompts.get("prose"))
    _write_optional_markdown(paths["reader_memo_prose_raw"], raws.get("prose"))


def reader_memo_edit_summary_paths(rewrite_result: dict[str, Any], paths: dict[str, Path]) -> dict[str, Path | None]:
    prompts = rewrite_result.get("prompts", {}) if isinstance(rewrite_result.get("prompts"), dict) else {}
    raws = rewrite_result.get("raws", {}) if isinstance(rewrite_result.get("raws"), dict) else {}
    return {
        "memo_final_diagnosis": paths["memo_final_diagnosis"],
        "memo_protected_spans": paths["memo_protected_spans"],
        "memo_coherence_edits": paths["memo_coherence_edits"],
        "memo_prose_edits": paths["memo_prose_edits"],
        "reader_memo_coherence_prompt": paths["reader_memo_coherence_prompt"] if prompts.get("coherence") else None,
        "reader_memo_coherence_raw": paths["reader_memo_coherence_raw"] if raws.get("coherence") else None,
        "reader_memo_prose_prompt": paths["reader_memo_prose_prompt"] if prompts.get("prose") else None,
        "reader_memo_prose_raw": paths["reader_memo_prose_raw"] if raws.get("prose") else None,
    }


def _reports_by_pass(rewrite_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pass_reports = rewrite_result.get("report", {}).get("passes", [])
    return {
        str(report.get("pass")): report
        for report in pass_reports
        if isinstance(report, dict) and str(report.get("pass", "")).strip()
    }


def _write_optional_markdown(path: Path, value: Any) -> None:
    if str(value or "").strip():
        write_markdown(path, str(value))
