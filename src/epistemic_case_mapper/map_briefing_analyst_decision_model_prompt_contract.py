from __future__ import annotations

from typing import Any


def decision_model_required_output_schema(decision_question: Any) -> dict[str, Any]:
    return {
        "schema_id": "analyst_decision_model_v1",
        "decision_question": decision_question,
        "direct_answer": "one sentence answering the decision question",
        "confidence": "low | medium | high | not_specified",
        "overall_rationale": "why the evidence groups support this answer",
        "evidence_groups": [
            {
                "group_id": "stable group label",
                "proposition": "decision-relevant proposition synthesized across covered evidence",
                "memo_role": "one allowed_memo_role value",
                "answer_relation": (
                    "supports_answer | challenges_answer | bounds_scope | identifies_crux | "
                    "contextualizes_answer | not_decision_relevant | uncertain_relation"
                ),
                "target_answer_option": "the answer option or stance this group most directly bears on",
                "effect_on_final_answer": (
                    "supports current_best_answer | weakens current_best_answer | bounds current_best_answer | "
                    "supports target answer | weakens target answer | bounds target answer | rebuts alternative | "
                    "distinguishes live options | explains tension | background"
                ),
                "tension_type": "none | clinical_outcome_vs_biomarker | subgroup_scope | dose_scope | study_conflict | mechanism | other",
                "importance_rank": "integer 1-100; 1 is most important globally",
                "covered_evidence_item_ids": ["evidence IDs from context"],
                "rationale": "why this group matters to the decision",
                "evidence_strength": "brief strength assessment",
                "answer_impact": "how this group supports, weakens, bounds, or changes the answer",
                "uncertainty_type": "measurement, external validity, confounding, missing evidence, implementation, none, or other",
                "applicability_limits": ["scope/population/context limits"],
                "conflict_note": "how this group relates to conflicting evidence, if any",
            }
        ],
        "evidence_dispositions": [
            {
                "evidence_item_id": "evidence ID from context",
                "disposition": "one allowed_disposition value",
                "group_id": "group that uses or covers this item, if applicable",
                "rationale": "why it is backgrounded, excluded, or needs review; omit rows already covered by evidence_groups unless there is a special reason",
            }
        ],
        "memo_relevance_decisions": [
            {
                "evidence_item_id": "evidence ID from context",
                "memo_inclusion": "memo_spine | supporting_context | trace_only | exclude",
                "group_id": "evidence_group that owns this decision, if applicable",
                "source_ids": ["source IDs supporting the evidence item"],
                "rationale": "transparent reason this evidence should appear in memo prose, remain trace-only, or be excluded",
            }
        ],
        "quantity_relevance_decisions": [
            {
                "evidence_item_id": "evidence ID from context",
                "quantity_value": "copy the quantity exactly from the evidence row",
                "memo_inclusion": "must_use | supporting_context | trace_only | exclude",
                "quantity_role": "decision_anchor | supporting_detail | study_descriptor | statistical_detail | audit_only",
                "retention_phrase": "reader-facing wording to use if this quantity is must_use or supporting_context, otherwise empty",
                "rationale": "why this quantity is reader-facing or audit-only for the decision question",
            }
        ],
        "quantitative_anchors": ["quantities that should survive final synthesis"],
        "what_would_change_the_answer": ["cruxes or missing evidence that would change the answer"],
        "decision_logic": {
            "bounded_bottom_line": "specific answer with confidence boundary",
            "support_summary": "load-bearing support in one or two sentences",
            "strongest_counterweight": "strongest contrary or limiting consideration",
            "counterweight_weighting": "why it changes, weakens, or only bounds the answer",
            "reconciled_cruxes": ["cruxes written as resolved analyst guidance where possible"],
            "scope_boundaries": ["where the answer applies and its relevant boundaries"],
            "practical_implications": ["decision implications"],
            "do_not_overstate": ["claims outside the supported conclusion"],
        },
        "argument_plan": [
            {
                "step_id": "stable step label",
                "section": "memo section",
                "writing_goal": "what this paragraph must accomplish",
                "required_points": ["claims, quantities, caveats, or comparisons to include"],
                "evidence_item_ids": ["evidence IDs this step uses"],
                "transition_from_previous": "how this reasoning step should connect",
            }
        ],
    }
