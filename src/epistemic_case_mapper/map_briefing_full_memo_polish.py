from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_final_memo_diagnosis import build_memo_protected_spans
from epistemic_case_mapper.map_briefing_rewrite_edits import NUMBER_RE, SOURCE_LABEL_RE


def build_full_memo_polish_prompt(memo: str, obligation_packet: dict[str, Any], *, previous_issues: list[str] | None = None) -> str:
    retry_block = ""
    if previous_issues:
        retry_block = (
            "\nThe previous polished memo was rejected for these reasons. Correct them while preserving readability:\n"
            f"{json.dumps(previous_issues, indent=2, ensure_ascii=False)}\n"
        )
    return (
        "You are a senior decision analyst writing for a thoughtful human decision-maker.\n"
        "Rewrite the memo below into a polished, coherent, natural briefing memo that is decision-ready.\n\n"
        f"Goal: {_full_memo_polish_target_instruction(memo)}\n\n"
        "Use this structure unless the memo itself strongly suggests a better one:\n"
        "## Decision Brief\n"
        "[exact decision question line]\n"
        "[2-4 paragraph answer with the bottom line, main evidence tension, and practical implication]\n"
        "[exact confidence line]\n\n"
        "## What the Evidence Supports\n"
        "[explain the positive, neutral, or default case and the strongest supporting evidence]\n\n"
        "## What Limits the Inference\n"
        "[explain uncertainty, caveats, subgroup exceptions, evidence-family limits, and comparator limits]\n\n"
        "## Decision Cruxes\n"
        "[3-5 concrete cruxes in prose or a compact table; make them specific and complete]\n\n"
        "## Sources\n"
        "[leave source list for deterministic restoration]\n\n"
        "Hard constraints:\n"
        "- Preserve the decision question exactly.\n"
        "- Preserve the confidence level exactly.\n"
        "- Preserve the bottom-line stance, uncertainty, subgroup caveats, and named evidence limits.\n"
        "- Preserve the required evidence checklist below while merging or trimming repeated sentences.\n"
        "- Preserve load-bearing numbers and confidence intervals from the checklist; incidental numbers may move to the appendix.\n"
        "- Use factual claims, sources, numbers, populations, and causal interpretations already present in the memo or checklist.\n"
        "- It is okay to remove repetitive phrasing and merge sections when no decision-relevant information is lost.\n"
        "- Write like an analyst, not like a schema renderer.\n"
        "- Return the polished memo in Markdown only.\n"
        f"{retry_block}\n"
        "Required evidence checklist:\n"
        f"{_full_memo_polish_checklist(obligation_packet)}\n\n"
        "Original memo:\n"
        f"{memo.strip()}\n"
    )


def build_full_memo_polish_obligation_packet(
    memo: str,
    scaffold: dict[str, Any],
    contract: dict[str, Any],
    protected_spans: dict[str, Any] | None = None,
) -> dict[str, Any]:
    protected_spans = protected_spans or build_memo_protected_spans(memo, contract)
    load_bearing_numbers = _load_bearing_numbers(memo, contract)
    source_names = [
        str(value).strip()
        for value in (scaffold.get("source_display_names", {}) if isinstance(scaffold.get("source_display_names"), dict) else {}).values()
        if str(value).strip()
    ]
    source_names.extend(_source_lines_from_memo(memo))
    return {
        "schema_id": "reader_memo_full_polish_obligations_v1",
        "question": str(contract.get("question", "")).strip(),
        "confidence": str(contract.get("confidence", "")).strip(),
        "required_sources": sorted(set(source_names)),
        "required_numbers": sorted(load_bearing_numbers),
        "optional_numbers": sorted(_regex_tokens(memo, NUMBER_RE) - load_bearing_numbers),
        "required_source_labels": sorted(_regex_tokens(memo, SOURCE_LABEL_RE)),
        "required_evidence": contract.get("required_evidence", []) if isinstance(contract.get("required_evidence"), list) else [],
        "required_gaps": contract.get("required_gaps", []) if isinstance(contract.get("required_gaps"), list) else [],
        "practical_actions": contract.get("practical_actions", []) if isinstance(contract.get("practical_actions"), list) else [],
        "answer_frame": contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {},
        "protected_content_rules": protected_spans.get("rules", []) if isinstance(protected_spans.get("rules"), list) else [],
    }


def restore_full_memo_protected_content(candidate: str, *, original_memo: str, contract: dict[str, Any]) -> str:
    restored = _clean_memo_text(candidate)
    question_line = _protected_line(original_memo, "**Decision question:**")
    confidence_line = _protected_line(original_memo, "**Confidence:**")
    if not confidence_line:
        confidence = str(contract.get("confidence", "")).strip()
        if confidence:
            confidence_line = f"**Confidence:** {confidence}"
    if question_line:
        restored = _restore_or_insert_protected_line(restored, question_line, marker="decision question")
    if confidence_line:
        restored = _restore_or_insert_protected_line(restored, confidence_line, marker="confidence")
    restored = _drop_duplicate_protected_payload_lines(restored, [question_line, confidence_line])
    source_block = _source_block_from_memo(original_memo)
    if source_block:
        restored = _restore_source_block(restored, source_block)
    return _clean_memo_text(restored)


def build_full_memo_polish_patch_prompt(memo: str, issues: list[str], obligation_packet: dict[str, Any]) -> str:
    return (
        "You are repairing a polished decision memo after validation found missing required evidence.\n"
        "Revise the memo only enough to address the listed issues while preserving its concise analyst style.\n\n"
        "Rules:\n"
        "- Return the full revised memo in Markdown.\n"
        "- Add only information already present in the required evidence checklist or the current memo.\n"
        "- Use sources, numbers, populations, recommendations, and causal interpretations already present in the required evidence checklist or current memo.\n"
        "- Preserve the decision question, confidence line, uncertainty, and final Sources section.\n"
        "- Prefer a targeted sentence or bullet over expanding the whole memo.\n\n"
        "Validation issues to fix:\n"
        f"{json.dumps(issues[:12], indent=2, ensure_ascii=False)}\n\n"
        "Required evidence checklist:\n"
        f"{_full_memo_polish_checklist(obligation_packet)}\n\n"
        "Memo to patch:\n"
        f"{memo.strip()}\n"
    )


def build_full_memo_warning_repair_prompt(memo: str, warnings: list[str], repair_packet: dict[str, Any] | None = None) -> str:
    packet_block = ""
    if repair_packet:
        packet_block = (
            "Targeted repair packet:\n"
            f"{json.dumps(repair_packet, indent=2, ensure_ascii=False)}\n\n"
        )
    return (
        "You are repairing a polished decision memo after validation produced warnings.\n"
        "Use only the memo, warning list, and targeted repair packet below.\n"
        "Correct warnings when the fix is directly supported by that information.\n"
        "Correct only warnings with direct support in the memo, warning list, or targeted repair packet; leave unsupported warning points unchanged.\n\n"
        "Rules:\n"
        "- Return the full revised memo in Markdown.\n"
        "- Return Markdown.\n"
        "- Use facts, sources, numbers, populations, recommendations, and causal interpretations present in the memo, warnings, or repair packet.\n"
        "- Preserve the decision question, confidence line, uncertainty, and final Sources section.\n"
        "- If the repair packet provides an exact final_source_list, use those exact source names in the Sources section.\n"
        "- If the repair packet provides suggested_insertions, turn the minimum needed information into a natural edit in the most relevant existing sentence or paragraph.\n"
        "- Turn checklist fragments into fluent prose that preserves their supported meaning.\n"
        "- Prefer replacing the surrounding sentence or short paragraph over appending a new sentence that interrupts the flow.\n"
        "- Preserve exact numbers and parenthetical source labels when the repair packet marks them as validation targets.\n"
        "- Prefer targeted fixes over rewriting the memo again.\n\n"
        "Warnings to correct if possible:\n"
        f"{json.dumps(warnings[:16], indent=2, ensure_ascii=False)}\n\n"
        f"{packet_block}"
        "Memo to repair:\n"
        f"{memo.strip()}\n"
    )


def patchable_polish_issues(issues: list[str]) -> list[str]:
    patchable_prefixes = (
        "rewrite dropped required evidence:",
        "rewrite dropped required gap:",
        "rewrite did not convert the Practical Read",
        "rewrite does not explicitly address the comparator",
        "polish dropped practical obligation:",
        "polish dropped answer-frame obligation:",
        "polish dropped required number:",
        "polish dropped required source label:",
    )
    patchable_contains = ("failed scaffold validation",)
    selected: list[str] = []
    for issue in issues:
        text = str(issue).strip()
        if text and (text.startswith(patchable_prefixes) or any(marker in text for marker in patchable_contains)):
            selected.append(text)
    return _dedupe_issues(selected)


def _full_memo_polish_target_instruction(memo: str) -> str:
    words = len(memo.split())
    if words >= 1300:
        return "produce a coherent 900-1200 word memo that is easier to read than the original while preserving decision-relevant evidence."
    if words >= 800:
        return "produce a coherent memo that is shorter than the original where safe, without dropping decision-relevant evidence."
    return "produce a coherent memo about the same length or shorter; keep compact memos compact."


def _full_memo_polish_checklist(obligation_packet: dict[str, Any]) -> str:
    lines: list[str] = []
    question = str(obligation_packet.get("question", "")).strip()
    confidence = str(obligation_packet.get("confidence", "")).strip()
    if question:
        lines.append(f"- Decision question: {question}")
    if confidence:
        lines.append(f"- Confidence: {confidence}")
    lines.extend(_curated_evidence_checklist_lines(obligation_packet))
    lines.append("- Incidental appendix-only quantities may be omitted unless they carry one of the bullets above.")
    lines.append("- Preserve the final source list; exact source formatting will be restored deterministically.")
    return "\n".join(lines)


def _curated_evidence_checklist_lines(obligation_packet: dict[str, Any]) -> list[str]:
    selected = _select_checklist_rows(obligation_packet)
    lines: list[str] = []
    for role, row in selected:
        claim = _clean_claim_for_checklist(str(row.get("claim", "")).strip())
        if claim:
            lines.append(f"- Preserve {role}: {claim}")
    lines.extend(_answer_frame_checklist_lines(obligation_packet))
    lines.extend(_gap_checklist_lines(obligation_packet))
    return _dedupe_checklist_lines(lines)[:14]


def _select_checklist_rows(obligation_packet: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    question_terms = set(_content_terms(str(obligation_packet.get("question", ""))))
    rows = [
        row
        for row in obligation_packet.get("required_evidence", [])
        if isinstance(row, dict) and str(row.get("claim", "")).strip()
    ]
    ranked = sorted(
        (( _checklist_role(row), row) for row in rows),
        key=lambda item: _checklist_row_rank(item[1], item[0], question_terms),
    )
    caps = {
        "bottom-line support": 2,
        "main counterweight": 2,
        "subgroup exception": 2,
        "evidence-family limit": 2,
        "comparator/context limit": 2,
        "guideline/context limit": 1,
    }
    selected: list[tuple[str, dict[str, Any]]] = []
    role_counts: dict[str, int] = {}
    seen: set[str] = set()
    for role, row in ranked:
        if not _checklist_row_is_relevant(row, role, question_terms):
            continue
        if role_counts.get(role, 0) >= caps.get(role, 1):
            continue
        fingerprint = " ".join(_content_terms(str(row.get("claim", "")))[:10])
        if not fingerprint or fingerprint in seen:
            continue
        selected.append((role, row))
        role_counts[role] = role_counts.get(role, 0) + 1
        seen.add(fingerprint)
    return _ensure_minimum_role_coverage(selected, ranked, question_terms)


def _checklist_row_rank(row: dict[str, Any], role: str, question_terms: set[str]) -> tuple[int, int, int, str]:
    claim = str(row.get("claim", ""))
    claim_terms = set(_content_terms(claim))
    overlap = len(claim_terms & question_terms)
    quantity_bonus = 2 if _regex_tokens(claim, NUMBER_RE) else 0
    role_priority = {
        "bottom-line support": 0,
        "main counterweight": 1,
        "subgroup exception": 2,
        "evidence-family limit": 3,
        "comparator/context limit": 4,
        "guideline/context limit": 5,
    }.get(role, 6)
    return (-overlap - quantity_bonus, role_priority, len(claim), claim.lower())


def _checklist_row_is_relevant(row: dict[str, Any], role: str, question_terms: set[str]) -> bool:
    claim = str(row.get("claim", "")).lower()
    if role in {"evidence-family limit", "guideline/context limit"}:
        return True
    if role == "comparator/context limit" and any(term in claim for term in ("replacement", "substitution", "comparator")):
        return True
    claim_terms = set(_content_terms(claim))
    if not question_terms:
        return True
    return len(claim_terms & question_terms) >= 2


def _ensure_minimum_role_coverage(
    selected: list[tuple[str, dict[str, Any]]],
    ranked: list[tuple[str, dict[str, Any]]],
    question_terms: set[str],
) -> list[tuple[str, dict[str, Any]]]:
    present = {role for role, _ in selected}
    required_roles = ("bottom-line support", "main counterweight", "evidence-family limit")
    for required in required_roles:
        if required in present:
            continue
        for role, row in ranked:
            if role == required and _checklist_row_is_relevant(row, role, question_terms):
                selected.append((role, row))
                present.add(role)
                break
    return selected


def _checklist_role(row: dict[str, Any]) -> str:
    claim = str(row.get("claim", "")).lower()
    slot = str(row.get("slot", "")).lower()
    if any(term in claim for term in ("subgroup", "population", "individuals with", "people with", "participants with", "restricted to")):
        return "subgroup exception"
    if any(term in claim for term in ("guideline", "recommendation", "target recommendation")):
        return "guideline/context limit"
    if "counter" in slot or any(term in claim for term in ("higher risk", "increased risk", "increase", "elevat", "ratio")):
        return "main counterweight"
    if any(term in claim for term in ("rct", "randomized", "intervention", "observational", "residual confounding", "reverse causation")):
        return "evidence-family limit"
    if any(term in claim for term in ("replacement", "substitution", "comparator", "compared to", "versus")):
        return "comparator/context limit"
    if "support" in slot or any(term in claim for term in ("no association", "not associated", "lower", "neutral")):
        return "bottom-line support"
    return "bottom-line support"


def _answer_frame_checklist_lines(obligation_packet: dict[str, Any]) -> list[str]:
    answer_frame = obligation_packet.get("answer_frame", {}) if isinstance(obligation_packet.get("answer_frame"), dict) else {}
    mapping = (
        ("direct answer", "direct_answer"),
        ("near-term recommendation", "near_term_recommendation"),
        ("implementation condition", "implementation_condition"),
        ("important exception", "downside_or_exception"),
    )
    lines = []
    for label, key in mapping:
        value = _clean_claim_for_checklist(str(answer_frame.get(key, "")).strip())
        if value.lower().startswith("give a direct"):
            continue
        if value:
            lines.append(f"- Preserve {label}: {value}")
    return lines


def _gap_checklist_lines(obligation_packet: dict[str, Any]) -> list[str]:
    lines = []
    for gap in _string_list(obligation_packet.get("required_gaps")):
        cleaned = _clean_claim_for_checklist(gap)
        if cleaned:
            lines.append(f"- Preserve evidence-family limit: {cleaned}")
    return lines


def _clean_claim_for_checklist(claim: str) -> str:
    cleaned = re.sub(r"\s+", " ", claim).strip()
    cleaned = re.sub(r"\s+\[[^\]]+\]$", "", cleaned)
    cleaned = _trim_ellipsized_claim(cleaned)
    cleaned = _first_sentence_or_word_cap(cleaned, max_words=60)
    cleaned = _remove_trailing_incomplete_phrase(cleaned)
    return cleaned.rstrip(".") + "." if cleaned and not cleaned.endswith((".", "?", "!")) else cleaned


def _trim_ellipsized_claim(claim: str) -> str:
    if "..." not in claim:
        return claim
    before = claim.split("...", 1)[0].rstrip()
    sentence_end = _last_sentence_boundary(before)
    if sentence_end >= 40:
        return before[: sentence_end + 1].strip()
    return before.strip()


def _first_sentence_or_word_cap(claim: str, *, max_words: int) -> str:
    match = re.search(r"(?<=[.!?])\s+(?=[A-Z])", claim)
    if match and match.start() >= 40:
        claim = claim[: match.start() + 1].strip()
    words = claim.split()
    if len(words) <= max_words:
        return claim
    return " ".join(words[:max_words]).rstrip(",;:") + "."


def _last_sentence_boundary(text: str) -> int:
    candidates = [match.start() for match in re.finditer(r"[!?;]|(?<!\d)\.(?!\d)", text)]
    return max(candidates) if candidates else -1


def _remove_trailing_incomplete_phrase(claim: str) -> str:
    words = claim.rstrip(".").split()
    incomplete_tail_terms = {
        "with",
        "to",
        "by",
        "and",
        "or",
        "of",
        "for",
        "in",
        "as",
        "associated",
        "is",
        "are",
        "was",
        "were",
        "be",
        "being",
        "been",
    }
    while words and words[-1].lower().strip(".,;:") in incomplete_tail_terms:
        words.pop()
    return " ".join(words).rstrip(",;:") if words else claim


def _dedupe_checklist_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        terms = _content_terms(line.split(":", 1)[-1])
        key = " ".join(terms[:8])
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def _content_terms(text: str) -> list[str]:
    stop = {
        "about", "after", "again", "also", "among", "because", "before", "being", "between", "could",
        "current", "decision", "does", "from", "have", "into", "more", "should", "source", "that",
        "their", "there", "this", "those", "under", "when", "where", "which", "while", "with", "would",
    }
    terms: list[str] = []
    for raw in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower()):
        term = _normalize_term(raw)
        if term not in stop and term not in terms:
            terms.append(term)
    return terms


def _normalize_term(term: str) -> str:
    if term.endswith("ies") and len(term) > 4:
        return term[:-3] + "y"
    if term.endswith("s") and len(term) > 4:
        return term[:-1]
    return term


def _load_bearing_numbers(memo: str, contract: dict[str, Any]) -> set[str]:
    fields: list[str] = []
    for row in contract.get("required_evidence", []) if isinstance(contract.get("required_evidence"), list) else []:
        if isinstance(row, dict):
            fields.extend(str(row.get(key, "")) for key in ("claim", "source"))
            fields.extend(str(term) for term in row.get("anchor_terms", []) if isinstance(term, str))
    fields.extend(_string_list(contract.get("required_gaps")))
    fields.extend(_string_list(contract.get("practical_actions")))
    answer_frame = contract.get("answer_frame", {}) if isinstance(contract.get("answer_frame"), dict) else {}
    fields.extend(str(value) for value in answer_frame.values() if isinstance(value, str))
    for row in contract.get("required_cruxes", []) if isinstance(contract.get("required_cruxes"), list) else []:
        if isinstance(row, dict):
            fields.extend(str(value) for value in row.values() if isinstance(value, str))
    numbers: set[str] = set()
    for text in fields:
        numbers.update(_regex_tokens(text, NUMBER_RE))
    return numbers or _regex_tokens(memo, NUMBER_RE)


def _protected_line(markdown: str, prefix: str) -> str:
    prefix_lower = prefix.lower()
    for line in markdown.splitlines():
        if line.strip().lower().startswith(prefix_lower):
            return line.strip()
    return ""


def _restore_or_insert_protected_line(markdown: str, protected_line: str, *, marker: str) -> str:
    pattern = re.compile(rf"^\s*\*\*{re.escape(marker)}:\*\*.*$", flags=re.IGNORECASE | re.MULTILINE)
    if pattern.search(markdown):
        return pattern.sub(protected_line, markdown, count=1)
    decision_heading = re.search(r"^## Decision Brief\s*$", markdown, flags=re.MULTILINE)
    if decision_heading:
        return markdown[: decision_heading.end()] + "\n\n" + protected_line + markdown[decision_heading.end() :]
    return protected_line + "\n\n" + markdown


def _drop_duplicate_protected_payload_lines(markdown: str, protected_lines: list[str]) -> str:
    payloads = {_normalize_payload(_protected_payload(line)) for line in protected_lines if line}
    payloads.discard("")
    seen_payloads: set[str] = set()
    kept: list[str] = []
    for line in markdown.splitlines():
        payload = _protected_line_payload(line)
        if payload in payloads:
            if payload in seen_payloads:
                continue
            seen_payloads.add(payload)
            kept.append(line)
            continue
        kept.append(line)
    return "\n".join(kept)


def _protected_payload(line: str) -> str:
    return re.sub(r"^\*\*[^*]+:\*\*\s*", "", line.strip())


def _protected_line_payload(line: str) -> str:
    stripped = line.strip()
    if re.match(r"^\*\*[^*]+:\*\*", stripped):
        return _normalize_payload(_protected_payload(stripped))
    markdown_stripped = re.sub(r"[*_`]+", "", stripped)
    markdown_stripped = re.sub(r"^(decision question|confidence):\s*", "", markdown_stripped, flags=re.IGNORECASE)
    return _normalize_payload(markdown_stripped)


def _normalize_payload(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _source_block_from_memo(memo: str) -> str:
    match = re.search(r"^## Sources\s*\n(?P<body>.*)$", memo, flags=re.MULTILINE | re.DOTALL)
    return "## Sources\n" + match.group("body").strip() + "\n" if match else ""


def _restore_source_block(markdown: str, source_block: str) -> str:
    match = re.search(r"^#{2,3}\s+Sources\s*$", markdown, flags=re.MULTILINE)
    return markdown.rstrip() + "\n\n" + source_block if not match else markdown[: match.start()].rstrip() + "\n\n" + source_block


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


def _source_lines_from_memo(memo: str) -> list[str]:
    match = re.search(r"^## Sources\s*\n(?P<body>.*)$", memo, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return []
    lines = []
    for line in match.group("body").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("- "):
            lines.append(stripped.removeprefix("- ").strip())
    return [line for line in lines if line]


def _regex_tokens(text: str, pattern: re.Pattern[str]) -> set[str]:
    tokens: set[str] = set()
    for match in pattern.findall(text):
        value = " ".join(str(part) for part in match if str(part).strip()) if isinstance(match, tuple) else str(match)
        if value.strip():
            tokens.add(value.strip())
    return tokens


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _dedupe_issues(issues: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        text = str(issue).strip()
        if text and text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped
