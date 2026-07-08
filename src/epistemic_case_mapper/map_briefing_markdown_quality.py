from __future__ import annotations

import re


KNOWN_MEMO_HEADINGS = (
    "Decision Brief",
    "What the Evidence Supports",
    "What Limits the Inference",
    "Decision Cruxes",
    "Practical Scope and Exceptions",
    "Practical Read",
    "Why This Read",
    "Evidence Carrying the Conclusion",
    "Limits of the Current Map",
    "Evidence Gaps and Scope Limits",
    "Evidence Trail",
    "Sources",
)


def repair_markdown_structure(markdown: str) -> str:
    """Repair common model formatting damage without changing semantics."""

    text = str(markdown).replace("\\n", "\n").strip()
    if not text:
        return ""
    for heading in KNOWN_MEMO_HEADINGS:
        text = re.sub(rf"(?<!^)(?<!\n)\s+##\s+{re.escape(heading)}\b", f"\n\n## {heading}", text)
        text = re.sub(rf"(?m)^(##\s+{re.escape(heading)})(\s+)(?=\*\*|[A-Z0-9])", r"\1\n\n", text)
    text = re.sub(r"(?m)([^\n])\s+(\*\*Confidence:\*\*)", r"\1\n\n\2", text)
    text = re.sub(r"(?<!\n)\s+(-\s+(?:\*\*|\[[^\]]+\]|\S))", r"\n\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip() + "\n"


def markdown_structure_issues(markdown: str, *, original: str = "") -> list[str]:
    text = str(markdown)
    issues: list[str] = []
    heading_count = len(re.findall(r"^##\s+\S", text, flags=re.MULTILINE))
    original_heading_count = len(re.findall(r"^##\s+\S", str(original), flags=re.MULTILINE))
    if original_heading_count >= 2 and heading_count < max(2, original_heading_count // 2):
        issues.append("repair dropped most Markdown section headings")
    if any(re.search(r"\S\s+##\s+\S", line) for line in text.splitlines()):
        issues.append("repair contains inline Markdown headings")
    long_lines = [line for line in text.splitlines() if len(line) > 1600]
    if long_lines:
        issues.append("repair contains collapsed overlong Markdown lines")
    if "```" in text:
        issues.append("repair contains fenced wrapper")
    return issues


def extraction_debris_issues(markdown: str) -> list[str]:
    text = str(markdown)
    issues: list[str] = []
    if "..." in text or "…" in text:
        issues.append("memo contains ellipsis-truncated extraction fragments")
    if re.search(r"\b(?:eTable|eFigure)\s+\d+\b|\b(?:Fig\.?|Table)\s+\d+[.:]", text, flags=re.IGNORECASE):
        issues.append("memo contains table or figure caption fragments")
    if re.search(r"\[(?:DOI|PubMed|Google Scholar|Crossref)\]", text, flags=re.IGNORECASE):
        issues.append("memo contains reference-list debris")
    if re.search(r"\bdoi:\s*10\.", text, flags=re.IGNORECASE):
        issues.append("memo contains DOI reference debris")
    return issues
