from pathlib import Path

from scripts.validate_worked_regions import _require_no_template_status, _require_no_todo


def test_worked_region_validator_rejects_templates(tmp_path: Path) -> None:
    path = tmp_path / "template.md"
    path.write_text("# Demo\n\nStatus: `template`\n\nTODO\n", encoding="utf-8")
    failures: list[str] = []

    _require_no_template_status(path, failures)
    _require_no_todo(path, failures)

    assert any("template_not_filled" in failure for failure in failures)
    assert any("todo_remaining" in failure for failure in failures)
