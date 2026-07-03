from __future__ import annotations

from typing import Any


def apply_reader_memo_edit_suggestions(memo: str, payload: dict[str, Any]) -> dict[str, Any]:
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
    applied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for index, edit in enumerate(edits[:8]):
        if not isinstance(edit, dict):
            skipped.append({"index": str(index), "reason": "edit was not an object"})
            continue
        target = str(edit.get("target", "")).strip()
        replacement = str(edit.get("replacement", "")).strip()
        reason = str(edit.get("reason", "")).strip()
        issue = _edit_suggestion_issue(candidate, target, replacement)
        if issue:
            skipped.append({"index": str(index), "reason": issue, "target": target[:120]})
            continue
        candidate = candidate.replace(target, replacement, 1)
        applied.append({"index": str(index), "target": target, "replacement": replacement, "reason": reason})
    return {
        "memo": _clean_memo_text(candidate),
        "raw_edit_count": len(edits),
        "applied_edits": applied,
        "skipped_edits": skipped,
        "issues": [item["reason"] for item in skipped],
    }


def _edit_suggestion_issue(memo: str, target: str, replacement: str) -> str:
    if not target or not replacement:
        return "target and replacement are required"
    if target == replacement:
        return "replacement is identical to target"
    if len(target) > 700 or len(replacement) > 900:
        return "edit is too large for a local prose cleanup"
    if "\n## " in target or "\n## " in replacement or target.startswith("##") or replacement.startswith("##"):
        return "top-level headings cannot be edited by the whole-memo edit pass"
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
