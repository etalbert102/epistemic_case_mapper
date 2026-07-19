from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def build_section_reader_guidance_application(
    reader_packet: dict[str, Any],
    raw_section: dict[str, Any],
    *,
    section_id: str,
    source_ids: list[str],
) -> dict[str, Any]:
    guidance = _dict(reader_packet.get("lightweight_writer_guidance"))
    if not guidance:
        return {}
    matched_reader_guidance = _matching_guidance_rows(guidance.get("reader_guidance"), source_ids)
    matched_caveats = _matching_guidance_rows(guidance.get("evidence_quality_caveats"), source_ids)
    matched_quantity_risks = _matching_guidance_rows(guidance.get("quantity_wording_risks"), source_ids)
    return _drop_empty(
        {
            "schema_id": "section_reader_guidance_application_v1",
            "section_strategy": _guidance_section_strategy(section_id, guidance),
            "foreground": _guidance_foreground(section_id, guidance, raw_section),
            "caveat_handling": _guidance_caveat_handling(section_id, matched_caveats),
            "matched_reader_guidance": matched_reader_guidance[:3],
            "matched_quantity_wording_risks": matched_quantity_risks[:3],
            "repeat_control": _guidance_repeat_control(section_id),
            "source_ids_considered": source_ids,
        }
    )


def _matching_guidance_rows(value: Any, source_ids: list[str]) -> list[dict[str, Any]]:
    source_set = set(source_ids)
    rows = []
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        row_sources = set(_string_list(item.get("source_ids")))
        if source_set and row_sources and not source_set.intersection(row_sources):
            continue
        rows.append(_compact_guidance_row(item))
    return rows


def _compact_guidance_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "instruction": row.get("instruction") or row.get("caveat") or row.get("risk") or row.get("description"),
            "why_it_matters": row.get("why_it_matters") or row.get("applies_to"),
            "safe_wording": row.get("safe_wording"),
            "quantities": row.get("quantities"),
            "source_ids": row.get("source_ids"),
        }
    )


def _guidance_section_strategy(section_id: str, guidance: dict[str, Any]) -> str:
    flow = "; ".join(_string_list(guidance.get("suggested_reader_flow"))[:2])
    strategies = {
        "source_weighting": "Use the guidance to assign each source a job before the evidence argument starts.",
        "answer_evidence": "Use the guidance to make the affirmative case concrete, then keep caveats proportional.",
        "counterweights": "Use the guidance to isolate the boundary conditions and update triggers.",
        "practical_implication": "Use the guidance to convert evidence limits into action conditions.",
    }
    strategy = strategies.get(section_id, strategies["answer_evidence"])
    return f"{strategy} Suggested reader flow: {flow}" if flow else strategy


def _guidance_foreground(section_id: str, guidance: dict[str, Any], raw_section: dict[str, Any]) -> str:
    if section_id == "source_weighting":
        return "Separate sources that carry the answer from sources that calibrate dose, bound high consumption, or contextualize practical advice."
    if section_id == "counterweights":
        return "Foreground the boundary that prevents the answer from becoming an unrestricted health claim."
    if section_id == "practical_implication":
        return "Foreground what a decision-maker should do differently inside the supported scope."
    judgment = str(guidance.get("overall_judgment") or "").strip()
    return judgment or str(raw_section.get("writing_job") or "").strip()


def _guidance_caveat_handling(section_id: str, caveats: list[dict[str, Any]]) -> str:
    if not caveats:
        return ""
    caveat_text = "; ".join(str(row.get("instruction") or "") for row in caveats if row.get("instruction"))
    if section_id == "source_weighting":
        return f"Centralize this caveat here so later sections can refer to it lightly: {caveat_text}"
    if section_id == "answer_evidence":
        return f"Use this caveat once to calibrate confidence after the main evidence, not after every claim: {caveat_text}"
    if section_id == "counterweights":
        return f"Use this caveat to explain what narrows or could change the answer: {caveat_text}"
    return f"Translate this caveat into a practical condition instead of restating methodology: {caveat_text}"


def _guidance_repeat_control(section_id: str) -> str:
    controls = {
        "source_weighting": "This section may name recurring evidence-quality caveats; later sections should add new decision value instead of repeating the full caveat.",
        "answer_evidence": "After source weighting, avoid repeating source-quality caveats unless they change the affirmative inference.",
        "counterweights": "Avoid re-summarizing the support case; explain the boundary's decision consequence.",
        "practical_implication": "Avoid rearguing the evidence; turn the answer and limits into usable advice.",
    }
    return controls.get(section_id, controls["answer_evidence"])


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
