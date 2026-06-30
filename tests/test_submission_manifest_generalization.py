from __future__ import annotations

from pathlib import Path

from scripts import validate_submission_manifest, validate_submission_references, validate_worked_regions


def test_manifest_driven_validators_accept_synthetic_transfer_case(monkeypatch, tmp_path: Path) -> None:
    _write_transfer_fixture(tmp_path)

    monkeypatch.setattr(
        validate_submission_manifest.sys,
        "argv",
        ["validate_submission_manifest.py", "--repo-root", str(tmp_path)],
    )
    assert validate_submission_manifest.main() == 0

    monkeypatch.setattr(
        validate_worked_regions.sys,
        "argv",
        ["validate_worked_regions.py", "--repo-root", str(tmp_path)],
    )
    assert validate_worked_regions.main() == 0

    monkeypatch.setattr(
        validate_submission_references.sys,
        "argv",
        ["validate_submission_references.py", "--repo-root", str(tmp_path)],
    )
    assert validate_submission_references.main() == 0

    (tmp_path / "docs/demo_doc.md").write_text("This stale reference should fail: `demo_c999`.\n", encoding="utf-8")
    assert validate_submission_references.main() == 1


def _write_transfer_fixture(repo_root: Path) -> None:
    for relative_dir in ("data/cases/demo/sources/text", "docs/worked_regions", "examples/demo"):
        (repo_root / relative_dir).mkdir(parents=True)
    (repo_root / "docs").mkdir(exist_ok=True)

    (repo_root / "data/cases/demo/sources/text/source_1.txt").write_text("Alpha line.\nBeta line.\n", encoding="utf-8")
    (repo_root / "data/cases/demo/sources/text/source_2.txt").write_text("Gamma line.\nDelta line.\n", encoding="utf-8")
    (repo_root / "data/cases/demo/case.yaml").write_text(
        """case_id: demo
title: Demo Transfer Case
question: Can a synthetic case use the same manifest-driven validators?
case_type: synthetic transfer fixture
evidence_mode: source_grounded
review_status: draft
status: in_progress
sources:
  - source_id: demo_source_1
    title: Demo Source One
    source_type: test
    path: data/cases/demo/sources/text/source_1.txt
  - source_id: demo_source_2
    title: Demo Source Two
    source_type: test
    path: data/cases/demo/sources/text/source_2.txt
""",
        encoding="utf-8",
    )
    (repo_root / "docs/demo_doc.md").write_text(
        "Valid references: `demo_c001`, `demo_r001`, and `demo_loss_001`.\n",
        encoding="utf-8",
    )
    (repo_root / "docs/worked_regions/demo_region.md").write_text(
        "# Demo Worked Region\n\nSources: `demo_source_1`, `demo_source_2`.\n",
        encoding="utf-8",
    )
    (repo_root / "examples/demo/worked_map.md").write_text(_worked_map_text(), encoding="utf-8")
    (repo_root / "examples/demo/audit.md").write_text(_audit_text(), encoding="utf-8")
    (repo_root / "examples/demo/baseline.md").write_text(_baseline_text(), encoding="utf-8")
    (repo_root / "examples/demo/BEST_REGIONS.md").write_text(_best_regions_text(), encoding="utf-8")
    (repo_root / "submission_manifest.yaml").write_text(_manifest_text(), encoding="utf-8")


def _manifest_text() -> str:
    return """schema_version: 1
judge_paths:
  - docs/demo_doc.md
required_docs:
  - docs/demo_doc.md
reference_scan_paths:
  - docs/demo_doc.md
cases:
  - case_key: demo
    case_id: demo
    label: Demo Transfer Case
    case_path: data/cases/demo/case.yaml
    ui:
      include: false
    worked_regions:
      - case_key: demo
        case_label: Demo Transfer Case
        region_id: demo_region
        id_prefix: demo
        definition_path: docs/worked_regions/demo_region.md
        map_path: examples/demo/worked_map.md
        audit_path: examples/demo/audit.md
        baseline_path: examples/demo/baseline.md
        best_path: examples/demo/BEST_REGIONS.md
        output_json_path: examples/demo/worked_map.json
        required_sources:
          - demo_source_1
          - demo_source_2
        thresholds:
          min_claims: 3
          max_claims: 8
          min_relation_types: 2
          min_crux_mentions: 1
          min_evidence_rows: 2
          min_losses: 1
          min_surviving_checks: 1
          min_baseline_words: 10
        review:
          worked_region_id: demo_region
          claim_ids: [demo_c001, demo_c002]
          relation_ids: [demo_r001]
          loss_ids: [demo_loss_001]
"""


def _worked_map_text() -> str:
    return """# Demo Worked Map
Status: `human-review-needed`
Prompt/procedure: `synthetic_transfer_fixture`
Evidence mode: `source_grounded`

## Source Subset
- demo_source_1
- demo_source_2

## Claims
claim_id: demo_c001
text: Alpha supports the first demo claim.
source_id: demo_source_1
excerpt: Alpha line.
entailed_by_excerpt: yes

claim_id: demo_c002
text: Beta supports the second demo claim.
source_id: demo_source_1
excerpt: Beta line.
entailed_by_excerpt: yes

claim_id: demo_c003
text: Gamma supports a crux-bearing claim.
source_id: demo_source_2
excerpt: Gamma line.
entailed_by_excerpt: yes

## Relations
relation_id: demo_r001
source_claim: demo_c001
target_claim: demo_c002
relation_type: supports
rationale: The first claim supports the second in this fixture.

relation_id: demo_r002
source_claim: demo_c003
target_claim: demo_c002
relation_type: crux_for
rationale: The third claim is a crux for the second claim.

## Crux Candidates
- The synthetic crux is whether demo_c003 changes demo_c002.

## Similar But Not Identical
- demo_c001 and demo_c002 are related but distinct.

## Evidence Check
| Probe | Result | Notes |
| --- | --- | --- |
| Source one grounding | Survives | Excerpts are present. |
| Source two grounding | Survives | Crux evidence is present. |
"""


def _audit_text() -> str:
    return """# Demo Erosion Audit
Status: `human-review-needed`
Prompt/procedure: `synthetic_transfer_fixture`
Baseline comparator: `examples/demo/baseline.md`
Map comparator: `examples/demo/worked_map.md`

loss_id: demo_loss_001
lost_item: The flat baseline drops the demo crux.
source_support: demo_source_2
flat_baseline_omission: It summarizes without the crux.
case_map_preserves: demo_c003 and demo_r002 preserve the crux.
adversarial_check: survives

## Borderline Or Rejected Losses
- None in fixture.
"""


def _baseline_text() -> str:
    return """# Demo Flat Baseline
Prompt version: `flat_baseline_prompt_v1`
Isolation: `baseline_writer_had_access_to_curated_map=false`

This baseline cites demo_source_1 and demo_source_2 while intentionally staying short for a transfer test.
"""


def _best_regions_text() -> str:
    return """# Demo Best Regions

## Strongest Claim Cluster
demo_c003

## Strongest Relation Cluster
demo_r002

## Strongest Crux
The fixture crux.

## Strongest Preserved Caveat Or Disagreement
The fixture caveat.

## Strongest Flat-Synthesis Loss
demo_loss_001
"""
