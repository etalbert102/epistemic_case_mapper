from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper import cli
from scripts import build_ui_data, validate_submission_manifest, validate_submission_references, validate_worked_regions
from scripts.run_blinded_baselines import _configs_from_manifest


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

    baseline_configs = _configs_from_manifest(tmp_path)
    assert sorted(baseline_configs) == ["demo_region", "demo_region_followup"]
    assert {config.case_key for config in baseline_configs.values()} == {"demo"}

    ui_payload = build_ui_data.build_payload(tmp_path)
    assert len(ui_payload["cases"]) == 1
    assert ui_payload["package"]["packageId"] == "demo_package"
    assert "LHC" not in str(ui_payload["hero"])
    assert [region["regionId"] for region in ui_payload["cases"][0]["workedRegions"]] == [
        "demo_region",
        "demo_region_followup",
    ]

    monkeypatch.setattr(
        validate_submission_references.sys,
        "argv",
        ["validate_submission_references.py", "--repo-root", str(tmp_path)],
    )
    assert validate_submission_references.main() == 0

    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["ecm.py", "--repo-root", str(tmp_path), "validate", "package"],
    )
    assert cli.main() == 0

    (tmp_path / "docs/demo_doc.md").write_text("This stale reference should fail: `claim:demo:999`.\n", encoding="utf-8")
    monkeypatch.setattr(
        validate_submission_references.sys,
        "argv",
        ["validate_submission_references.py", "--repo-root", str(tmp_path)],
    )
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
        "Valid references: `claim:demo:001`, `rel:demo:001`, and `loss:demo:001`.\n",
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
    (repo_root / "examples/demo/worked_map_followup.md").write_text(_worked_map_text("claim:demo:101", "claim:demo:102", "claim:demo:103", "rel:demo:101", "rel:demo:102"), encoding="utf-8")
    (repo_root / "examples/demo/audit_followup.md").write_text(_audit_text("loss:demo:101", "claim:demo:103", "rel:demo:102"), encoding="utf-8")
    (repo_root / "examples/demo/baseline_followup.md").write_text(_baseline_text(), encoding="utf-8")
    (repo_root / "examples/demo/BEST_REGIONS_FOLLOWUP.md").write_text(_best_regions_text("claim:demo:103", "rel:demo:102", "loss:demo:101"), encoding="utf-8")
    (repo_root / "submission_manifest.yaml").write_text(_manifest_text(), encoding="utf-8")


def _manifest_text() -> str:
    return """schema_version: 1
package_id: demo_package
package_label: Demo Package
id_patterns:
  claim: "claim:demo:[0-9]+"
  relation: "rel:demo:[0-9]+"
  loss: "loss:demo:[0-9]+"
ui_hero:
  eyebrow: Demo Mode
  title: Demo package review surface
  body: This package uses custom ID patterns and multiple regions under one case.
  links:
    - label: Demo doc
      path: docs/demo_doc.md
      primary: true
  cards:
    - label: Flat synthesis
      text: A normal summary drops the custom crux.
    - label: Map surface
      text: "`claim:demo:003` and `rel:demo:002` keep it inspectable."
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
      include: true
      label: Demo Transfer Case
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
          claim_ids: ["claim:demo:001", "claim:demo:002"]
          relation_ids: ["rel:demo:001"]
          loss_ids: ["loss:demo:001"]
        blinded_baseline:
          title: Demo Blinded Baseline
          question: Can the first demo region be synthesized from spans?
          output_path: examples/demo/blinded_flat_synthesis_baseline_gemma4.md
          required_sources: [demo_source_1, demo_source_2]
          spans:
            - source_id: demo_source_1
              path: data/cases/demo/sources/text/source_1.txt
              ranges: [[1, 2]]
            - source_id: demo_source_2
              path: data/cases/demo/sources/text/source_2.txt
              ranges: [[1, 2]]
          min_words: 10
      - case_key: demo
        case_label: Demo Transfer Case
        region_id: demo_region_followup
        id_prefix: demo
        definition_path: docs/worked_regions/demo_region.md
        map_path: examples/demo/worked_map_followup.md
        audit_path: examples/demo/audit_followup.md
        baseline_path: examples/demo/baseline_followup.md
        best_path: examples/demo/BEST_REGIONS_FOLLOWUP.md
        output_json_path: examples/demo/worked_map_followup.json
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
          worked_region_id: demo_region_followup
          claim_ids: ["claim:demo:101", "claim:demo:102"]
          relation_ids: ["rel:demo:101"]
          loss_ids: ["loss:demo:101"]
        blinded_baseline:
          title: Demo Followup Blinded Baseline
          question: Can the second demo region be synthesized from spans?
          output_path: examples/demo/blinded_followup_flat_synthesis_baseline_gemma4.md
          required_sources: [demo_source_1, demo_source_2]
          spans:
            - source_id: demo_source_1
              path: data/cases/demo/sources/text/source_1.txt
              ranges: [[1, 2]]
            - source_id: demo_source_2
              path: data/cases/demo/sources/text/source_2.txt
              ranges: [[1, 2]]
          min_words: 10
"""


def _worked_map_text(
    claim_1: str = "claim:demo:001",
    claim_2: str = "claim:demo:002",
    claim_3: str = "claim:demo:003",
    relation_1: str = "rel:demo:001",
    relation_2: str = "rel:demo:002",
) -> str:
    return f"""# Demo Worked Map
Status: `human-review-needed`
Prompt/procedure: `synthetic_transfer_fixture`
Evidence mode: `source_grounded`

## Source Subset
- demo_source_1
- demo_source_2

## Claims
claim_id: {claim_1}
text: Alpha supports the first demo claim.
source_id: demo_source_1
excerpt: Alpha line.
entailed_by_excerpt: yes

claim_id: {claim_2}
text: Beta supports the second demo claim.
source_id: demo_source_1
excerpt: Beta line.
entailed_by_excerpt: yes

claim_id: {claim_3}
text: Gamma supports a crux-bearing claim.
source_id: demo_source_2
excerpt: Gamma line.
entailed_by_excerpt: yes

## Relations
relation_id: {relation_1}
source_claim: {claim_1}
target_claim: {claim_2}
relation_type: supports
rationale: The first claim supports the second in this fixture.

relation_id: {relation_2}
source_claim: {claim_3}
target_claim: {claim_2}
relation_type: crux_for
rationale: The third claim is a crux for the second claim.

## Crux Candidates
- The synthetic crux is whether {claim_3} changes {claim_2}.

## Similar But Not Identical
- {claim_1} and {claim_2} are related but distinct.

## Evidence Check
| Probe | Result | Notes |
| --- | --- | --- |
| Source one grounding | Survives | Excerpts are present. |
| Source two grounding | Survives | Crux evidence is present. |
"""


def _audit_text(loss_id: str = "loss:demo:001", claim_id: str = "claim:demo:003", relation_id: str = "rel:demo:002") -> str:
    return f"""# Demo Erosion Audit
Status: `human-review-needed`
Prompt/procedure: `synthetic_transfer_fixture`
Baseline comparator: `examples/demo/baseline.md`
Map comparator: `examples/demo/worked_map.md`

loss_id: {loss_id}
lost_item: The flat baseline drops the demo crux.
source_support: demo_source_2
flat_baseline_omission: It summarizes without the crux.
case_map_preserves: {claim_id} and {relation_id} preserve the crux.
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


def _best_regions_text(claim_id: str = "claim:demo:003", relation_id: str = "rel:demo:002", loss_id: str = "loss:demo:001") -> str:
    return f"""# Demo Best Regions

## Strongest Claim Cluster
{claim_id}

## Strongest Relation Cluster
{relation_id}

## Strongest Crux
The fixture crux.

## Strongest Preserved Caveat Or Disagreement
The fixture caveat.

## Strongest Flat-Synthesis Loss
{loss_id}
"""
