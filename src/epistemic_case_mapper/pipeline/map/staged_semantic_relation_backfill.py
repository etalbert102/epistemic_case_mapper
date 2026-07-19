from __future__ import annotations

from typing import Any

from epistemic_case_mapper.submission_manifest import WorkedRegion


def finalize_sparse_relation_graph(
    *,
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    pair_packets: list[dict[str, Any]],
    permitted_types: set[str],
    region: WorkedRegion,
    relation_index: int,
    seen: set[tuple[str, str, str]],
    min_relation_count: int = 0,
    allow_deterministic_fallback: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    if not accepted and allow_deterministic_fallback:
        from epistemic_case_mapper.pipeline.map.staged_semantic_sources import _fallback_relation

        fallback = _fallback_relation(pair_packets, permitted_types)
        if fallback is not None:
            fallback["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
            relation_index += 1
            accepted.append(fallback)
            seen.add((fallback["source_claim"], fallback["target_claim"], fallback["relation_type"]))
            rejected.append(
                {
                    "reason": "model_under_related_used_deterministic_fallback",
                    "source_claim": fallback["source_claim"],
                    "target_claim": fallback["target_claim"],
                    "relation_type": fallback["relation_type"],
                }
            )
    if allow_deterministic_fallback:
        accepted, relation_index, densification_rows = _densify_sparse_fallback_relations(
            accepted=accepted,
            pair_packets=pair_packets,
            permitted_types=permitted_types,
            region=region,
            relation_index=relation_index,
            seen=seen,
            min_relation_count=min_relation_count,
        )
    else:
        densification_rows = []
    if densification_rows:
        rejected.append(
            {
                "reason": "relation_graph_sparse_used_deterministic_densification",
                "added_relation_count": len(densification_rows),
                "added_relations": densification_rows,
            }
        )
    return accepted, rejected, relation_index


def _densify_sparse_fallback_relations(
    *,
    accepted: list[dict[str, Any]],
    pair_packets: list[dict[str, Any]],
    permitted_types: set[str],
    region: WorkedRegion,
    relation_index: int,
    seen: set[tuple[str, str, str]],
    min_relation_count: int = 0,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    if not pair_packets:
        return accepted, relation_index, []
    unique_claim_ids = {
        str(packet[side].get("claim_id", ""))
        for packet in pair_packets
        for side in ("left", "right")
        if isinstance(packet.get(side), dict)
    }
    target_count = min(len(pair_packets), max(min_relation_count, 1, min(8, len(unique_claim_ids) // 6)))
    if len(accepted) >= target_count:
        return accepted, relation_index, []
    added: list[dict[str, Any]] = []
    covered = {str(relation.get("source_claim", "")) for relation in accepted} | {str(relation.get("target_claim", "")) for relation in accepted}
    ordered_packets = sorted(
        pair_packets,
        key=lambda packet: (
            sum(1 for side in ("left", "right") if str(packet[side].get("claim_id", "")) in covered),
            -float(packet.get("candidate_score", 0) or 0),
            str(packet.get("pair_id", "")),
        ),
    )
    for packet in ordered_packets:
        if len(accepted) >= target_count:
            break
        from epistemic_case_mapper.pipeline.map.staged_semantic_sources import _fallback_relation

        fallback = _fallback_relation([packet], permitted_types)
        if fallback is None:
            continue
        key = (fallback["source_claim"], fallback["target_claim"], fallback["relation_type"])
        reverse_key = (fallback["target_claim"], fallback["source_claim"], fallback["relation_type"])
        if key in seen or reverse_key in seen:
            continue
        fallback["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
        relation_index += 1
        fallback["relation_provenance"] = "deterministic_sparse_graph_backfill"
        fallback["requires_review"] = True
        fallback["relation_confidence"] = "low"
        fallback["graph_densification"] = {
            "reason": "accepted_relation_count_below_claim_volume_floor",
            "candidate_pair_id": packet.get("pair_id"),
            "candidate_score": packet.get("candidate_score"),
            "candidate_reason": packet.get("candidate_reason"),
        }
        accepted.append(fallback)
        seen.add(key)
        covered.update([fallback["source_claim"], fallback["target_claim"]])
        added.append(
            {
                "relation_id": fallback["relation_id"],
                "source_claim": fallback["source_claim"],
                "target_claim": fallback["target_claim"],
                "relation_type": fallback["relation_type"],
            }
        )
    return accepted, relation_index, added
