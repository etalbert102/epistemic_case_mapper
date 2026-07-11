from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_obligations import all_memo_obligations
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
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
    next_memo = _replace_source_aliases(normalized, source_aliases)
    if next_memo != normalized:
        changes.append("normalized_source_labels")
        normalized = next_memo
    next_memo = _replace_sources_section(normalized, packet)
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


def _replace_sources_section(memo: str, packet: dict[str, Any]) -> str:
    body = _strip_sources_section(memo).rstrip()
    sources = _cited_source_lines(body, packet)
    if not sources:
        return body + "\n"
    return "\n".join([body, "", "## Sources", "", *sources]).rstrip() + "\n"


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
        display = entry["display"]
        if display and _contains_text(body, display):
            cited.append((lowered.find(display.lower()), _source_line_for_entry(entry)))
    return _dedupe(line for _, line in sorted(cited, key=lambda row: row[0]))


def _canonical_source_entries(packet: dict[str, Any]) -> list[dict[str, str]]:
    urls = _source_url_lookup(packet)
    labels = _packet_source_labels(packet)
    common_prefix = _common_token_prefix(labels)
    entries = []
    for label in labels:
        display = _preferred_source_display({"source_label": label}, common_prefix=common_prefix)
        if not display:
            continue
        entries.append({"display": display, "url": urls.get(label, "")})
    return _dedupe_entries(entries)


def _source_url_lookup(packet: dict[str, Any]) -> dict[str, str]:
    urls = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        label = str(source.get("source_label") or "").strip()
        url = str(source.get("source_url") or "").strip()
        if label and url:
            for variant in _source_label_variants(label):
                urls[variant] = url
    return urls


def _source_line_for_entry(entry: dict[str, str]) -> str:
    display = entry.get("display", "")
    url = entry.get("url", "")
    return f"* [{display}]({url})" if display and url else f"* {display}"


def _dedupe_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    deduped = []
    for entry in entries:
        key = _norm(entry.get("display", ""))
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


def _replace_source_aliases(memo: str, replacements: dict[str, str]) -> str:
    normalized = memo
    for source_label, display in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if source_label and display and source_label != display:
            normalized = normalized.replace(source_label, display)
    return normalized


def _source_alias_replacements(packet: dict[str, Any]) -> dict[str, str]:
    labels = _packet_source_labels(packet)
    common_prefix = _common_token_prefix(labels)
    replacements: dict[str, str] = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        source_label = str(source.get("source_label") or "").strip()
        display = _preferred_source_display(source, common_prefix=common_prefix)
        if not display:
            continue
        aliases = [
            str(source.get("source_id") or "").strip(),
            source_label,
            str(source.get("display_label") or "").strip(),
            str(source.get("citation_label") or "").strip(),
        ]
        for alias in aliases:
            for variant in _source_label_variants(alias):
                if variant and variant != display:
                    replacements[variant] = display
    for source_label in labels:
        if not source_label:
            continue
        display = _preferred_source_display({"source_label": source_label}, common_prefix=common_prefix)
        if display and display != source_label:
            for alias in _source_label_variants(source_label):
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


def _source_label_variants(source_label: str) -> list[str]:
    variants = [source_label]
    if "_" in source_label:
        variants.append(source_label.replace("_", " "))
    if " " in source_label:
        variants.append(source_label.replace(" ", "_"))
        variants.append(source_label.replace(" Sources ", "_Sources "))
        variants.append(source_label.replace(" sources ", "_sources "))
    if "_Sources " in source_label:
        variants.append(source_label.replace("_Sources ", " Sources "))
    if "_sources " in source_label:
        variants.append(source_label.replace("_sources ", " sources "))
    return list(dict.fromkeys(variant for variant in variants if variant))


def _preferred_source_display(source: dict[str, Any], *, common_prefix: list[str]) -> str:
    label = str(source.get("source_label") or "").strip()
    for key in ("citation_label", "display_label"):
        value = str(source.get(key) or "").strip()
        if value and value != label:
            return value
    if common_prefix:
        tokens = label.replace("_", " ").split()
        if [token.lower() for token in tokens[: len(common_prefix)]] == [token.lower() for token in common_prefix]:
            stripped = " ".join(tokens[len(common_prefix) :]).strip()
            if stripped:
                return stripped
    artifact_stripped = _strip_artifact_source_prefix(label)
    if artifact_stripped != label:
        return artifact_stripped
    return label


def _strip_artifact_source_prefix(label: str) -> str:
    tokens = str(label or "").replace("_", " ").split()
    lowered = [token.lower() for token in tokens]
    if len(tokens) >= 5 and lowered[:2] == ["deep", "research"] and "sources" in lowered[2:5]:
        source_index = lowered.index("sources", 2, 5)
        stripped = " ".join(tokens[source_index + 1 :]).strip()
        if len(stripped.split()) >= 2:
            return stripped
    return label


def _common_token_prefix(labels: list[str]) -> list[str]:
    tokenized = [label.replace("_", " ").split() for label in labels if label.strip()]
    if len(tokenized) < 2:
        return []
    prefix: list[str] = []
    for tokens in zip(*tokenized):
        lowered = {token.lower() for token in tokens}
        if len(lowered) != 1:
            break
        prefix.append(tokens[0])
    if len(prefix) < 2:
        return []
    shortest_remainder = min((len(tokens) - len(prefix) for tokens in tokenized), default=0)
    return prefix if shortest_remainder >= 2 else []


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    return not needle or needle.lower() in text.lower()
