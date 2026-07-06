from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError


NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])(?:\d+(?:\.\d+)?%?|\d+\s*(?:-|to)\s*\d+|\b\d+/\d+\b)(?:\s*(?:mg|g|kg|ml|l|cm|mm|years?|months?|days?|weeks?|hours?|per\s+\w+))?", flags=re.IGNORECASE)
SOURCE_LABEL_RE = re.compile(r"\([A-Z][A-Za-z0-9][A-Za-z0-9 .,&:/+-]{1,90}\)")
EVIDENCE_ID_RE = re.compile(r"\b(?:claim|relation|source|evidence)_[A-Za-z0-9_.:-]+\b|`[^`\n]*(?:claim|relation|source|evidence)[^`\n]*`", flags=re.IGNORECASE)


class ReaderMemoEditSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target: str
    replacement: str
    reason: str = ""
    target_section: str = ""
    edit_type: str = ""


def apply_reader_memo_edit_suggestions(
    memo: str,
    payload: dict[str, Any],
    *,
    protected_spans: dict[str, Any] | None = None,
    max_edits: int = 8,
    allowed_edit_types: set[str] | None = None,
    pass_name: str = "reader_memo_edit",
) -> dict[str, Any]:
    edits = payload.get("edits", [])
    if not isinstance(edits, list):
        return {
            "memo": memo,
            "raw_edit_count": 0,
            "applied_edits": [],
            "skipped_edits": [],
            "issues": ["edit response did not contain an edits list"],
        }
    candidate = memo
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    protected_texts = _protected_texts(protected_spans or {})
    changed_chars = 0
    for index, raw_edit in enumerate(edits[:max_edits]):
        try:
            edit = ReaderMemoEditSuggestion.model_validate(raw_edit)
        except ValidationError:
            skipped.append({"index": str(index), "reason": "edit was not an object or had invalid fields"})
            continue
        target = edit.target.strip()
        replacement = edit.replacement.strip()
        issue = _edit_suggestion_issue(
            candidate,
            target,
            replacement,
            protected_texts=protected_texts,
            allowed_edit_types=allowed_edit_types,
            edit_type=edit.edit_type.strip(),
        )
        if issue:
            skipped.append({"index": str(index), "reason": issue, "target": target[:120]})
            continue
        candidate = candidate.replace(target, replacement, 1)
        changed_chars += abs(len(replacement) - len(target))
        applied.append(
            {
                "index": str(index),
                "target": target,
                "replacement": replacement,
                "reason": edit.reason.strip(),
                "target_section": edit.target_section.strip(),
                "edit_type": edit.edit_type.strip(),
                "pass": pass_name,
            }
        )
    return {
        "memo": _clean_memo_text(candidate),
        "raw_edit_count": len(edits),
        "applied_edits": applied,
        "skipped_edits": skipped,
        "issues": [item["reason"] for item in skipped],
        "changed_char_count": changed_chars,
        "pass": pass_name,
    }


def _edit_suggestion_issue(
    memo: str,
    target: str,
    replacement: str,
    *,
    protected_texts: set[str] | None = None,
    allowed_edit_types: set[str] | None = None,
    edit_type: str = "",
) -> str:
    if not target or not replacement:
        return "target and replacement are required"
    if target == replacement:
        return "replacement is identical to target"
    if allowed_edit_types is not None and edit_type and edit_type not in allowed_edit_types:
        return "edit_type is not allowed for this pass"
    if len(target) > 700 or len(replacement) > 900:
        return "edit is too large for a local prose cleanup"
    if "\n## " in target or "\n## " in replacement or target.startswith("##") or replacement.startswith("##"):
        return "top-level headings cannot be edited by the whole-memo edit pass"
    if _touches_protected_text(target, protected_texts or set()):
        return "edit touches protected memo content"
    if _protected_tokens_changed(target, replacement, NUMBER_RE):
        return "edit changes or introduces protected numbers"
    if _protected_tokens_changed(target, replacement, SOURCE_LABEL_RE):
        return "edit changes or introduces source labels"
    if _protected_tokens_changed(target, replacement, EVIDENCE_ID_RE):
        return "edit changes or introduces evidence identifiers"
    count = memo.count(target)
    if count == 0:
        return "target text was not found exactly"
    if count > 1:
        return "target text was ambiguous"
    return ""


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


def _protected_texts(protected_spans: dict[str, Any]) -> set[str]:
    texts: set[str] = set()
    for span in protected_spans.get("spans", []) if isinstance(protected_spans.get("spans"), list) else []:
        if not isinstance(span, dict):
            continue
        text = str(span.get("text", "")).strip()
        if len(text) >= 2:
            texts.add(text)
    return texts


def _touches_protected_text(target: str, protected_texts: set[str]) -> bool:
    return any(text in target for text in protected_texts)


def _protected_tokens_changed(target: str, replacement: str, pattern: re.Pattern[str]) -> bool:
    target_tokens = set(pattern.findall(target))
    replacement_tokens = set(pattern.findall(replacement))
    return replacement_tokens != target_tokens
