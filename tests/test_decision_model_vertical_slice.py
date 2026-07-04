from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from epistemic_case_mapper.map_briefing import (
    build_argument_model,
    build_compact_decision_model,
    briefing_scaffold,
    evaluate_decision_model_brief,
    render_decision_model_brief,
    run_decision_model_slice,
)
from epistemic_case_mapper.model_schemas import (
    ArgumentModelOutput,
    CompactDecisionModelOutput,
    RelationClassificationOutput,
    parse_model_output,
    parse_model_output_report,
)


def test_relation_output_schema_requires_contract_for_positive_relation() -> None:
    valid = parse_model_output(
        """```json
        {
          "pair_id": "p001",
          "relation_type": "challenges",
          "source_claim": "c002",
          "target_claim": "c001",
          "rationale": "The subgroup result limits the broad default claim.",
          "source_claim_support_excerpt": "higher risk in the subgroup",
          "target_claim_support_excerpt": "neutral in the default group",
          "confidence": "high"
        }
        ```""",
        RelationClassificationOutput,
    )

    assert valid.relation_type == "challenges"
    assert valid.confidence == "high"

    with pytest.raises(ValidationError):
        RelationClassificationOutput.model_validate(
            {
                "relation_type": "supports",
                "source_claim": "c001",
                "target_claim": "c002",
            }
        )

    neutral = RelationClassificationOutput.model_validate({"relation_type": "none"})
    assert neutral.relation_type == "none"


def test_parse_model_output_report_returns_repair_friendly_errors() -> None:
    report = parse_model_output_report('{"relation_type": "crux_for"}', RelationClassificationOutput)

    assert report["ok"] is False
    assert any("positive relation missing contract fields" in item["message"] for item in report["errors"])


def test_compact_decision_model_caps_slots_and_preserves_anchors() -> None:
    model = build_compact_decision_model(
        _arbitrary_candidate_map(),
        _quality_report(),
        question="Should the city pilot remote permitting for small building projects?",
    )

    validated = CompactDecisionModelOutput.model_validate(model)
    assert len(validated.top_support) <= 3
    assert len(validated.top_counterevidence_or_tensions) <= 3
    assert len(validated.top_scope_boundaries) <= 3
    assert len(validated.top_cruxes) <= 3
    assert validated.top_support[0].claim_ids
    assert validated.top_cruxes[0].relation_ids == ["r001"]
    assert validated.audit["claim_count"] == 6


def test_argument_model_preserves_load_bearing_anchors_and_quantities() -> None:
    candidate_map = _arbitrary_candidate_map()
    source_lookup = {"audit": "Permit Office Audit", "survey": "Applicant Survey", "security": "Security Review"}
    scaffold = briefing_scaffold(
        candidate_map,
        _quality_report(),
        source_lookup,
        {"items": []},
        question="Should the city pilot remote permitting for small building projects?",
    )

    model = build_argument_model(
        candidate_map,
        _quality_report(),
        scaffold,
        question="Should the city pilot remote permitting for small building projects?",
    )

    validated = ArgumentModelOutput.model_validate(model)
    assert validated.decision_question.startswith("Should the city")
    assert validated.strongest_support
    assert validated.scope_boundaries
    assert validated.cruxes[0].relation_ids == ["r001"]
    assert all(item.claim_ids or item.source_ids or item.relation_ids or item.quantity_ids for item in validated.strongest_support)
    assert validated.audit["method"] == "deterministic_argument_model_from_briefing_scaffold_v1"


def test_decision_model_brief_improves_crux_scope_visibility_without_unanchored_evidence() -> None:
    model = build_compact_decision_model(
        _arbitrary_candidate_map(),
        _quality_report(),
        question="Should the city pilot remote permitting for small building projects?",
    )
    brief = render_decision_model_brief(model)
    current = "# Brief\n\nRemote permitting may be useful. Evidence is mixed.\n"
    report = evaluate_decision_model_brief(current, brief, model)

    assert "## What could change the answer" in brief
    assert "## Scope and missing evidence" in brief
    assert report["status"] == "improved"
    assert report["metrics"]["unsupported_evidence_items"] == 0
    assert report["metrics"]["decision_confidence_visible"] is True


def test_run_decision_model_slice_writes_artifacts(tmp_path: Path) -> None:
    map_path = tmp_path / "map.json"
    quality_path = tmp_path / "quality.json"
    current_path = tmp_path / "current.md"
    map_path.write_text(json.dumps(_arbitrary_candidate_map()), encoding="utf-8")
    quality_path.write_text(json.dumps(_quality_report()), encoding="utf-8")
    current_path.write_text("# Brief\n\nRemote permitting may be useful.\n", encoding="utf-8")

    result = run_decision_model_slice(
        repo_root=tmp_path,
        map_path=map_path,
        quality_report_path=quality_path,
        question="Should the city pilot remote permitting for small building projects?",
        current_brief_path=current_path,
        output_dir=tmp_path / "slice",
    )

    assert result.status == "improved"
    assert result.decision_model_path.exists()
    assert result.briefing_path.read_text(encoding="utf-8").startswith("# Decision Brief")
    assert json.loads(result.eval_path.read_text(encoding="utf-8"))["status"] == "improved"


def test_run_decision_model_slice_can_use_main_synthesis_stage(tmp_path: Path) -> None:
    map_path = tmp_path / "map.json"
    quality_path = tmp_path / "quality.json"
    map_path.write_text(json.dumps(_arbitrary_candidate_map()), encoding="utf-8")
    quality_path.write_text(json.dumps(_quality_report()), encoding="utf-8")

    result = run_decision_model_slice(
        repo_root=tmp_path,
        map_path=map_path,
        quality_report_path=quality_path,
        question="Should the city pilot remote permitting for small building projects?",
        output_dir=tmp_path / "slice",
        synthesis_backend="prompt",
    )

    assert result.synthesized_briefing_path is not None
    assert result.synthesized_appendix_path is not None
    assert result.synthesis_report_path is not None
    assert result.synthesized_briefing_path.name == "BRIEFING.md"
    assert result.synthesized_briefing_path.exists()
    assert "Decision Brief" in result.synthesized_briefing_path.read_text(encoding="utf-8")
    report = json.loads(result.synthesis_report_path.read_text(encoding="utf-8"))
    assert report["status"] == "skipped_prompt_backend"


def _arbitrary_candidate_map() -> dict:
    return {
        "case_id": "remote_permitting",
        "question": "Should the city pilot remote permitting for small building projects?",
        "sources": [
            {"source_id": "audit", "title": "Permit Office Audit"},
            {"source_id": "survey", "title": "Applicant Survey"},
            {"source_id": "security", "title": "Security Review"},
        ],
        "claims": [
            {
                "claim_id": "c001",
                "claim": "Remote permitting reduced average application cycle time for small projects.",
                "source_id": "audit",
                "excerpt": "cycle time fell for small projects",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "Applicants reported fewer repeat trips when simple permits could be handled online.",
                "source_id": "survey",
                "excerpt": "fewer repeat trips",
                "entailed_by_excerpt": "yes",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c003",
                "claim": "Complex projects still needed in-person plan review before approval.",
                "source_id": "audit",
                "excerpt": "complex projects needed in-person plan review",
                "entailed_by_excerpt": "yes",
                "role": "scope_limit",
            },
            {
                "claim_id": "c004",
                "claim": "The security review found unresolved identity verification risks for contractor accounts.",
                "source_id": "security",
                "excerpt": "unresolved identity verification risks",
                "entailed_by_excerpt": "yes",
                "role": "scope_limit",
            },
            {
                "claim_id": "c005",
                "claim": "The audit did not measure downstream inspection failure rates.",
                "source_id": "audit",
                "excerpt": "did not measure downstream inspection failure rates",
                "entailed_by_excerpt": "yes",
                "role": "measurement_validity",
            },
            {
                "claim_id": "c006",
                "claim": "A phased pilot was recommended only for low-risk project categories.",
                "source_id": "security",
                "excerpt": "phased pilot for low-risk categories",
                "entailed_by_excerpt": "yes",
                "role": "implementation_constraint",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c004",
                "target_claim": "c001",
                "relation_type": "crux_for",
                "rationale": "Identity verification risk is a crux for whether speed gains justify a pilot.",
                "relation_confidence": "high",
            },
            {
                "relation_id": "r002",
                "source_claim": "c003",
                "target_claim": "c001",
                "relation_type": "refines",
                "rationale": "The cycle-time finding applies mainly to small or simple projects.",
                "relation_confidence": "medium",
            },
        ],
    }


def _quality_report() -> dict:
    return {
        "status": "usable_with_review",
        "score": 86,
        "issues": [
            {
                "severity": "warning",
                "issue_type": "missing_downstream_outcomes",
                "message": "The map does not establish inspection failure or rework outcomes.",
            }
        ],
    }
