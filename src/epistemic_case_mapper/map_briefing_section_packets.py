from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.decision_argument_artifacts import compact_decision_argument_artifacts
from epistemic_case_mapper.io import write_json
from epistemic_case_mapper.map_briefing_section_quantities import section_quantitative_anchors


def section_synthesis_packet(title: str, full_contract: dict[str, Any]) -> dict[str, Any]:
    scaffold = (
        full_contract.get("_section_synthesis_scaffold", {})
        if isinstance(full_contract.get("_section_synthesis_scaffold"), dict)
        else {}
    )
    graph_packet = scaffold.get("graph_synthesis_packet", {}) if isinstance(scaffold.get("graph_synthesis_packet"), dict) else {}
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    title_key = title.lower()
    packet = {
        "section_goal": _section_goal(title_key),
        "argument_model": compact_argument_model(scaffold, title_key),
        "graph_summary": graph_packet.get("graph_summary", {}),
        "issue_clusters": _section_issue_clusters(title_key, graph_packet),
        "load_bearing_claims": _section_claims(title_key, graph_packet.get("load_bearing_claims", [])),
        "bridge_claims": _section_claims(title_key, graph_packet.get("bridge_claims", [])),
        "central_tensions": _section_tensions(title_key, graph_packet.get("central_tensions", [])),
        "decision_synthesis": _section_decision_synthesis(title_key, synthesis),
        "decision_argument_artifacts": compact_decision_argument_artifacts(scaffold, title_key),
        "quantitative_anchors": section_quantitative_anchors(title_key, scaffold),
        "style_instruction": _section_style_instruction(title_key),
    }
    return drop_empty_packet_values(packet)


def write_section_packets_artifact(artifacts: Any, packets: list[dict[str, Any]]) -> Any:
    path = artifacts / "section_synthesis_packets.json"
    write_json(
        path,
        {
            "schema_id": "section_synthesis_packets_v1",
            "packet_count": len(packets),
            "packets": packets,
        },
    )
    return path


def compact_argument_model(scaffold: dict[str, Any], title_key: str) -> dict[str, Any]:
    argument_model = scaffold.get("argument_model", {}) if isinstance(scaffold.get("argument_model"), dict) else {}
    if not argument_model:
        return {}
    base = {
        "proposed_answer": argument_model.get("proposed_answer"),
        "confidence": argument_model.get("confidence"),
    }
    if "decision brief" in title_key:
        base.update(
            {
                "strongest_support": argument_model.get("strongest_support", [])[:2],
                "strongest_counterarguments": argument_model.get("strongest_counterarguments", [])[:2],
                "quantitative_anchors": argument_model.get("quantitative_anchors", [])[:2],
                "known_failure_modes": argument_model.get("known_failure_modes", [])[:2],
            }
        )
    elif "practical" in title_key:
        base.update(
            {
                "scope_boundaries": argument_model.get("scope_boundaries", [])[:4],
                "known_failure_modes": argument_model.get("known_failure_modes", [])[:2],
            }
        )
    elif "scope" in title_key or "exception" in title_key:
        base.update(
            {
                "scope_boundaries": argument_model.get("scope_boundaries", [])[:5],
                "strongest_counterarguments": argument_model.get("strongest_counterarguments", [])[:2],
            }
        )
    elif "crux" in title_key:
        base.update(
            {
                "cruxes": argument_model.get("cruxes", [])[:5],
                "strongest_counterarguments": argument_model.get("strongest_counterarguments", [])[:3],
            }
        )
    elif "limit" in title_key:
        base.update(
            {
                "missing_evidence": argument_model.get("missing_evidence", [])[:4],
                "known_failure_modes": argument_model.get("known_failure_modes", [])[:4],
            }
        )
    else:
        base.update(
            {
                "strongest_support": argument_model.get("strongest_support", [])[:4],
                "strongest_counterarguments": argument_model.get("strongest_counterarguments", [])[:3],
                "quantitative_anchors": argument_model.get("quantitative_anchors", [])[:3],
            }
        )
    return drop_empty_packet_values(base)


def drop_empty_packet_values(packet: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in packet.items() if value not in ({}, [], "", None)}


def _section_goal(title_key: str) -> str:
    if "decision brief" in title_key:
        return "State the answer frame directly, with confidence and the one or two reasons that carry the read."
    if "practical read" in title_key:
        return "Translate the graph into concrete practical implications and exception checks."
    if "why this read" in title_key:
        return "Explain the reasoning path from load-bearing claims through the central tensions."
    if "evidence carrying" in title_key:
        return "Group the carrying evidence by issue cluster rather than listing isolated claims."
    if "scope" in title_key or "exception" in title_key:
        return "Separate the default case from boundaries, exceptions, and bridge conditions."
    if "crux" in title_key:
        return "Convert central graph tensions and bridge claims into human-readable cruxes."
    if "limit" in title_key:
        return "Name what the map does not establish and keep orphan claims out of the main answer."
    return "Improve this section while preserving its local source-grounded obligations."


def _section_issue_clusters(title_key: str, graph_packet: dict[str, Any]) -> list[dict[str, Any]]:
    clusters = [item for item in graph_packet.get("issue_clusters", []) if isinstance(item, dict)]
    if "decision brief" in title_key or "practical read" in title_key:
        return _compact_issue_clusters(clusters[:3])
    if "evidence carrying" in title_key or "why this read" in title_key:
        return _compact_issue_clusters(clusters[:5])
    if "scope" in title_key or "exception" in title_key:
        return _compact_issue_clusters([item for item in clusters if _cluster_has_scope_signal(item)][:4] or clusters[:3])
    if "crux" in title_key:
        return _compact_issue_clusters([item for item in clusters if _cluster_has_tension(item)][:4] or clusters[:3])
    return _compact_issue_clusters(clusters[:3])


def _compact_issue_clusters(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for cluster in clusters:
        compact.append(
            {
                "label": cluster.get("label"),
                "claim_count": cluster.get("claim_count"),
                "relation_mix": cluster.get("relation_mix", {}),
                "synthesis_job": cluster.get("synthesis_job"),
                "representative_claims": _compact_claims(cluster.get("representative_claims", []), limit=3),
            }
        )
    return compact


def _section_claims(title_key: str, value: Any) -> list[dict[str, Any]]:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    if "limit" in title_key:
        return []
    if "crux" in title_key or "why this read" in title_key:
        return _compact_claims(rows, limit=5)
    return _compact_claims(rows, limit=3)


def _section_tensions(title_key: str, value: Any) -> list[dict[str, Any]]:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    if "decision brief" in title_key:
        return _compact_tensions(rows, limit=2)
    if "crux" in title_key or "scope" in title_key or "why this read" in title_key:
        return _compact_tensions(rows, limit=5)
    if "evidence carrying" in title_key:
        return _compact_tensions(rows, limit=3)
    return _compact_tensions(rows, limit=2)


def _section_decision_synthesis(title_key: str, synthesis: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(synthesis, dict):
        return {}
    if "decision brief" in title_key:
        return {"bottom_line": synthesis.get("bottom_line"), "central_tensions": synthesis.get("central_tensions", [])[:2]}
    if "practical read" in title_key:
        return {"recommendations": synthesis.get("recommendations", [])[:4], "exceptions": synthesis.get("exceptions", [])[:3]}
    if "scope" in title_key or "exception" in title_key:
        return {"scope_boundaries": synthesis.get("scope_boundaries", [])[:5], "exceptions": synthesis.get("exceptions", [])[:5]}
    if "crux" in title_key:
        return {"cruxes": synthesis.get("cruxes", [])[:5], "central_tensions": synthesis.get("central_tensions", [])[:4]}
    if "limit" in title_key:
        return {"limits": synthesis.get("limits", [])[:5]}
    return {
        "evidence_lines": synthesis.get("evidence_lines", [])[:5],
        "central_tensions": synthesis.get("central_tensions", [])[:3],
    }


def _section_style_instruction(title_key: str) -> str:
    if "crux" in title_key:
        return "Use concrete crux names; avoid generic relation labels and internal graph language."
    if "evidence carrying" in title_key:
        return "Lead with the strongest cluster-level proposition, then name the counterweight or scope boundary."
    if "decision brief" in title_key:
        return "Keep the opening short, direct, and calibrated."
    return "Prefer polished human prose over internal map terminology."


def _compact_claims(value: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    compact: list[dict[str, Any]] = []
    for row in rows[:limit]:
        compact.append(
            {
                "claim_id": row.get("claim_id"),
                "claim": _short_text(str(row.get("claim", "")), 260),
                "source": row.get("source"),
                "weight": row.get("weight"),
                "role": row.get("role"),
                "evidence_family": row.get("evidence_family"),
            }
        )
    return compact


def _compact_tensions(value: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    compact: list[dict[str, Any]] = []
    for row in rows[:limit]:
        left = row.get("left", {}) if isinstance(row.get("left"), dict) else {}
        right = row.get("right", {}) if isinstance(row.get("right"), dict) else {}
        compact.append(
            {
                "relation_id": row.get("relation_id"),
                "relation_type": row.get("relation_type"),
                "left_claim": _short_text(str(left.get("claim", "")), 220),
                "right_claim": _short_text(str(right.get("claim", "")), 220),
                "why_it_matters": _short_text(str(row.get("why_it_matters") or row.get("rationale", "")), 260),
                "failure_condition": _short_text(str(row.get("failure_condition", "")), 220),
            }
        )
    return compact


def _cluster_has_scope_signal(cluster: dict[str, Any]) -> bool:
    text = json.dumps(cluster, ensure_ascii=False).lower()
    return any(marker in text for marker in ("scope", "subgroup", "boundary", "implementation", "condition", "exception"))


def _cluster_has_tension(cluster: dict[str, Any]) -> bool:
    mix = cluster.get("relation_mix", {}) if isinstance(cluster.get("relation_mix"), dict) else {}
    return int(mix.get("negative", 0)) > 0


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."
