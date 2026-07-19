from __future__ import annotations

import re


SECTION_MODEL_ATTEMPTS = 3


def retry_section_prompt(base_prompt: str, issues: list[str], *, attempt: int, rejected_section: str = "") -> str:
    feedback = "\n".join(f"- {_sanitized_retry_issue(issue)}" for issue in issues[:8]) or "- Output was not parseable or locally valid."
    rejected_block = _rejected_section_block(rejected_section)
    return (
        f"{base_prompt.rstrip()}\n\n"
        f"Previous attempt {attempt - 1} was rejected for these reasons:\n"
        f"{feedback}\n\n"
        f"{rejected_block}"
        "Correct the rejected section instead of starting over. Make the smallest changes needed to satisfy the rejection reasons and the original section contract. "
        "Return the same section only. Preserve the heading, required evidence, required gaps, and required cruxes. "
        "If a required main-memo obligation was dropped, satisfy it using the required obligation search terms from the original section contract. "
        "Use parenthetical source labels exactly as supplied. "
        "Return regular Markdown only, beginning with the same ## heading.\n"
    )


def _sanitized_retry_issue(issue: str) -> str:
    text = re.sub(r"\s+", " ", str(issue)).strip()
    if text.startswith("section repeats evidence owned by ") or text.startswith("section repeats source detail without adding "):
        return "section repeated source detail without adding this section's distinct analytic value"
    if text.startswith("section over-explains evidence owned by "):
        owner = text.removeprefix("section over-explains evidence owned by ").split(":", 1)[0].strip()
        return f"section over-explained reference-only evidence" + (f" ({owner})" if owner else "")
    if text.startswith("section dropped required main-memo obligation:"):
        obligation = re.search(r"\b([a-z]+_[a-z]+_\d+)\b", text)
        return (
            f"section dropped required main-memo obligation {obligation.group(1)}"
            if obligation
            else "section dropped a required main-memo obligation"
        )
    if text.startswith("section dropped required evidence:"):
        return "section dropped required local evidence"
    if text.startswith("section dropped required gap:"):
        return "section dropped a required named gap"
    if text.startswith("section dropped required crux:"):
        return "section dropped a required crux"
    return text.split(":", 1)[0]


def _rejected_section_block(rejected_section: str) -> str:
    section = _trim_rejected_section(rejected_section)
    if not section:
        return ""
    return (
        "Rejected section to correct:\n"
        f"{section}\n\n"
    )


def _trim_rejected_section(text: str, *, max_chars: int = 3500) -> str:
    cleaned = "\n".join(line.rstrip() for line in str(text).strip().splitlines())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "\n[truncated]"
