from __future__ import annotations

from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_citation_care import build_citation_care_report
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_evidence_anchoring import (
    render_evidence_tagged_memo,
)


def section_citation_validation_issues(
    tagged_markdown: str,
    contracts: list[dict[str, Any]],
) -> list[str]:
    evidence_by_source = _contract_source_evidence(contracts)
    rendered = render_evidence_tagged_memo(
        tagged_markdown,
        contracts,
        source_evidence_by_source=evidence_by_source,
    )["memo"]
    report = build_citation_care_report(
        rendered,
        contracts,
        source_evidence_by_source=evidence_by_source,
    )
    issues = []
    for warning in _list(report.get("warnings")):
        if not isinstance(warning, dict):
            continue
        warning_type = str(warning.get("warning_type") or "")
        if warning_type == "citation_claim_entailment_mismatch":
            issues.append(f"citation_claim_entailment_mismatch:{warning.get('source_id') or 'unknown'}")
        elif warning_type == "uncited_material_claim":
            issues.append("uncited_material_claim")
    return _dedupe(issues)


def _contract_source_evidence(contracts: list[dict[str, Any]]) -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}
    for contract in contracts:
        for row in _list(contract.get("source_evidence")):
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("source_id") or "").strip()
            if not source_id:
                continue
            evidence.setdefault(source_id, []).extend(_string_list(row.get("excerpts")))
    return {source_id: _dedupe(excerpts) for source_id, excerpts in evidence.items() if excerpts}
