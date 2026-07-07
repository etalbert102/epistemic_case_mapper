from __future__ import annotations

from epistemic_case_mapper.staged_semantic_relation_quality import (
    relation_pair_intent,
    relation_quality_issue_rows,
    relation_semantic_rejection_reason,
)


def test_cross_source_mechanism_scope_cannot_refine_unrelated_finding() -> None:
    left = _claim("demo_c001", "The potential benefit may be offset by changes in a mechanistic biomarker.", "mechanism_trial", "scope_limit")
    right = _claim("demo_c002", "A separate cohort found the exposure was not associated with clinical events.", "cohort_b", "conclusion_support")
    packet = {"pair_id": "pair_001", "left": left, "right": right}

    assert relation_pair_intent(left, right) == {
        "intent": "cross_source_mechanism_scope_to_finding",
        "allowed_relation_types": ["supports", "in_tension_with", "challenges", "none"],
    }
    assert _semantic_reason("refines", "The biomarker caveat refines the cohort finding.", packet) == "cross_source_mechanism_scope_refines"


def test_relation_semantic_validator_rejects_cross_source_study_scope_refinement() -> None:
    left = _claim("demo_c001", "The trial enrolled patients with prior cardiovascular events.", "trial_a", "scope_limit")
    right = _claim("demo_c002", "The meta-analysis found egg intake was not associated with cardiovascular events.", "meta_b", "conclusion_support")

    assert _semantic_reason(
        "refines",
        "The trial population refines the meta-analysis population.",
        {"pair_id": "pair_001", "left": left, "right": right},
    ) == "cross_source_study_scope_relation"


def test_relation_semantic_validator_rejects_type_rationale_mismatch() -> None:
    left = _claim("demo_c001", "The decision turns on whether the intervention improves outcomes.", "a", "crux")
    right = _claim("demo_c002", "The evidence supports the intervention.", "b", "conclusion_support")

    assert _semantic_reason(
        "in_tension_with",
        "Both claims are consistent and support the same conclusion.",
        {"pair_id": "pair_001", "left": left, "right": right},
    ) == "relation_type_rationale_mismatch"


def test_relation_semantic_validator_rejects_weak_support_contract() -> None:
    left = _claim("demo_c001", "The trial found no association with clinical events.", "a", "conclusion_support")
    right = _claim("demo_c002", "The cohort found no association with mortality.", "b", "conclusion_support")

    assert _semantic_reason(
        "supports",
        "Both claims lean neutral and are broadly consistent.",
        {"pair_id": "pair_001", "left": left, "right": right},
    ) == "weak_support_contract"


def test_relation_semantic_validator_accepts_mechanistic_and_quantitative_support() -> None:
    left = _claim("demo_c001", "A mechanism explains lower event risk.", "a", "conclusion_support")
    right = _claim("demo_c002", "The cohort found lower event risk.", "b", "conclusion_support")
    packet = {"pair_id": "pair_001", "left": left, "right": right}

    assert _semantic_reason("supports", "The mechanism explains why the cohort finding would occur.", packet) == ""
    assert _semantic_reason("supports", "The hazard ratio estimate quantitatively strengthens the same endpoint.", packet) == ""


def test_relation_semantic_validator_requires_crux_contract_but_allows_valid_crux() -> None:
    left = _claim("demo_c001", "The decision turns on whether clinical outcomes outweigh biomarkers.", "a", "crux")
    right = _claim("demo_c002", "The trial measured only biomarkers rather than clinical events.", "b", "measurement_validity")
    packet = {"pair_id": "pair_001", "left": left, "right": right}

    assert _semantic_reason("crux_for", "The trial is relevant to the decision.", packet) == "missing_crux_contract"
    assert _semantic_reason("crux_for", "This is critical because it would change whether biomarker-only evidence should drive the decision.", packet) == ""
    assert _semantic_reason("crux_for", "If the mechanism is true, it implies the target finding drives the decision.", packet) == ""


def test_relation_quality_rows_report_crux_overuse() -> None:
    claims = [
        _claim("demo_c001", "Decision crux.", "a", "crux"),
        _claim("demo_c002", "Evidence one.", "b", "conclusion_support"),
        _claim("demo_c003", "Evidence two.", "c", "conclusion_support"),
        _claim("demo_c004", "Evidence three.", "d", "conclusion_support"),
        _claim("demo_c005", "Evidence four.", "e", "conclusion_support"),
    ]
    relations = [
        {
            "relation_id": f"r{index}",
            "source_claim": "demo_c001",
            "target_claim": f"demo_c00{index + 1}",
            "relation_type": "crux_for",
            "rationale": "This crux would change the decision.",
        }
        for index in range(1, 5)
    ]

    rows = relation_quality_issue_rows(relations, claims)

    assert any(row["issue_type"] == "crux_relation_overuse" for row in rows)


def _semantic_reason(relation_type: str, rationale: str, packet: dict[str, object]) -> str:
    return relation_semantic_rejection_reason(
        {
            "source_claim": packet["left"]["claim_id"],
            "target_claim": packet["right"]["claim_id"],
            "relation_type": relation_type,
            "rationale": rationale,
        },
        packet,
    )


def _claim(claim_id: str, claim: str, source_id: str, role: str) -> dict[str, str]:
    return {
        "claim_id": claim_id,
        "claim": claim,
        "source_id": source_id,
        "excerpt": claim,
        "role": role,
    }
