from __future__ import annotations

import re
from typing import Any


def build_direct_source_synthesis_comparison_report(
    *,
    question: str,
    packet: dict[str, Any],
    briefing_text: str,
    baseline_text: str = "",
    baseline_path: str | None = None,
) -> dict[str, Any]:
    """Compare packet-based memo retention against a flat source-synthesis baseline.

    This report deliberately measures traceable anchors rather than prose
    quality. It can be run against a live direct-source baseline, a saved deep
    research baseline, or no baseline yet.
    """

    anchors = _packet_anchors(packet)
    current = _score_text_against_anchors(briefing_text, anchors)
    baseline = _score_text_against_anchors(baseline_text, anchors) if baseline_text.strip() else {}
    return {
        "schema_id": "direct_source_synthesis_comparison_report_v1",
        "status": _status(current, baseline),
        "question": question,
        "baseline_path": baseline_path,
        "baseline_available": bool(baseline_text.strip()),
        "direct_source_baseline_prompt": build_direct_source_baseline_prompt(question),
        "anchor_inventory": {
            "source_label_count": len(anchors["source_labels"]),
            "quantity_count": len(anchors["quantities"]),
            "bundle_anchor_count": len(anchors["bundle_anchors"]),
        },
        "packet_memo_retention": current,
        "baseline_retention": baseline,
        "retention_delta_vs_baseline": _delta(current, baseline),
        "notes": _notes(current, baseline),
    }


def build_direct_source_baseline_prompt(question: str) -> str:
    return "\n".join(
        [
            "You are an analyst producing decision-ready synthesis from the provided source documents.",
            "",
            f"Decision question: {question}",
            "",
            "Use only the provided sources. Answer the question directly, preserve important quantities,",
            "surface counterevidence and scope limits, cite sources by their simplest labels, and name",
            "important gaps or uncertainty. Write a coherent briefing memo, not a literature summary.",
        ]
    )


def _packet_anchors(packet: dict[str, Any]) -> dict[str, list[Any]]:
    bundles = [row for row in packet.get("evidence_bundles", []) if isinstance(row, dict)]
    return {
        "source_labels": sorted({label for row in bundles for label in _string_list(row.get("source_labels"))}),
        "quantities": sorted({quantity for row in bundles for quantity in _string_list(row.get("quantity_values"))}),
        "bundle_anchors": [_bundle_anchor(row) for row in bundles if _bundle_anchor(row)["terms"]],
    }


def _score_text_against_anchors(text: str, anchors: dict[str, list[Any]]) -> dict[str, Any]:
    lowered = text.lower()
    source_labels = [str(row) for row in anchors["source_labels"]]
    quantities = [str(row) for row in anchors["quantities"]]
    bundle_anchors = [row for row in anchors["bundle_anchors"] if isinstance(row, dict)]
    mentioned_sources = [label for label in source_labels if label.lower() in lowered]
    mentioned_quantities = [quantity for quantity in quantities if quantity.lower() in lowered]
    covered_bundles = [row["bundle_id"] for row in bundle_anchors if _anchor_covered(row, lowered)]
    return {
        "source_label_mentions": len(mentioned_sources),
        "source_label_total": len(source_labels),
        "source_label_coverage": _ratio(len(mentioned_sources), len(source_labels)),
        "quantity_mentions": len(mentioned_quantities),
        "quantity_total": len(quantities),
        "quantity_coverage": _ratio(len(mentioned_quantities), len(quantities)),
        "bundle_anchor_mentions": len(covered_bundles),
        "bundle_anchor_total": len(bundle_anchors),
        "bundle_anchor_coverage": _ratio(len(covered_bundles), len(bundle_anchors)),
        "missing_source_labels": [label for label in source_labels if label not in mentioned_sources][:30],
        "missing_quantities": [quantity for quantity in quantities if quantity not in mentioned_quantities][:30],
        "missing_bundle_ids": [row["bundle_id"] for row in bundle_anchors if row["bundle_id"] not in covered_bundles][:30],
    }


def _bundle_anchor(bundle: dict[str, Any]) -> dict[str, Any]:
    claim = str(bundle.get("claim", ""))
    terms = _content_terms(claim)[:6]
    return {
        "bundle_id": str(bundle.get("bundle_id", "")),
        "decision_role": str(bundle.get("decision_role", "")),
        "terms": terms,
    }


def _anchor_covered(anchor: dict[str, Any], lowered_text: str) -> bool:
    terms = [str(term).lower() for term in anchor.get("terms", []) if str(term).strip()]
    if not terms:
        return False
    required = 2 if len(terms) >= 3 else 1
    return sum(1 for term in terms if term in lowered_text) >= required


def _delta(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if not baseline:
        return {"status": "baseline_not_available"}
    return {
        "source_label_mentions": int(current.get("source_label_mentions", 0)) - int(baseline.get("source_label_mentions", 0)),
        "quantity_mentions": int(current.get("quantity_mentions", 0)) - int(baseline.get("quantity_mentions", 0)),
        "bundle_anchor_mentions": int(current.get("bundle_anchor_mentions", 0)) - int(baseline.get("bundle_anchor_mentions", 0)),
    }


def _status(current: dict[str, Any], baseline: dict[str, Any]) -> str:
    if not baseline:
        return "comparison_pending_baseline"
    delta = _delta(current, baseline)
    if all(int(delta.get(key, 0)) >= 0 for key in ("source_label_mentions", "quantity_mentions", "bundle_anchor_mentions")):
        return "packet_memo_retains_at_least_as_many_traceable_anchors"
    return "baseline_retains_more_traceable_anchors"


def _notes(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    notes = ["This report compares traceable retention anchors only; it does not score prose quality or argument sophistication."]
    if not baseline:
        notes.append("No direct-source baseline text was supplied, so only packet-memo retention and the baseline prompt are emitted.")
    elif int(current.get("quantity_mentions", 0)) < int(baseline.get("quantity_mentions", 0)):
        notes.append("The baseline retains more exact quantities than the packet-based memo.")
    return notes


def _content_terms(text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for term in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text.lower()):
        if term in _STOPWORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 1.0


_STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "between",
    "could",
    "from",
    "have",
    "into",
    "more",
    "should",
    "that",
    "their",
    "there",
    "this",
    "were",
    "with",
    "would",
}
