from __future__ import annotations

import re

from epistemic_case_mapper.map_briefing_memo_ready_presentation import run_memo_ready_presentation_normalization
from epistemic_case_mapper.map_briefing_source_id_projection import project_memo_ready_packet_source_ids
from epistemic_case_mapper.map_briefing_source_identity import source_id_alias_map, source_ids_for_labels


def test_projection_makes_source_ids_opaque_and_preserves_lineage() -> None:
    packet = _packet()

    projected = project_memo_ready_packet_source_ids(packet)
    source = projected["source_trail"][0]
    source_id = source["source_id"]

    assert re.fullmatch(r"SRC_[A-Z2-7]{8}", source_id)
    assert source["citation_key"] == source_id
    assert source["source_slug"] == "jama_2019_dietary_cholesterol_eggs"
    assert source["original_source_id"] == "jama_2019_dietary_cholesterol_eggs"
    assert projected["evidence_items"][0]["source_ids"] == [source_id]
    assert projected["canonical_decision_writer_packet"]["priority_evidence"][0]["source_ids"] == [source_id]
    assert projected["canonical_decision_writer_packet"]["source_weight_judgments"][0]["source_ids"] == [source_id]
    assert projected["source_identity_projection"]["status"] == "ready"


def test_projection_is_idempotent_and_aliases_old_ids_to_opaque_id() -> None:
    projected_once = project_memo_ready_packet_source_ids(_packet())
    projected_twice = project_memo_ready_packet_source_ids(projected_once)
    source_id = projected_once["source_trail"][0]["source_id"]

    assert projected_twice["source_trail"][0]["source_id"] == source_id
    aliases = source_id_alias_map(projected_once["source_trail"])
    assert aliases["jama_2019_dietary_cholesterol_eggs"] == source_id
    assert source_ids_for_labels(["Zhong et al. 2019"], projected_once["source_trail"]) == [source_id]


def test_presentation_normalizes_opaque_source_ids_to_reader_labels() -> None:
    projected = project_memo_ready_packet_source_ids(_packet())
    source_id = projected["source_trail"][0]["source_id"]
    memo = f"# Decision Memo\n\n**Bottom Line:** Moderate intake is bounded by observational risk [{source_id}]."

    result = run_memo_ready_presentation_normalization(memo, projected)

    assert "[Zhong et al. 2019]" in result["memo"]
    assert f"[{source_id}]" not in result["memo"]
    assert "[Zhong et al. 2019]: CITATION_TRACE.md#zhong-et-al-2019" in result["memo"]


def test_presentation_compacts_projected_institutional_source_from_original_slug() -> None:
    packet = {
        "decision_question": "Should dietary advice treat eggs as neutral?",
        "source_trail": [
            {
                "source_id": "dga_2020_2025_pmc_summary",
                "source_label": "U.S. Department of Agriculture and U.S. Department of Health and Human Services 2020",
                "source_url": "https://example.test/dga",
            }
        ],
        "evidence_items": [],
        "canonical_decision_writer_packet": {},
        "memo_warning_packet": {"warnings": []},
    }
    projected = project_memo_ready_packet_source_ids(packet)
    source_id = projected["source_trail"][0]["source_id"]
    memo = f"# Decision Memo\n\nThe guidance context cites [{source_id}] and [U S 2020]."

    result = run_memo_ready_presentation_normalization(memo, projected)

    assert "The guidance context cites [DGA 2020]" in result["memo"]
    assert "[U S 2020]" not in result["memo"]
    assert f"[{source_id}]" not in result["memo"]
    assert "* [DGA 2020](https://example.test/dga)" in result["memo"]


def _packet() -> dict:
    return {
        "decision_question": "What should an investigator believe about eating eggs?",
        "source_trail": [
            {
                "source_id": "jama_2019_dietary_cholesterol_eggs",
                "source_label": "Associations of Dietary Cholesterol or Egg Consumption With Incident Cardiovascular Disease and Mortality",
                "citation_label": "Zhong et al. 2019",
                "source_url": "https://example.test/zhong",
            }
        ],
        "evidence_items": [
            {
                "item_id": "item_001",
                "reader_claim": "Higher egg consumption is associated with higher risk.",
                "source_ids": ["jama_2019_dietary_cholesterol_eggs"],
                "source_labels": ["Zhong et al. 2019"],
                "must_use": True,
            }
        ],
        "canonical_decision_writer_packet": {
            "decision_question": "What should an investigator believe about eating eggs?",
            "decision_brief_skeleton": {
                "direct_answer": "Moderate intake is not clearly harmful, but high intake is bounded by subgroup risk.",
                "scope": "Healthy adults versus high-risk subgroups.",
                "confidence": "medium",
                "main_reason": "Evidence distinguishes moderate from high intake.",
                "strongest_counterweight": "Observational confounding remains.",
                "counterweight_disposition": "Bounds confidence.",
            },
            "decision_answer_classification": {"answer_shape": "single_stance"},
            "priority_evidence": [{"source_ids": ["jama_2019_dietary_cholesterol_eggs"]}],
            "counterweight_dispositions": [{"source_ids": ["jama_2019_dietary_cholesterol_eggs"]}],
            "source_weighted_answer_frame": {"lanes": {"primary_answer_drivers": [{"source_ids": ["jama_2019_dietary_cholesterol_eggs"]}]}},
            "source_weight_notes": [{"source_ids": ["jama_2019_dietary_cholesterol_eggs"], "decision_directness": "direct"}],
            "source_weight_judgments": [
                {
                    "source_ids": ["jama_2019_dietary_cholesterol_eggs"],
                    "main_use": "drives_answer",
                    "why_weight_this_way": "Use for the central association evidence.",
                    "evidence_item_ids": ["item_001"],
                }
            ],
            "source_weight_judgment_report": {"status": "ready"},
            "mandatory_retention_checklist": [{"source_ids": ["jama_2019_dietary_cholesterol_eggs"]}],
            "organized_evidence_inventory": {"lanes": {"support": [{"source_ids": ["jama_2019_dietary_cholesterol_eggs"]}]}},
            "evidence_language_contracts": [{"source_ids": ["jama_2019_dietary_cholesterol_eggs"]}],
            "evidence_weighted_argument_spine": {"steps": [{"source_ids": ["jama_2019_dietary_cholesterol_eggs"]}], "quality_report": {"status": "ready"}},
        },
    }
