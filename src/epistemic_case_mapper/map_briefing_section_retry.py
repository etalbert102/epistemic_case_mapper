from __future__ import annotations

import re


SECTION_MODEL_ATTEMPTS = 3


def retry_section_prompt(base_prompt: str, issues: list[str], *, attempt: int) -> str:
    feedback = "\n".join(f"- {_sanitized_retry_issue(issue)}" for issue in issues[:8]) or "- Output was not parseable or locally valid."
    return (
        f"{base_prompt.rstrip()}\n\n"
        f"Previous attempt {attempt - 1} was rejected for these reasons:\n"
        f"{feedback}\n\n"
        "Try again. Return the same section only. Preserve the heading, required evidence, required gaps, and required cruxes. "
        "Return regular Markdown only, beginning with the same ## heading. Do not use JSON or a code fence.\n"
    )


def _sanitized_retry_issue(issue: str) -> str:
    text = re.sub(r"\s+", " ", str(issue)).strip()
    if text.startswith("section repeats evidence owned by "):
        owner = text.removeprefix("section repeats evidence owned by ").split(":", 1)[0].strip()
        return f"section used evidence assigned outside this section" + (f" ({owner})" if owner else "")
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
