from __future__ import annotations

import json
import re


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", flags=re.DOTALL | re.IGNORECASE)


def canonical_json_output(text: str) -> str:
    cleaned = ANSI_ESCAPE_RE.sub("", text).strip()
    for candidate in _json_candidates(cleaned):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        data = _repair_known_field_aliases(data)
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return cleaned + ("\n" if cleaned else "")


def _json_candidates(text: str) -> list[str]:
    candidates = [match.group(1).strip() for match in JSON_FENCE_RE.finditer(text)]
    extracted = _extract_first_json_value(text)
    if extracted:
        candidates.append(extracted)
    candidates.append(text)
    return [candidate for candidate in candidates if candidate]


def _extract_first_json_value(text: str) -> str | None:
    starts = [index for index, char in enumerate(text) if char in "[{"]
    decoder = json.JSONDecoder()
    for start in starts:
        try:
            _, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        return text[start : start + end]
    return None


def _repair_known_field_aliases(value):
    if isinstance(value, list):
        return [_repair_known_field_aliases(item) for item in value]
    if not isinstance(value, dict):
        return value
    repaired = {}
    for key, item in value.items():
        repaired[_canonical_key(key)] = _repair_known_field_aliases(item)
    return repaired


def _canonical_key(key: str) -> str:
    aliases = {
        "entailed_by__excerpt": "entailed_by_excerpt",
        "excerpt_entailed_by_excerpt": "entailed_by_excerpt",
        "entally_by_excerpt": "entailed_by_excerpt",
        "entailed_by_by_excerpt": "entailed_by_excerpt",
        "entailed_by_source_excerpt": "entailed_by_excerpt",
        "sourcecap_id": "source_id",
        "sourceID": "source_id",
        "ration_type": "rationale",
    }
    return aliases.get(key, key)
