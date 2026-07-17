from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    short_text as _short_text,
    string_list as _string_list,
)


def build_reader_judgment_packet(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    """Project upstream analyst judgments into reader-visible writing obligations.

    This packet does not add semantic judgment. It makes already-computed analyst
    judgments explicit enough for section prompts and telemetry to track whether
    the memo surfaced them.
    """

    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    judgments: list[dict[str, Any]] = []
    judgments.extend(_bottom_line_and_confidence(packet))
    judgments.extend(_source_weighting_judgments(packet))
    judgments.extend(_counterweight_judgments(packet))
    judgments.extend(_decision_usefulness_judgments(packet))
    judgments.extend(_lightweight_guidance_judgments(packet))
    judgments.extend(_excluded_or_deemphasized_judgments(packet))
    deduped = _dedupe_judgments(judgments)
    return {
        "schema_id": "reader_judgment_packet_v1",
        "decision_question": packet.get("decision_question"),
        "policy": [
            "Surface the smallest useful set of analyst judgments in reader-facing prose.",
            "Do not expose packet IDs or internal telemetry in the memo body.",
            "Use the trace fields only for audit and coverage checks.",
        ],
        "judgments": deduped,
        "target_section_counts": _section_counts(deduped),
    }


def compact_reader_judgments_for_section(
    reader_judgment_packet: dict[str, Any] | None,
    section_id: str,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    packet = _dict(reader_judgment_packet)
    section = str(section_id or "").strip()
    aliases = _section_aliases(section)
    rows = []
    for row in _list(packet.get("judgments")):
        if not isinstance(row, dict):
            continue
        target = str(row.get("target_section") or "").strip()
        if target not in aliases:
            continue
        rows.append(_compact_judgment(row))
    return rows[:limit]


def build_reader_judgment_surface_report(memo: str, packet: dict[str, Any]) -> dict[str, Any]:
    canonical = _dict(packet.get("canonical_decision_writer_packet")) or packet
    judgment_packet = (
        _dict(canonical.get("reader_judgment_packet"))
        or _dict(packet.get("reader_judgment_packet"))
        or build_reader_judgment_packet(canonical)
    )
    if not judgment_packet:
        return {
            "schema_id": "reader_judgment_surface_report_v1",
            "status": "not_available",
            "judgment_count": 0,
            "surfaced_count": 0,
            "missing_count": 0,
            "issues": [],
        }
    statuses = [_judgment_surface_status(memo, row) for row in _list(judgment_packet.get("judgments")) if isinstance(row, dict)]
    issues = [row for row in statuses if row.get("priority") == "high" and not row.get("surfaced")]
    return {
        "schema_id": "reader_judgment_surface_report_v1",
        "status": "ready" if not issues else "warning",
        "judgment_count": len(statuses),
        "high_priority_judgment_count": sum(1 for row in statuses if row.get("priority") == "high"),
        "surfaced_count": sum(1 for row in statuses if row.get("surfaced")),
        "missing_count": len(issues),
        "statuses": statuses,
        "issues": issues,
    }


def _bottom_line_and_confidence(packet: dict[str, Any]) -> list[dict[str, Any]]:
    skeleton = _dict(packet.get("decision_brief_skeleton"))
    balanced = _dict(packet.get("balanced_answer_frame"))
    analyst = _dict(packet.get("analyst_reasoning_frame"))
    bluf = _dict(packet.get("bluf_contract"))
    rows = []
    bottom_line = _first_text(
        bluf.get("recommended_read"),
        bluf.get("one_sentence_version"),
        balanced.get("best_current_read"),
        skeleton.get("direct_answer"),
        analyst.get("bottom_line"),
    )
    if bottom_line:
        rows.append(
            _judgment(
                "bottom_line_judgment",
                "opening_context",
                bottom_line,
                why_surface="The reader needs the controlled answer frame before interpreting evidence.",
                priority="high",
                search_text=[bottom_line],
            )
        )
    confidence = _first_text(skeleton.get("confidence"), balanced.get("confidence"), analyst.get("confidence"))
    confidence_basis = _first_text(
        skeleton.get("confidence_basis"),
        balanced.get("confidence_basis"),
        *_string_list(analyst.get("confidence_reasons")),
    )
    if confidence or confidence_basis:
        rows.append(
            _judgment(
                "confidence_rationale",
                "source_weighting",
                _join_parts([f"Confidence: {confidence}" if confidence else "", confidence_basis]),
                why_surface="The memo should explain why the answer is as strong or limited as it is.",
                priority="high",
                search_text=[confidence, confidence_basis],
            )
        )
    return rows


def _source_weighting_judgments(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    frame = _dict(packet.get("source_weighted_answer_frame"))
    lanes = _dict(frame.get("lanes"))
    lane_targets = {
        "primary_answer_drivers": ("evidence_drivers", "answer_evidence", "This evidence carries the answer."),
        "quantitative_or_interpretive_calibrators": ("calibrators", "answer_evidence", "This evidence calibrates magnitude or interpretation."),
        "counterweights_or_tensions": ("counterweights", "counterweights", "This evidence bounds or weakens the answer."),
        "scope_limiters": ("scope_boundaries", "counterweights", "This evidence defines where the answer stops applying."),
        "decision_cruxes": ("decision_cruxes", "counterweights", "This evidence identifies what would change the answer."),
        "context_only": ("contextual_evidence", "practical_implication", "This evidence contextualizes application rather than carrying the answer."),
    }
    for lane, lane_rows in lanes.items():
        kind, section, default_why = lane_targets.get(str(lane), ("source_weighting", "source_weighting", "This evidence has a source-weighting role."))
        for item in _list(lane_rows)[:4]:
            if not isinstance(item, dict):
                continue
            claim = _first_text(item.get("claim"), item.get("why_this_weight"), item.get("decision_relevance"))
            if not claim:
                continue
            use_contract = _judgment_use_contract(kind, lane=str(lane), row=item)
            rows.append(
                _judgment(
                    kind,
                    section,
                    claim,
                    source_ids=_string_list(item.get("source_ids")),
                    evidence_item_ids=_string_list(item.get("evidence_item_ids") or item.get("item_id")),
                    why_surface=_first_text(item.get("why_this_weight"), item.get("decision_relevance"), default_why),
                    priority="high" if kind in {"evidence_drivers", "counterweights", "scope_boundaries"} else "medium",
                    allowed_use=use_contract["allowed_use"],
                    not_enough_for=use_contract["not_enough_for"],
                    search_text=[claim, item.get("why_this_weight"), *_quantity_values(item)],
                )
            )
    for source in _list(packet.get("source_weight_judgments"))[:8]:
        if not isinstance(source, dict):
            continue
        judgment_text = _first_text(source.get("why_weight_this_way"), source.get("reader_facing_limit"), source.get("main_use"))
        if not judgment_text:
            continue
        rows.append(
            _judgment(
                "source_weighting",
                "source_weighting",
                judgment_text,
                source_ids=_string_list(source.get("source_ids")),
                evidence_item_ids=_string_list(source.get("evidence_item_ids")),
                why_surface="The reader should know how much work this source can do in the answer.",
                priority="medium",
                allowed_use=_source_judgment_allowed_use(source),
                not_enough_for=_source_judgment_not_enough_for(source),
                search_text=[judgment_text, source.get("main_use"), source.get("reader_facing_limit")],
            )
        )
    return rows


def _counterweight_judgments(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    analyst = _dict(packet.get("analyst_reasoning_frame"))
    if analyst.get("counterweight_weighting"):
        rows.append(
            _judgment(
                "counterweight_disposition",
                "counterweights",
                analyst.get("counterweight_weighting"),
                why_surface="The memo should say whether counterweights overturn, bound, weaken, or merely calibrate the answer.",
                priority="high",
                allowed_use="Use this to state what the limiting evidence does to the answer.",
                not_enough_for=["Independent support for the main answer."],
                search_text=[analyst.get("counterweight_weighting")],
            )
        )
    for row in _list(packet.get("counterweight_dispositions"))[:6]:
        if not isinstance(row, dict):
            continue
        judgment_text = _join_parts([row.get("claim"), row.get("disposition"), row.get("disposition_rationale")])
        if not judgment_text:
            continue
        rows.append(
            _judgment(
                "counterweight_disposition",
                "counterweights",
                judgment_text,
                source_ids=_string_list(row.get("source_ids") or row.get("source_labels")),
                evidence_item_ids=_string_list(row.get("item_id")),
                why_surface="The reader needs to know what this limitation does to the answer.",
                priority="high",
                allowed_use="Use this to bound, weaken, qualify, or create a crux for the answer.",
                not_enough_for=_dedupe(
                    [
                        *_string_list(row.get("not_enough_for")),
                        "Broad support for the answer.",
                    ]
                ),
                search_text=[row.get("claim"), row.get("disposition"), row.get("disposition_rationale"), *_quantity_values(row)],
            )
        )
    return rows


def _decision_usefulness_judgments(packet: dict[str, Any]) -> list[dict[str, Any]]:
    usefulness = _dict(packet.get("decision_usefulness_packet"))
    rows = []
    stance = _dict(usefulness.get("recommended_stance"))
    if stance:
        stance_text = _join_parts([stance.get("stance"), stance.get("scope"), stance.get("why_this_stance")])
        if stance_text:
            rows.append(
                _judgment(
                    "practical_stance",
                    "practical_implication",
                    stance_text,
                    source_ids=_string_list(stance.get("source_ids")),
                    evidence_item_ids=_string_list(stance.get("evidence_item_ids")),
                    why_surface="The memo should translate the answer into a usable stance.",
                    priority="high",
                    search_text=[stance.get("stance"), stance.get("scope"), stance.get("why_this_stance")],
                )
            )
    for row in _list(usefulness.get("tradeoffs"))[:4]:
        if not isinstance(row, dict):
            continue
        text = _join_parts([row.get("tradeoff"), row.get("choose_a_if"), row.get("choose_b_if")])
        if text:
            rows.append(
                _judgment(
                    "decision_tradeoff",
                    "practical_implication",
                    text,
                    source_ids=_string_list(row.get("source_ids")),
                    evidence_item_ids=_string_list(row.get("evidence_item_ids")),
                    why_surface="The reader should see the choice or value tradeoff created by the evidence.",
                    priority="high",
                    search_text=[row.get("tradeoff"), row.get("choose_a_if"), row.get("choose_b_if")],
                )
            )
    for row in _list(usefulness.get("cruxes_and_thresholds"))[:4]:
        if not isinstance(row, dict):
            continue
        text = _join_parts([row.get("crux"), row.get("current_read"), row.get("threshold"), row.get("would_change_if")])
        if text:
            rows.append(
                _judgment(
                    "decision_crux",
                    "counterweights",
                    text,
                    source_ids=_string_list(row.get("source_ids")),
                    evidence_item_ids=_string_list(row.get("evidence_item_ids")),
                    why_surface="The reader should know what would change the answer.",
                    priority="high",
                    search_text=[row.get("crux"), row.get("threshold"), row.get("would_change_if")],
                )
            )
    for row in _list(usefulness.get("monitoring_triggers"))[:4]:
        if not isinstance(row, dict):
            continue
        text = _join_parts([row.get("trigger"), row.get("would_update")])
        if text:
            rows.append(
                _judgment(
                    "update_trigger",
                    "practical_implication",
                    text,
                    source_ids=_string_list(row.get("source_ids")),
                    evidence_item_ids=_string_list(row.get("evidence_item_ids")),
                    why_surface="The reader should know what future evidence or condition would change the memo.",
                    priority="medium",
                    search_text=[row.get("trigger"), row.get("would_update")],
                )
            )
    return rows


def _lightweight_guidance_judgments(packet: dict[str, Any]) -> list[dict[str, Any]]:
    guidance = _dict(packet.get("lightweight_writer_guidance"))
    rows = []
    if guidance.get("overall_judgment"):
        rows.append(
            _judgment(
                "writing_judgment",
                "answer_evidence",
                guidance.get("overall_judgment"),
                why_surface="The writer guidance identifies the reader-facing analytical emphasis.",
                priority="medium",
                search_text=[guidance.get("overall_judgment")],
            )
        )
    for caveat in _list(guidance.get("evidence_quality_caveats"))[:4]:
        if not isinstance(caveat, dict):
            continue
        text = _first_text(caveat.get("caveat"), caveat.get("safe_wording"))
        if text:
            rows.append(
                _judgment(
                    "evidence_quality_caveat",
                    "source_weighting",
                    text,
                    source_ids=_string_list(caveat.get("source_ids")),
                    why_surface="Evidence quality caveats should be concrete rather than generic.",
                    priority="medium",
                    search_text=[text],
                )
            )
    for risk in _list(guidance.get("quantity_wording_risks"))[:4]:
        if not isinstance(risk, dict):
            continue
        text = _join_parts([risk.get("risk"), risk.get("safe_wording")])
        if text:
            rows.append(
                _judgment(
                    "quantity_wording_risk",
                    "answer_evidence",
                    text,
                    source_ids=_string_list(risk.get("source_ids")),
                    why_surface="Quantity endpoints need to stay distinct in the memo.",
                    priority="medium",
                    search_text=[risk.get("risk"), risk.get("safe_wording"), *_string_list(risk.get("quantities"))],
                )
            )
    return rows


def _excluded_or_deemphasized_judgments(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(_dict(packet.get("writer_decision_interface")).get("excluded_evidence_log"))[:6]:
        if not isinstance(row, dict):
            continue
        text = _first_text(row.get("reason_excluded"), row.get("claim"), row.get("statement"))
        if text:
            rows.append(
                _judgment(
                    "excluded_or_deemphasized_evidence",
                    "source_weighting",
                    text,
                    source_ids=_string_list(row.get("source_ids")),
                    evidence_item_ids=_string_list(row.get("item_id")),
                    why_surface="The trace should preserve why nearby evidence did not carry the answer.",
                    priority="low",
                    search_text=[text],
                )
            )
    return rows


def _judgment(
    judgment_type: str,
    target_section: str,
    judgment: Any,
    *,
    why_surface: str,
    source_ids: list[str] | None = None,
    evidence_item_ids: list[str] | None = None,
    priority: str = "medium",
    allowed_use: str = "",
    not_enough_for: list[str] | None = None,
    search_text: list[Any] | None = None,
) -> dict[str, Any]:
    text = _short_text(str(judgment or "").strip(), 700)
    return {
        "judgment_id": "",
        "judgment_type": judgment_type,
        "target_section": target_section,
        "priority": priority,
        "judgment": text,
        "why_surface": _short_text(why_surface, 360),
        "allowed_use": _short_text(allowed_use, 360),
        "not_enough_for": _dedupe(not_enough_for or []),
        "source_ids": _dedupe(source_ids or []),
        "evidence_item_ids": _dedupe(evidence_item_ids or []),
        "search_terms": _search_terms([text, *(search_text or [])]),
    }


def _dedupe_judgments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen: set[str] = set()
    for row in rows:
        text = str(row.get("judgment") or "").strip()
        if not text:
            continue
        key = f"{row.get('judgment_type')}::{row.get('target_section')}::{_norm(text)[:220]}"
        if key in seen:
            continue
        seen.add(key)
        item = _compact_judgment(row)
        item["judgment_id"] = f"J{len(deduped) + 1:03d}_{str(item.get('judgment_type') or 'judgment').upper()}"
        deduped.append(item)
    return deduped[:32]


def _compact_judgment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "judgment_id": row.get("judgment_id"),
            "judgment_type": row.get("judgment_type"),
            "target_section": row.get("target_section"),
            "priority": row.get("priority"),
            "judgment": _short_text(row.get("judgment"), 520),
            "why_surface": _short_text(row.get("why_surface"), 260),
            "allowed_use": _optional_short_text(row.get("allowed_use"), 260),
            "not_enough_for": _string_list(row.get("not_enough_for"))[:6],
            "source_ids": _string_list(row.get("source_ids"))[:6],
            "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:6],
            "search_terms": _string_list(row.get("search_terms"))[:8],
        }.items()
        if value not in ("", None, [], {})
    }


def _judgment_surface_status(memo: str, row: dict[str, Any]) -> dict[str, Any]:
    memo_norm = _norm(memo)
    terms = _string_list(row.get("search_terms"))
    hits = [term for term in terms if _term_present(memo_norm, term)]
    source_ids = _string_list(row.get("source_ids"))
    source_hits = [source_id for source_id in source_ids if source_id and source_id in memo]
    enough_text = len(hits) >= 2 or (len(hits) >= 1 and (not source_ids or source_hits))
    return {
        "judgment_id": row.get("judgment_id"),
        "judgment_type": row.get("judgment_type"),
        "target_section": row.get("target_section"),
        "priority": row.get("priority"),
        "surfaced": bool(enough_text),
        "matched_terms": hits[:6],
        "source_ids_present": source_hits[:6],
        "judgment": row.get("judgment"),
    }


def _term_present(memo_norm: str, term: str) -> bool:
    normalized = _norm(term)
    if not normalized:
        return False
    if len(normalized) <= 4:
        return re.search(rf"\b{re.escape(normalized)}\b", memo_norm) is not None
    return normalized in memo_norm


def _search_terms(values: list[Any]) -> list[str]:
    terms: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        terms.extend(_explicit_terms(text))
        terms.extend(_content_ngrams(text))
    return _dedupe(terms)[:10]


def _explicit_terms(text: str) -> list[str]:
    terms = []
    for match in re.findall(r"\b\d+(?:\.\d+)?(?:\s*%|\s*(?:mg/dL|g/day|per day|CI|HR|RR|OR))?\b", text, flags=re.IGNORECASE):
        if match.strip():
            terms.append(match.strip())
    for phrase in ("medium", "low confidence", "high confidence", "bounds", "does not overturn", "overturn", "scope", "tradeoff", "monitor"):
        if phrase in text.lower():
            terms.append(phrase)
    return terms


def _content_ngrams(text: str) -> list[str]:
    words = [
        word
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text.lower())
        if word not in _STOPWORDS
    ]
    grams = []
    if len(words) >= 3:
        grams.append(" ".join(words[:3]))
    if len(words) >= 5:
        grams.append(" ".join(words[:5]))
    return grams


def _section_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        section = str(row.get("target_section") or "unknown")
        counts[section] = counts.get(section, 0) + 1
    return counts


def _section_aliases(section_id: str) -> set[str]:
    normalized = section_id.strip()
    aliases = {normalized}
    if normalized == "answer_evidence":
        aliases.update({"answer_evidence", "opening_context"})
    if normalized == "source_weighting":
        aliases.update({"source_weighting", "opening_context"})
    if normalized == "counterweights":
        aliases.update({"counterweights", "limiting evidence", "limits", "boundaries"})
    if normalized == "practical_implication":
        aliases.update({"practical_implication", "practical implication", "how to use this read"})
    return aliases


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _optional_short_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return _short_text(text, limit) if text else ""


def _join_parts(parts: list[Any]) -> str:
    return _short_text("; ".join(str(part).strip() for part in parts if str(part or "").strip()), 700)


def _quantity_values(row: dict[str, Any]) -> list[str]:
    values = []
    for quantity in _list(row.get("quantities")):
        if isinstance(quantity, dict):
            values.extend(_string_list(quantity.get("value")))
        else:
            values.extend(_string_list(quantity))
    return values


def _judgment_use_contract(kind: str, *, lane: str, row: dict[str, Any]) -> dict[str, Any]:
    existing_limits = _string_list(row.get("not_enough_for"))
    if kind == "evidence_drivers":
        return {
            "allowed_use": "Use this to carry the main answer.",
            "not_enough_for": existing_limits,
        }
    if kind == "calibrators":
        return {
            "allowed_use": "Use this to calibrate magnitude, mechanism, or plausibility while keeping its endpoint and design limits attached.",
            "not_enough_for": _dedupe(
                [
                    *existing_limits,
                    "Direct outcome evidence by itself.",
                    "A recommendation beyond the measured endpoint by itself.",
                ]
            ),
        }
    if kind in {"counterweights", "scope_boundaries"}:
        return {
            "allowed_use": "Use this to bound, narrow, or stress-test the answer.",
            "not_enough_for": _dedupe(
                [
                    *existing_limits,
                    "Broad support for the main answer.",
                    "Application outside the stated scope.",
                ]
            ),
        }
    if kind == "decision_crux":
        return {
            "allowed_use": "Use this to state what would change the answer.",
            "not_enough_for": _dedupe([*existing_limits, "Settled evidence when framed as a crux."]),
        }
    if kind == "contextual_evidence":
        return {
            "allowed_use": "Use this for application context or interpretation.",
            "not_enough_for": _dedupe([*existing_limits, "Independent evidence for the main answer."]),
        }
    return {
        "allowed_use": _first_text(row.get("how_to_use"), f"Use this according to its {str(lane).replace('_', ' ')} source role."),
        "not_enough_for": existing_limits,
    }


def _source_judgment_allowed_use(source: dict[str, Any]) -> str:
    main_use = str(source.get("main_use") or "").lower()
    if "drive" in main_use or "support" in main_use:
        return "Use this source to carry the main answer only for the claims it directly supports."
    if "calibrat" in main_use or "interpret" in main_use:
        return "Use this source to calibrate magnitude, mechanism, or interpretation while keeping endpoint limits visible."
    if "bound" in main_use or "counter" in main_use or "limit" in main_use:
        return "Use this source to bound, narrow, or stress-test the answer."
    if "context" in main_use:
        return "Use this source for context or application rather than as independent answer support."
    return "Use this source only for the role assigned by the analyst source hierarchy."


def _source_judgment_not_enough_for(source: dict[str, Any]) -> list[str]:
    limits = _string_list(source.get("what_not_to_use_it_for") or source.get("limits"))
    main_use = str(source.get("main_use") or "").lower()
    if "calibrat" in main_use or "interpret" in main_use:
        limits.extend(
            [
                "Direct outcome evidence by itself.",
                "A recommendation beyond the measured endpoint by itself.",
            ]
        )
    if "bound" in main_use or "counter" in main_use or "limit" in main_use:
        limits.append("Broad support for the main answer.")
    if "context" in main_use:
        limits.append("Independent answer support.")
    return _dedupe(limits)


_STOPWORDS = {
    "about",
    "above",
    "after",
    "answer",
    "because",
    "before",
    "being",
    "between",
    "claim",
    "could",
    "decision",
    "evidence",
    "from",
    "have",
    "into",
    "only",
    "reader",
    "should",
    "source",
    "that",
    "their",
    "there",
    "this",
    "where",
    "which",
    "with",
    "would",
}
