from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_ready_presentation import (
    _canonical_source_entries,
    _contains_text,
    _readable_main_use,
    _readable_warning,
    _source_anchor,
    _source_weight_judgments_by_source,
    _strip_sources_section,
)
from epistemic_case_mapper.map_briefing_source_identity import source_label_variants


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
            limits = _string_list(judgment.get("reader_facing_limit")) or _string_list(judgment.get("what_not_to_use_it_for"))
            if limits:
                lines.append(f"- Use limits: {', '.join(_readable_warning(item) for item in limits[:4])}")
        if contexts:
            lines.append("- Memo citation contexts:")
            role_line = _trace_context_role_line(entry, judgment, items)
            for context in contexts:
                lines.append(f"  - {context}")
                if role_line:
                    lines.append(f"    - {role_line}")
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
    source_id = str(entry.get("source_id") or "").strip()
    if source_id and source_id in _string_list(item.get("source_ids")) + _string_list(item.get("source_id")):
        return True
    item_labels = _string_list(item.get("source_labels"))
    item_labels.append(str(item.get("source_label") or "").strip())
    item_norms = {_norm(variant) for label in item_labels for variant in source_label_variants(label) if variant}
    return bool(candidate_labels & item_norms)


def _trace_evidence_lines(item: dict[str, Any]) -> list[str]:
    item_id = str(item.get("item_id") or item.get("claim_id") or "evidence_item").strip()
    role = str(item.get("role") or "evidence").strip()
    claim = str(item.get("reader_claim") or item.get("claim") or item.get("summary") or "").strip()
    lines = [f"  - `{item_id}` ({role}): {claim}" if claim else f"  - `{item_id}` ({role})"]
    citation_role = str(item.get("citation_role") or item.get("reader_evidence_role") or item.get("main_use") or "").strip()
    if citation_role:
        lines.append(f"    - Citation job: {_readable_main_use(citation_role)}")
    use_for = str(item.get("use_for") or item.get("memo_weight_sentence") or item.get("why_weight_this_way") or "").strip()
    if use_for:
        lines.append(f"    - Use for: {use_for}")
    limits = _string_list(item.get("do_not_use_for")) or _string_list(item.get("cannot_support")) or _string_list(item.get("reader_facing_limit"))
    if limits:
        lines.append(f"    - Use limits: {', '.join(_readable_warning(item) for item in limits[:4])}")
    quantities = _trace_quantity_strings(item)
    if quantities:
        lines.append(f"    - Quantities: {'; '.join(quantities)}")
    bundles = _trace_assertion_bundle_lines(item)
    if bundles:
        lines.append("    - Source assertion bundles:")
        lines.extend(bundles)
    return lines


def _trace_context_role_line(
    entry: dict[str, str],
    judgment: dict[str, Any] | None,
    items: list[dict[str, Any]],
) -> str:
    source_id = str(entry.get("source_id") or "").strip()
    if isinstance(judgment, dict) and judgment:
        main_use = str(judgment.get("main_use") or "").strip()
        if main_use:
            return f"Source role for this citation: {_readable_main_use(main_use)}"
    for item in items:
        for item_source in _string_list(item.get("source_ids")) + _string_list(item.get("source_id")):
            if source_id and item_source != source_id:
                continue
            role = str(item.get("citation_role") or item.get("reader_evidence_role") or item.get("role") or "").strip()
            if role:
                return f"Source role for this citation: {_readable_main_use(role)}"
    return ""


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


def _trace_assertion_bundle_lines(item: dict[str, Any]) -> list[str]:
    rows = []
    seen = set()
    for bundle in _list(item.get("assertion_bundles")):
        if not isinstance(bundle, dict):
            continue
        bundle_id = str(bundle.get("evidence_bundle_id") or "").strip()
        if not bundle_id or bundle_id in seen:
            continue
        seen.add(bundle_id)
        parts = [
            str(bundle.get("value") or "").strip(),
            str(bundle.get("endpoint") or "").strip(),
            str(bundle.get("interval") or "").strip(),
        ]
        label = "; ".join(part for part in parts if part)
        line = f"      - `{bundle_id}`"
        if label:
            line += f": {label}"
        inference = str(bundle.get("allowed_inference") or "").strip()
        if inference:
            line += f" | Use as: {inference}"
        forbidden = str(bundle.get("forbidden_inference") or "").strip()
        if forbidden:
            line += f" | Do not use as: {forbidden}"
        rows.append(line)
    return rows
