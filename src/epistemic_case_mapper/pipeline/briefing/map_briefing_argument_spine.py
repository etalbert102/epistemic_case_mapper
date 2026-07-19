from __future__ import annotations

from collections import Counter
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


def build_evidence_weighted_argument_spine(
    *,
    skeleton: dict[str, Any],
    decision_question: Any = "",
    source_weighted_frame: dict[str, Any],
    counterweights: list[dict[str, Any]],
    scope_boundaries: list[dict[str, Any]],
    source_weight_judgments: list[dict[str, Any]],
    mandatory_retention_checklist: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    steps = [
        _answer_step(skeleton),
        *_lane_steps("primary_driver", _lane(source_weighted_frame, "primary_answer_drivers"), "Use this evidence to carry the answer."),
        *_lane_steps("calibrator", _lane(source_weighted_frame, "quantitative_or_interpretive_calibrators"), "Use this evidence to calibrate magnitude or mechanism."),
        *_counterweight_steps(counterweights),
        *_lane_steps("crux", _lane(source_weighted_frame, "decision_cruxes"), "Use this evidence to state what would change the answer."),
        *_scope_steps(scope_boundaries),
        _practical_step(skeleton),
    ]
    steps = [step for step in steps if step]
    section_titles = _section_titles(decision_question)
    steps = [_with_section_owner(step, section_titles=section_titles) for step in steps]
    section_plan = _section_plan(steps, mandatory_retention_checklist or [], section_titles=section_titles)
    report = build_argument_spine_quality_report(steps, source_weight_judgments)
    return {
        "schema_id": "evidence_weighted_argument_spine_v1",
        "writing_policy": [
            "Write the memo from this ordered spine rather than restating every packet field.",
            "Each step has a primary_section; use that section as the evidence owner's home in the memo.",
            "When another section needs the same evidence, refer to the prior role briefly and add a new decision function instead of repeating the same sentence.",
            "Use source_weight_judgments to explain why a source drives, calibrates, bounds, or contextualizes the answer.",
        ],
        "section_plan": section_plan,
        "steps": steps,
        "quality_report": report,
    }


def build_argument_spine_quality_report(steps: list[dict[str, Any]], source_weight_judgments: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_roles = Counter(
        (str(step.get("memo_job") or ""), evidence_id)
        for step in steps
        for evidence_id in _string_list(step.get("evidence_item_ids"))
    )
    repeated = [
        {"memo_job": memo_job, "evidence_item_id": evidence_id, "count": count}
        for (memo_job, evidence_id), count in evidence_roles.items()
        if memo_job and evidence_id and count > 1
    ]
    jobs = {str(step.get("memo_job") or "") for step in steps}
    warnings = []
    for required in ("answer", "primary_driver", "counterweight_or_boundary", "practical_implication"):
        if required not in jobs:
            warnings.append(f"missing_{required}_step")
    if repeated:
        warnings.append("repeated_same_role_evidence")
    if not source_weight_judgments:
        warnings.append("missing_source_weight_judgments")
    return {
        "schema_id": "argument_spine_quality_report_v1",
        "status": "ready" if not warnings else "warning",
        "step_count": len(steps),
        "memo_jobs": sorted(jobs),
        "repeated_same_role_evidence": repeated[:30],
        "source_weight_judgment_count": len(source_weight_judgments),
        "warnings": warnings,
    }


def _answer_step(skeleton: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "step_id": "answer",
            "memo_job": "answer",
            "point": _short_text(skeleton.get("direct_answer"), 620),
            "confidence": skeleton.get("confidence"),
            "scope": _short_text(skeleton.get("scope"), 420),
        }
    )


def _with_section_owner(step: dict[str, Any], *, section_titles: dict[str, str]) -> dict[str, Any]:
    job = str(step.get("memo_job") or "").strip()
    owner = {
        "answer": section_titles["bottom_line"],
        "primary_driver": section_titles["answer_evidence"],
        "calibrator": section_titles["answer_evidence"],
        "counterweight_or_boundary": section_titles["counterweights"],
        "crux": section_titles["counterweights"],
        "scope_boundary": section_titles["counterweights"],
        "practical_implication": section_titles["practical_implication"],
    }.get(job, "")
    if not owner:
        return step
    owned = dict(step)
    owned["primary_section"] = owner
    return owned


def _section_plan(
    steps: list[dict[str, Any]],
    mandatory_retention_checklist: list[dict[str, Any]],
    *,
    section_titles: dict[str, str],
) -> list[dict[str, Any]]:
    sections = [
        (section_titles["bottom_line"], "State the answer, scope, and confidence without previewing every evidence detail."),
        (section_titles["answer_evidence"], "Weigh the main answer drivers and calibrators into the affirmative case for the answer."),
        (section_titles["counterweights"], "Handle counterweights, cruxes, and scope boundaries as limits on the answer."),
        (section_titles["practical_implication"], _practical_section_job(section_titles["practical_implication"])),
    ]
    rows = []
    for section, writing_job in sections:
        owned_steps = [step for step in steps if step.get("primary_section") == section]
        obligations = [row for row in mandatory_retention_checklist if _obligation_section(row, section_titles=section_titles) == section]
        rows.append(
            _drop_empty(
                {
                    "section": section,
                    "writing_job": writing_job,
                    "owned_step_ids": [str(step.get("step_id") or "") for step in owned_steps if step.get("step_id")],
                    "owned_evidence_item_ids": _dedupe(
                        evidence_id
                        for step in owned_steps
                        for evidence_id in _string_list(step.get("evidence_item_ids"))
                    ),
                    "owned_mandatory_obligation_ids": [
                        str(row.get("obligation_id") or row.get("item_id") or "")
                        for row in obligations
                        if row.get("obligation_id") or row.get("item_id")
                    ],
                    "must_include_points": [
                        _short_text(row.get("statement") or row.get("claim") or row.get("prose_instruction"), 360)
                        for row in obligations[:8]
                        if row.get("statement") or row.get("claim") or row.get("prose_instruction")
                    ],
                }
            )
        )
    return rows


def _obligation_section(row: dict[str, Any], *, section_titles: dict[str, str]) -> str:
    role = str(row.get("role") or row.get("obligation_type") or "").lower()
    text = str(row.get("statement") or row.get("claim") or row.get("prose_instruction") or "").lower()
    if any(token in role for token in ("counter", "boundary", "scope", "crux", "limit", "risk")):
        return section_titles["counterweights"]
    if any(token in text for token in ("subgroup", "scope", "bound", "risk factor", "exception", "threshold", "high-risk")):
        return section_titles["counterweights"]
    if any(token in role for token in ("practical", "application", "implementation")):
        return section_titles["practical_implication"]
    if any(token in text for token in ("practical", "application", "implementation", "advice", "recommend", "replacement", "action", "translate")):
        return section_titles["practical_implication"]
    if "bottom" in role or "answer" in role:
        return section_titles["bottom_line"]
    return section_titles["answer_evidence"]


def _section_titles(question: Any) -> dict[str, str]:
    text = str(question or "").lower()
    belief_question = any(term in text for term in ("what should", "believe", "current read", "interpret", "assess", "conclude"))
    if belief_question:
        return {
            "bottom_line": "Current Read",
            "answer_evidence": "Why This Is the Best Current Read",
            "counterweights": "What Could Change or Bound the Read",
            "practical_implication": "How to Use This Read",
        }
    return {
        "bottom_line": "Bottom Line",
        "answer_evidence": "Why This Is the Best Current Read",
        "counterweights": "What Could Change or Bound the Answer",
        "practical_implication": "Practical Implication",
    }


def _practical_section_job(title: str) -> str:
    if "use this read" in str(title or "").lower():
        return "Explain how to apply the read, what scope limits matter, and what would justify updating it."
    return "Translate the answer into action guidance without reopening the whole evidence argument."


def _lane_steps(memo_job: str, rows: list[dict[str, Any]], instruction: str) -> list[dict[str, Any]]:
    steps = []
    for index, row in enumerate(rows[:6], start=1):
        steps.append(
            _drop_empty(
                {
                    "step_id": f"{memo_job}_{index:02d}",
                    "memo_job": memo_job,
                    "point": _short_text(row.get("claim"), 620),
                    "source_ids": _string_list(row.get("source_ids")),
                    "evidence_item_ids": _string_list(row.get("item_id")),
                    "quantities": _list(row.get("quantities"))[:6],
                    "source_weight_role": row.get("source_weight_role"),
                    "reader_evidence_role": row.get("reader_evidence_role"),
                    "why_this_step_matters": _short_text(row.get("why_this_weight") or row.get("decision_relevance") or instruction, 520),
                }
            )
        )
    return steps


def _counterweight_steps(counterweights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = []
    for index, row in enumerate(counterweights[:6], start=1):
        steps.append(
            _drop_empty(
                {
                    "step_id": f"counterweight_{index:02d}",
                    "memo_job": "counterweight_or_boundary",
                    "point": _short_text(row.get("claim"), 620),
                    "disposition": row.get("disposition"),
                    "disposition_rationale": _short_text(row.get("disposition_rationale"), 420),
                    "source_ids": _string_list(row.get("source_ids")),
                    "evidence_item_ids": _string_list(row.get("item_id")),
                    "quantities": _list(row.get("quantities"))[:6],
                }
            )
        )
    return steps


def _scope_steps(scope_boundaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = []
    for index, row in enumerate(scope_boundaries[:6], start=1):
        steps.append(
            _drop_empty(
                {
                    "step_id": f"scope_{index:02d}",
                    "memo_job": "scope_boundary",
                    "point": _short_text(row.get("statement") or row.get("claim"), 520),
                    "source_ids": _string_list(row.get("source_ids")),
                    "evidence_item_ids": _string_list(row.get("evidence_item_ids") or row.get("item_id")),
                    "quantities": _list(row.get("quantities"))[:6],
                }
            )
        )
    return steps


def _practical_step(skeleton: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "step_id": "practical_implication",
            "memo_job": "practical_implication",
            "point": _short_text(skeleton.get("practical_implication"), 620),
        }
    )


def _lane(source_weighted_frame: dict[str, Any], lane: str) -> list[dict[str, Any]]:
    return [row for row in _list(_dict(source_weighted_frame.get("lanes")).get(lane)) if isinstance(row, dict)]


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}
