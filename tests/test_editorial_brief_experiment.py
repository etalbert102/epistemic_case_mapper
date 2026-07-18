from __future__ import annotations

from pathlib import Path

from epistemic_case_mapper.map_briefing_editorial_brief_experiment import (
    VARIANTS,
    build_source_weighted_outline_integrated_section_plan,
    build_outline_contract_integration_report,
    build_outline_active_evidence_ids,
    build_outline_owned_memo_ready_packet,
    build_opinionated_section_plan,
    build_editorial_brief_prompt,
    deterministic_source_weighted_narrative_outline,
    deterministic_editorial_brief,
    run_editorial_brief_instruction_experiment,
    run_editorial_brief_memo_generation,
    run_source_weighted_narrative_outline_experiment,
    score_editorial_brief,
)


def test_editorial_brief_prompt_variants_expose_different_context_sizes() -> None:
    section = _section_packet()
    minimal = next(variant for variant in VARIANTS if variant.variant_id == "minimal_thesis")
    full = next(variant for variant in VARIANTS if variant.variant_id == "full_packet_control")

    minimal_prompt = build_editorial_brief_prompt(section, minimal)
    full_prompt = build_editorial_brief_prompt(section, full)

    assert "editorial_brief_v1" in minimal_prompt
    assert "section_thesis" in minimal_prompt
    assert len(minimal_prompt) < len(full_prompt)
    assert "validation_contract" not in minimal_prompt
    assert "validation_contract" in full_prompt


def test_editorial_brief_scoring_rewards_compact_coverage() -> None:
    section = _section_packet()
    variant = next(variant for variant in VARIANTS if variant.variant_id == "source_weighted")
    prompt = build_editorial_brief_prompt(section, variant)
    brief = deterministic_editorial_brief(section, variant)

    score = score_editorial_brief(brief, prompt=prompt, section_packet=section)

    assert score["score"] >= 80
    assert score["source_coverage"] == 1.0
    assert score["evidence_count"] >= 1
    assert not score["missing_fields"]


def test_editorial_brief_instruction_experiment_writes_summary(tmp_path: Path) -> None:
    packet = _memo_ready_packet()

    summary = run_editorial_brief_instruction_experiment(
        packet,
        output_dir=tmp_path / "experiment",
        backend="prompt",
    )

    assert summary["schema_id"] == "editorial_brief_instruction_experiment_v1"
    assert summary["section_count"] >= 1
    assert summary["recommended_variant"]
    assert (tmp_path / "experiment/editorial_brief_instruction_experiment.json").exists()
    assert (tmp_path / "experiment/EDITORIAL_BRIEF_INSTRUCTION_EXPERIMENT.md").exists()


def test_editorial_brief_memo_generation_writes_variant_memos(tmp_path: Path) -> None:
    summary = run_editorial_brief_memo_generation(
        _memo_ready_packet(),
        output_dir=tmp_path / "memos",
        variant_ids=["decision_curated", "source_weighted"],
        backend="prompt",
    )

    assert summary["schema_id"] == "editorial_brief_memo_generation_comparison_v1"
    assert summary["variant_count"] == 2
    assert summary["best_by_proxy"]
    assert (tmp_path / "memos/decision_curated/MEMO.md").exists()
    assert (tmp_path / "memos/source_weighted/MEMO.md").exists()


def test_source_weighted_narrative_outline_experiment_writes_outputs(tmp_path: Path) -> None:
    summary = run_source_weighted_narrative_outline_experiment(
        _memo_ready_packet(),
        output_dir=tmp_path / "outline",
        backend="prompt",
    )

    assert summary["schema_id"] == "source_weighted_narrative_outline_experiment_v1"
    assert summary["outline_status"] == "prompt_mode_target"
    assert summary["score"]["score"] >= 70
    assert (tmp_path / "outline/source_weighted_narrative_outline.json").exists()
    assert (tmp_path / "outline/OUTLINE_GUIDED_MEMO.md").exists()
    assert (tmp_path / "outline/SOURCE_WEIGHTED_NARRATIVE_OUTLINE_EXPERIMENT.md").exists()


def test_source_weighted_outline_integrates_with_section_plan() -> None:
    packet = _memo_ready_packet()

    from epistemic_case_mapper.map_briefing_memo_ready_prompt import build_memo_ready_section_synthesis_plan

    section_plan = build_memo_ready_section_synthesis_plan(packet)
    variant = next(variant for variant in VARIANTS if variant.variant_id == "source_weighted")
    briefs = [
        deterministic_editorial_brief(section["packet"], variant)
        for section in section_plan["sections"]
    ]
    outline = deterministic_source_weighted_narrative_outline(packet, editorial_briefs=briefs)
    integrated = build_source_weighted_outline_integrated_section_plan(section_plan, outline)

    assert integrated["bottom_line"] != section_plan["bottom_line"]
    first_packet = integrated["sections"][0]["packet"]
    assert first_packet["top_context"]["current_read_reference"] == integrated["bottom_line"]
    assert first_packet["section_focus"]["paragraph_shape"]


def test_opinionated_section_plan_adds_distinct_section_jobs() -> None:
    plan = {
        "schema_id": "memo_ready_section_synthesis_plan_v1",
        "sections": [
            {
                "section_id": "answer_evidence",
                "heading": "Why This Is the Best Current Read",
                "packet": {
                    "section_id": "answer_evidence",
                    "heading": "Why This Is the Best Current Read",
                    "section_focus": {"paragraph_shape": ["Existing move."]},
                    "section_role_contract": {"do": ["Existing job."]},
                    "evidence_context": [{"item_id": "support"}],
                },
            }
        ],
    }

    updated, report = build_opinionated_section_plan(plan)
    packet = updated["sections"][0]["packet"]

    assert report["status"] == "changed"
    assert "State the positive case for the current read in one clear analytic move." in packet["section_role_contract"]["do"]
    assert "Lead with the direct answer evidence and its supported scope." in packet["section_focus"]["paragraph_shape"]
    assert packet["evidence_context"] == [{"item_id": "support"}]


def test_outline_owned_packet_demotes_non_outline_required_evidence() -> None:
    packet = _memo_ready_packet()
    outline = {
        "schema_id": "source_weighted_narrative_outline_v1",
        "answer_order": ["Adopt option A where implementation capacity is adequate."],
        "narrative_arc": [{"evidence_ids": ["support"]}],
        "section_guidance": [],
    }
    packet["evidence_items"].append(
        {
            "item_id": "residue",
            "claim": "Appendix-only extraction with low atomicity or low decision relevance; use only as source context.",
            "source_ids": ["study_a"],
            "must_use": True,
            "obligation_level": "must_include",
            "role": "strongest_support",
            "quantities": [{"value": "999 mg", "interpretation": "residue"}],
        }
    )
    packet["canonical_decision_writer_packet"].setdefault("mandatory_retention_checklist", []).append(
        {
            "obligation_id": "residue_obligation",
            "evidence_item_ids": ["residue"],
            "statement": "Retain residue.",
        }
    )
    packet["canonical_decision_writer_packet"]["source_weight_judgments"] = [
        {
            "source_ids": ["study_a"],
            "evidence_item_ids": ["support", "residue"],
            "weight_role": "driver",
            "rationale": "Study A carries the answer.",
        }
    ]
    packet["canonical_decision_writer_packet"]["reader_judgment_packet"] = {
        "judgments": [
            {
                "judgment_id": "j1",
                "evidence_item_ids": ["support", "residue"],
                "judgment": "Use the support evidence.",
            },
            {
                "judgment_id": "j2",
                "evidence_item_ids": ["residue"],
                "judgment": "Use residue.",
            },
        ]
    }
    packet["memo_obligations"] = {
        "schema_id": "memo_obligations_v1",
        "obligations": [
            {"obligation_id": "keep_support", "required": True, "evidence_item_ids": ["support"]},
            {"obligation_id": "drop_residue", "required": True, "evidence_item_ids": ["residue"]},
        ],
    }

    active = build_outline_owned_memo_ready_packet(packet, outline)
    active_ids = {item["item_id"] for item in active["evidence_items"]}
    report = build_outline_contract_integration_report(packet, active, outline)

    assert "residue" not in active_ids
    assert "residue" in report["demoted_required_evidence_ids"]
    assert "canonical_decision_writer_packet" not in active
    assert "writer_decision_interface" not in active
    assert active["answer_spine"]["default_read"] == "Adopt option A where implementation capacity is adequate."
    assert [row["obligation_id"] for row in active["memo_obligations"]["obligations"]] == ["keep_support"]


def test_outline_owned_packet_preserves_critical_evidence_omitted_by_outline() -> None:
    packet = _memo_ready_packet()
    packet["evidence_items"].append(
        {
            "item_id": "critical_counterweight",
            "claim": "A critical counterweight could change the answer.",
            "source_ids": ["study_a"],
            "must_use": True,
            "obligation_level": "must_include",
            "role": "strongest_counterweight",
            "answer_relation": "challenges_answer",
        }
    )
    outline = {
        "schema_id": "source_weighted_narrative_outline_v1",
        "answer_order": ["Adopt option A where implementation capacity is adequate."],
        "narrative_arc": [{"evidence_ids": ["support"]}],
        "section_guidance": [],
    }

    active_ids = build_outline_active_evidence_ids(packet, outline, protect_critical_evidence=True)
    active = build_outline_owned_memo_ready_packet(packet, outline, active_evidence_ids=active_ids)
    counterweight = next(item for item in active["evidence_items"] if item["item_id"] == "critical_counterweight")

    assert "critical_counterweight" in active_ids
    assert counterweight["must_use"] is True
    assert counterweight["obligation_level"] == "must_include"


def _memo_ready_packet() -> dict:
    return {
        "schema_id": "memo_ready_packet_v1",
        "decision_question": "Should the city adopt option A?",
        "source_trail": [{"source_id": "study_a", "source_label": "Study A"}],
        "evidence_items": [
            {
                "item_id": "support",
                "claim": "Option A reduced flood losses by 20%.",
                "source_ids": ["study_a"],
                "must_use": True,
                "decision_relevance": "Directly supports adoption.",
                "quantities": ["20%"],
            }
        ],
        "canonical_decision_writer_packet": {
            "schema_id": "canonical_decision_writer_packet_v1",
            "decision_question": "Should the city adopt option A?",
            "decision_brief_skeleton": {
                "primary_answer": "Adopt option A where implementation capacity is adequate.",
                "confidence": "medium",
                "scope": "Applies to flood-prone neighborhoods with implementation capacity.",
            },
            "bluf_contract": {
                "recommended_read": "Adopt option A where implementation capacity is adequate.",
                "secondary_detail": "The strongest evidence is direct loss reduction, bounded by implementation risk.",
            },
            "source_weight_judgments": [
                {
                    "source_ids": ["study_a"],
                    "weight_role": "driver",
                    "rationale": "Study A directly measures the decision outcome.",
                }
            ],
            "priority_evidence": [
                {
                    "item_id": "support",
                    "claim": "Option A reduced flood losses by 20%.",
                    "source_ids": ["study_a"],
                    "quantities": ["20%"],
                    "why_it_matters": "This sizes the main benefit.",
                }
            ],
            "evidence_language_contracts": [],
            "evidence_weighted_argument_spine": {
                "section_plan": [
                    {
                        "section_id": "answer_evidence",
                        "heading": "Why This Is the Best Current Read",
                        "primary_section": True,
                        "must_include_points": ["Study A directly measures flood losses."],
                    }
                ],
                "steps": [
                    {
                        "step_id": "step_1",
                        "section_id": "answer_evidence",
                        "claim": "Option A reduced flood losses by 20%.",
                        "source_ids": ["study_a"],
                        "quantities": ["20%"],
                    }
                ],
            },
        },
    }


def _section_packet() -> dict:
    return {
        "schema_id": "memo_ready_section_writer_packet_v1",
        "section_id": "answer_evidence",
        "heading": "Why This Is the Best Current Read",
        "section_job": "Explain why the main answer follows from the driver evidence.",
        "section_role_contract": {
            "avoid": ["turning into a source inventory", "previewing all implementation caveats"],
        },
        "section_focus": {
            "reader_question": "Why should I believe this answer?",
            "prose_lead": "Open with the direct evidence that Option A reduced flood losses by 20%.",
            "new_value": "make the positive case for the current read",
            "paragraph_shape": ["driver evidence", "source weighting", "confidence boundary"],
        },
        "required_points": ["Study A directly measures flood losses rather than a proxy endpoint."],
        "source_bound_evidence_atoms": [
            {
                "evidence_id": "support",
                "source_ids": ["study_a"],
                "citation_role": "direct_support",
                "writing_job": "Use this as the load-bearing benefit estimate.",
                "protected_quantities": ["20%"],
            }
        ],
        "source_weighting": [
            {
                "source_ids": ["study_a"],
                "weight_role": "driver",
                "rationale": "Study A directly measures the decision outcome.",
            }
        ],
        "validation_contract": {"status": "ready"},
    }
