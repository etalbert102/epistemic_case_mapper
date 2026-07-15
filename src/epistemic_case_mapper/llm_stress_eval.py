from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output
from epistemic_case_mapper.prompt_templates import examples_block, json_schema_block, render_prompt, xml_block
from epistemic_case_mapper.submission_manifest import WorkedRegion, load_submission_manifest


EVAL_VERSION = "llm_stress_eval_v1"

PROMPT_SPECS = (
    {
        "prompt_id": "insight_delta",
        "title": "Map-vs-baseline insight delta",
        "instruction": (
            "Compare the structured map with the flat baseline. Return only deltas where the map "
            "preserves a crux, caveat, source-boundary distinction, counterexample, relation, or "
            "uncertainty that the flat baseline blurs or omits."
        ),
        "schema": {
            "insight_deltas": [
                {
                    "delta_type": "crux|caveat|source_boundary|counterexample|relation|uncertainty",
                    "decision_consequence": "What a downstream investigator should inspect or believe differently.",
                    "map_claim_ids": ["known claim ids"],
                    "relation_ids": ["known relation ids, if any"],
                    "source_ids": ["known source ids"],
                    "baseline_excerpt": "Exact short baseline phrase being corrected or separated.",
                    "risk_if_wrong": "How this delta could mislead if overstated.",
                }
            ]
        },
    },
    {
        "prompt_id": "adversarial_critique",
        "title": "Adversarial source and rhetoric critique",
        "instruction": (
            "Red-team the map for unsupported confidence, rhetoric treated as evidence, missing "
            "caveats, asymmetric burden framing, and source-status confusion. Focus on stress signals rather than final adjudication "
            "truth. Identify boundary failures and fragile claims."
        ),
        "schema": {
            "critic_findings": [
                {
                    "finding_type": "unsupported_confidence|rhetoric_as_evidence|missing_caveat|source_status_confusion|overclaim",
                    "severity": "low|medium|high",
                    "threatened_claim_ids": ["known claim ids"],
                    "relation_ids": ["known relation ids, if any"],
                    "source_ids": ["known source ids"],
                    "reason": "Why this is a boundary or robustness risk.",
                    "repair_prompt": "Concrete next check the mapper should run.",
                }
            ]
        },
    },
    {
        "prompt_id": "relation_usefulness",
        "title": "Relation usefulness proxy",
        "instruction": (
            "Assess generated relations as review-routing objects. Separate schema validity from "
            "epistemic usefulness. Look for non-obvious, crux-relevant, unsupported, misleading, "
            "duplicate, and novel-but-unsettled relations."
        ),
        "schema": {
            "relation_assessments": [
                {
                    "relation_id": "known relation id",
                    "decision": "useful|shallow|misleading|unsupported|duplicate|crux_relevant|novel_but_unsettled",
                    "claim_ids": ["known endpoint claim ids"],
                    "source_ids": ["known source ids"],
                    "rationale": "Why the relation does or does not help a reviewer reason better.",
                    "next_review_action": "What to inspect next.",
                }
            ]
        },
    },
    {
        "prompt_id": "metamorphic_pressure",
        "title": "Metamorphic pressure-test design",
        "instruction": (
            "Design source-packet mutations that should change or preserve the map in predictable ways. "
            "Prefer tests that catch caveat loss, counterexample loss, loaded-language adoption, "
            "source-order sensitivity, and removed-source confidence failures."
        ),
        "schema": {
            "metamorphic_tests": [
                {
                    "test_type": "caveat_injection|counterexample_injection|loaded_language_injection|source_order_shuffle|source_removal",
                    "mutation": "Concrete mutation to the document packet.",
                    "expected_invariant": "What should stay stable, or how uncertainty should move.",
                    "linked_claim_ids": ["known claim ids affected"],
                    "source_ids": ["known source ids"],
                    "failure_signal": "What output behavior would reveal a product weakness.",
                }
            ]
        },
    },
)

BUILT_IN_METAMORPHIC_CHECKS = (
    {
        "test_type": "source_order_shuffle",
        "expected_invariant": "Source, claim, and relation identifiers should remain stable under source order changes.",
        "failure_signal": "Different conclusions appear only because source order changed.",
    },
    {
        "test_type": "caveat_injection",
        "expected_invariant": "A newly added source-backed caveat should increase uncertainty or add a scope-limit claim.",
        "failure_signal": "The map preserves the old conclusion without caveat or uncertainty movement.",
    },
    {
        "test_type": "counterexample_injection",
        "expected_invariant": "A source-backed counterexample should create or modify a crux, challenge, or open question.",
        "failure_signal": "The counterexample is summarized but does not affect any load-bearing claim or relation.",
    },
    {
        "test_type": "loaded_language_injection",
        "expected_invariant": "Persuasive wording should be represented as framing risk rather than adopted as evidence.",
        "failure_signal": "Loaded wording reappears as a settled source-supported conclusion.",
    },
    {
        "test_type": "source_removal",
        "expected_invariant": "Removing a load-bearing source should reduce support or mark affected claims fragile.",
        "failure_signal": "Confidence remains unchanged after cited evidence disappears.",
    },
)


@dataclass(frozen=True)
class LlmStressEvalResult:
    output_dir: Path
    json_path: Path
    markdown_path: Path
    prompt_count: int
    model_run_count: int
    finding_count: int
    reference_issue_count: int


def run_llm_stress_eval(
    repo_root: Path,
    manifest_path: str,
    region_id: str,
    backend: str,
    *,
    compare_backends: list[str] | None = None,
    output_dir: str | Path | None = None,
    baseline_path: str | Path | None = None,
    timeout_seconds: int | None = 90,
    max_retries: int = 0,
) -> LlmStressEvalResult:
    manifest = load_submission_manifest(repo_root, manifest_path)
    region = manifest.region_for_id(region_id)
    artifacts = _output_dir(repo_root, region_id, output_dir)
    map_artifact = _load_map_artifact(repo_root, region)
    baseline_text = _read_text(repo_root, baseline_path or region.baseline_path)
    packet = _case_packet(region, map_artifact, baseline_text)
    prompts = {spec["prompt_id"]: _build_prompt(spec, packet, map_artifact) for spec in PROMPT_SPECS}
    specs_by_id = {spec["prompt_id"]: spec for spec in PROMPT_SPECS}
    for prompt_id, prompt in prompts.items():
        write_markdown(artifacts / "prompts" / f"{prompt_id}.txt", prompt)

    backends = [backend, *(compare_backends or [])]
    model_runs: list[dict[str, Any]] = []
    parsed_outputs: list[dict[str, Any]] = []
    reference_issues: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for backend_spec in backends:
        for prompt_id, prompt in prompts.items():
            run_record = _run_eval_prompt(
                prompt_id=prompt_id,
                prompt=prompt,
                response_schema=_stress_response_schema(specs_by_id[prompt_id]),
                backend=backend_spec,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                artifacts=artifacts,
            )
            model_runs.append(run_record)
            payload = run_record.get("parsed_json")
            if payload is None:
                if not run_record.get("prompt_only"):
                    findings.append(
                        {
                            "finding_type": "invalid_model_json",
                            "severity": "high",
                            "backend": backend_spec,
                            "prompt_id": prompt_id,
                            "reason": run_record.get("error") or "Model response was not parseable JSON.",
                        }
                    )
                continue
            parsed_outputs.append(
                {
                    "backend": backend_spec,
                    "prompt_id": prompt_id,
                    "payload": payload,
                }
            )
            reference_issues.extend(_reference_issues(prompt_id, backend_spec, payload, map_artifact, baseline_text))
            findings.extend(_findings_from_payload(prompt_id, backend_spec, payload))

    cross_backend = _cross_backend_disagreements(parsed_outputs)
    deterministic_checks = _deterministic_checks(map_artifact, baseline_text, model_runs, reference_issues)
    if cross_backend:
        findings.append(
            {
                "finding_type": "cross_backend_disagreement",
                "severity": "medium",
                "reason": "Backends produced different referenced claim, relation, source, or finding sets.",
                "disagreement_count": len(cross_backend),
            }
        )
    for issue in reference_issues:
        findings.append(
            {
                "finding_type": "reference_validation_issue",
                "severity": "high",
                "backend": issue["backend"],
                "prompt_id": issue["prompt_id"],
                "reason": issue["reason"],
            }
        )

    report = {
        "schema_id": EVAL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "region_id": region_id,
        "map_path": map_artifact["path"],
        "baseline_path": str(baseline_path or region.baseline_path),
        "backends": backends,
        "prompt_ids": list(prompts),
        "artifact_paths": {
            "json": (artifacts / "llm_stress_eval.json").relative_to(repo_root).as_posix(),
            "markdown": (artifacts / "LLM_STRESS_EVAL.md").relative_to(repo_root).as_posix(),
            "prompts": (artifacts / "prompts").relative_to(repo_root).as_posix(),
            "raw_outputs": (artifacts / "raw_outputs").relative_to(repo_root).as_posix(),
        },
        "map_inventory": _inventory(map_artifact),
        "model_runs": model_runs,
        "parsed_outputs": parsed_outputs,
        "reference_issues": reference_issues,
        "cross_backend_disagreements": cross_backend,
        "deterministic_checks": deterministic_checks,
        "built_in_metamorphic_checks": list(BUILT_IN_METAMORPHIC_CHECKS),
        "findings": findings,
        "summary": {
            "prompt_count": len(prompts),
            "backend_count": len(backends),
            "model_run_count": len(model_runs),
            "parsed_output_count": len(parsed_outputs),
            "reference_issue_count": len(reference_issues),
            "cross_backend_disagreement_count": len(cross_backend),
            "finding_count": len(findings),
            "prompt_only": all(run.get("prompt_only") for run in model_runs),
            "status": _status(findings),
        },
    }
    json_path = artifacts / "llm_stress_eval.json"
    markdown_path = artifacts / "LLM_STRESS_EVAL.md"
    write_json(json_path, report)
    write_markdown(markdown_path, _markdown_report(report))
    return LlmStressEvalResult(
        output_dir=artifacts,
        json_path=json_path,
        markdown_path=markdown_path,
        prompt_count=len(prompts),
        model_run_count=len(model_runs),
        finding_count=len(findings),
        reference_issue_count=len(reference_issues),
    )


def _output_dir(repo_root: Path, region_id: str, output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        path = Path(output_dir)
        if not path.is_absolute():
            path = repo_root / path
    else:
        path = repo_root / "artifacts" / "llm_stress_eval" / region_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_map_artifact(repo_root: Path, region: WorkedRegion) -> dict[str, Any]:
    path = _json_map_path(repo_root, region)
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = data.get("worked_map") if isinstance(data, dict) and isinstance(data.get("worked_map"), dict) else data
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "raw": data,
        "payload": payload,
        "claims": _claims(payload),
        "relations": _relations(payload),
        "cruxes": payload.get("crux_candidates", []) if isinstance(payload, dict) else [],
    }


def _json_map_path(repo_root: Path, region: WorkedRegion) -> Path:
    map_path = repo_root / region.map_path
    if map_path.suffix.lower() == ".json":
        return map_path
    output_json_path = repo_root / region.output_json_path
    if output_json_path.exists():
        return output_json_path
    return map_path


def _claims(payload: dict[str, Any]) -> list[dict[str, Any]]:
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    normalized: list[dict[str, Any]] = []
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            continue
        normalized.append(
            {
                "claim_id": claim_id,
                "text": _as_text(claim.get("claim") or claim.get("text")),
                "source_id": _as_text(claim.get("source_id")),
                "source_span": _as_text(claim.get("source_span")),
                "excerpt": _as_text(claim.get("excerpt")),
                "role": _as_text(claim.get("role") or claim.get("claim_type")),
                "entailed_by_excerpt": _as_text(claim.get("entailed_by_excerpt")),
            }
        )
    return normalized


def _relations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    relations = payload.get("relations", []) if isinstance(payload, dict) else []
    normalized: list[dict[str, Any]] = []
    for relation in relations if isinstance(relations, list) else []:
        if not isinstance(relation, dict):
            continue
        relation_id = relation.get("relation_id")
        if not isinstance(relation_id, str) or not relation_id:
            continue
        normalized.append(
            {
                "relation_id": relation_id,
                "source_claim_id": _as_text(relation.get("source_claim") or relation.get("source_claim_id")),
                "target_claim_id": _as_text(relation.get("target_claim") or relation.get("target_claim_id")),
                "relation_type": _as_text(relation.get("relation_type")),
                "rationale": _as_text(relation.get("rationale")),
            }
        )
    return normalized


def _read_text(repo_root: Path, path: str | Path) -> str:
    target = Path(path)
    if not target.is_absolute():
        target = repo_root / target
    return target.read_text(encoding="utf-8")


def _case_packet(region: WorkedRegion, map_artifact: dict[str, Any], baseline_text: str) -> str:
    claims = "\n".join(
        (
            f"- {claim['claim_id']} [{claim['role']}; source={claim['source_id']} {claim['source_span']}]: "
            f"{claim['text']} Excerpt: {claim['excerpt']}"
        )
        for claim in map_artifact["claims"]
    )
    relations = "\n".join(
        (
            f"- {relation['relation_id']} {relation['source_claim_id']} -> {relation['target_claim_id']} "
            f"({relation['relation_type']}): {relation['rationale']}"
        )
        for relation in map_artifact["relations"]
    )
    cruxes = "\n".join(f"- {crux}" for crux in map_artifact["cruxes"] if isinstance(crux, str))
    return "\n\n".join(
        (
            f"Region ID: {region.region_id}",
            f"Case: {region.case_label}",
            f"Required sources: {', '.join(region.required_sources)}",
            "Structured map claims:\n" + (claims or "No claims found."),
            "Structured map relations:\n" + (relations or "No relations found."),
            "Structured map crux candidates:\n" + (cruxes or "No crux candidates found."),
            "Flat baseline text:\n" + _truncate(baseline_text, 9000),
        )
    )


def _build_prompt(spec: dict[str, Any], packet: str, map_artifact: dict[str, Any]) -> str:
    known_claims = ", ".join(sorted(claim["claim_id"] for claim in map_artifact["claims"])) or "none"
    known_relations = ", ".join(sorted(relation["relation_id"] for relation in map_artifact["relations"])) or "none"
    known_sources = ", ".join(sorted({claim["source_id"] for claim in map_artifact["claims"] if claim["source_id"]})) or "none"
    return render_prompt(
        ("Task", f"You are an automated epistemic stress evaluator.\n{spec['instruction']}"),
        (
            "Metadata",
            f"Prompt version: {EVAL_VERSION}\nPrompt ID: {spec['prompt_id']}\nTask: {spec['title']}",
        ),
        (
            "Rules",
            [
                "- Return valid JSON only.",
                "- Use only known IDs from the packet.",
                "- Produce source-linked stress signals and candidate improvements.",
                "- If there is insufficient evidence, return an empty list for the relevant field.",
                f"- Known claim IDs: {known_claims}",
                f"- Known relation IDs: {known_relations}",
                f"- Known source IDs: {known_sources}",
            ],
        ),
        ("Output Schema", json_schema_block(spec["schema"])),
        ("Examples", examples_block(_stress_prompt_examples(spec))),
        ("Context", xml_block("packet", packet)),
    )


def _stress_prompt_examples(spec: dict[str, Any]) -> list[dict[str, Any]]:
    root_key = next(iter(spec["schema"]))
    return [
        {
            "input_hint": "Packet lacks enough evidence for a reliable finding.",
            "output": {root_key: []},
        }
    ]


def _stress_response_schema(spec: dict[str, Any]) -> dict[str, Any]:
    root_key = next(iter(spec["schema"]))
    return {
        "type": "object",
        "properties": {root_key: {"type": "array", "items": {"type": "object"}}},
        "required": [root_key],
    }


def _run_eval_prompt(
    *,
    prompt_id: str,
    prompt: str,
    response_schema: dict[str, Any],
    backend: str,
    timeout_seconds: int | None,
    max_retries: int,
    artifacts: Path,
) -> dict[str, Any]:
    output_stem = f"{_safe(backend)}__{prompt_id}"
    try:
        result = run_model_backend(
            prompt,
            backend,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            response_schema=response_schema,
        )
    except (RuntimeError, ValueError) as exc:
        return {
            "backend": backend,
            "prompt_id": prompt_id,
            "status": "backend_error",
            "prompt_only": False,
            "error": str(exc),
        }
    raw_path = artifacts / "raw_outputs" / f"{output_stem}.txt"
    write_markdown(raw_path, result.text)
    if result.prompt_only:
        return {
            "backend": backend,
            "prompt_id": prompt_id,
            "status": "prompt_only",
            "prompt_only": True,
            "attempts": result.attempts,
            "raw_output_path": raw_path.as_posix(),
            "parsed_json": None,
        }
    canonical = canonical_json_output(result.text)
    try:
        payload = json.loads(canonical)
    except json.JSONDecodeError:
        payload = None
    if payload is not None:
        write_json(artifacts / "parsed_outputs" / f"{output_stem}.json", payload)
    return {
        "backend": backend,
        "prompt_id": prompt_id,
        "status": "parsed" if payload is not None else "invalid_json",
        "prompt_only": False,
        "attempts": result.attempts,
        "raw_output_path": raw_path.as_posix(),
        "parsed_json": payload,
    }


def _reference_issues(
    prompt_id: str,
    backend: str,
    payload: Any,
    map_artifact: dict[str, Any],
    baseline_text: str,
) -> list[dict[str, Any]]:
    known_claims = {claim["claim_id"] for claim in map_artifact["claims"]}
    known_relations = {relation["relation_id"] for relation in map_artifact["relations"]}
    known_sources = {claim["source_id"] for claim in map_artifact["claims"] if claim["source_id"]}
    issues: list[dict[str, Any]] = []
    for key_path, value in _walk_json(payload):
        key = key_path[-1] if key_path else ""
        if key in {"map_claim_ids", "threatened_claim_ids", "linked_claim_ids", "claim_ids"}:
            for item in _string_items(value):
                if item not in known_claims:
                    issues.append(_issue(prompt_id, backend, key_path, f"unknown_claim_id {item}"))
        if key == "relation_ids" or key == "relation_id":
            for item in _string_items(value):
                if item not in known_relations:
                    issues.append(_issue(prompt_id, backend, key_path, f"unknown_relation_id {item}"))
        if key == "source_ids" or key == "source_id":
            for item in _string_items(value):
                if item and item not in known_sources:
                    issues.append(_issue(prompt_id, backend, key_path, f"unknown_source_id {item}"))
        if key == "baseline_excerpt" and isinstance(value, str) and value.strip():
            if _normalize_phrase(value) not in _normalize_phrase(baseline_text):
                issues.append(_issue(prompt_id, backend, key_path, "baseline_excerpt_not_found"))
    return issues


def _findings_from_payload(prompt_id: str, backend: str, payload: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return [
            {
                "finding_type": "unexpected_payload_shape",
                "severity": "medium",
                "backend": backend,
                "prompt_id": prompt_id,
                "reason": "Expected a JSON object.",
            }
        ]
    if prompt_id == "insight_delta":
        for delta in payload.get("insight_deltas", []) if isinstance(payload.get("insight_deltas"), list) else []:
            if isinstance(delta, dict):
                findings.append(
                    {
                        "finding_type": "candidate_insight_delta",
                        "severity": "note",
                        "backend": backend,
                        "prompt_id": prompt_id,
                        "reason": _as_text(delta.get("decision_consequence")),
                    }
                )
    if prompt_id == "adversarial_critique":
        for finding in payload.get("critic_findings", []) if isinstance(payload.get("critic_findings"), list) else []:
            if isinstance(finding, dict):
                findings.append(
                    {
                        "finding_type": _as_text(finding.get("finding_type")) or "critic_finding",
                        "severity": _severity(finding.get("severity")),
                        "backend": backend,
                        "prompt_id": prompt_id,
                        "reason": _as_text(finding.get("reason")),
                    }
                )
    if prompt_id == "relation_usefulness":
        assessments = payload.get("relation_assessments", [])
        for assessment in assessments if isinstance(assessments, list) else []:
            if not isinstance(assessment, dict):
                continue
            decision = _as_text(assessment.get("decision"))
            if decision in {"misleading", "unsupported"}:
                severity = "high"
            elif decision in {"shallow", "duplicate"}:
                severity = "medium"
            else:
                severity = "note"
            findings.append(
                {
                    "finding_type": f"relation_{decision or 'assessment'}",
                    "severity": severity,
                    "backend": backend,
                    "prompt_id": prompt_id,
                    "reason": _as_text(assessment.get("rationale")),
                }
            )
    if prompt_id == "metamorphic_pressure":
        tests = payload.get("metamorphic_tests", [])
        for test in tests if isinstance(tests, list) else []:
            if isinstance(test, dict):
                findings.append(
                    {
                        "finding_type": "model_proposed_metamorphic_test",
                        "severity": "note",
                        "backend": backend,
                        "prompt_id": prompt_id,
                        "reason": _as_text(test.get("failure_signal")),
                    }
                )
    return findings


def _cross_backend_disagreements(parsed_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_prompt: dict[str, list[dict[str, Any]]] = {}
    for output in parsed_outputs:
        by_prompt.setdefault(output["prompt_id"], []).append(output)
    disagreements: list[dict[str, Any]] = []
    for prompt_id, outputs in by_prompt.items():
        if len(outputs) < 2:
            continue
        fingerprints = {
            output["backend"]: {
                "claim_ids": sorted(_referenced_values(output["payload"], {"map_claim_ids", "threatened_claim_ids", "linked_claim_ids", "claim_ids"})),
                "relation_ids": sorted(_referenced_values(output["payload"], {"relation_id", "relation_ids"})),
                "source_ids": sorted(_referenced_values(output["payload"], {"source_id", "source_ids"})),
                "finding_keys": sorted(_top_level_finding_keys(output["payload"])),
            }
            for output in outputs
        }
        if len({json.dumps(value, sort_keys=True) for value in fingerprints.values()}) > 1:
            disagreements.append({"prompt_id": prompt_id, "fingerprints": fingerprints})
    return disagreements


def _deterministic_checks(
    map_artifact: dict[str, Any],
    baseline_text: str,
    model_runs: list[dict[str, Any]],
    reference_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    claims = map_artifact["claims"]
    relations = map_artifact["relations"]
    caveat_claims = [claim for claim in claims if re.search(r"caveat|scope|limit|uncertain|challenge", claim["role"], re.I)]
    return {
        "claim_count": len(claims),
        "relation_count": len(relations),
        "source_count": len({claim["source_id"] for claim in claims if claim["source_id"]}),
        "baseline_word_count": len(re.findall(r"\w+", baseline_text)),
        "caveat_or_scope_claim_count": len(caveat_claims),
        "model_parse_success_count": sum(1 for run in model_runs if run["status"] == "parsed"),
        "model_error_count": sum(1 for run in model_runs if run["status"] in {"backend_error", "invalid_json"}),
        "prompt_only_count": sum(1 for run in model_runs if run.get("prompt_only")),
        "reference_issue_count": len(reference_issues),
        "relation_endpoint_issue_count": _relation_endpoint_issue_count(claims, relations),
    }


def _relation_endpoint_issue_count(claims: list[dict[str, Any]], relations: list[dict[str, Any]]) -> int:
    known = {claim["claim_id"] for claim in claims}
    issues = 0
    for relation in relations:
        if relation["source_claim_id"] not in known:
            issues += 1
        if relation["target_claim_id"] not in known:
            issues += 1
    return issues


def _inventory(map_artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_ids": [claim["claim_id"] for claim in map_artifact["claims"]],
        "relation_ids": [relation["relation_id"] for relation in map_artifact["relations"]],
        "source_ids": sorted({claim["source_id"] for claim in map_artifact["claims"] if claim["source_id"]}),
        "crux_count": len(map_artifact["cruxes"]),
    }


def _status(findings: list[dict[str, Any]]) -> str:
    severities = {finding.get("severity") for finding in findings}
    if "high" in severities:
        return "risk"
    if "medium" in severities:
        return "watch"
    return "ok"


def _markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# LLM Stress Eval: {report['region_id']}",
        "",
        f"Status: `{summary['status']}`",
        f"Schema: `{report['schema_id']}`",
        "",
        "## Summary",
        "",
        f"- Backends: {', '.join(report['backends'])}",
        f"- Prompts: {summary['prompt_count']}",
        f"- Model runs: {summary['model_run_count']}",
        f"- Parsed outputs: {summary['parsed_output_count']}",
        f"- Reference issues: {summary['reference_issue_count']}",
        f"- Cross-backend disagreements: {summary['cross_backend_disagreement_count']}",
        "",
        "## What This Tests",
        "",
        "- Map-vs-flat-baseline insight deltas.",
        "- Adversarial critique for unsupported confidence, rhetoric, missing caveats, and source-status confusion.",
        "- Relation usefulness as distinct from schema validity.",
        "- Metamorphic pressure tests that should change or preserve map behavior in predictable ways.",
        "",
        "## Deterministic Checks",
        "",
    ]
    for key, value in report["deterministic_checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Findings", ""])
    if not report["findings"]:
        lines.append("No findings emitted.")
    else:
        for finding in report["findings"][:30]:
            backend = finding.get("backend", "deterministic")
            prompt_id = finding.get("prompt_id", "summary")
            lines.append(
                f"- `{finding.get('severity', 'note')}` {finding.get('finding_type', 'finding')} "
                f"({backend}/{prompt_id}): {finding.get('reason', '')}"
            )
    lines.extend(["", "## Built-In Metamorphic Checks", ""])
    for check in report["built_in_metamorphic_checks"]:
        lines.append(f"- `{check['test_type']}`: {check['expected_invariant']}")
    lines.extend(
        [
            "",
            "## Artifact Paths",
            "",
            f"- JSON: `{report['artifact_paths']['json']}`",
            f"- Prompts: `{report['artifact_paths']['prompts']}`",
            f"- Raw outputs: `{report['artifact_paths']['raw_outputs']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _walk_json(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    rows = [(path, value)]
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(_walk_json(item, (*path, str(key))))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_walk_json(item, (*path, str(index))))
    return rows


def _string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _referenced_values(payload: Any, keys: set[str]) -> set[str]:
    values: set[str] = set()
    for key_path, value in _walk_json(payload):
        if key_path and key_path[-1] in keys:
            values.update(_string_items(value))
    return values


def _top_level_finding_keys(payload: Any) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    keys: set[str] = set()
    for key, value in payload.items():
        if isinstance(value, list):
            keys.add(f"{key}:{len(value)}")
        else:
            keys.add(key)
    return keys


def _issue(prompt_id: str, backend: str, key_path: tuple[str, ...], reason: str) -> dict[str, Any]:
    return {
        "prompt_id": prompt_id,
        "backend": backend,
        "path": ".".join(key_path),
        "reason": reason,
    }


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _severity(value: Any) -> str:
    if isinstance(value, str) and value in {"low", "medium", "high", "note"}:
        return value
    return "medium"


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "backend"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def _normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
