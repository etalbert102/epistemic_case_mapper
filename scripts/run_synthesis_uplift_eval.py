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

    map_only = _run_synthesis_backend(map_only_prompt, backend, timeout_seconds, max_retries)
    stress_assisted = _run_synthesis_backend(stress_prompt, backend, timeout_seconds, max_retries)
    initial_stress_coverage = _deterministic_requirement_coverage(stress_assisted, requirements)
    if _needs_repair(initial_stress_coverage):
        write_markdown(output_dir / "stress_assisted_initial_synthesis.md", stress_assisted)
        repair_prompt = _repair_synthesis_prompt(region, stress_assisted, initial_stress_coverage, requirements)
        write_markdown(output_dir / "stress_assisted_repair_prompt.txt", repair_prompt)
        stress_assisted = _run_synthesis_backend(repair_prompt, backend, timeout_seconds, max_retries)
        repaired_coverage = _deterministic_requirement_coverage(stress_assisted, requirements)
        if _needs_repair(repaired_coverage):
            write_markdown(output_dir / "stress_assisted_repaired_before_patch.md", stress_assisted)
            stress_assisted = _deterministic_patch_synthesis(stress_assisted, repaired_coverage, requirements)
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
    if requirements:
        requirement_brief = _requirements_prompt_block(requirements)
    return "\n\n".join(
        (
            "You are revising a flat synthesis so it better preserves the decision space.",
            f"Region: {region.region_id}",
            "Write a concise review packet for an informed reader. Return valid JSON only.",
            "Required JSON shape: {\"synthesis\": \"readable prose\", \"mapped_distinctions\": [\"map-backed distinction bullets\"], \"stress_caveats\": [\"stress caveat bullets\"]}",
            "Requirements:",
            "- Treat the validated rewrite requirements as the backbone of the synthesis.",
            "- Preserve the mapped claim and relation anchors before adding any stress finding.",
            "- Use stress findings only to add pressure, caveats, or uncertainty; do not let them replace map distinctions.",
            "- Preserve cruxes, caveats, source-role boundaries, and load-bearing relations.",
            "- Put readable prose in `synthesis`; put checklist-like material in `mapped_distinctions`, not in the prose.",
            "- Do not merely list claim IDs; make the prose readable.",
            "- Keep uncertainty visible and avoid adding facts beyond the provided artifacts.",
            "- Prefer explicit distinctions over fluent compression when the distinction changes interpretation.",
            "- If a stress finding conflicts with a mapped source-backed distinction, keep the mapped distinction and phrase the stress finding as a question or caveat.",
            "Known erosion-audit losses to avoid:\n" + loss_brief,
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
        term_source = " ".join((loss.loss_type, loss.lost_item, loss.flat_baseline_omission))
        for claim_id in claim_ids:
            claim = claims.get(claim_id)
            if claim is None:
                continue
            term_source += " " + _claim_text(claim)
            claim_anchors.append(f"{claim_id}: {_claim_statement(claim)}")
            source_id = _as_text(claim.get("source_id"))
            source_span = _as_text(claim.get("source_span"))
            if source_id:
                source_refs.append(f"{source_id} {source_span}".strip())
        for relation_id in relation_ids:
            relation = relation_lookup.get(relation_id)
            if relation is None:
                continue
            term_source += " " + _as_text(relation.get("relation_type")) + " " + _as_text(relation.get("rationale"))
            relation_anchors.append(f"{relation_id}: {_relation_statement(relation)}")
        for stress_terms in safe_stress_terms:
            if _loss_overlap(loss, stress_terms):
                term_source += " " + " ".join(stress_terms)
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
        phrase_hits = [phrase for phrase in req.required_phrases if _normalize_for_coverage(phrase) in text]
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
            )
        )
        lines.append(
            f"- {req.requirement_id} / {req.loss_id}: {req.instruction} "
            f"Anchors: {ids}. Source refs: {refs}. {anchors}. Coverage terms: {terms}."
            f" Directional phrases to preserve: {phrases}."
        )
    return "\n".join(lines)


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
                "- Claim anchors:",
                *[f"  - {anchor}" for anchor in req.claim_anchors],
                "- Relation anchors:",
                *[f"  - {anchor}" for anchor in req.relation_anchors],
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
    for row in failed_rows:
        req = requirement_lookup.get(row.get("requirement_id"))
        if req is None:
            continue
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
                    "  Missing directional/boundary phrases: " + (" | ".join(missing_phrases) or "none"),
                    "  Missing coverage terms: " + (", ".join(missing_terms) or "none"),
                )
            )
        )
    return "\n\n".join(
        (
            "You are repairing a review packet that failed deterministic map-coverage checks.",
            f"Region: {region.region_id}",
            "Return valid JSON only.",
            "Required JSON shape: {\"synthesis\": \"readable repaired prose\", \"mapped_distinctions\": [\"map-backed distinction bullets\"], \"stress_caveats\": [\"stress caveat bullets\"]}",
            "Repair rules:",
            "- Preserve the existing readable synthesis where it is correct, but do not bury checklist residue in it.",
            "- Correct any reversed directional distinction.",
            "- Add the missing mapped distinctions below to `mapped_distinctions` unless they can be integrated naturally into the prose.",
            "- Use exact directional/boundary phrases when supplied, unless grammar requires a minimal surrounding phrase.",
            "- Do not add facts beyond the mapped claim and relation anchors.",
            "Failed requirements:\n" + ("\n\n".join(failed_blocks) or "none"),
            "Current synthesis:\n" + synthesis,
        )
    )


def _deterministic_patch_synthesis(
    synthesis: str,
    coverage: dict[str, Any],
    requirements: tuple[RewriteRequirement, ...],
) -> str:
    requirement_lookup = {req.requirement_id: req for req in requirements}
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
        missing_phrases = [
            phrase
            for phrase in req.required_phrases
            if phrase not in row.get("phrase_hits", [])
        ]
        if missing_phrases:
            additions.append(f"{req.loss_id}: {missing_phrases[0]}.")
        else:
            additions.append(f"{req.loss_id}: {req.instruction}")
    if not additions:
        return _ensure_sectioned_packet(patched)
    return _add_mapped_distinctions_section(patched, additions)


def _ensure_sectioned_packet(text: str) -> str:
    if "## Readable Synthesis" in text and "## Mapped Distinctions Preserved" in text:
        return text
    return "\n".join(
        [
            "## Readable Synthesis",
            "",
            text.strip(),
            "",
            "## Mapped Distinctions Preserved",
            "",
            "- No additional deterministic mapped-distinction patch required.",
            "",
            "## Stress-Test Caveats",
            "",
            "- No stress caveats returned.",
            "",
        ]
    )


def _add_mapped_distinctions_section(text: str, additions: list[str]) -> str:
    unique_additions = [item for index, item in enumerate(additions) if item and item not in additions[:index]]
    if "## Mapped Distinctions Preserved" not in text:
        lines = ["## Readable Synthesis", "", text.strip(), "", "## Mapped Distinctions Preserved", ""]
        lines.extend(f"- {item}" for item in unique_additions)
        lines.extend(["", "## Stress-Test Caveats", "", "- No stress caveats returned.", ""])
        return "\n".join(lines)
    lines = text.rstrip().splitlines()
    output = []
    inserted = False
    for line in lines:
        if line.startswith("## Stress-Test Caveats") and not inserted:
            output.extend(f"- {item}" for item in unique_additions)
            output.append("")
            inserted = True
        output.append(line)
    if not inserted:
        output.extend(["", *[f"- {item}" for item in unique_additions]])
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


def _run_synthesis_backend(prompt: str, backend: str, timeout_seconds: int, max_retries: int) -> str:
    raw = _run_text_backend(prompt, backend, timeout_seconds, max_retries)
    payload = _parse_json(raw)
    if isinstance(payload, dict) and isinstance(payload.get("synthesis"), str):
        return _render_synthesis_packet(payload)
    return raw


def _render_synthesis_packet(payload: dict[str, Any]) -> str:
    synthesis = _as_text(payload.get("synthesis"))
    mapped = _string_list(payload.get("mapped_distinctions"))
    caveats = _string_list(payload.get("stress_caveats"))
    if not mapped and not caveats:
        return synthesis
    lines = ["## Readable Synthesis", "", synthesis or "No readable synthesis returned.", ""]
    lines.extend(["## Mapped Distinctions Preserved", ""])
    if mapped:
        lines.extend(f"- {item}" for item in mapped)
    else:
        lines.append("- No mapped distinctions returned.")
    lines.extend(["", "## Stress-Test Caveats", ""])
    if caveats:
        lines.extend(f"- {item}" for item in caveats)
    else:
        lines.append("- No stress caveats returned.")
    lines.append("")
    return "\n".join(lines)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _parse_json(text: str) -> dict[str, Any] | None:
    canonical = canonical_json_output(text)
    try:
        payload = json.loads(canonical)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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
