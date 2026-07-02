from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.llm_stress_eval import run_llm_stress_eval
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.submission_manifest import WorkedRegion, load_submission_manifest


@dataclass(frozen=True)
class Loss:
    loss_id: str
    loss_type: str
    lost_item: str
    flat_baseline_omission: str
    case_map_preserves: str


@dataclass(frozen=True)
class RewriteRequirement:
    requirement_id: str
    loss_id: str
    loss_type: str
    instruction: str
    claim_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    source_refs: tuple[str, ...]
    claim_anchors: tuple[str, ...]
    relation_anchors: tuple[str, ...]
    required_phrases: tuple[str, ...]
    required_terms: tuple[str, ...]
    claim_roles: tuple[str, ...] = ()
    relation_types: tuple[str, ...] = ()
    relation_rationales: tuple[str, ...] = ()
    reader_anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class PacketSlot:
    section: str
    text: str
    requirement_id: str
    loss_id: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test whether LLM stress findings help produce better syntheses against erosion-audit losses."
    )
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="submission_manifest.yaml")
    parser.add_argument("--region", action="append", required=True, help="Region ID. May be passed multiple times.")
    parser.add_argument("--backend", default="ollama:llama3.2:3b", help="Synthesis and stress backend.")
    parser.add_argument("--judge-backend", help="Judge backend. Defaults to --backend.")
    parser.add_argument("--output-dir", default="artifacts/synthesis_uplift_eval/latest")
    parser.add_argument("--backend-timeout", type=int, default=120)
    parser.add_argument("--backend-retries", type=int, default=0)
    parser.add_argument("--skip-stress-run", action="store_true", help="Reuse an existing stress report when present.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_submission_manifest(repo_root, args.manifest)

    rows = []
    for region_id in args.region:
        try:
            region = manifest.region_for_id(region_id)
        except KeyError:
            print(f"unknown_region {region_id}", file=sys.stderr)
            return 1
        row = _run_region(
            repo_root=repo_root,
            manifest_path=args.manifest,
            region=region,
            backend=args.backend,
            judge_backend=args.judge_backend or args.backend,
            output_dir=output_dir / region_id,
            timeout_seconds=args.backend_timeout,
            max_retries=args.backend_retries,
            skip_stress_run=args.skip_stress_run,
        )
        rows.append(row)
        print(
            f"{region_id}: stress_wins={row['summary']['stress_wins']} "
            f"map_only_wins={row['summary']['map_only_wins']} ties={row['summary']['ties']} "
            f"invalid_judgments={row['summary']['invalid_judgments']}"
        )

    report = {
        "schema_id": "synthesis_uplift_eval_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": args.backend,
        "judge_backend": args.judge_backend or args.backend,
        "regions": rows,
        "summary": _aggregate_summary(rows),
    }
    write_json(output_dir / "synthesis_uplift_eval.json", report)
    write_markdown(output_dir / "SYNTHESIS_UPLIFT_EVAL.md", _markdown_report(report))
    print(f"Wrote {(output_dir / 'synthesis_uplift_eval.json').relative_to(repo_root).as_posix()}")
    print(f"Wrote {(output_dir / 'SYNTHESIS_UPLIFT_EVAL.md').relative_to(repo_root).as_posix()}")
    return 0


def _run_region(
    *,
    repo_root: Path,
    manifest_path: str,
    region: WorkedRegion,
    backend: str,
    judge_backend: str,
    output_dir: Path,
    timeout_seconds: int,
    max_retries: int,
    skip_stress_run: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stress_dir = output_dir / "stress"
    stress_json = stress_dir / "llm_stress_eval.json"
    if not skip_stress_run or not stress_json.exists():
        run_llm_stress_eval(
            repo_root=repo_root,
            manifest_path=manifest_path,
            region_id=region.region_id,
            backend=backend,
            output_dir=stress_dir,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    stress_report = json.loads(stress_json.read_text(encoding="utf-8"))
    losses = _parse_losses(repo_root / region.audit_path)
    baseline = _read(repo_root / region.baseline_path)
    map_payload = _read_map_payload(repo_root, region)
    map_text = json.dumps(map_payload, indent=2)
    requirements = _compile_rewrite_requirements(losses, map_payload, stress_report)
    write_json(output_dir / "rewrite_requirements.json", {"requirements": [_requirement_dict(req) for req in requirements]})
    write_markdown(output_dir / "REWRITE_REQUIREMENTS.md", _requirements_markdown(requirements))

    map_only_prompt = _synthesis_prompt(region, baseline, map_text, losses, requirements=(), stress_report=None)
    stress_prompt = _synthesis_prompt(region, baseline, map_text, losses, requirements=requirements, stress_report=stress_report)
    write_markdown(output_dir / "map_only_prompt.txt", map_only_prompt)
    write_markdown(output_dir / "stress_assisted_prompt.txt", stress_prompt)

    map_only = _run_synthesis_backend(map_only_prompt, backend, timeout_seconds, max_retries, map_payload, ())
    stress_assisted = _run_synthesis_backend(
        stress_prompt, backend, timeout_seconds, max_retries, map_payload, requirements
    )
    initial_stress_coverage = _deterministic_requirement_coverage(stress_assisted, requirements)
    if _needs_repair(initial_stress_coverage):
        write_markdown(output_dir / "stress_assisted_initial_synthesis.md", stress_assisted)
        repair_prompt = _repair_synthesis_prompt(region, stress_assisted, initial_stress_coverage, requirements)
        write_markdown(output_dir / "stress_assisted_repair_prompt.txt", repair_prompt)
        stress_assisted = _run_synthesis_backend(
            repair_prompt, backend, timeout_seconds, max_retries, map_payload, requirements
        )
        repaired_coverage = _deterministic_requirement_coverage(stress_assisted, requirements)
        if _needs_repair(repaired_coverage):
            write_markdown(output_dir / "stress_assisted_repaired_before_patch.md", stress_assisted)
            stress_assisted = _deterministic_patch_synthesis(stress_assisted, repaired_coverage, requirements)
    map_only = _clean_reader_packet_metadata(map_only)
    stress_assisted = _clean_reader_packet_metadata(stress_assisted)
    write_markdown(output_dir / "map_only_synthesis.md", map_only)
    write_markdown(output_dir / "stress_assisted_synthesis.md", stress_assisted)
    deterministic_coverage = {
        "map_only": _deterministic_requirement_coverage(map_only, requirements),
        "stress_assisted": _deterministic_requirement_coverage(stress_assisted, requirements),
    }
    write_json(output_dir / "deterministic_requirement_coverage.json", deterministic_coverage)

    judgments = []
    for loss in losses:
        judgment_prompt = _single_loss_judgment_prompt(region, loss, map_only, stress_assisted)
        write_markdown(output_dir / "judgment_prompts" / f"{loss.loss_id}.txt", judgment_prompt)
        judgment_raw = _run_text_backend(judgment_prompt, judge_backend, timeout_seconds, max_retries)
        write_markdown(output_dir / "judgment_raw" / f"{loss.loss_id}.txt", judgment_raw)
        parsed = _parse_json(judgment_raw)
        if parsed is None:
            judgments.append({"loss_id": loss.loss_id, "parse_error": "judge_returned_invalid_json"})
            continue
        judgments.append(_normalize_loss_judgment(loss.loss_id, parsed))
    judgment = {"loss_judgments": judgments, "overall": _overall_from_loss_judgments(judgments)}
    write_json(output_dir / "judgment.json", judgment)

    summary = _region_summary(losses, judgment)
    summary["deterministic_coverage"] = {
        "map_only_clear": deterministic_coverage["map_only"]["clear_count"],
        "stress_assisted_clear": deterministic_coverage["stress_assisted"]["clear_count"],
        "map_only_partial": deterministic_coverage["map_only"]["partial_count"],
        "stress_assisted_partial": deterministic_coverage["stress_assisted"]["partial_count"],
        "requirement_count": len(requirements),
        "accepted_synthesis": _accepted_synthesis(deterministic_coverage),
    }
    return {
        "region_id": region.region_id,
        "loss_count": len(losses),
        "requirement_count": len(requirements),
        "paths": {
            "stress_report": _rel(repo_root, stress_json),
            "rewrite_requirements": _rel(repo_root, output_dir / "rewrite_requirements.json"),
            "deterministic_requirement_coverage": _rel(repo_root, output_dir / "deterministic_requirement_coverage.json"),
            "map_only_synthesis": _rel(repo_root, output_dir / "map_only_synthesis.md"),
            "stress_assisted_synthesis": _rel(repo_root, output_dir / "stress_assisted_synthesis.md"),
            "judgment": _rel(repo_root, output_dir / "judgment.json"),
        },
        "stress_summary": stress_report.get("summary", {}),
        "summary": summary,
    }


def _parse_losses(path: Path) -> list[Loss]:
    text = path.read_text(encoding="utf-8")
    starts = list(re.finditer(r"^loss_id:\s*([A-Za-z0-9_\-]+)\s*$", text, re.MULTILINE))
    losses: list[Loss] = []
    for index, match in enumerate(starts):
        start = match.start()
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[start:end]
        losses.append(
            Loss(
                loss_id=match.group(1),
                loss_type=_field(block, "loss_type"),
                lost_item=_field(block, "lost_item"),
                flat_baseline_omission=_field(block, "flat_baseline_omission"),
                case_map_preserves=_field(block, "case_map_preserves"),
            )
        )
    return losses


def _field(block: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.*?)(?=\n[a-z_]+:|\n\n[a-z_]+:|\Z)", block, re.MULTILINE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _synthesis_prompt(
    region: WorkedRegion,
    baseline: str,
    map_text: str,
    losses: list[Loss],
    requirements: tuple[RewriteRequirement, ...],
    stress_report: dict[str, Any] | None,
) -> str:
    loss_brief = "\n".join(
        f"- {loss.loss_id} ({loss.loss_type}): {loss.lost_item} Preserved by: {loss.case_map_preserves}"
        for loss in losses
    )
    stress_brief = "No stress report supplied."
    if stress_report is not None:
        stress_brief = _reference_safe_stress_brief(stress_report)
    requirement_brief = "No compiled rewrite requirements supplied."
    scaffold_brief = "No deterministic packet scaffold supplied."
    if requirements:
        requirement_brief = _requirements_prompt_block(requirements)
        scaffold_brief = _packet_scaffold_prompt_block(requirements)
    return "\n\n".join(
        (
            "You are revising a flat synthesis so it better preserves the decision space.",
            f"Region: {region.region_id}",
            "Write a concise decision-support packet for an informed reader. Return valid JSON only.",
            "Required JSON shape: "
            "{\"decision_brief\": \"readable bottom-line prose\", "
            "\"confidence\": \"low|medium|high\", "
            "\"decision_implications\": [\"action-relevant implication\"], "
            "\"top_cruxes\": [{\"crux\": \"...\", \"why_it_matters\": \"...\", \"current_read\": \"...\", \"would_change_if\": \"...\"}], "
            "\"evidence_roles\": {\"main_support\": [\"...\"], \"conflicting_evidence\": [\"...\"], \"scope_limits\": [\"...\"], \"method_limits\": [\"...\"]}, "
            "\"stress_caveats\": [\"decision-relevant caveat\"], "
            "\"audit_trail\": [\"map-backed distinction or source-role boundary\"]}",
            "Requirements:",
            "- Treat the validated rewrite requirements as the backbone of the synthesis.",
            "- Make the decision picture understandable before exposing the audit machinery.",
            "- Preserve the mapped claim and relation anchors before adding any stress finding.",
            "- Use stress findings only to add pressure, caveats, or uncertainty; do not let them replace map distinctions.",
            "- Preserve cruxes, caveats, source-role boundaries, and load-bearing relations.",
            "- Put readable prose in `decision_brief`; put checklist-like coverage material in `audit_trail`, not in the prose.",
            "- Use `top_cruxes` only for distinctions that could change a decision or confidence level.",
            "- Use `evidence_roles` to separate support, conflict, scope limits, and method limits.",
            "- Do not put bare claim IDs or relation IDs in reader-facing fields; write the actual distinction in words.",
            "- Keep uncertainty visible and avoid adding facts beyond the provided artifacts.",
            "- Prefer explicit distinctions over fluent compression when the distinction changes interpretation.",
            "- If a stress finding conflicts with a mapped source-backed distinction, keep the mapped distinction and phrase the stress finding as a question or caveat.",
            "How to use the deterministic scaffold:",
            "- Treat scaffold entries as minimum packet content, not as final prose.",
            "- Every scaffold evidence-role item should appear in the returned `evidence_roles`, unless it is promoted to a crux or decision implication.",
            "- Use scaffold crux candidates as candidates, not mandatory headings; merge overlapping candidates if that makes the packet easier to read.",
            "- Preserve scaffold audit items in `audit_trail` using reader-facing wording.",
            "- Do not include internal loss-analysis wording such as `flat baseline`, `baseline failure`, or `explicitly avoid`.",
            "Deterministic packet scaffold:\n" + scaffold_brief,
            "Internal erosion-audit losses to avoid; use these only as diagnostics, not as reader-facing wording:\n" + loss_brief,
            "Validated rewrite requirements:\n" + requirement_brief,
            "Stress findings:\n" + stress_brief,
            "Flat baseline to revise:\n" + baseline,
            "Structured map artifact:\n" + _truncate(map_text, 14000),
        )
    )


def _reference_safe_stress_brief(stress_report: dict[str, Any]) -> str:
    failed_prompt_ids = {
        issue.get("prompt_id")
        for issue in stress_report.get("reference_issues", [])
        if isinstance(issue, dict) and isinstance(issue.get("prompt_id"), str)
    }
    lines = []
    dropped = sorted(prompt_id for prompt_id in failed_prompt_ids if prompt_id)
    if dropped:
        lines.append(
            "Dropped stress findings from prompts with deterministic reference failures: " + ", ".join(dropped)
        )
    for finding in stress_report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        if finding.get("finding_type") == "reference_validation_issue":
            continue
        if finding.get("prompt_id") in failed_prompt_ids:
            continue
        lines.append(
            f"- {finding.get('severity', 'note')} {finding.get('finding_type', 'finding')}: {finding.get('reason', '')}"
        )
        if len(lines) >= 20:
            break
    return "\n".join(lines) if lines else "No reference-safe stress findings available."


def _compile_rewrite_requirements(
    losses: list[Loss],
    map_payload: dict[str, Any],
    stress_report: dict[str, Any],
) -> tuple[RewriteRequirement, ...]:
    claims = _claim_lookup(map_payload)
    relation_lookup = _relation_lookup(map_payload)
    safe_stress_terms = _safe_stress_terms(stress_report)
    requirements: list[RewriteRequirement] = []
    for index, loss in enumerate(losses, start=1):
        claim_ids, relation_ids = _preserved_ids(loss.case_map_preserves)
        source_refs = []
        claim_anchors = []
        relation_anchors = []
        claim_roles = []
        relation_types = []
        relation_rationales = []
        reader_anchors = []
        fallback_term_source = " ".join((loss.loss_type, loss.lost_item, loss.flat_baseline_omission))
        map_term_parts: list[str] = []
        for claim_id in claim_ids:
            claim = claims.get(claim_id)
            if claim is None:
                continue
            map_term_parts.append(_claim_text(claim))
            claim_anchors.append(f"{claim_id}: {_claim_statement(claim)}")
            claim_role = _as_text(claim.get("role") or claim.get("claim_type"))
            if claim_role:
                claim_roles.append(claim_role)
            reader_claim = _reader_claim_statement(claim)
            if reader_claim:
                reader_anchors.append(reader_claim)
            source_id = _as_text(claim.get("source_id"))
            source_span = _as_text(claim.get("source_span"))
            if source_id:
                source_refs.append(f"{source_id} {source_span}".strip())
        for relation_id in relation_ids:
            relation = relation_lookup.get(relation_id)
            if relation is None:
                continue
            relation_type = _as_text(relation.get("relation_type"))
            rationale = _as_text(relation.get("rationale"))
            map_term_parts.append(relation_type + " " + rationale)
            relation_anchors.append(f"{relation_id}: {_relation_statement(relation)}")
            if relation_type:
                relation_types.append(relation_type)
            if rationale:
                relation_rationales.append(rationale)
            reader_relation = _reader_relation_statement_from_claims(relation, claims)
            if reader_relation:
                reader_anchors.append(reader_relation)
        for stress_terms in safe_stress_terms:
            if _loss_overlap(loss, stress_terms):
                map_term_parts.append(" ".join(stress_terms))
        term_source = " ".join(part for part in map_term_parts if part) or fallback_term_source
        terms = _coverage_terms(term_source)
        phrases = _required_phrases(loss, claim_anchors, relation_anchors)
        requirements.append(
            RewriteRequirement(
                requirement_id=f"req_{index:03d}",
                loss_id=loss.loss_id,
                loss_type=loss.loss_type.strip("`"),
                instruction=_requirement_instruction(loss),
                claim_ids=tuple(claim_id for claim_id in claim_ids if claim_id in claims),
                relation_ids=tuple(relation_id for relation_id in relation_ids if relation_id in relation_lookup),
                source_refs=tuple(dict.fromkeys(source_refs)),
                claim_anchors=tuple(claim_anchors),
                relation_anchors=tuple(relation_anchors),
                required_phrases=tuple(phrases),
                required_terms=tuple(terms),
                claim_roles=tuple(dict.fromkeys(claim_roles)),
                relation_types=tuple(dict.fromkeys(relation_types)),
                relation_rationales=tuple(dict.fromkeys(relation_rationales)),
                reader_anchors=tuple(dict.fromkeys(reader_anchors)),
            )
        )
    return tuple(requirements)


def _requirement_instruction(loss: Loss) -> str:
    omission = loss.flat_baseline_omission or "The flat baseline compresses a loss-critical distinction."
    return (
        f"Preserve the `{loss.loss_type.strip('`')}` distinction from {loss.loss_id}: "
        f"{loss.lost_item} Explicitly avoid this baseline failure: {omission}"
    )


def _preserved_ids(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    claim_ids = tuple(dict.fromkeys(re.findall(r"\b[A-Za-z0-9_\-]+_c\d+\b", text)))
    relation_ids = tuple(dict.fromkeys(re.findall(r"\b[A-Za-z0-9_\-]+_r\d+\b", text)))
    return claim_ids, relation_ids


def _claim_lookup(map_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = _worked_map_payload(map_payload)
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    return {
        claim["claim_id"]: claim
        for claim in claims
        if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)
    }


def _relation_lookup(map_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = _worked_map_payload(map_payload)
    relations = payload.get("relations", []) if isinstance(payload, dict) else []
    return {
        relation["relation_id"]: relation
        for relation in relations
        if isinstance(relation, dict) and isinstance(relation.get("relation_id"), str)
    }


def _worked_map_payload(map_payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(map_payload.get("worked_map"), dict):
        return map_payload["worked_map"]
    return map_payload


def _claim_text(claim: dict[str, Any]) -> str:
    return " ".join(
        _as_text(claim.get(key))
        for key in ("claim", "text", "role", "source_id", "source_span", "excerpt")
    )


def _claim_statement(claim: dict[str, Any]) -> str:
    statement = _as_text(claim.get("claim") or claim.get("text"))
    role = _as_text(claim.get("role") or claim.get("claim_type"))
    source_id = _as_text(claim.get("source_id"))
    source_span = _as_text(claim.get("source_span"))
    parts = [statement]
    if role:
        parts.append(f"role={role}")
    if source_id:
        parts.append(f"source={source_id} {source_span}".strip())
    return "; ".join(part for part in parts if part)


def _relation_statement(relation: dict[str, Any]) -> str:
    source_claim = _as_text(relation.get("source_claim") or relation.get("source_claim_id"))
    target_claim = _as_text(relation.get("target_claim") or relation.get("target_claim_id"))
    relation_type = _as_text(relation.get("relation_type"))
    rationale = _as_text(relation.get("rationale"))
    edge = f"{source_claim} -> {target_claim}".strip()
    return "; ".join(part for part in (edge, relation_type, rationale) if part)


def _reader_relation_statement_from_claims(
    relation: dict[str, Any],
    claims: dict[str, dict[str, Any]],
) -> str:
    source_claim = _as_text(relation.get("source_claim") or relation.get("source_claim_id"))
    target_claim = _as_text(relation.get("target_claim") or relation.get("target_claim_id"))
    source_text = _reader_claim_statement(claims.get(source_claim, {}))
    target_text = _reader_claim_statement(claims.get(target_claim, {}))
    relation_type = _as_text(relation.get("relation_type"))
    rationale = _as_text(relation.get("rationale"))
    if rationale:
        return rationale
    if source_text and target_text and relation_type:
        return f"{_short_text(source_text, 120)} {relation_type} {_short_text(target_text, 120)}"
    return _relation_statement(relation)


def _safe_stress_terms(stress_report: dict[str, Any]) -> list[tuple[str, ...]]:
    failed_prompt_ids = {
        issue.get("prompt_id")
        for issue in stress_report.get("reference_issues", [])
        if isinstance(issue, dict) and isinstance(issue.get("prompt_id"), str)
    }
    terms = []
    for finding in stress_report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        if finding.get("finding_type") == "reference_validation_issue":
            continue
        if finding.get("prompt_id") in failed_prompt_ids:
            continue
        reason = _as_text(finding.get("reason"))
        if reason:
            terms.append(tuple(_coverage_terms(reason)))
    return terms


def _loss_overlap(loss: Loss, terms: tuple[str, ...]) -> bool:
    text = _normalize_for_coverage(" ".join((loss.loss_type, loss.lost_item, loss.flat_baseline_omission)))
    return any(term in text for term in terms[:8])


def _coverage_terms(text: str) -> list[str]:
    normalized = _normalize_for_coverage(text)
    candidates = re.findall(r"[a-z][a-z0-9\-]{3,}", normalized)
    stopwords = {
        "about",
        "after",
        "against",
        "also",
        "baseline",
        "because",
        "claim",
        "claims",
        "does",
        "doesn",
        "evidence",
        "explicit",
        "flat",
        "from",
        "into",
        "loss",
        "make",
        "more",
        "preserve",
        "preserves",
        "rather",
        "relation",
        "review",
        "source",
        "than",
        "that",
        "their",
        "this",
        "with",
        "without",
    }
    ordered = []
    for candidate in candidates:
        if candidate in stopwords or candidate.endswith("_id"):
            continue
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered[:14]


def _required_phrases(
    loss: Loss,
    claim_anchors: list[str],
    relation_anchors: list[str],
) -> list[str]:
    anchor_candidates = _phrase_candidates([*claim_anchors, *relation_anchors])
    if anchor_candidates:
        return anchor_candidates[:4]
    return _phrase_candidates([loss.lost_item, loss.flat_baseline_omission])[:4]


def _phrase_candidates(texts: list[str]) -> list[str]:
    candidates: list[str] = []
    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+|;\s+", text):
            phrase = _clean_required_phrase(sentence)
            if not phrase:
                continue
            if _is_meta_loss_text(phrase):
                continue
            if _is_directional_or_boundary_phrase(phrase) and phrase not in candidates:
                candidates.append(phrase)
    return candidates


def _clean_required_phrase(text: str) -> str:
    text = re.sub(r"^[A-Za-z0-9_\-]+:\s*", "", text)
    text = re.sub(r"\brole=[^;]+", "", text)
    text = re.sub(r"\bsource=[^;]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .;")
    if len(text.split()) < 5:
        return ""
    if len(text) <= 220:
        return text
    return text[:220].rsplit(" ", 1)[0]


def _is_directional_or_boundary_phrase(text: str) -> bool:
    normalized = _normalize_for_coverage(text)
    markers = (
        " than ",
        " rather than ",
        " versus ",
        " vs ",
        " between ",
        " separate ",
        " distinguish",
        " distinct ",
        " depends on",
        " requires ",
        " may be ",
        " not ",
        " does not ",
        " cannot ",
    )
    return any(marker in f" {normalized} " for marker in markers)


def _deterministic_requirement_coverage(synthesis: str, requirements: tuple[RewriteRequirement, ...]) -> dict[str, Any]:
    text = _normalize_for_coverage(synthesis)
    rows = []
    for req in requirements:
        term_hits = [term for term in req.required_terms if term in text]
        phrase_hits = [phrase for phrase in req.required_phrases if _phrase_present_in_synthesis(phrase, synthesis)]
        id_hits = [item for item in (*req.claim_ids, *req.relation_ids) if item.lower() in text]
        source_hits = [
            source_ref
            for source_ref in req.source_refs
            if source_ref.split()[0].lower() in text
        ]
        needed = min(4, max(2, len(req.required_terms) // 3))
        phrase_required = bool(req.required_phrases)
        phrase_ok = not phrase_required or bool(phrase_hits)
        if phrase_ok and (len(term_hits) >= needed or len(id_hits) >= 2):
            status = "clear"
        elif term_hits or id_hits or source_hits or phrase_hits:
            status = "partial"
        else:
            status = "missing"
        rows.append(
            {
                "requirement_id": req.requirement_id,
                "loss_id": req.loss_id,
                "status": status,
                "term_hits": term_hits,
                "phrase_hits": phrase_hits,
                "id_hits": id_hits,
                "source_hits": source_hits,
                "required_phrases": list(req.required_phrases),
                "required_terms": list(req.required_terms),
            }
        )
    return {
        "clear_count": sum(1 for row in rows if row["status"] == "clear"),
        "partial_count": sum(1 for row in rows if row["status"] == "partial"),
        "missing_count": sum(1 for row in rows if row["status"] == "missing"),
        "requirements": rows,
    }


def _needs_repair(coverage: dict[str, Any]) -> bool:
    return any(
        isinstance(row, dict) and row.get("status") != "clear"
        for row in coverage.get("requirements", [])
    )


def _phrase_present_in_synthesis(phrase: str, synthesis: str) -> bool:
    normalized_phrase = _normalize_for_coverage(phrase)
    normalized_synthesis = _normalize_for_coverage(synthesis)
    if normalized_phrase in normalized_synthesis:
        return True
    if _requires_exact_phrase_order(phrase):
        return False
    phrase_tokens = _content_token_set(phrase)
    if len(phrase_tokens) < 5:
        return False
    for segment in _reader_text_segments(synthesis):
        segment_tokens = _content_token_set(segment)
        if len(segment_tokens) < 4:
            continue
        overlap = len(phrase_tokens & segment_tokens) / len(phrase_tokens)
        if overlap >= 0.58:
            return True
    return False


def _requires_exact_phrase_order(phrase: str) -> bool:
    normalized = f" {_normalize_for_coverage(phrase)} "
    ordered_markers = (
        r"\bmay be\b.+\bthan\b",
        r"\brather than\b",
        r"\bslower\b.+\bthan\b",
        r"\bfaster\b.+\bthan\b",
        r"\bmore\b.+\bthan\b",
        r"\bless\b.+\bthan\b",
    )
    return any(re.search(marker, normalized) for marker in ordered_markers)


def _reader_text_segments(text: str) -> list[str]:
    segments = []
    for line in text.splitlines():
        stripped = line.strip(" -|\t")
        if not stripped or stripped.startswith("#") or stripped.startswith("|---"):
            continue
        segments.extend(
            segment.strip()
            for segment in re.split(r"(?<=[.!?])\s+|;\s+", stripped)
            if len(segment.split()) >= 4
        )
    return segments


def _accepted_synthesis(coverage: dict[str, Any]) -> str:
    map_only = coverage["map_only"]
    stress = coverage["stress_assisted"]
    if stress["clear_count"] > map_only["clear_count"]:
        return "stress_assisted"
    if stress["clear_count"] == map_only["clear_count"] and stress["partial_count"] > map_only["partial_count"]:
        return "stress_assisted"
    if stress["clear_count"] == map_only["clear_count"] and stress["partial_count"] == map_only["partial_count"]:
        return "tie"
    return "map_only"


def _requirements_prompt_block(requirements: tuple[RewriteRequirement, ...]) -> str:
    lines = []
    for req in requirements:
        refs = ", ".join(req.source_refs) or "no source refs recovered"
        ids = ", ".join((*req.claim_ids, *req.relation_ids)) or "no map IDs recovered"
        terms = ", ".join(req.required_terms[:8])
        phrases = " | ".join(req.required_phrases) or "none"
        anchors = " ".join(
            (
                "Claim anchors:",
                " | ".join(req.claim_anchors) or "none",
                "Relation anchors:",
                " | ".join(req.relation_anchors) or "none",
                "Reader anchors:",
                " | ".join(req.reader_anchors) or "none",
                "Relation types:",
                ", ".join(req.relation_types) or "none",
                "Claim roles:",
                ", ".join(req.claim_roles) or "none",
            )
        )
        lines.append(
            f"- {req.requirement_id} / {req.loss_id}: {req.instruction} "
            f"Anchors: {ids}. Source refs: {refs}. {anchors}. Coverage terms: {terms}."
            f" Directional phrases to preserve: {phrases}."
        )
    return "\n".join(lines)


def _packet_scaffold_prompt_block(requirements: tuple[RewriteRequirement, ...]) -> str:
    scaffold = _packet_scaffold(requirements)
    return json.dumps(scaffold, indent=2, ensure_ascii=True)


def _packet_scaffold(requirements: tuple[RewriteRequirement, ...]) -> dict[str, Any]:
    evidence_roles = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    for slot in _packet_slots_for_requirements(requirements):
        evidence_roles[slot.section].append(slot.text)
    for key, items in evidence_roles.items():
        evidence_roles[key] = _dedupe_text_items(items)
    audit_trail = [
        f"{req.loss_id}: {slot.text}"
        for req in requirements
        for slot in (_audit_slot_for_requirement(req),)
        if slot.text
    ]
    return {
        "purpose": "minimum map-backed packet content for the model to organize and phrase coherently",
        "evidence_roles": evidence_roles,
        "crux_candidates": _crux_candidates(requirements),
        "audit_trail": _dedupe_text_items(audit_trail),
        "forbidden_reader_language": [
            "flat baseline",
            "baseline failure",
            "explicitly avoid",
            "bare claim IDs",
            "bare relation IDs",
        ],
    }


def _crux_candidates(requirements: tuple[RewriteRequirement, ...]) -> list[dict[str, str]]:
    candidates = []
    requirement_lookup = {req.requirement_id: req for req in requirements}
    for slot in _packet_slots_for_requirements(requirements):
        if slot.section == "main_support":
            continue
        req = requirement_lookup.get(slot.requirement_id)
        candidates.append(
            {
                "candidate_crux": _short_text(slot.text, 140),
                "why_it_matters": _crux_why_it_matters(slot.section),
                "current_read": slot.text,
                "would_change_if": _crux_change_condition(slot.section, req),
            }
        )
        if len(candidates) >= 5:
            break
    return candidates


def _crux_why_it_matters(section: str) -> str:
    if section == "conflicting_evidence":
        return "It marks evidence that should not be collapsed into one bottom-line answer without resolving the disagreement."
    if section == "scope_limits":
        return "It bounds where the conclusion applies and prevents over-generalizing the packet."
    if section == "method_limits":
        return "It affects how strongly the evidence can support the decision."
    return "It is a load-bearing mapped distinction for the decision packet."


def _crux_change_condition(section: str, req: RewriteRequirement | None) -> str:
    anchor = ""
    if req is not None:
        anchor = _first_reader_anchor(req)
    if section == "conflicting_evidence":
        return "A stronger source or method comparison resolved this tension."
    if section == "scope_limits":
        return "The same claim was shown to apply outside the mapped scope boundary."
    if section == "method_limits":
        return "The mapped methodological limitation no longer applied to the evidence."
    if anchor:
        return "This mapped distinction no longer applied."
    return "A stronger source changed the mapped distinction."


def _requirement_dict(req: RewriteRequirement) -> dict[str, Any]:
    return {
        "requirement_id": req.requirement_id,
        "loss_id": req.loss_id,
        "loss_type": req.loss_type,
        "instruction": req.instruction,
        "claim_ids": list(req.claim_ids),
        "relation_ids": list(req.relation_ids),
        "source_refs": list(req.source_refs),
        "claim_anchors": list(req.claim_anchors),
        "relation_anchors": list(req.relation_anchors),
        "required_phrases": list(req.required_phrases),
        "required_terms": list(req.required_terms),
        "claim_roles": list(req.claim_roles),
        "relation_types": list(req.relation_types),
        "relation_rationales": list(req.relation_rationales),
        "reader_anchors": list(req.reader_anchors),
    }


def _requirements_markdown(requirements: tuple[RewriteRequirement, ...]) -> str:
    lines = ["# Validated Rewrite Requirements", "", "Status: `generated`", ""]
    for req in requirements:
        lines.extend(
            [
                f"## {req.requirement_id}: {req.loss_id}",
                "",
                req.instruction,
                "",
                f"- Claims: `{', '.join(req.claim_ids)}`",
                f"- Relations: `{', '.join(req.relation_ids)}`",
                f"- Source refs: `{', '.join(req.source_refs)}`",
                f"- Claim roles: `{', '.join(req.claim_roles)}`",
                f"- Relation types: `{', '.join(req.relation_types)}`",
                "- Claim anchors:",
                *[f"  - {anchor}" for anchor in req.claim_anchors],
                "- Relation anchors:",
                *[f"  - {anchor}" for anchor in req.relation_anchors],
                "- Reader anchors:",
                *[f"  - {anchor}" for anchor in req.reader_anchors],
                "- Directional/boundary phrases:",
                *[f"  - {phrase}" for phrase in req.required_phrases],
                f"- Coverage terms: `{', '.join(req.required_terms)}`",
                "",
            ]
        )
    return "\n".join(lines)


def _single_loss_judgment_prompt(region: WorkedRegion, loss: Loss, map_only: str, stress_assisted: str) -> str:
    loss_payload = {
        "loss_id": loss.loss_id,
        "loss_type": loss.loss_type,
        "lost_item": loss.lost_item,
        "flat_baseline_omission": loss.flat_baseline_omission,
        "case_map_preserves": loss.case_map_preserves,
    }
    return "\n\n".join(
        (
            "You are evaluating whether a synthesis preserves known decision-space losses.",
            f"Region: {region.region_id}",
            "Compare Synthesis A and Synthesis B against exactly one loss. Return valid JSON only.",
            "Do not reward length. Reward the synthesis that makes the loss more inspectable for a thoughtful reader.",
            "Allowed winner values: A, B, tie, neither.",
            "Required JSON shape: {\"loss_id\": \"...\", \"winner\": \"A|B|tie|neither\", \"a_coverage\": \"none|partial|clear\", \"b_coverage\": \"none|partial|clear\", \"reason\": \"...\"}",
            "Loss:\n" + json.dumps(loss_payload, indent=2),
            "Synthesis A (map-only rewrite):\n" + map_only,
            "Synthesis B (stress-assisted rewrite):\n" + stress_assisted,
        )
    )


def _repair_synthesis_prompt(
    region: WorkedRegion,
    synthesis: str,
    coverage: dict[str, Any],
    requirements: tuple[RewriteRequirement, ...],
) -> str:
    requirement_lookup = {req.requirement_id: req for req in requirements}
    failed_rows = [
        row
        for row in coverage.get("requirements", [])
        if isinstance(row, dict) and row.get("status") != "clear"
    ]
    failed_blocks = []
    failed_requirements = []
    for row in failed_rows:
        req = requirement_lookup.get(row.get("requirement_id"))
        if req is None:
            continue
        failed_requirements.append(req)
        missing_phrases = [
            phrase
            for phrase in req.required_phrases
            if phrase not in row.get("phrase_hits", [])
        ]
        missing_terms = [
            term
            for term in req.required_terms[:10]
            if term not in row.get("term_hits", [])
        ]
        failed_blocks.append(
            "\n".join(
                (
                    f"- {req.requirement_id} / {req.loss_id}: {req.instruction}",
                    "  Claim anchors: " + (" | ".join(req.claim_anchors) or "none"),
                    "  Relation anchors: " + (" | ".join(req.relation_anchors) or "none"),
                    "  Reader anchors: " + (" | ".join(req.reader_anchors) or "none"),
                    "  Claim roles: " + (", ".join(req.claim_roles) or "none"),
                    "  Relation types: " + (", ".join(req.relation_types) or "none"),
                    "  Missing directional/boundary phrases: " + (" | ".join(missing_phrases) or "none"),
                    "  Missing coverage terms: " + (", ".join(missing_terms) or "none"),
                )
            )
        )
    return "\n\n".join(
        (
            "You are repairing a decision-support packet that failed deterministic map-coverage checks.",
            f"Region: {region.region_id}",
            "Return valid JSON only.",
            "Required JSON shape: "
            "{\"decision_brief\": \"readable repaired bottom-line prose\", "
            "\"confidence\": \"low|medium|high\", "
            "\"decision_implications\": [\"action-relevant implication\"], "
            "\"top_cruxes\": [{\"crux\": \"...\", \"why_it_matters\": \"...\", \"current_read\": \"...\", \"would_change_if\": \"...\"}], "
            "\"evidence_roles\": {\"main_support\": [\"...\"], \"conflicting_evidence\": [\"...\"], \"scope_limits\": [\"...\"], \"method_limits\": [\"...\"]}, "
            "\"stress_caveats\": [\"decision-relevant caveat\"], "
            "\"audit_trail\": [\"map-backed distinction or source-role boundary\"]}",
            "Repair rules:",
            "- Preserve the existing readable decision brief where it is correct, but do not bury checklist residue in it.",
            "- Correct any reversed directional distinction.",
            "- Add missing mapped distinctions below to `audit_trail`, unless they are decision-changing cruxes.",
            "- Put decision-changing missing distinctions in `top_cruxes` with why they matter and what would change the decision.",
            "- Do not put bare claim IDs or relation IDs in reader-facing fields; write the actual distinction in words.",
            "- Use exact directional/boundary phrases when supplied, unless grammar requires a minimal surrounding phrase.",
            "- Do not add facts beyond the mapped claim and relation anchors.",
            "Failed requirements:\n" + ("\n\n".join(failed_blocks) or "none"),
            "Deterministic repair scaffold:\n" + _packet_scaffold_prompt_block(tuple(failed_requirements)),
            "Current synthesis:\n" + synthesis,
        )
    )


def _deterministic_patch_synthesis(
    synthesis: str,
    coverage: dict[str, Any],
    requirements: tuple[RewriteRequirement, ...],
) -> str:
    requirement_lookup = {req.requirement_id: req for req in requirements}
    slot_lookup = {slot.requirement_id: slot for slot in _packet_slots_for_requirements(requirements)}
    patched = synthesis
    for req in requirements:
        for phrase in req.required_phrases:
            patched = _replace_obvious_reversal(patched, phrase)
    coverage = _deterministic_requirement_coverage(patched, requirements)
    additions = []
    for row in coverage.get("requirements", []):
        if not isinstance(row, dict) or row.get("status") == "clear":
            continue
        req = requirement_lookup.get(row.get("requirement_id"))
        if req is None:
            continue
        slot = slot_lookup.get(req.requirement_id) or _audit_slot_for_requirement(req)
        missing_phrases = [
            phrase
            for phrase in req.required_phrases
            if phrase not in row.get("phrase_hits", [])
        ]
        slot_text = slot.text
        safe_missing_phrases = [phrase for phrase in missing_phrases if not _is_meta_loss_text(phrase)]
        if safe_missing_phrases and not any(
            _normalize_for_coverage(phrase) in _normalize_for_coverage(slot_text)
            for phrase in safe_missing_phrases
        ):
            slot_text = safe_missing_phrases[0]
        if slot_text:
            additions.append(f"{req.loss_id}: {slot_text}.")
    if not additions:
        return _ensure_sectioned_packet(patched)
    return _add_mapped_distinctions_section(patched, additions)


def _ensure_sectioned_packet(text: str) -> str:
    if "## Decision Brief" in text and "## Audit Trail" in text:
        return text
    return "\n".join(
        [
            "## Decision Brief",
            "",
            text.strip(),
            "",
            "**Confidence:** Not specified",
            "",
            "## Decision Implications",
            "",
            "- No decision implications returned.",
            "",
            "## What Could Change the Decision",
            "",
            "| Crux | Why it matters | Current read | Would change if |",
            "|---|---|---|---|",
            "| No crux returned | No crux explanation returned. | No current read returned. | No change condition returned. |",
            "",
            "## Evidence Roles",
            "",
            "### Main Support",
            "",
            "- No main support returned.",
            "",
            "### Conflicting Evidence",
            "",
            "- No conflicting evidence returned.",
            "",
            "### Scope Limits",
            "",
            "- No scope limits returned.",
            "",
            "### Method Limits",
            "",
            "- No method limits returned.",
            "",
            "## Decision-Relevant Caveats",
            "",
            "- No stress caveats returned.",
            "",
            "## Audit Trail",
            "",
            "- No additional deterministic mapped-distinction patch required.",
            "",
        ]
    )


def _add_mapped_distinctions_section(text: str, additions: list[str]) -> str:
    unique_additions = [item for index, item in enumerate(additions) if item and item not in additions[:index]]
    if "## Audit Trail" not in text:
        lines = [
            "## Decision Brief",
            "",
            text.strip(),
            "",
            "**Confidence:** Not specified",
            "",
            "## Audit Trail",
            "",
        ]
        lines.extend(f"- {item}" for item in unique_additions)
        return "\n".join(lines)
    lines = text.rstrip().splitlines()
    output = []
    inserted = False
    for line in lines:
        if line.startswith("## Audit Trail") and not inserted:
            output.append(line)
            output.append("")
            output.extend(f"- {item}" for item in unique_additions)
            inserted = True
            continue
        output.append(line)
    if not inserted:
        output.extend(["", "## Audit Trail", "", *[f"- {item}" for item in unique_additions]])
    return "\n".join(output).rstrip() + "\n"


def _replace_obvious_reversal(text: str, required_phrase: str) -> str:
    match = re.search(
        r"(?P<x>[A-Z][A-Za-z0-9\-]+(?: [A-Za-z0-9\-]+){0,4}) may be (?P<property>slower(?: and more trappable)?) than (?P<y>[A-Za-z0-9\-]+(?: [A-Za-z0-9\-]+){0,4})",
        required_phrase,
    )
    if not match:
        return text
    x = match.group("x").strip()
    y = match.group("y").strip()
    prop = match.group("property").strip()
    reversed_phrase = f"{y} may be {prop} than {x}"
    if reversed_phrase in text and required_phrase not in text:
        return text.replace(reversed_phrase, required_phrase)
    return text


def _normalize_loss_judgment(loss_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if "loss_judgments" in payload and isinstance(payload["loss_judgments"], list) and payload["loss_judgments"]:
        payload = payload["loss_judgments"][0] if isinstance(payload["loss_judgments"][0], dict) else {}
    row = {
        "loss_id": payload.get("loss_id") if isinstance(payload.get("loss_id"), str) else loss_id,
        "winner": payload.get("winner") if payload.get("winner") in {"A", "B", "tie", "neither"} else "invalid",
        "a_coverage": payload.get("a_coverage") if payload.get("a_coverage") in {"none", "partial", "clear"} else "invalid",
        "b_coverage": payload.get("b_coverage") if payload.get("b_coverage") in {"none", "partial", "clear"} else "invalid",
        "reason": payload.get("reason") if isinstance(payload.get("reason"), str) else "",
    }
    row["consistency_error"] = _judgment_consistency_error(row)
    return row


def _judgment_consistency_error(row: dict[str, Any]) -> str | None:
    winner = row["winner"]
    a_rank = _coverage_rank(row["a_coverage"])
    b_rank = _coverage_rank(row["b_coverage"])
    if winner == "invalid" or a_rank < 0 or b_rank < 0:
        return "invalid_enum"
    if winner == "A" and a_rank <= b_rank:
        return "winner_A_not_better_than_B"
    if winner == "B" and b_rank <= a_rank:
        return "winner_B_not_better_than_A"
    if winner == "tie" and a_rank != b_rank:
        return "tie_with_unequal_coverage"
    if winner == "neither" and (a_rank > 0 or b_rank > 0):
        return "neither_with_positive_coverage"
    return None


def _coverage_rank(value: str) -> int:
    return {"none": 0, "partial": 1, "clear": 2}.get(value, -1)


def _overall_from_loss_judgments(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in judgments if not row.get("parse_error") and not row.get("consistency_error")]
    winners = [row.get("winner") for row in valid]
    counts = {winner: winners.count(winner) for winner in ("A", "B", "tie", "neither")}
    if counts["B"] > counts["A"]:
        winner = "B"
    elif counts["A"] > counts["B"]:
        winner = "A"
    elif valid:
        winner = "tie"
    else:
        winner = "neither"
    return {"winner": winner, "counts": counts, "valid_judgments": len(valid), "total_judgments": len(judgments)}


def _region_summary(losses: list[Loss], judgment: dict[str, Any]) -> dict[str, Any]:
    known_loss_ids = {loss.loss_id for loss in losses}
    rows = judgment.get("loss_judgments", [])
    if not isinstance(rows, list):
        rows = []
    valid_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("loss_id") in known_loss_ids
        and not row.get("parse_error")
        and not row.get("consistency_error")
    ]
    winners = [row.get("winner") for row in valid_rows]
    invalid_rows = [row for row in rows if isinstance(row, dict) and row not in valid_rows]
    return {
        "stress_wins": winners.count("B"),
        "map_only_wins": winners.count("A"),
        "ties": winners.count("tie"),
        "neither": winners.count("neither"),
        "valid_judgments": len(valid_rows),
        "invalid_judgments": max(0, len(losses) - len(valid_rows)),
        "invalid_reasons": _invalid_reasons(invalid_rows),
        "overall_winner": (judgment.get("overall") or {}).get("winner") if isinstance(judgment.get("overall"), dict) else None,
    }


def _invalid_reasons(rows: list[dict[str, Any]]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for row in rows:
        reason = row.get("parse_error") or row.get("consistency_error") or "missing_or_unknown_loss_id"
        reasons[reason] = reasons.get(reason, 0) + 1
    return reasons


def _aggregate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "region_count": len(rows),
        "loss_count": sum(row["loss_count"] for row in rows),
        "stress_wins": sum(row["summary"]["stress_wins"] for row in rows),
        "map_only_wins": sum(row["summary"]["map_only_wins"] for row in rows),
        "ties": sum(row["summary"]["ties"] for row in rows),
        "neither": sum(row["summary"]["neither"] for row in rows),
        "invalid_judgments": sum(row["summary"]["invalid_judgments"] for row in rows),
    }


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Synthesis Uplift Eval",
        "",
        f"Schema: `{report['schema_id']}`",
        f"Backend: `{report['backend']}`",
        f"Judge backend: `{report['judge_backend']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Regions", ""])
    for row in report["regions"]:
        lines.append(f"### {row['region_id']}")
        lines.append("")
        for key, value in row["summary"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append(f"- stress report: `{row['paths']['stress_report']}`")
        lines.append(f"- rewrite requirements: `{row['paths']['rewrite_requirements']}`")
        lines.append(f"- deterministic coverage: `{row['paths']['deterministic_requirement_coverage']}`")
        lines.append(f"- map-only synthesis: `{row['paths']['map_only_synthesis']}`")
        lines.append(f"- stress-assisted synthesis: `{row['paths']['stress_assisted_synthesis']}`")
        lines.append(f"- judgment: `{row['paths']['judgment']}`")
        lines.append("")
    return "\n".join(lines)


def _run_text_backend(prompt: str, backend: str, timeout_seconds: int, max_retries: int) -> str:
    result = run_model_backend(prompt, backend, timeout_seconds=timeout_seconds, max_retries=max_retries)
    return result.text.strip()


def _run_synthesis_backend(
    prompt: str,
    backend: str,
    timeout_seconds: int,
    max_retries: int,
    map_payload: dict[str, Any] | None = None,
    requirements: tuple[RewriteRequirement, ...] = (),
) -> str:
    raw = _run_text_backend(prompt, backend, timeout_seconds, max_retries)
    payload = _parse_json(raw)
    if isinstance(payload, dict) and (
        isinstance(payload.get("decision_brief"), str) or isinstance(payload.get("synthesis"), str)
    ):
        return _render_synthesis_packet(payload, map_payload=map_payload, requirements=requirements)
    if _looks_like_structured_packet_attempt(raw):
        return _render_unparsed_structured_packet(raw)
    return raw


def _render_synthesis_packet(
    payload: dict[str, Any],
    map_payload: dict[str, Any] | None = None,
    requirements: tuple[RewriteRequirement, ...] = (),
) -> str:
    anchor_lookup = _anchor_text_lookup(map_payload or {})
    decision_brief = _as_text(payload.get("decision_brief") or payload.get("synthesis"))
    confidence = _confidence_label(payload.get("confidence"))
    implications = _expand_map_ids(_string_list(payload.get("decision_implications")), anchor_lookup)
    cruxes = _crux_list(payload.get("top_cruxes"), anchor_lookup)
    evidence_roles = _evidence_roles(payload.get("evidence_roles"), anchor_lookup)
    _backfill_evidence_roles(evidence_roles, requirements)
    _dedupe_evidence_roles(evidence_roles)
    audit = _expand_map_ids(
        _string_list(payload.get("audit_trail")) or _string_list(payload.get("mapped_distinctions")),
        anchor_lookup,
    )
    audit = _audit_items(audit, requirements)
    caveats = _expand_map_ids(_string_list(payload.get("stress_caveats")), anchor_lookup)
    if not any((implications, cruxes, any(evidence_roles.values()), audit, caveats)):
        return decision_brief
    lines = [
        "## Decision Brief",
        "",
        decision_brief or "No decision brief returned.",
        "",
        f"**Confidence:** {confidence}",
        "",
        "## Decision Implications",
        "",
    ]
    if implications:
        lines.extend(f"- {item}" for item in implications)
    else:
        lines.append("- No decision implications returned.")
    lines.extend(
        [
            "",
            "## What Could Change the Decision",
            "",
            "| Crux | Why it matters | Current read | Would change if |",
            "|---|---|---|---|",
        ]
    )
    if cruxes:
        lines.extend(
            "| "
            + " | ".join(
                _table_cell(crux[key])
                for key in ("crux", "why_it_matters", "current_read", "would_change_if")
            )
            + " |"
            for crux in cruxes
        )
    else:
        lines.append(
            "| No crux returned | No crux explanation returned. | No current read returned. | No change condition returned. |"
        )
    lines.extend(["", "## Evidence Roles", ""])
    role_labels = (
        ("main_support", "Main Support"),
        ("conflicting_evidence", "Conflicting Evidence"),
        ("scope_limits", "Scope Limits"),
        ("method_limits", "Method Limits"),
    )
    for role_key, role_label in role_labels:
        lines.extend([f"### {role_label}", ""])
        role_items = evidence_roles[role_key]
        if role_items:
            lines.extend(f"- {item}" for item in role_items)
        else:
            lines.append(f"- No {role_label.lower()} returned.")
        lines.append("")
    lines.extend(["## Decision-Relevant Caveats", ""])
    if caveats:
        lines.extend(f"- {item}" for item in caveats)
    else:
        lines.append("- No stress caveats returned.")
    lines.extend(["", "## Audit Trail", ""])
    if audit:
        lines.extend(f"- {item}" for item in audit)
    else:
        lines.append("- No audit trail returned.")
    lines.append("")
    return "\n".join(lines)


def _looks_like_structured_packet_attempt(text: str) -> bool:
    stripped = text.strip()
    return (
        stripped.startswith("```json")
        or stripped.startswith("{")
        or '"decision_brief"' in stripped[:500]
        or '"evidence_roles"' in stripped[:1500]
    )


def _render_unparsed_structured_packet(text: str) -> str:
    brief = _extract_json_string_field(text, "decision_brief")
    confidence = _extract_json_string_field(text, "confidence") or "Not specified"
    return "\n".join(
        [
            "## Decision Brief",
            "",
            brief or "The model returned an incomplete structured packet, so this section needs regeneration.",
            "",
            f"**Confidence:** {_confidence_label(confidence)}",
            "",
            "## Decision Implications",
            "",
            "- Structured output was incomplete before decision implications could be parsed.",
            "",
            "## What Could Change the Decision",
            "",
            "| Crux | Why it matters | Current read | Would change if |",
            "|---|---|---|---|",
            "| Structured output incomplete | The model response could not be parsed as a complete packet. | Deterministic coverage repair will preserve required map distinctions below. | Regenerate with a larger output budget or a stricter shorter schema. |",
            "",
            "## Evidence Roles",
            "",
            "### Main Support",
            "",
            "- Structured output was incomplete before evidence roles could be parsed.",
            "",
            "### Conflicting Evidence",
            "",
            "- Structured output was incomplete before conflicting evidence could be parsed.",
            "",
            "### Scope Limits",
            "",
            "- Structured output was incomplete before scope limits could be parsed.",
            "",
            "### Method Limits",
            "",
            "- Structured output was incomplete before method limits could be parsed.",
            "",
            "## Decision-Relevant Caveats",
            "",
            "- Structured output was incomplete before caveats could be parsed.",
            "",
            "## Audit Trail",
            "",
            "- The model returned a truncated or invalid structured packet; deterministic repair should add required map-backed distinctions.",
            "",
        ]
    )


def _confidence_label(value: Any) -> str:
    if not isinstance(value, str):
        return "Not specified"
    normalized = value.strip().lower()
    return normalized if normalized in {"low", "medium", "high"} else value.strip() or "Not specified"


def _crux_list(value: Any, anchor_lookup: dict[str, str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        row = {
            "crux": _clean_reader_text(_expand_map_id_text(_as_text(item.get("crux")), anchor_lookup)),
            "why_it_matters": _clean_reader_text(_expand_map_id_text(_as_text(item.get("why_it_matters")), anchor_lookup)),
            "current_read": _clean_reader_text(_expand_map_id_text(_as_text(item.get("current_read")), anchor_lookup)),
            "would_change_if": _clean_reader_text(_expand_map_id_text(_as_text(item.get("would_change_if")), anchor_lookup)),
        }
        if any(row.values()):
            rows.append(row)
    return rows


def _evidence_roles(value: Any, anchor_lookup: dict[str, str]) -> dict[str, list[str]]:
    roles = {
        "main_support": [],
        "conflicting_evidence": [],
        "scope_limits": [],
        "method_limits": [],
    }
    if not isinstance(value, dict):
        return roles
    for key in roles:
        roles[key] = _expand_map_ids(_string_list(value.get(key)), anchor_lookup)
    return roles


def _backfill_evidence_roles(
    roles: dict[str, list[str]],
    requirements: tuple[RewriteRequirement, ...],
) -> None:
    for slot in _packet_slots_for_requirements(requirements):
        if _similar_item_exists(roles[slot.section], slot.text):
            continue
        if slot.text not in roles[slot.section]:
            roles[slot.section].append(slot.text)


def _dedupe_evidence_roles(roles: dict[str, list[str]]) -> None:
    seen: set[str] = set()
    for key in ("main_support", "conflicting_evidence", "scope_limits", "method_limits"):
        unique = []
        for item in roles[key]:
            normalized = _dedupe_key(item)
            if not normalized or normalized in seen or _similar_item_exists(unique, item):
                continue
            seen.add(normalized)
            unique.append(item)
        roles[key] = unique


def _dedupe_key(text: str) -> str:
    normalized = _normalize_for_coverage(text)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return normalized.strip()


def _packet_slots_for_requirements(requirements: tuple[RewriteRequirement, ...]) -> tuple[PacketSlot, ...]:
    slots = [_slot_for_requirement(req) for req in requirements]
    return _dedupe_slots(slot for slot in slots if slot.text)


def _slot_for_requirement(req: RewriteRequirement) -> PacketSlot:
    return PacketSlot(
        section=_slot_section_for_requirement(req),
        text=_slot_text_for_requirement(req),
        requirement_id=req.requirement_id,
        loss_id=req.loss_id,
    )


def _audit_slot_for_requirement(req: RewriteRequirement) -> PacketSlot:
    anchor = _first_reader_anchor(req) or _fallback_slot_text(req)
    if not anchor:
        return PacketSlot("audit_trail", "", req.requirement_id, req.loss_id)
    return PacketSlot(
        section="audit_trail",
        text=anchor,
        requirement_id=req.requirement_id,
        loss_id=req.loss_id,
    )


def _slot_text_for_requirement(req: RewriteRequirement) -> str:
    candidates = [
        *req.relation_rationales,
        *req.reader_anchors,
        *[_reader_relation_anchor_text(anchor) for anchor in req.relation_anchors],
        *[_reader_anchor_text(anchor) for anchor in req.claim_anchors],
        *req.required_phrases,
    ]
    for candidate in candidates:
        cleaned = _clean_reader_text(candidate)
        if cleaned and not _is_meta_loss_text(cleaned):
            return cleaned
    return _fallback_slot_text(req)


def _first_reader_anchor(req: RewriteRequirement) -> str:
    for candidate in (*req.relation_rationales, *req.reader_anchors):
        cleaned = _clean_reader_text(candidate)
        if cleaned and not _is_meta_loss_text(cleaned):
            return cleaned
    return ""


def _fallback_slot_text(req: RewriteRequirement) -> str:
    evidence_terms = [term for term in req.required_terms if term not in {"baseline", "flat", "loss", "preserve"}]
    if evidence_terms:
        return "Evidence distinction to preserve: " + ", ".join(evidence_terms[:6]) + "."
    return ""


def _slot_section_for_requirement(req: RewriteRequirement) -> str:
    return (
        _role_section_from_relation_types(req.relation_types)
        or _role_section_from_claim_roles(req.claim_roles)
        or _role_section_from_loss_type(req.loss_type)
        or "main_support"
    )


def _role_section_from_relation_types(relation_types: tuple[str, ...]) -> str:
    text = _normalize_for_coverage(" ".join(relation_types))
    if any(marker in text for marker in ("tension", "conflict", "contradict", "challenge", "rebuts", "opposes")):
        return "conflicting_evidence"
    if any(marker in text for marker in ("limits", "bounds", "conditional", "scope", "exception", "qualifies")):
        return "scope_limits"
    if any(marker in text for marker in ("method", "measures", "proxy", "endpoint", "operationalizes")):
        return "method_limits"
    if any(marker in text for marker in ("supports", "entails", "grounds", "backs")):
        return "main_support"
    return ""


def _role_section_from_claim_roles(claim_roles: tuple[str, ...]) -> str:
    text = _normalize_for_coverage(" ".join(claim_roles))
    if any(marker in text for marker in ("conflict", "counter", "tension", "challenge", "opposing")):
        return "conflicting_evidence"
    if any(marker in text for marker in ("method", "measurement", "endpoint", "quality", "design", "validity", "proxy")):
        return "method_limits"
    if any(marker in text for marker in ("scope", "boundary", "subgroup", "population", "caveat", "limit")):
        return "scope_limits"
    if any(marker in text for marker in ("support", "premise", "finding", "evidence")):
        return "main_support"
    return ""


def _role_section_from_loss_type(loss_type: str) -> str:
    text = _normalize_for_coverage(loss_type)
    if any(marker in text for marker in ("conflict", "tension", "challenge", "critique", "response", "inconsistent")):
        return "conflicting_evidence"
    if any(marker in text for marker in ("scope", "population", "replacement", "regional", "caveat")):
        return "scope_limits"
    if any(marker in text for marker in ("method", "endpoint", "guideline", "authority", "scoping", "systematic", "study design")):
        return "method_limits"
    return ""


def _dedupe_slots(slots: Any) -> tuple[PacketSlot, ...]:
    unique = []
    seen: set[tuple[str, str]] = set()
    for slot in slots:
        key = (slot.section, _dedupe_key(slot.text))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        unique.append(slot)
    return tuple(unique)


def _audit_items(model_items: list[str], requirements: tuple[RewriteRequirement, ...]) -> list[str]:
    items = [_clean_reader_text(item) for item in model_items]
    items = [item for item in items if item and not _is_meta_loss_text(item)]
    for req in requirements:
        slot = _audit_slot_for_requirement(req)
        if slot.text:
            items.append(f"{req.loss_id}: {slot.text}")
    return _dedupe_text_items(items)


def _dedupe_text_items(items: list[str]) -> list[str]:
    unique = []
    seen: set[str] = set()
    for item in items:
        key = _dedupe_key(item)
        if not key or key in seen or _similar_item_exists(unique, item):
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _similar_item_exists(existing_items: list[str], candidate: str) -> bool:
    return any(_text_overlap_ratio(existing, candidate) >= 0.58 for existing in existing_items)


def _text_overlap_ratio(left: str, right: str) -> float:
    left_tokens = _content_token_set(left)
    right_tokens = _content_token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    smaller = min(len(left_tokens), len(right_tokens))
    if smaller < 4:
        return 0.0
    return len(left_tokens & right_tokens) / smaller


def _content_token_set(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "alone",
        "also",
        "because",
        "being",
        "between",
        "could",
        "from",
        "have",
        "into",
        "more",
        "one",
        "rather",
        "should",
        "than",
        "that",
        "the",
        "their",
        "these",
        "this",
        "using",
        "when",
        "where",
        "which",
        "while",
        "with",
        "without",
    }
    return {
        _content_token(token)
        for token in re.findall(r"[a-z][a-z0-9\-]{2,}", _normalize_for_coverage(text))
        if token not in stopwords
    }


def _content_token(token: str) -> str:
    if token.endswith("ss"):
        return token
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("sses"):
        return token[:-2]
    if len(token) > 5 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _strip_anchor_id(text: str) -> str:
    return re.sub(r"^[A-Za-z0-9_\-]+:\s*", "", text).strip()


def _reader_anchor_text(text: str) -> str:
    return _clean_required_phrase(_strip_anchor_id(text)) or _strip_anchor_id(text)


def _reader_relation_anchor_text(text: str) -> str:
    without_id = _strip_anchor_id(text)
    parts = [part.strip() for part in without_id.split(";") if part.strip()]
    if len(parts) >= 3:
        return parts[-1]
    return _reader_anchor_text(text)


def _is_meta_loss_text(text: str) -> bool:
    normalized = _normalize_for_coverage(text)
    meta_markers = (
        "the flat baseline",
        "flat baseline",
        "the baseline",
        "baseline failure",
        "explicitly avoid",
        "preserve the",
        "distinction from",
        "lost item",
    )
    return any(marker in normalized for marker in meta_markers)


def _evidence_role_for_requirement(req: RewriteRequirement) -> str:
    return _slot_section_for_requirement(req)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "\\|").strip() or "Not specified"


def _anchor_text_lookup(map_payload: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    claims = _claim_lookup(map_payload)
    for claim_id, claim in claims.items():
        statement = _reader_claim_statement(claim)
        if statement:
            lookup[claim_id] = statement
    for relation_id, relation in _relation_lookup(map_payload).items():
        statement = _reader_relation_statement(relation, lookup)
        if statement:
            lookup[relation_id] = statement
    return lookup


def _reader_claim_statement(claim: dict[str, Any]) -> str:
    return _as_text(claim.get("claim") or claim.get("text"))


def _reader_relation_statement(relation: dict[str, Any], claim_lookup: dict[str, str]) -> str:
    source_claim = _as_text(relation.get("source_claim") or relation.get("source_claim_id"))
    target_claim = _as_text(relation.get("target_claim") or relation.get("target_claim_id"))
    source_text = claim_lookup.get(source_claim, "unresolved source claim" if source_claim else "")
    target_text = claim_lookup.get(target_claim, "unresolved target claim" if target_claim else "")
    relation_type = _as_text(relation.get("relation_type"))
    rationale = _as_text(relation.get("rationale"))
    if rationale:
        return rationale
    edge = ""
    if source_text and target_text:
        edge = f"{_short_text(source_text, 120)} -> {_short_text(target_text, 120)}"
    elif source_text:
        edge = _short_text(source_text, 120)
    elif target_text:
        edge = _short_text(target_text, 120)
    if rationale and edge:
        relation_label = f"{relation_type} relation" if relation_type else "relation"
        return _short_text(f"{rationale} ({relation_label}: {edge})", 360)
    return _short_text("; ".join(part for part in (edge, relation_type, rationale) if part), 360)


def _short_text(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _expand_map_ids(items: list[str], anchor_lookup: dict[str, str]) -> list[str]:
    return [_clean_reader_text(_expand_map_id_text(item, anchor_lookup)) for item in items]


def _expand_map_id_text(text: str, anchor_lookup: dict[str, str]) -> str:
    stripped = text.strip("` ")
    if stripped in anchor_lookup:
        return anchor_lookup[stripped]
    return re.sub(
        r"`?([A-Za-z0-9_\-]+_[cr]\d+)`?",
        lambda match: anchor_lookup.get(match.group(1), match.group(0)),
        text,
    )


def _clean_reader_text(text: str) -> str:
    cleaned = re.sub(r";?\s*role=[^;.\n]+", "", text)
    cleaned = re.sub(r";?\s*source=[^;.\n]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" ;")


def _clean_reader_packet_metadata(text: str) -> str:
    cleaned = re.sub(r";?\s*role=[^;.\n]+", "", text)
    cleaned = re.sub(r";?\s*source=[^;.\n]+", "", cleaned)
    return _dedupe_packet_bullets(cleaned)


def _dedupe_packet_bullets(text: str) -> str:
    seen: set[str] = set()
    lines = []
    for line in text.splitlines():
        bullet = re.match(r"^(\s*-\s+)(.+?)\s*$", line)
        if bullet:
            key = _dedupe_key(bullet.group(2))
            if key and key in seen:
                continue
            if key:
                seen.add(key)
        lines.append(line)
    return "\n".join(lines).rstrip() + ("\n" if text.endswith("\n") else "")


def _parse_json(text: str) -> dict[str, Any] | None:
    canonical = canonical_json_output(text)
    try:
        payload = json.loads(canonical)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_json_string_field(text: str, field: str) -> str:
    pattern = re.compile(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', re.DOTALL)
    match = pattern.search(text)
    if not match:
        return ""
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return re.sub(r"\s+", " ", match.group(1)).strip()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_map_payload(repo_root: Path, region: WorkedRegion) -> dict[str, Any]:
    json_path = repo_root / region.output_json_path
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    map_path = repo_root / region.map_path
    if map_path.suffix.lower() == ".json":
        return json.loads(map_path.read_text(encoding="utf-8"))
    raise ValueError(f"region has no JSON map export region={region.region_id} path={region.output_json_path}")


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_for_coverage(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("‑", "-").replace("–", "-")).strip()


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
