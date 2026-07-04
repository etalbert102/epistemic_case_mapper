from __future__ import annotations


SECTION_MODEL_ATTEMPTS = 3


def retry_section_prompt(base_prompt: str, issues: list[str], *, attempt: int) -> str:
    feedback = "\n".join(f"- {issue}" for issue in issues[:8]) or "- Output was not parseable or locally valid."
    return (
        f"{base_prompt.rstrip()}\n\n"
        f"Previous attempt {attempt - 1} was rejected for these reasons:\n"
        f"{feedback}\n\n"
        "Try again. Return the same section only. Preserve the heading, required evidence, required gaps, and required cruxes. "
        "Return valid JSON if possible: {\"section_markdown\": \"## Same Heading\\n\\nRewritten section\"}.\n"
    )
