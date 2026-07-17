from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    norm as _norm,
    short_text as _short_text,
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
    aliases = source_aliases or {}
    invalid_tuples = [
        tuple_row
        for atom in atoms
        for tuple_row in _list(atom.get("excluded_quantity_tuples"))
        if isinstance(tuple_row, dict)
    ]
    sentence_warnings = _quantity_sentence_source_warnings(
        memo,
        atoms,
        source_aliases=aliases,
    )
    citation_care = build_citation_care_report(
        memo,
        atoms,
        source_aliases=aliases,
        source_roles_override=_source_weight_roles_by_source(packet),
    )
    ambiguous = _ambiguous_quantity_surfaces(atoms)
    warnings = [*invalid_tuples, *sentence_warnings, *ambiguous, *_list(citation_care.get("warnings"))]
    return {
        "schema_id": "source_binding_report_v1",
        "status": "ready" if not warnings else "warning",
        "source_bound_atom_count": len(atoms),
        "invalid_quantity_tuple_count": len(invalid_tuples),
        "quantity_source_adjacency_warning_count": len(sentence_warnings),
        "ambiguous_quantity_surface_count": len(ambiguous),
        "citation_care_warning_count": citation_care.get("warning_count", 0),
        "warning_count": len(warnings),
        "invalid_quantity_tuples": invalid_tuples[:24],
        "quantity_source_adjacency_warnings": sentence_warnings[:24],
        "ambiguous_quantity_surfaces": ambiguous[:24],
        "citation_care_report": citation_care,
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


def source_bound_quantity_phrases(row: dict[str, Any], *, limit: int = 8) -> list[str]:
    """Render quantity tuples as reader-safe phrases before model synthesis.

    The renderer keeps point estimates and uncertainty intervals together so a
    later writer sees "HR 0.93 (95% CI 0.82 to 1.05)" instead of two loose
    numeric anchors that can be grammatically rebound.
    """
    quantities = [quantity for quantity in _list(row.get("quantities")) if isinstance(quantity, dict)]
    if not quantities:
        return []
    phrases: list[str] = []
    consumed: set[int] = set()
    for index, quantity in enumerate(quantities):
        if index in consumed:
            continue
        if _quantity_is_uncertainty_interval(quantity):
            continue
        interval_index = _matching_interval_index(index, quantity, quantities, consumed)
        phrase = _render_quantity_phrase(quantity, quantities[interval_index] if interval_index is not None else None)
        if not phrase:
            continue
        phrases.append(phrase)
        consumed.add(index)
        if interval_index is not None:
            consumed.add(interval_index)
    for index, quantity in enumerate(quantities):
        if index in consumed:
            continue
        phrase = _render_quantity_phrase(quantity, None)
        if phrase:
            phrases.append(phrase)
            consumed.add(index)
    return _dedupe_quantity_phrases(phrases)[:limit]


def build_citation_care_report(
    memo: str,
    atoms: list[dict[str, Any]],
    *,
    source_aliases: dict[str, list[str]] | None = None,
    source_roles_override: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    alias_to_source = _citation_alias_to_source(atoms, source_aliases or {})
    roles_by_source = _citation_roles_by_source(atoms, override=source_roles_override or {})
    warnings: list[dict[str, Any]] = []
    cited_sentence_count = 0
    for sentence in _memo_sentences(memo):
        citation_groups = _sentence_citation_groups(sentence, alias_to_source)
        cited_source_ids = _dedupe(
            source_id
            for group in citation_groups
            for source_id in _string_list(group.get("source_ids"))
        )
        if not cited_source_ids:
            continue
        cited_sentence_count += 1
        for group in citation_groups:
            group_source_ids = _string_list(group.get("source_ids"))
            if not group_source_ids:
                continue
            clause = str(group.get("clause") or sentence)
            sentence_roles = _sentence_citation_roles(clause)
            source_roles = {source_id: sorted(roles_by_source.get(source_id, set())) for source_id in group_source_ids}
            if len(group_source_ids) > 2 or _mixed_citation_roles(source_roles):
                warnings.append(
                    {
                        "warning_type": "overbundled_or_mixed_role_citation",
                        "source_ids": group_source_ids,
                        "source_roles": source_roles,
                        "sentence_roles": sorted(sentence_roles),
                        "sentence": sentence[:360],
                        "citation_clause": clause[:260],
                        "guidance": "Consider splitting the citation so each source supports the exact clause beside it.",
                    }
                )
            for source_id in group_source_ids:
                roles = roles_by_source.get(source_id, set())
                if not roles:
                    warnings.append(
                        {
                            "warning_type": "citation_without_packet_atom",
                            "source_id": source_id,
                            "sentence": sentence[:360],
                            "citation_clause": clause[:260],
                            "guidance": "The cited source was not found in source-bound packet evidence.",
                        }
                    )
                    continue
                if _role_mismatch(sentence_roles, roles):
                    warnings.append(
                        {
                            "warning_type": "citation_role_mismatch",
                            "source_id": source_id,
                            "source_roles": sorted(roles),
                            "sentence_roles": sorted(sentence_roles),
                            "sentence": sentence[:360],
                            "citation_clause": clause[:260],
                            "guidance": _role_mismatch_guidance(sentence_roles, roles),
                        }
                    )
    deduped = _dedupe_warning_rows(warnings)
    return {
        "schema_id": "citation_care_report_v1",
        "status": "ready" if not deduped else "warning",
        "method": "deterministic_sentence_citation_role_audit",
        "cited_sentence_count": cited_sentence_count,
        "known_citation_source_count": len(roles_by_source),
        "warning_count": len(deduped),
        "warnings": deduped[:48],
    }


def _source_bound_atom(row: dict[str, Any]) -> dict[str, Any]:
    source_ids = _row_source_ids(row)
    claim = str(row.get("claim") or row.get("statement") or row.get("reader_claim") or "").strip()
    quantities, excluded = _source_bound_quantity_tuples(row)
    if not claim and not quantities:
        return {}
    item_id = str(row.get("item_id") or row.get("obligation_id") or row.get("requirement_id") or "").strip()
    citation_role = _citation_role(row, quantity_tuples=quantities)
    return _drop_empty(
        {
            "atom_id": item_id or _atom_id(claim, source_ids),
            "item_id": item_id,
            "claim": claim,
            "source_ids": source_ids,
            "allowed_citations": source_ids,
            "citation_role": citation_role,
            "use_for": _citation_use_for(row, citation_role),
            "do_not_use_for": _citation_do_not_use_for(row),
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
                "citation_role": "calibration",
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


def _matching_interval_index(
    estimate_index: int,
    estimate: dict[str, Any],
    quantities: list[dict[str, Any]],
    consumed: set[int],
) -> int | None:
    estimate_source = str(estimate.get("source_evidence_item_id") or "").strip()
    estimate_sources = set(_string_list(estimate.get("source_ids")) or _string_list(estimate.get("source_labels")))
    best: tuple[int, int] | None = None
    for index, candidate in enumerate(quantities):
        if index == estimate_index or index in consumed:
            continue
        if not _quantity_is_uncertainty_interval(candidate):
            continue
        candidate_source = str(candidate.get("source_evidence_item_id") or "").strip()
        candidate_sources = set(_string_list(candidate.get("source_ids")) or _string_list(candidate.get("source_labels")))
        if estimate_source and candidate_source and estimate_source != candidate_source:
            continue
        if estimate_sources and candidate_sources and not estimate_sources.intersection(candidate_sources):
            continue
        distance = abs(index - estimate_index)
        if best is None or distance < best[0]:
            best = (distance, index)
    return best[1] if best else None


def _render_quantity_phrase(quantity: dict[str, Any], interval: dict[str, Any] | None) -> str:
    value = str(quantity.get("value") or "").strip()
    if not value:
        return ""
    if _quantity_is_uncertainty_interval(quantity) and interval is None:
        return _short_text(_interval_text(quantity), 260)
    label = _quantity_label(quantity)
    value_text = _quantity_value_with_label(value, label)
    interval_text = _interval_text(interval) if isinstance(interval, dict) else ""
    measure = _quantity_measure_phrase(quantity)
    phrase = value_text
    if interval_text:
        phrase = f"{phrase} ({interval_text})"
    if measure:
        phrase = f"{phrase} for {measure}"
    return _short_text(phrase, 260)


def _quantity_value_with_label(value: str, label: str) -> str:
    value = " ".join(str(value or "").split()).strip()
    if not label:
        return value
    value = _strip_embedded_quantity_label(value, label)
    if _norm(label) in _norm(value):
        return value
    if label == "MD":
        return f"MD = {value}" if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value) else f"MD {value}"
    return f"{label} {value}"


def _strip_embedded_quantity_label(value: str, label: str) -> str:
    label_patterns = {
        "HR": r"(?:HR|hazard ratio)",
        "RR": r"(?:RR|relative risk)",
        "OR": r"(?:OR|odds ratio)",
        "MD": r"(?:MD|mean difference)",
    }
    pattern = label_patterns.get(label)
    if not pattern:
        return value
    stripped = re.sub(rf"^\s*{pattern}\s*(?:=|of)?\s*", "", value, flags=re.IGNORECASE).strip()
    return stripped or value


def _interval_text(interval: dict[str, Any]) -> str:
    value = str(interval.get("value") or "").strip()
    if not value:
        return ""
    text = " ".join(value.split())
    lowered = text.lower()
    if "confidence interval" in lowered or re.search(r"\bci\b", lowered):
        return text
    interpretation = " ".join(
        str(interval.get(key) or "")
        for key in ("interpretation", "retention_phrase", "measures", "claim_quantity_interpretation")
    ).lower()
    if "95" in interpretation or "confidence" in interpretation or "ci" in interpretation:
        return f"95% CI {text}"
    return f"interval {text}"


def _quantity_measure_phrase(quantity: dict[str, Any]) -> str:
    interpretation = str(
        quantity.get("retention_phrase")
        or quantity.get("interpretation")
        or quantity.get("claim_quantity_interpretation")
        or ""
    ).strip()
    text = re.sub(
        r"^\s*(?:hazard ratio|relative risk|odds ratio|mean difference|increase|decrease|confidence interval)\s+(?:for|of|in)\s+",
        "",
        interpretation,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^\s*(?:HR|RR|OR|MD)\s+(?:for|of|in)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" .;:")
    if not text or _norm(text) == _norm(str(quantity.get("value") or "")):
        return ""
    if not re.search(r"[A-Za-z]", text):
        return ""
    if _quantity_is_uncertainty_interval(quantity):
        return ""
    return _short_text(text, 180)


def _dedupe_quantity_phrases(phrases: list[str]) -> list[str]:
    richer_keys: set[str] = set()
    unique = _dedupe(phrases)
    for phrase in unique:
        key = _estimate_surface_key(phrase)
        if key and not _bare_quantity_phrase(phrase):
            richer_keys.add(key)
    result: list[str] = []
    for phrase in unique:
        key = _estimate_surface_key(phrase)
        if key and _bare_quantity_phrase(phrase) and key in richer_keys:
            continue
        result.append(phrase)
    return result


def _estimate_surface_key(text: str) -> str:
    if re.match(r"\s*(?:95%\s*)?(?:CI|confidence interval|credible interval|uncertainty interval)\b", text, re.IGNORECASE):
        return ""
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if numbers:
        return numbers[0]
    return ""


def _bare_quantity_phrase(phrase: str) -> bool:
    return not (
        re.search(r"\b(?:CI|confidence interval|interval)\b", phrase, flags=re.IGNORECASE)
        or " for " in phrase.lower()
    )


def _quantity_label(quantity: dict[str, Any]) -> str:
    text = " ".join(
        str(quantity.get(key) or "")
        for key in (
            "value",
            "interpretation",
            "retention_phrase",
            "measures",
            "claim_quantity_interpretation",
            "quantity_role",
            "claim_quantity_role",
        )
    ).lower()
    if "hazard ratio" in text or re.search(r"\bhr\b", text):
        return "HR"
    if "relative risk" in text or re.search(r"\brr\b", text):
        return "RR"
    if "odds ratio" in text or re.search(r"\bor\b", text):
        return "OR"
    if "mean difference" in text or re.search(r"\bmd\b", text):
        return "MD"
    return ""


def _quantity_is_uncertainty_interval(quantity: dict[str, Any]) -> bool:
    value = str(quantity.get("value") or "")
    text = " ".join(
        str(quantity.get(key) or "")
        for key in (
            "interpretation",
            "retention_phrase",
            "measures",
            "quantity_role",
            "claim_quantity_role",
            "claim_quantity_type",
        )
    )
    if re.search(r"\b(?:ci|confidence interval|credible interval|uncertainty interval)\b", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:to|through|[-–—])\s*\d+(?:\.\d+)?\b", value) and re.search(
        r"\b(?:ci|confidence|interval)\b", text, flags=re.IGNORECASE
    ):
        return True
    return False


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


def _citation_alias_to_source(atoms: list[dict[str, Any]], source_aliases: dict[str, list[str]]) -> dict[str, str]:
    source_ids = _dedupe(
        source_id
        for atom in atoms
        for source_id in _string_list(atom.get("source_ids"))
        if source_id
    )
    alias_to_source: dict[str, str] = {}
    for source_id in source_ids:
        for alias in _dedupe([source_id, *source_aliases.get(source_id, [])]):
            alias_to_source[_norm(alias)] = source_id
    for key, aliases in source_aliases.items():
        canonical = next((alias for alias in _string_list(aliases) if alias in source_ids), "")
        if not canonical and key in source_ids:
            canonical = key
        if not canonical:
            continue
        for alias in _dedupe([key, *aliases]):
            alias_to_source[_norm(alias)] = canonical
    return {key: value for key, value in alias_to_source.items() if key and value}


def _citation_roles_by_source(atoms: list[dict[str, Any]], *, override: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {source_id: set(role_set) for source_id, role_set in (override or {}).items()}
    for atom in atoms:
        role = str(atom.get("citation_role") or "direct_support").strip() or "direct_support"
        for source_id in _string_list(atom.get("source_ids")):
            if source_id in roles:
                continue
            roles.setdefault(source_id, set()).add(role)
    return roles


def _source_weight_roles_by_source(packet: dict[str, Any]) -> dict[str, set[str]]:
    canonical = packet.get("canonical_decision_writer_packet") if isinstance(packet.get("canonical_decision_writer_packet"), dict) else {}
    roles: dict[str, set[str]] = {}
    for row in _list(canonical.get("source_weight_judgments")):
        if not isinstance(row, dict):
            continue
        role = _source_weight_citation_role(row)
        if not role:
            continue
        for source_id in _string_list(row.get("source_ids")):
            roles[source_id] = {role}
    return roles


def _source_weight_citation_role(row: dict[str, Any]) -> str:
    text = _norm(
        " ".join(
            str(row.get(key) or "")
            for key in (
                "main_use",
                "memo_weight_sentence",
                "why_weight_this_way",
                "reader_facing_limit",
            )
        )
    )
    main_use = _norm(str(row.get("main_use") or ""))
    if re.search(r"\b(calibrat|magnitude|quant|estimate)\b", main_use):
        return "calibration"
    if re.search(r"\b(bounds?|boundary|scope|limit)\b", main_use):
        return "boundary"
    if re.search(r"\b(counter|tension|weaken)\b", main_use):
        return "counterweight"
    if re.search(r"\b(context|contextual|guidance)\b", main_use):
        return "context"
    if re.search(r"\b(drives?|support|primary|answer)\b", main_use):
        return "direct_support"
    if re.search(r"\b(calibrat|magnitude|dose|threshold|estimate|ratio)\b", text):
        return "calibration"
    if re.search(r"\b(bound|bounds|boundary|scope|limit|caveat|subgroup)\b", text):
        return "boundary"
    if re.search(r"\b(context|guidance|practical|pattern|implementation)\b", text):
        return "context"
    if re.search(r"\b(drive|support|primary)\b", text):
        return "direct_support"
    return ""


def _sentence_cited_source_ids(sentence: str, alias_to_source: dict[str, str]) -> list[str]:
    source_ids: list[str] = []
    for raw in re.findall(r"\[([^\[\]\n]{1,180})\]", str(sentence or "")):
        if "](" in raw or raw.strip().startswith("^"):
            continue
        for token in re.split(r"\s*(?:,|;)\s*", raw):
            key = _norm(token)
            if key in alias_to_source:
                source_ids.append(alias_to_source[key])
    return _dedupe(source_ids)


def _sentence_citation_groups(sentence: str, alias_to_source: dict[str, str]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for match in re.finditer(r"\[([^\[\]\n]{1,180})\]", str(sentence or "")):
        raw = match.group(1)
        if "](" in raw or raw.strip().startswith("^"):
            continue
        source_ids = []
        for token in re.split(r"\s*(?:,|;)\s*", raw):
            key = _norm(token)
            if key in alias_to_source:
                source_ids.append(alias_to_source[key])
        source_ids = _dedupe(source_ids)
        if source_ids:
            groups.append(
                {
                    "source_ids": source_ids,
                    "clause": _citation_local_clause(sentence, match.start(), match.end()),
                }
            )
    return groups


def _citation_local_clause(sentence: str, start: int, end: int) -> str:
    text = str(sentence or "")
    left = max(_clause_boundary_indexes(text, 0, start), default=-1)
    right_candidates = _clause_boundary_indexes(text, end, len(text))
    right = min(right_candidates) if right_candidates else len(text)
    return " ".join(text[left + 1 : right].split())


def _clause_boundary_indexes(text: str, start: int, end: int) -> list[int]:
    boundaries: list[int] = []
    for index in range(max(start, 0), min(end, len(text))):
        char = text[index]
        if char in ";:":
            boundaries.append(index)
        elif char == "." and not _is_decimal_period(text, index):
            boundaries.append(index)
    return boundaries


def _is_decimal_period(text: str, index: int) -> bool:
    return index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit()


def _sentence_citation_roles(sentence: str) -> set[str]:
    text = _norm(_strip_bracket_citations(sentence))
    roles: set[str] = set()
    risk_counter = bool(re.search(r"\b(?:increased|higher)\s+risk\b", text)) and not bool(
        re.search(r"\b(?:not associated with|no|does not|without)\s+(?:\w+\s+){0,4}(?:increased|higher)\s+risk\b", text)
    )
    if re.search(r"\b(bound\w*|limit\w*|scope|caveat\w*|except\w*|subgroup|high risk|dose[- ]?response|mortality|qualif\w*)\b", text) or risk_counter:
        roles.add("boundary")
    if re.search(r"\b(counter\w*|tension|however|although|whereas|but|conflict\w*|contradict\w*|harm|mortality)\b", text) or risk_counter:
        roles.add("counterweight")
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|per day|hr|rr|or|md|ci|ratio)\b", text):
        roles.add("calibration")
    if re.search(r"\b(context|guidance|recommend\w*|practical|pattern\w*|dietary pattern|framework)\b", text):
        roles.add("context")
    if re.search(r"\b(neutral|not associated|safe|supports?|driven by|primary conclusion|best current read|does not increase|no increased|without specific concern)\b", text):
        roles.add("direct_support")
    return roles or {"direct_support"}


def _strip_bracket_citations(sentence: str) -> str:
    return re.sub(r"\[[^\[\]\n]{1,180}\]", "", str(sentence or ""))


def _mixed_citation_roles(source_roles: dict[str, list[str]]) -> bool:
    role_sets = {tuple(roles or ["unknown"]) for roles in source_roles.values()}
    if len(role_sets) <= 1:
        return False
    flattened = {role for roles in role_sets for role in roles}
    return bool(flattened.intersection({"boundary", "counterweight", "calibration", "context"}) and "direct_support" in flattened)


def _role_mismatch(sentence_roles: set[str], source_roles: set[str]) -> bool:
    if not source_roles:
        return False
    if "direct_support" in sentence_roles and not sentence_roles.intersection({"boundary", "counterweight", "calibration"}):
        if source_roles.issubset({"boundary", "counterweight", "calibration"}):
            return True
    if "calibration" in sentence_roles and source_roles == {"context"}:
        return True
    return False


def _role_mismatch_guidance(sentence_roles: set[str], source_roles: set[str]) -> str:
    if "direct_support" in sentence_roles and source_roles.issubset({"boundary", "counterweight", "calibration"}):
        return "Use this source on a boundary, counterweight, or calibration clause rather than a broad support claim."
    return "Check whether this source supports the exact sentence claim in the cited role."


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
    return [
        " ".join(chunk.split())
        for chunk in chunks
        if chunk.strip()
        and not chunk.lstrip().startswith("#")
        and not re.match(r"^\s*\[[^\]\n]+\]:\s+", chunk)
        and not chunk.lstrip().startswith("[^")
    ]


def _row_source_ids(row: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(row.get("source_ids")), *_string_list(row.get("source_id"))])


def _citation_role(row: dict[str, Any], *, quantity_tuples: list[dict[str, Any]]) -> str:
    text = _norm(
        " ".join(
            str(row.get(key) or "")
            for key in (
                "citation_role",
                "main_use",
                "reader_evidence_role",
                "evidence_role",
                "role",
                "role_description",
                "lane",
                "section_id",
                "section",
                "quantity_role",
                "claim_quantity_role",
                "decision_relevance",
                "writing_job",
                "prose_instruction",
            )
        )
    )
    if re.search(r"\b(counterweight|counter|tension|oppos|conflict|against|contradict|exception)\b", text):
        return "counterweight"
    if re.search(r"\b(bounds?|boundary|limit\w*|scope|limiter|caveat\w*|qualif\w*|exception\w*|subgroup|applicab\w*)\b", text):
        return "boundary"
    if re.search(r"\b(calibrat\w*|magnitude|quant\w*|statistical|estimate\w*|endpoint|dose|threshold|ratio|measure\w*)\b", text):
        return "calibration"
    if re.search(r"\b(context|background|guidance|advisory|practice|implementation|interpret)\b", text):
        return "context"
    if re.search(r"\b(driver|drive|support|primary|answer|best current read|main reason|direct)\b", text):
        return "direct_support"
    if quantity_tuples and not str(row.get("claim") or row.get("statement") or row.get("reader_claim") or "").strip():
        return "calibration"
    return "direct_support"


def _citation_use_for(row: dict[str, Any], citation_role: str) -> str:
    explicit = str(row.get("use_for") or row.get("memo_weight_sentence") or row.get("why_weight_this_way") or "").strip()
    if explicit:
        return _short_text(explicit, 320)
    for key in (
        "decision_relevance",
        "role_rationale",
        "writing_job",
        "prose_instruction",
        "rationale",
        "claim",
        "statement",
        "reader_claim",
    ):
        value = str(row.get(key) or "").strip()
        if value:
            return _short_text(value, 320)
    defaults = {
        "direct_support": "Use as direct support for the sentence-level claim.",
        "boundary": "Use to bound, scope, or qualify the sentence-level claim.",
        "counterweight": "Use to state a counterweight, tension, or exception.",
        "calibration": "Use to calibrate magnitude, threshold, endpoint, or quantity.",
        "context": "Use for background, guidance, or interpretive context.",
    }
    return defaults.get(citation_role, "Use for the sentence-level claim it directly supports.")


def _citation_do_not_use_for(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "do_not_use_for",
        "cannot_support",
        "reader_facing_limit",
        "what_not_to_use_it_for",
        "source_appraisal_caveats",
        "must_not_overstate",
        "avoid_language",
        "limitations",
        "limits",
    ):
        raw = row.get(key)
        values.extend(_string_list(raw))
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
    return _dedupe(_short_text(value, 220) for value in values if str(value or "").strip())[:4]


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
