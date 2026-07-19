from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)


def build_citation_care_report(
    memo: str,
    atoms: list[dict[str, Any]],
    *,
    source_aliases: dict[str, list[str]] | None = None,
    source_roles_override: dict[str, set[str]] | None = None,
    source_evidence_by_source: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    alias_to_source = _citation_alias_to_source(atoms, source_aliases or {})
    roles_by_source = _citation_roles_by_source(atoms, override=source_roles_override or {})
    evidence_by_source = source_evidence_by_source or {}
    warnings: list[dict[str, Any]] = []
    cited_sentence_count = 0
    for sentence_context in _memo_sentence_contexts(memo):
        sentence = str(sentence_context.get("sentence") or "")
        role_context = str(sentence_context.get("role_context") or sentence)
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
            sentence_roles = _sentence_citation_roles(f"{role_context} {clause}")
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
                entailment_warning = _citation_entailment_warning(
                    clause,
                    source_id=source_id,
                    source_evidence=evidence_by_source.get(source_id, []),
                    evidence_by_source=evidence_by_source,
                )
                if entailment_warning:
                    warnings.append({**entailment_warning, "sentence": sentence[:360]})
    deduped = _dedupe_warning_rows(warnings)
    return {
        "schema_id": "citation_care_report_v1",
        "status": "ready" if not deduped else "warning",
        "method": "deterministic_sentence_citation_role_audit",
        "cited_sentence_count": cited_sentence_count,
        "known_citation_source_count": len(roles_by_source),
        "source_evidence_count": sum(len(rows) for rows in evidence_by_source.values()),
        "warning_count": len(deduped),
        "warnings": deduped[:48],
    }


_ENTAILMENT_STOPWORDS = {
    "adult",
    "adults",
    "associated",
    "association",
    "cardiovascular",
    "compared",
    "consumption",
    "dietary",
    "effect",
    "effects",
    "evidence",
    "finding",
    "findings",
    "from",
    "health",
    "higher",
    "including",
    "increased",
    "lower",
    "moderate",
    "outcome",
    "outcomes",
    "people",
    "population",
    "research",
    "result",
    "results",
    "risk",
    "showed",
    "shows",
    "significant",
    "significantly",
    "study",
    "subjects",
    "their",
    "than",
    "that",
    "where",
    "which",
    "while",
    "these",
    "those",
    "versus",
    "with",
}


def _citation_entailment_warning(
    clause: str,
    *,
    source_id: str,
    source_evidence: list[str],
    evidence_by_source: dict[str, list[str]],
) -> dict[str, Any] | None:
    if not source_evidence:
        return None
    claim = _clean_citation_clause(clause)
    evidence_text = " ".join(source_evidence)
    claim_terms = _entailment_terms(claim)
    evidence_terms = _entailment_terms(evidence_text)
    distinctive_terms = _distinctive_claim_terms(claim_terms, evidence_by_source)
    matched_distinctive = sorted(set(distinctive_terms).intersection(evidence_terms))
    matched_terms = sorted(set(claim_terms).intersection(evidence_terms))
    quantities = _specific_quantity_surfaces(claim)
    if quantities:
        matched_quantities = [quantity for quantity in quantities if _quantity_surface_matches(evidence_text, quantity)]
        strong_qualitative_match = bool(matched_distinctive) and len(matched_terms) >= 2
        if not matched_quantities and not strong_qualitative_match:
            return _entailment_warning(
                source_id,
                claim,
                source_evidence,
                reason="cited source evidence does not contain the clause's specific quantity",
                unmatched_quantities=quantities,
            )
        return None

    if len(claim_terms) < 2:
        return None
    minimum_overlap = 2 if len(claim_terms) >= 5 else 1
    if matched_distinctive or len(matched_terms) >= minimum_overlap:
        return None
    return _entailment_warning(
        source_id,
        claim,
        source_evidence,
        reason="cited source evidence does not match the clause's distinctive claim terms",
        unmatched_terms=distinctive_terms[:8] or claim_terms[:8],
    )


def _entailment_warning(
    source_id: str,
    claim: str,
    source_evidence: list[str],
    *,
    reason: str,
    unmatched_quantities: list[str] | None = None,
    unmatched_terms: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "warning_type": "citation_claim_entailment_mismatch",
        "source_id": source_id,
        "citation_clause": " ".join(claim.split())[:260],
        "reason": reason,
        "unmatched_quantities": unmatched_quantities or [],
        "unmatched_terms": unmatched_terms or [],
        "source_evidence_samples": [" ".join(text.split())[:220] for text in source_evidence[:3]],
        "guidance": "Keep this citation only if its source-specific evidence supports the exact adjacent claim; otherwise remove or replace it.",
    }


def _specific_quantity_surfaces(text: str) -> list[str]:
    patterns = (
        r"(?:HR|RR|OR|MD)\s*(?:=|:)?\s*\d+(?:\.\d+)?",
        r"\d+(?:\.\d+)?\s*(?:±|\+/-)\s*\d+(?:\.\d+)?\s*%?",
        r"(?:[<>≤≥]\s*)?\d+(?:\.\d+)?\s*%",
        r"[<>≤≥]\s*\d+(?:\.\d+)?\s*(?:times?/week|/week|[a-z]+s?/(?:week|day))",
        r"\d+(?:\.\d+)?\s*(?:times?/week|[a-z]+s?/(?:week|day))",
        r"\d+(?:\.\d+)?\s*[–-]\s*\d+(?:\.\d+)?",
    )
    values: list[str] = []
    for pattern in patterns:
        values.extend(match.group(0) for match in re.finditer(pattern, str(text or ""), flags=re.IGNORECASE))
    deduped = sorted(_dedupe(" ".join(value.split()) for value in values), key=len, reverse=True)
    retained: list[str] = []
    for value in deduped:
        normalized = _norm(value)
        if any(normalized in _norm(existing) for existing in retained):
            continue
        retained.append(value)
    return retained


def _quantity_surface_matches(text: str, quantity: str) -> bool:
    numbers = re.findall(r"\d+(?:\.\d+)?", quantity)
    if not numbers:
        return True
    normalized = str(text or "").replace("−", "-").replace("–", "-").replace("—", "-")
    return all(re.search(rf"(?<![\d.]){re.escape(number)}(?![\d.])", normalized) for number in numbers)


def _entailment_terms(text: str) -> list[str]:
    terms = []
    for raw in re.findall(r"[a-z][a-z0-9-]{3,}", _norm(text)):
        term = raw.rstrip(".,;:")
        if term in _ENTAILMENT_STOPWORDS:
            continue
        terms.append(term)
    return _dedupe(terms)


def _distinctive_claim_terms(claim_terms: list[str], evidence_by_source: dict[str, list[str]]) -> list[str]:
    source_count = max(len(evidence_by_source), 1)
    maximum_frequency = max(2, source_count // 5)
    frequencies: dict[str, int] = {}
    for evidence_rows in evidence_by_source.values():
        source_terms = set(_entailment_terms(" ".join(evidence_rows)))
        for term in claim_terms:
            if term in source_terms:
                frequencies[term] = frequencies.get(term, 0) + 1
    return [term for term in claim_terms if frequencies.get(term, 0) <= maximum_frequency]


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
    left_candidates = _clause_boundary_indexes(text, 0, start)
    left = max(left_candidates, default=-1)
    # A conventional citation often follows the sentence-ending period. In
    # that form the nearest boundary is not the start of a new empty clause;
    # the citation belongs to the complete sentence immediately before it.
    if left >= 0 and not text[left + 1 : start].strip():
        left = max((index for index in left_candidates if index < left), default=-1)
    right_candidates = _clause_boundary_indexes(text, end, len(text))
    right = min(right_candidates) if right_candidates else len(text)
    return " ".join(text[left + 1 : right].split())


def _clause_boundary_indexes(text: str, start: int, end: int) -> list[int]:
    boundaries: list[int] = []
    for index in range(max(start, 0), min(end, len(text))):
        char = text[index]
        if char in ";:":
            boundaries.append(index)
        elif char == "." and not _is_decimal_period(text, index) and not _is_abbreviation_period(text, index):
            boundaries.append(index)
    return boundaries


def _is_decimal_period(text: str, index: int) -> bool:
    return index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit()


def _is_abbreviation_period(text: str, index: int) -> bool:
    prefix = str(text or "")[: index + 1].lower()
    return bool(re.search(r"(?:\bvs|\be\.g|\bi\.e|\bet\s+al)\.$", prefix))


def _sentence_citation_roles(sentence: str) -> set[str]:
    text = _norm(_strip_bracket_citations(sentence))
    roles: set[str] = set()
    risk_counter = bool(re.search(r"\b(?:increased|higher)\s+risk\b", text)) and not bool(
        re.search(r"\b(?:not associated with|no|does not|without)\s+(?:\w+\s+){0,4}(?:increased|higher)\s+risk\b", text)
    )
    if re.search(
        r"\b(bound\w*|limit\w*|scope|caveat\w*|except\w*|subgroup|high risk|dose[- ]?response|mortality|qualif\w*)\b"
        r"|\bonly\s+appl(?:y|ies)\b|\bappl(?:y|ies)\s+(?:only\s+)?where\b",
        text,
    ) or risk_counter:
        roles.add("boundary")
    if re.search(
        r"\b(counter\w*|tension|however|although|whereas|but|conflict\w*|contradict\w*|harm|mortality|fail\w*|undermin\w*|offset\w*)\b"
        r"|\berase\w*(?:\s+the)?\s+benefit\b",
        text,
    ) or risk_counter:
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


def _clean_citation_clause(clause: str) -> str:
    text = _strip_bracket_citations(clause)
    text = re.sub(r"(?:\s*,\s*)+$", "", text)
    return " ".join(text.split()).strip()


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


def _memo_sentence_contexts(memo: str) -> list[dict[str, str]]:
    body = re.sub(r"\n## Sources\b.*", "", str(memo or ""), flags=re.IGNORECASE | re.DOTALL)
    body = re.sub(r"\[[^\]\n]+\]:\s+\S+", "", body)
    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []
    current_heading = ""

    def flush_paragraph() -> None:
        if paragraph_lines:
            blocks.append((current_heading, " ".join(paragraph_lines)))
            paragraph_lines.clear()

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("#"):
            flush_paragraph()
            current_heading = line.lstrip("#").strip()
            continue
        list_item = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if list_item:
            flush_paragraph()
            item = list_item.group(1).strip()
            blocks.append((current_heading, item))
            continue
        paragraph_lines.append(line)
    flush_paragraph()

    sentences: list[dict[str, str]] = []
    for heading, block in blocks:
        parts = _split_memo_sentences(re.sub(r"\s+", " ", block))
        for part in parts:
            sentence = part.strip()
            if not sentence:
                continue
            sentences.append(
                {
                    "sentence": sentence,
                    "role_context": f"{heading}: {sentence}" if heading else sentence,
                }
            )
    return sentences


def _split_memo_sentences(block: str) -> list[str]:
    protected = str(block or "")
    placeholders = {
        "vs.": "vs\u0000",
        "e.g.": "e\u0000g\u0000",
        "i.e.": "i\u0000e\u0000",
        "et al.": "et al\u0000",
    }
    for surface, placeholder in placeholders.items():
        protected = re.sub(re.escape(surface), placeholder, protected, flags=re.IGNORECASE)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9*])", protected)
    return [part.replace("\u0000", ".") for part in parts]


def _dedupe_warning_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (
            row.get("warning_type"),
            row.get("quantity"),
            row.get("source_id"),
            tuple(_string_list(row.get("source_ids"))),
            tuple(_string_list(row.get("expected_source_ids"))),
            row.get("citation_clause"),
            row.get("sentence"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped
