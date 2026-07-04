from __future__ import annotations

import json

from epistemic_case_mapper.decision_argument_artifacts import (
    build_structured_decision_cruxes,
    compact_decision_argument_artifacts,
    evaluate_traceability_against_memo,
)
from epistemic_case_mapper.main_memo_obligations import build_unified_requirement_ledger
from epistemic_case_mapper.map_briefing import briefing_scaffold
from epistemic_case_mapper.map_briefing_artifacts import write_scaffold_artifacts


def test_decision_argument_artifacts_build_decision_structures() -> None:
    candidate_map = _candidate_map()
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 84, "issues": []},
        {"source_a": "Source A", "source_b": "Source B", "source_c": "Source C"},
        {"items": []},
        question="Should the city adopt the new process?",
    )

    artifacts = scaffold["decision_argument_artifacts"]

    assert artifacts["evidence_to_decision_matrix"]["schema_id"] == "evidence_to_decision_matrix_v1"
    assert artifacts["evidence_to_decision_matrix"]["row_count"] >= 3
    assert artifacts["summary_of_findings"]["finding_count"] >= 3
    assert len(artifacts["competing_reads"]["reads"]) == 4
    assert artifacts["argument_case_graph"]["node_count"] >= artifacts["summary_of_findings"]["finding_count"]
    assert artifacts["decision_traceability_matrix"]["row_count"] > 0

    compact = compact_decision_argument_artifacts(scaffold, "Decision Brief")
    assert compact["summary_of_findings"]
    assert compact["competing_reads"]
    assert compact["argument_case_top_claim"]


def test_traceability_matrix_evaluates_final_memo_presence() -> None:
    candidate_map = _candidate_map()
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 84, "issues": []},
        {"source_a": "Source A", "source_b": "Source B", "source_c": "Source C"},
        {"items": []},
        question="Should the city adopt the new process?",
    )
    matrix = scaffold["decision_argument_artifacts"]["decision_traceability_matrix"]

    evaluated = evaluate_traceability_against_memo(
        matrix,
        "## Decision Brief\n\nThe pilot reduced processing time by 18% compared with the legacy workflow and should remain conditional on staff capacity.",
    )

    assert evaluated["schema_id"] == "decision_traceability_matrix_v1"
    assert evaluated["status_counts"]
    assert any(row["status"] == "satisfied" for row in evaluated["rows"])


def test_unified_requirement_ledger_keeps_missing_and_source_dispositions() -> None:
    main_ledger = {
        "obligations": [
            {
                "obligation_id": "required_a",
                "category": "strongest_support",
                "statement": "Included requirement",
                "stage_owner": "decision_synthesis",
                "status": "satisfied",
                "priority": 90,
                "matched_terms": ["Included"],
            },
            {
                "obligation_id": "required_b",
                "category": "baseline_comparison_concept",
                "statement": "Missing source requirement",
                "stage_owner": "source_coverage",
                "status": "source_missing",
                "priority": 88,
            },
            {
                "obligation_id": "required_c",
                "category": "baseline_comparison_concept",
                "statement": "Missing synthesis requirement",
                "stage_owner": "decision_synthesis",
                "status": "missing_from_memo",
                "priority": 87,
            },
        ]
    }
    traceability = {
        "rows": [
            {
                "requirement_id": "required_a",
                "target_sections": ["Decision Brief"],
                "memo_sections": ["Decision Brief"],
                "supporting_finding_ids": ["finding_01"],
                "argument_node_ids": ["claim_top"],
            }
        ]
    }

    ledger = build_unified_requirement_ledger(main_memo_ledger=main_ledger, traceability_ledger=traceability)

    assert ledger["disposition_counts"]["included"] == 1
    assert ledger["disposition_counts"]["source_missing"] == 1
    assert ledger["disposition_counts"]["missing"] == 1
    included = next(row for row in ledger["rows"] if row["requirement_id"] == "required_a")
    assert included["supporting_finding_ids"] == ["finding_01"]


def test_structured_cruxes_tolerate_direction_taxonomy_drift() -> None:
    findings = {
        "findings": [
            {
                "finding_id": "finding_01",
                "finding": "The default option improved the primary outcome by 18%.",
                "direction": "supports_default",
                "decision_factor": "supporting_evidence",
                "source_ids": ["source_a"],
            },
            {
                "finding_id": "finding_02",
                "finding": "The default option increased review workload during peak periods.",
                "direction": "challenges_or_warns",
                "decision_factor": "counterevidence_or_risk",
                "source_ids": ["source_b"],
            },
            {
                "finding_id": "finding_03",
                "finding": "The result only applies where supervisors can review exceptions within two days.",
                "direction": "bounds_or_conditions",
                "decision_factor": "scope_boundary",
                "source_ids": ["source_c"],
            },
        ]
    }
    reads = {
        "reads": [
            {
                "label": "Treat the default option as worth adopting.",
                "diagnostic_score": 3,
                "supporting_findings": [{"finding_id": "finding_01"}],
                "challenging_findings": [{"finding_id": "finding_02"}],
            }
        ]
    }

    cruxes = build_structured_decision_cruxes(findings, reads)

    assert cruxes["crux_count"] >= 3
    assert {row["crux_type"] for row in cruxes["cruxes"]} >= {"evidence_balance", "scope_boundary", "competing_read"}
    assert "should outweigh" not in json.dumps(cruxes).lower()
    assert "keeps both the supporting evidence and the counterevidence visible" in json.dumps(cruxes)


def test_scaffold_artifacts_write_decision_argument_outputs(tmp_path) -> None:
    candidate_map = _candidate_map()
    scaffold = briefing_scaffold(
        candidate_map,
        {"status": "usable_with_review", "score": 84, "issues": []},
        {"source_a": "Source A", "source_b": "Source B", "source_c": "Source C"},
        {"items": []},
        question="Should the city adopt the new process?",
    )

    paths = write_scaffold_artifacts(
        artifacts=tmp_path,
        prompt="prompt",
        prioritized_map=candidate_map,
        prioritization_report={"changed": False},
        erosion_audit={"items": []},
        scaffold=scaffold,
    )

    for key in (
        "evidence_to_decision_matrix",
        "summary_of_findings",
        "competing_reads",
        "argument_case_graph",
        "decision_traceability_matrix",
    ):
        payload = json.loads(paths[key].read_text(encoding="utf-8"))
        assert payload["schema_id"].endswith("_v1")
    assert paths["summary_of_findings_markdown"].read_text(encoding="utf-8").startswith("# Summary Of Findings")


def _candidate_map() -> dict:
    return {
        "claims": [
            {
                "claim_id": "c001",
                "claim": "The pilot reduced processing time by 18% compared with the legacy workflow.",
                "source_id": "source_a",
                "role": "conclusion_support",
            },
            {
                "claim_id": "c002",
                "claim": "The pilot increased error review workload for staff during peak periods.",
                "source_id": "source_b",
                "role": "scope_limit",
            },
            {
                "claim_id": "c003",
                "claim": "The process should only be adopted where supervisors can review exceptions within two days.",
                "source_id": "source_c",
                "role": "implementation_constraint",
            },
        ],
        "relations": [
            {
                "relation_id": "r001",
                "source_claim": "c002",
                "target_claim": "c001",
                "relation_type": "in_tension_with",
                "rationale": "Efficiency gains depend on review capacity.",
            }
        ],
    }
