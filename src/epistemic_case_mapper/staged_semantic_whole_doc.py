from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.prompt_templates import json_schema_block, render_prompt
from epistemic_case_mapper.staged_semantic_claim_quantities import (
    claim_quantity_json_schema,
    claim_quantity_values,
    normalize_claim_quantity_rows,
)
from epistemic_case_mapper.staged_semantic_evidence_units import build_source_evidence_units

WHOLE_DOC_CLAIM_PROMPT_VERSION = "whole_doc_source_card_claim_extraction_v5_decision_ranked_json"
WHOLE_DOC_REPAIR_PROMPT_VERSION = "whole_doc_source_card_schema_repair_v5_decision_ranked_json"
SOURCE_EXTRACTED_ROLE = "source_claim"
DEFAULT_WHOLE_DOC_NUM_PREDICT = 8192
DEFAULT_WHOLE_DOC_NUM_PREDICT_MAX = 16384


def whole_doc_claim_payload_for_source(
    *,
    source_id: str,
    source_title: str,
    source_text: str,
    decision_question: str,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    max_claims: int,
    canonical_path: Path,
    raw_path: Path,
    repair_raw_path: Path,
    report_path: Path,
    reuse_claim_cache: bool,
) -> tuple[dict[str, Any] | None, bool, str]:
    if reuse_claim_cache:
        cached = _read_cached_payload(canonical_path)
        if cached is not None:
            return cached, True, ""
    effective_max_claims = effective_whole_doc_claim_cap(source_text, max_claims)
    num_predict = whole_doc_num_predict(source_text, effective_max_claims)
    prompt = _source_card_prompt(
        source_id=source_id,
        source_title=source_title,
        source_text=source_text,
        decision_question=decision_question,
        max_claims=effective_max_claims,
    )
    write_markdown(raw_path.with_name(raw_path.name.replace("_raw.txt", "_prompt.txt")), prompt)
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            response_schema=source_card_json_schema(max_claims=effective_max_claims),
            num_predict=num_predict,
        )
        raw = result.text
    except (RuntimeError, ValueError) as exc:
        _write_backend_error_report(
            canonical_path=canonical_path,
            report_path=report_path,
            source_id=source_id,
            requested_max_claims=max_claims,
            effective_max_claims=effective_max_claims,
            num_predict=num_predict,
            error=str(exc),
            phase="initial_extraction",
        )
        return None, False, str(exc)
    write_markdown(raw_path, raw)
    parsed = _parse_model_json(raw)
    source_card, repair_info = _standard_source_card(
        parsed,
        source_id=source_id,
        source_text=source_text,
    )
    if source_card is None:
        repair_prompt = _repair_prompt(
            source_id=source_id,
            decision_question=decision_question,
            raw_extraction=raw,
            max_claims=effective_max_claims,
        )
        write_markdown(repair_raw_path.with_name(repair_raw_path.name.replace("_repair_raw.txt", "_repair_prompt.txt")), repair_prompt)
        try:
            repair_result = run_model_backend(
                repair_prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
                response_schema=source_card_json_schema(max_claims=effective_max_claims),
                num_predict=num_predict,
            )
            repair_raw = repair_result.text
        except (RuntimeError, ValueError) as exc:
            _write_backend_error_report(
                canonical_path=canonical_path,
                report_path=report_path,
                source_id=source_id,
                requested_max_claims=max_claims,
                effective_max_claims=effective_max_claims,
                num_predict=num_predict,
                error=str(exc),
                phase="schema_repair",
            )
            return None, False, str(exc)
        write_markdown(repair_raw_path, repair_raw)
        repaired = _parse_model_json(repair_raw)
        source_card, repair_info = _standard_source_card(
            repaired,
            source_id=source_id,
            source_text=source_text,
            repaired=True,
        )
        if source_card is None:
            source_card, repair_info = _standard_source_card(
                parsed,
                source_id=source_id,
                source_text=source_text,
                allow_common_variants=True,
            )
    if source_card is None:
        report = {
            "schema_id": "whole_doc_claim_extraction_report_v1",
            "status": "error",
            "source_id": source_id,
            "reason": "no_usable_source_card",
            "requested_max_claims": max_claims,
            "effective_max_claims": effective_max_claims,
            "num_predict": num_predict,
        }
        write_json(report_path, report)
        write_json(canonical_path, {})
        return None, False, "whole-doc extraction produced no usable source card"
    payload, report = _successful_source_card_payload(
        source_card,
        source_id=source_id,
        source_text=source_text,
        max_claims=max_claims,
        effective_max_claims=effective_max_claims,
        num_predict=num_predict,
        repair_info=repair_info,
    )
    write_json(canonical_path, payload)
    write_json(report_path, report)
    return payload, False, ""


def _successful_source_card_payload(
    source_card: dict[str, Any],
    *,
    source_id: str,
    source_text: str,
    max_claims: int,
    effective_max_claims: int,
    num_predict: int,
    repair_info: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposals, proposal_report = _claim_proposals_from_source_card(source_card, source_text=source_text, source_id=source_id)
    evidence_unit_bundle = build_source_evidence_units(source_card, source_id=source_id, source_text=source_text)
    evidence_unit_report = evidence_unit_bundle["source_evidence_unit_quality_report"]
    payload = {
        "claims": proposals,
        "source_card": source_card,
        **evidence_unit_bundle,
        "extractor": "whole-doc",
        "prompt_version": WHOLE_DOC_CLAIM_PROMPT_VERSION,
    }
    report = {
        "schema_id": "whole_doc_claim_extraction_report_v1",
        "status": "ok",
        "source_id": source_id,
        "claim_count": len(proposals),
        "requested_max_claims": max_claims,
        "effective_max_claims": effective_max_claims,
        "num_predict": num_predict,
        **repair_info,
        **proposal_report,
        "source_evidence_unit_count": evidence_unit_report["unit_count"],
        "source_quantity_tuple_count": evidence_unit_report["quantity_tuple_count"],
        "source_evidence_unit_warning_counts": evidence_unit_report["warning_counts"],
    }
    return payload, report


def _write_backend_error_report(
    *,
    canonical_path: Path,
    report_path: Path,
    source_id: str,
    requested_max_claims: int,
    effective_max_claims: int,
    num_predict: int,
    error: str,
    phase: str,
) -> None:
    write_json(canonical_path, {})
    write_json(
        report_path,
        {
            "schema_id": "whole_doc_claim_extraction_report_v1",
            "status": "backend_error",
            "source_id": source_id,
            "phase": phase,
            "error": error,
            "requested_max_claims": requested_max_claims,
            "effective_max_claims": effective_max_claims,
            "num_predict": num_predict,
        },
    )


def effective_whole_doc_claim_cap(source_text: str, requested_max_claims: int) -> int:
    """Allow longer documents to return more source-level claims.

    The CLI option remains the floor requested by the caller. Long documents
    often need extra slots to preserve distinct endpoint, population, and
    subgroup claims without forcing the model into oversized claims.
    """

    base = max(1, int(requested_max_claims))
    hard_cap = max(base, _int_env("ECM_WHOLE_DOC_MAX_CLAIMS_CAP", 24))
    extra = (max(0, len(source_text)) // 20_000) * 2
    return min(hard_cap, base + extra)


def whole_doc_num_predict(source_text: str, effective_max_claims: int) -> int:
    override = _int_env("ECM_WHOLE_DOC_OLLAMA_NUM_PREDICT", 0)
    if override > 0:
        return override
    global_default = _int_env("ECM_OLLAMA_NUM_PREDICT", 2048)
    max_budget = max(DEFAULT_WHOLE_DOC_NUM_PREDICT, _int_env("ECM_WHOLE_DOC_OLLAMA_NUM_PREDICT_MAX", DEFAULT_WHOLE_DOC_NUM_PREDICT_MAX))
    long_doc_extra = (max(0, len(source_text)) // 50_000) * 2048
    claim_extra = max(0, int(effective_max_claims) - 8) * 512
    budget = max(DEFAULT_WHOLE_DOC_NUM_PREDICT, global_default) + long_doc_extra + claim_extra
    return min(max_budget, max(1024, budget))


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def source_card_json_schema(*, max_claims: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "source_id": {"type": "string"},
            "source_bottom_line": {"type": "string"},
            "canonical_claims": {
                "type": "array",
                "maxItems": max_claims,
                "items": {
                        "type": "object",
                        "properties": {
                            "claim": {"type": "string"},
                            "question_relevance": {"type": "string", "enum": ["direct", "indirect", "scope_limit", "background", "irrelevant"]},
                            "scope_flags": {"type": "array", "items": {"type": "string"}},
                            "decision_importance": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                            "why_it_matters": {"type": "string"},
                        "supporting_quotes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "quote": {"type": "string"},
                                    "line_hint": {"type": "string"},
                                },
                                "required": ["quote", "line_hint"],
                            },
                        },
                        "quantities": {
                            "type": "array",
                            "items": {"anyOf": [{"type": "string"}, claim_quantity_json_schema()]},
                        },
                        "scope_conditions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "claim",
                        "question_relevance",
                        "scope_flags",
                        "decision_importance",
                        "why_it_matters",
                        "supporting_quotes",
                        "quantities",
                        "scope_conditions",
                    ],
                },
            },
            "excluded_as_not_decision_relevant": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["source_id", "source_bottom_line", "canonical_claims", "excluded_as_not_decision_relevant"],
    }


def _source_card_prompt(
    *,
    source_id: str,
    source_title: str,
    source_text: str,
    decision_question: str,
    max_claims: int,
) -> str:
    numbered = "\n".join(f"{index}: {line}" for index, line in enumerate(source_text.splitlines(), start=1))
    return render_prompt(
        ("Task", "Extract a compact source-level claim card from one whole source document."),
        (
            "Metadata",
            f"Prompt version: {WHOLE_DOC_CLAIM_PROMPT_VERSION}\nSource ID: {source_id}\nSource title: {source_title}\nDecision question: {decision_question}",
        ),
        (
            "Rules",
            [
                "- Read the whole document before choosing claims.",
                f"- Return 3 to {max_claims} canonical claims for this source, not one claim per paragraph or table row.",
                "- A canonical claim should be something a decision analyst would want in the main evidence map.",
                "- Turn table results into interpretable claims with row/column context; treat headings, references, and labels as context.",
                "- If a table result matters, combine row/column context into one interpretable claim and cite a table-adjacent quote or narrative sentence.",
                "- Preserve key quantities inside the relevant canonical claim rather than as separate claims.",
                "- For quantities, prefer objects with value, quantity_role, measures, local_interpretation, source_quote, line_hint, and retention_hint.",
                "- Use retention_hint must_retain only when the memo would be materially worse without that number; otherwise use use_if_space or audit_only.",
                "- Assign only extraction fields here; later stages assign support, counterweight, crux, scope, mechanism, and final map roles after an overall answer frame exists.",
                "- For every canonical claim, set question_relevance and scope_flags to explain why it belongs in this decision map.",
                "- Use decision_importance sparingly: critical only if the claim would materially change the answer or confidence.",
                "- supporting_quotes must be exact substrings from the document; line_hint can be approximate, such as lines 50-52.",
                "- Output JSON only.",
            ],
        ),
        ("Preferred Output Schema", json_schema_block(source_card_json_schema(max_claims=max_claims))),
        ("Source Document With Line Numbers", numbered),
    )


def _repair_prompt(*, source_id: str, decision_question: str, raw_extraction: str, max_claims: int) -> str:
    return render_prompt(
        ("Task", "Reformat extracted source-level claims into the required JSON schema."),
        ("Metadata", f"Prompt version: {WHOLE_DOC_REPAIR_PROMPT_VERSION}\nSource ID: {source_id}\nDecision question: {decision_question}"),
        (
            "Rules",
            [
                "- Preserve factual claims already present in the raw extraction.",
                "- Preserve useful claims from the raw extraction unless they are clearly off-question.",
                "- Keep role assignment limited to question_relevance, scope_flags, and decision_importance.",
                "- Use only question_relevance, scope_flags, and decision_importance values allowed by the schema.",
                "- Use only decision_importance values: critical, high, medium, low.",
                "- Convert each supporting quote string into an object with quote and line_hint.",
                "- If a line hint is present outside the quote object, copy it into each relevant quote object.",
                "- Use source_bottom_line to summarize this source in one sentence.",
                "- Output JSON only.",
            ],
        ),
        ("Output Schema", json_schema_block(source_card_json_schema(max_claims=max_claims))),
        ("Raw Extraction To Reformat", raw_extraction),
    )


def _parse_model_json(text: str) -> Any:
    try:
        return json.loads(canonical_json_output(text))
    except json.JSONDecodeError:
        return None


def _standard_source_card(
    payload: Any,
    *,
    source_id: str,
    source_text: str,
    repaired: bool = False,
    allow_common_variants: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("canonical_claims"), list):
        if allow_common_variants:
            payload = _coerce_common_source_card_variant(payload, source_id=source_id)
        else:
            return None, {"repair_used": False, "repair_reason": "noncanonical_payload"}
    if not isinstance(payload, dict):
        return None, {"repair_used": repaired, "repair_reason": "unusable_payload"}
    claims = payload.get("canonical_claims")
    if not isinstance(claims, list):
        return None, {"repair_used": repaired, "repair_reason": "canonical_claims_not_list"}
    normalized_claims: list[dict[str, Any]] = []
    rejected = 0
    for item in claims:
        claim = _normalize_source_card_claim(item, source_text=source_text)
        if claim is None:
            rejected += 1
            continue
        normalized_claims.append(claim)
    if not normalized_claims:
        return None, {"repair_used": repaired, "repair_reason": "no_valid_claims", "schema_rejected_claim_count": rejected}
    return (
        {
            "source_id": str(payload.get("source_id") or source_id),
            "source_bottom_line": _compact(str(payload.get("source_bottom_line") or "")),
            "canonical_claims": normalized_claims,
            "excluded_as_not_decision_relevant": _string_list(payload.get("excluded_as_not_decision_relevant")),
        },
        {
            "repair_used": repaired,
            "repair_reason": "schema_repair" if repaired else "not_needed",
            "schema_rejected_claim_count": rejected,
        },
    )


def _coerce_common_source_card_variant(payload: Any, *, source_id: str) -> dict[str, Any] | None:
    if isinstance(payload, list):
        return {
            "source_id": source_id,
            "source_bottom_line": "",
            "canonical_claims": payload,
            "excluded_as_not_decision_relevant": [],
        }
    if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
        return {
            "source_id": str(payload.get("source_id") or source_id),
            "source_bottom_line": str(payload.get("source_bottom_line") or ""),
            "canonical_claims": payload["claims"],
            "excluded_as_not_decision_relevant": _string_list(payload.get("excluded_as_not_decision_relevant")),
        }
    return None


def _normalize_source_card_claim(item: Any, *, source_text: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    claim = _compact(str(item.get("claim") or ""))
    if not claim:
        return None
    quotes = _quote_rows(item)
    exact_quotes = [row for row in quotes if _quote_matches_source(row["quote"], source_text)]
    if not exact_quotes:
        return None
    importance = _normalize_importance(item.get("decision_importance"))
    quantity_rows = normalize_claim_quantity_rows(item.get("quantities"), supporting_quotes=exact_quotes)
    return {
        "claim": claim,
        "question_relevance": _normalize_question_relevance(item.get("question_relevance")),
        "scope_flags": _normalize_scope_flags(item.get("scope_flags")),
        "decision_importance": importance,
        "why_it_matters": _compact(str(item.get("why_it_matters") or item.get("relevance_rationale") or "")),
        "supporting_quotes": exact_quotes[:3],
        "quantities": claim_quantity_values(quantity_rows),
        "claim_quantities": quantity_rows,
        "scope_conditions": _string_list(item.get("scope_conditions")),
    }


def _claim_proposals_from_source_card(source_card: dict[str, Any], *, source_text: str, source_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    quote_count = 0
    exact_quote_count = 0
    short_quote_count = 0
    acronym_expansions = _source_acronym_expansions(source_text)
    for claim in source_card["canonical_claims"]:
        quotes = claim.get("supporting_quotes", [])
        quote = str(quotes[0].get("quote", "") if quotes else "").strip()
        claim_quantities = normalize_claim_quantity_rows(claim.get("claim_quantities") or claim.get("quantities"), supporting_quotes=quotes)
        quantity_values = claim_quantity_values(claim_quantities)
        quote_count += len(quotes)
        exact_quote_count += sum(1 for row in quotes if _quote_matches_source(str(row.get("quote", "")), source_text))
        short_quote_count += sum(1 for row in quotes if len(str(row.get("quote", "")).strip()) < 25)
        importance = claim["decision_importance"]
        proposals.append(
            {
                "claim": claim["claim"],
                "source_quote": quote,
                "span_id": _span_id_from_line_hint(source_id, str(quotes[0].get("line_hint", "") if quotes else "")),
                "entailed_by_excerpt": "yes",
                "role": SOURCE_EXTRACTED_ROLE,
                "question_relevance": claim.get("question_relevance", "unspecified"),
                "relevance_rationale": claim.get("why_it_matters", ""),
                "scope_flags": claim.get("scope_flags", ["none"]),
                "decision_importance": importance,
                "importance_rationale": claim.get("why_it_matters", ""),
                "quantity_values": quantity_values,
                "claim_quantities": claim_quantities,
                "source_acronym_expansions": _used_acronym_expansions(
                    acronym_expansions,
                    text=" ".join([claim["claim"], quote]),
                ),
                "whole_doc_source_card": {
                    "source_bottom_line": source_card.get("source_bottom_line", ""),
                    "quantities": quantity_values,
                    "claim_quantities": claim_quantities,
                    "scope_conditions": claim.get("scope_conditions", []),
                    "supporting_quotes": quotes,
                },
            }
        )
    return proposals, {
        "source_card_quote_count": quote_count,
        "source_card_exact_quote_count": exact_quote_count,
        "source_card_short_quote_count": short_quote_count,
        "source_card_acronym_expansion_count": len(acronym_expansions),
    }


def _source_acronym_expansions(source_text: str) -> dict[str, str]:
    expansions: dict[str, str] = {}
    pattern = re.compile(r"([A-Za-z][A-Za-z0-9 ,;:/\-]{3,140}?)\s*\(([A-Z][A-Z0-9-]{1,10}s?)\)")
    for match in pattern.finditer(source_text):
        acronym = _clean_acronym(match.group(2))
        expansion = _best_acronym_expansion(match.group(1), acronym)
        if acronym and expansion:
            expansions.setdefault(acronym, expansion)
    return expansions


def _used_acronym_expansions(expansions: dict[str, str], *, text: str) -> dict[str, str]:
    return {
        acronym: expansion
        for acronym, expansion in expansions.items()
        if re.search(rf"\b{re.escape(acronym)}s?\b", text, flags=re.IGNORECASE)
    }


def _clean_acronym(value: str) -> str:
    acronym = re.sub(r"[^A-Za-z0-9-]", "", value).strip("-").upper()
    if acronym.endswith("S") and len(acronym) > 2:
        acronym = acronym[:-1]
    if not re.fullmatch(r"[A-Z][A-Z0-9-]{1,10}", acronym):
        return ""
    return acronym


def _best_acronym_expansion(text: str, acronym: str) -> str:
    if not acronym:
        return ""
    segment = re.split(r"[.;:\n?!]", text)[-1]
    words = re.findall(r"[A-Za-z][A-Za-z0-9/-]*", segment)
    words = [word.strip("-/") for word in words if word.strip("-/")]
    if not words:
        return ""
    for size in range(1, min(8, len(words)) + 1):
        phrase_words = words[-size:]
        phrase = " ".join(phrase_words)
        if _acronym_matches_phrase(acronym, phrase):
            return _compact(phrase)
    return ""


def _acronym_matches_phrase(acronym: str, phrase: str) -> bool:
    compact_phrase = re.sub(r"[^A-Za-z0-9]", "", phrase).upper()
    if not compact_phrase:
        return False
    position = 0
    for char in acronym.replace("-", ""):
        position = compact_phrase.find(char, position)
        if position < 0:
            return False
        position += 1
    return True


def _quote_rows(item: dict[str, Any]) -> list[dict[str, str]]:
    raw = item.get("supporting_quotes", [])
    if not isinstance(raw, list):
        raw = [raw]
    fallback_hint = _first_line_hint(item)
    rows: list[dict[str, str]] = []
    for quote in raw:
        if isinstance(quote, dict):
            text = str(quote.get("quote") or "").strip()
            line_hint = str(quote.get("line_hint") or quote.get("line_hints") or fallback_hint).strip()
        else:
            text = str(quote or "").strip()
            line_hint = fallback_hint
        if text:
            rows.append({"quote": _clean_quote(text), "line_hint": line_hint})
    return rows


def _first_line_hint(item: dict[str, Any]) -> str:
    for key in ("line_hint", "line_hints"):
        value = item.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if value:
            return str(value)
    return ""


def _normalize_question_relevance(value: Any) -> str:
    relevance = str(value or "").strip().lower()
    if relevance in {"direct", "indirect", "scope_limit", "background", "irrelevant"}:
        return relevance
    return "unspecified"


def _normalize_scope_flags(value: Any) -> list[str]:
    if isinstance(value, list):
        flags = [str(item).strip().lower() for item in value if str(item).strip()]
    else:
        flags = [part.strip().lower() for part in re.split(r"[,;|]", str(value or "")) if part.strip()]
    allowed = {
        "target_population_mismatch",
        "outcome_mismatch",
        "intervention_or_exposure_mismatch",
        "mechanism_only",
        "administrative_context",
        "none",
    }
    normalized = [flag for flag in flags if flag in allowed]
    return normalized or ["none"]


def _normalize_importance(value: Any) -> str:
    if isinstance(value, bool):
        return "high" if value else "low"
    importance = str(value or "").strip().lower()
    return importance if importance in {"critical", "high", "medium", "low"} else "medium"


def _span_id_from_line_hint(source_id: str, line_hint: str) -> str:
    match = re.search(r"\d+", line_hint)
    if not match:
        return ""
    return f"{_safe_filename(source_id)}_s{int(match.group(0)):04d}"


def _quote_matches_source(quote: str, source_text: str) -> bool:
    cleaned = _clean_quote(quote)
    if cleaned in source_text:
        return True
    return _normalize_space(cleaned) in _normalize_space(source_text)


def _clean_quote(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().strip('"').strip("'")).strip()


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_compact(str(item)) for item in value if str(item).strip()]
    if value:
        return [_compact(str(value))]
    return []


def _compact(value: str, max_chars: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def _read_cached_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
        return payload
    return None


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
