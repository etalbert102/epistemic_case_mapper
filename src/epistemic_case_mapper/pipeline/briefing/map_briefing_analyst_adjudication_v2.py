from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CompactMemoUse = Literal[
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
    "mechanism_or_context",
    "background_only",
    "not_decision_relevant",
    "needs_human_or_model_review",
]
CompactAnswerRelation = Literal[
    "supports_answer",
    "challenges_answer",
    "bounds_scope",
    "identifies_crux",
    "contextualizes_answer",
    "not_decision_relevant",
    "uncertain_relation",
]
PriorityTier = Literal["core", "supporting", "context"]


class EvidenceAdjudicationResponseRowV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item_id: str = Field(min_length=1)
    memo_use: CompactMemoUse
    answer_relation: CompactAnswerRelation
    priority: PriorityTier
    reason: str = Field(min_length=1, max_length=360)
    guardrail: str = Field(default="", max_length=240)
    target_answer_option: str = Field(default="", max_length=160)

    @field_validator("evidence_item_id", "reason", "guardrail", "target_answer_option", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()


class AnalystAdjudicationResponseV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[EvidenceAdjudicationResponseRowV2]

    @model_validator(mode="after")
    def _unique_rows(self) -> "AnalystAdjudicationResponseV2":
        row_ids = [row.evidence_item_id for row in self.rows]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("rows must have unique evidence_item_id values")
        return self


def analyst_adjudication_response_schema_v2() -> dict[str, Any]:
    return AnalystAdjudicationResponseV2.model_json_schema()


def build_analyst_adjudication_prompt_v2(ledger: dict[str, Any]) -> str:
    rows = [_prompt_row(row) for row in _dict_rows(ledger.get("rows"))]
    packet = {
        "task": "Classify each evidence row for decision-model routing.",
        "decision_question": ledger.get("decision_question"),
        "answer_frame": _compact_answer_frame(ledger.get("stable_final_answer_frame")),
        "instructions": [
            "Return exactly one row for every supplied evidence_item_id.",
            "Classify relative to current_best_answer when one is supplied; otherwise use the relevant live answer option.",
            "Use source_bottom_lines and source_bottom_line_signals over support-shaped claim wording when they conflict.",
            "Treat candidate relation labels as provisional and judge their endpoint evidence before assigning a role.",
            "Use guardrail only for a qualifier or unsafe inference that must travel with the row.",
            "Do not copy sources, quantities, claims, or provenance into the response.",
            "Return strict JSON only.",
        ],
        "output_contract": {
            "required": ["evidence_item_id", "memo_use", "answer_relation", "priority", "reason"],
            "optional": ["guardrail", "target_answer_option"],
            "memo_use": list(CompactMemoUse.__args__),
            "answer_relation": list(CompactAnswerRelation.__args__),
            "priority": list(PriorityTier.__args__),
        },
        "evidence_rows": rows,
    }
    return (
        "You are an analyst triaging evidence before global decision modeling.\n"
        "Return a strict JSON object only.\n\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def _prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "evidence_item_id": row.get("evidence_item_id"),
        "input_kind": row.get("input_kind"),
        "current_role": row.get("current_role"),
        "current_priority": row.get("current_priority"),
        "current_weight": row.get("current_weight"),
        "directionality": row.get("directionality"),
        "relation_semantic_role": row.get("relation_semantic_role"),
        "source_ids": _strings(row.get("source_ids"))[:6],
        "source_quality": _source_quality(row),
        "quantity_values": _strings(row.get("quantity_values"))[:6],
        "claim": _short_text(row.get("claim"), 360),
        "source_bottom_lines": _source_bottom_lines(row.get("source_bottom_lines")),
        "source_bottom_line_signals": _strings(row.get("source_bottom_line_signals"))[:4],
        "why_it_matters": _short_text(row.get("why_it_matters"), 180),
        "failure_condition": _short_text(row.get("failure_condition"), 180),
        "existing_warning_codes": _strings(row.get("existing_warning_codes"))[:4],
    }
    if str(row.get("input_kind") or "") == "candidate_decision_edge":
        compact.update(
            {
                "relation_contract": _selected_dict(
                    row.get("relation_contract"),
                    ("edge_basis", "source_anchor_a", "source_anchor_b", "why_decision_relevant", "failure_condition"),
                ),
                "candidate_pair": _selected_dict(
                    row.get("candidate_pair"),
                    ("pair_id", "decision_edge_contract", "reason", "score", "pair_intent"),
                ),
                "endpoint_claims": [_endpoint_claim(item) for item in _dict_rows(row.get("endpoint_claims"))[:4]],
                "relation_endpoint_answer_matrix": row.get("relation_endpoint_answer_matrix")
                if isinstance(row.get("relation_endpoint_answer_matrix"), dict)
                else {},
            }
        )
    return _drop_empty(compact)


def _compact_answer_frame(value: Any) -> dict[str, Any]:
    frame = value if isinstance(value, dict) else {}
    return _drop_empty(
        {
            key: frame.get(key)
            for key in (
                "answer_status",
                "current_best_answer",
                "confidence",
                "classification_rule",
                "classification_target_policy",
                "live_answer_options",
            )
        }
    )


def _source_quality(row: dict[str, Any]) -> dict[str, Any]:
    appraisal = row.get("source_appraisal") if isinstance(row.get("source_appraisal"), dict) else {}
    return _drop_empty(
        {
            "quality": row.get("quality"),
            "warnings": _strings(row.get("source_use_warnings"))[:4],
            "decision_directness": appraisal.get("decision_directness"),
            "evidence_proximity": _strings(appraisal.get("evidence_proximity"))[:4],
            "recommended_uses": _strings(appraisal.get("recommended_uses"))[:4],
        }
    )


def _source_bottom_lines(value: Any) -> list[dict[str, str]]:
    return [
        _drop_empty(
            {
                "source_id": str(row.get("source_id") or ""),
                "source_bottom_line": _short_text(row.get("source_bottom_line"), 260),
                "polarity_signal": str(row.get("polarity_signal") or ""),
            }
        )
        for row in _dict_rows(value)[:4]
    ]


def _endpoint_claim(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "endpoint": row.get("endpoint"),
            "claim_id": row.get("claim_id"),
            "source_ids": _strings(row.get("source_ids"))[:4],
            "decision_edge_role": row.get("decision_edge_role"),
            "decision_function": row.get("decision_function"),
            "claim": _short_text(row.get("claim"), 240),
            "source_bottom_lines": _source_bottom_lines(row.get("source_bottom_lines")),
            "source_bottom_line_signals": _strings(row.get("source_bottom_line_signals"))[:4],
        }
    )


def _selected_dict(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    return _drop_empty({key: row.get(key) for key in keys})


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [] if value in (None, "") else [value]
    return [str(item).strip() for item in value if str(item).strip()]


def _short_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
