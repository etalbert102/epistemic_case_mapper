from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import read_yaml, write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.semantic_pipeline import MAP_PROMPT_VERSION, VALID_ENTAILMENT, validate_map_candidate
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest


CLAIM_EXTRACTION_PROMPT_VERSION = "staged_claim_extraction_prompt_v1_json"
RELATION_PROMPT_VERSION = "staged_relation_prompt_v1_json"
VALID_CLAIM_ROLES = {
    "conclusion_support",
    "crux",
    "scope_limit",
    "implementation_constraint",
    "background",
    "other",
}


@dataclass(frozen=True)
class SourceSpan:
    span_id: str
    source_id: str
    source_span: str
    text: str


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    source_id: str
    title: str
    start_line: int
    end_line: int
    numbered_text: str
    plain_text: str
    spans: tuple[SourceSpan, ...]


@dataclass(frozen=True)
class StagedMapResult:
    output_path: Path
    artifact_dir: Path
    claim_count: int
    relation_count: int
    rejected_claim_count: int
    rejected_relation_count: int
    failures: tuple[str, ...]


def run_staged_map(
    repo_root: Path,
    manifest_path: str,
    region_id: str,
    backend: str,
    output_path: str | Path | None = None,
    artifact_dir: str | Path | None = None,
    chunk_lines: int = 40,
    max_claims_per_chunk: int = 4,
    max_relation_pairs: int = 12,
    backend_timeout: int | None = 90,
    backend_retries: int = 1,
    validate: bool = True,
) -> StagedMapResult:
    manifest, region, case_manifest = _load_context(repo_root, manifest_path, region_id)
    artifacts = _artifact_dir(repo_root, region_id, artifact_dir)
    artifacts.mkdir(parents=True, exist_ok=True)

    chunks = _source_chunks(repo_root, case_manifest, region, chunk_lines)
    claims, rejected_claims = _extract_claims(
        repo_root=repo_root,
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        chunks=chunks,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifacts,
        max_claims_per_chunk=max_claims_per_chunk,
    )
    relations, relation_payloads, rejected_relations = _extract_relations(
        manifest=manifest,
        region=region,
        case_manifest=case_manifest,
        claims=claims,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        artifact_dir=artifacts,
        max_relation_pairs=max_relation_pairs,
    )
    final_map = _assemble_map(
        region=region,
        case_manifest=case_manifest,
        claims=claims,
        relations=relations,
        relation_payloads=relation_payloads,
    )
    target = Path(output_path or region.map_path)
    if not target.is_absolute():
        target = repo_root / target
    validation_target = artifacts / "candidate_map.json"
    write_json(validation_target, final_map)
    failures: list[str] = []
    if validate:
        failures = validate_map_candidate(repo_root, manifest_path, region_id, validation_target)
    if failures and validate:
        target = artifacts / "failed_candidate.json"
    write_json(target, final_map)
    write_json(
        artifacts / "run_summary.json",
        {
            "region_id": region.region_id,
            "backend": backend,
            "chunk_lines": chunk_lines,
            "max_claims_per_chunk": max_claims_per_chunk,
            "max_relation_pairs": max_relation_pairs,
            "backend_timeout": backend_timeout,
            "backend_retries": backend_retries,
            "chunks": [_chunk_summary(chunk) for chunk in chunks],
            "claim_count": len(claims),
            "relation_count": len(relations),
            "rejected_claims": rejected_claims,
            "rejected_relations": rejected_relations,
            "candidate_path": _relative(repo_root, validation_target),
            "output_path": _relative(repo_root, target),
            "failures": failures,
        },
    )
    return StagedMapResult(
        output_path=target,
        artifact_dir=artifacts,
        claim_count=len(claims),
        relation_count=len(relations),
        rejected_claim_count=len(rejected_claims),
        rejected_relation_count=len(rejected_relations),
        failures=tuple(failures),
    )


def _extract_claims(
    repo_root: Path,
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    chunks: list[SourceChunk],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    max_claims_per_chunk: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    claim_index = 1

    for chunk in chunks:
        span_lookup = {span.span_id: span for span in chunk.spans}
        chunk_accept_count = 0
        prompt = _claim_prompt(manifest, region, case_manifest, chunk, max_claims_per_chunk)
        write_markdown(artifact_dir / "claim_chunks" / f"{chunk.chunk_id}_prompt.txt", prompt)
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
            )
            raw = result.text
        except (RuntimeError, ValueError) as exc:
            fallback = _fallback_claim_for_chunk(chunk)
            if fallback is not None:
                key = (
                    fallback["source_id"],
                    _normalize_text(fallback["excerpt"]),
                    _normalize_text(fallback["claim"]),
                )
                if key not in seen:
                    seen.add(key)
                    fallback["claim_id"] = f"{region.id_prefix}_c{claim_index:03d}"
                    claim_index += 1
                    accepted.append(fallback)
                    rejected.append(
                        {
                            "chunk_id": chunk.chunk_id,
                            "reason": "backend_error_used_deterministic_fallback",
                            "error": str(exc),
                            "span_id": fallback["span_id"],
                        }
                    )
                    continue
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "backend_error", "error": str(exc)})
            continue
        write_markdown(artifact_dir / "claim_chunks" / f"{chunk.chunk_id}_raw.txt", raw)
        payload = _parse_model_json(raw)
        write_json(artifact_dir / "claim_chunks" / f"{chunk.chunk_id}_canonical.json", payload or {})
        if not isinstance(payload, dict):
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "invalid_json"})
            continue
        proposals = payload.get("claims", [])
        if not isinstance(proposals, list) and "claim" in payload:
            proposals = [payload]
        if not isinstance(proposals, list):
            rejected.append({"chunk_id": chunk.chunk_id, "reason": "claims_not_list"})
            continue
        for proposal in proposals:
            claim, reason = _normalize_claim_proposal(proposal, span_lookup)
            if claim is None:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": reason, "proposal": proposal})
                continue
            key = (
                claim["source_id"],
                _normalize_text(claim["excerpt"]),
                _normalize_text(claim["claim"]),
            )
            if key in seen:
                rejected.append({"chunk_id": chunk.chunk_id, "reason": "duplicate_claim", "proposal": proposal})
                continue
            seen.add(key)
            claim["claim_id"] = f"{region.id_prefix}_c{claim_index:03d}"
            claim_index += 1
            accepted.append(claim)
            chunk_accept_count += 1
        if chunk_accept_count == 0:
            fallback = _fallback_claim_for_chunk(chunk)
            if fallback is not None:
                key = (
                    fallback["source_id"],
                    _normalize_text(fallback["excerpt"]),
                    _normalize_text(fallback["claim"]),
                )
                if key not in seen:
                    seen.add(key)
                    fallback["claim_id"] = f"{region.id_prefix}_c{claim_index:03d}"
                    claim_index += 1
                    accepted.append(fallback)
                    rejected.append(
                        {
                            "chunk_id": chunk.chunk_id,
                            "reason": "model_under_extracted_used_deterministic_fallback",
                            "span_id": fallback["span_id"],
                        }
                    )
    write_json(artifact_dir / "accepted_claims.json", {"claims": accepted, "rejected": rejected})
    return accepted, rejected


def _extract_relations(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    claims: list[dict[str, Any]],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifact_dir: Path,
    max_relation_pairs: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if len(claims) < 2:
        return [], [], [{"reason": "too_few_claims"}]
    pair_packets = _candidate_relation_pairs(claims, max_relation_pairs)
    claim_ids = {claim["claim_id"] for claim in claims}
    permitted_types = manifest.relation_ontology.permitted_types()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    relation_index = 1

    for packet in pair_packets:
        prompt = _relation_pair_prompt(manifest, region, case_manifest, packet)
        write_markdown(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_prompt.txt", prompt)
        try:
            result = run_model_backend(
                prompt,
                backend,
                timeout_seconds=backend_timeout,
                max_retries=backend_retries,
            )
            raw = result.text
        except (RuntimeError, ValueError) as exc:
            rejected.append({"pair_id": packet["pair_id"], "reason": "backend_error", "error": str(exc)})
            continue
        write_markdown(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_raw.txt", raw)
        payload = _parse_model_json(raw)
        write_json(artifact_dir / "relation_pairs" / f"{packet['pair_id']}_canonical.json", payload or {})
        if not isinstance(payload, dict):
            rejected.append({"pair_id": packet["pair_id"], "reason": "invalid_json"})
            continue
        payloads.append(payload)
        relation, reason = _normalize_relation_proposal(payload, claim_ids, permitted_types, packet)
        if relation is None:
            rejected.append({"pair_id": packet["pair_id"], "reason": reason, "proposal": payload})
            continue
        key = (relation["source_claim"], relation["target_claim"], relation["relation_type"])
        if key in seen:
            rejected.append({"pair_id": packet["pair_id"], "reason": "duplicate_relation", "proposal": payload})
            continue
        seen.add(key)
        relation["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
        relation_index += 1
        accepted.append(relation)
    if not accepted:
        fallback = _fallback_relation(pair_packets, permitted_types)
        if fallback is not None:
            fallback["relation_id"] = f"{region.id_prefix}_r{relation_index:03d}"
            accepted.append(fallback)
            rejected.append(
                {
                    "reason": "model_under_related_used_deterministic_fallback",
                    "source_claim": fallback["source_claim"],
                    "target_claim": fallback["target_claim"],
                    "relation_type": fallback["relation_type"],
                }
            )
    write_json(artifact_dir / "accepted_relations.json", {"relations": accepted, "rejected": rejected})
    return accepted, payloads, rejected


def _assemble_map(
    region: WorkedRegion,
    case_manifest: CaseManifest,
    claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    relation_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    cruxes = [
        str(crux)
        for payload in relation_payloads
        for crux in (payload.get("crux_candidates", []) if isinstance(payload.get("crux_candidates", []), list) else [])
    ]
    if not cruxes and relations:
        cruxes = [
            f"{relations[0]['source_claim']} {relations[0]['relation_type']} {relations[0]['target_claim']} is a candidate crux for the question."
        ]
    distinctions = [
        str(item)
        for payload in relation_payloads
        for item in (
            payload.get("similar_but_not_identical", [])
            if isinstance(payload.get("similar_but_not_identical", []), list)
            else []
        )
    ]
    evidence_rows = [
        [
            f"Does {claim['claim_id']} quote exact source text?",
            "Survives",
            f"{claim['source_id']} {claim['source_span']}: {claim['excerpt']}",
        ]
        for claim in claims[: max(1, region.thresholds.min_evidence_rows)]
    ]
    return {
        "title": f"{case_manifest.title} Staged Map",
        "status": "human-review-needed",
        "prompt_procedure": MAP_PROMPT_VERSION,
        "pipeline": "staged_chunked_mapper_v1",
        "evidence_mode": "source_grounded",
        "sources": [source.source_id for source in _required_sources(case_manifest, region)],
        "claims": claims,
        "relations": relations,
        "crux_candidates": cruxes,
        "similar_but_not_identical": distinctions,
        "evidence_check": evidence_rows,
    }


def _claim_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    chunk: SourceChunk,
    max_claims: int,
) -> str:
    span_catalog = "\n".join(
        f"- span_id: {span.span_id}\n  source_span: {span.source_span}\n  text: {span.text}"
        for span in chunk.spans
    )
    return f"""You are selecting source-grounded claim candidates from one bounded source-span catalog.

Prompt version: {CLAIM_EXTRACTION_PROMPT_VERSION}
Region ID: {region.region_id}
Case question: {case_manifest.question}
Source ID: {chunk.source_id}
Source title: {chunk.title}
Line range: {chunk.start_line}-{chunk.end_line}

Source span catalog:
{span_catalog}

Return only JSON:
{{
  "claims": [
    {{
      "claim": "one concise claim supported by the excerpt",
      "span_id": "one span_id from the catalog",
      "entailed_by_excerpt": "yes|no|uncertain",
      "role": "conclusion_support|crux|scope_limit|implementation_constraint|background|other"
    }}
  ]
}}

Rules:
- Return at most {max_claims} claims.
- Do not include claim_id. Deterministic code assigns IDs later.
- Do not include source_id, source_span, or excerpt. Deterministic code derives them from span_id.
- Use only span IDs shown in the catalog.
- Prefer claims that affect the case question, not bibliographic metadata.
- If the chunk has no useful claim, return {{"claims": []}}.
"""


def _relation_pair_prompt(
    manifest: SubmissionManifest,
    region: WorkedRegion,
    case_manifest: CaseManifest,
    packet: dict[str, Any],
) -> str:
    left = packet["left"]
    right = packet["right"]
    relation_types = ", ".join(sorted(manifest.relation_ontology.permitted_types()))
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
- If no defensible relation exists, set source_claim and target_claim to null and relation_type to "none".
"""


def _normalize_claim_proposal(
    proposal: Any,
    span_lookup: dict[str, SourceSpan],
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
    if role not in VALID_CLAIM_ROLES:
        role = "other"
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


def _source_chunks(repo_root: Path, case_manifest: CaseManifest, region: WorkedRegion, chunk_lines: int) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    for source in _required_sources(case_manifest, region):
        lines = _source_text(repo_root, source).splitlines()
        if not lines:
            continue
        for start in range(0, len(lines), chunk_lines):
            selected = lines[start : start + chunk_lines]
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
            chunks.append(
                SourceChunk(
                    chunk_id=_safe_filename(chunk_id),
                    source_id=source.source_id,
                    title=source.title,
                    start_line=start_line,
                    end_line=end_line,
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
        "span_count": len(chunk.spans),
        "spans": [span.__dict__ for span in chunk.spans],
    }


def _parse_model_json(text: str) -> dict[str, Any] | list[Any] | None:
    canonical = canonical_json_output(text)
    try:
        return json.loads(canonical)
    except json.JSONDecodeError:
        return None


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
