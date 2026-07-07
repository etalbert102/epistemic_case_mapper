from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from epistemic_case_mapper.classical_ml import (
    relation_edge_weight,
    tfidf_near_duplicate_pairs,
    weighted_pagerank,
)
from epistemic_case_mapper.config_profiles import (
    DEFAULT_PROFILE_ID,
    infer_profile_id_from_text,
    profile_vocabulary,
)
from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.evidence_drift_validation import evidence_drift_issues
from epistemic_case_mapper.map_briefing_spine_memo_validation import spine_memo_validation_issues
from epistemic_case_mapper.model_backends import run_model_backend

def _lint_reader_overstatements(text: str, active_lints: set[str]) -> str:
    cleaned = text
    if "null_evidence_not_benefit" in active_lints:
        cleaned = re.sub(
            r"\bneutral to potentially beneficial\b",
            "low-concern under the stated conditions",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\bpotentially beneficial\b",
            "not shown to be harmful in the mapped evidence",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\bmay even show an inverse association\b",
            "has some scope-bound signals in the mapped evidence",
            cleaned,
            flags=re.IGNORECASE,
        )
    if "confidence_language" in active_lints:
        replacements = {
            r"\bclearly\b": "on the mapped evidence",
            r"\bproven\b": "supported",
            r"\bsettled\b": "best read",
            r"\bno risk\b": "no clear risk in the mapped evidence",
            r"\bsafe\b": "not shown to be harmful in the mapped evidence",
            r"\bsafely\b": "with no adverse signal in the mapped evidence",
        }
        for pattern, replacement in replacements.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    if "surrogate_to_hard_outcome" in active_lints:
        cleaned = re.sub(
            r"\b(no adverse cardiometabolic effects)\b",
            r"no adverse cardiometabolic biomarker effects",
            cleaned,
            flags=re.IGNORECASE,
        )
    return cleaned

def _clean_reader_relation_placeholders(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"\bthough this stance is not best read and faces\b",
        "while this stance faces",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b[Cc]laim A\b", "One mapped claim", cleaned)
    cleaned = re.sub(r"\b[Cc]laim B\b", "another mapped claim", cleaned)
    cleaned = re.sub(r"\b[Cc]laim ([A-Z])\b", r"one mapped claim", cleaned)
    cleaned = re.sub(r"\b[Oo]ne source-grounded finding\b", "One line of evidence", cleaned)
    cleaned = re.sub(r"\b[Aa]nother source-grounded finding\b", "another line of evidence", cleaned)
    cleaned = re.sub(r"\b[Tt]he source-grounded finding\b", "that line of evidence", cleaned)
    cleaned = re.sub(r"\bsource-grounded finding\b", "line of evidence", cleaned)
    cleaned = re.sub(r"\b[Oo]ne finding\b", "One line of evidence", cleaned)
    cleaned = re.sub(r"\b[Aa]nother finding\b", "another line of evidence", cleaned)
    cleaned = re.sub(r"\b[Tt]he finding\b", "that line of evidence", cleaned)
    cleaned = re.sub(r"\b[Oo]ne mapped claim\b", "One line of evidence", cleaned)
    cleaned = re.sub(r"\b[Aa]nother mapped claim\b", "another line of evidence", cleaned)
    cleaned = re.sub(r"\b[Tt]he mapped claim\b", "that line of evidence", cleaned)
    cleaned = re.sub(r"\bmapped claim\b", "line of evidence", cleaned)
    cleaned = re.sub(r"\b[Bb]oth claims\b", "Both lines of evidence", cleaned)
    return cleaned

def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        compact = re.sub(r"\s+", " ", item).strip()
        key = compact.lower()
        if compact and key not in seen:
            seen.add(key)
            result.append(compact)
    return result

def _dedupe_dicts(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result

def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]

def _is_substantive_evidence_statement(text: str, source_names: set[str]) -> bool:
    stripped = re.sub(r"\s+", " ", text).strip(" -.;")
    if not stripped:
        return False
    if stripped in source_names:
        return False
    without_parenthetical_sources = stripped
    for source_name in source_names:
        without_parenthetical_sources = without_parenthetical_sources.replace(f"({source_name})", "")
    if without_parenthetical_sources.strip(" -.;") in source_names:
        return False
    terms = _content_terms(without_parenthetical_sources)
    if len(terms) < 4:
        return False
    return any(
        marker in without_parenthetical_sources.lower()
        for marker in (
            " is ",
            " are ",
            " can ",
            " cannot ",
            " should ",
            " must ",
            " reduce",
            " lower",
            " increase",
            " depend",
            " require",
            " observed",
            " tested",
            " found",
            " showed",
        )
    )

def _similar_text_exists(items: list[str], candidate: str) -> bool:
    candidate_terms = set(_content_terms(candidate))
    if not candidate_terms:
        return False
    for item in items:
        item_terms = set(_content_terms(item))
        if not item_terms:
            continue
        overlap = len(candidate_terms & item_terms) / min(len(candidate_terms), len(item_terms))
        if overlap >= 0.7:
            return True
    return False

def _content_terms(text: str) -> list[str]:
    terms = []
    stopwords = {
        "about",
        "after",
        "also",
        "claim",
        "claims",
        "does",
        "evidence",
        "from",
        "have",
        "into",
        "more",
        "source",
        "than",
        "that",
        "this",
        "with",
    }
    for term in re.findall(r"[a-z][a-z0-9\-]{3,}", text.lower()):
        if term in stopwords:
            continue
        if term not in terms:
            terms.append(term)
    return terms

def _confidence_label(value: Any) -> str:
    if not isinstance(value, str):
        return "not specified"
    normalized = value.strip().lower()
    return normalized if normalized in CONFIDENCE_ORDER else value.strip() or "not specified"

def _looks_like_structured_attempt(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("```json") or '"decision_brief"' in stripped[:500]

def _replace_confidence_line(markdown: str, confidence: str) -> str:
    if "**Confidence:**" in markdown:
        return re.sub(r"\*\*Confidence:\*\*\s*[^\n]+", f"**Confidence:** {confidence}", markdown)
    return markdown

def _ensure_confidence_visible(markdown: str, confidence: str) -> str:
    if "**Confidence:**" in markdown:
        return _replace_confidence_line(markdown, confidence)
    return markdown.rstrip() + f"\n\n**Confidence:** {confidence}\n"

def _normalize_reader_punctuation(text: str) -> str:
    cleaned = re.sub(r"\.{4,}", "...", text)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned

def validate_briefing_against_scaffold(
    rendered: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
) -> dict[str, Any]:
    sufficiency_report = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    obligations = [item for item in sufficiency_report.get("output_obligations", []) if isinstance(item, dict)]
    issues: list[dict[str, str]] = []
    satisfied: list[str] = []
    for obligation in obligations:
        obligation_id = str(obligation.get("obligation_id", ""))
        kind = str(obligation.get("kind", ""))
        if kind == "include_present_slot":
            values = _string_list(obligation.get("candidate_values"))
            if _rendered_mentions_any_slot_value(rendered, values):
                satisfied.append(obligation_id)
            else:
                issues.append(
                    {
                        "severity": "warning",
                        "issue_type": "missing_present_slot_in_briefing",
                        "message": f"The briefing does not visibly include a mapped {_slot_label(str(obligation.get('slot', '')))}.",
                    }
                )
        elif kind == "acknowledge_missing_slot":
            slot = str(obligation.get("slot", ""))
            if _rendered_acknowledges_missing_slot(rendered, slot):
                satisfied.append(obligation_id)
            else:
                issues.append(
                    {
                        "severity": "warning",
                        "issue_type": "missing_gap_acknowledgement",
                        "message": f"The briefing does not acknowledge the missing {_slot_label(slot)}.",
                    }
                )
        elif kind == "acknowledge_missing_family":
            family = str(obligation.get("evidence_family", ""))
            if _rendered_acknowledges_missing_family(rendered, family):
                satisfied.append(obligation_id)
            else:
                issues.append(
                    {
                        "severity": "warning",
                        "issue_type": "missing_family_gap_acknowledgement",
                        "message": f"The briefing does not acknowledge absent {family.replace('_', ' ')} evidence.",
                    }
                )
    concept_packets = scaffold.get("concept_evidence_packets", {}) if isinstance(scaffold.get("concept_evidence_packets"), dict) else {}
    for packet in concept_packets.get("packets", []) if isinstance(concept_packets.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        terms = _string_list(packet.get("must_surface_terms"))
        if not terms:
            continue
        if _rendered_mentions_any_surface_term(rendered, terms):
            satisfied.append(f"concept_{packet.get('concept')}")
        else:
            issues.append(
                {
                    "severity": "warning",
                    "issue_type": "missing_concept_packet_surface_term",
                    "message": f"The briefing does not visibly surface retained {packet.get('label', packet.get('concept', 'concept'))} evidence.",
                }
            )
    evidence_ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    if isinstance(evidence_ledger, dict):
        issues.extend(_briefing_evidence_fit_issues(rendered, evidence_ledger, candidate_map))
    for issue in evidence_drift_issues(
        _main_memo_reliance_text(rendered),
        {"scaffold": scaffold, "candidate_map": candidate_map},
        subject="briefing",
    ):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "possible_evidence_drift",
                "message": issue,
            }
        )
    if _has_reader_unfriendly_identifier(rendered):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "reader_unfriendly_map_identifier",
                "message": "The briefing appears to contain raw claim/relation identifiers or generic claim labels.",
            }
        )
    if _briefing_overclaims_against_scaffold(rendered, scaffold):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "possible_overclaim",
                "message": "The briefing uses stronger benefit/safety language than the scaffold appears to support.",
            }
        )
    issues.extend(spine_memo_validation_issues(rendered, scaffold))
    if re.search(r"\bcurrent source packet does not establish\b", _main_memo_reliance_text(rendered), flags=re.IGNORECASE):
        issues.append(
            {
                "severity": "warning",
                "issue_type": "gap_boilerplate_in_main_analysis",
                "message": "Gap boilerplate appears in the main answer instead of being contained in the limits section.",
            }
        )
    if "## Evidence Roles" not in rendered:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "missing_evidence_roles_section",
                "message": "The briefing does not expose separated evidence-role sections.",
            }
        )
    readiness_status = str(scaffold.get("section_context_acceptance_status", "")).strip()
    if readiness_status == "not_synthesis_ready":
        issues.append(
            {
                "severity": "error",
                "issue_type": "section_context_not_synthesis_ready",
                "message": "At least one section had insufficient source-backed context for synthesis.",
            }
        )
    score = max(0, 100 - 12 * len(issues))
    has_error = any(issue.get("severity") == "error" for issue in issues)
    return {
        "schema_id": "briefing_validation_report_v1",
        "method": "sufficiency_obligation_text_checks_plus_reader_contract_lints",
        "status": "fails_contract" if has_error else "passes_contract" if not issues else "passes_with_warnings" if score >= 70 else "needs_review",
        "score": score,
        "satisfied_obligation_ids": satisfied,
        "unsatisfied_obligation_count": sum(1 for issue in issues if issue.get("issue_type", "").startswith("missing")),
        "issues": issues,
        "claim_count": len(_claims(candidate_map)),
        "relation_count": len(_relations(candidate_map)),
    }

def _has_reader_unfriendly_identifier(rendered: str) -> bool:
    return any(
        re.search(pattern, rendered)
        for pattern in (
            r"\b[A-Za-z0-9_\-]+_c\d{3,}\b",
            r"\b[A-Za-z0-9_\-]+_r\d{3,}\b",
            r"\b(?:sc|ec|spine)_?\d{3,}\b",
            r"\bClaim [A-Z]\b",
            r"\bClaim [cC]?\d{3,}\b",
        )
    )

def model_parse_diagnostics(text: str, *, parse_ok: bool) -> dict[str, Any]:
    stripped = text.strip()
    open_braces = stripped.count("{")
    close_braces = stripped.count("}")
    open_brackets = stripped.count("[")
    close_brackets = stripped.count("]")
    return {
        "schema_id": "model_parse_diagnostics_v1",
        "parse_ok": parse_ok,
        "raw_char_count": len(text),
        "starts_with_json_fence": stripped.startswith("```json"),
        "starts_with_json_object": stripped.startswith("{"),
        "brace_balance": open_braces - close_braces,
        "bracket_balance": open_brackets - close_brackets,
        "looks_truncated": bool(stripped)
        and (
            open_braces != close_braces
            or open_brackets != close_brackets
            or stripped.endswith((",", "[", "{", ":"))
            or (stripped.startswith("```json") and not stripped.endswith("```"))
        ),
    }

def _rendered_mentions_any_slot_value(rendered: str, values: list[str]) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    for value in values:
        value_norm = re.sub(r"\s+", " ", value.lower()).strip()
        if not value_norm:
            continue
        if len(value_norm) >= 6 and value_norm in normalized:
            return True
        terms = _content_terms(value_norm)
        if len(terms) >= 2 and sum(1 for term in terms if term in normalized) >= min(3, len(terms)):
            return True
    return False

def _rendered_acknowledges_missing_slot(rendered: str, slot: str) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    label_terms = _content_terms(_slot_label(slot))
    missing_signal = any(
        marker in normalized
        for marker in ("not expose", "does not expose", "does not establish", "not establish", "missing", "not available", "not surfaced", "does not identify")
    )
    return missing_signal and any(term in normalized for term in label_terms)

def _rendered_mentions_any_surface_term(rendered: str, terms: list[str]) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    for term in terms:
        term_norm = re.sub(r"\s+", " ", term.lower()).strip()
        if len(term_norm) >= 4 and term_norm in normalized:
            return True
        if "-" in term_norm and term_norm.replace("-", " ") in normalized:
            return True
    return False

def _rendered_acknowledges_missing_family(rendered: str, family: str) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    family_terms = _content_terms(family.replace("_", " "))
    missing_signal = any(
        marker in normalized
        for marker in ("not expose", "does not expose", "does not establish", "not establish", "missing", "not available", "not assessed", "lacks")
    )
    return missing_signal and any(term in normalized for term in family_terms)

def _briefing_overclaims_against_scaffold(rendered: str, scaffold: dict[str, Any]) -> bool:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    default_answer = decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}
    classification = str(default_answer.get("classification", ""))
    normalized = rendered.lower()
    if classification == "neutral_or_low_concern_under_stated_conditions":
        return any(marker in normalized for marker in ("beneficial default", "clearly safe", "proven safe", "no risk"))
    return "proven safe" in normalized or "no risk" in normalized

def _briefing_evidence_fit_issues(rendered: str, evidence_ledger: dict[str, Any], candidate_map: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    reliance_text = _main_memo_reliance_text(rendered)
    rows = [row for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict)]
    mismatch_rows = [
        row
        for row in rows
        if isinstance(row.get("question_fit"), dict)
        and row["question_fit"].get("status") == "mismatch"
        and _rendered_mentions_specific_evidence(reliance_text, str(row.get("claim", "")))
    ]
    if mismatch_rows:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "briefing_mentions_wrong_scope_evidence",
                "message": "The briefing appears to use evidence flagged as a target-population mismatch.",
            }
        )
    appendix_rows = [
        row
        for row in rows
        if row.get("appendix_only")
        and row.get("section") in {"main_support", "conflicting_evidence"}
        and _rendered_mentions_specific_evidence(reliance_text, str(row.get("claim", "")))
    ]
    if appendix_rows:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "briefing_uses_appendix_only_evidence",
                "message": "The briefing appears to rely on evidence marked appendix-only by deterministic eligibility checks.",
            }
        )
    relation_count = len(_relations(candidate_map))
    claim_count = len(_claims(candidate_map))
    relation_floor = max(2, claim_count // 20) if claim_count >= 20 else 0
    if relation_floor and relation_count < relation_floor:
        issues.append(
            {
                "severity": "warning",
                "issue_type": "sparse_relation_graph",
                "message": f"The source map has {relation_count} relation(s) for {claim_count} claim(s), below the graph sufficiency floor.",
            }
        )
    return issues

def _main_memo_reliance_text(rendered: str) -> str:
    before_appendix = re.split(r"\n##\s+Evidence Appendix\b", rendered, maxsplit=1, flags=re.IGNORECASE)[0]
    sections: list[str] = []
    for title in ("Decision Brief", "Why This Read", "Evidence Carrying the Conclusion"):
        match = re.search(
            rf"(^##\s+{re.escape(title)}\s*$.*?)(?=^##\s+|\Z)",
            before_appendix,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if match:
            sections.append(match.group(1))
    return "\n\n".join(sections) if sections else before_appendix

def _rendered_mentions_specific_evidence(rendered: str, claim: str) -> bool:
    normalized = re.sub(r"\s+", " ", rendered.lower())
    claim_norm = re.sub(r"\s+", " ", claim.lower()).strip()
    if len(claim_norm) >= 24 and claim_norm in normalized:
        return True
    if any(phrase in normalized for phrase in _distinctive_evidence_phrases(claim_norm)):
        return True
    terms = _distinctive_evidence_terms(claim_norm)
    if len(terms) < 6:
        return False
    overlap = sum(1 for term in terms if term in normalized)
    return overlap >= max(6, int(len(terms) * 0.85))

def _distinctive_evidence_phrases(text: str) -> list[str]:
    terms = _distinctive_evidence_terms(text)
    phrases: list[str] = []
    for index in range(0, max(0, len(terms) - 3)):
        phrase = " ".join(terms[index : index + 4])
        if len(phrase) >= 24:
            phrases.append(phrase)
    return phrases[:8]

def _distinctive_evidence_terms(text: str) -> list[str]:
    generic = {
        "associated",
        "association",
        "cardiovascular",
        "consumption",
        "disease",
        "evidence",
        "higher",
        "intake",
        "lower",
        "moderate",
        "people",
        "reported",
        "risk",
        "study",
    }
    return [term for term in _content_terms(text) if term not in generic]

def _rel(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.map_briefing_decision_model import _slot_label
from epistemic_case_mapper.map_briefing_map_utils import _claims, _relations
from epistemic_case_mapper.map_briefing_pipeline import CONFIDENCE_ORDER
