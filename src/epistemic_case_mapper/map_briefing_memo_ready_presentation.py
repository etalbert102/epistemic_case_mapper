from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet
from epistemic_case_mapper.map_briefing_citation_dedupe import (
    compact_repeated_sentence_citations,
    dedupe_linked_citation_clusters,
    dedupe_reference_citation_runs,
)
from epistemic_case_mapper.map_briefing_lightweight_guidance import evidence_quality_caveat_text
from epistemic_case_mapper.map_briefing_model_source_weighting_presentation import render_model_source_weighting_section
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_style_smoothing import smooth_stock_memo_phrasing
from epistemic_case_mapper.map_briefing_memo_citation_alignment import align_inline_citations
from epistemic_case_mapper.map_briefing_source_identity import (
    compact_source_display,
    common_source_prefix,
    preferred_source_display,
    source_label_variants,
)
from epistemic_case_mapper.map_briefing_source_hierarchy import render_source_hierarchy_section
from epistemic_case_mapper.map_briefing_source_use_notes import source_use_note_for_entry
from epistemic_case_mapper.map_briefing_source_weighting_caveats import render_source_weighting_caveat_note

DEFAULT_CITATION_TRACE_HREF = "CITATION_TRACE.md"

def run_memo_ready_presentation_normalization(
    memo: str,
    packet: dict[str, Any],
    *,
    citation_trace_href: str = DEFAULT_CITATION_TRACE_HREF,
) -> dict[str, Any]:
    """Apply deterministic presentation-only fixes without changing analysis."""
    question = str(packet.get("decision_question") or "").strip()
    source_aliases = _source_alias_replacements(packet)
    normalized = str(memo or "").strip()
    changes: list[str] = []
    if question:
        next_memo = _ensure_decision_question(normalized, question)
        if next_memo != normalized:
            changes.append("normalized_decision_title" if normalized.splitlines()[:1] != next_memo.splitlines()[:1] else "inserted_decision_question")
            normalized = next_memo
    next_memo = _remove_duplicate_decision_heading(normalized)
    if next_memo != normalized:
        changes.append("removed_duplicate_decision_heading")
        normalized = next_memo
    next_memo = smooth_stock_memo_phrasing(normalized)
    if next_memo != normalized:
        changes.append("smoothed_stock_phrasing")
        normalized = next_memo
    next_memo = _ensure_source_weighting_section(normalized, packet)
    if next_memo != normalized:
        changes.append("inserted_source_weighting")
        normalized = next_memo
    next_memo = _normalize_parenthetical_source_id_citations(normalized, packet)
    if next_memo != normalized:
        changes.append("normalized_parenthetical_source_id_citations")
        normalized = next_memo
    next_memo = _strip_reader_internal_evidence_ids(normalized, packet)
    if next_memo != normalized:
        changes.append("removed_reader_internal_evidence_ids")
        normalized = next_memo
    next_memo = _replace_source_aliases(normalized, source_aliases)
    if next_memo != normalized:
        changes.append("normalized_source_labels")
        normalized = next_memo
    next_memo = align_inline_citations(
        normalized,
        packet,
        entries=_canonical_source_entries(packet),
        display_lookup=_citation_display_lookup(_canonical_source_entries(packet)),
        citation_parts=_citation_parts,
    )
    if next_memo != normalized:
        changes.append("aligned_inline_citations")
        normalized = next_memo
    next_memo = _link_inline_citations(normalized, packet, citation_trace_href=citation_trace_href)
    if next_memo != normalized:
        changes.append("linked_inline_citations_to_trace")
        normalized = next_memo
    next_memo = dedupe_linked_citation_clusters(normalized)
    if next_memo != normalized:
        changes.append("deduplicated_inline_citations")
        normalized = next_memo
    next_memo = _strip_inline_citation_trace_links(normalized)
    if next_memo != normalized:
        changes.append("converted_inline_citations_to_reference_style")
        normalized = next_memo
    citation_displays = [
        entry.get("citation_display") or entry.get("inline_display") or entry.get("source_display")
        for entry in _canonical_source_entries(packet)
    ]
    next_memo = dedupe_reference_citation_runs(normalized, citation_displays)
    if next_memo != normalized:
        changes.append("deduplicated_reference_citations")
        normalized = next_memo
    next_memo = compact_repeated_sentence_citations(normalized, citation_displays)
    if next_memo != normalized:
        changes.append("compacted_repeated_sentence_citations")
        normalized = next_memo
    next_memo = _repair_stitched_surface_punctuation(normalized)
    if next_memo != normalized:
        changes.append("repaired_stitched_surface_punctuation")
        normalized = next_memo
    next_memo = _replace_sources_section(normalized, packet)
    if next_memo != normalized:
        changes.append("deterministic_sources")
        normalized = next_memo
    next_memo = _append_citation_reference_definitions(normalized, packet, citation_trace_href=citation_trace_href)
    if next_memo != normalized:
        changes.append("added_citation_reference_definitions")
        normalized = next_memo
    normalized = normalized.rstrip() + "\n"
    return {
        "memo": normalized,
        "prompt": "",
        "raw": "",
        "report": {
            "schema_id": "memo_ready_presentation_normalization_report_v1",
            "status": "changed" if changes else "no_changes",
            "accepted": True,
            "changes": changes,
            "source_alias_count": len(source_aliases),
            "citation_trace_href": citation_trace_href,
            "citation_trace_source_count": len(_canonical_source_entries(packet)),
            "issues": [],
        },
    }

def _source_weight_judgments_by_source(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    judgments = _list(canonical.get("source_weight_judgments"))
    by_source: dict[str, dict[str, Any]] = {}
    for judgment in judgments:
        if not isinstance(judgment, dict):
            continue
        for source_id in _string_list(judgment.get("source_ids")):
            by_source[source_id] = judgment
    return by_source


def _strip_reader_internal_evidence_ids(memo: str, packet: dict[str, Any]) -> str:
    evidence_ids = _reader_internal_evidence_ids(packet)
    if not evidence_ids:
        return str(memo or "")
    id_pattern = "|".join(re.escape(evidence_id) for evidence_id in sorted(evidence_ids, key=len, reverse=True))
    text = str(memo or "")
    text = re.sub(rf"\s*\((?:{id_pattern})(?:\s*,\s*(?:{id_pattern}))*\)", "", text)
    text = re.sub(rf"\s*\b(?:{id_pattern})\b", "", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def _reader_internal_evidence_ids(packet: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for row in _list(packet.get("evidence_items")):
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "").strip()
        if _is_reader_internal_evidence_id(item_id):
            ids.add(item_id)
    canonical = _dict(packet.get("canonical_decision_writer_packet"))
    for key in (
        "mandatory_retention_checklist",
        "evidence_language_contracts",
        "source_weighted_answer_frame",
    ):
        _collect_internal_evidence_ids(canonical.get(key), ids)
    return ids


def _collect_internal_evidence_ids(value: Any, ids: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"item_id", "evidence_id"}:
                item_id = str(child or "").strip()
                if _is_reader_internal_evidence_id(item_id):
                    ids.add(item_id)
            elif key in {"item_ids", "evidence_ids", "evidence_item_ids"}:
                for item_id in _string_list(child):
                    if _is_reader_internal_evidence_id(item_id):
                        ids.add(item_id)
            else:
                _collect_internal_evidence_ids(child, ids)
        return
    if isinstance(value, list):
        for child in value:
            _collect_internal_evidence_ids(child, ids)


def _is_reader_internal_evidence_id(value: str) -> bool:
    return bool(re.fullmatch(r"(?:decision_writer_item|evidence_item|claim|bundle)_[A-Za-z0-9_-]+", str(value or "").strip()))


def _readable_main_use(value: Any) -> str:
    return str(value or "unspecified").replace("_", " ")


def _replace_sources_section(memo: str, packet: dict[str, Any]) -> str:
    body = _strip_sources_section(memo).rstrip()
    sources = _cited_source_lines(body, packet)
    if not sources:
        return body + "\n"
    return "\n".join([body, "", "## Sources", "", *sources]).rstrip() + "\n"


def _ensure_source_weighting_section(memo: str, packet: dict[str, Any]) -> str:
    if _has_heading(memo, "how to weight the evidence") or _has_embedded_source_weighting(memo):
        return memo
    section = _source_weighting_section(packet)
    if not section:
        return memo
    return _insert_after_bottom_line(memo, section)


def _has_embedded_source_weighting(memo: str) -> bool:
    body = re.split(r"(?m)^##\s+Sources\s*$", str(memo or ""), maxsplit=1)[0]
    if len(re.findall(r"\[[^\]\n]+\]", body)) < 3:
        return False
    normalized = re.sub(r"\s+", " ", body.lower())
    role_groups = [
        ("driven by", "anchored by", "primary", "foundational", "load-bearing", "main support"),
        ("bound", "bounded", "limit", "scope", "exclude", "does not extend"),
        ("calibrat", "size", "magnitude", "dose-response", "mean difference", "hazard ratio"),
        ("crux", "would change", "alter the decision", "counter", "tension"),
        ("context", "confound", "total diet", "interpret"),
    ]
    matched = sum(1 for group in role_groups if any(term in normalized for term in group))
    return matched >= 3


def _source_weighting_section(packet: dict[str, Any]) -> str:
    canonical = _dict(packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(packet)
    guidance = _dict(packet.get("lightweight_writer_guidance")) or _dict(canonical.get("lightweight_writer_guidance"))
    hierarchy_section = render_source_hierarchy_section(
        _dict(canonical.get("source_hierarchy"))
        or _dict(packet.get("analyst_source_hierarchy"))
    )
    if hierarchy_section:
        return hierarchy_section
    judgment_section = _source_weighting_from_judgments(_list(canonical.get("source_weight_judgments")), guidance=guidance)
    if judgment_section:
        return judgment_section
    frame = _dict(canonical.get("source_weighted_answer_frame"))
    lanes = _dict(frame.get("lanes"))
    notes = _list(canonical.get("source_weight_notes"))
    if not lanes and not notes:
        return ""
    primary = _lane_sources(lanes, "primary_answer_drivers", limit=3)
    calibrators = _lane_sources(lanes, "quantitative_or_interpretive_calibrators", limit=2)
    counterweights = _lane_sources(lanes, "counterweights_or_tensions", limit=2)
    scope = _lane_sources(lanes, "scope_limiters", limit=2)
    context = _lane_sources(lanes, "context_only", limit=2)
    lines = ["## How to Weight the Evidence", ""]
    role_paragraph = _lane_source_weighting_paragraph(primary, calibrators, counterweights, scope, context)
    if role_paragraph:
        lines.append(role_paragraph)
    credibility = _source_credibility_sentence(notes)
    if credibility:
        lines.extend(["", credibility])
    return "\n".join(lines).strip()


def _source_weighting_from_judgments(judgments: list[Any], *, guidance: dict[str, Any] | None = None) -> str:
    rows = [
        row
        for row in judgments
        if isinstance(row, dict)
        and _string_list(row.get("source_ids"))
        and (_string_list(row.get("evidence_item_ids")) or not row.get("omission_reason"))
    ]
    if not rows:
        return ""
    per_source_section = render_model_source_weighting_section(
        rows,
        summary=_source_weighting_summary({"model_adjudicated": rows}),
        guidance=guidance,
    )
    if per_source_section:
        return per_source_section
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get("main_use") or "contextualizes"), []).append(row)
    lines = ["## How to Weight the Evidence", "", _source_weighting_summary(groups)]
    role_sentences = []
    caveat_rows: list[dict[str, Any]] = []
    for use, template in [
        ("drives_answer", "put the most weight on {sources} for the core answer"),
        ("calibrates_magnitude", "use {sources} to size effects, mechanisms, or plausibility"),
        ("bounds_answer", "use {sources} as the main check on how far the answer travels"),
        ("defines_scope", "let {sources} define the population, setting, or decision scope"),
        ("identifies_crux", "treat {sources} as crux evidence for what could change the answer"),
        ("contextualizes", "use {sources} for translation or background rather than as independent proof"),
    ]:
        sentence, caveat_row = _judgment_group_sentence(template, groups.get(use, [])[:4], guidance=guidance)
        if sentence:
            role_sentences.append(sentence)
        if caveat_row:
            caveat_rows.append(caveat_row)
    if role_sentences:
        lines.extend(["", "In practical terms, " + _join_clauses(role_sentences) + "."])
    caveat_note = _source_weighting_caveat_note(caveat_rows)
    if caveat_note:
        lines.extend(["", caveat_note])
    return "\n".join(lines).strip()


def _source_weighting_summary(groups: dict[str, list[dict[str, Any]]]) -> str:
    if any(groups.values()):
        return (
            "Read source weight by what each source can decide: "
            "some sources carry the answer, while others mainly size effects, expose limits, identify cruxes, "
            "or show where confidence should narrow."
        )
    return "Weigh the sources by what they can actually decide: some carry the answer, while others mainly size effects, expose counterweights, identify cruxes, or set boundaries."


def _judgment_group_sentence(template: str, rows: list[dict[str, Any]], *, guidance: dict[str, Any] | None = None) -> tuple[str, dict[str, Any] | None]:
    sources = _source_group_citations(rows)
    if not sources:
        return "", None
    source_ids = _dedupe(source_id for row in rows for source_id in _string_list(row.get("source_ids")))
    limits = _dedupe(
        limit
        for row in rows
        for limit in (
            _string_list(row.get("reader_facing_limit"))
            or _string_list(row.get("what_not_to_use_it_for"))
        )
    )[:3]
    readable_limits = _readable_limits(limits, source_ids=source_ids, guidance=guidance)
    sentence = template.format(sources=sources)
    caveat_row = {"sources": sources, "limits": readable_limits} if readable_limits else None
    return sentence, caveat_row


def _source_group_citations(rows: list[dict[str, Any]]) -> str:
    return _cite_list(_dedupe(source_id for row in rows for source_id in _string_list(row.get("source_ids"))))


def _source_weighting_caveat_note(caveat_rows: list[dict[str, Any]]) -> str:
    return render_source_weighting_caveat_note(caveat_rows)


def _lane_source_weighting_paragraph(
    primary: list[str],
    calibrators: list[str],
    counterweights: list[str],
    scope: list[str],
    context: list[str],
) -> str:
    clauses = _dedupe(
        [
            _lane_weighting_clause(primary, "put the most weight on {sources} for the core answer"),
            _lane_weighting_clause(calibrators, "use {sources} to size the effect, mechanism, or plausibility"),
            _lane_weighting_clause(counterweights, "let {sources} narrow confidence or scope"),
            _lane_weighting_clause(scope, "use {sources} to mark where the answer applies and where it should stop"),
            _lane_weighting_clause(context, "use {sources} for translation and background"),
        ]
    )
    if clauses:
        return "Use the evidence in layers: " + _join_clauses(clauses) + "."
    return _weighting_thesis(primary, calibrators, counterweights, scope, context)


def _weighting_thesis(
    primary: list[str],
    calibrators: list[str],
    counterweights: list[str],
    scope: list[str],
    context: list[str],
) -> str:
    if not any([primary, calibrators, counterweights, scope, context]):
        return ""
    if primary:
        return (
            "Use the evidence in layers: start with the sources closest to the bottom-line answer, then bring in other sources "
            "to calibrate confidence, explain mechanisms, identify counterweights, or set scope boundaries."
        )
    return "No single source class carries the whole answer; weigh the evidence by decision role rather than by source count."


def _lane_weighting_clause(sources: list[str], template: str) -> str:
    if not sources:
        return ""
    return template.format(sources=_cite_list(sources))


def _join_clauses(clauses: list[str]) -> str:
    cleaned = [str(clause or "").strip().rstrip(".") for clause in clauses if str(clause or "").strip()]
    if len(cleaned) <= 1:
        return "".join(cleaned)
    if len(cleaned) == 2:
        return " and ".join(cleaned)
    return "; ".join(cleaned[:-1]) + "; and " + cleaned[-1]


def _join_readable_list(items: list[str]) -> str:
    cleaned = [str(item or "").strip().rstrip(".") for item in items if str(item or "").strip()]
    if len(cleaned) <= 1:
        return "".join(cleaned)
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + ", and " + cleaned[-1]


def _source_credibility_sentence(notes: list[Any]) -> str:
    rows = [row for row in notes if isinstance(row, dict)]
    warnings = _dedupe(warning for row in rows for warning in _string_list(row.get("not_enough_for")))
    directness = _dedupe(str(row.get("decision_directness") or "").strip() for row in rows if row.get("decision_directness"))
    parts = []
    if directness:
        parts.append(f"Keep decision directness in view ({', '.join(directness[:3])})")
    readable = [_readable_warning(warning) for warning in warnings[:4]]
    if readable:
        parts.append("the known limits are " + "; ".join(readable))
    sentence = ". ".join(parts)
    return sentence[:1].upper() + sentence[1:] + "." if sentence else ""


def _lane_sources(lanes: dict[str, Any], lane: str, *, limit: int) -> list[str]:
    return _dedupe(source for row in _list(lanes.get(lane)) if isinstance(row, dict) for source in _string_list(row.get("source_ids")))[:limit]


def _cite_list(source_ids: list[str]) -> str:
    return ", ".join(f"[{source_id}]" for source_id in source_ids if source_id)


def _readable_warning(warning: str) -> str:
    warning = str(warning or "").strip()
    if warning == "quality_limit":
        return "weak, indirect, or unknown evidence-quality status"
    return warning.replace("_", " ")


def _readable_limits(limits: list[str], *, source_ids: list[str], guidance: dict[str, Any] | None) -> list[str]:
    rows: list[str] = []
    caveats = evidence_quality_caveat_text(guidance, source_ids)
    for limit in limits:
        if limit == "quality_limit" and caveats:
            rows.extend(_clean_limit_phrase(caveat) for caveat in caveats)
        else:
            rows.append(_clean_limit_phrase(_readable_warning(limit)))
    return _dedupe(rows)[:3]


def _clean_limit_phrase(value: str) -> str:
    phrase = str(value or "").strip().rstrip(".;")
    if not phrase:
        return ""
    return phrase[:1].lower() + phrase[1:]


def _has_heading(memo: str, heading: str) -> bool:
    wanted = heading.strip().lower()
    return any(line.lstrip("# ").strip().lower() == wanted for line in str(memo or "").splitlines())


def _insert_after_bottom_line(memo: str, section: str) -> str:
    lines = str(memo or "").rstrip().splitlines()
    if not lines:
        return section + "\n"
    for index, line in enumerate(lines):
        if line.strip().startswith("## ") and "bottom" not in line.lower() and index > 0:
            return "\n".join([*lines[:index], "", section, "", *lines[index:]]).rstrip()
    return "\n".join([*lines, "", section]).rstrip()


def _strip_sources_section(memo: str) -> str:
    lines = str(memo or "").splitlines()
    for index, line in enumerate(lines):
        if _is_sources_heading(line):
            end = index
            while end > 0 and lines[end - 1].strip() in {"***", "---", "___"}:
                end -= 1
            return "\n".join(lines[:end]).rstrip()
    return str(memo or "").rstrip()


def _is_sources_heading(line: str) -> bool:
    normalized = re.sub(r"[*_`]+", "", str(line or "").strip()).strip().lower()
    normalized = normalized.lstrip("#").strip()
    return normalized in {"sources", "source list", "references"}


def _repair_stitched_surface_punctuation(memo: str) -> str:
    text = str(memo or "")
    text = re.sub(r"\.;\s*", ". ", text)
    text = re.sub(r"\s+;", ";", text)
    text = re.sub(r";\s+(In|This|The|A|An)\b", r". \1", text)
    return text


def _cited_source_lines(body: str, packet: dict[str, Any]) -> list[str]:
    entries = _canonical_source_entries(packet)
    cited = []
    lowered = body.lower()
    for entry in entries:
        displays = [entry["citation_display"], entry["inline_display"], entry["source_display"]]
        matches = [lowered.find(display.lower()) for display in displays if display and _contains_text(body, display)]
        if matches:
            cited.append((min(index for index in matches if index >= 0), _source_line_for_entry(entry, packet)))
    return _dedupe(line for _, line in sorted(cited, key=lambda row: row[0]))


def _append_citation_reference_definitions(memo: str, packet: dict[str, Any], *, citation_trace_href: str) -> str:
    entries = _canonical_source_entries(packet)
    cited = _cited_entry_norms(memo, entries)
    definitions = [
        f"[{entry['citation_display']}]: {citation_trace_href}#{_source_anchor(entry['citation_display'])}"
        for entry in entries
        if entry.get("citation_display") and _norm(entry["citation_display"]) in cited
    ]
    if not definitions:
        return memo
    return str(memo or "").rstrip() + "\n\n" + "\n".join(_dedupe(definitions)) + "\n"


def _link_inline_citations(memo: str, packet: dict[str, Any], *, citation_trace_href: str) -> str:
    entries = _canonical_source_entries(packet)
    display_lookup = _citation_display_lookup(entries)
    if not display_lookup:
        return memo

    def replace_parenthetical(match: re.Match[str]) -> str:
        content = match.group(1)
        if _skip_parenthetical_citation_link(content):
            return match.group(0)
        linked, changed = _linked_citation_content(content, display_lookup, citation_trace_href)
        if not changed:
            return match.group(0)
        return f"({linked})"

    def replace_bracketed(match: re.Match[str]) -> str:
        content = match.group(1)
        if "](" in content:
            return match.group(0)
        linked, changed = _linked_citation_content(content, display_lookup, citation_trace_href)
        if not changed:
            return match.group(0)
        return linked

    linked = re.sub(r"\(([^\(\)\n]{1,260})\)", replace_parenthetical, memo)
    return re.sub(r"\[([^\[\]\n]{1,260})\](?!\()", replace_bracketed, linked)


def _normalize_parenthetical_source_id_citations(memo: str, packet: dict[str, Any]) -> str:
    known_ids = {
        str(entry.get("source_id") or "").strip()
        for entry in _canonical_source_entries(packet)
        if str(entry.get("source_id") or "").strip()
    }
    if not known_ids:
        return memo

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        parts = _citation_parts(content)
        if parts and all(part in known_ids for part in parts):
            return f"[{', '.join(parts)}]"
        return match.group(0)

    return re.sub(r"\(([^\(\)\n]{1,260})\)", replace, str(memo or ""))



def _skip_parenthetical_citation_link(content: str) -> bool:
    content = str(content or "")
    return any(token in content for token in ["](", "://", "#", "/", "\n"])


def _linked_citation_content(
    content: str,
    display_lookup: dict[str, str],
    citation_trace_href: str,
) -> tuple[str, bool]:
    parts = _citation_parts(content)
    if not parts:
        return content, False
    linked_parts = []
    seen_parts: set[str] = set()
    changed = False
    for part in parts:
        display = display_lookup.get(_norm(part))
        marker = _norm(display or part)
        if marker and marker in seen_parts:
            changed = True
            continue
        if marker:
            seen_parts.add(marker)
        if display:
            linked_parts.append(_citation_trace_link(display, citation_trace_href))
            changed = True
        else:
            linked_parts.append(part)
    if not changed:
        return content, False
    separator = "; " if ";" in content else ", "
    return separator.join(linked_parts), True


def _citation_display_lookup(entries: list[dict[str, str]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for entry in entries:
        display = entry.get("citation_display") or entry.get("inline_display") or entry.get("source_display")
        for value in [
            entry.get("source_id", ""),
            entry.get("source_label", ""),
            entry.get("source_display", ""),
            entry.get("inline_display", ""),
            entry.get("citation_display", ""),
        ]:
            for variant in source_label_variants(value):
                if variant and display:
                    lookup[_norm(variant)] = display
    return lookup


def _citation_trace_link(display: str, citation_trace_href: str) -> str:
    display = str(display or "").strip()
    if not display:
        return display
    if "](" in display:
        return display
    return f"[{display}]"


def _strip_inline_citation_trace_links(memo: str) -> str:
    return re.sub(r"\[([^\]\n]+)\]\(CITATION_TRACE\.md#[^\)\n]+\)", r"[\1]", str(memo or ""))


def _source_anchor(display: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(display or "").lower()).strip("-")
    return slug or "source"


def _citation_parts(content: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"\s*(?:,|;)\s*", content)
        if part.strip()
    ]


def _canonical_source_entries(packet: dict[str, Any]) -> list[dict[str, str]]:
    urls = _source_url_lookup(packet)
    labels = _packet_source_labels(packet)
    common_prefix = common_source_prefix(labels)
    entries = []
    sources = _source_lookup(packet)
    for label in labels:
        source = sources.get(label, {"source_label": label})
        source_display = preferred_source_display(source, common_prefix=common_prefix)
        inline_display = compact_source_display(source, common_prefix=common_prefix)
        if not source_display:
            continue
        source_id = str(source.get("source_id") or "").strip()
        source_label = str(source.get("source_label") or label).strip()
        entries.append(
            {
                "source_display": source_display,
                "inline_display": inline_display,
                "citation_display": inline_display or source_display,
                "url": str(source.get("source_url") or "").strip() or urls.get(label, ""),
                "source_id": source_id,
                "source_label": source_label,
            }
        )
    return _dedupe_entries(entries)


def _source_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        for value in [str(source.get("source_id") or "").strip(), str(source.get("source_label") or "").strip()]:
            if value:
                lookup[value] = source
    return lookup


def _source_url_lookup(packet: dict[str, Any]) -> dict[str, str]:
    urls = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        label = str(source.get("source_label") or "").strip()
        url = str(source.get("source_url") or "").strip()
        if label and url:
            for variant in source_label_variants(label):
                urls[variant] = url
    return urls


def _source_line_for_entry(entry: dict[str, str], packet: dict[str, Any]) -> str:
    display = entry.get("inline_display", "") or entry.get("source_display", "")
    title = entry.get("source_display", "") or display
    url = entry.get("url", "")
    linked = f"[{display}]({url})" if display and url else display
    suffix = f" — {title}" if title and title != display else ""
    note = source_use_note_for_entry(entry, packet)
    note_suffix = f" — {note}" if note else ""
    return f"* {linked}{suffix}{note_suffix}"


def _dedupe_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    deduped = []
    for entry in entries:
        key = _norm(entry.get("source_display", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _cited_entry_norms(memo: str, entries: list[dict[str, str]]) -> set[str]:
    cited: set[str] = set()
    body = _strip_sources_section(memo)
    for entry in entries:
        for display in [entry.get("citation_display", ""), entry.get("inline_display", ""), entry.get("source_display", "")]:
            if display and _contains_text(body, display):
                cited.add(_norm(display))
    return cited


def _ensure_decision_question(memo: str, question: str) -> str:
    lines = memo.splitlines()
    if lines and lines[0].strip().lower().startswith("# decision memo"):
        title = question.strip().rstrip("?")
        repaired = f"# Decision Memo: {title}" if title else lines[0]
        if repaired != lines[0]:
            lines[0] = repaired
            memo = "\n".join(lines)
    if _contains_text(memo, question):
        return memo
    line = f"**Decision question:** {question}"
    lines = memo.splitlines()
    if not lines:
        return f"## Decision Brief\n\n{line}\n"
    for index, existing in enumerate(lines):
        if existing.strip().lower() == "## decision brief":
            insert_at = index + 1
            while insert_at < len(lines) and not lines[insert_at].strip():
                insert_at += 1
            return "\n".join([*lines[: index + 1], "", line, "", *lines[insert_at:]])
    return f"## Decision Brief\n\n{line}\n\n{memo.strip()}"


def _remove_duplicate_decision_heading(memo: str) -> str:
    lines = str(memo or "").splitlines()
    if not lines or lines[0].strip().lower() != "## decision brief":
        return str(memo or "")
    for index, line in enumerate(lines[1:8], start=1):
        if line.strip().lower() == "### decision brief":
            before = lines[:index]
            after = lines[index + 1 :]
            while after and not after[0].strip():
                after = after[1:]
            return "\n".join([*before, "", *after]).strip()
    return str(memo or "")


def _replace_source_aliases(memo: str, replacements: dict[str, str]) -> str:
    normalized = memo
    for source_label, display in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if source_label and display and source_label != display:
            normalized = normalized.replace(source_label, display)
    return normalized


def _source_alias_replacements(packet: dict[str, Any]) -> dict[str, str]:
    labels = _packet_source_labels(packet)
    common_prefix = common_source_prefix(labels)
    source_lookup = _source_lookup(packet)
    replacements: dict[str, str] = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        source_label = str(source.get("source_label") or "").strip()
        display = compact_source_display(source, common_prefix=common_prefix)
        if not display:
            continue
        aliases = [
            str(source.get("source_id") or "").strip(),
            str(source.get("source_slug") or "").strip(),
            str(source.get("original_source_id") or "").strip(),
            source_label,
            str(source.get("display_label") or "").strip(),
            str(source.get("citation_label") or "").strip(),
            *_string_list(source.get("source_aliases")),
        ]
        for alias in aliases:
            for variant in source_label_variants(alias):
                if variant and variant != display:
                    replacements[variant] = display
    for source_label in labels:
        if not source_label:
            continue
        source = source_lookup.get(source_label, {"source_label": source_label})
        display = compact_source_display(source, common_prefix=common_prefix)
        if display and display != source_label:
            for alias in source_label_variants(source_label):
                replacements[alias] = display
    replacements.update(_evidence_item_alias_replacements(packet, source_lookup, common_prefix=common_prefix))
    return replacements

def _evidence_item_alias_replacements(packet: dict[str, Any], source_lookup: dict[str, dict[str, Any]], *, common_prefix: list[str]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or item.get("claim_id") or "").strip()
        if not item_id:
            continue
        displays = []
        for source_id in _string_list(item.get("source_ids")):
            source = source_lookup.get(source_id)
            if isinstance(source, dict):
                display = compact_source_display(source, common_prefix=common_prefix)
                if display:
                    displays.append(display)
        if displays:
            replacements[item_id] = "; ".join(_dedupe(displays))
    return replacements

def _packet_source_labels(packet: dict[str, Any]) -> list[str]:
    labels = []
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        labels.extend(
            [
                str(source.get("source_id") or "").strip(),
                str(source.get("source_label") or "").strip(),
                str(source.get("display_label") or "").strip(),
                str(source.get("citation_label") or "").strip(),
            ]
        )
    return _dedupe(label for label in labels if label)

def _contains_text(text: str, needle: str) -> bool:
    return not str(needle).strip() or str(needle).strip().lower() in text.lower()
