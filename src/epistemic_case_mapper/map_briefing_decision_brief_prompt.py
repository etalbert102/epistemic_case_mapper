from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_decision_brief_last import (
    decision_brief_answer_frame_guidance,
    decision_brief_last_packet,
)


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)


def _decision_brief_bluf_prompt(contract: dict[str, Any], body_memo: str, fallback: str) -> str:
    substantive_body = _substantive_body_sections_for_bluf(body_memo)
    question = str(contract.get("question", "")).strip()
    confidence = str(contract.get("confidence") or "").strip()
    answer_frame = decision_brief_answer_frame_guidance(contract)
    spine_packet = decision_brief_last_packet(contract, body_memo)
    return (
        "You are an analyst writing the opening BLUF for a source-grounded decision memo.\n"
        "Use only the canonical decision spine and accepted body sections below as the source of truth. Do not add facts.\n"
        "Write a crisp executive opening that directly answers the decision question before caveats.\n"
        "Use the controlling answer frame below, but express it in the natural vocabulary of this decision question and source packet.\n"
        "Do not force the answer into generic labels such as beneficial, harmful, neutral, use, or avoid unless that exact framing is warranted by the answer frame and accepted body sections.\n"
        "If the controlling frame is conditional or context-dependent, say so directly and then name the practical default or boundary.\n"
        "Prefer this shape: direct answer frame; why; main boundary; confidence.\n"
        "Keep it under 150 words, preserve the exact Decision Brief heading, include the decision question line, and include a confidence line.\n"
        "Return only the rewritten Decision Brief section as Markdown. Do not include any other ## section.\n\n"
        f"Decision question: {question}\n"
        f"Confidence: {confidence}\n\n"
        "Controlling answer frame:\n"
        f"{answer_frame}\n\n"
        "Canonical decision spine packet:\n"
        f"{json.dumps(spine_packet, indent=2, ensure_ascii=False)}\n\n"
        "Accepted body sections:\n"
        f"{substantive_body.strip()}\n\n"
        "Section to rewrite:\n"
        f"{fallback.strip()}"
    )


def decision_brief_repair_prompt(contract: dict[str, Any], body_memo: str, rejected_section: str, issues: list[str]) -> str:
    feedback = "\n".join(f"- {_safe_issue(issue)}" for issue in issues[:8]) or "- The Decision Brief did not pass validation."
    return (
        "You are correcting a rejected Decision Brief section for a source-grounded decision memo.\n"
        "Do not start over. Repair the rejected section with the smallest changes needed to fix the validation failures.\n"
        "Use only the controlling answer frame, accepted body sections, and rejected section below. Do not add facts.\n"
        "The opening must answer the decision question before caveats, preserve the question line and confidence line, and avoid upgrading a bounded answer into a stronger verdict.\n"
        "Return only the corrected Decision Brief section as Markdown. Do not include any other ## section.\n\n"
        "Validation failures to fix:\n"
        f"{feedback}\n\n"
        "Controlling answer frame:\n"
        f"{decision_brief_answer_frame_guidance(contract)}\n\n"
        "Accepted body sections:\n"
        f"{_substantive_body_sections_for_bluf(body_memo)}\n\n"
        "Rejected Decision Brief to correct. The text under Section to rewrite is the rejected section:\n"
        "Section to rewrite:\n"
        f"{rejected_section.strip()}"
    )


def _safe_issue(issue: str) -> str:
    text = re.sub(r"\s+", " ", str(issue)).strip()
    return text.split(":", 1)[0]


def _substantive_body_sections_for_bluf(body_memo: str) -> str:
    _leading, sections = _split_sections(body_memo)
    substantive = [
        section["markdown"]
        for section in sections
        if section["title"].strip().lower() not in {"evidence trail", "sources"}
    ]
    return "\n\n".join(substantive).strip() or body_memo.strip()


def _split_sections(markdown: str) -> tuple[str, list[dict[str, str]]]:
    matches = list(SECTION_RE.finditer(markdown))
    if not matches:
        return markdown, []
    leading = markdown[: matches[0].start()]
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append({"title": match.group(1).strip(), "markdown": markdown[match.start():end].strip()})
    return leading, sections
