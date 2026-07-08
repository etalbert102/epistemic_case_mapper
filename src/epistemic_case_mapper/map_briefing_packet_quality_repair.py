from __future__ import annotations

from copy import deepcopy
from typing import Any


ROLE_SECTION_BUCKET = {
    "counterweight": "contrast_bundle_ids",
    "scope_boundary": "boundary_bundle_ids",
    "context": "context_bundle_ids",
    "mechanism": "context_bundle_ids",
    "strongest_support": "primary_bundle_ids",
    "quantitative_anchor": "primary_bundle_ids",
    "decision_crux": "primary_bundle_ids",
}

SECTION_BUCKETS = ("primary_bundle_ids", "contrast_bundle_ids", "boundary_bundle_ids", "context_bundle_ids")


def repair_packet_for_synthesis(packet: dict[str, Any], critique_adjudication: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    repaired = deepcopy(packet)
    claim_repairs, suppressed = _repair_or_suppress_unsafe_claim_bundles(repaired, critique_adjudication)
    rerouted = _repair_section_routing(repaired, critique_adjudication)
    retain_updates = _suppress_retain_items_for_suppressed_bundles(repaired, suppressed)
    warnings = _repair_warnings(critique_adjudication)
    coverage = repaired.get("coverage_report", {}) if isinstance(repaired.get("coverage_report"), dict) else {}
    repaired["coverage_report"] = {
        **coverage,
        "packet_quality_repair_claim_repair_count": len(claim_repairs),
        "packet_quality_repair_suppressed_bundle_count": len(suppressed),
        "packet_quality_repair_rerouted_section_count": len(rerouted),
        "packet_quality_repair_warning_count": len(warnings),
    }
    report = {
        "schema_id": "packet_quality_repair_report_v1",
        "status": _repair_status(suppressed=suppressed, rerouted=rerouted, warnings=warnings),
        "claim_repair_count": len(claim_repairs),
        "claim_repairs": claim_repairs,
        "suppressed_bundle_count": len(suppressed),
        "suppressed_bundle_ids": [row["bundle_id"] for row in suppressed],
        "suppressed_bundles": suppressed,
        "rerouted_section_count": len(rerouted),
        "rerouted_sections": rerouted,
        "suppressed_retain_item_count": len(retain_updates),
        "suppressed_retain_items": retain_updates,
        "warning_count": len(warnings),
        "warnings": warnings,
    }
    return repaired, report


def _repair_or_suppress_unsafe_claim_bundles(
    packet: dict[str, Any],
    critique_adjudication: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bundle_lookup = _bundle_lookup(packet)
    repaired: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for issue in critique_adjudication.get("claim_quality_issues", []) if isinstance(critique_adjudication.get("claim_quality_issues"), list) else []:
        if not isinstance(issue, dict) or str(issue.get("severity", "")).lower() not in {"high", "critical"}:
            continue
        bundle_id = str(issue.get("bundle_id", "")).strip()
        bundle = bundle_lookup.get(bundle_id)
        if not bundle:
            continue
        repaired_claim = _repair_claim_from_existing_fields(bundle)
        if repaired_claim:
            old_claim = str(bundle.get("claim", "")).strip()
            bundle["claim"] = repaired_claim
            bundle["claim_repaired_for_synthesis"] = True
            bundle["claim_repair_reason"] = str(issue.get("issue") or "Unsafe claim quality for synthesis.")
            _repair_matching_retain_statement(packet, bundle_id, old_claim, repaired_claim)
            repaired.append(
                {
                    "bundle_id": bundle_id,
                    "old_claim": old_claim,
                    "new_claim": repaired_claim,
                    "reason": bundle["claim_repair_reason"],
                }
            )
            continue
        bundle["synthesis_suppressed"] = True
        bundle["suppression_reason"] = str(issue.get("issue") or "Unsafe claim quality for synthesis.")
        bundle["suppression_source"] = issue.get("source", "packet_quality_repair")
        suppressed.append(
            {
                "bundle_id": bundle_id,
                "reason": bundle["suppression_reason"],
                "claim": bundle.get("claim", ""),
            }
        )
    suppressed_ids = {row["bundle_id"] for row in suppressed}
    if suppressed_ids:
        _remove_bundle_ids_from_section_views(packet, suppressed_ids)
    return repaired, suppressed


def _repair_claim_from_existing_fields(bundle: dict[str, Any]) -> str:
    role = str(bundle.get("decision_role", "")).strip()
    quantities = _string_list(bundle.get("quantity_values"))
    if role != "quantitative_anchor" or not quantities:
        return ""
    source = ", ".join(_string_list(bundle.get("source_labels"))[:1])
    quantity_text = "; ".join(quantities[:4])
    if source:
        return f"Quantitative anchor from {source}: {quantity_text}."
    return f"Quantitative anchor: {quantity_text}."


def _repair_matching_retain_statement(packet: dict[str, Any], bundle_id: str, old_claim: str, repaired_claim: str) -> None:
    for item in packet.get("must_retain_ledger", []) if isinstance(packet.get("must_retain_ledger"), list) else []:
        if not isinstance(item, dict) or bundle_id not in _string_list(item.get("bundle_ids")):
            continue
        if str(item.get("statement", "")).strip() == old_claim:
            item["statement"] = repaired_claim
            item["claim_repaired_for_synthesis"] = True


def _repair_section_routing(packet: dict[str, Any], critique_adjudication: dict[str, Any]) -> list[dict[str, Any]]:
    bundle_lookup = _bundle_lookup(packet)
    rerouted: list[dict[str, Any]] = []
    for section in packet.get("section_views", []) if isinstance(packet.get("section_views"), list) else []:
        if not isinstance(section, dict):
            continue
        section_name = str(section.get("section", "")).strip()
        for bucket in SECTION_BUCKETS:
            for bundle_id in list(_string_list(section.get(bucket))):
                bundle = bundle_lookup.get(bundle_id, {})
                if bundle.get("synthesis_suppressed"):
                    continue
                expected = ROLE_SECTION_BUCKET.get(str(bundle.get("decision_role", "")).strip())
                if expected and expected != bucket:
                    section[bucket] = [item for item in _string_list(section.get(bucket)) if item != bundle_id]
                    section[expected] = _dedupe([*_string_list(section.get(expected)), bundle_id])
                    rerouted.append(
                        {
                            "bundle_id": bundle_id,
                            "section": section_name,
                            "from_bucket": bucket,
                            "to_bucket": expected,
                            "reason": "role_bucket_mismatch",
                        }
                    )
    return _dedupe_dicts(rerouted, key_fields=("bundle_id", "section", "from_bucket", "to_bucket"))


def _suppress_retain_items_for_suppressed_bundles(packet: dict[str, Any], suppressed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suppressed_ids = {row["bundle_id"] for row in suppressed}
    if not suppressed_ids:
        return []
    updates = []
    for item in packet.get("must_retain_ledger", []) if isinstance(packet.get("must_retain_ledger"), list) else []:
        if not isinstance(item, dict):
            continue
        bundle_ids = set(_string_list(item.get("bundle_ids")))
        if bundle_ids and bundle_ids <= suppressed_ids:
            item["synthesis_suppressed"] = True
            item["suppression_reason"] = "All supporting bundle IDs were suppressed for unsafe claim quality."
            updates.append({"item_id": item.get("item_id"), "bundle_ids": sorted(bundle_ids)})
    return updates


def _repair_warnings(critique_adjudication: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    for key in ("answer_frame_issues", "insufficiency_warnings", "misleading_synthesis_risks"):
        for row in critique_adjudication.get(key, []) if isinstance(critique_adjudication.get(key), list) else []:
            if isinstance(row, dict):
                warnings.append({"issue_type": key, **row})
    return warnings[:24]


def _remove_bundle_ids_from_section_views(packet: dict[str, Any], bundle_ids: set[str]) -> None:
    for section in packet.get("section_views", []) if isinstance(packet.get("section_views"), list) else []:
        if not isinstance(section, dict):
            continue
        for bucket in SECTION_BUCKETS:
            section[bucket] = [item for item in _string_list(section.get(bucket)) if item not in bundle_ids]


def _repair_status(*, suppressed: list[dict[str, Any]], rerouted: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> str:
    if suppressed or rerouted:
        return "repaired_with_warnings" if warnings else "repaired"
    return "warnings_only" if warnings else "no_repairs_needed"


def _bundle_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(bundle.get("bundle_id")): bundle
        for bundle in packet.get("evidence_bundles", [])
        if isinstance(bundle, dict) and str(bundle.get("bundle_id", "")).strip()
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _dedupe_dicts(rows: list[dict[str, Any]], *, key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = "|".join(str(row.get(field, "")).strip().lower() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result
