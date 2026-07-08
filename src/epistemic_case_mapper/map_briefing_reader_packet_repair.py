from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_packet_memo import build_reader_facing_packet
from epistemic_case_mapper.model_backends import run_model_backend


def build_reader_packet_retention_report(memo: str, reader_packet: dict[str, Any] | None) -> dict[str, Any]:
    """Check whether a memo retained source-grounded reader-packet evidence.

    This is intentionally narrower than the internal packet retention audit. It
    asks whether the prose preserved the clean evidence cards that were actually
    sent to the synthesis model, especially cards carrying numbers.
    """

    packet = reader_packet if isinstance(reader_packet, dict) else {}
    required_cards = _required_cards(packet)
    card_statuses = [_card_status(memo, card) for card in required_cards]
    issues = [status for status in card_statuses if not status["retained"]]
    return {
        "schema_id": "reader_packet_retention_report_v1",
        "status": "ready" if not issues else "warning",
        "required_card_count": len(required_cards),
        "retained_card_count": sum(1 for status in card_statuses if status["retained"]),
        "missing_card_count": len(issues),
        "missing_number_count": sum(len(status.get("missing_numbers", [])) for status in issues),
        "card_statuses": card_statuses,
        "issues": issues,
    }


def run_reader_packet_retention_repair(
    memo: str,
    packet: dict[str, Any] | None,
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    reader_packet = build_reader_facing_packet(packet if isinstance(packet, dict) else {})
    before = build_reader_packet_retention_report(memo, reader_packet)
    prompt = build_reader_packet_retention_repair_prompt(memo, reader_packet, before)
    report: dict[str, Any] = {
        "schema_id": "reader_packet_retention_repair_report_v1",
        "status": "not_needed" if not before["issues"] else "not_run",
        "accepted": False,
        "initial_missing_card_count": before["missing_card_count"],
        "initial_missing_number_count": before["missing_number_count"],
        "initial_retention_report": before,
        "issues": [],
    }
    if not before["issues"]:
        return {"memo": memo, "prompt": "", "raw": "", "report": report}
    if backend.strip() == "prompt":
        report.update({"status": "skipped_prompt_backend", "issues": ["reader-packet repair backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    if result.prompt_only:
        report.update({"status": "prompt_backend_kept_original", "issues": ["reader-packet repair backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    candidate = _extract_markdown(raw)
    if not candidate:
        report.update({"status": "empty_response_kept_original", "issues": ["reader-packet repair returned empty markdown"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    after = build_reader_packet_retention_report(candidate, reader_packet)
    regressions = _retention_regressions(before, after)
    accepted = _retention_improved(before, after) and not regressions and not _has_internal_markers(candidate)
    accepted_via = "model"
    deterministic_report: dict[str, Any] = {}
    if not accepted:
        deterministic_candidate = _deterministic_reader_packet_repair(memo, before)
        deterministic_after = build_reader_packet_retention_report(deterministic_candidate, reader_packet)
        deterministic_regressions = _retention_regressions(before, deterministic_after)
        deterministic_accepted = (
            deterministic_candidate != memo
            and _retention_improved(before, deterministic_after)
            and not deterministic_regressions
            and not _has_internal_markers(deterministic_candidate)
        )
        deterministic_report = {
            "attempted": deterministic_candidate != memo,
            "accepted": deterministic_accepted,
            "final_missing_card_count": deterministic_after["missing_card_count"],
            "final_missing_number_count": deterministic_after["missing_number_count"],
            "retention_regressions": deterministic_regressions,
        }
        if deterministic_accepted:
            candidate = deterministic_candidate
            after = deterministic_after
            regressions = []
            accepted = True
            accepted_via = "deterministic_fallback"
    report.update(
        {
            "status": "accepted" if accepted else "no_reader_packet_retention_improvement_kept_original",
            "accepted": accepted,
            "accepted_via": accepted_via if accepted else "",
            "final_missing_card_count": after["missing_card_count"],
            "final_missing_number_count": after["missing_number_count"],
            "final_retained_card_count": after["retained_card_count"],
            "final_retention_report": after,
            "retention_regressions": regressions,
            "deterministic_fallback": deterministic_report,
            "issues": [] if accepted else ["reader-packet repair did not improve retention without leaking internal markers or regressions"],
        }
    )
    return {"memo": candidate if accepted else memo, "prompt": prompt, "raw": raw, "report": report}


def build_reader_packet_retention_repair_prompt(
    memo: str,
    reader_packet: dict[str, Any],
    retention_report: dict[str, Any],
) -> str:
    repair_packet = _repair_packet(reader_packet, retention_report)
    protected = _protected_surface_tokens(memo)
    return (
        "You are repairing a polished decision memo after a reader-packet retention audit found dropped key evidence.\n"
        "Use only the current memo and targeted repair packet below.\n\n"
        "Rules:\n"
        "- Return the full revised memo in Markdown, not JSON.\n"
        "- Make additive edits only: preserve the current memo's wording wherever possible and insert the smallest necessary sentence or clause in the most relevant existing section.\n"
        "- Do not remove, rewrite away, or paraphrase existing numbers or bracketed source labels from the current memo.\n"
        "- Preserve exact numbers and bracketed source labels from the repair packet.\n"
        "- Do not add new sources, examples, populations, causal claims, or recommendations beyond the repair packet.\n"
        "- Do not mention packet schema, validation, repair, or internal pipeline status.\n"
        "- Preserve the decision question and Sources section if present.\n"
        "- If an issue cannot be fixed directly from the repair packet, leave it unresolved rather than guessing.\n\n"
        "Protected existing numbers and source labels that must remain present:\n"
        f"{json.dumps(protected, indent=2, ensure_ascii=False)}\n\n"
        "Targeted repair packet:\n"
        f"{json.dumps(repair_packet, indent=2, ensure_ascii=False)}\n\n"
        "Current memo:\n"
        f"{memo.strip()}\n"
    )


def _required_cards(reader_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in ("quantitative_anchors", "evidence_cards", "counterweight_cards"):
        for index, card in enumerate(reader_packet.get(section, []) if isinstance(reader_packet.get(section), list) else []):
            if not isinstance(card, dict):
                continue
            role = str(card.get("role") or "").strip()
            if section == "counterweight_cards" and role != "counterweight":
                continue
            statement = str(card.get("statement") or "").strip()
            source = str(card.get("source") or "").strip()
            numbers = _required_numbers_for_card(card, statement=statement)
            if section != "quantitative_anchors" and not numbers:
                continue
            if not statement or not source:
                continue
            rows.append(
                {
                    "card_id": f"{section}_{index + 1}",
                    "section": section,
                    "role": role,
                    "statement": statement,
                    "source": source,
                    "numbers": _dedupe(numbers),
                    "interpretation": card.get("interpretation"),
                }
            )
    return _dedupe_cards(rows)[:16]


def _required_numbers_for_card(card: dict[str, Any], *, statement: str) -> list[str]:
    quantities = _string_list(card.get("quantities"))
    if quantities:
        return _dedupe(_number_tokens(" ".join(quantities[:3])))
    return _dedupe(_number_tokens(statement))


def _card_status(memo: str, card: dict[str, Any]) -> dict[str, Any]:
    statement = str(card.get("statement") or "").strip()
    source = str(card.get("source") or "").strip()
    numbers = _string_list(card.get("numbers"))
    missing_numbers = [number for number in numbers if not _contains_text(memo, number)]
    source_retained = _contains_text(memo, source)
    statement_retained = _mentions_enough_content_terms(memo, statement, minimum=4)
    retained = source_retained and statement_retained and not missing_numbers
    return {
        **card,
        "retained": retained,
        "source_retained": source_retained,
        "statement_retained": statement_retained,
        "missing_numbers": missing_numbers,
    }


def _repair_packet(reader_packet: dict[str, Any], retention_report: dict[str, Any]) -> dict[str, Any]:
    issues = [issue for issue in retention_report.get("issues", []) if isinstance(issue, dict)]
    return {
        "schema_id": "reader_packet_retention_repair_packet_v1",
        "decision_question": reader_packet.get("decision_question"),
        "missing_cards": [
            {
                "card_id": issue.get("card_id"),
                "preferred_section": _preferred_section(issue),
                "statement": issue.get("statement"),
                "source": issue.get("source"),
                "numbers": issue.get("numbers", []),
                "missing_numbers": issue.get("missing_numbers", []),
                "interpretation": issue.get("interpretation"),
            }
            for issue in issues[:8]
        ],
    }


def _protected_surface_tokens(memo: str) -> dict[str, list[str]]:
    return {
        "numbers": _dedupe(_number_tokens(memo)),
        "source_labels": _dedupe(re.findall(r"\[([^\]]+)\]", memo)),
    }


def _preferred_section(issue: dict[str, Any]) -> str:
    section = str(issue.get("section") or "")
    if section == "counterweight_cards":
        return "What Limits the Inference"
    if section == "decision_cruxes":
        return "Decision Cruxes"
    return "What the Evidence Supports"


def _retention_improved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if int(after.get("missing_number_count", 0)) < int(before.get("missing_number_count", 0)):
        return True
    if int(after.get("missing_card_count", 0)) < int(before.get("missing_card_count", 0)):
        return True
    return int(after.get("retained_card_count", 0)) > int(before.get("retained_card_count", 0))


def _retention_regressions(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    before_rows = {
        str(row.get("card_id") or ""): row
        for row in before.get("card_statuses", [])
        if isinstance(row, dict) and str(row.get("card_id") or "")
    }
    after_rows = {
        str(row.get("card_id") or ""): row
        for row in after.get("card_statuses", [])
        if isinstance(row, dict) and str(row.get("card_id") or "")
    }
    regressions: list[dict[str, Any]] = []
    for card_id, before_row in before_rows.items():
        after_row = after_rows.get(card_id)
        if not after_row:
            continue
        before_missing = set(_string_list(before_row.get("missing_numbers")))
        after_missing = set(_string_list(after_row.get("missing_numbers")))
        newly_missing = sorted(after_missing - before_missing)
        if newly_missing:
            regressions.append({"card_id": card_id, "issue_type": "newly_missing_numbers", "numbers": newly_missing})
        if before_row.get("source_retained") and not after_row.get("source_retained"):
            regressions.append({"card_id": card_id, "issue_type": "source_no_longer_retained"})
        if before_row.get("statement_retained") and not after_row.get("statement_retained"):
            regressions.append({"card_id": card_id, "issue_type": "statement_no_longer_retained"})
        if before_row.get("retained") and not after_row.get("retained"):
            regressions.append({"card_id": card_id, "issue_type": "card_no_longer_retained"})
    return regressions


def _deterministic_reader_packet_repair(memo: str, retention_report: dict[str, Any]) -> str:
    issues = _dedup_repair_issues([issue for issue in retention_report.get("issues", []) if isinstance(issue, dict)])
    if not issues:
        return memo
    repaired = memo
    for issue in issues[:4]:
        sentence = _repair_sentence(issue)
        if not sentence or sentence in repaired:
            continue
        repaired = _insert_sentence_in_section(repaired, _preferred_section(issue), sentence)
    return _clean_markdown(repaired)


def _repair_sentence(issue: dict[str, Any]) -> str:
    statement = str(issue.get("statement") or "").strip()
    source = str(issue.get("source") or "").strip()
    if not statement or not source:
        return ""
    text = statement.rstrip(".")
    numbers = _string_list(issue.get("numbers"))
    if numbers and not all(_contains_text(text, number) for number in numbers):
        text += f". Key quantities: {', '.join(numbers[:8])}"
    if source not in text:
        text += f" [{source}]"
    return f"- {text}."


def _dedup_repair_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_number_sets: list[tuple[str, set[str]]] = []
    role_rank = {"quantitative_anchors": 0, "counterweight_cards": 1, "evidence_cards": 2, "decision_cruxes": 3}
    ranked = sorted(issues, key=lambda issue: (role_rank.get(str(issue.get("section")), 9), -len(_string_list(issue.get("missing_numbers")))))
    for issue in ranked:
        source = str(issue.get("source") or "")
        numbers = set(_string_list(issue.get("numbers")))
        if numbers and any(source == seen_source and numbers <= seen_numbers for seen_source, seen_numbers in seen_number_sets):
            continue
        selected.append(issue)
        if numbers:
            seen_number_sets.append((source, numbers))
    return selected


def _insert_sentence_in_section(memo: str, section_title: str, sentence: str) -> str:
    heading_pattern = re.compile(rf"^##\s+{re.escape(section_title)}\s*$", flags=re.MULTILINE)
    match = heading_pattern.search(memo)
    if not match:
        insert = f"\n\n## {section_title}\n{sentence}\n"
        sources_match = re.search(r"^##\s+Sources\s*$", memo, flags=re.MULTILINE)
        if sources_match:
            return memo[: sources_match.start()].rstrip() + insert + "\n" + memo[sources_match.start() :].lstrip()
        return memo.rstrip() + insert
    next_heading = re.search(r"^##\s+", memo[match.end() :], flags=re.MULTILINE)
    insert_at = match.end() + next_heading.start() if next_heading else len(memo)
    prefix = memo[:insert_at].rstrip()
    suffix = memo[insert_at:].lstrip("\n")
    return prefix + "\n\n" + sentence + ("\n\n" + suffix if suffix else "\n")


def _has_internal_markers(text: str) -> bool:
    markers = ("bundle_", "retain_", "required_terms", "synthesis_suppressed", "Appendix-only extraction", "Map quality status")
    return any(marker in text for marker in markers)


def _extract_markdown(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    if cleaned.startswith("{") or cleaned.startswith("["):
        return ""
    return _clean_markdown(cleaned)


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    if not needle:
        return True
    return needle.lower() in text.lower()


def _mentions_enough_content_terms(text: str, statement: str, *, minimum: int) -> bool:
    terms = _content_terms(statement)
    if not terms:
        return True
    required = min(minimum, len(terms))
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered) >= required


def _content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "after",
        "again",
        "also",
        "because",
        "before",
        "between",
        "could",
        "current",
        "decision",
        "does",
        "from",
        "have",
        "into",
        "more",
        "should",
        "source",
        "that",
        "their",
        "there",
        "this",
        "those",
        "under",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
    }
    terms = []
    for term in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower()):
        if term not in stop and term not in terms:
            terms.append(term)
    return terms


def _number_tokens(text: str) -> list[str]:
    return re.findall(r"\$?\d+(?:\.\d+)?%?", text)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = str(item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(str(item).strip())
    return result


def _dedupe_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = re.sub(r"[^a-z0-9]+", " ", str(row.get("statement", "")).lower()).strip()[:140]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _clean_markdown(text: str) -> str:
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
