from __future__ import annotations

from typing import Any


def decision_model_required_output_schema(decision_question: Any) -> dict[str, Any]:
    return {
        "schema_id": "analyst_decision_model_v2",
        "decision_question": decision_question,
        "active_evidence_universe": {
            "evidence_row_count": "number of rows considered for the decision model",
            "full_reasoning_evidence_item_ids": ["evidence IDs used for full reasoning"],
            "routed_away_evidence_item_ids": ["evidence IDs kept for audit but not full reasoning"],
            "source_ids": ["source IDs represented in the active evidence universe"],
        },
        "direct_answer": "complete bounded answer, including important secondary calibration or boundary detail",
        "primary_answer": "crisp first-sentence answer before secondary calibration, exception, or subgroup detail",
        "secondary_detail": "important calibration, exception, subgroup, or boundary detail that should appear after the BLUF if present",
        "secondary_detail_type": "scope_boundary | counterweight_or_calibration | secondary_calibration | none",
        "full_direct_answer": "same substance as direct_answer; use when direct_answer is intentionally split into primary_answer plus secondary_detail",
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
                "result_tuple_ids": ["source result_tuple_id values when supplied in context for this quantity"],
                "memo_inclusion": "must_use | supporting_context | trace_only | exclude",
                "quantity_role": "decision_anchor | supporting_detail | study_descriptor | statistical_detail | audit_only",
                "retention_phrase": "reader-facing wording to use if this quantity is must_use or supporting_context, otherwise empty",
                "rationale": "why this quantity is reader-facing or audit-only for the decision question",
            }
        ],
        "source_hierarchy": {
            "schema_id": "source_weight_hierarchy_v1",
            "hierarchy_thesis": "one concise paragraph explaining the comparative source hierarchy for the decision",
            "lanes": {
                "primary_answer_drivers": [
                    {
                        "source_ids": ["source_id"],
                        "evidence_item_ids": ["evidence ID from context"],
                        "role": "what this lane does for the decision",
                        "rationale": "why this source belongs in this role",
                    }
                ],
                "quantitative_calibrators": [
                    {
                        "source_ids": ["source_id"],
                        "evidence_item_ids": ["evidence ID from context"],
                        "role": "what this lane does for the decision",
                        "rationale": "why this source belongs in this role",
                    }
                ],
                "counterweight_sources": [
                    {
                        "source_ids": ["source_id"],
                        "evidence_item_ids": ["evidence ID from context"],
                        "role": "what this lane does for the decision",
                        "rationale": "why this source belongs in this role",
                    }
                ],
                "scope_boundary_sources": [
                    {
                        "source_ids": ["source_id"],
                        "evidence_item_ids": ["evidence ID from context"],
                        "role": "what this lane does for the decision",
                        "rationale": "why this source belongs in this role",
                    }
                ],
                "contextual_sources": [
                    {
                        "source_ids": ["source_id"],
                        "evidence_item_ids": ["evidence ID from context"],
                        "role": "what this lane does for the decision",
                        "rationale": "why this source belongs in this role",
                    }
                ],
            },
            "source_accounting": [
                {
                    "source_id": "source_id",
                    "primary_lane": "one lane key above",
                    "rationale": "why this is the source's primary role",
                }
            ],
        },
        "counterweight_dispositions": [
            {
                "evidence_item_ids": ["evidence IDs carrying the counterweight"],
                "disposition": "changes_answer | lowers_confidence | bounds_scope | outweighed | unresolved",
                "rationale": "how this counterweight should affect the answer",
            }
        ],
        "cruxes": [
            {
                "crux": "uncertainty or condition that matters to the decision",
                "evidence_item_ids": ["evidence IDs bearing on it"],
                "current_read": "what the present evidence suggests",
            }
        ],
        "update_triggers": [
            {
                "trigger": "new evidence or condition that would change the decision read",
                "why_it_matters": "decision impact",
            }
        ],
        "practical_implications": [
            {
                "implication": "action-facing implication",
                "evidence_item_ids": ["evidence IDs supporting it"],
                "source_ids": ["source IDs supporting it"],
                "scope": "where it applies",
            }
        ],
        "do_not_overstate_constraints": ["unsupported stronger claims the memo should avoid"],
        "appendix_accounting": [
            {
                "evidence_item_id": "evidence ID accounted for outside foreground prose",
                "reason": "why it is appendix/background/trace-only",
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
