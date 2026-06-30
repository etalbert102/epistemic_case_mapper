from pathlib import Path

from scripts import validate_worked_regions
from scripts.validate_worked_regions import _require_no_template_status, _require_no_todo


def test_worked_region_validator_rejects_templates(tmp_path: Path) -> None:
    path = tmp_path / "template.md"
    path.write_text("# Demo\n\nStatus: `template`\n\nTODO\n", encoding="utf-8")
    failures: list[str] = []

    _require_no_template_status(path, failures)
    _require_no_todo(path, failures)

    assert any("template_not_filled" in failure for failure in failures)
    assert any("todo_remaining" in failure for failure in failures)


def test_worked_region_validator_accepts_single_region_selector(monkeypatch) -> None:
    selected: list[str] = []

    def fake_validate_region(repo_root: Path, manifest, region, failures: list[str]) -> None:
        selected.append(region.region_id)

    monkeypatch.setattr(validate_worked_regions, "_validate_region", fake_validate_region)
    monkeypatch.setattr(validate_worked_regions.sys, "argv", ["validate_worked_regions.py", "--region", "lhc_cosmic_ray_argument"])

    assert validate_worked_regions.main() == 0
    assert selected == ["lhc_cosmic_ray_argument"]
