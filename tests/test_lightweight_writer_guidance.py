from __future__ import annotations

from epistemic_case_mapper.pipeline.briefing.map_briefing_lightweight_guidance import (
    attach_lightweight_guidance_to_packet,
    build_lightweight_writer_guidance_prompt,
    compact_lightweight_guidance_for_prompt,
    evidence_quality_caveat_text,
    normalize_lightweight_writer_guidance,
    run_lightweight_writer_guidance,
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
    assert "source_inventory" in prompt
    assert "Create guidance for the later memo writer" in prompt
    assert "source_weight_hierarchy_v1" not in prompt


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
            "do_not_overstate": ["Do not claim eggs reduce cardiovascular risk."],
            "suggested_reader_flow": ["answer first"],
        },
        allowed_source_ids=["s1", "s2"],
    )

    compact = compact_lightweight_guidance_for_prompt(guidance)

    assert guidance["schema_id"] == "lightweight_writer_guidance_v1"
    assert guidance["summary"]["evidence_quality_caveat_count"] == 1
    assert "source_hierarchy" not in guidance
    assert "source_hierarchy_report" not in guidance
    assert evidence_quality_caveat_text(guidance, ["s1"]) == [
        "This is observational evidence, so avoid causal wording."
    ]
    assert compact["quantity_wording_risks"][0]["safe_wording"] == "Keep intake and biomarker endpoints in separate clauses."
    assert "source_hierarchy" not in compact


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


def test_lightweight_guidance_reuses_writer_packet_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ECM_LIGHTWEIGHT_GUIDANCE_MODE", raising=False)
    canonical = {
        "balanced_answer_frame": {"default_answer": "Use option A with monitoring."},
        "source_weight_judgments": [
            {
                "source_ids": ["s1"],
                "reader_facing_limit": "Treat this source as associative, not causal.",
            }
        ],
        "do_not_overstate": ["Do not claim causality."],
    }
    scaffold = {
        "writer_guidance_packet": {
            "guidance": [
                {
                    "instruction": "Surface the monitoring boundary.",
                    "why_it_matters": "It bounds implementation.",
                    "target_ids": ["item_1"],
                    "validation_terms": ["monitoring"],
                    "model_instruction_ready": True,
                }
            ]
        }
    }

    result = run_lightweight_writer_guidance(
        canonical_packet=canonical,
        scaffold=scaffold,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["lightweight_writer_guidance_report"]["status"] == "reused_writer_packet"
    assert result["lightweight_writer_guidance_report"]["method"] == "deterministic_writer_packet_reuse"
    assert result["lightweight_writer_guidance"]["reader_guidance"][0]["instruction"] == "Surface the monitoring boundary."
    assert result["lightweight_writer_guidance"]["evidence_quality_caveats"][0]["source_ids"] == ["s1"]
