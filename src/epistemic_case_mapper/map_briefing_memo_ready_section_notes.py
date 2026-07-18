from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


def build_memo_ready_section_markdown_prompt(section_packet: dict[str, Any], *, known_source_ids: list[str]) -> str:
    heading = str(section_packet.get("heading") or "").strip()
    return (
        "You are writing one section of a source-grounded decision memo from markdown analyst notes.\n"
        "Use these notes as the sole semantic handoff for this section. Write polished decision-ready prose, not a checklist.\n\n"
        "Output rules:\n"
        f"- Output must start exactly with: ## {heading}\n"
        "- Use bracketed citations only for source IDs listed in Known source IDs.\n"
        "- Use parentheses, not square brackets, for confidence intervals, uncertainty ranges, and numeric ranges.\n"
        "- Every bracketed citation must contain one or more known source IDs separated by comma-space.\n"
        "- When one paragraph uses the same source cluster throughout, cite the cluster once at the end of the paragraph.\n"
        "- When sources support different jobs in the same paragraph, cite each source beside the clause it supports.\n"
        "- Keep packet IDs, schema terms, validation machinery, and audit language out of the prose.\n"
        "- Use the Expert judgment brief as the first-order analytical framing when present.\n"
        "- Use the Decision argument for this section as the governing structure; use evidence notes to support those argument moves.\n"
        "- Combine, reorder, and compress the notes naturally, but preserve every required claim, quantity, boundary, and citation.\n"
        "- Use Priority quantity contracts to keep decision-relevant quantities with the claim, endpoint, subgroup, and comparator they belong to.\n"
        "- Cite sources for their listed citation job: support sources for support claims, boundary sources for boundaries, counterweight sources for tensions, calibration sources for quantities, and context sources for context.\n"
        "- For reader-facing judgments, follow the allowed-use and not-enough-for limits when deciding what the judgment can support.\n"
        "- Let each evidence role determine the sentence job: driver evidence carries the answer; boundary evidence narrows scope or dose; calibrator evidence adjusts confidence or magnitude; context evidence explains interpretation.\n"
        "- Split evidence with different citation jobs into separate clauses or sentences so each citation supports the exact claim beside it.\n"
        "- Make each paragraph do a distinct reasoning job with fresh sentence-level value.\n\n"
        f"{render_memo_ready_section_markdown_notes(section_packet, known_source_ids=known_source_ids)}\n"
        "Now write the section as natural Markdown prose.\n"
    )


def render_memo_ready_section_markdown_notes(section_packet: dict[str, Any], *, known_source_ids: list[str]) -> str:
    packet = section_packet if isinstance(section_packet, dict) else {}
    top = _dict(packet.get("top_context"))
    focus = _dict(packet.get("section_focus"))
    role = _dict(packet.get("section_role_contract"))
    guidance_application = _dict(packet.get("reader_guidance_application"))
    expert_mode = bool(_dict(packet.get("expert_judgment_section")))
    lines = [
        f"Known source IDs: {', '.join(known_source_ids)}",
        "",
        f"## Section to Write: {_text(packet.get('heading'))}",
        f"Purpose: {_text(packet.get('section_job')) or _text(role.get('role'))}",
        f"Reader question: {_text(focus.get('reader_question'))}",
        f"Decision question: {_text(top.get('decision_question'))}",
        f"Current read: {_text(top.get('current_read_reference'))}",
        f"Confidence: {_text(top.get('confidence'))}",
        *_top_context_lines(top),
        "",
        *_section("### Expert judgment brief", _expert_judgment_section_lines(packet.get("expert_judgment_section"))),
        "### Section job",
        *_bullet_list(role.get("do")),
        *_section("### Analyst argument moves to resolve", _analyst_argument_move_lines(packet.get("analyst_argument_moves"))),
        *_section("### Decision-usefulness moves to surface", _decision_usefulness_move_lines(packet.get("decision_usefulness_moves"))),
        *_section("### Decision argument for this section", _decision_argument_section_lines(packet.get("decision_argument_section"))),
        *([] if expert_mode else _section("### Reader guidance applied to this section", _reader_guidance_application_lines(guidance_application))),
        *([] if expert_mode else _section("### Decision action contract", _decision_action_contract_lines(top.get("decision_action_contract")))),
        *_section("### Avoid", _bullet_list(role.get("avoid"))),
        *_section("### Calibration limits", _bullet_list(top.get("must_not_overstate"))),
        *_section("### Required evidence points", _source_bound_atom_lines(packet.get("source_bound_evidence_atoms"))),
        *_section("### Required obligations", _retention_requirement_lines(packet.get("section_retention_requirements"))),
        *_section("### Priority quantity contracts", _priority_quantity_contract_lines(packet.get("priority_quantity_contracts"))),
        *_section("### Source role contract", _source_role_group_lines(packet.get("source_role_groups"))),
        *([] if expert_mode else _section("### Source hierarchy lane notes", _lane_card_lines(packet.get("lane_cards")))),
        *([] if expert_mode else _section("### Source weighting validation target", _source_weighting_validation_lines(packet.get("validation_contract")))),
        *_section("### Protected quantity sets", _protected_quantity_set_lines(packet.get("protected_quantity_sets"))),
        *_section("### Quantity collision warnings", _quantity_collision_lines(packet.get("quantity_collision_warnings"))),
        *([] if expert_mode else _section("### Section argument steps", _argument_step_lines(packet.get("section_argument_steps")))),
        *([] if expert_mode else _section("### Additional evidence context", _evidence_context_lines(packet.get("evidence_context")))),
        *([] if expert_mode else _section("### Source weighting notes", _source_weighting_lines(packet.get("source_weighting")))),
        *([] if expert_mode else _section("### Reader-facing judgments to surface", _reader_judgment_lines(top.get("reader_judgments_to_surface")))),
        *([] if expert_mode else _section("### Decision cruxes, thresholds, and update triggers", _decision_usefulness_lines(top.get("decision_usefulness")))),
        *(
            []
            if expert_mode
            else _section(
                "### Writing guidance, caveats, and quantity risks",
                _lightweight_guidance_lines(top.get("lightweight_writer_guidance")) if not guidance_application else [],
            )
        ),
        *_section("### Source language and use limits", _language_contract_lines(top.get("evidence_language_contracts"))),
        *([] if expert_mode else _section("### Suggested paragraph flow", _numbered_list(focus.get("paragraph_shape")))),
    ]
    return "\n".join(line for line in lines if line is not None).strip()


def _top_context_lines(top: dict[str, Any]) -> list[str]:
    rows = []
    for key, label in (
        ("main_support", "Main support"),
        ("main_counterweight_reference", "Main counterweight reference"),
        ("main_counterweight", "Main counterweight"),
        ("scope", "Scope"),
        ("practical_read", "Practical read"),
        ("main_boundary", "Main boundary"),
        ("source_hierarchy_thesis", "Source hierarchy thesis"),
    ):
        if value := _text(top.get(key)):
            rows.append(f"{label}: {value}")
    return rows


def _source_bound_atom_lines(value: Any) -> list[str]:
    rows = []
    for atom in _dict_rows(value)[:16]:
        if claim := _text(atom.get("claim")):
            rows.append(_bullet(f"{claim} {_citations(atom)}".strip()))
        if citation_role := _text(atom.get("citation_role")):
            rows.append(f"  - Citation job: {citation_role.replace('_', ' ')}")
        if section_job := _text(atom.get("section_specific_job")):
            rows.append(f"  - Section-specific job: {section_job}")
        if use_for := _text(atom.get("use_for")):
            rows.append(f"  - Use for: {use_for}")
        if avoid := _string_list(atom.get("do_not_use_for")):
            rows.append(f"  - Use limit: {'; '.join(avoid[:3])}")
        if relevance := _text(atom.get("decision_relevance")):
            rows.append(f"  - Decision use: {relevance}")
        quantities = [_quantity_line(row) for row in _dict_rows(atom.get("quantity_tuples"))]
        if quantities:
            rows.append("  - Quantities to preserve: " + "; ".join(quantities))
        if scope := _text(atom.get("applicability_scope")):
            rows.append(f"  - Scope to keep attached: {scope}")
    return rows


def _decision_argument_section_lines(value: Any) -> list[str]:
    section = _dict(value)
    if not section:
        return []
    rows = []
    if reader_question := _text(section.get("reader_question")):
        rows.append(f"Reader question to answer: {reader_question}")
    if why := _text(section.get("why_this_section_matters")):
        rows.append(f"Why this section matters: {why}")
    if job := _text(section.get("section_job")):
        rows.append(f"Section decision job: {job}")
    for move in _dict_rows(section.get("owned_moves"))[:8]:
        point = _text(move.get("point"))
        if not point:
            continue
        parts = [
            _text(move.get("move_type")).replace("_", " "),
            point,
            f"Writing job: {_text(move.get('writing_job'))}" if _text(move.get("writing_job")) else "",
            _citations(move),
        ]
        rows.append(_bullet("; ".join(part for part in parts if part)))
        if evidence_ids := _string_list(move.get("evidence_item_ids")):
            rows.append(f"  - Evidence IDs for this move: {', '.join(evidence_ids[:12])}")
        if quantities := _string_list(move.get("quantities")):
            rows.append(f"  - Quantities for this move: {'; '.join(quantities[:8])}")
        if disposition := _text(move.get("disposition")):
            rows.append(f"  - Disposition: {disposition}")
        if would_change := _text(move.get("would_change_if")):
            rows.append(f"  - Would change if: {would_change}")
    return rows


def _expert_judgment_section_lines(value: Any) -> list[str]:
    section = _dict(value)
    if not section:
        return []
    rows = []
    if point := _text(section.get("governing_point")):
        rows.append(f"Governing point: {point}")
    if lead := _text(section.get("lead_with")):
        rows.append(f"Lead with: {lead}")
    rows.extend(f"Strategy: {item}" for item in _string_list(section.get("paragraph_strategy"))[:5])
    rows.extend(f"Emphasize: {item}" for item in _string_list(section.get("emphasize"))[:6])
    rows.extend(f"Subordinate: {item}" for item in _string_list(section.get("subordinate"))[:5])
    if source_ids := _string_list(section.get("source_ids")):
        rows.append(f"Sources to use: {', '.join(source_ids[:10])}")
    if quantities := _string_list(section.get("quantity_values")):
        rows.append(f"Quantities to preserve: {'; '.join(quantities[:10])}")
    return rows


def _retention_requirement_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:16]:
        parts = [_text(item.get("statement"))]
        quantities = [_quantity_line(row) for row in _dict_rows(item.get("quantities"))]
        if quantities:
            parts.append("Quantities: " + "; ".join(quantities))
        if sources := _citations(item):
            parts.append(f"Sources: {sources}")
        if instruction := _text(item.get("prose_instruction")):
            parts.append(f"Writing job: {instruction}")
        if line := " ".join(part for part in parts if part):
            rows.append(_bullet(line))
    return rows


def _priority_quantity_contract_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:10]:
        parts = [
            f"{_text(item.get('quantity'))} belongs with {_text(item.get('evidence_id'))}",
            f"Decision role: {_text(item.get('decision_role'))}" if _text(item.get("decision_role")) else "",
            f"Claim: {_text(item.get('claim'))}" if _text(item.get("claim")) else "",
            f"Sources: {_citations(item)}" if _citations(item) else "",
        ]
        line = " ".join(part for part in parts if part).strip()
        if line:
            rows.append(_bullet(line))
    return rows


def _protected_quantity_set_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:10]:
        parts = [_text(item.get("claim")) or _text(item.get("statement"))]
        quantities = [_quantity_line(row) for row in _dict_rows(item.get("source_bound_quantity_atoms"))]
        if quantities:
            parts.append("Keep together: " + "; ".join(quantities))
        if sources := _citations(item):
            parts.append(f"Sources: {sources}")
        if line := " ".join(part for part in parts if part):
            rows.append(_bullet(line))
    return rows


def _quantity_collision_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:8]:
        parts = [
            _text(item.get("instruction")),
            f"Surface: {_text(item.get('quantity_surface'))}" if _text(item.get("quantity_surface")) else "",
        ]
        entries = []
        for entry in _dict_rows(item.get("entries"))[:6]:
            entry_line = "; ".join(
                part
                for part in (
                    _quantity_line(entry),
                    f"scope: {_text(entry.get('applicability_scope'))}" if _text(entry.get("applicability_scope")) else "",
                    _citations(entry),
                )
                if part
            )
            if entry_line:
                entries.append(entry_line)
        if entries:
            parts.append("Entries: " + " | ".join(entries))
        if line := " ".join(part for part in parts if part):
            rows.append(_bullet(line))
    return rows


def _argument_step_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:10]:
        line = "; ".join(
            part
            for part in (
                _text(item.get("writing_goal") or item.get("step")),
                _text(item.get("transition_from_previous")),
                _citations(item),
            )
            if part
        )
        if line:
            rows.append(_bullet(line))
    return rows


def _analyst_argument_move_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:8]:
        parts = [
            _strip_raw_map_ids(_text(item.get("writing_goal"))),
            f"Transition: {_strip_raw_map_ids(_text(item.get('transition_from_previous')))}"
            if _text(item.get("transition_from_previous"))
            else "",
            _citations(item),
        ]
        if line := "; ".join(part for part in parts if part):
            rows.append(_bullet(line))
        if required := _string_list(item.get("required_points")):
            rows.append(f"  - Required reasoning points: {'; '.join(_strip_raw_map_ids(row) for row in required[:6])}")
    return rows


def _decision_usefulness_move_lines(value: Any) -> list[str]:
    useful = _dict(value)
    rows = []
    stance = _dict(useful.get("recommended_stance"))
    if stance_text := _text(stance.get("stance")):
        rows.append(_bullet(f"Recommended stance: {stance_text}"))
        if why := _text(stance.get("why_this_stance")):
            rows.append(f"  - Why: {why}")
        if scope := _text(stance.get("scope")):
            rows.append(f"  - Scope: {scope}")
    for key, label, fields in (
        ("decision_criteria", "Decision criterion", ("label", "why_it_matters")),
        ("diagnostic_evidence", "Diagnostic evidence", ("why_diagnostic", "distinguishes")),
        ("tradeoffs", "Tradeoff", ("tradeoff", "choose_a_if", "choose_b_if")),
        ("cruxes_and_thresholds", "Crux", ("crux", "current_read", "threshold", "would_change_if")),
        ("premortem", "Premortem", ("failure_mode", "why_plausible", "mitigation_or_monitoring")),
        ("monitoring_triggers", "Monitoring trigger", ("trigger", "would_update")),
    ):
        for item in _dict_rows(useful.get(key))[:6]:
            parts = [label]
            for field in fields:
                value_text = _text(item.get(field))
                if not value_text and field == "distinguishes":
                    value_text = "; ".join(_string_list(item.get(field))[:4])
                if value_text:
                    parts.append(f"{field.replace('_', ' ')}: {value_text}")
            if sources := _citations(item):
                parts.append(sources)
            if line := "; ".join(part for part in parts if part):
                rows.append(_bullet(line))
    return rows


def _evidence_context_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:16]:
        line = "; ".join(
            part
            for part in (
                _text(item.get("reader_claim") or item.get("claim") or item.get("statement")),
                f"Section job: {_text(item.get('section_specific_job'))}" if _text(item.get("section_specific_job")) else "",
                _text(item.get("decision_relevance")),
                _citations(item),
            )
            if part
        )
        if line:
            rows.append(_bullet(line))
    return rows


def _source_weighting_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:12]:
        line = "; ".join(
            part
            for part in (
                _citations(item),
                _text(item.get("main_use") or item.get("use") or item.get("reader_evidence_role")),
                _text(
                    item.get("memo_weight_sentence")
                    or item.get("why_weight_this_way")
                    or item.get("weight_summary")
                    or item.get("reader_facing_limit")
                ),
            )
            if part
        )
        if line:
            rows.append(_bullet(line))
    return rows


def _reader_judgment_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:8]:
        judgment = _text(item.get("judgment"))
        if not judgment:
            continue
        parts = [
            _text(item.get("judgment_type")).replace("_", " "),
            judgment,
            f"Why it matters: {_text(item.get('why_surface'))}" if _text(item.get("why_surface")) else "",
            _citations(item),
        ]
        rows.append(_bullet("; ".join(part for part in parts if part)))
        if allowed := _text(item.get("allowed_use")):
            rows.append(f"  - Allowed use: {allowed}")
        if limits := _string_list(item.get("not_enough_for")):
            rows.append(f"  - Not enough for: {'; '.join(limits[:3])}")
    return rows


def _source_role_group_lines(value: Any) -> list[str]:
    rows = []
    for group in _dict_rows(value)[:8]:
        role = _text(group.get("role"))
        if job := _text(group.get("writing_job")):
            rows.append(_bullet(f"{role}: {job}"))
        for source in _dict_rows(group.get("sources"))[:8]:
            parts = [
                _citations(source),
                _text(source.get("memo_weight_sentence") or source.get("role_rationale")),
            ]
            if caveats := _string_list(source.get("source_appraisal_caveats")):
                parts.append("Use limit: " + "; ".join(caveats[:2]))
            if cannot := _string_list(source.get("cannot_support")):
                parts.append("Cannot support: " + "; ".join(cannot[:2]))
            if line := "; ".join(part for part in parts if part):
                rows.append(_bullet(line))
    return rows


def _lane_card_lines(value: Any) -> list[str]:
    rows = []
    for card in _dict_rows(value)[:10]:
        line = "; ".join(
            part
            for part in (
                _text(card.get("role")),
                _text(card.get("role_description")),
                _text(card.get("rationale")),
                _citations(card),
            )
            if part
        )
        if line:
            rows.append(_bullet(line))
    return rows


def _source_weighting_validation_lines(value: Any) -> list[str]:
    target = _dict(value)
    rows = []
    if roles := _string_list(target.get("roles_to_cover")):
        rows.append(_bullet("Cover these source roles: " + ", ".join(roles)))
    if source_ids := _string_list(target.get("source_ids_to_account_for")):
        rows.append(_bullet("Account for these source IDs: " + ", ".join(f"[{source_id}]" for source_id in source_ids)))
    return rows


def _decision_usefulness_lines(value: Any) -> list[str]:
    useful = _dict(value)
    rows = []
    for key, label in (
        ("tradeoffs", "Tradeoff"),
        ("cruxes_and_thresholds", "Crux"),
        ("monitoring_triggers", "Monitoring trigger"),
    ):
        for item in _dict_rows(useful.get(key))[:8]:
            parts = [f"{label}: {_text(item.get('tradeoff') or item.get('crux') or item.get('trigger'))}"]
            for field in ("current_read", "threshold", "would_change_if", "would_update", "choose_a_if", "choose_b_if"):
                if value_text := _text(item.get(field)):
                    parts.append(f"{field.replace('_', ' ')}: {value_text}")
            if sources := _citations(item):
                parts.append(sources)
            if line := "; ".join(part for part in parts if part and not part.endswith(": ")):
                rows.append(_bullet(line))
    return rows


def _lightweight_guidance_lines(value: Any) -> list[str]:
    guidance = _dict(value)
    rows = []
    if overall := _text(guidance.get("overall_judgment")):
        rows.append(_bullet(f"Overall writing judgment: {overall}"))
    rows.extend(_guidance_rows(guidance.get("reader_guidance"), "Guidance"))
    rows.extend(_guidance_rows(guidance.get("evidence_quality_caveats"), "Caveat"))
    rows.extend(_quantity_risk_rows(guidance.get("quantity_wording_risks")))
    rows.extend(_bullet_list(guidance.get("do_not_overstate"), prefix="Do not overstate: "))
    return rows


def _reader_guidance_application_lines(value: Any) -> list[str]:
    application = _dict(value)
    rows = []
    if strategy := _text(application.get("section_strategy")):
        rows.append(_bullet(f"Strategy: {strategy}"))
    if foreground := _text(application.get("foreground")):
        rows.append(_bullet(f"Foreground: {foreground}"))
    if caveat := _text(application.get("caveat_handling")):
        rows.append(_bullet(f"Caveat handling: {caveat}"))
    if repeat := _text(application.get("repeat_control")):
        rows.append(_bullet(f"Repeat control: {repeat}"))
    rows.extend(_applied_guidance_rows(application.get("matched_reader_guidance"), "Use"))
    rows.extend(_applied_guidance_rows(application.get("matched_quantity_wording_risks"), "Quantity wording"))
    return rows


def _decision_action_contract_lines(value: Any) -> list[str]:
    contract = _dict(value)
    rows = []
    for key, label in (
        ("default_action", "Default action"),
        ("scope", "Scope"),
        ("exception_handling", "Exception handling"),
        ("confidence", "Confidence"),
        ("tradeoff", "Tradeoff"),
        ("update_trigger", "Update trigger"),
    ):
        if text := _text(contract.get(key)):
            rows.append(_bullet(f"{label}: {text}"))
    rows.extend(_bullet_list(contract.get("what_not_to_say"), prefix="Do not overstate: "))
    return rows


def _applied_guidance_rows(value: Any, label: str) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:4]:
        line = "; ".join(
            part
            for part in (
                f"{label}: {_text(item.get('instruction'))}",
                f"Why: {_text(item.get('why_it_matters'))}" if _text(item.get("why_it_matters")) else "",
                f"Safe wording: {_text(item.get('safe_wording'))}" if _text(item.get("safe_wording")) else "",
                _citations(item),
            )
            if part and not part.endswith(": ")
        )
        if line:
            rows.append(_bullet(line))
    return rows


def _guidance_rows(value: Any, label: str) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:8]:
        line = "; ".join(
            part
            for part in (
                f"{label}: {_text(item.get('instruction') or item.get('caveat') or item.get('description'))}",
                _text(item.get("why_it_matters") or item.get("applies_to")),
                _citations(item),
            )
            if part and not part.endswith(": ")
        )
        if line:
            rows.append(_bullet(line))
    return rows


def _quantity_risk_rows(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:8]:
        quantities = ", ".join(_string_list(item.get("quantities")))
        line = "; ".join(
            part
            for part in (
                f"Quantity wording risk: {_text(item.get('risk'))}",
                f"Quantities: {quantities}" if quantities else "",
                f"Safe wording: {_text(item.get('safe_wording'))}",
                _citations(item),
            )
            if part and not part.endswith(": ")
        )
        if line:
            rows.append(_bullet(line))
    return rows


def _language_contract_lines(value: Any) -> list[str]:
    rows = []
    for item in _dict_rows(value)[:12]:
        line = "; ".join(
            part
            for part in (
                _citations(item),
                f"design: {_text(item.get('evidence_design'))}" if _text(item.get("evidence_design")) else "",
                "allowed language: " + ", ".join(_string_list(item.get("allowed_language"))[:5]) if _string_list(item.get("allowed_language")) else "",
                "avoid: " + ", ".join(_string_list(item.get("avoid_language"))[:5]) if _string_list(item.get("avoid_language")) else "",
                f"rule: {_text(item.get('wording_rule'))}" if _text(item.get("wording_rule")) else "",
            )
            if part
        )
        if line:
            rows.append(_bullet(line))
    return rows


def _quantity_line(row: dict[str, Any]) -> str:
    value = _text(row.get("value"))
    interpretation = _text(row.get("interpretation"))
    core = f"{value}: {interpretation}" if value and interpretation else value or interpretation
    return " ".join(part for part in (core, _citations(row)) if part)


def _section(title: str, rows: list[str]) -> list[str]:
    return ["", title, *rows] if rows else []


def _bullet_list(value: Any, *, prefix: str = "") -> list[str]:
    return [_bullet(prefix + _text(item)) for item in _string_list(value) if _text(item)]


def _numbered_list(value: Any) -> list[str]:
    return [f"{index}. {_text(item)}" for index, item in enumerate(_string_list(value), start=1) if _text(item)]


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in _list(value) if isinstance(row, dict)]


def _citations(row: dict[str, Any]) -> str:
    ids = _string_list(row.get("allowed_citations")) or _string_list(row.get("source_ids"))
    return ", ".join(f"[{source_id}]" for source_id in ids if source_id)


def _bullet(value: str) -> str:
    return f"- {_short_text(value, 900)}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strip_raw_map_ids(text: Any) -> str:
    return re.sub(r"\b(?:claim|relation):[A-Za-z0-9_:-]+\b", "mapped evidence", str(text or ""))
