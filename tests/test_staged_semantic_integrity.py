from __future__ import annotations

from epistemic_case_mapper.schema import CaseManifest
from epistemic_case_mapper.staged_semantic_pipeline import (
    _assemble_map,
    _claim_polarity,
    _normalize_relation_proposal,
    consolidate_claims_for_map,
)
from epistemic_case_mapper.submission_manifest import WorkedRegion


def test_consolidation_keeps_null_and_beneficial_claims_distinct() -> None:
    claims = [
        _claim(
            "demo_c001",
            "Daily exposure was not associated with lower cardiovascular risk in adults.",
            "doc_a",
        ),
        _claim(
            "demo_c002",
            "Daily exposure was associated with lower cardiovascular risk in adults.",
            "doc_b",
        ),
        _claim("demo_c003", "The trial enrolled 400 participants for twelve months.", "doc_c"),
        _claim("demo_c004", "Implementation costs exceeded the annual budget.", "doc_d"),
    ]

    consolidated, report = consolidate_claims_for_map(claims, min_claims=2)

    assert _claim_polarity(claims[0]["claim"]) == "null_or_no_clear_association"
    assert _claim_polarity(claims[1]["claim"]) == "beneficial_or_lower"
    assert len(consolidated) == 4
    assert report["changed"] is False
    assert {claim["claim_id"] for claim in consolidated} == {"demo_c001", "demo_c002", "demo_c003", "demo_c004"}


def test_map_cruxes_come_only_from_accepted_relations() -> None:
    claims = [
        _claim("demo_c001", "The intervention reduced the target risk.", "doc_a"),
        _claim("demo_c002", "The result depends on baseline severity.", "doc_b"),
    ]
    packet = {"pair_id": "pair_001", "left": claims[0], "right": claims[1]}
    relation, reason = _normalize_relation_proposal(
        {
            "pair_id": "pair_001",
            "source_claim": "demo_c002",
            "target_claim": "demo_c001",
            "relation_type": "crux_for",
            "rationale": "Baseline severity would change whether the result should guide the decision.",
            "crux_candidates": ["Whether demo_c002 changes demo_c001 is the accepted crux."],
        },
        {"demo_c001", "demo_c002"},
        {"supports", "crux_for"},
        packet,
    )
    rejected_payload = {
        "relations": [
            {
                "pair_id": "unknown_pair",
                "source_claim": "missing_a",
                "target_claim": "missing_b",
                "relation_type": "crux_for",
                "rationale": "This proposal is invalid.",
                "crux_candidates": ["A rejected relation must not become a crux."],
            }
        ]
    }

    assert reason == ""
    assert relation is not None
    relation["relation_id"] = "demo_r001"
    candidate = _assemble_map(
        _region(),
        _case_manifest(),
        claims,
        [relation],
        [rejected_payload],
        decision_question="Should the intervention be adopted?",
    )
    no_relation_candidate = _assemble_map(
        _region(),
        _case_manifest(),
        claims,
        [],
        [rejected_payload],
        decision_question="Should the intervention be adopted?",
    )

    assert candidate["crux_candidates"] == ["Whether demo_c002 changes demo_c001 is the accepted crux."]
    assert no_relation_candidate["crux_candidates"] == []


def _claim(claim_id: str, text: str, source_id: str) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "claim": text,
        "source_id": source_id,
        "source_span": "lines 1-1",
        "excerpt": text,
        "source_quote": text,
        "entailed_by_excerpt": "yes",
        "role": "source_claim",
    }


def _region() -> WorkedRegion:
    return WorkedRegion.model_validate(
        {
            "case_key": "demo",
            "case_label": "Demo",
            "region_id": "demo_region",
            "id_prefix": "demo",
            "definition_path": "definition.md",
            "map_path": "map.json",
            "audit_path": "audit.json",
            "baseline_path": "baseline.md",
            "output_json_path": "output.json",
            "required_sources": ["doc_a", "doc_b"],
            "thresholds": {"min_evidence_rows": 1},
        }
    )


def _case_manifest() -> CaseManifest:
    return CaseManifest.model_validate(
        {
            "case_id": "demo",
            "title": "Demo Case",
            "question": "Should the intervention be adopted?",
            "case_type": "test",
            "sources": [
                {"source_id": "doc_a", "title": "Source A", "text": "The intervention reduced the target risk."},
                {"source_id": "doc_b", "title": "Source B", "text": "The result depends on baseline severity."},
            ],
        }
    )
