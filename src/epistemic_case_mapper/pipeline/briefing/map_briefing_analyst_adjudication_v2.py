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


def adapt_analyst_adjudication_v2(response: Any, ledger: dict[str, Any]) -> dict[str, Any]:
    parsed = AnalystAdjudicationResponseV2.model_validate(response)
    ledger_rows = _dict_rows(ledger.get("rows"))
    ledger_by_id = {
        str(row.get("evidence_item_id") or "").strip(): row
        for row in ledger_rows
        if str(row.get("evidence_item_id") or "").strip()
    }
    expected_ids = list(ledger_by_id)
    response_by_id = {row.evidence_item_id: row for row in parsed.rows}
    unknown_ids = sorted(set(response_by_id) - set(ledger_by_id))
    missing_ids = sorted(set(ledger_by_id) - set(response_by_id))
    if unknown_ids or missing_ids:
        raise ValueError(
            "compact adjudication must cover the ledger exactly: "
            f"missing_evidence_item_ids={missing_ids} unknown_evidence_item_ids={unknown_ids}"
        )

    rank_by_id = _global_rank_by_id(parsed.rows, ledger_by_id, expected_ids)
    rows = [
        _canonical_row(response_by_id[evidence_id], ledger_by_id[evidence_id], rank_by_id[evidence_id], ledger)
        for evidence_id in expected_ids
    ]
    return {
        "schema_id": "analyst_adjudication_v1",
        "decision_question": str(ledger.get("decision_question") or "").strip(),
        "rows": rows,
        "overall_rationale": "Compact analyst adjudication projected deterministically onto the canonical v1 artifact.",
    }


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


def _global_rank_by_id(
    rows: list[EvidenceAdjudicationResponseRowV2],
    ledger_by_id: dict[str, dict[str, Any]],
    ledger_order: list[str],
) -> dict[str, int]:
    tier_order = {"core": 0, "supporting": 1, "context": 2}
    position = {evidence_id: index for index, evidence_id in enumerate(ledger_order)}
    ordered = sorted(
        rows,
        key=lambda row: (
            tier_order[row.priority],
            _integer(ledger_by_id[row.evidence_item_id].get("current_priority"), 100),
            position[row.evidence_item_id],
        ),
    )
    return {row.evidence_item_id: min(index, 100) for index, row in enumerate(ordered, start=1)}


def _canonical_row(
    row: EvidenceAdjudicationResponseRowV2,
    ledger_row: dict[str, Any],
    importance_rank: int,
    ledger: dict[str, Any],
) -> dict[str, Any]:
    guardrail = row.guardrail
    return {
        "evidence_item_id": row.evidence_item_id,
        "memo_use": row.memo_use,
        "importance_rank": importance_rank,
        "rationale": row.reason,
        "answer_relation": row.answer_relation,
        "covered_by": [],
        "source_ids": _strings(ledger_row.get("source_ids")),
        "quantity_values": _strings(ledger_row.get("quantity_values")),
        "target_answer_option": row.target_answer_option,
        "effect_on_final_answer": _effect_on_answer(row.answer_relation, row.target_answer_option, ledger),
        "tension_type": "",
        "downgrade_reason": row.reason
        if row.memo_use in {"background_only", "not_decision_relevant"}
        else "",
        "decision_contribution": row.reason,
        "use_in_reasoning": _reasoning_use(row.memo_use),
        "key_qualifier": guardrail,
        "quantity_takeaway": "",
        "source_weight_note": "",
        "misuse_warning": guardrail,
        "if_omitted": "",
    }


def _effect_on_answer(answer_relation: str, target_answer_option: str, ledger: dict[str, Any]) -> str:
    frame = ledger.get("stable_final_answer_frame") if isinstance(ledger.get("stable_final_answer_frame"), dict) else {}
    has_current_answer = bool(str(frame.get("current_best_answer") or "").strip())
    target = "current_best_answer" if has_current_answer else "target answer" if target_answer_option else "answer"
    return {
        "supports_answer": f"supports {target}",
        "challenges_answer": f"weakens {target}",
        "bounds_scope": f"bounds {target}",
        "identifies_crux": "distinguishes live options",
        "contextualizes_answer": f"contextualizes {target}",
        "not_decision_relevant": "background",
        "uncertain_relation": "explains tension",
    }[answer_relation]


def _reasoning_use(memo_use: str) -> str:
    return {
        "load_bearing_primary_support": "answer anchor",
        "load_bearing_counterweight": "counterweight",
        "quantitative_anchor": "quantity calibrator",
        "scope_or_applicability": "scope limiter",
        "decision_crux": "decision crux",
        "mechanism_or_context": "mechanism/context",
        "background_only": "trace only",
        "not_decision_relevant": "trace only",
        "needs_human_or_model_review": "review",
    }[memo_use]


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


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
