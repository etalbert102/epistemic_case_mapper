from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_obligations import all_memo_obligations
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
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
            changes.append("inserted_decision_question")
            normalized = next_memo
    next_memo = _remove_duplicate_decision_heading(normalized)
    if next_memo != normalized:
        changes.append("removed_duplicate_decision_heading")
        normalized = next_memo
    next_memo = _replace_source_aliases(normalized, source_aliases)
    if next_memo != normalized:
        changes.append("normalized_source_labels")
        normalized = next_memo
    next_memo, compacted_citation_sources = _compact_crowded_citations(
        normalized,
        packet,
        citation_trace_href=citation_trace_href,
    )
    if next_memo != normalized:
        changes.append("compacted_crowded_citations")
        normalized = next_memo
    next_memo = _link_inline_citations(normalized, packet, citation_trace_href=citation_trace_href)
    if next_memo != normalized:
        changes.append("linked_inline_citations_to_trace")
        normalized = next_memo
    next_memo = _replace_sources_section(normalized, packet, additional_cited_displays=compacted_citation_sources)
    if next_memo != normalized:
        changes.append("deterministic_sources")
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
    lines = [
        "# Citation Trace",
        "",
        "Inline memo citations link here for packet-level traceability. External URLs are kept in the memo source list.",
        "",
    ]
    for entry in entries:
        display = entry.get("inline_display") or entry.get("source_display") or "Source"
        source_id = entry.get("source_id", "")
        source_display = entry.get("source_display", "")
        source_label = entry.get("source_label", "")
        url = entry.get("url", "")
        contexts = _trace_memo_contexts(memo, entry)
        items = _trace_evidence_items(packet, entry)
        lines.extend(
            [
                f"## {display}",
                "",
                f"- Cited in memo: {'yes' if _norm(display) in cited or _norm(source_display) in cited else 'not detected'}",
                f"- Source title: {source_display or source_label or display}",
            ]
        )
        if source_id:
            lines.append(f"- Source ID: `{source_id}`")
        if url:
            lines.append(f"- External URL: {url}")
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


def _replace_sources_section(memo: str, packet: dict[str, Any], *, additional_cited_displays: list[str] | None = None) -> str:
    body = _strip_sources_section(memo).rstrip()
    sources = _cited_source_lines(body, packet, additional_cited_displays=additional_cited_displays or [])
    if not sources:
        return body + "\n"
    return "\n".join([body, "", "## Sources", "", *sources]).rstrip() + "\n"


def _strip_sources_section(memo: str) -> str:
    lines = str(memo or "").splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() == "## sources":
            return "\n".join(lines[:index]).rstrip()
    return str(memo or "").rstrip()


def _cited_source_lines(body: str, packet: dict[str, Any], *, additional_cited_displays: list[str] | None = None) -> list[str]:
    entries = _canonical_source_entries(packet)
    cited = []
    lowered = body.lower()
    additional = {_norm(display) for display in additional_cited_displays or [] if display}
    for entry in entries:
        displays = [entry["inline_display"], entry["source_display"]]
        matches = [lowered.find(display.lower()) for display in displays if display and _contains_text(body, display)]
        if _norm(entry["inline_display"]) in additional or _norm(entry["source_display"]) in additional:
            matches.append(len(body) + len(cited))
        if matches:
            cited.append((min(index for index in matches if index >= 0), _source_line_for_entry(entry)))
    return _dedupe(line for _, line in sorted(cited, key=lambda row: row[0]))


def _compact_crowded_citations(
    memo: str,
    packet: dict[str, Any],
    *,
    citation_trace_href: str,
) -> tuple[str, list[str]]:
    entries = _canonical_source_entries(packet)
    displays = _dedupe([entry["inline_display"] for entry in entries if entry.get("inline_display")])
    if not displays:
        return memo, []
    display_lookup = {_norm(display): display for display in displays}
    additional_sources: list[str] = []
    citation_notes: dict[tuple[str, ...], str] = {}

    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        parts = _citation_parts(content)
        cited = [display_lookup[_norm(part)] for part in parts if _norm(part) in display_lookup]
        if len(cited) < 4:
            return match.group(0)
        kept = cited[:2]
        omitted = cited[2:]
        additional_sources.extend(omitted)
        note_key = tuple(omitted)
        if note_key not in citation_notes:
            citation_notes[note_key] = f"sources-{len(citation_notes) + 1}"
        note_id = citation_notes[note_key]
        linked_kept = [_citation_trace_link(display, citation_trace_href) for display in kept]
        return "[" + "; ".join([*linked_kept, f"+{len(omitted)} sources"]) + f"][^{note_id}]"

    compacted = re.sub(r"\[([^\[\]\n]{1,260})\]", replace, memo)
    compacted = _insert_citation_notes(compacted, citation_notes, citation_trace_href=citation_trace_href)
    return compacted, _dedupe(additional_sources)


def _insert_citation_notes(
    memo: str,
    citation_notes: dict[tuple[str, ...], str],
    *,
    citation_trace_href: str,
) -> str:
    if not citation_notes:
        return memo
    note_lines = [
        f"[^{note_id}]: Additional sources: {'; '.join(_citation_trace_link(source, citation_trace_href) for source in sources)}."
        for sources, note_id in citation_notes.items()
    ]
    lines = str(memo or "").rstrip().splitlines()
    insert_at = len(lines)
    for index, line in enumerate(lines):
        if line.strip().lower() == "## sources":
            insert_at = index
            break
    before = lines[:insert_at]
    after = lines[insert_at:]
    while before and not before[-1].strip():
        before.pop()
    return "\n".join([*before, "", *note_lines, "", *after]).rstrip()


def _link_inline_citations(memo: str, packet: dict[str, Any], *, citation_trace_href: str) -> str:
    entries = _canonical_source_entries(packet)
    displays = _dedupe(
        display
        for entry in entries
        for display in [entry.get("inline_display", ""), entry.get("source_display", "")]
        if display
    )
    if not displays:
        return memo
    display_lookup = {_norm(display): display for display in displays}

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
        return f"[{linked}]"

    linked = re.sub(r"\(([^\(\)\n]{1,260})\)", replace_parenthetical, memo)
    return re.sub(r"\[([^\[\]\n]{1,260})\](?!\()", replace_bracketed, linked)


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
    changed = False
    for part in parts:
        display = display_lookup.get(_norm(part))
        if display:
            linked_parts.append(_citation_trace_link(display, citation_trace_href))
            changed = True
        else:
            linked_parts.append(part)
    if not changed:
        return content, False
    separator = "; " if ";" in content else ", "
    return separator.join(linked_parts), True


def _citation_trace_link(display: str, citation_trace_href: str) -> str:
    display = str(display or "").strip()
    if not display:
        return display
    if "](" in display:
        return display
    return f"[{display}]({citation_trace_href}#{_source_anchor(display)})"


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
    url = entry.get("url", "")
    return f"* [{display}]({url})" if display and url else f"* {display}"


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
        for display in [entry.get("inline_display", ""), entry.get("source_display", "")]:
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
    ]
    return _dedupe(variant for value in values for variant in source_label_variants(value) if variant)


def _memo_context_segments(memo: str) -> list[str]:
    segments = []
    for line in str(memo or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("[^"):
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
