from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_quantity_retention import contains_quantity


def build_source_bound_evidence_atoms(rows: list[dict[str, Any]], *, limit: int = 16) -> list[dict[str, Any]]:
    atoms = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        atom = _source_bound_atom(row)
        if atom:
            atoms.append(atom)
    return _dedupe_atoms(atoms)[:limit]


def build_source_binding_report(
    memo: str,
    packet: dict[str, Any],
    *,
    source_aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    atoms = collect_packet_source_bound_atoms(packet)
    invalid_tuples = [
        tuple_row
        for atom in atoms
        for tuple_row in _list(atom.get("excluded_quantity_tuples"))
        if isinstance(tuple_row, dict)
    ]
    sentence_warnings = _quantity_sentence_source_warnings(
        memo,
        atoms,
        source_aliases=source_aliases or {},
    )
    ambiguous = _ambiguous_quantity_surfaces(atoms)
    warnings = [*invalid_tuples, *sentence_warnings, *ambiguous]
    return {
        "schema_id": "source_binding_report_v1",
        "status": "ready" if not warnings else "warning",
        "source_bound_atom_count": len(atoms),
        "invalid_quantity_tuple_count": len(invalid_tuples),
        "quantity_source_adjacency_warning_count": len(sentence_warnings),
        "ambiguous_quantity_surface_count": len(ambiguous),
        "warning_count": len(warnings),
        "invalid_quantity_tuples": invalid_tuples[:24],
        "quantity_source_adjacency_warnings": sentence_warnings[:24],
        "ambiguous_quantity_surfaces": ambiguous[:24],
    }


def collect_packet_source_bound_atoms(packet: dict[str, Any], *, limit: int = 240) -> list[dict[str, Any]]:
    canonical = packet.get("canonical_decision_writer_packet") if isinstance(packet.get("canonical_decision_writer_packet"), dict) else {}
    rows: list[dict[str, Any]] = quantity_binding_rows(packet)
    for key in (
        "priority_evidence",
        "counterweight_dispositions",
        "scope_boundaries",
        "decision_cruxes",
        "mandatory_retention_checklist",
    ):
        rows.extend(row for row in _list(canonical.get(key)) if isinstance(row, dict))
    inventory = canonical.get("organized_evidence_inventory") if isinstance(canonical.get("organized_evidence_inventory"), dict) else {}
    lanes = inventory.get("lanes") if isinstance(inventory.get("lanes"), dict) else {}
    for lane_rows in lanes.values():
        rows.extend(row for row in _list(lane_rows) if isinstance(row, dict))
    rows.extend(row for row in _list(packet.get("evidence_items")) if isinstance(row, dict))
    rows.extend(row for row in _list(packet.get("memo_obligations")) if isinstance(row, dict))
    return build_source_bound_evidence_atoms(rows, limit=limit)


def quantity_binding_rows(packet: dict[str, Any], *, source_ids: list[str] | None = None) -> list[dict[str, Any]]:
    report = packet.get("analyst_quantity_binding_report") if isinstance(packet.get("analyst_quantity_binding_report"), dict) else {}
    allowed_sources = set(source_ids or [])
    rows = []
    for key in ("must_retain_bindings", "approved_bindings"):
        for binding in _list(report.get(key)):
            if not isinstance(binding, dict):
                continue
            binding_sources = _string_list(binding.get("source_ids"))
            if allowed_sources and not allowed_sources.intersection(binding_sources):
                continue
            if str(binding.get("memo_use") or "yes").lower() not in {"yes", "must_use", "use"}:
                continue
            value = str(binding.get("value") or "").strip()
            if not value:
                continue
            rows.append(
                _drop_empty(
                    {
                        "item_id": binding.get("candidate_id") or binding.get("source_evidence_item_id"),
                        "claim": binding.get("source_claim") or binding.get("group_proposition"),
                        "source_ids": binding_sources,
                        "source_excerpt": binding.get("source_excerpt"),
                        "applicability_scope": _applicability_scope(binding),
                        "decision_relevance": binding.get("required_for_memo_reason") or binding.get("rationale"),
                        "quantities": [
                            _drop_empty(
                                {
                                    "value": value,
                                    "interpretation": binding.get("interpretation") or binding.get("claim_quantity_interpretation"),
                                    "retention_phrase": binding.get("retention_phrase"),
                                    "source_ids": binding_sources,
                                    "source_excerpt": binding.get("source_excerpt"),
                                    "applicability_scope": _applicability_scope(binding),
                                }
                            )
                        ],
                    }
                )
            )
    return _dedupe_binding_rows(rows)


def source_bound_quantity_tuples(row: dict[str, Any]) -> list[dict[str, Any]]:
    return _source_bound_quantity_tuples(row)[0]


def excluded_source_bound_quantity_tuples(row: dict[str, Any]) -> list[dict[str, Any]]:
    return _source_bound_quantity_tuples(row)[1]


def _source_bound_atom(row: dict[str, Any]) -> dict[str, Any]:
    source_ids = _row_source_ids(row)
    claim = str(row.get("claim") or row.get("statement") or row.get("reader_claim") or "").strip()
    quantities, excluded = _source_bound_quantity_tuples(row)
    if not claim and not quantities:
        return {}
    item_id = str(row.get("item_id") or row.get("obligation_id") or row.get("requirement_id") or "").strip()
    return _drop_empty(
        {
            "atom_id": item_id or _atom_id(claim, source_ids),
            "item_id": item_id,
            "claim": claim,
            "source_ids": source_ids,
            "allowed_citations": source_ids,
            "source_excerpt": _source_excerpt(row),
            "applicability_scope": _applicability_scope(row),
            "decision_relevance": row.get("decision_relevance"),
            "quantity_tuples": quantities,
            "excluded_quantity_tuples": excluded,
        }
    )


def _source_bound_quantity_tuples(row: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tuples = []
    excluded = []
    row_source_ids = _row_source_ids(row)
    for quantity in _list(row.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if not value:
            continue
        source_ids = _dedupe([*_string_list(quantity.get("source_ids")), *row_source_ids])
        source_excerpt = _source_excerpt(quantity) or _source_excerpt(row)
        tuple_row = _drop_empty(
            {
                "value": value,
                "interpretation": quantity.get("interpretation"),
                "retention_phrase": quantity.get("retention_phrase"),
                "source_ids": source_ids,
                "allowed_citations": source_ids,
                "source_excerpt": source_excerpt,
                "applicability_scope": _applicability_scope(quantity) or _applicability_scope(row),
            }
        )
        if _excerpt_has_numeric_surface(source_excerpt) and not contains_quantity(source_excerpt, value):
            excluded.append(
                {
                    **tuple_row,
                    "warning_type": "quantity_not_found_in_source_excerpt",
                    "warning": "Quantity value was not found in the local source excerpt, so it is not safe to use as a bound tuple.",
                }
            )
        else:
            tuples.append(tuple_row)
    return _dedupe_quantity_tuples(tuples), _dedupe_quantity_tuples(excluded)


def _quantity_sentence_source_warnings(
    memo: str,
    atoms: list[dict[str, Any]],
    *,
    source_aliases: dict[str, list[str]],
) -> list[dict[str, Any]]:
    warnings = []
    sentences = _memo_sentences(memo)
    for atom in atoms:
        for tuple_row in _list(atom.get("quantity_tuples")):
            if not isinstance(tuple_row, dict):
                continue
            value = str(tuple_row.get("value") or "").strip()
            if not value:
                continue
            if not _quantity_surface_specific_enough(value):
                continue
            scope = str(tuple_row.get("applicability_scope") or atom.get("applicability_scope") or "").strip()
            allowed_source_ids = _string_list(tuple_row.get("source_ids")) or _string_list(atom.get("source_ids"))
            if not allowed_source_ids:
                continue
            for sentence in sentences:
                if not _quantity_surface_in_sentence(sentence, value):
                    continue
                if scope and not _sentence_matches_applicability_scope(sentence, scope):
                    continue
                if _sentence_has_source(sentence, allowed_source_ids, source_aliases):
                    continue
                warnings.append(
                    {
                        "warning_type": "quantity_without_bound_source_nearby",
                        "quantity": value,
                        "expected_source_ids": allowed_source_ids,
                        "applicability_scope": scope,
                        "atom_id": atom.get("atom_id"),
                        "claim": atom.get("claim"),
                        "sentence": sentence[:300],
                    }
                )
    return _dedupe_warning_rows(warnings)


def _ambiguous_quantity_surfaces(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_value: dict[str, dict[str, Any]] = {}
    for atom in atoms:
        for tuple_row in _list(atom.get("quantity_tuples")):
            if not isinstance(tuple_row, dict):
                continue
            value = str(tuple_row.get("value") or "").strip()
            if not value:
                continue
            if not _quantity_surface_specific_enough(value):
                continue
            key = _norm(value)
            bucket = by_value.setdefault(key, {"value": value, "interpretations": [], "source_ids": []})
            bucket["interpretations"].extend(_string_list(tuple_row.get("interpretation")))
            bucket["source_ids"].extend(_string_list(tuple_row.get("source_ids")) or _string_list(atom.get("source_ids")))
    warnings = []
    for bucket in by_value.values():
        interpretations = _dedupe(bucket.get("interpretations", []))
        if len(interpretations) < 2:
            continue
        warnings.append(
            {
                "warning_type": "ambiguous_quantity_surface",
                "quantity": bucket.get("value"),
                "source_ids": _dedupe(bucket.get("source_ids", [])),
                "interpretations": interpretations[:6],
                "warning": "The same quantity surface has multiple interpretations; synthesis should use a source-bound tuple, not the bare number.",
            }
        )
    return warnings


def _sentence_has_source(sentence: str, source_ids: list[str], source_aliases: dict[str, list[str]]) -> bool:
    aliases = _dedupe(alias for source_id in source_ids for alias in [source_id, *source_aliases.get(source_id, [])] if alias)
    return any(_contains_text(sentence, alias) for alias in aliases)


def _sentence_matches_applicability_scope(sentence: str, scope: str) -> bool:
    terms = _scope_terms(scope)
    if not terms:
        return True
    normalized = _norm(sentence)
    matched = sum(1 for term in terms if _norm(term) in normalized)
    return matched >= min(2, len(terms))


def _scope_terms(scope: str) -> list[str]:
    stopwords = {
        "among",
        "between",
        "each",
        "from",
        "increase",
        "intake",
        "only",
        "participants",
        "patients",
        "people",
        "population",
        "risk",
        "subgroup",
        "with",
    }
    return _dedupe(
        term
        for term in re.findall(r"[a-z0-9]+", str(scope or "").lower())
        if len(term) >= 3 and term not in stopwords
    )[:8]


def _applicability_scope(row: dict[str, Any]) -> str:
    explicit = _row_applicability_scope(row)
    if explicit:
        return explicit
    return _scope_hint_from_texts(
        [
            str(row.get("interpretation") or row.get("claim_quantity_interpretation") or ""),
            str(row.get("source_claim") or ""),
            str(row.get("group_proposition") or ""),
            str(row.get("source_excerpt") or ""),
        ]
    )


def _row_applicability_scope(row: dict[str, Any]) -> str:
    for key in (
        "applicability_scope",
        "population_scope",
        "subgroup_scope",
        "scope",
        "population",
        "subgroup",
        "setting",
        "applicability",
    ):
        text = str(row.get(key) or "").strip()
        if text:
            return _short_scope_text(text)
    return ""


def _scope_hint_from_texts(values: list[str]) -> str:
    for value in values:
        text = " ".join(str(value or "").split())
        if not text:
            continue
        match = re.search(
            r"\b(?:among|in|for|to)\s+([^.;:,]{0,110}?(?:participants|patients|people|individuals|adults|children|women|men|cohort|population|subgroup|respondents|subjects|sites|settings|regions|countries|households|schools|firms|users)[^.;:,]*)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return _short_scope_text(match.group(0))
        match = re.search(
            r"\b(?:participants|patients|people|individuals|adults|children|women|men|cohort|population|subgroup|respondents|subjects|sites|settings|regions|countries|households|schools|firms|users)\s+(?:with|without|who|where|aged|under|over|from|in)\s+[^.;:]{1,90}",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return _short_scope_text(match.group(0))
    return ""


def _short_scope_text(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip(" ,;:.")
    return cleaned[:140].rstrip(" ,;:.") if len(cleaned) > 140 else cleaned


def _quantity_surface_in_sentence(sentence: str, value: str) -> bool:
    value_text = str(value or "").strip()
    if _bare_numeric_surface(value_text):
        return _bare_numeric_surface_in_sentence(sentence, value_text)
    if "%" in value_text:
        number = re.escape(value_text.replace("%", "").strip())
        return bool(re.search(rf"(?<![\d.]){number}(?:\s*%|\s+percent\b)", str(sentence or ""), flags=re.IGNORECASE))
    return contains_quantity(sentence, value_text)


def _bare_numeric_surface(value: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", str(value or "").strip()))


def _bare_numeric_surface_in_sentence(sentence: str, value: str) -> bool:
    text = str(sentence or "")
    interval_spans = _interval_spans(text)
    pattern = rf"(?<![\d.]){re.escape(value)}(?![\d.])"
    for match in re.finditer(pattern, text):
        if any(start <= match.start() and match.end() <= end for start, end in interval_spans):
            continue
        return True
    return False


def _interval_spans(text: str) -> list[tuple[int, int]]:
    endpoint = r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?"
    interval = rf"{endpoint}\s*(?:to|through|[-–—])\s*{endpoint}"
    spans: list[tuple[int, int]] = []
    for match in re.finditer(interval, str(text or ""), flags=re.IGNORECASE):
        start, end = match.span()
        prefix_start = max(0, start - 28)
        prefix = str(text or "")[prefix_start:start].lower()
        if re.search(r"\b(?:ci|confidence interval|credible interval|range|interval)\b|[(,]\s*$", prefix):
            spans.append((start, end))
    return spans


def _quantity_surface_specific_enough(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return "." in text or len(text) >= 3
    return bool(
        re.search(r"%|\b(?:hr|rr|or|md|ci|mg|g/dl|mmol|ratio|hazard|relative|risk|per|/day|serving|dose|month|year)\b|\d+\s*[–-]\s*\d+|\([^)]*\d", text)
    )


def _memo_sentences(memo: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", str(memo or ""))
    return [" ".join(chunk.split()) for chunk in chunks if chunk.strip() and not chunk.lstrip().startswith("#")]


def _row_source_ids(row: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(row.get("source_ids")), *_string_list(row.get("source_id"))])


def _source_excerpt(row: dict[str, Any]) -> str:
    return str(row.get("source_excerpt") or row.get("quote") or row.get("quoted_text") or row.get("excerpt") or "").strip()


def _excerpt_has_numeric_surface(text: str) -> bool:
    return bool(re.search(r"\d", str(text or "")))


def _contains_text(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


def _atom_id(claim: str, source_ids: list[str]) -> str:
    base = _norm(" ".join([claim, *source_ids]))[:60].replace(" ", "_") or "source_bound_atom"
    return f"atom_{base}"


def _dedupe_atoms(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (str(row.get("atom_id") or ""), _norm(str(row.get("claim") or "")), tuple(_string_list(row.get("source_ids"))))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _dedupe_binding_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        quantity = _list(row.get("quantities"))[0] if _list(row.get("quantities")) else {}
        key = (
            str(row.get("item_id") or ""),
            _norm(str(quantity.get("value") if isinstance(quantity, dict) else "")),
            _norm(str(quantity.get("interpretation") if isinstance(quantity, dict) else "")),
            tuple(_string_list(row.get("source_ids"))),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _dedupe_quantity_tuples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (_norm(str(row.get("value") or "")), _norm(str(row.get("interpretation") or "")), tuple(_string_list(row.get("source_ids"))))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _dedupe_warning_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (row.get("warning_type"), row.get("quantity"), tuple(_string_list(row.get("expected_source_ids"))), row.get("sentence"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
