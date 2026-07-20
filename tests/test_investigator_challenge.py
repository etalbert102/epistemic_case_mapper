from __future__ import annotations

import json
from pathlib import Path

from scripts.run_investigator_challenge import run_challenge


def test_investigator_challenge_outputs_acceptance_artifacts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = tmp_path / "investigator_challenge"

    run_challenge(
        repo_root,
        repo_root / "experiments/investigator_challenge/challenge_manifest.yaml",
        repo_root / "experiments/investigator_challenge/answer_keys.json",
        output_dir,
        case_ids=["lhc", "eggs", "covid"],
    )

    assert (output_dir / "challenge_run.json").exists()
    assert (output_dir / "FINAL_EVIDENCE_PACKET.md").exists()
    assert (output_dir / "completion_audit.json").exists()

    audit = json.loads((output_dir / "completion_audit.json").read_text())
    assert audit["all_plan_acceptance_criteria_met"] is True


def test_investigator_challenge_detects_mutation_and_preserves_update_scope(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = tmp_path / "investigator_challenge"

    run_challenge(
        repo_root,
        repo_root / "experiments/investigator_challenge/challenge_manifest.yaml",
        repo_root / "experiments/investigator_challenge/answer_keys.json",
        output_dir,
        case_ids=["lhc"],
    )

    mutation = json.loads((output_dir / "mutation/lhc/mutation_report.json").read_text())
    assert mutation["detected"] is True
    assert mutation["restoration_method"] == "copy_from_frozen_clean_snapshot"
    assert mutation["restored_from_frozen_clean_snapshot"] is True
    assert mutation["semantic_repair_attempted"] is False
    assert mutation["localized_object_id"] == "lhc_r004"
    assert mutation["clean_control_triggered"] is False
    assert mutation["unaffected_objects_changed"] == 0

    ledger = json.loads((output_dir / "update/lhc/affected_object_ledger.json").read_text())
    assert ledger["new_source_id"] == "cern_lhc_current_page"
    assert ledger["update_method"] == "apply_prewritten_claim_and_relation_delta"
    assert "lhc_update_c001" in ledger["added_claim_ids"]
    assert "lhc_update_r001" in ledger["added_relation_ids"]
    assert ledger["all_unaffected_ids_stable"] is True

    map_diff = (output_dir / "update/lhc/map_update_diff.md").read_text()
    assert "## After" not in map_diff
    assert "## Reviewer Tasks" not in map_diff


def test_map_condition_scores_above_flat_on_lhc_dependency_task(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = tmp_path / "investigator_challenge"

    run_challenge(
        repo_root,
        repo_root / "experiments/investigator_challenge/challenge_manifest.yaml",
        repo_root / "experiments/investigator_challenge/answer_keys.json",
        output_dir,
        case_ids=["lhc"],
    )

    scores = json.loads((output_dir / "scoring/lhc/task_scores.json").read_text())
    velocity_task = scores["tasks"]["lhc_t003"]["conditions"]
    assert velocity_task["map"]["composite_score"] > velocity_task["flat"]["composite_score"]
    assert velocity_task["map"]["source_trace_accuracy"] == 1.0
