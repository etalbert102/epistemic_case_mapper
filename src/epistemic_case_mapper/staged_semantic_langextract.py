from __future__ import annotations

import importlib
import json
import os
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json


def langextract_claim_payload_for_chunk(
    *,
    chunk: Any,
    case_question: str,
    role_options: list[str],
    backend: str,
    max_claims: int,
    canonical_path: Path,
    report_path: Path,
    reuse_claim_cache: bool,
    extraction_passes: int = 2,
) -> tuple[dict[str, Any] | None, bool, str]:
    """Extract grounded claim proposals with Google's optional LangExtract package."""
    if reuse_claim_cache and canonical_path.exists():
        try:
            return json.loads(canonical_path.read_text(encoding="utf-8")), True, ""
        except json.JSONDecodeError:
            pass
    try:
        payload, report = _run_langextract(
            chunk=chunk,
            case_question=case_question,
            role_options=role_options,
            backend=backend,
            max_claims=max_claims,
            extraction_passes=extraction_passes,
        )
    except (ImportError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
        write_json(report_path, {"schema_id": "langextract_claim_report_v1", "status": "error", "error": str(exc)})
        return None, False, str(exc)
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(canonical_path, payload)
    write_json(report_path, report)
    return payload, False, ""


def _run_langextract(
    *,
    chunk: Any,
    case_question: str,
    role_options: list[str],
    backend: str,
    max_claims: int,
    extraction_passes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    lx = _import_langextract()
    model_kwargs = _model_kwargs(backend)
    runtime_options = _runtime_options(backend)
    result = lx.extract(
        text_or_documents=str(chunk.plain_text),
        prompt_description=_prompt_description(case_question, role_options, max_claims),
        examples=_examples(lx),
        extraction_passes=max(1, extraction_passes),
        max_workers=1,
        max_char_buffer=max(1000, len(str(chunk.plain_text)) + 1),
        **runtime_options,
        **model_kwargs,
    )
    proposals, rejected = _proposals_from_extractions(result, chunk, max_claims=max_claims)
    report = {
        "schema_id": "langextract_claim_report_v1",
        "status": "ok",
        "chunk_id": chunk.chunk_id,
        "model_id": model_kwargs.get("model_id"),
        "runtime_options": runtime_options,
        "proposal_count": len(proposals),
        "rejected_count": len(rejected),
        "rejected": rejected[:50],
    }
    return {"claims": proposals, "extractor": "langextract"}, report


def _import_langextract() -> Any:
    try:
        return importlib.import_module("langextract")
    except ImportError as exc:
        raise ImportError("LangExtract is not installed. Install with `pip install -e .[langextract]`.") from exc


def _model_kwargs(backend: str) -> dict[str, Any]:
    selected = str(backend or "").strip()
    if not selected or selected == "prompt":
        raise ValueError("LangExtract claim extraction requires a real model backend, not `prompt`.")
    if selected.startswith("ollama:"):
        return {
            "model_id": selected.split(":", 1)[1],
            "model_url": os.environ.get("LANGEXTRACT_OLLAMA_URL", "http://localhost:11434"),
        }
    if selected.startswith(("openai:", "gemini:")):
        return {"model_id": selected.split(":", 1)[1]}
    return {"model_id": selected}


def _runtime_options(backend: str) -> dict[str, Any]:
    selected = str(backend or "").strip()
    if selected.startswith("ollama:"):
        return {
            "use_schema_constraints": False,
            "resolver_params": {
                "suppress_parse_errors": True,
            },
        }
    return {}


def _prompt_description(case_question: str, role_options: list[str], max_claims: int) -> str:
    del role_options
    return (
        "Extract decision-relevant evidence spans for an epistemic decision map.\n"
        "Use exact text from the input as extraction_text. Do not extract titles, citations, boilerplate, or purely topical mentions.\n"
        "For each extracted span, add attributes: claim, question_relevance, relevance_rationale, scope_flags, entailed_by_excerpt, decision_importance, importance_rationale.\n"
        "The claim attribute should be a concise faithful paraphrase of only the extracted span.\n"
        "Do not classify evidence as support, counterweight, crux, scope role, or final map section; later stages assign those roles after an overall answer frame exists.\n"
        f"Decision question: {case_question}\n"
        "Allowed question_relevance values: direct, indirect, scope_limit, background, irrelevant.\n"
        "Allowed scope_flags values: target_population_mismatch, outcome_mismatch, intervention_or_exposure_mismatch, mechanism_only, administrative_context, none.\n"
        "Allowed decision_importance values: critical, high, medium, low. Importance means how much this span should affect the decision map.\n"
        f"Return at most {max_claims} high-value extractions from this chunk."
    )


def _examples(lx: Any) -> list[Any]:
    return [
        lx.data.ExampleData(
            text="The pilot reduced processing time for eligible small projects by 34 percent without increasing error rates.",
            extractions=[
                lx.data.Extraction(
                    extraction_class="decision_relevant_claim",
                    extraction_text="reduced processing time for eligible small projects by 34 percent without increasing error rates",
                    attributes={
                        "claim": "The pilot reduced processing time for eligible small projects by 34 percent without increasing error rates.",
                        "question_relevance": "direct",
                        "relevance_rationale": "The span reports an outcome directly relevant to the decision.",
                        "scope_flags": ["none"],
                        "entailed_by_excerpt": "yes",
                        "decision_importance": "high",
                        "importance_rationale": "It reports a target outcome and should shape the main map.",
                    },
                )
            ],
        )
    ]


def _proposals_from_extractions(result: Any, chunk: Any, *, max_claims: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    proposals: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, extraction in enumerate(getattr(result, "extractions", []) or [], start=1):
        extraction_text = str(getattr(extraction, "extraction_text", "") or "").strip()
        attrs = getattr(extraction, "attributes", {}) or {}
        if not isinstance(attrs, dict):
            attrs = {}
        interval = getattr(extraction, "char_interval", None)
        if not extraction_text or not interval:
            rejected.append({"index": index, "reason": "ungrounded_or_empty_extraction", "text": extraction_text[:160]})
            continue
        span_id = _span_id_for_extraction(chunk, extraction_text, interval)
        if not span_id:
            rejected.append({"index": index, "reason": "no_matching_source_span", "text": extraction_text[:160]})
            continue
        proposals.append(
            {
                "claim": str(attrs.get("claim") or extraction_text).strip(),
                "source_quote": extraction_text,
                "span_id": span_id,
                "entailed_by_excerpt": str(attrs.get("entailed_by_excerpt") or "yes").strip().lower(),
                "question_relevance": str(attrs.get("question_relevance") or "unspecified").strip().lower(),
                "relevance_rationale": str(attrs.get("relevance_rationale") or "").strip(),
                "scope_flags": _scope_flags(attrs.get("scope_flags")),
                "decision_importance": str(attrs.get("decision_importance") or attrs.get("importance") or "").strip().lower(),
                "importance_rationale": str(attrs.get("importance_rationale") or "").strip(),
                "langextract": {
                    "extraction_text": extraction_text,
                    "char_interval": _interval_dict(interval),
                    "alignment_status": str(getattr(extraction, "alignment_status", "") or ""),
                },
            }
        )
        if len(proposals) >= max_claims:
            break
    return proposals, rejected


def _span_id_for_extraction(chunk: Any, extraction_text: str, interval: Any) -> str:
    lowered = extraction_text.lower()
    exact = [span for span in chunk.spans if lowered in str(span.text).lower()]
    if exact:
        return max(exact, key=lambda span: len(str(span.text))).span_id
    scored = [(_overlap_count(extraction_text, str(span.text)), span.span_id) for span in chunk.spans]
    scored = [item for item in scored if item[0] >= 3]
    if scored:
        return max(scored)[1]
    return _span_id_from_interval(chunk, interval)


def _span_id_from_interval(chunk: Any, interval: Any) -> str:
    start = _interval_start(interval)
    if start is None:
        return ""
    line_no = int(chunk.start_line) + str(chunk.plain_text)[:start].count("\n")
    expected_span = f"lines {line_no}-{line_no}"
    for span in chunk.spans:
        if str(span.source_span) == expected_span:
            return str(span.span_id)
    return ""


def _interval_start(interval: Any) -> int | None:
    if isinstance(interval, dict):
        value = interval.get("start_pos") if "start_pos" in interval else interval.get("start")
        return int(value) if value is not None else None
    value = getattr(interval, "start_pos", getattr(interval, "start", None))
    return int(value) if value is not None else None


def _interval_dict(interval: Any) -> dict[str, int]:
    if isinstance(interval, dict):
        return {key: int(value) for key, value in interval.items() if key in {"start_pos", "end_pos", "start", "end"} and value is not None}
    output: dict[str, int] = {}
    for key in ("start_pos", "end_pos", "start", "end"):
        value = getattr(interval, key, None)
        if value is not None:
            output[key] = int(value)
    return output


def _scope_flags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return [part.strip().lower() for part in re.split(r"[,;|]", str(value or "")) if part.strip()] or ["none"]


def _overlap_count(left: str, right: str) -> int:
    left_terms = set(re.findall(r"[a-z0-9]{4,}", left.lower()))
    return sum(1 for term in re.findall(r"[a-z0-9]{4,}", right.lower()) if term in left_terms)
