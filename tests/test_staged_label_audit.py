from __future__ import annotations

from epistemic_case_mapper.staged_semantic_label_audit import (
    attach_label_audit,
    claim_label_audit,
    label_audit_bucket_counts,
    label_audit_warning_counts,
)
from epistemic_case_mapper.staged_semantic_relation_candidates import (
    _candidate_endpoint_telemetry,
    _default_use,
    _decision_importance_level,
    _relation_endpoint_priority,
)


def test_label_audit_demotes_direct_high_claim_with_deterministic_warning() -> None:
    claim = {
        "claim": "Evidence for a link between egg consumption and cancer is limited.",
        "role": "conclusion_support",
        "question_relevance": "direct",
        "decision_importance_level": "high",
        "decision_function": "answer_bearing",
        "default_use": "main_map",
        "deterministic_relevance_validation": {
            "status": "warning",
            "reason": "question_outcome_mismatch",
            "blocking": False,
        },
        "whole_doc_source_card": {"source_card_role": "main_finding"},
    }

    audit = claim_label_audit(claim)

    assert audit["synthesis_bucket"] == "supporting"
    assert audit["routing_default_use"] == "supporting_map"
    assert audit["routing_importance_level"] == "medium"
    assert "model_direct_with_deterministic_warning" in audit["warnings"]
    assert "model_main_map_demoted_by_audit" in audit["warnings"]


def test_label_audit_keeps_direct_grounded_cvd_claim_core() -> None:
    claim = {
        "claim": "Each additional half an egg consumed per day was associated with higher incident CVD risk.",
        "role": "conclusion_support",
        "question_relevance": "direct",
        "decision_importance_level": "high",
        "decision_function": "answer_bearing",
        "default_use": "main_map",
        "deterministic_relevance_validation": {"status": "ok", "reason": "", "blocking": False},
        "whole_doc_source_card": {"source_card_role": "main_finding"},
    }

    audit = claim_label_audit(claim)

    assert audit["synthesis_bucket"] == "core"
    assert audit["routing_default_use"] == "main_map"
    assert audit["routing_role"] == "source_claim"
    assert audit["warnings"] == []


def test_label_audit_keeps_unclassified_source_claim_in_supporting_map() -> None:
    claim = {
        "claim": "The trial found a decision-relevant outcome changed after the intervention.",
        "role": "source_claim",
        "question_relevance": "unspecified",
        "decision_importance_level": "medium",
        "decision_function": "unclassified_evidence",
        "default_use": "supporting_map",
        "deterministic_relevance_validation": {"status": "ok", "reason": "", "blocking": False},
    }

    audit = claim_label_audit(claim)

    assert audit["synthesis_bucket"] == "supporting"
    assert audit["routing_role"] == "source_claim"
    assert audit["routing_default_use"] == "supporting_map"
    assert audit["warnings"] == []


def test_label_audit_preserves_mechanism_warning_as_supporting_context() -> None:
    claim = {
        "claim": "Egg consumption can change LDL cholesterol, which is a plausible cardiovascular mechanism.",
        "role": "scope_limit",
        "question_relevance": "indirect",
        "decision_importance_level": "high",
        "decision_function": "mechanism",
        "default_use": "main_map",
        "deterministic_relevance_validation": {
            "status": "warning",
            "reason": "question_outcome_mismatch",
            "blocking": False,
        },
        "whole_doc_source_card": {"source_card_role": "mechanism"},
    }

    audit = attach_label_audit(claim)

    assert audit["synthesis_bucket"] == "supporting"
    assert audit["routing_role"] == "source_claim"
    assert audit["routing_default_use"] == "supporting_map"
    assert "deterministic_relevance:question_outcome_mismatch" in claim["validation_warnings"]
    assert "model_main_map_demoted_by_audit" in claim["validation_warnings"]


def test_label_audit_counts_buckets_and_warning_types() -> None:
    core = {
        "claim": "Egg intake was associated with cardiovascular risk.",
        "role": "conclusion_support",
        "question_relevance": "direct",
        "decision_importance_level": "high",
        "decision_function": "answer_bearing",
        "default_use": "main_map",
        "deterministic_relevance_validation": {"status": "ok", "reason": "", "blocking": False},
        "whole_doc_source_card": {"source_card_role": "main_finding"},
    }
    warned = {
        "claim": "Egg intake was associated with unrelated cancer outcomes.",
        "role": "conclusion_support",
        "question_relevance": "direct",
        "decision_importance_level": "high",
        "decision_function": "answer_bearing",
        "default_use": "main_map",
        "deterministic_relevance_validation": {
            "status": "warning",
            "reason": "question_outcome_mismatch",
            "blocking": False,
        },
        "whole_doc_source_card": {"source_card_role": "main_finding"},
    }
    attach_label_audit(core)
    attach_label_audit(warned)

    assert label_audit_bucket_counts([core, warned]) == {"core": 1, "supporting": 1}
    assert label_audit_warning_counts([core, warned])["model_main_map_demoted_by_audit"] == 1


def test_relation_candidate_priority_uses_audited_routing_labels() -> None:
    core_claim = {
        "claim_id": "c1",
        "claim": "Each additional half an egg consumed per day was associated with higher incident CVD risk.",
        "role": "conclusion_support",
        "question_relevance": "direct",
        "decision_importance_level": "high",
        "decision_function": "answer_bearing",
        "default_use": "main_map",
        "deterministic_relevance_validation": {"status": "ok", "reason": "", "blocking": False},
        "whole_doc_source_card": {"source_card_role": "main_finding"},
    }
    warned_claim = {
        "claim_id": "c2",
        "claim": "Evidence for a link between egg consumption and cancer is limited.",
        "role": "conclusion_support",
        "question_relevance": "direct",
        "decision_importance_level": "high",
        "decision_function": "answer_bearing",
        "default_use": "main_map",
        "deterministic_relevance_validation": {
            "status": "warning",
            "reason": "question_outcome_mismatch",
            "blocking": False,
        },
        "whole_doc_source_card": {"source_card_role": "main_finding"},
    }
    attach_label_audit(core_claim)
    attach_label_audit(warned_claim)

    assert _default_use(core_claim) == "main_map"
    assert _default_use(warned_claim) == "supporting_map"
    assert _decision_importance_level(warned_claim) == "medium"
    assert _relation_endpoint_priority(core_claim) > _relation_endpoint_priority(warned_claim)
    telemetry = _candidate_endpoint_telemetry(warned_claim)
    assert telemetry["label_audit"]["routing_default_use"] == "supporting_map"
