from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import networkx as nx
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

from epistemic_case_mapper.classical_ml import STOPWORDS
from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.prompt_templates import json_schema_block, render_prompt

VECTOR_CLUSTER_PROMPT_VERSION = "claim_vector_cluster_consolidation_v1_json"


def consolidate_claims_with_vector_llm(
    claims: list[dict[str, Any]],
    *,
    backend: str,
    artifact_dir: Path,
    decision_question: str,
    backend_timeout: int | None,
    backend_retries: int,
    min_claims: int = 1,
    max_cluster_size: int = 8,
    max_clusters: int = 60,
    run_backend: Callable[..., Any] = run_model_backend,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(claims) < 2 or backend.strip() == "prompt":
        return claims, _empty_report(claims, reason="too_few_claims_or_prompt_backend")
    clusters, cluster_report = _candidate_clusters(claims, max_cluster_size=max_cluster_size, max_clusters=max_clusters)
    cluster_dir = artifact_dir / "claim_consolidation_clusters"
    accepted_groups: list[dict[str, Any]] = []
    rejected_clusters: list[dict[str, Any]] = []
    assigned: set[str] = set()
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    for index, cluster in enumerate(clusters, start=1):
        cluster_ids = [claim_id for claim_id in cluster["claim_ids"] if claim_id not in assigned]
        if len(cluster_ids) < 2:
            continue
        prompt = _cluster_prompt(cluster_ids, claim_lookup, decision_question)
        stem = f"cluster_{index:03d}"
        write_markdown(cluster_dir / f"{stem}_prompt.txt", prompt)
        payload = _run_cluster_prompt(prompt, backend, backend_timeout, backend_retries, run_backend)
        write_json(cluster_dir / f"{stem}_canonical.json", payload or {})
        groups, rejection = _validated_groups(payload, cluster_ids, claim_lookup)
        if rejection:
            rejected_clusters.append({"cluster_id": stem, "claim_ids": cluster_ids, "reason": rejection})
            continue
        for group in groups:
            if any(claim_id in assigned for claim_id in group["member_claim_ids"]):
                continue
            accepted_groups.append(group)
            assigned.update(group["member_claim_ids"])
    consolidated = _apply_groups(claims, accepted_groups)
    if len(consolidated) < min_claims:
        return claims, {
            **_report(claims, claims, cluster_report, accepted_groups, rejected_clusters),
            "changed": False,
            "reason": "would_reduce_below_min_claims",
            "candidate_output_claim_count": len(consolidated),
            "min_claims": min_claims,
        }
    return consolidated, _report(claims, consolidated, cluster_report, accepted_groups, rejected_clusters)


def _candidate_clusters(claims: list[dict[str, Any]], *, max_cluster_size: int, max_clusters: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ids = [str(claim.get("claim_id", "")) for claim in claims]
    vectors = _claim_vectors(claims)
    similarities = cosine_similarity(vectors) if len(ids) > 1 else []
    graph = nx.Graph()
    graph.add_nodes_from(ids)
    edge_rows: list[dict[str, Any]] = []
    for left_index, left_id in enumerate(ids):
        for right_index in range(left_index + 1, len(ids)):
            right_id = ids[right_index]
            left, right = claims[left_index], claims[right_index]
            score = float(similarities[left_index][right_index])
            reason = _cluster_edge_reason(left, right, score)
            if not reason:
                continue
            graph.add_edge(left_id, right_id, weight=score, reason=reason)
            edge_rows.append({"left": left_id, "right": right_id, "score": round(score, 4), "reason": reason})
    clusters = _bounded_components(graph, claims, max_cluster_size=max_cluster_size, max_clusters=max_clusters)
    return clusters, {
        "schema_id": "claim_vector_cluster_report_v1",
        "method": "tfidf_svd_dense_vectors_with_exact_excerpt_edges",
        "candidate_edge_count": len(edge_rows),
        "candidate_cluster_count": len(clusters),
        "candidate_edges": edge_rows[:300],
        "candidate_clusters": clusters,
    }


def _claim_vectors(claims: list[dict[str, Any]]) -> Any:
    texts = [_claim_cluster_text(claim) for claim in claims]
    matrix = TfidfVectorizer(stop_words=list(STOPWORDS), ngram_range=(1, 2), min_df=1, norm="l2").fit_transform(texts)
    components = min(64, matrix.shape[0] - 1, matrix.shape[1] - 1)
    if components < 2:
        return matrix
    return normalize(TruncatedSVD(n_components=components, random_state=0).fit_transform(matrix))


def _cluster_edge_reason(left: dict[str, Any], right: dict[str, Any], score: float) -> str:
    if not _compatible_role_family(left, right):
        return ""
    if _same_source_role_excerpt(left, right):
        return "same_source_role_exact_excerpt"
    if score >= 0.78 and _same_direction_guard(left, right):
        return "high_vector_similarity"
    if score >= 0.72 and _same_source_role(left, right) and _same_direction_guard(left, right):
        return "same_source_role_vector_similarity"
    return ""


def _bounded_components(graph: nx.Graph, claims: list[dict[str, Any]], *, max_cluster_size: int, max_clusters: int) -> list[dict[str, Any]]:
    order = {str(claim.get("claim_id")): index for index, claim in enumerate(claims)}
    clusters: list[dict[str, Any]] = []
    for component in nx.connected_components(graph):
        ids = sorted(component, key=lambda claim_id: order.get(claim_id, len(order)))
        for window in _split_component(ids, max_cluster_size):
            if len(window) > 1:
                clusters.append({"claim_ids": window, "size": len(window)})
    clusters.sort(key=lambda row: (-row["size"], [order.get(claim_id, 0) for claim_id in row["claim_ids"]]))
    return clusters[:max_clusters]


def _split_component(ids: list[str], max_cluster_size: int) -> list[list[str]]:
    return [ids[index : index + max_cluster_size] for index in range(0, len(ids), max_cluster_size)]


def _cluster_prompt(cluster_ids: list[str], claim_lookup: dict[str, dict[str, Any]], decision_question: str) -> str:
    cards = [_claim_card(claim_lookup[claim_id]) for claim_id in cluster_ids if claim_id in claim_lookup]
    return render_prompt(
        ("Task", "You are adjudicating whether vector-neighbor claim cards should be consolidated."),
        ("Metadata", f"Prompt version: {VECTOR_CLUSTER_PROMPT_VERSION}\nDecision question: {decision_question}"),
        (
            "Rules",
            [
                "- Merge only claims that state the same evidence proposition.",
                "- Do not merge claims that differ in endpoint, population, geography, exposure dose, comparator, adjustment set, study design, or direction of effect.",
                "- If claims are related but meaningfully different, preserve them as separate claims.",
                "- A canonical claim must be entailed by every member claim's quoted evidence.",
                "- If numeric estimates differ, write a general canonical claim about direction/statistical interpretation; do not copy one member's exact number.",
                "- Use only claim IDs shown in the cards.",
                "- Prefer several smaller groups over one broad group.",
            ],
        ),
        ("Output Schema", json_schema_block(_cluster_schema(cluster_ids))),
        ("Claim Cards", "\n\n".join(cards)),
    )


def _cluster_schema(cluster_ids: list[str]) -> dict[str, Any]:
    return {
        "groups": [
            {
                "canonical_claim": "one sentence entailed by all member claims",
                "member_claim_ids": cluster_ids[:2],
                "rationale": "why these claims are the same proposition",
            }
        ],
        "preserve_claim_ids": cluster_ids,
    }


def _run_cluster_prompt(prompt: str, backend: str, timeout: int | None, retries: int, run_backend: Callable[..., Any]) -> dict[str, Any] | None:
    try:
        result = run_backend(prompt, backend, timeout_seconds=timeout, max_retries=retries)
    except (RuntimeError, ValueError):
        return None
    try:
        return json.loads(canonical_json_output(result.text))
    except json.JSONDecodeError:
        return None


def _validated_groups(payload: dict[str, Any] | None, cluster_ids: list[str], claim_lookup: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(payload, dict):
        return [], "invalid_json"
    groups = payload.get("groups", [])
    if not isinstance(groups, list):
        return [], "groups_not_list"
    known = set(cluster_ids)
    accepted: list[dict[str, Any]] = []
    used: set[str] = set()
    for group in groups:
        ids = [str(item) for item in group.get("member_claim_ids", [])] if isinstance(group, dict) else []
        ids = [claim_id for claim_id in ids if claim_id in known]
        if len(ids) < 2 or used & set(ids):
            continue
        canonical = str(group.get("canonical_claim", "")).strip()
        if not canonical:
            continue
        reason = _group_rejection_reason(ids, claim_lookup, canonical)
        if reason:
            continue
        accepted.append({"canonical_claim": canonical, "member_claim_ids": ids, "rationale": str(group.get("rationale", "")).strip()})
        used.update(ids)
    if not accepted:
        return [], "no_valid_merge_groups"
    return accepted, ""


def _group_rejection_reason(ids: list[str], claim_lookup: dict[str, dict[str, Any]], canonical_claim: str) -> str:
    claims = [claim_lookup[claim_id] for claim_id in ids if claim_id in claim_lookup]
    first = claims[0]
    if any(not _compatible_role_family(first, claim) for claim in claims[1:]):
        return "role_family_mismatch"
    if any(not _same_direction_guard(first, claim) for claim in claims[1:]):
        return "direction_conflict"
    if _canonical_uses_nonshared_decimal(canonical_claim, claims):
        return "canonical_uses_nonshared_numeric_estimate"
    return ""


def _apply_groups(claims: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_member = {claim_id: group for group in groups for claim_id in group["member_claim_ids"]}
    emitted_groups: set[int] = set()
    claim_lookup = {str(claim.get("claim_id")): claim for claim in claims}
    output: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = str(claim.get("claim_id"))
        group = by_member.get(claim_id)
        if group is None:
            output.append(claim)
            continue
        marker = id(group)
        if marker in emitted_groups:
            continue
        emitted_groups.add(marker)
        output.append(_canonical_claim(group, claim_lookup))
    return output


def _canonical_claim(group: dict[str, Any], claim_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    claims = [claim_lookup[claim_id] for claim_id in group["member_claim_ids"] if claim_id in claim_lookup]
    canonical = dict(_best_claim(claims))
    canonical["claim"] = group["canonical_claim"]
    canonical["supporting_claim_ids"] = group["member_claim_ids"]
    canonical["supporting_sources"] = sorted({str(claim.get("source_id")) for claim in claims if claim.get("source_id")})
    canonical["supporting_excerpts"] = _supporting_excerpts(claims)[:8]
    canonical["consolidation_method"] = "vector_cluster_llm_adjudicated"
    canonical["consolidation_rationale"] = group.get("rationale", "")
    return canonical


def _best_claim(claims: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(claims, key=lambda claim: (-_signal_score(str(claim.get("claim", ""))), len(str(claim.get("claim", ""))), str(claim.get("claim_id", ""))))[0]


def _supporting_excerpts(claims: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for claim in claims:
        row = {key: str(claim.get(key, "")) for key in ("claim_id", "source_id", "source_span", "excerpt")}
        key = (row["source_id"], row["source_span"], row["excerpt"])
        if row["excerpt"] and key not in seen:
            rows.append(row)
            seen.add(key)
    return rows


def _report(claims: list[dict[str, Any]], consolidated: list[dict[str, Any]], cluster_report: dict[str, Any], groups: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_id": "claim_consolidation_report_v1",
        "changed": len(consolidated) != len(claims),
        "method": "vector_cluster_llm_adjudicated",
        "input_claim_count": len(claims),
        "output_claim_count": len(consolidated),
        "vector_clusters": cluster_report,
        "merged_groups": groups,
        "rejected_clusters": rejected,
    }


def _empty_report(claims: list[dict[str, Any]], *, reason: str) -> dict[str, Any]:
    return {"schema_id": "claim_consolidation_report_v1", "changed": False, "method": "vector_cluster_llm_adjudicated", "reason": reason, "input_claim_count": len(claims), "output_claim_count": len(claims), "merged_groups": []}


def _claim_card(claim: dict[str, Any]) -> str:
    fields = {
        "claim_id": claim.get("claim_id"),
        "source_id": claim.get("source_id"),
        "role": claim.get("role"),
        "claim": claim.get("claim"),
        "source_span": claim.get("source_span"),
        "excerpt": _compact(str(claim.get("excerpt", "")), 600),
    }
    return json.dumps(fields, indent=2, ensure_ascii=False)


def _claim_cluster_text(claim: dict[str, Any]) -> str:
    return " ".join(str(claim.get(key, "")) for key in ("role", "claim", "excerpt", "source_id"))


def _same_source_role_excerpt(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _same_source_role(left, right) and _norm(left.get("excerpt", "")) == _norm(right.get("excerpt", "")) and bool(_norm(left.get("excerpt", "")))


def _same_source_role(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return str(left.get("source_id")) == str(right.get("source_id")) and str(left.get("role")) == str(right.get("role"))


def _compatible_role_family(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _role_family(str(left.get("role", ""))) == _role_family(str(right.get("role", "")))


def _role_family(role: str) -> str:
    return {"conclusion_support": "directional", "crux": "crux", "scope_limit": "limit", "background": "background", "implementation_constraint": "method"}.get(role, role or "other")


def _same_direction_guard(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_direction = _direction(str(left.get("claim", "")))
    right_direction = _direction(str(right.get("claim", "")))
    return "mixed" in {left_direction, right_direction} or left_direction == right_direction


def _direction(text: str) -> str:
    normalized = f" {_norm(text)} "
    null_markers = (" no association ", " not associated ", " no significant ", " non-significant ", " not statistically significant ", " confidence interval includes 1")
    harmful_markers = (" higher risk ", " increased risk ", " significantly associated with an increased ", " harmful ", " adverse ")
    beneficial_markers = (" lower risk ", " reduced risk ", " inverse association ", " protective ", " beneficial ")
    has_null = any(marker in normalized for marker in null_markers)
    has_harm = any(marker in normalized for marker in harmful_markers)
    has_benefit = any(marker in normalized for marker in beneficial_markers)
    if has_harm and not has_null and not has_benefit:
        return "harmful"
    if has_benefit and not has_null and not has_harm:
        return "beneficial"
    if has_null and not has_harm and not has_benefit:
        return "null"
    return "mixed"


def _canonical_uses_nonshared_decimal(canonical_claim: str, claims: list[dict[str, Any]]) -> bool:
    canonical_numbers = _decimal_numbers(canonical_claim)
    if not canonical_numbers:
        return False
    member_sets = [_decimal_numbers(_claim_cluster_text(claim)) for claim in claims]
    shared = set.intersection(*member_sets) if member_sets else set()
    return bool(canonical_numbers - shared)


def _decimal_numbers(text: str) -> set[str]:
    numbers: set[str] = set()
    for match in re.findall(r"\b\d+\.\d+\b", text):
        try:
            numbers.add(f"{float(match):.4g}")
        except ValueError:
            numbers.add(match)
    return numbers


def _signal_score(text: str) -> int:
    markers = ("confidence interval", "hazard ratio", "relative risk", "adjust", "population", "subgroup", "significant")
    lowered = text.lower()
    return sum(1 for marker in markers if marker in lowered)


def _compact(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())
