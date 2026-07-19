from __future__ import annotations

import json


def fake_global_task_payload(prompt: str) -> dict:
    payload = json.loads(prompt)
    schema = payload["required_output_schema"]["schema_id"]
    context = payload["context"]
    rows = (
        context.get("evidence_rows")
        or context.get("decision_diagnostic_evidence_rows")
        or context.get("quantity_bearing_evidence_rows")
        or context.get("top_decision_evidence")
        or []
    )
    evidence_ids = [row["evidence_item_id"] for row in rows if row.get("evidence_item_id")]
    source_ids = sorted({source_id for row in rows for source_id in row.get("source_ids", [])}) or ["s1"]
    if schema == "global_answer_frame_v1":
        return {
            "schema_id": schema,
            "best_answer": "Adopt option A if the global evidence warrants it.",
            "confidence": "medium",
            "confidence_basis": "Global answer frame used all selected evidence.",
            "main_answer_drivers": [
                {
                    "source_ids": source_ids[:1],
                    "evidence_item_ids": evidence_ids[:2],
                    "reason": "Primary selected rows support adoption.",
                }
            ],
            "main_counterweights": [],
            "counterweight_weighting": "Counterweights bound scope when they are present.",
            "what_would_change_the_answer": ["Contrary direct evidence would change the answer."],
            "scope_boundaries": ["Applies to the tested context."],
            "practical_implication": "Use option A with monitoring.",
            "practical_implications": ["Monitor implementation."],
            "do_not_overstate": ["Do not overstate beyond the tested context."],
        }
    if schema == "global_evidence_roles_v1":
        return {
            "schema_id": schema,
            "evidence_roles": [
                {
                    "evidence_item_id": row["evidence_item_id"],
                    "memo_inclusion": "memo_spine",
                    "decision_role": "answer_driver",
                    "answer_relation": "supports_answer",
                    "priority_rank": index,
                    "rationale": "Global role assignment.",
                }
                for index, row in enumerate(rows, start=1)
            ],
        }
    if schema == "global_evidence_reconciliation_v1":
        return {
            "schema_id": schema,
            "groups": [
                {
                    "group_id": "primary_group",
                    "proposition": "Primary selected rows support the answer.",
                    "role": "answer_driver",
                    "answer_relation": "supports_answer",
                    "priority_band": "high",
                    "evidence_item_ids": evidence_ids[:6],
                    "qualifier": "",
                    "rationale": "Global reconciliation grouped the selected evidence.",
                }
            ],
            "overrides": [],
            "unresolved_evidence_item_ids": [],
        }
    if schema == "global_quantity_plan_v1":
        return {
            "schema_id": schema,
            "quantity_decisions": [
                {
                    "evidence_item_id": row["evidence_item_id"],
                    "quantity_value": quantity,
                    "memo_inclusion": "supporting_context",
                    "quantity_role": "supporting_detail",
                    "retention_phrase": quantity,
                    "rationale": "Quantity helps calibrate the answer.",
                }
                for row in rows
                for quantity in row.get("quantity_values", [])
            ],
        }
    if schema == "source_weight_hierarchy_v1":
        return {
            "schema_id": schema,
            "hierarchy_thesis": "Global source hierarchy.",
            "lanes": {
                "primary_answer_drivers": [
                    {
                        "source_ids": source_ids[:1],
                        "evidence_item_ids": evidence_ids[:4],
                        "role": "Primary source role.",
                        "rationale": "Primary sources carry the answer.",
                    }
                ],
                "quantitative_calibrators": [],
                "counterweight_sources": [],
                "scope_boundary_sources": [],
                "contextual_sources": [],
            },
            "source_accounting": [
                {
                    "source_id": source_id,
                    "primary_lane": "primary_answer_drivers",
                    "rationale": "Accounted by global source hierarchy.",
                }
                for source_id in source_ids
            ],
        }
    if schema == "global_source_weighting_guidance_v1":
        return {
            "schema_id": schema,
            "source_weight_judgments": [
                {
                    "source_ids": [source_id],
                    "source_type": "evidence_synthesis",
                    "main_use": "drives_answer" if index == 1 else "contextualizes",
                    "why_weight_this_way": f"Source {source_id} has a distinct decision role.",
                    "reader_facing_limit": "Use according to its supplied evidence role.",
                    "what_not_to_use_it_for": ["Do not use as broader proof than the evidence supports."],
                    "memo_weight_sentence": f"Use {source_id} for its assigned decision role.",
                    "confidence_effect": "raises_confidence" if index == 1 else "neutral",
                    "evidence_item_ids": evidence_ids[:2],
                }
                for index, source_id in enumerate(source_ids, start=1)
            ],
        }
    if schema == "global_argument_blueprint_v1":
        return {
            "schema_id": schema,
            "memo_thesis": "Option A has a global argument blueprint.",
            "section_plan": [
                {
                    "section_id": "answer",
                    "heading": "Why Option A Is Supported",
                    "section_job": "Explain the answer-driving evidence.",
                    "core_claim": "The selected evidence supports option A.",
                    "must_use_evidence_item_ids": evidence_ids[:6],
                    "must_use_quantities": [],
                    "source_weighting_move": "Use primary sources as answer drivers.",
                    "transition": "Then apply monitoring.",
                }
            ],
            "footnote_or_appendix_material": [],
        }
    return {}
