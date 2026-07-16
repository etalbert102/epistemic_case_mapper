from __future__ import annotations

from epistemic_case_mapper.map_briefing_lightweight_guidance import (
    attach_lightweight_guidance_to_packet,
    build_lightweight_writer_guidance_prompt,
    compact_lightweight_guidance_for_prompt,
    evidence_quality_caveat_text,
    normalize_lightweight_writer_guidance,
)


def test_lightweight_writer_guidance_prompt_uses_compact_post_analyst_context() -> None:
    canonical = {
        "decision_question": "Should dietary advice treat one egg per day as acceptable?",
        "decision_brief_skeleton": {"bottom_line": "bounded neutral"},
        "source_weight_judgments": [{"source_ids": ["s1"], "main_use": "drives_answer"}],
        "priority_evidence": [{"reader_claim": "One egg per day was not associated with higher CVD risk."}],
    }
    scaffold = {
        "evidence_quality_report": {
            "weak_or_indirect_count": 1,
            "quality_components": [{"source_ids": ["s1"], "warning": "observational evidence"}],
        },
        "analyst_quantity_binding_report": {
            "approved_bindings": [
                {
                    "value": "1 egg/day",
                    "interpretation": "moderate intake endpoint",
                    "source_ids": ["s1"],
                }
            ]
        },
    }

    prompt = build_lightweight_writer_guidance_prompt(canonical_packet=canonical, scaffold=scaffold)

    assert "lightweight_writer_guidance_v1" in prompt
    assert "Should dietary advice treat one egg per day as acceptable?" in prompt
    assert "observational evidence" in prompt
    assert "quantity wording" in prompt
    assert "source_weight_hierarchy_v1" in prompt
    assert "source_inventory" in prompt
    assert "Create guidance for the later memo writer" in prompt


def test_lightweight_writer_guidance_normalizes_and_compacts_model_output() -> None:
    guidance = normalize_lightweight_writer_guidance(
        {
            "overall_judgment": "State the answer, then explain evidence limits.",
            "reader_guidance": [{"guidance": "Use the cohort evidence as direct support.", "source_ids": ["s1"]}],
            "evidence_quality_caveats": [
                {"description": "This is observational evidence, so avoid causal wording.", "source_ids": ["s1"]}
            ],
            "quantity_wording_risks": [
                {
                    "risk": "1 egg/day and concentration changes are different endpoints.",
                    "recommended_wording": "Keep intake and biomarker endpoints in separate clauses.",
                }
            ],
            "source_hierarchy": {
                "hierarchy_thesis": "Use outcomes first, then mechanism evidence.",
                "lanes": {
                    "primary_answer_drivers": [
                        {"source_ids": ["s1", "bad_source"], "rationale": "It directly measures the target outcome."}
                    ],
                    "quantitative_calibrators": [
                        {"source_ids": ["s2"], "rationale": "It sizes the endpoint."}
                    ],
                },
                "source_accounting": [
                    {"source_id": "s1", "primary_lane": "primary_answer_drivers", "rationale": "Direct outcome."},
                    {"source_id": "bad_source", "primary_lane": "primary_answer_drivers"},
                ],
            },
            "do_not_overstate": ["Do not claim eggs reduce cardiovascular risk."],
            "suggested_reader_flow": ["answer first"],
        },
        allowed_source_ids=["s1", "s2"],
    )

    compact = compact_lightweight_guidance_for_prompt(guidance)

    assert guidance["schema_id"] == "lightweight_writer_guidance_v1"
    assert guidance["summary"]["evidence_quality_caveat_count"] == 1
    assert guidance["source_hierarchy_report"]["status"] == "warning"
    assert guidance["source_hierarchy_report"]["invalid_source_ids_removed"] == ["bad_source"]
    assert guidance["source_hierarchy"]["lanes"]["primary_answer_drivers"][0]["source_ids"] == ["s1"]
    assert evidence_quality_caveat_text(guidance, ["s1"]) == [
        "This is observational evidence, so avoid causal wording."
    ]
    assert compact["quantity_wording_risks"][0]["safe_wording"] == "Keep intake and biomarker endpoints in separate clauses."
    assert compact["source_hierarchy"]["lanes"]["primary_answer_drivers"][0]["source_ids"] == ["s1"]


def test_attach_lightweight_guidance_updates_top_level_and_canonical_packet() -> None:
    packet = {"canonical_decision_writer_packet": {"schema_id": "canonical_decision_writer_packet_v1"}}
    bundle = {
        "lightweight_writer_guidance": {"schema_id": "lightweight_writer_guidance_v1", "reader_guidance": []},
        "lightweight_writer_guidance_report": {"status": "parsed"},
    }

    updated = attach_lightweight_guidance_to_packet(packet, bundle)

    assert updated["lightweight_writer_guidance"]["schema_id"] == "lightweight_writer_guidance_v1"
    assert updated["canonical_decision_writer_packet"]["lightweight_writer_guidance"]["schema_id"] == "lightweight_writer_guidance_v1"
    assert updated["canonical_decision_writer_packet"]["lightweight_writer_guidance_report"]["status"] == "parsed"
