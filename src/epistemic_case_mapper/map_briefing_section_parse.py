from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.model_outputs import canonical_json_output


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)


def parse_section_payload(raw: str, *, expected_title: str = "") -> dict[str, Any] | None:
    if _looks_like_section_prompt(raw.strip()):
        return None
    payload = _json_payload(raw)
    if isinstance(payload, dict):
        markdown = _payload_markdown(payload)
        if markdown and _heading_matches(markdown, expected_title):
            return {"section_markdown": markdown}
    markdown = _loose_payload_markdown(raw)
    if markdown and _heading_matches(markdown, expected_title):
        return {"section_markdown": markdown}
    markdown = _raw_markdown_section(raw, expected_title=expected_title)
    if markdown:
        return {"section_markdown": markdown}
    return None


def _json_payload(raw: str) -> Any:
    try:
        return json.loads(canonical_json_output(raw))
    except json.JSONDecodeError:
        return None


def _payload_markdown(payload: dict[str, Any]) -> str:
    for key in ("section_markdown", "memo_markdown", "section", "markdown", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _strip_markdown_fence(value)
    return ""


def _loose_payload_markdown(raw: str) -> str:
    cleaned = raw.strip()
    if _looks_like_section_prompt(cleaned):
        return ""
    if _is_fenced_block(cleaned):
        cleaned = _strip_fence_boundaries(cleaned).strip()
    elif not cleaned.lstrip().startswith("{"):
        return ""
    keys = "|".join(("section_markdown", "memo_markdown", "section", "markdown", "text", "content"))
    match = re.search(rf'"(?:{keys})"\s*:\s*"(?P<value>.*)"\s*}}\s*$', cleaned, flags=re.DOTALL)
    if not match:
        return ""
    return (
        match.group("value")
        .replace("\\n", "\n")
        .replace('\\"', '"')
        .replace("\\/", "/")
        .strip()
    )


def _raw_markdown_section(raw: str, *, expected_title: str) -> str:
    cleaned = _strip_markdown_fence(raw)
    if expected_title:
        pattern = re.compile(rf"^##\s+{re.escape(expected_title)}\s*$", flags=re.MULTILINE | re.IGNORECASE)
        match = pattern.search(cleaned)
        if not match:
            return ""
        return cleaned[match.start() :].strip()
    return cleaned.strip() if cleaned.lstrip().startswith("## ") else ""


def _heading_matches(markdown: str, expected_title: str) -> bool:
    if not expected_title:
        return markdown.lstrip().startswith("## ")
    headings = SECTION_RE.findall(markdown)
    return bool(headings and headings[0].strip().lower() == expected_title.strip().lower())


def _strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    return _strip_fence_boundaries(cleaned).strip() if _is_fenced_block(cleaned) else cleaned


def _looks_like_section_prompt(text: str) -> bool:
    prefix = text[:3000]
    return (
        prefix.startswith("You are ")
        and "Section contract:" in prefix
    )


def _is_fenced_block(text: str) -> bool:
    return text.startswith("```") and text.endswith("```")


def _strip_fence_boundaries(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text
