from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.classical_ml import tfidf_near_duplicate_pairs
from epistemic_case_mapper.config_profiles import (
    EpistemicConfigProfile,
    config_profile_from_manifest_payload,
    profile_vocabulary,
)
from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION, VALID_ENTAILMENT, validate_map_candidate
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest

def _relation_pair_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    packet: dict[str, Any],
) -> str:
    left = packet["left"]
    right = packet["right"]
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
    scaffold = json.dumps(_map_quality_scaffold(manifest, region, case_manifest), indent=2)
    profile_rules = _profile_relation_rule_text(case_manifest)
    return f"""You are classifying one possible relation between two already-validated claim cards.

Prompt version: {RELATION_PROMPT_VERSION}
Region ID: {region.region_id}
Pair ID: {packet['pair_id']}
Case question: {case_manifest.question}

Allowed relation types:
{relation_types}

Claim A:
- claim_id: {left['claim_id']}
- claim: {left['claim']}
- source_id: {left['source_id']}
- role: {left['role']}
- excerpt: {left['excerpt']}

Claim B:
- claim_id: {right['claim_id']}
- claim: {right['claim']}
- source_id: {right['source_id']}
- role: {right['role']}
- excerpt: {right['excerpt']}

Deterministic map-quality scaffold:
{scaffold}

Return only JSON:
{{
  "pair_id": "{packet['pair_id']}",
  "source_claim": "claim_id or null",
  "target_claim": "claim_id or null",
  "relation_type": "one allowed relation type or none",
  "rationale": "why this edge improves reasoning without overstating support, or why no edge is warranted",
  "crux_candidates": ["crux text naming claim IDs"],
  "similar_but_not_identical": ["distinction text naming claim IDs"]
}}

Rules:
- Do not include relation_id. Deterministic code assigns IDs later.
- Use only the two claim IDs shown above.
- Use only allowed relation types, or use relation_type "none".
- Use the map-quality scaffold to preserve cruxes, tensions, source limitations, and scope boundaries.
- Prefer decision-relevant relations over generic ones: use crux_for when one claim would change the decision read of the other, depends_on when a recommendation only works under a condition, and in_tension_with/challenges when a scope limit or contrary finding weakens a support claim.
{profile_rules}
- Use similar_to only when the claims are redundant enough that a reviewer could merge them.
- Use refines only when the rationale names the exact boundary, population, endpoint, mechanism, or implementation condition being refined.
- If no defensible relation exists, set source_claim and target_claim to null and relation_type to "none".
"""

def _relation_batch_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    packets: list[dict[str, Any]],
    batch_id: str,
) -> str:
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
    pair_blocks = "\n\n".join(_relation_pair_block(packet) for packet in packets)
    pair_ids = ", ".join(packet["pair_id"] for packet in packets)
    scaffold = json.dumps(_map_quality_scaffold(manifest, region, case_manifest), indent=2)
    profile_rules = _profile_relation_rule_text(case_manifest)
    return f"""You are classifying possible relations between already-validated claim cards.

Prompt version: {RELATION_BATCH_PROMPT_VERSION}
Region ID: {region.region_id}
Batch ID: {batch_id}
Case question: {case_manifest.question}

Allowed relation types:
{relation_types}

Pairs to classify:
{pair_blocks}

Deterministic map-quality scaffold:
{scaffold}

Return only JSON:
{{
  "relations": [
    {{
      "pair_id": "one of: {pair_ids}",
      "source_claim": "claim_id or null",
      "target_claim": "claim_id or null",
      "relation_type": "one allowed relation type or none",
      "rationale": "why this edge improves reasoning without overstating support, or why no edge is warranted",
      "crux_candidates": ["crux text naming claim IDs"],
      "similar_but_not_identical": ["distinction text naming claim IDs"]
    }}
  ]
}}

Rules:
- Return exactly one object for each pair ID in this batch.
- Do not include relation_id. Deterministic code assigns IDs later.
- Use only the two claim IDs shown for each pair.
- Use only allowed relation types, or use relation_type "none".
- Use the map-quality scaffold to preserve cruxes, tensions, source limitations, and scope boundaries.
- Prefer decision-relevant relations over generic ones: use crux_for when one claim would change the decision read of the other, depends_on when a recommendation only works under a condition, and in_tension_with/challenges when a scope limit or contrary finding weakens a support claim.
{profile_rules}
- Use similar_to only when the claims are redundant enough that a reviewer could merge them.
- Use refines only when the rationale names the exact boundary, population, endpoint, mechanism, or implementation condition being refined.
- If no defensible relation exists for a pair, set source_claim and target_claim to null and relation_type to "none".
"""

def _relation_pair_block(packet: dict[str, Any]) -> str:
    left = packet["left"]
    right = packet["right"]
    return f"""Pair ID: {packet['pair_id']}
Claim A:
- claim_id: {left['claim_id']}
- claim: {left['claim']}
- source_id: {left['source_id']}
- role: {left['role']}
- excerpt: {left['excerpt']}

Claim B:
- claim_id: {right['claim_id']}
- claim: {right['claim']}
- source_id: {right['source_id']}
- role: {right['role']}
- excerpt: {right['excerpt']}"""

def _normalize_claim_proposal(
    proposal: Any,
    span_lookup: dict[str, SourceSpan],
    valid_roles: set[str] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(proposal, dict):
        return None, "claim_not_object"
    span_id = str(proposal.get("span_id", proposal.get("spanId", ""))).strip()
    if span_id not in span_lookup:
        return None, "unknown_span_id"
    span = span_lookup[span_id]
    claim_text = str(proposal.get("claim", "")).strip()
    if not claim_text:
        return None, "missing_claim"
    entailed = str(proposal.get("entailed_by_excerpt", "uncertain")).strip().lower()
    if entailed not in VALID_ENTAILMENT:
        entailed = "uncertain"
    role = str(proposal.get("role", "other")).strip()
    allowed_roles = valid_roles or VALID_CLAIM_ROLES
    if role not in allowed_roles:
        role = "other"
    if role not in allowed_roles:
        role = sorted(allowed_roles)[0] if allowed_roles else "other"
    return (
        {
            "claim_id": "",
            "claim": claim_text,
            "source_id": span.source_id,
            "source_span": span.source_span,
            "excerpt": span.text,
            "entailed_by_excerpt": entailed,
            "role": role,
        },
        "",
    )

def _fallback_claim_for_chunk(chunk: SourceChunk) -> dict[str, Any] | None:
    span = _best_fallback_span(chunk)
    if span is None:
        return None
    return {
        "claim_id": "",
        "claim": span.text,
        "source_id": span.source_id,
        "source_span": span.source_span,
        "excerpt": span.text,
        "entailed_by_excerpt": "yes",
        "role": _fallback_role(span.text),
        "span_id": span.span_id,
        "extraction_method": "deterministic_fallback_span",
    }

def _best_fallback_span(chunk: SourceChunk) -> SourceSpan | None:
    candidates = [span for span in chunk.spans if _span_signal_score(span.text) > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda span: (_span_signal_score(span.text), len(span.text)))

def _span_signal_score(text: str) -> int:
    stripped = text.strip()
    lowered = stripped.lower()
    if not stripped or stripped.startswith("#"):
        return 0
    if lowered.startswith(("source:", "author:", "date:", "retrieved:", "use in worked region:")):
        return 0
    score = 1
    for marker in (
        "%",
        "odds",
        "bayes",
        "favor",
        "likely",
        "disagreement",
        "challenge",
        "critique",
        "not measure",
        "limitation",
        "failed",
        "won",
        "risk",
        "could",
    ):
        if marker in lowered:
            score += 2
    return score

def _fallback_role(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("not measure", "not peer reviewed", "limitation", "failed", "risk")):
        return "scope_limit"
    if any(marker in lowered for marker in ("disagreement", "critique", "challenge")):
        return "crux"
    if any(marker in lowered for marker in ("favor", "likely", "%", "odds")):
        return "conclusion_support"
    return "background"

def _normalize_relation_proposal(
    proposal: Any,
    claim_ids: set[str],
    permitted_types: set[str],
    packet: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(proposal, dict):
        return None, "relation_not_object"
    if str(proposal.get("pair_id", packet["pair_id"])).strip() != packet["pair_id"]:
        return None, "wrong_pair_id"
    source_claim = str(proposal.get("source_claim", "")).strip()
    target_claim = str(proposal.get("target_claim", "")).strip()
    relation_type = str(proposal.get("relation_type", "")).strip()
    rationale = str(proposal.get("rationale", "")).strip()
    if relation_type == "none":
        return None, "no_relation"
    if source_claim not in claim_ids or target_claim not in claim_ids:
        return None, "unknown_endpoint"
    packet_ids = {packet["left"]["claim_id"], packet["right"]["claim_id"]}
    if source_claim not in packet_ids or target_claim not in packet_ids:
        return None, "endpoint_not_in_pair"
    if source_claim == target_claim:
        return None, "self_relation"
    if relation_type not in permitted_types:
        return None, "unknown_relation_type"
    if not rationale:
        return None, "missing_rationale"
    return (
        {
            "relation_id": "",
            "source_claim": source_claim,
            "target_claim": target_claim,
            "relation_type": relation_type,
            "rationale": rationale,
        },
        "",
    )

def _candidate_relation_pairs(claims: list[dict[str, Any]], max_pairs: int) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, int, dict[str, Any], dict[str, Any]]] = []
    for left_index, left in enumerate(claims):
        for right_index, right in enumerate(claims):
            if left_index >= right_index:
                continue
            score = _pair_score(left, right)
            if score <= 0:
                continue
            scored.append((score, left_index, right_index, left, right))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    packets = []
    for index, (_score, _left_index, _right_index, left, right) in enumerate(scored[:max_pairs], start=1):
        packets.append({"pair_id": f"pair_{index:03d}", "left": left, "right": right})
    return packets

def _fallback_relation(pair_packets: list[dict[str, Any]], permitted_types: set[str]) -> dict[str, Any] | None:
    if not pair_packets:
        return None
    packet = pair_packets[0]
    left = packet["left"]
    right = packet["right"]
    relation_type = _fallback_relation_type(left, right, permitted_types)
    if relation_type is None:
        return None
    return {
        "relation_id": "",
        "source_claim": left["claim_id"],
        "target_claim": right["claim_id"],
        "relation_type": relation_type,
        "rationale": (
            "Deterministic fallback edge: these high-priority cross-source claims were selected as a likely "
            "reasoning dependency after model relation classification produced no accepted edge. Human review "
            "should confirm the exact relation type before treating it as substantive."
        ),
        "extraction_method": "deterministic_fallback_pair",
    }

def _fallback_relation_type(left: dict[str, Any], right: dict[str, Any], permitted_types: set[str]) -> str | None:
    left_text = _normalize_text(f"{left.get('claim', '')} {left.get('excerpt', '')}")
    right_text = _normalize_text(f"{right.get('claim', '')} {right.get('excerpt', '')}")
    combined = f"{left_text} {right_text}"
    if "in_tension_with" in permitted_types and _looks_like_tension(left_text, right_text):
        return "in_tension_with"
    if "challenges" in permitted_types and any(
        marker in combined
        for marker in (
            "flawed",
            "no evidence",
            "not require",
            "without requiring",
            "critique",
            "reject",
            "failed",
        )
    ):
        return "challenges"
    if "crux_for" in permitted_types and {left.get("role"), right.get("role")} & {"crux"}:
        return "crux_for"
    if "refines" in permitted_types:
        return "refines"
    return next(iter(sorted(permitted_types)), None)

def _looks_like_tension(left_text: str, right_text: str) -> bool:
    lab_markers = ("lab leak", "research-related accident", "accidental lab")
    zoonosis_markers = ("zoonosis", "zoonotic", "natural")
    lab_left = any(marker in left_text for marker in lab_markers)
    lab_right = any(marker in right_text for marker in lab_markers)
    zoonosis_left = any(marker in left_text for marker in zoonosis_markers)
    zoonosis_right = any(marker in right_text for marker in zoonosis_markers)
    return (lab_left and zoonosis_right) or (lab_right and zoonosis_left)

def _pair_score(left: dict[str, Any], right: dict[str, Any]) -> int:
    score = 0
    if left.get("source_id") != right.get("source_id"):
        score += 3
    left_role = str(left.get("role", ""))
    right_role = str(right.get("role", ""))
    if "crux" in {left_role, right_role}:
        score += 4
    if {left_role, right_role} & {"scope_limit", "implementation_constraint"}:
        score += 3
    if {left_role, right_role} & {"conclusion_support"}:
        score += 2
    shared_terms = _content_terms(str(left.get("claim", ""))) & _content_terms(str(right.get("claim", "")))
    score += min(3, len(shared_terms))
    return score

def _content_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "but",
        "for",
        "from",
        "has",
        "have",
        "into",
        "not",
        "that",
        "the",
        "their",
        "this",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]{4,}", text.lower())
        if token not in stopwords
    }

def _source_chunks(
    repo_root: Path,
    case_manifest: CaseManifest,
    region: WorkedRegion,
    chunk_lines: int,
    chunk_overlap_lines: int,
) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    ordinal = 0
    step = max(1, chunk_lines - chunk_overlap_lines)
    for source in _required_sources(case_manifest, region):
        lines = _source_text(repo_root, source).splitlines()
        if not lines:
            continue
        for start in range(0, len(lines), step):
            selected = lines[start : start + chunk_lines]
            if not selected:
                continue
            start_line = start + 1
            end_line = start + len(selected)
            chunk_id = f"{source.source_id}_lines_{start_line}_{end_line}"
            numbered = "\n".join(f"{line_no}: {line}" for line_no, line in enumerate(selected, start=start_line))
            spans = tuple(
                SourceSpan(
                    span_id=f"{_safe_filename(source.source_id)}_s{line_no:04d}",
                    source_id=source.source_id,
                    source_span=f"lines {line_no}-{line_no}",
                    text=line.strip(),
                )
                for line_no, line in enumerate(selected, start=start_line)
                if line.strip()
            )
            ordinal += 1
            chunks.append(
                SourceChunk(
                    chunk_id=_safe_filename(chunk_id),
                    source_id=source.source_id,
                    title=source.title,
                    start_line=start_line,
                    end_line=end_line,
                    ordinal=ordinal,
                    numbered_text=numbered,
                    plain_text="\n".join(selected),
                    spans=spans,
                )
            )
    return chunks

def _chunk_summary(chunk: SourceChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "title": chunk.title,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "ordinal": chunk.ordinal,
        "signal_score": _chunk_signal_score(chunk),
        "span_count": len(chunk.spans),
        "spans": [span.__dict__ for span in chunk.spans],
    }

def _budget_chunks(
    chunks: list[SourceChunk],
    max_chunks_per_source: int | None,
    max_total_chunks: int | None,
) -> tuple[list[SourceChunk], list[dict[str, Any]]]:
    selected = list(chunks)
    skipped: list[dict[str, Any]] = []
    if max_chunks_per_source is not None:
        selected_ids: set[str] = set()
        by_source: dict[str, list[SourceChunk]] = {}
        for chunk in selected:
            by_source.setdefault(chunk.source_id, []).append(chunk)
        for source_chunks in by_source.values():
            ranked = sorted(source_chunks, key=_chunk_priority)
            kept = set(ranked[:max_chunks_per_source])
            selected_ids.update(chunk.chunk_id for chunk in kept)
            for chunk in source_chunks:
                if chunk not in kept:
                    skipped.append(_skipped_chunk_summary(chunk, "max_chunks_per_source"))
        selected = [chunk for chunk in selected if chunk.chunk_id in selected_ids]
    if max_total_chunks is not None and len(selected) > max_total_chunks:
        selected_set = _select_total_budget(selected, max_total_chunks)
        for chunk in selected:
            if chunk.chunk_id not in selected_set:
                skipped.append(_skipped_chunk_summary(chunk, "max_total_chunks"))
        selected = [chunk for chunk in selected if chunk.chunk_id in selected_set]
    selected.sort(key=lambda chunk: chunk.ordinal)
    skipped.sort(key=lambda item: int(item["ordinal"]))
    return selected, skipped

def _select_total_budget(chunks: list[SourceChunk], max_total_chunks: int) -> set[str]:
    by_source: dict[str, list[SourceChunk]] = {}
    for chunk in chunks:
        by_source.setdefault(chunk.source_id, []).append(chunk)
    if max_total_chunks < len(by_source):
        return {chunk.chunk_id for chunk in sorted(chunks, key=_chunk_priority)[:max_total_chunks]}
    selected_order: list[str] = []
    selected: set[str] = set()
    for source_chunks in sorted(by_source.values(), key=lambda items: min(chunk.ordinal for chunk in items)):
        if len(selected) >= max_total_chunks:
            break
        chunk_id = min(source_chunks, key=_chunk_priority).chunk_id
        selected.add(chunk_id)
        selected_order.append(chunk_id)
    if len(selected) >= max_total_chunks:
        return set(selected_order[:max_total_chunks])
    for chunk in sorted(chunks, key=_chunk_priority):
        if len(selected) >= max_total_chunks:
            break
        if chunk.chunk_id not in selected:
            selected.add(chunk.chunk_id)
            selected_order.append(chunk.chunk_id)
    return selected

def _skipped_chunk_summary(chunk: SourceChunk, reason: str) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "ordinal": chunk.ordinal,
        "signal_score": _chunk_signal_score(chunk),
        "span_count": len(chunk.spans),
        "reason": reason,
    }

def _chunk_priority(chunk: SourceChunk) -> tuple[int, int, int]:
    return (-_chunk_signal_score(chunk), -len(chunk.spans), chunk.ordinal)

def _chunk_signal_score(chunk: SourceChunk) -> int:
    return sum(_span_signal_score(span.text) for span in chunk.spans)

def _parse_model_json(text: str) -> dict[str, Any] | list[Any] | None:
    canonical = canonical_json_output(text)
    try:
        return json.loads(canonical)
    except json.JSONDecodeError:
        return None

def _relation_proposals(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "pair_id" in payload:
        return [payload]
    proposals = payload.get("relations", [])
    if isinstance(proposals, list):
        return [proposal for proposal in proposals if isinstance(proposal, dict)]
    return []

def _batches(items: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]

def _relation_batch_count(max_relation_pairs: int, relation_batch_size: int, claims: list[dict[str, Any]]) -> int:
    if len(claims) < 2:
        return 0
    pair_count = len(_candidate_relation_pairs(claims, max_relation_pairs))
    if pair_count == 0:
        return 0
    return (pair_count + relation_batch_size - 1) // relation_batch_size

def _line_span_for_excerpt(chunk: SourceChunk, excerpt: str) -> str:
    chunk_lines = chunk.plain_text.splitlines()
    for offset, line in enumerate(chunk_lines):
        if excerpt in line:
            line_no = chunk.start_line + offset
            return f"lines {line_no}-{line_no}"
    return f"lines {chunk.start_line}-{chunk.end_line}"

def _excerpt_from_source_span(chunk: SourceChunk, source_span: str) -> str | None:
    match = re.search(r"lines?\s+(\d+)(?:\s*-\s*(\d+))?", source_span)
    if not match:
        return None
    start_line = int(match.group(1))
    end_line = int(match.group(2) or match.group(1))
    if start_line < chunk.start_line or end_line > chunk.end_line or end_line < start_line:
        return None
    lines = chunk.plain_text.splitlines()
    start_index = start_line - chunk.start_line
    end_index = end_line - chunk.start_line + 1
    excerpt = "\n".join(lines[start_index:end_index]).strip()
    return excerpt or None

def _load_context(repo_root: Path, manifest_path: str, region_id: str) -> tuple[SubmissionManifest, WorkedRegion, CaseManifest]:
    manifest = load_submission_manifest(repo_root, manifest_path)
    region = manifest.region_for_id(region_id)
    case = manifest.case_for_key(region.case_key)
    case_manifest = CaseManifest.model_validate(read_yaml(repo_root / case.case_path))
    return manifest, region, case_manifest

def _required_sources(case_manifest: CaseManifest, region: WorkedRegion) -> list[Source]:
    if not region.required_sources:
        return case_manifest.sources
    lookup = {source.source_id: source for source in case_manifest.sources}
    return [lookup[source_id] for source_id in region.required_sources if source_id in lookup]

def _source_text(repo_root: Path, source: Source) -> str:
    if source.text:
        return source.text
    if source.path:
        path = repo_root / source.path
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return source.excerpt or source.notes or ""

def _artifact_dir(repo_root: Path, region_id: str, artifact_dir: str | Path | None) -> Path:
    path = Path(artifact_dir or f"artifacts/semantic/{region_id}/staged")
    if not path.is_absolute():
        path = repo_root / path
    return path

def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()

def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")

def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()



# Explicit cross-module dependencies for compatibility facade removal.
from epistemic_case_mapper.staged_semantic_pipeline_runner import (
    RELATION_BATCH_PROMPT_VERSION,
    RELATION_PROMPT_VERSION,
    SourceChunk,
    SourceSpan,
    VALID_CLAIM_ROLES,
)
from epistemic_case_mapper.staged_semantic_quality import _map_quality_scaffold, _profile_relation_rule_text
