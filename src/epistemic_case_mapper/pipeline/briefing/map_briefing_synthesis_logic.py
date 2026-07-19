from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)


def calibrated_bottom_line(decision_anchor: dict[str, Any]) -> str:
    answer = str(decision_anchor.get("bounded_answer") or decision_anchor.get("compact_answer") or "").strip()
    if not answer:
        return ""
    first, separator, remainder = answer.partition(". However")
    rationale = first.lower().split(" because ", 1)[-1] if " because " in first.lower() else ""
    surrogate_terms = (
        "acute",
        "biomarker",
        "function",
        "level",
        "marker",
        "mechanism",
        "ratio",
        "response",
        "single dose",
        "short-term",
    )
    if rationale and any(term in rationale for term in surrogate_terms):
        first = re.split(r"\s+because\s+", first, maxsplit=1, flags=re.IGNORECASE)[0].rstrip(" ,;:")
    answer = first + (f". However{remainder}" if separator else "")
    answer = re.sub(
        r"\b(?:high|higher)[- ]dose thresholds?\b",
        "study-specific higher-exposure findings",
        answer,
        flags=re.IGNORECASE,
    )
    answer = re.sub(r"\s*\(e\.g\.,[^)]*\)", "", answer, flags=re.IGNORECASE)
    parts = [answer.rstrip(". ")]
    confidence = str(decision_anchor.get("confidence") or "").strip()
    if confidence and "confidence" not in answer.lower():
        parts.append(f"Confidence: {confidence.rstrip('. ')}")
    if bounded_answer_required(decision_anchor) and not _bounded_answer_visible(answer):
        parts.append("This is a bounded read of the current evidence")
    return ". ".join(part for part in parts if part).strip() + "."


def bounded_answer_required(decision_anchor: dict[str, Any]) -> bool:
    answer = str(decision_anchor.get("bounded_answer") or "").lower()
    return bool(_string_list(decision_anchor.get("scope_boundaries"))) or any(
        term in answer for term in ("bound", "except", "however", "only when", "within")
    )


def source_grounded_quantity_atoms(contract: dict[str, Any]) -> list[dict[str, Any]]:
    atoms = []
    for atom in _list(contract.get("required_quantity_atoms")):
        if not isinstance(atom, dict):
            continue
        bundle = _dict(atom.get("assertion_bundle"))
        atoms.append(
            _drop_empty(
                {
                    "value": atom.get("value"),
                    "interpretation": atom.get("allowed_inference")
                    or bundle.get("allowed_inference")
                    or bundle.get("source_quote"),
                    "source_ids": atom.get("source_ids") or bundle.get("source_ids"),
                }
            )
        )
    return atoms


def controlling_source_excerpt(contract: dict[str, Any]) -> str:
    excerpts = [
        excerpt
        for row in _list(contract.get("source_evidence"))
        if isinstance(row, dict)
        for excerpt in _string_list(row.get("excerpts"))
        if excerpt
    ]
    selected = next((excerpt for excerpt in excerpts if not excerpt.rstrip().endswith("...")), excerpts[0] if excerpts else "")
    for value in _dict(contract.get("claim_context")).values():
        match = re.search(r"\b([^();]{3,80}?)\s*\(([A-Z]{2,8})\)", str(value or ""))
        if match:
            expansion = match.group(1).strip().lower()
            consumption = re.fullmatch(r"more\s+(.+?)\s+consumption", expansion)
            if consumption:
                expansion = f"higher {consumption.group(1)}-consumption"
            selected = re.sub(
                rf"\b{re.escape(match.group(2))}\s+group\b",
                f"{expansion} group",
                selected,
            )
    selected = selected[:1].upper() + selected[1:]
    selected = re.sub(r"^(The odds\b.*?)\bwas\b", r"\1were", selected, count=1, flags=re.IGNORECASE)
    return re.sub(r"\bI\s*2\s*=", "I² =", selected)


def build_synthesis_constraints(
    contracts: list[dict[str, Any]],
    decision_anchor: dict[str, Any],
    *,
    section_id: str = "",
) -> dict[str, Any]:
    texts = [
        " ".join(
            str(value or "")
            for value in (
                contract.get("claim"),
                contract.get("population_scope"),
                contract.get("required_caveat"),
                " ".join(
                    str(row.get("value") or "")
                    for row in _list(contract.get("required_quantity_atoms"))
                    if isinstance(row, dict)
                ),
            )
        )
        for contract in contracts
        if isinstance(contract, dict)
    ]
    combined = " ".join(texts)
    exposure_surfaces = _dedupe(
        [
            match.group(0)
            for match in re.finditer(
                r"(?:[<>≤≥]\s*)?\d+(?:\.\d+)?\s*(?:times?\s*)?(?:[a-z]+\s*)?(?:/|per\s+)(?:day|week|month)\b",
                combined,
                flags=re.IGNORECASE,
            )
        ]
    )
    positive = any(
        re.search(r"\b(?:benefit|favorable|lower|reduc|no adverse|not associated with (?:an? )?(?:increase|higher))", text, re.IGNORECASE)
        for text in texts
    )
    negative = any(
        re.search(r"\b(?:adverse|harm|higher|increase|mortality|risk signal)", text, re.IGNORECASE)
        for text in texts
    )
    surrogate_ids = [
        str(contract.get("evidence_id") or "")
        for contract in contracts
        if isinstance(contract, dict)
        and re.search(
            r"\b(?:acute|biomarker|function|level|marker|mechanism|pathway|ratio|response|single dose)\b",
            str(contract.get("claim") or ""),
            re.IGNORECASE,
        )
    ]
    observational_ids = [
        str(contract.get("evidence_id") or "")
        for contract in contracts
        if isinstance(contract, dict)
        and (
            "observational evidence" in _string_list(contract.get("must_qualify_with"))
            or re.search(
                r"\b(?:associated|multivariable-adjusted|cohort)\b",
                str(contract.get("claim") or ""),
                re.IGNORECASE,
            )
        )
    ]
    randomized_ids = [
        str(contract.get("evidence_id") or "")
        for contract in contracts
        if isinstance(contract, dict)
        and re.search(
            r"\b(?:RCTs?|randomized|systematic review|meta-analysis)\b",
            str(contract.get("claim") or ""),
            re.IGNORECASE,
        )
    ]
    intermediate_ids = [
        str(contract.get("evidence_id") or "")
        for contract in contracts
        if isinstance(contract, dict)
        and re.search(
            r"\b(?:biomarker|concentration|level|marker|profile|ratio|response)\b",
            str(contract.get("claim") or ""),
            re.IGNORECASE,
        )
    ]
    decision_effect = ""
    if section_id == "answer_evidence" and (observational_ids or intermediate_ids):
        decision_effect = (
            "Because the supporting evidence is observational or focused on intermediate markers, it supports the bounded default but does not justify a stronger favorable classification."
        )
    elif section_id == "counterweights" and contracts:
        confidence = str(decision_anchor.get("confidence") or "bounded").lower()
        decision_effect = (
            "Because the counterevidence varies by design, exposure, and endpoint and does not point in one consistent direction, "
            f"it bounds the default and supports {confidence} confidence without establishing one uniform adverse effect."
        )
    return _drop_empty(
        {
            "confidence_to_show": decision_anchor.get("confidence"),
            "bounded_answer_required": bounded_answer_required(decision_anchor),
            "opposing_signals_require_reconciliation": positive and negative,
            "study_specific_exposure_surfaces": exposure_surfaces[:12],
            "exposure_comparability_rule": (
                "Do not combine these study-specific exposure surfaces into one universal threshold; explain population, endpoint, or design differences."
                if len(exposure_surfaces) > 1
                else ""
            ),
            "surrogate_or_mechanistic_evidence_ids": _dedupe(surrogate_ids),
            "observational_evidence_ids": _dedupe(observational_ids),
            "randomized_or_synthesis_evidence_ids": _dedupe(randomized_ids),
            "intermediate_endpoint_evidence_ids": _dedupe(intermediate_ids),
            "required_decision_effect_sentence": decision_effect,
            "surrogate_rule": (
                "These items may calibrate or explain the answer but cannot carry a broader clinical or long-term conclusion by themselves."
                if surrogate_ids
                else ""
            ),
        }
    )


def section_synthesis_logic_issues(
    markdown: str,
    *,
    section_id: str,
    contracts: list[dict[str, Any]],
    packet: dict[str, Any],
) -> list[str]:
    text = str(markdown or "")
    normalized = text.lower()
    constraints = _dict(packet.get("synthesis_constraints"))
    issues: list[str] = []
    reconciliation_markers = (
        "cannot be treated as",
        "differences may reflect",
        "differ by",
        "not directly comparable",
        "varies by",
    )
    if (
        section_id == "counterweights"
        and constraints.get("opposing_signals_require_reconciliation")
        and not any(marker in normalized for marker in reconciliation_markers)
    ):
        issues.append("missing_conflict_reconciliation")
    exposure_surfaces = _string_list(constraints.get("study_specific_exposure_surfaces"))
    if (
        len(exposure_surfaces) > 1
        and re.search(r"\b(?:dose|exposure|consumption)\s+thresholds?\b", normalized)
        and not any(marker in normalized for marker in ("not directly comparable", "study-specific", "no single", "cannot be combined"))
    ):
        issues.append("unreconciled_dose_thresholds")
    strength_surface = re.sub(
        r"\b(?:(?:do|does|did|can|could|would)\s+not|cannot|rather\s+than)\s+establish\w*\b",
        "",
        normalized,
    )
    if (
        constraints.get("surrogate_or_mechanistic_evidence_ids")
        and re.search(r"\b(?:robust body|establish(?:es|ed)?|proves?|demonstrat(?:e|es|ed) that)\b", strength_surface)
    ):
        issues.append("unsupported_strength_from_indirect_evidence")
    issues.extend(_unsupported_temporal_qualifier_issues(text, contracts))
    return _dedupe(issues)


def repair_section_synthesis_logic(
    markdown: str,
    *,
    section_id: str,
    contracts: list[dict[str, Any]],
    packet: dict[str, Any],
) -> str:
    text = str(markdown or "")
    constraints = _dict(packet.get("synthesis_constraints"))
    text = re.sub(
        r"\s+because\s+(?:an?\s+)?(?:single dose|acute|short[- ]term|biomarker|mechanistic)\b[^.]*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if constraints.get("surrogate_or_mechanistic_evidence_ids"):
        text = re.sub(r"\brobust body of evidence\b", "multiple lines of evidence", text, flags=re.IGNORECASE)
    for issue in _unsupported_temporal_qualifier_issues(text, contracts):
        if issue.endswith(":long_term"):
            text = re.sub(r"\s*\b(?:long[- ]term|longer[- ]term|over longer periods?)\b", "", text, flags=re.IGNORECASE)
        elif issue.endswith(":short_term"):
            text = re.sub(r"\s*\b(?:short[- ]term|acute|single dose)\b", "", text, flags=re.IGNORECASE)
    exposure_surfaces = _string_list(constraints.get("study_specific_exposure_surfaces"))
    if len(exposure_surfaces) > 1:
        text = re.sub(
            r"\b(?:high|higher)[- ](?:dose|consumption|exposure)\s+thresholds?\b",
            "study-specific higher-exposure findings",
            text,
            flags=re.IGNORECASE,
        )
    additions: list[str] = []
    normalized = text.lower()
    decision_effect = str(constraints.get("required_decision_effect_sentence") or "").strip()
    if decision_effect and decision_effect.lower() not in normalized:
        additions.append(decision_effect)
    if section_id == "counterweights" and constraints.get("opposing_signals_require_reconciliation") and not any(
        marker in normalized
        for marker in ("cannot be treated as", "differences may reflect", "differ by", "not directly comparable", "varies by")
    ):
        additions.append(
            "The opposing findings differ by population, endpoint, and study design, so they bound the answer rather than establish one uniform effect."
        )
    if section_id == "counterweights" and len(exposure_surfaces) > 1 and not any(
        marker in normalized for marker in ("not directly comparable", "no single", "cannot be combined")
    ):
        additions.append(
            "The reported exposure ranges are study-specific and not directly comparable, so they do not establish a single threshold."
        )
    if additions:
        text = text.rstrip() + "\n\n" + " ".join(additions) + "\n"
    return text


def strip_redundant_post_tag_quantities(markdown: str, contracts: list[dict[str, Any]]) -> str:
    text = str(markdown or "")
    for contract in contracts:
        evidence_id = str(contract.get("evidence_id") or "").strip()
        for quantity in _list(contract.get("required_quantity_atoms")):
            value = str(_dict(quantity).get("value") or "").strip()
            if not evidence_id or not value:
                continue
            pattern = re.compile(
                rf"(?P<prefix>[^\n]{{0,1200}}\{{E:{re.escape(evidence_id)}\}})\s+{re.escape(value)}"
            )

            def remove_if_redundant(match: re.Match[str]) -> str:
                numbers = re.findall(r"\d+(?:\.\d+)?", value)
                return match.group("prefix") if numbers and all(number in match.group("prefix") for number in numbers) else match.group(0)

            text = pattern.sub(remove_if_redundant, text)
    return text


def _unsupported_temporal_qualifier_issues(
    markdown: str,
    contracts: list[dict[str, Any]],
) -> list[str]:
    qualifier_patterns = {
        "long_term": r"\b(?:long[- ]term|longer[- ]term|over longer periods?)\b",
        "short_term": r"\b(?:short[- ]term|acute|single dose)\b",
    }
    issues: list[str] = []
    for contract in contracts:
        evidence_id = str(contract.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        evidence_text = " ".join(
            excerpt
            for row in _list(contract.get("source_evidence"))
            if isinstance(row, dict)
            for excerpt in _string_list(row.get("excerpts"))
        ).lower()
        if not evidence_text:
            continue
        for match in re.finditer(rf"\{{(?:E:)?{re.escape(evidence_id)}\}}", markdown):
            sentence = _sentence_for_logic_check(markdown, match.start())
            for label, pattern in qualifier_patterns.items():
                if re.search(pattern, sentence, re.IGNORECASE) and not re.search(pattern, evidence_text, re.IGNORECASE):
                    issues.append(f"unsupported_temporal_qualifier:{evidence_id}:{label}")
    return _dedupe(issues)


def _sentence_for_logic_check(text: str, index: int) -> str:
    left = max(text.rfind(mark, 0, index) for mark in (". ", "? ", "! ", "\n"))
    ends = [position for mark in (". ", "? ", "! ", "\n") if (position := text.find(mark, index)) >= 0]
    right = min(ends) if ends else len(text)
    return text[left + 1 : right].strip()


def _bounded_answer_visible(answer: str) -> bool:
    text = str(answer or "").lower()
    return any(term in text for term in ("bounded read", "current evidence", "within the stated scope"))


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
