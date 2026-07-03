from __future__ import annotations

import re
from typing import Any


def ensure_reader_memo_metadata(markdown: str, scaffold: dict[str, Any]) -> str:
    memo = markdown.strip()
    question = str(scaffold.get("question", "")).strip()
    if question:
        memo = remove_standalone_question_restatement(memo, question)
    if "**Decision question:**" not in memo:
        question_lines = decision_question_lines(scaffold)
        if question_lines:
            metadata = "\n" + "\n".join(question_lines) + "\n"
            memo = re.sub(r"^(## Decision Brief\s*)", lambda match: match.group(1) + metadata, memo, count=1)
    if "\n## Sources\n" not in memo:
        source_lines = source_list_lines(scaffold)
        if source_lines:
            memo = memo.rstrip() + "\n" + "\n".join(source_lines)
    return _clean_memo_text(memo)


def decision_question_lines(scaffold: dict[str, Any]) -> list[str]:
    question = str(scaffold.get("question", "")).strip()
    if not question:
        return []
    return [f"**Decision question:** {question}", ""]


def remove_standalone_question_restatement(markdown: str, question: str) -> str:
    normalized_question = _normalized_question_text(question)
    if not normalized_question:
        return markdown
    paragraphs = re.split(r"(\n\s*\n)", markdown.strip())
    kept: list[str] = []
    for index in range(0, len(paragraphs), 2):
        paragraph = paragraphs[index]
        separator = paragraphs[index + 1] if index + 1 < len(paragraphs) else ""
        if _normalized_question_text(paragraph) == normalized_question:
            continue
        kept.append(paragraph)
        if separator:
            kept.append(separator)
    return "".join(kept).strip()


def source_list_lines(scaffold: dict[str, Any]) -> list[str]:
    source_lookup = scaffold.get("source_display_names", {})
    if not isinstance(source_lookup, dict) or not source_lookup:
        return []
    rows = []
    for source_id, display in sorted(source_lookup.items(), key=lambda item: str(item[1]).lower()):
        label = str(display).strip() or str(source_id).strip()
        if label:
            rows.append(f"- {label}")
    return ["", "## Sources", "", *rows] if rows else []


def _clean_memo_text(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    collapsed: list[str] = []
    blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and blank:
            continue
        collapsed.append(line)
        blank = is_blank
    return "\n".join(collapsed).strip() + "\n"


def _normalized_question_text(text: str) -> str:
    cleaned = re.sub(r"^\*\*Decision question:\*\*\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned.rstrip("?!.")
