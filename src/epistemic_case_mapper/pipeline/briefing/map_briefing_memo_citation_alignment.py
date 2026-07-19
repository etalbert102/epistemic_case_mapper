from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_identity import source_label_variants
from epistemic_case_mapper.pipeline.briefing.map_briefing_citation_care import source_ids_supported_by_claim


def align_inline_citations(
    memo: str,
    packet: dict[str, Any],
    *,
    entries: list[dict[str, str]],
    display_lookup: dict[str, str],
    citation_parts: Any,
    source_evidence_by_source: dict[str, list[str]] | None = None,
) -> str:
    if not entries:
        return str(memo or "")
    source_by_display = _source_id_lookup_for_citations(entries)
    role_by_source = _presentation_source_roles(packet)
    if not display_lookup or not source_by_display:
        return str(memo or "")
    lines = str(memo or "").splitlines()
    aligned_lines = []
    current_heading = ""
    for line in lines:
        heading = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if heading:
            current_heading = _norm(heading.group(1))
            aligned_lines.append(line)
            continue
        stripped = line.strip()
        if (
            current_heading in {"sources", "how to weight the evidence"}
            or stripped.startswith("#")
            or re.match(r"^\[[^\]\n]+\]:\s+", stripped)
        ):
            aligned_lines.append(line)
            continue
        aligned_lines.append(
            _align_citation_line(
                line,
                display_lookup,
                source_by_display,
                role_by_source,
                citation_parts,
                source_evidence_by_source=source_evidence_by_source or {},
            )
        )
    return "\n".join(aligned_lines)


def _align_citation_line(
    line: str,
    display_lookup: dict[str, str],
    source_by_display: dict[str, str],
    role_by_source: dict[str, str],
    citation_parts: Any,
    *,
    source_evidence_by_source: dict[str, list[str]],
) -> str:
    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        if "](" in content:
            return match.group(0)
        parts = citation_parts(content)
        mapped: list[tuple[str, str]] = []
        for part in parts:
            display = display_lookup.get(_norm(part))
            source_id = source_by_display.get(_norm(display or part))
            if display and source_id:
                mapped.append((display, source_id))
        if not mapped:
            return match.group(0)
        clause = _presentation_citation_clause(line, match.start(), match.end())
        support_claim = _presentation_citation_sentence(line, match.start(), match.end())
        supported_source_ids = source_ids_supported_by_claim(
            support_claim,
            [source_id for _, source_id in mapped],
            source_evidence_by_source=source_evidence_by_source,
        )
        if supported_source_ids:
            selected = [row for row in mapped if row[1] in supported_source_ids]
            if [source_id for _, source_id in selected] == [source_id for _, source_id in mapped]:
                return match.group(0)
            return "[" + ", ".join(display for display, _ in selected) + "]"
        desired_roles = _presentation_clause_roles(clause)
        selected = _aligned_citation_sources(mapped, desired_roles, role_by_source)
        if not selected:
            return match.group(0)
        if [source_id for _, source_id in selected] == [source_id for _, source_id in mapped]:
            return match.group(0)
        return "[" + ", ".join(display for display, _ in selected) + "]"

    aligned = re.sub(r"\[([^\[\]\n]{1,260})\](?!\()", replace, line)
    leading = re.match(r"^\s*", aligned).group(0)
    body = aligned[len(leading) :]
    body = re.sub(r"\s+([.,;:])", r"\1", body)
    body = re.sub(r" {2,}", " ", body)
    return leading + body


def _source_id_lookup_for_citations(entries: list[dict[str, str]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for entry in entries:
        source_id = str(entry.get("source_id") or "").strip()
        if not source_id:
            continue
        for value in (
            entry.get("source_id", ""),
            entry.get("source_label", ""),
            entry.get("source_display", ""),
            entry.get("inline_display", ""),
            entry.get("citation_display", ""),
        ):
            for variant in source_label_variants(value):
                if variant:
                    lookup[_norm(variant)] = source_id
    return lookup


def _presentation_source_roles(packet: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    for row in _list(canonical.get("source_weight_judgments")):
        if not isinstance(row, dict):
            continue
        role = _presentation_source_role(row)
        if not role:
            continue
        for source_id in _string_list(row.get("source_ids")):
            roles[source_id] = role
    return roles


def _presentation_source_role(row: dict[str, Any]) -> str:
    main_use = _norm(str(row.get("main_use") or ""))
    text = _norm(
        " ".join(
            str(row.get(key) or "")
            for key in ("main_use", "memo_weight_sentence", "why_weight_this_way", "reader_facing_limit")
        )
    )
    if re.search(r"\b(calibrat\w*|magnitude|quant\w*|estimate\w*)\b", main_use):
        return "calibration"
    if re.search(r"\b(bounds?|boundary|scope|limit\w*)\b", main_use):
        return "boundary"
    if re.search(r"\b(counter\w*|tension|weaken)\b", main_use):
        return "counterweight"
    if re.search(r"\b(context\w*|guidance)\b", main_use):
        return "context"
    if re.search(r"\b(drives?|support|primary|answer)\b", main_use):
        return "direct_support"
    if re.search(r"\b(calibrat\w*|magnitude|dose|threshold|estimate|ratio)\b", text):
        return "calibration"
    if re.search(r"\b(bound|bounds|boundary|scope|limit|caveat|subgroup)\b", text):
        return "boundary"
    if re.search(r"\b(context\w*|guidance|practical|pattern|implementation)\b", text):
        return "context"
    if re.search(r"\b(drive|support|primary)\b", text):
        return "direct_support"
    return ""


def _presentation_citation_clause(line: str, start: int, end: int) -> str:
    text = str(line or "")
    left = max(_clause_boundary_indexes(text, 0, start), default=-1)
    right_candidates = _clause_boundary_indexes(text, end, len(text))
    right = min(right_candidates) if right_candidates else len(text)
    return " ".join(text[left + 1 : right].split())


def _presentation_citation_sentence(line: str, start: int, end: int) -> str:
    text = str(line or "")
    boundaries = [
        index
        for index, char in enumerate(text)
        if char == "." and not _is_decimal_period(text, index)
    ]
    left = max((index for index in boundaries if index < start), default=-1)
    right = min((index for index in boundaries if index >= end), default=len(text))
    return " ".join(text[left + 1 : right].split())


def _clause_boundary_indexes(text: str, start: int, end: int) -> list[int]:
    boundaries: list[int] = []
    depth = 0
    for index in range(max(start, 0), min(end, len(text))):
        char = text[index]
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            continue
        if depth:
            continue
        if char in ";:":
            boundaries.append(index)
        elif char == "." and not _is_decimal_period(text, index):
            boundaries.append(index)
    return boundaries


def _is_decimal_period(text: str, index: int) -> bool:
    return index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit()


def _presentation_clause_roles(text: str) -> set[str]:
    citationless = re.sub(r"\[[^\[\]\n]{1,260}\]", "", str(text or ""))
    normed = _norm(citationless)
    roles: set[str] = set()
    if _looks_like_quantitative_clause(citationless):
        roles.add("calibration")
    risk_counter = bool(re.search(r"\b(?:increased|higher)\s+risk\b", normed)) and not bool(
        re.search(r"\b(?:not associated with|no|does not|without)\s+(?:\w+\s+){0,4}(?:increased|higher)\s+risk\b", normed)
    )
    if re.search(r"\b(bound\w*|limit\w*|scope|caveat\w*|except\w*|subgroup|high risk|dose[- ]?response|mortality|qualif\w*)\b", normed) or risk_counter:
        roles.add("boundary")
    if re.search(r"\b(counter\w*|tension|however|although|whereas|but|conflict\w*|contradict\w*|harm|mortality)\b", normed) or risk_counter:
        roles.add("counterweight")
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|per day|hr|rr|or|md|ci|ratio)\b", normed):
        roles.add("calibration")
    if re.search(r"\b(ratio|estimate|threshold|signal|magnitude|mean difference|hazard ratio|relative risk)\b", normed) and re.search(r"\d", normed):
        roles.add("calibration")
    if re.search(r"\b(context\w*|explain\w*|guidance|recommend\w*|practical|pattern\w*|dietary pattern|framework)\b", normed):
        roles.add("context")
    if re.search(r"\b(neutral|not associated|safe|supports?|driven by|primary conclusion|best current read|does not increase|no increased|without specific concern)\b", normed):
        roles.add("direct_support")
    return roles or {"direct_support"}


def _looks_like_quantitative_clause(text: str) -> bool:
    raw = str(text or "")
    if re.search(r"\b(?:MD|HR|RR|OR|CI|I2|I²)\s*[=:]?\s*\d", raw, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(?:hazard ratio|relative risk|mean difference|confidence interval)\b", raw, flags=re.IGNORECASE) and re.search(r"\d", raw):
        return True
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|percent|per day|[A-Za-z]+/day|ratio)\b", raw, flags=re.IGNORECASE))


def _aligned_citation_sources(
    mapped: list[tuple[str, str]],
    desired_roles: set[str],
    role_by_source: dict[str, str],
) -> list[tuple[str, str]]:
    if not role_by_source:
        return mapped
    compatible = [
        (display, source_id)
        for display, source_id in mapped
        if _citation_role_compatible(role_by_source.get(source_id, ""), desired_roles)
    ]
    if compatible:
        return compatible
    unknown_role = [(display, source_id) for display, source_id in mapped if not role_by_source.get(source_id)]
    if unknown_role:
        return unknown_role
    return []


def _citation_role_compatible(source_role: str, desired_roles: set[str]) -> bool:
    role = source_role or "direct_support"
    if role in desired_roles:
        return True
    if role == "direct_support" and desired_roles.intersection({"context", "direct_support"}):
        return True
    if role == "context" and desired_roles.intersection({"context", "direct_support"}):
        return True
    if role == "calibration" and desired_roles.intersection({"calibration", "boundary", "counterweight"}):
        return True
    if role in {"boundary", "counterweight"} and desired_roles.intersection({"boundary", "counterweight"}):
        return True
    return False
