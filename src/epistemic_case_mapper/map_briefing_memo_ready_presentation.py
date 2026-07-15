from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet
from epistemic_case_mapper.map_briefing_lightweight_guidance import evidence_quality_caveat_text
from epistemic_case_mapper.map_briefing_memo_obligations import all_memo_obligations
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_source_identity import (
    compact_source_display,
    common_source_prefix,
    preferred_source_display,
    source_label_variants,
)

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
    next_memo = _ensure_source_weighting_section(normalized, packet)
    if next_memo != normalized:
        changes.append("inserted_source_weighting")
        normalized = next_memo
    next_memo = _replace_source_aliases(normalized, source_aliases)
    if next_memo != normalized:
        changes.append("normalized_source_labels")
        normalized = next_memo
    next_memo = _link_inline_citations(normalized, packet, citation_trace_href=citation_trace_href)
    if next_memo != normalized:
        changes.append("linked_inline_citations_to_trace")
        normalized = next_memo
    next_memo = _dedupe_linked_citation_clusters(normalized)
    if next_memo != normalized:
        changes.append("deduplicated_inline_citations")
        normalized = next_memo
    next_memo = _strip_inline_citation_trace_links(normalized)
    if next_memo != normalized:
        changes.append("converted_inline_citations_to_reference_style")
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


def build_citation_trace_markdown(memo: str, packet: dict[str, Any]) -> str:
    """Render the local citation trace target used by inline memo citations."""
    entries = _canonical_source_entries(packet)
    if not entries:
        return "# Citation Trace\n\nNo source trail was available for this memo.\n"
    cited = _cited_entry_norms(memo, entries)
    judgments_by_source = _source_weight_judgments_by_source(packet)
    lines = [
        "# Citation Trace",
        "",
        "Inline memo citations link here for packet-level traceability. External URLs are kept in the memo source list.",
        "",
    ]
    for entry in entries:
        display = entry.get("citation_display") or entry.get("inline_display") or entry.get("source_display") or "Source"
        source_id = entry.get("source_id", "")
        source_display = entry.get("source_display", "")
        source_label = entry.get("source_label", "")
        inline_display = entry.get("inline_display", "")
        url = entry.get("url", "")
        contexts = _trace_memo_contexts(memo, entry)
        items = _trace_evidence_items(packet, entry)
        lines.extend(
            [
                f"## {display}",
                "",
                f"- Cited in memo: {'yes' if _norm(display) in cited or _norm(source_display) in cited else 'not detected'}",
                f"- Short label: {inline_display or source_display or source_label or display}",
                f"- Source title: {source_display or source_label or display}",
            ]
        )
        if source_id:
            lines.append(f"- Source ID: `{source_id}`")
        if url:
            lines.append(f"- External URL: {url}")
        judgment = judgments_by_source.get(str(source_id or ""))
        if judgment:
            lines.append(f"- Source weight: {_readable_main_use(judgment.get('main_use'))}")
            summary = str(judgment.get("why_weight_this_way") or "").strip()
            if summary:
                lines.append(f"- Weight rationale: {summary}")
            limits = _string_list(judgment.get("what_not_to_use_it_for"))
            if limits:
                lines.append(f"- Use limits: {', '.join(_readable_warning(item) for item in limits[:4])}")
        if contexts:
            lines.append("- Memo citation contexts:")
            for context in contexts:
                lines.append(f"  - {context}")
        else:
            lines.append("- Memo citation contexts: no direct memo citation context detected")
        if items:
            lines.append("- Packet evidence:")
            for item in items:
                lines.extend(_trace_evidence_lines(item))
        else:
            lines.append("- Packet evidence: no directly matched evidence item")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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


def _readable_main_use(value: Any) -> str:
    return str(value or "unspecified").replace("_", " ")


def _replace_sources_section(memo: str, packet: dict[str, Any]) -> str:
    body = _strip_sources_section(memo).rstrip()
    sources = _cited_source_lines(body, packet)
    if not sources:
        return body + "\n"
    return "\n".join([body, "", "## Sources", "", *sources]).rstrip() + "\n"


def _ensure_source_weighting_section(memo: str, packet: dict[str, Any]) -> str:
    if _has_heading(memo, "how to weight the evidence"):
        return memo
    section = _source_weighting_section(packet)
    if not section:
        return memo
    return _insert_after_bottom_line(memo, section)


def _source_weighting_section(packet: dict[str, Any]) -> str:
    canonical = _dict(packet.get("canonical_decision_writer_packet")) or build_canonical_decision_writer_packet(packet)
    guidance = _dict(packet.get("lightweight_writer_guidance")) or _dict(canonical.get("lightweight_writer_guidance"))
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
    paragraphs = _dedupe(
        [
            _weighting_thesis(primary, calibrators, counterweights, scope, context),
            _lane_weighting_sentence(
                primary,
                "Start with {sources}; those are the closest sources to the bottom-line answer.",
            ),
            _lane_weighting_sentence(
                calibrators,
                "Use {sources} to size the effect, mechanism, or plausibility rather than to replace direct answer evidence.",
            ),
            _lane_weighting_sentence(
                counterweights,
                "Let {sources} narrow confidence or scope where they point against the main read.",
            ),
            _lane_weighting_sentence(
                scope,
                "Use {sources} to mark where the answer applies and where it should stop.",
            ),
            _lane_weighting_sentence(
                context,
                "Use {sources} for translation and background, not as independent causal evidence.",
            ),
        ]
    )
    if paragraphs:
        lines.append("\n\n".join(paragraphs))
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
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get("main_use") or "contextualizes"), []).append(row)
    lines = [
        "## How to Weight the Evidence",
        "",
        _source_weighting_summary(groups),
    ]
    paragraphs = []
    caveat_rows: list[dict[str, Any]] = []
    for use, template in [
        ("drives_answer", "Start with {sources}; these are the closest sources to the bottom-line answer."),
        ("calibrates_magnitude", "Use {sources} to calibrate magnitude, mechanism, or plausibility rather than to replace direct answer evidence."),
        ("bounds_answer", "Let {sources} narrow the claim where they identify countervailing evidence or uncertainty."),
        ("defines_scope", "Use {sources} to mark where the answer applies and where it should stop."),
        ("identifies_crux", "Treat {sources} as crux evidence because they identify what could change the answer."),
        ("contextualizes", "Use {sources} for translation and background rather than as independent proof."),
    ]:
        sentence, caveat_row = _judgment_group_sentence(template, groups.get(use, [])[:4], guidance=guidance)
        if sentence:
            paragraphs.append(sentence)
        if caveat_row:
            caveat_rows.append(caveat_row)
    if paragraphs:
        lines.extend(["", "\n\n".join(paragraphs)])
    caveat_note = _source_weighting_caveat_note(caveat_rows)
    if caveat_note:
        lines.extend(["", "Detailed source caveats are in [^source-weight-caveats].", "", caveat_note])
    return "\n".join(lines).strip()


def _source_weighting_summary(groups: dict[str, list[dict[str, Any]]]) -> str:
    if any(groups.values()):
        return (
            "Read the sources by what each can decide, not by source count: direct evidence carries the answer, "
            "while other sources size effects, expose limits, identify cruxes, or show where confidence should narrow."
        )
    return "Weigh the sources by what they can actually decide: some carry the answer, while others mainly size effects, expose counterweights, identify cruxes, or set boundaries."


def _judgment_group_sentence(template: str, rows: list[dict[str, Any]], *, guidance: dict[str, Any] | None = None) -> tuple[str, dict[str, Any] | None]:
    sources = _source_group_citations(rows)
    if not sources:
        return "", None
    source_ids = _dedupe(source_id for row in rows for source_id in _string_list(row.get("source_ids")))
    limits = _dedupe(limit for row in rows for limit in _string_list(row.get("what_not_to_use_it_for")))[:3]
    readable_limits = _readable_limits(limits, source_ids=source_ids, guidance=guidance)
    sentence = template.format(sources=sources)
    caveat_row = {"sources": sources, "limits": readable_limits} if readable_limits else None
    return sentence, caveat_row


def _source_group_citations(rows: list[dict[str, Any]]) -> str:
    return _cite_list(_dedupe(source_id for row in rows for source_id in _string_list(row.get("source_ids"))))


def _source_weighting_caveat_note(caveat_rows: list[dict[str, Any]]) -> str:
    parts = [
        f"{row['sources']}: {limits}"
        for row in caveat_rows
        if row.get("sources")
        if (limits := "; ".join(_dedupe(str(limit).strip() for limit in _list(row.get("limits")) if str(limit).strip())))
    ]
    if not parts:
        return ""
    return "[^source-weight-caveats]: Source-weighting caveats: " + "; ".join(parts) + "."


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


def _lane_weighting_sentence(sources: list[str], template: str) -> str:
    if not sources:
        return ""
    return template.format(sources=_cite_list(sources))


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
    return ". ".join(parts) + "." if parts else ""


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
        if line.strip().lower() == "## sources":
            return "\n".join(lines[:index]).rstrip()
    return str(memo or "").rstrip()


def _cited_source_lines(body: str, packet: dict[str, Any]) -> list[str]:
    entries = _canonical_source_entries(packet)
    cited = []
    lowered = body.lower()
    for entry in entries:
        displays = [entry["citation_display"], entry["inline_display"], entry["source_display"]]
        matches = [lowered.find(display.lower()) for display in displays if display and _contains_text(body, display)]
        if matches:
            cited.append((min(index for index in matches if index >= 0), _source_line_for_entry(entry)))
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


def _dedupe_linked_citation_clusters(memo: str) -> str:
    link_pattern = re.compile(r"\[[^\]\n]+\]\([^\)\n]+\)")

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        links = link_pattern.findall(content)
        if len(links) == 1 and content.strip() == links[0]:
            return links[0]
        if len(links) < 2:
            return match.group(0)
        deduped = _dedupe_by_norm(links)
        if len(deduped) == 1:
            return deduped[0]
        return "; ".join(deduped)

    return re.sub(r"\[((?:\[[^\]\n]+\]\([^\)\n]+\)(?:\s*(?:;|,)\s*)?)+)\]", replace, memo)


def _dedupe_by_norm(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped = []
    for value in values:
        marker = _norm(value)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(value)
    return deduped


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
                "url": urls.get(label, ""),
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


def _source_line_for_entry(entry: dict[str, str]) -> str:
    display = entry.get("inline_display", "") or entry.get("source_display", "")
    title = entry.get("source_display", "") or display
    url = entry.get("url", "")
    linked = f"[{display}]({url})" if display and url else display
    suffix = f" — {title}" if title and title != display else ""
    return f"* {linked}{suffix}"


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


def _trace_memo_contexts(memo: str, entry: dict[str, str]) -> list[str]:
    body = _strip_sources_section(memo)
    contexts = []
    tokens = _trace_entry_citation_tokens(entry)
    for segment in _memo_context_segments(body):
        if _segment_has_citation_reference(segment, tokens):
            contexts.append(_clean_trace_context(segment))
    return _dedupe(context for context in contexts if context)


def _trace_entry_citation_tokens(entry: dict[str, str]) -> list[str]:
    values = [
        entry.get("source_id", ""),
        entry.get("source_label", ""),
        entry.get("source_display", ""),
        entry.get("inline_display", ""),
        entry.get("citation_display", ""),
    ]
    return _dedupe(variant for value in values for variant in source_label_variants(value) if variant)


def _memo_context_segments(memo: str) -> list[str]:
    segments = []
    for line in str(memo or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("[^") or re.match(r"^\[[^\]]+\]:\s+", stripped):
            continue
        stripped = re.sub(r"^\s*[-*]\s+", "", stripped)
        segments.extend(_sentence_like_segments(stripped))
    return segments


def _sentence_like_segments(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9*])", text)
    return [part.strip() for part in parts if part.strip()]


def _segment_has_citation_reference(segment: str, tokens: list[str]) -> bool:
    linked_targets = {f"#{_source_anchor(token)})" for token in tokens if token}
    if any(target in segment for target in linked_targets):
        return True
    return any(_citation_container_mentions(segment, token) for token in tokens if token)


def _citation_container_mentions(segment: str, token: str) -> bool:
    token_pattern = re.escape(token)
    return bool(re.search(rf"[\[(][^\]\)\n]*\b{token_pattern}\b[^\]\)\n]*[\])]", segment, flags=re.IGNORECASE))


def _clean_trace_context(segment: str) -> str:
    return re.sub(r"\s+", " ", str(segment or "").strip())


def _trace_evidence_items(packet: dict[str, Any], entry: dict[str, str]) -> list[dict[str, Any]]:
    matched = []
    for item in _list(packet.get("evidence_items")):
        if isinstance(item, dict) and _trace_item_matches_entry(item, entry):
            matched.append(item)
    return matched


def _trace_item_matches_entry(item: dict[str, Any], entry: dict[str, str]) -> bool:
    candidate_labels = set()
    for value in [
        entry.get("source_id", ""),
        entry.get("source_label", ""),
        entry.get("source_display", ""),
        entry.get("inline_display", ""),
        entry.get("citation_display", ""),
    ]:
        candidate_labels.update(_norm(variant) for variant in source_label_variants(value) if variant)
    item_labels = _string_list(item.get("source_labels"))
    item_labels.append(str(item.get("source_label") or "").strip())
    item_norms = {_norm(variant) for label in item_labels for variant in source_label_variants(label) if variant}
    return bool(candidate_labels & item_norms)


def _trace_evidence_lines(item: dict[str, Any]) -> list[str]:
    item_id = str(item.get("item_id") or item.get("claim_id") or "evidence_item").strip()
    role = str(item.get("role") or "evidence").strip()
    claim = str(item.get("reader_claim") or item.get("claim") or item.get("summary") or "").strip()
    lines = [f"  - `{item_id}` ({role}): {claim}" if claim else f"  - `{item_id}` ({role})"]
    quantities = _trace_quantity_strings(item)
    if quantities:
        lines.append(f"    - Quantities: {'; '.join(quantities)}")
    return lines


def _trace_quantity_strings(item: dict[str, Any]) -> list[str]:
    values = []
    for quantity in _list(item.get("quantities")):
        if isinstance(quantity, dict):
            value = str(quantity.get("value") or quantity.get("text") or "").strip()
            interpretation = str(quantity.get("interpretation") or quantity.get("meaning") or "").strip()
            if value and interpretation:
                values.append(f"{value}: {interpretation}")
            elif value:
                values.append(value)
        else:
            text = str(quantity or "").strip()
            if text:
                values.append(text)
    return _dedupe(values)


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
            source_label,
            str(source.get("display_label") or "").strip(),
            str(source.get("citation_label") or "").strip(),
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
    labels = [
        str(source.get("source_label") or "").strip()
        for source in _list(packet.get("source_trail"))
        if isinstance(source, dict) and str(source.get("source_label") or "").strip()
    ]
    for item in _list(packet.get("evidence_items")):
        if not isinstance(item, dict):
            continue
        labels.extend(_string_list(item.get("source_labels")))
        labels.append(str(item.get("source_label") or "").strip())
    for obligation in all_memo_obligations(packet):
        labels.extend(_string_list(obligation.get("source_labels")))
        labels.append(str(obligation.get("source_label") or "").strip())
    return _dedupe(label for label in labels if label)


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    return not needle or needle.lower() in text.lower()
