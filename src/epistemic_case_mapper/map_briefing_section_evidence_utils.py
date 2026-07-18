from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


BRACE_TAG_RE = re.compile(r"\{([^{}\n]{1,240})\}")


def quantity_source_ids(quantities: list[dict[str, Any]]) -> list[str]:
    return _dedupe(source_id for quantity in quantities for source_id in _string_list(quantity.get("source_ids")))


def label_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def contract_required(
    item: dict[str, Any],
    obligation: dict[str, Any],
    *,
    role: str,
    quantities: list[dict[str, Any]],
) -> bool:
    role_text = role.lower()
    return (
        bool(item.get("must_use"))
        or str(item.get("obligation_level") or "") == "must_include"
        or bool(obligation)
        or bool(quantities)
        or role_text in {"strongest_counterweight", "scope_boundary", "quantitative_anchor", "decision_crux"}
    )


def quantity_contracts(rows: list[Any]) -> list[dict[str, Any]]:
    quantities = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = str(row.get("value") or "").strip()
        if not value:
            continue
        quantity = drop_empty(
            {
                "value": value,
                "interpretation": row.get("interpretation"),
                "quantity_role": row.get("quantity_role"),
                "source_ids": row.get("source_ids"),
            }
        )
        key = (re.sub(r"\s+", " ", value.lower()).strip(), str(quantity.get("interpretation") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        quantities.append(quantity)
    return quantities


def quantity_warnings(tagged_memo: str, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    for contract in contracts:
        if not contract.get("required"):
            continue
        spans = spans_for_evidence_id(tagged_memo, str(contract.get("evidence_id") or ""))
        if not spans:
            continue
        for quantity in _list(contract.get("required_quantity_atoms")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if value and not any(quantity_surface_present(value, span) for span in spans):
                warnings.append(
                    {
                        "evidence_id": contract.get("evidence_id"),
                        "missing_quantity_near_tag": value,
                        "span": _short_text(spans[0], 240),
                    }
                )
    return warnings


def span_for_evidence_id(text: str, evidence_id: str) -> str:
    spans = spans_for_evidence_id(text, evidence_id)
    return spans[0] if spans else ""


def spans_for_evidence_id(text: str, evidence_id: str) -> list[str]:
    if not evidence_id:
        return []
    tag_pattern = re.compile(
        rf"(?:\{{E:{re.escape(evidence_id)}\}}|\{{[^}}\n]*\b{re.escape(evidence_id)}\b[^}}\n]*\}})"
    )
    matches = list(tag_pattern.finditer(str(text or "")))
    if not matches:
        return []
    paragraphs = [paragraph_around_index(str(text or ""), tag.start()) for tag in matches]
    paragraphs = _dedupe(paragraph for paragraph in paragraphs if paragraph)
    if paragraphs:
        return paragraphs
    pattern = re.compile(rf"[^\n]*(?:\{{E:{re.escape(evidence_id)}\}}|\{{[^}}\n]*\b{re.escape(evidence_id)}\b[^}}\n]*\}})[^\n]*(?:\n|$)")
    return _dedupe(match.group(0).strip() for match in pattern.finditer(text) if match.group(0).strip())


def paragraph_around_index(text: str, index: int) -> str:
    before = text.rfind("\n\n", 0, max(0, index))
    after = text.find("\n\n", index)
    start = 0 if before < 0 else before + 2
    end = len(text) if after < 0 else after
    return text[start:end].strip()


def quantity_surface_present(value: str, text: str) -> bool:
    value_text = str(value or "").lower()
    text_norm = str(text or "").lower()
    if value_text in text_norm:
        return True
    numbers = re.findall(r"\d+(?:\.\d+)?", value_text)
    return bool(numbers) and all(number in text_norm for number in numbers)


def untagged_high_risk_sentences(tagged_memo: str) -> list[str]:
    rows = []
    for sentence in sentences_without_sources(tagged_memo):
        if evidence_ids_in_text(sentence, []):
            continue
        lowered = sentence.lower()
        if re.search(r"\d", sentence) or any(
            token in lowered
            for token in ("associated", "risk", "increased", "reduced", "should", "must", "recommend", "causes", "proves")
        ):
            rows.append(_short_text(BRACE_TAG_RE.sub("", sentence).strip(), 300))
    return rows


def sentences_without_sources(memo: str) -> list[str]:
    body = re.split(r"(?m)^## Sources\s*$", memo)[0]
    body = "\n".join(line for line in body.splitlines() if not line.startswith("#") and not line.startswith("**Decision"))
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if len(part.strip()) > 30]


def evidence_ids_from_brace_content(content: str, contracts_by_id: dict[str, dict[str, Any]]) -> list[str]:
    ids = []
    for token in brace_tokens(content):
        candidate = token.removeprefix("E:")
        contract = contracts_by_id.get(candidate)
        if contract:
            ids.append(str(contract.get("evidence_id") or candidate))
    return _dedupe(ids)


def contracts_by_evidence_alias(contracts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in contracts:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        for alias in evidence_id_aliases(evidence_id):
            by_id.setdefault(alias, row)
    return by_id


def evidence_id_aliases(evidence_id: str) -> list[str]:
    aliases = [evidence_id]
    match = re.match(r"^(.*?)(\d+)$", evidence_id)
    if match:
        prefix, digits = match.groups()
        unpadded = str(int(digits)) if digits.strip("0") else "0"
        aliases.append(f"{prefix}{unpadded}")
    return _dedupe(aliases)


def source_ids_from_brace_content(content: str, known_source_ids: set[str]) -> list[str]:
    tokens = brace_tokens(content)
    if tokens and all(token in known_source_ids for token in tokens):
        return _dedupe(tokens)
    return []


def brace_tokens(content: str) -> list[str]:
    return [token.strip() for token in re.split(r"[,;]", str(content or "")) if token.strip()]


def primary_section_for_role(role: str) -> str:
    text = role.lower()
    if any(token in text for token in ("counter", "scope", "boundary", "crux", "limit")):
        return "counterweights"
    if any(token in text for token in ("practical", "context")):
        return "practical_implication"
    return "answer_evidence"


def heading_matches_section(section_id: str, heading: str) -> bool:
    lowered = heading.lower()
    return (
        (section_id == "answer_evidence" and "best current" in lowered)
        or (section_id == "counterweights" and ("change" in lowered or "bound" in lowered))
        or (section_id == "practical_implication" and "practical" in lowered)
        or (section_id == "source_weighting" and "weight" in lowered)
    )


def compact_contract_for_prompt(row: dict[str, Any]) -> dict[str, Any]:
    return drop_empty(
        {
            "evidence_id": row.get("evidence_id"),
            "argument_move_ids": row.get("argument_move_ids"),
            "claim": row.get("claim"),
            "required": row.get("required"),
            "source_ids": row.get("source_ids"),
            "citation_source_ids": row.get("citation_source_ids"),
            "quantities": row.get("required_quantity_atoms"),
            "must_preserve_terms": row.get("must_preserve_terms"),
            "scope": row.get("population_scope"),
            "caveat": row.get("required_caveat"),
            "must_qualify_with": row.get("must_qualify_with"),
            "must_not_imply": row.get("must_not_imply"),
        }
    )


def drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}


def evidence_ids_in_text(text: str, known_evidence_ids: list[str]) -> list[str]:
    known = set(known_evidence_ids)
    if not known:
        return []
    return _dedupe(match.group(1) for match in re.finditer(r"\{E:([^{}\n]+)\}", str(text or "")) if match.group(1) in known)


def evidence_ids_in_contract_text(text: str, contracts: list[dict[str, Any]]) -> list[str]:
    contracts_by_id = contracts_by_evidence_alias(contracts)
    if not contracts_by_id:
        candidates = []
        for content in BRACE_TAG_RE.findall(text or ""):
            candidates.extend(brace_tokens(content))
        return [token.removeprefix("E:") for token in candidates if token.startswith("E:")]
    found = []
    for content in BRACE_TAG_RE.findall(text or ""):
        found.extend(evidence_ids_from_brace_content(content.strip(), contracts_by_id))
    found.extend(evidence_ids_from_source_citations(text, contracts))
    return _dedupe(found)


def evidence_ids_from_source_citations(text: str, contracts: list[dict[str, Any]]) -> list[str]:
    source_to_evidence: dict[str, list[str]] = {}
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        evidence_id = str(contract.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        for source_key in contract_source_match_keys(contract):
            source_to_evidence.setdefault(source_key, []).append(evidence_id)
    unique_source_to_evidence = {
        source_id: _dedupe(evidence_ids)
        for source_id, evidence_ids in source_to_evidence.items()
        if len(_dedupe(evidence_ids)) == 1
    }
    found = []
    for content in re.findall(r"\[([^\[\]\n]{1,300})\]", str(text or "")):
        for token in re.split(r"\s*(?:,|;)\s*", content):
            evidence_ids = unique_source_to_evidence.get(label_key(token))
            if evidence_ids:
                found.extend(evidence_ids)
    return found


def contract_source_match_keys(contract: dict[str, Any]) -> list[str]:
    values = [
        *_string_list(contract.get("citation_source_ids")),
        *_string_list(contract.get("source_ids")),
        *_string_list(contract.get("source_match_keys")),
        *_string_list(contract.get("source_labels")),
        *_string_list(contract.get("source_label")),
    ]
    return _dedupe(key for value in values if (key := label_key(value)))
