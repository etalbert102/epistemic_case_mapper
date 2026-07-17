from __future__ import annotations

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
        "- Combine, reorder, and compress the notes naturally, but preserve every required claim, quantity, boundary, and citation.\n"
        "- Cite sources for their listed citation job: support sources for support claims, boundary sources for boundaries, counterweight sources for tensions, calibration sources for quantities, and context sources for context.\n"
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
        "### Section job",
        *_bullet_list(role.get("do")),
        *_section("### Reader guidance applied to this section", _reader_guidance_application_lines(guidance_application)),
        *_section("### Decision action contract", _decision_action_contract_lines(top.get("decision_action_contract"))),
        *_section("### Avoid", _bullet_list(role.get("avoid"))),
        *_section("### Calibration limits", _bullet_list(top.get("must_not_overstate"))),
        *_section("### Required evidence points", _source_bound_atom_lines(packet.get("source_bound_evidence_atoms"))),
        *_section("### Required obligations", _retention_requirement_lines(packet.get("section_retention_requirements"))),
        *_section("### Source role contract", _source_role_group_lines(packet.get("source_role_groups"))),
        *_section("### Source hierarchy lane notes", _lane_card_lines(packet.get("lane_cards"))),
        *_section("### Source weighting validation target", _source_weighting_validation_lines(packet.get("validation_contract"))),
        *_section("### Protected quantity sets", _protected_quantity_set_lines(packet.get("protected_quantity_sets"))),
        *_section("### Quantity collision warnings", _quantity_collision_lines(packet.get("quantity_collision_warnings"))),
        *_section("### Section argument steps", _argument_step_lines(packet.get("section_argument_steps"))),
        *_section("### Additional evidence context", _evidence_context_lines(packet.get("evidence_context"))),
        *_section("### Source weighting notes", _source_weighting_lines(packet.get("source_weighting"))),
        *_section("### Decision cruxes, thresholds, and update triggers", _decision_usefulness_lines(top.get("decision_usefulness"))),
        *_section(
            "### Writing guidance, caveats, and quantity risks",
            _lightweight_guidance_lines(top.get("lightweight_writer_guidance")) if not guidance_application else [],
        ),
        *_section("### Source language and use limits", _language_contract_lines(top.get("evidence_language_contracts"))),
        *_section("### Suggested paragraph flow", _numbered_list(focus.get("paragraph_shape"))),
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
