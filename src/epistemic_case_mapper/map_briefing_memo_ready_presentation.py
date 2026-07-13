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


def run_memo_ready_presentation_normalization(memo: str, packet: dict[str, Any]) -> dict[str, Any]:
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
    next_memo, compacted_citation_sources = _compact_crowded_citations(normalized, packet)
    if next_memo != normalized:
        changes.append("compacted_crowded_citations")
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
            "issues": [],
        },
    }


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


def _compact_crowded_citations(memo: str, packet: dict[str, Any]) -> tuple[str, list[str]]:
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
        return "[" + "; ".join([*kept, f"+{len(omitted)} sources"]) + f"][^{note_id}]"

    compacted = re.sub(r"\[([^\[\]\n]{1,260})\]", replace, memo)
    compacted = _insert_citation_notes(compacted, citation_notes)
    return compacted, _dedupe(additional_sources)


def _insert_citation_notes(memo: str, citation_notes: dict[tuple[str, ...], str]) -> str:
    if not citation_notes:
        return memo
    note_lines = [
        f"[^{note_id}]: Additional sources: {'; '.join(sources)}."
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
        entries.append({"source_display": source_display, "inline_display": inline_display, "url": urls.get(label, "")})
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
    display = entry.get("source_display", "")
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
