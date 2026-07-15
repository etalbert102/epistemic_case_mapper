from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.map_briefing_map_utils import (
    _claims,
    _relations,
    build_source_display_lookup,
    confidence_cap,
    generated_map_erosion_audit,
)
from epistemic_case_mapper.map_briefing_final_outputs import ModelBackendConfig, write_final_reader_outputs
from epistemic_case_mapper.map_briefing_decision_packet_stage import attach_decision_briefing_packet
from epistemic_case_mapper.map_briefing_pipeline import briefing_scaffold, deterministic_briefing_payload
from epistemic_case_mapper.map_briefing_text_cleanup import (
    reader_facing_unresolved_family,
    reader_facing_unresolved_slot,
)
from epistemic_case_mapper.model_schemas import CompactDecisionModelOutput, DecisionModelItem
from epistemic_case_mapper.decision_frame import question_quality_report


@dataclass(frozen=True)
class DecisionModelSliceResult:
    decision_model_path: Path
    briefing_path: Path
    eval_path: Path
    status: str
    synthesized_briefing_path: Path | None = None
    synthesized_appendix_path: Path | None = None
    synthesis_report_path: Path | None = None


def build_compact_decision_model(
    candidate_map: dict[str, Any],
    quality_report: dict[str, Any],
    *,
    question: str,
    source_titles: dict[str, str] | None = None,
    scaffold: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_concrete_question(question)
    source_lookup = build_source_display_lookup(candidate_map, source_titles=source_titles)
    scaffold = scaffold or briefing_scaffold(
        candidate_map,
        quality_report,
        source_lookup,
        generated_map_erosion_audit(candidate_map),
        question=question,
    )
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    deterministic_payload = deterministic_briefing_payload(scaffold)
    claim_lookup = {str(claim.get("claim_id")): claim for claim in _claims(candidate_map)}
    compact = CompactDecisionModelOutput(
        answer_frame={
            "question": question,
            "current_read": _current_read(decision_model, deterministic_payload),
            "confidence": _confidence(quality_report, scaffold),
            "why_this_frame": _default_answer(decision_model).get("why_this_frame", ""),
        },
        top_support=_items_from_cluster_rows(decision_model.get("main_reasons", []), claim_lookup)[:3],
        top_counterevidence_or_tensions=_counter_items(decision_model, claim_lookup)[:3],
        top_scope_boundaries=_scope_items(scaffold, decision_model, claim_lookup)[:3],
        top_cruxes=_crux_items(candidate_map, claim_lookup)[:3],
        confidence_drivers=_confidence_drivers(scaffold, quality_report)[:3],
        missing_evidence=_missing_evidence(scaffold)[:3],
        decision_implications=_decision_implications(deterministic_payload, decision_model)[:3],
        audit={
            "method": "deterministic_compaction_from_existing_map_scaffold",
            "source_display_names": source_lookup,
            "claim_count": len(_claims(candidate_map)),
            "relation_count": len(_relations(candidate_map)),
            "quality_status": quality_report.get("status", scaffold.get("quality_status", "unknown")),
            "sufficiency_status": _sufficiency_report(scaffold).get("status", "unknown"),
        },
    )
    return compact.model_dump()


def render_decision_model_brief(decision_model: dict[str, Any]) -> str:
    model = CompactDecisionModelOutput.model_validate(decision_model)
    lines = [
        "# Decision Brief",
        "",
        f"**Question.** {model.answer_frame.question}",
        "",
        f"**Current read.** {model.answer_frame.current_read} Confidence: {model.answer_frame.confidence}.",
    ]
    if model.answer_frame.why_this_frame:
        lines.extend(["", f"**Why this frame.** {model.answer_frame.why_this_frame}"])
    lines.extend(_item_section("What carries the answer", model.top_support, empty="The map does not expose strong support rows."))
    lines.extend(
        _item_section(
            "What could change the answer",
            [*model.top_cruxes, *model.top_counterevidence_or_tensions][:3],
            empty="The map does not expose live cruxes or counterevidence.",
        )
    )
    lines.extend(
        _item_section(
            "Scope and missing evidence",
            [*model.top_scope_boundaries, *model.missing_evidence][:4],
            empty="The map does not expose scope boundaries or missing-evidence warnings.",
        )
    )
    lines.extend(_item_section("Decision implications", model.decision_implications, empty="No practical implication is warranted from the map."))
    lines.extend(
        [
            "## Audit Trail",
            "",
            f"- Claims considered: {model.audit.get('claim_count', 0)}.",
            f"- Relations considered: {model.audit.get('relation_count', 0)}.",
            f"- Map quality: {model.audit.get('quality_status', 'unknown')}; sufficiency: {model.audit.get('sufficiency_status', 'unknown')}.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def evaluate_decision_model_brief(
    current_brief: str,
    decision_brief: str,
    decision_model: dict[str, Any],
) -> dict[str, Any]:
    model = CompactDecisionModelOutput.model_validate(decision_model)
    current_first = current_brief[:1200].lower()
    decision_first = decision_brief[:1200].lower()
    current_crux = _term_count(current_first, ("crux", "would change", "change the answer", "tension"))
    decision_crux = len(model.top_cruxes) + _term_count(decision_first, ("would change", "change the answer", "tension"))
    current_scope = _term_count(current_first, ("scope", "boundary", "missing", "does not hold", "applies"))
    decision_scope = len(model.top_scope_boundaries) + len(model.missing_evidence)
    unsupported = _unsupported_evidence_item_count(model)
    improved = decision_crux >= current_crux and decision_scope >= current_scope and unsupported == 0
    return {
        "schema_id": "decision_model_brief_eval_v1",
        "status": "improved" if improved else "mixed",
        "metrics": {
            "current_word_count": _word_count(current_brief),
            "decision_model_word_count": _word_count(decision_brief),
            "current_first_page_crux_signals": current_crux,
            "decision_first_page_crux_signals": decision_crux,
            "current_first_page_scope_signals": current_scope,
            "decision_scope_and_missing_items": decision_scope,
            "unsupported_evidence_items": unsupported,
            "decision_confidence_visible": model.answer_frame.confidence in decision_first,
        },
        "notes": [
            "This eval is a vertical-slice readability and anchoring check, not a human quality judgment.",
            "Evidence-bearing sections count as unsupported if an item lacks claim, source, and relation anchors.",
        ],
    }


def run_decision_model_slice(
    *,
    repo_root: Path,
    map_path: str | Path,
    quality_report_path: str | Path,
    question: str,
    output_dir: str | Path | None = None,
    current_brief_path: str | Path | None = None,
    source_titles: dict[str, str] | None = None,
    synthesis_backend: str | None = None,
    backend_timeout: int | None = 120,
    backend_retries: int = 0,
) -> DecisionModelSliceResult:
    if backend_retries < 0:
        raise ValueError("backend_retries must be nonnegative")
    if backend_timeout is not None and backend_timeout < 1:
        raise ValueError("backend_timeout must be positive")
    _require_concrete_question(question)
    map_file = _resolve(repo_root, map_path)
    quality_file = _resolve(repo_root, quality_report_path)
    candidate_map = json.loads(map_file.read_text(encoding="utf-8"))
    quality_report = json.loads(quality_file.read_text(encoding="utf-8"))
    artifacts = _resolve(repo_root, output_dir or Path("artifacts") / "decision_model_slices" / map_file.stem)
    artifacts.mkdir(parents=True, exist_ok=True)
    source_lookup = build_source_display_lookup(candidate_map, source_titles=source_titles)
    scaffold = briefing_scaffold(
        candidate_map,
        quality_report,
        source_lookup,
        generated_map_erosion_audit(candidate_map),
        question=question,
    )
    compact_model = build_compact_decision_model(
        candidate_map,
        quality_report,
        question=question,
        source_titles=source_titles,
        scaffold=scaffold,
    )
    brief = render_decision_model_brief(compact_model)
    current_brief = ""
    if current_brief_path:
        current_brief = _resolve(repo_root, current_brief_path).read_text(encoding="utf-8")
    eval_report = evaluate_decision_model_brief(current_brief, brief, compact_model)
    decision_model_path = artifacts / "decision_model.json"
    briefing_path = artifacts / "decision_model_brief.md"
    eval_path = artifacts / "decision_model_eval.json"
    write_json(decision_model_path, compact_model)
    write_markdown(briefing_path, brief)
    write_json(eval_path, eval_report)
    synthesized_paths: dict[str, Path | None] = {
        "briefing": None,
        "appendix": None,
        "report": None,
    }
    if synthesis_backend:
        backend_config = ModelBackendConfig(
            backend=synthesis_backend,
            timeout=backend_timeout,
            retries=backend_retries,
        )
        attach_decision_briefing_packet(
            candidate_map,
            scaffold,
            question=question,
            backend_config=backend_config,
        )
        final_outputs = write_final_reader_outputs(
            rendered=brief,
            scaffold=scaffold,
            prioritized_map=candidate_map,
            artifacts=artifacts,
            backend_config=backend_config,
        )
        synthesized_paths = {
            "briefing": final_outputs.get("briefing_path"),
            "appendix": final_outputs.get("evidence_appendix_path"),
            "report": final_outputs.get("summary_paths", {}).get("reader_memo_rewrite_report"),
        }
    return DecisionModelSliceResult(
        decision_model_path=decision_model_path,
        briefing_path=briefing_path,
        eval_path=eval_path,
        status=str(eval_report.get("status", "unknown")),
        synthesized_briefing_path=synthesized_paths["briefing"],
        synthesized_appendix_path=synthesized_paths["appendix"],
        synthesis_report_path=synthesized_paths["report"],
    )


def _require_concrete_question(question: str) -> None:
    report = question_quality_report(question)
    if report["status"] == "blocked":
        issues = "; ".join(str(issue.get("message", issue.get("issue_type", "question issue"))) for issue in report.get("issues", []))
        raise ValueError(f"decision model slice requires a concrete decision question: {issues}")


def _current_read(decision_model: dict[str, Any], deterministic_payload: dict[str, Any]) -> str:
    brief = str(deterministic_payload.get("decision_brief", "")).strip()
    if brief:
        return _first_sentence(brief)
    default = _default_answer(decision_model)
    classification = str(default.get("classification", "mixed_or_context_dependent")).replace("_", " ")
    return str(default.get("plain_language_instruction", "")).strip() or f"The map supports a {classification} read."


def _default_answer(decision_model: dict[str, Any]) -> dict[str, Any]:
    return decision_model.get("default_answer", {}) if isinstance(decision_model.get("default_answer"), dict) else {}


def _confidence(quality_report: dict[str, Any], scaffold: dict[str, Any]) -> str:
    candidate = str(scaffold.get("confidence_cap") or confidence_cap(quality_report) or "medium").lower()
    return candidate if candidate in {"low", "medium", "high"} else "medium"


def _items_from_cluster_rows(rows: Any, claim_lookup: dict[str, dict[str, Any]]) -> list[DecisionModelItem]:
    items: list[DecisionModelItem] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        claim_ids = _canonical_claim_ids(
            [
                str(claim.get("claim_id"))
                for claim in row.get("representative_claims", [])
                if isinstance(claim, dict) and str(claim.get("claim_id", "")).strip()
            ],
            claim_lookup,
            [
                str(claim.get("claim"))
                for claim in row.get("representative_claims", [])
                if isinstance(claim, dict) and str(claim.get("claim", "")).strip()
            ],
        )
        items.append(
            DecisionModelItem(
                statement=str(row.get("proposition", "")).strip() or _claim_statement(claim_ids, claim_lookup),
                why_it_matters=f"Evidence weight: {row.get('evidence_weight', 'medium')}.",
                claim_ids=claim_ids,
                source_ids=_source_ids_for_claims(claim_ids, claim_lookup),
                confidence=_confidence_from_weight(str(row.get("evidence_weight", "medium"))),
            )
        )
    return [item for item in items if item.statement]


def _counter_items(decision_model: dict[str, Any], claim_lookup: dict[str, dict[str, Any]]) -> list[DecisionModelItem]:
    items = _items_from_cluster_rows(decision_model.get("strongest_counterarguments", []), claim_lookup)
    return _dedupe_items(items)


def _scope_items(scaffold: dict[str, Any], decision_model: dict[str, Any], claim_lookup: dict[str, dict[str, Any]]) -> list[DecisionModelItem]:
    items = _ledger_items(scaffold, "scope_limits", claim_lookup)
    for key, prefix in (("holds_for", "Holds for"), ("does_not_hold_for", "Does not hold for")):
        for value in decision_model.get(key, []) if isinstance(decision_model.get(key), list) else []:
            statement = str(value).strip()
            if statement:
                claim_ids = _canonical_claim_ids([], claim_lookup, [statement])
                if claim_ids:
                    items.append(
                        DecisionModelItem(
                            statement=f"{prefix}: {statement}",
                            why_it_matters="This bounds the decision read.",
                            claim_ids=claim_ids,
                            source_ids=_source_ids_for_claims(claim_ids, claim_lookup),
                        )
                    )
    return _dedupe_items(items)


def _crux_items(candidate_map: dict[str, Any], claim_lookup: dict[str, dict[str, Any]]) -> list[DecisionModelItem]:
    items: list[DecisionModelItem] = []
    relation_lookup = {str(relation.get("relation_id", "")): relation for relation in _relations(candidate_map)}
    for relation_id, relation in relation_lookup.items():
        relation_type = str(relation.get("relation_type", ""))
        if relation_type not in {"crux_for", "in_tension_with", "challenges", "depends_on"}:
            continue
        claim_ids = _dedupe([_relation_claim_id(relation, "source"), _relation_claim_id(relation, "target")])
        statement = _relation_statement(relation, claim_lookup) or str(relation.get("rationale", "")).strip() or relation_type.replace("_", " ")
        items.append(
            DecisionModelItem(
                statement=statement,
                why_it_matters=_relation_why_it_matters(relation),
                claim_ids=claim_ids,
                source_ids=_source_ids_for_claims(claim_ids, claim_lookup),
                relation_ids=[relation_id],
                confidence=_relation_confidence(relation),
            )
        )
    return _dedupe_items(items)


def _confidence_drivers(scaffold: dict[str, Any], quality_report: dict[str, Any]) -> list[DecisionModelItem]:
    items = [
        DecisionModelItem(
            statement=f"Confidence is capped at {_confidence(quality_report, scaffold)} by the map quality report.",
            why_it_matters="The brief should keep certainty within what the map supports.",
        )
    ]
    for issue in quality_report.get("issues", []) if isinstance(quality_report.get("issues"), list) else []:
        if isinstance(issue, dict):
            message = str(issue.get("message") or issue.get("issue_type") or "").strip()
            if message:
                items.append(DecisionModelItem(statement=message, why_it_matters=str(issue.get("severity", "quality issue"))))
    return _dedupe_items(items)


def _missing_evidence(scaffold: dict[str, Any]) -> list[DecisionModelItem]:
    report = _sufficiency_report(scaffold)
    items: list[DecisionModelItem] = []
    for slot in report.get("missing_expected_decision_slots", []) if isinstance(report.get("missing_expected_decision_slots"), list) else []:
        items.append(DecisionModelItem(statement=reader_facing_unresolved_slot(str(slot)), why_it_matters="Leave this gap explicit unless source-backed evidence fills it."))
    for family in report.get("missing_expected_evidence_families", []) if isinstance(report.get("missing_expected_evidence_families"), list) else []:
        items.append(DecisionModelItem(statement=reader_facing_unresolved_family(str(family)), why_it_matters="State that this evidence remains unassessed."))
    return _dedupe_items(items)


def _decision_implications(deterministic_payload: dict[str, Any], decision_model: dict[str, Any]) -> list[DecisionModelItem]:
    values = []
    values.extend(deterministic_payload.get("decision_implications", []) if isinstance(deterministic_payload.get("decision_implications"), list) else [])
    values.extend(decision_model.get("practical_recommendations", []) if isinstance(decision_model.get("practical_recommendations"), list) else [])
    return _dedupe_items([DecisionModelItem(statement=str(value).strip(), why_it_matters="Practical implication derived from mapped evidence.") for value in values if str(value).strip()])


def _ledger_items(scaffold: dict[str, Any], section: str, claim_lookup: dict[str, dict[str, Any]]) -> list[DecisionModelItem]:
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    rows_by_section = ledger.get("top_evidence_by_section", {}) if isinstance(ledger.get("top_evidence_by_section"), dict) else {}
    rows = rows_by_section.get(section, []) if isinstance(rows_by_section.get(section), list) else []
    items: list[DecisionModelItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        claim_id = str(row.get("claim_id", "")).strip()
        claim_ids = _canonical_claim_ids([claim_id], claim_lookup, [str(row.get("claim", ""))])
        items.append(
            DecisionModelItem(
                statement=str(row.get("claim", "")).strip(),
                why_it_matters=f"{section.replace('_', ' ')}; weight {row.get('weight', 'medium')}.",
                claim_ids=claim_ids,
                source_ids=_source_ids_for_claims(claim_ids, claim_lookup),
                confidence=_confidence_from_weight(str(row.get("weight", "medium"))),
            )
        )
    return [item for item in items if item.statement]


def _item_section(title: str, items: list[DecisionModelItem], *, empty: str) -> list[str]:
    lines = ["", f"## {title}", ""]
    if not items:
        return [*lines, f"- {empty}"]
    for item in items:
        suffix = _anchor_suffix(item)
        why = f" {item.why_it_matters}" if item.why_it_matters else ""
        lines.append(f"- {item.statement}{suffix}{why}")
    return lines


def _anchor_suffix(item: DecisionModelItem) -> str:
    anchors = [*item.source_ids[:2], *item.claim_ids[:2], *item.relation_ids[:1]]
    return f" ({', '.join(anchors)})" if anchors else ""


def _unsupported_evidence_item_count(model: CompactDecisionModelOutput) -> int:
    anchored_sections = [*model.top_support, *model.top_counterevidence_or_tensions, *model.top_scope_boundaries, *model.top_cruxes]
    return sum(1 for item in anchored_sections if not (item.claim_ids or item.source_ids or item.relation_ids))


def _sufficiency_report(scaffold: dict[str, Any]) -> dict[str, Any]:
    return scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}


def _source_ids_for_claims(claim_ids: list[str], claim_lookup: dict[str, dict[str, Any]]) -> list[str]:
    return _dedupe([str(claim_lookup.get(claim_id, {}).get("source_id", "")).strip() for claim_id in claim_ids])


def _canonical_claim_ids(raw_ids: list[str], claim_lookup: dict[str, dict[str, Any]], raw_texts: list[str]) -> list[str]:
    claim_ids: list[str] = []
    for raw_id in raw_ids:
        if raw_id in claim_lookup:
            claim_ids.append(raw_id)
            continue
        matched = _claim_id_for_text(raw_id, claim_lookup)
        if matched:
            claim_ids.append(matched)
    for text in raw_texts:
        matched = _claim_id_for_text(text, claim_lookup)
        if matched:
            claim_ids.append(matched)
    return _dedupe(claim_ids)


def _claim_id_for_text(text: str, claim_lookup: dict[str, dict[str, Any]]) -> str:
    normalized = _normalize_claim_text(text)
    if not normalized:
        return ""
    for claim_id, claim in claim_lookup.items():
        claim_text = str(claim.get("claim") or claim.get("text") or "")
        if _normalize_claim_text(claim_text) == normalized:
            return claim_id
    for claim_id, claim in claim_lookup.items():
        claim_text = _normalize_claim_text(str(claim.get("claim") or claim.get("text") or ""))
        if claim_text and (claim_text in normalized or normalized in claim_text):
            return claim_id
    return ""


def _normalize_claim_text(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _claim_statement(claim_ids: list[str], claim_lookup: dict[str, dict[str, Any]]) -> str:
    for claim_id in claim_ids:
        claim = claim_lookup.get(claim_id, {})
        text = str(claim.get("claim") or claim.get("text") or "").strip()
        if text:
            return text
    return ""


def _relation_claim_id(relation: dict[str, Any], side: str) -> str:
    return str(relation.get(f"{side}_claim") or relation.get(f"{side}_claim_id") or "").strip()


def _relation_statement(relation: dict[str, Any], claim_lookup: dict[str, dict[str, Any]]) -> str:
    source = _first_sentence(_claim_statement([_relation_claim_id(relation, "source")], claim_lookup), max_chars=120)
    target = _first_sentence(_claim_statement([_relation_claim_id(relation, "target")], claim_lookup), max_chars=120)
    if not source or not target:
        return ""
    return f"Source claim: {source} Relationship: {_relation_phrase(str(relation.get('relation_type', '')))}. Target claim: {target}"


def _relation_phrase(relation_type: str) -> str:
    return {
        "supports": "supports",
        "challenges": "pushes against",
        "refines": "narrows",
        "similar_to": "tracks similar evidence to",
        "depends_on": "depends on",
        "crux_for": "is a crux for",
        "in_tension_with": "is in tension with",
    }.get(relation_type, relation_type.replace("_", " "))


def _relation_why_it_matters(relation: dict[str, Any]) -> str:
    relation_type = str(relation.get("relation_type", "")).replace("_", " ")
    rationale = str(relation.get("rationale", "")).strip()
    if rationale and not re.search(r"\bclaim\s+[ab]\b", rationale, flags=re.IGNORECASE):
        return rationale
    return f"Map relation type: {relation_type}."


def _relation_confidence(relation: dict[str, Any]) -> str:
    confidence = str(relation.get("relation_confidence") or relation.get("confidence") or "medium").lower()
    return confidence if confidence in {"low", "medium", "high"} else "medium"


def _confidence_from_weight(weight: str) -> str:
    return weight if weight in {"low", "medium", "high"} else "medium"


def _first_sentence(text: str, max_chars: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    match = re.search(r"(?<=[.!?])\s+", compact)
    first = compact[: match.start()].strip() if match else compact
    return first if len(first) <= max_chars else first[: max_chars - 3].rstrip(" ,.;") + "..."


def _term_count(text: str, terms: tuple[str, ...]) -> int:
    return sum(text.count(term) for term in terms)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _dedupe_items(items: list[DecisionModelItem]) -> list[DecisionModelItem]:
    seen: set[str] = set()
    result: list[DecisionModelItem] = []
    for item in items:
        key = re.sub(r"\W+", " ", item.statement.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _resolve(repo_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root / candidate
