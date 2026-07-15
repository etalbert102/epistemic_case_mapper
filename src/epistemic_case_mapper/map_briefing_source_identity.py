from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    string_list as _string_list,
)


def common_source_prefix(labels: list[str]) -> list[str]:
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


def preferred_source_display(source: dict[str, Any], *, common_prefix: list[str] | None = None) -> str:
    label = str(source.get("source_label") or source.get("display_label") or source.get("source_id") or "").strip()
    for key in ("citation_label", "display_label"):
        value = str(source.get(key) or "").strip()
        if value and value != label:
            return value
    prefix = common_prefix or []
    if prefix:
        tokens = label.replace("_", " ").split()
        if [token.lower() for token in tokens[: len(prefix)]] == [token.lower() for token in prefix]:
            stripped = " ".join(tokens[len(prefix) :]).strip()
            if stripped:
                return stripped
    artifact_stripped = strip_artifact_source_prefix(label)
    if artifact_stripped != label:
        return artifact_stripped
    return label


def compact_source_display(source: dict[str, Any], *, common_prefix: list[str] | None = None) -> str:
    citation = str(source.get("citation_label") or "").strip()
    if citation and len(citation) <= 64:
        return citation
    source_id = str(source.get("source_id") or "").strip()
    from_id = _compact_source_id(source_id)
    if from_id:
        return from_id
    if citation:
        return _compact_title(citation)
    label = str(source.get("source_label") or "").strip()
    if label and label != source_id:
        label = strip_artifact_source_prefix(label)
        return _compact_title(label) if len(label) > 64 else label
    display = preferred_source_display(source, common_prefix=common_prefix)
    return _compact_title(display) if len(display) > 64 else display


def _compact_source_id(source_id: str) -> str:
    tokens = [token for token in re.split(r"[_\s-]+", str(source_id or "")) if token]
    for index, token in enumerate(tokens):
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            lead = tokens[index - 1] if index else ""
            if not lead:
                return token
            compact_lead = lead.title() if len(lead) <= 2 else lead.upper() if len(lead) <= 5 else lead.title()
            return f"{compact_lead} {token}"
    return ""


def _compact_title(title: str) -> str:
    year = re.search(r"\b((?:19|20)\d{2})\b", str(title or ""))
    words = [word for word in re.findall(r"[A-Za-z][A-Za-z-]*", str(title or "")) if word.lower() not in _TITLE_STOPWORDS]
    if not words:
        return str(title or "").strip()
    prefix = " ".join(words[:2])
    return f"{prefix} {year.group(1)}" if year else prefix


_TITLE_STOPWORDS = {"a", "an", "and", "between", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with"}


def strip_artifact_source_prefix(label: str) -> str:
    tokens = str(label or "").replace("_", " ").split()
    lowered = [token.lower() for token in tokens]
    if len(tokens) >= 5 and lowered[:2] == ["deep", "research"] and "sources" in lowered[2:5]:
        source_index = lowered.index("sources", 2, 5)
        stripped = " ".join(tokens[source_index + 1 :]).strip()
        if len(stripped.split()) >= 2:
            return stripped
    return str(label or "")


def source_label_variants(source_label: str) -> list[str]:
    variants = [source_label]
    if "_" in source_label:
        variants.append(source_label.replace("_", " "))
        tokens = [token for token in source_label.split("_") if token]
        for index, token in enumerate(tokens):
            if index and re.fullmatch(r"(?:19|20)\d{2}", token):
                lead = tokens[index - 1]
                rest = "_".join(tokens[index + 1 :])
                if lead and rest:
                    variants.append(f"{lead.title()} et{token}_{rest}")
                    variants.append(f"{lead.lower()} et{token}_{rest}")
    if " " in source_label:
        variants.append(source_label.replace(" ", "_"))
        variants.append(source_label.replace(" Sources ", "_Sources "))
        variants.append(source_label.replace(" sources ", "_sources "))
    if "_Sources " in source_label:
        variants.append(source_label.replace("_Sources ", " Sources "))
    if "_sources " in source_label:
        variants.append(source_label.replace("_sources ", " sources "))
    return list(dict.fromkeys(variant for variant in variants if variant))


def source_id_alias_map(source_trail: list[Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for source in source_trail:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or source.get("source_label") or "").strip()
        if not source_id:
            continue
        values = [
            source_id,
            str(source.get("source_label") or "").strip(),
            str(source.get("display_label") or "").strip(),
            str(source.get("citation_label") or "").strip(),
        ]
        for value in values:
            for variant in source_label_variants(value):
                if variant:
                    aliases[variant] = source_id
    return aliases


def source_ids_for_labels(labels: list[str], source_trail: list[Any]) -> list[str]:
    aliases = source_id_alias_map(source_trail)
    return _dedupe(source_id_for_label(label, aliases) for label in labels if source_id_for_label(label, aliases))


def source_id_for_label(label: str, aliases: dict[str, str]) -> str:
    value = str(label or "").strip()
    if not value:
        return ""
    if value in aliases:
        return aliases[value]
    normalized = _normalize_source_key(value)
    for alias, source_id in aliases.items():
        if _normalize_source_key(alias) == normalized:
            return source_id
    return value


def project_sources_to_ids_for_model(payload: Any, source_trail: list[Any]) -> Any:
    aliases = source_id_alias_map(source_trail)
    return _project_sources_to_ids(payload, aliases)


def project_source_text_to_ids_for_model(payload: Any, source_trail: list[Any]) -> Any:
    aliases = source_id_alias_map(source_trail)
    return _project_source_text_to_ids(payload, aliases)


def replace_source_aliases_with_ids(text: str, source_trail: list[Any]) -> str:
    return _replace_source_aliases_with_ids(text, source_id_alias_map(source_trail))


def source_id_registry_for_model(source_trail: list[Any]) -> list[dict[str, Any]]:
    aliases = source_id_alias_map(source_trail)
    rows = []
    seen = set()
    for source in source_trail:
        if not isinstance(source, dict):
            continue
        source_id = source_id_for_label(str(source.get("source_id") or source.get("source_label") or ""), aliases)
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        row = {"source_id": source_id}
        used_for = _string_list(source.get("used_for"))
        if used_for:
            row["used_for"] = used_for
        rows.append(row)
    return rows


def _project_sources_to_ids(payload: Any, aliases: dict[str, str]) -> Any:
    if isinstance(payload, list):
        return [_project_sources_to_ids(row, aliases) for row in payload]
    if not isinstance(payload, dict):
        return payload
    projected: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "source_label":
            source_id = source_id_for_label(str(value or ""), aliases)
            if source_id:
                projected["source_id"] = source_id
            continue
        if key == "source_labels":
            source_ids = _dedupe(
                source_id_for_label(label, aliases)
                for label in _string_list(value)
                if source_id_for_label(label, aliases)
            )
            if source_ids:
                projected["source_ids"] = _merge_source_ids(projected.get("source_ids"), source_ids, aliases)
            continue
        if key == "source_id":
            source_id = source_id_for_label(str(value or ""), aliases)
            if source_id:
                projected["source_id"] = source_id
            continue
        if key == "source_ids":
            projected["source_ids"] = _merge_source_ids(projected.get("source_ids"), _string_list(value), aliases)
            continue
        if key in {"display_label", "citation_label", "source_aliases"}:
            continue
        if key == "source_trail":
            projected["source_trail"] = source_id_registry_for_model(_list(value))
            continue
        projected[key] = _project_sources_to_ids(value, aliases)
    return projected


def _project_source_text_to_ids(payload: Any, aliases: dict[str, str]) -> Any:
    if isinstance(payload, str):
        return _replace_source_aliases_with_ids(payload, aliases)
    if isinstance(payload, list):
        return [_project_source_text_to_ids(row, aliases) for row in payload]
    if isinstance(payload, dict):
        return {key: _project_source_text_to_ids(value, aliases) for key, value in payload.items()}
    return payload


def _replace_source_aliases_with_ids(text: str, aliases: dict[str, str]) -> str:
    value = str(text or "")
    for alias, source_id in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if alias and source_id and alias != source_id:
            value = value.replace(alias, source_id)
    return value


def _merge_source_ids(existing: Any, incoming: list[str], aliases: dict[str, str]) -> list[str]:
    return _dedupe(
        source_id_for_label(value, aliases)
        for value in [*_string_list(existing), *incoming]
        if source_id_for_label(value, aliases)
    )


def _normalize_source_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
