from __future__ import annotations

from pathlib import Path

import json

from epistemic_case_mapper import cli
from epistemic_case_mapper.unseen_quality import init_quality_test, validate_quality_test
from test_submission_manifest_generalization import _write_transfer_fixture


def test_unseen_quality_init_and_check_lifecycle(tmp_path: Path) -> None:
    written = init_quality_test(
        tmp_path,
        "Urban Trees",
        "Urban Tree Canopy",
        "Should a city prioritize tree canopy expansion as a heat mitigation strategy?",
    )

    assert sorted(path.name for path in written) == [
        "BASELINE_COMPARISON.md",
        "QUALITY_REVIEW.md",
        "SCORECARD.md",
        "TEST_PROTOCOL.md",
    ]
    failures = validate_quality_test(tmp_path, "urban_trees")
    assert any("unseen_quality_placeholder" in failure for failure in failures)

    _write_completed_quality_docs(tmp_path, "urban_trees", "Urban Tree Canopy")

    assert validate_quality_test(tmp_path, "urban_trees") == []


def test_quality_cli_gate_accepts_completed_transfer_package(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)
    case_path = tmp_path / "data/cases/demo/case.yaml"
    case_path.write_text(
        case_path.read_text(encoding="utf-8").replace(
            "    source_type: test\n    path: data/cases/demo/sources/text/source_1.txt",
            "    source_type: test\n    provenance_level: local_note\n    evidence_role: implementation\n    needs_upgrade: true\n    limitations:\n      - Fixture source is not primary evidence.\n    path: data/cases/demo/sources/text/source_1.txt",
            1,
        ),
        encoding="utf-8",
    )
    init_quality_test(
        tmp_path,
        "demo_unseen",
        "Demo Unseen Case",
        "Can a synthetic package exercise the unseen quality gate?",
    )
    _write_completed_quality_docs(tmp_path, "demo_unseen", "Demo Unseen Case")

    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["ecm.py", "--repo-root", str(tmp_path), "quality", "gate", "--case", "demo_unseen"],
    )

    assert cli.main() == 0
    assert (tmp_path / "ui/index.html").exists()
    assert (tmp_path / "examples/demo/worked_map_json_export.json").exists()
    risk_tasks = tmp_path / "docs/unseen_case_tests/demo_unseen/GENERATED_RISK_TASKS.md"
    assert "demo_source_1" in risk_tasks.read_text(encoding="utf-8")
    ui_data = json.loads((tmp_path / "ui/data.json").read_text(encoding="utf-8"))
    warnings = ui_data["cases"][0]["qualityWarnings"]
    assert any(warning["label"] == "demo_source_1" for warning in warnings)


def test_unseen_quality_check_fails_closed_on_failed_criterion(monkeypatch, tmp_path: Path) -> None:
    _write_completed_quality_docs(tmp_path, "demo_unseen", "Demo Unseen Case")
    scorecard = tmp_path / "docs/unseen_case_tests/demo_unseen/SCORECARD.md"
    scorecard.write_text(
        scorecard.read_text(encoding="utf-8").replace(
            "| better_than_flat_baseline | pass |",
            "| better_than_flat_baseline | fail |",
        ),
        encoding="utf-8",
    )

    failures = validate_quality_test(tmp_path, "demo_unseen")
    assert any("unseen_quality_acceptance_failed" in failure for failure in failures)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["ecm.py", "--repo-root", str(tmp_path), "quality", "check", "--case", "demo_unseen"],
    )
    assert cli.main() == 1


def test_unseen_quality_check_fails_closed_on_nonpassing_overall_result(monkeypatch, tmp_path: Path) -> None:
    for overall in ("fail", "inconclusive"):
        case_slug = f"demo_{overall}"
        _write_completed_quality_docs(tmp_path, case_slug, f"Demo {overall.title()}")
        scorecard = tmp_path / f"docs/unseen_case_tests/{case_slug}/SCORECARD.md"
        scorecard.write_text(
            scorecard.read_text(encoding="utf-8").replace("Overall result: `pass`", f"Overall result: `{overall}`"),
            encoding="utf-8",
        )
        failures = validate_quality_test(tmp_path, case_slug)
        assert any(f"result={overall}" in failure for failure in failures)
        monkeypatch.setattr(
            cli.sys,
            "argv",
            ["ecm.py", "--repo-root", str(tmp_path), "quality", "check", "--case", case_slug],
        )
        assert cli.main() == 1


def _write_completed_quality_docs(repo_root: Path, case_slug: str, title: str) -> None:
    case_dir = repo_root / "docs/unseen_case_tests" / case_slug
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "TEST_PROTOCOL.md").write_text(
        f"""# {title} Unseen Case Test Protocol

Status: `complete`

## Case

The case asks whether a new package can produce useful source-grounded map artifacts.

## Why This Is Unseen

The case differs from prior examples in domain, source shape, and identifier grammar.

## Source Inclusion Rules

Use a balanced source packet with source IDs recorded in the case manifest.

## Baseline Isolation

The flat baseline is generated before reading the map, audit, checklist, or UI data.

## Budget

The test uses one short mapping pass, one package gate, and one human-review simulation.

## Success Criteria

The map must preserve at least one source-grounded crux that the flat baseline blurs.

## Failure Criteria

The test fails if sources are overclaimed, artifacts cannot be inspected, or the baseline is equally useful.
""",
        encoding="utf-8",
    )
    (case_dir / "QUALITY_REVIEW.md").write_text(
        f"""# {title} Quality Review

Status: `complete`

| Dimension | Score | Evidence |
| --- | --- | --- |
| Source fidelity | 4 | Claims point to source excerpts and can be challenged. |
| Load-bearing visibility | 4 | The important support and caveats are visible in claim rows. |
| Crux quality | 4 | The package identifies an implementation crux. |
| Relation usefulness | 3 | Relations are useful but still need human review. |
| Erosion audit quality | 4 | The audit names a concrete flat-synthesis loss. |
| Human reviewability | 4 | The checklist and source paths support review. |
| Generalizability | 4 | The package uses custom IDs and non-FLF labels. |
| Incremental extensibility | 3 | Another investigator could add sources through the manifest. |
| UI usefulness | 4 | The UI exposes generated package data. |
| Baseline improvement | 4 | The map preserves distinctions the flat baseline compresses. |

## Human Judge Simulation

The reviewer found the strongest support, named the central crux, and identified one claim to weaken.

## Adversarial Findings

One relation label may need revision, classified as a methodology weakness.

## Revision Decisions

The package is showable with the relation-label limitation recorded.
""",
        encoding="utf-8",
    )
    (case_dir / "BASELINE_COMPARISON.md").write_text(
        f"""# {title} Baseline Comparison

Status: `complete`

## Flat Baseline Summary

The flat baseline gives a concise answer but compresses implementation uncertainty.

## Map Preserved

The map preserves which claim carries the implementation caveat and which relation makes it load-bearing.

## Flat Baseline Did Better

The flat baseline is easier to read quickly.

## Cruxes Clarified

The map clarifies whether implementation constraints change the practical recommendation.

## Claims Made More Inspectable

The source-grounded claims can be checked against excerpts and source files.

## Investigator View Change

The investigator became less confident in a simple recommendation.

## Complexity Worth It

The extra structure is worth it because it makes the key uncertainty reviewable.
""",
        encoding="utf-8",
    )
    (case_dir / "SCORECARD.md").write_text(
        f"""# {title} Unseen Case Scorecard

Status: `complete`

Overall result: `pass`

| Criterion | Status | Evidence |
| --- | --- | --- |
| package_prepare | pass | Generated UI and review artifacts. |
| package_validate | pass | Manifest, worked regions, and references validate. |
| ui_renders | pass | Static UI files and data are present. |
| review_checklist_source_spans | pass | Checklist rows point to source files and spans. |
| no_parser_artifacts | pass | Structured UI fields contain no parser markers. |
| non_obvious_crux | pass | The implementation crux is visible. |
| real_flat_synthesis_loss | pass | The audit identifies a concrete omitted caveat. |
| human_reviewer_can_inspect | pass | Reviewer can inspect source, map, checklist, and UI. |
| better_than_flat_baseline | pass | The map preserves a distinction the baseline compressed. |

## Final Assessment

The prototype passes this quality run with a relation-label limitation to review.
""",
        encoding="utf-8",
    )
