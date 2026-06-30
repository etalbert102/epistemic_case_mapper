from __future__ import annotations

import re
import json
from pathlib import Path
from textwrap import dedent

from epistemic_case_mapper.io import read_yaml
from epistemic_case_mapper.schema import CaseManifest, Source
from epistemic_case_mapper.submission_manifest import SubmissionManifest, WorkedRegion, load_submission_manifest


MAP_PROMPT_VERSION = "source_mapping_prompt_v2_json"
CRITIQUE_PROMPT_VERSION = "semantic_critique_prompt_v1_json"
VALID_ENTAILMENT = {"yes", "no", "uncertain"}
VALID_CRITIQUE_SEVERITY = {"note", "risk", "fail"}
VALID_CRITIQUE_CATEGORY = {
    "unsupported_claim",
    "relation_overreach",
    "missing_perspective",
    "weak_source_provenance",
    "baseline_uplift",
    "crux_quality",
    "endpoint_confusion",
    "quantitative_gap",
    "presentation_risk",
    "other",
}


def build_map_prompt(repo_root: Path, manifest_path: str, region_id: str) -> str:
    manifest, region, case_manifest = _load_context(repo_root, manifest_path, region_id)
    relation_types = sorted(manifest.relation_ontology.permitted_types())
    source_blocks = "\n\n".join(_source_prompt_block(repo_root, source) for source in _required_sources(case_manifest, region))
    relation_definitions = "\n".join(
        f"- {relation_type}: {definition}"
        for relation_type, definition in sorted(manifest.relation_ontology.custom_definitions.items())
    )
    return f"""You are producing a source-grounded epistemic case-map candidate.

Prompt version: {MAP_PROMPT_VERSION}
Region ID: {region.region_id}
Case question: {case_manifest.question}

Worked-region definition:
{_read_optional(repo_root / region.definition_path)}

Source packet:
{source_blocks}

Allowed relation types:
{", ".join(relation_types)}

Custom relation definitions:
{relation_definitions or "- None"}

Return only JSON matching this shape:
{{
  "title": "...",
  "status": "human-review-needed",
  "prompt_procedure": "{MAP_PROMPT_VERSION}",
  "evidence_mode": "source_grounded",
  "sources": ["source_id"],
  "claims": [
    {{
      "claim_id": "stable package claim ID",
      "claim": "one source-grounded claim",
      "source_id": "source_id",
      "source_span": "lines X-Y",
      "excerpt": "exact quote from the source packet",
      "entailed_by_excerpt": "yes|no|uncertain",
      "role": "conclusion_support|crux|scope_limit|implementation_constraint|background|other"
    }}
  ],
  "relations": [
    {{
      "relation_id": "stable package relation ID",
      "source_claim": "claim_id",
      "target_claim": "claim_id",
      "relation_type": "one allowed relation type",
      "rationale": "why this edge helps reasoning without overstating support"
    }}
  ],
  "crux_candidates": ["crux text that names relevant claim IDs where possible"],
  "similar_but_not_identical": ["distinction text"],
  "evidence_check": [["Probe", "Survives|Needs review|Fails", "Notes"]]
}}

Rules:
- Extract only claims supported by exact excerpts in the source packet.
- Do not convert a weak local note into a stronger external-evidence claim.
- Preserve implementation constraints, endpoint distinctions, and source limitations as claims or cruxes when they affect the answer.
- Do not invent sources, IDs, spans, effect sizes, or consensus.
- Use only allowed relation types unless the package manifest defines a custom relation type.
- Prefer fewer, more inspectable claims over broad narrative coverage.
"""


def build_critique_prompt(repo_root: Path, manifest_path: str, region_id: str, map_path: str | None = None) -> str:
    manifest, region, case_manifest = _load_context(repo_root, manifest_path, region_id)
    source_blocks = "\n\n".join(_source_prompt_block(repo_root, source) for source in _required_sources(case_manifest, region))
    candidate_path = repo_root / (map_path or region.map_path)
    candidate_text = candidate_path.read_text(encoding="utf-8") if candidate_path.exists() else ""
    baseline_text = _read_optional(repo_root / region.baseline_path)
    return f"""You are red-teaming a source-grounded epistemic case-map candidate.

Prompt version: {CRITIQUE_PROMPT_VERSION}
Region ID: {region.region_id}
Case question: {case_manifest.question}

Source packet:
{source_blocks}

Candidate map:
{candidate_text}

Flat baseline:
{baseline_text}

Return only JSON matching this shape:
{{
  "title": "...",
  "status": "human-review-needed",
  "prompt_procedure": "{CRITIQUE_PROMPT_VERSION}",
  "findings": [
    {{
      "finding_id": "critique_001",
      "severity": "note|risk|fail",
      "category": "unsupported_claim|relation_overreach|missing_perspective|weak_source_provenance|baseline_uplift|crux_quality|endpoint_confusion|quantitative_gap|presentation_risk|other",
      "target_id": "claim/relation/loss/source id or overall",
      "issue": "specific problem",
      "source_basis": "source ID/span or baseline/map basis",
      "recommended_fix": "concrete change"
    }}
  ]
}}

Critique rules:
- Be stricter about source support than prose style.
- Flag claims that are faithful to local notes but would need primary sources before policy-strength use.
- Flag relation labels that imply too much.
- Flag cases where the map is not much better than the flat baseline.
- Do not propose unsupported new claims as fixes.
"""


def validate_map_candidate(repo_root: Path, manifest_path: str, region_id: str, candidate_path: Path) -> list[str]:
    manifest, region, case_manifest = _load_context(repo_root, manifest_path, region_id)
    failures: list[str] = []
    data = _read_json(candidate_path, failures)
    if not isinstance(data, dict):
        return failures
    required_sources = {source.source_id for source in _required_sources(case_manifest, region)}
    source_lookup = {source.source_id: source for source in case_manifest.sources}

    _require_equal(data, "evidence_mode", "source_grounded", failures)
    _require_field(data, "title", failures)
    _require_field(data, "status", failures)
    _require_prompt(data, MAP_PROMPT_VERSION, failures)
    listed_sources = set(str(source_id) for source_id in data.get("sources", []))
    if not listed_sources:
        failures.append("semantic_map_missing_sources")
    unknown_sources = listed_sources - {source.source_id for source in case_manifest.sources}
    for source_id in sorted(unknown_sources):
        failures.append(f"semantic_map_unknown_source source={source_id}")
    missing_required = required_sources - listed_sources
    for source_id in sorted(missing_required):
        failures.append(f"semantic_map_missing_required_source source={source_id}")

    claims = data.get("claims", [])
    relations = data.get("relations", [])
    if not isinstance(claims, list) or not claims:
        failures.append("semantic_map_missing_claims")
        claims = []
    if not isinstance(relations, list) or not relations:
        failures.append("semantic_map_missing_relations")
        relations = []

    claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            failures.append("semantic_map_claim_not_object")
            continue
        claim_id = str(claim.get("claim_id", ""))
        if not claim_id:
            failures.append("semantic_map_claim_missing_id")
        elif claim_id in claim_ids:
            failures.append(f"semantic_map_duplicate_claim_id claim={claim_id}")
        claim_ids.add(claim_id)
        _validate_claim(repo_root, source_lookup, claim, failures)

    permitted_relation_types = manifest.relation_ontology.permitted_types()
    relation_ids: set[str] = set()
    for relation in relations:
        if not isinstance(relation, dict):
            failures.append("semantic_map_relation_not_object")
            continue
        relation_id = str(relation.get("relation_id", ""))
        if not relation_id:
            failures.append("semantic_map_relation_missing_id")
        elif relation_id in relation_ids:
            failures.append(f"semantic_map_duplicate_relation_id relation={relation_id}")
        relation_ids.add(relation_id)
        _validate_relation(relation, claim_ids, permitted_relation_types, failures)

    cruxes = data.get("crux_candidates", [])
    if not isinstance(cruxes, list) or len(cruxes) < region.thresholds.min_crux_mentions:
        failures.append(
            f"semantic_map_too_few_cruxes count={len(cruxes) if isinstance(cruxes, list) else 'missing'}"
        )
    evidence_check = data.get("evidence_check", [])
    if not isinstance(evidence_check, list) or len(evidence_check) < region.thresholds.min_evidence_rows:
        failures.append(
            f"semantic_map_evidence_check_too_short rows={len(evidence_check) if isinstance(evidence_check, list) else 'missing'}"
        )
    if not isinstance(data.get("similar_but_not_identical", []), list):
        failures.append("semantic_map_similar_but_not_identical_not_list")
    return failures


def validate_critique_candidate(candidate_path: Path) -> list[str]:
    failures: list[str] = []
    data = _read_json(candidate_path, failures)
    if not isinstance(data, dict):
        return failures
    _require_field(data, "title", failures)
    _require_field(data, "status", failures)
    _require_prompt(data, CRITIQUE_PROMPT_VERSION, failures)
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        failures.append("semantic_critique_findings_not_list")
        return failures
    finding_ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            failures.append("semantic_critique_finding_not_object")
            continue
        finding_id = str(finding.get("finding_id", ""))
        if not finding_id:
            failures.append("semantic_critique_finding_missing_id")
        elif finding_id in finding_ids:
            failures.append(f"semantic_critique_duplicate_finding_id finding={finding_id}")
        finding_ids.add(finding_id)
        severity = str(finding.get("severity", ""))
        if severity not in VALID_CRITIQUE_SEVERITY:
            failures.append(f"semantic_critique_bad_severity finding={finding_id} severity={severity}")
        category = str(finding.get("category", ""))
        if category not in VALID_CRITIQUE_CATEGORY:
            failures.append(f"semantic_critique_bad_category finding={finding_id} category={category}")
        for field in ("target_id", "issue", "source_basis", "recommended_fix"):
            if not str(finding.get(field, "")).strip():
                failures.append(f"semantic_critique_missing_field finding={finding_id} field={field}")
    return failures


def _validate_claim(repo_root: Path, source_lookup: dict[str, Source], claim: dict, failures: list[str]) -> None:
    claim_id = str(claim.get("claim_id", ""))
    source_id = str(claim.get("source_id", ""))
    if source_id not in source_lookup:
        failures.append(f"semantic_map_claim_unknown_source claim={claim_id} source={source_id}")
        return
    for field in ("claim", "source_span", "excerpt", "role"):
        if not str(claim.get(field, "")).strip():
            failures.append(f"semantic_map_claim_missing_field claim={claim_id} field={field}")
    entailed = str(claim.get("entailed_by_excerpt", ""))
    if entailed not in VALID_ENTAILMENT:
        failures.append(f"semantic_map_claim_bad_entailment claim={claim_id} value={entailed}")
    excerpt = str(claim.get("excerpt", "")).strip()
    if excerpt:
        source_text = _source_text(repo_root, source_lookup[source_id])
        if excerpt not in source_text:
            failures.append(f"semantic_map_claim_excerpt_not_in_source claim={claim_id} source={source_id}")


def _validate_relation(
    relation: dict,
    claim_ids: set[str],
    permitted_relation_types: set[str],
    failures: list[str],
) -> None:
    relation_id = str(relation.get("relation_id", ""))
    for endpoint in ("source_claim", "target_claim"):
        claim_id = str(relation.get(endpoint, ""))
        if claim_id not in claim_ids:
            failures.append(f"semantic_map_relation_unknown_endpoint relation={relation_id} field={endpoint} claim={claim_id}")
    relation_type = str(relation.get("relation_type", ""))
    if relation_type not in permitted_relation_types:
        failures.append(f"semantic_map_relation_unknown_type relation={relation_id} type={relation_type}")
    if not str(relation.get("rationale", "")).strip():
        failures.append(f"semantic_map_relation_missing_rationale relation={relation_id}")


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


def _source_prompt_block(repo_root: Path, source: Source) -> str:
    lines = _source_text(repo_root, source).splitlines()
    numbered = "\n".join(f"{index}: {line}" for index, line in enumerate(lines, start=1))
    limitations = "; ".join(source.limitations) if source.limitations else "none recorded"
    return dedent(
        f"""
        source_id: {source.source_id}
        title: {source.title}
        source_type: {source.source_type}
        provenance_level: {source.provenance_level}
        evidence_role: {source.evidence_role}
        needs_upgrade: {str(source.needs_upgrade).lower()}
        limitations: {limitations}
        path: {source.path or ""}
        text:
        {numbered}
        """
    ).strip()


def _source_text(repo_root: Path, source: Source) -> str:
    if source.text:
        return source.text
    if source.path:
        path = repo_root / source.path
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return source.excerpt or source.notes or ""


def _read_json(path: Path, failures: list[str]) -> object | None:
    if not path.exists():
        failures.append(f"semantic_candidate_missing path={path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"semantic_candidate_invalid_json path={path} error={exc}")
        return None


def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _require_field(data: dict, field: str, failures: list[str]) -> None:
    if not str(data.get(field, "")).strip():
        failures.append(f"semantic_candidate_missing_field field={field}")


def _require_equal(data: dict, field: str, expected: str, failures: list[str]) -> None:
    actual = str(data.get(field, ""))
    if actual != expected:
        failures.append(f"semantic_candidate_bad_field field={field} expected={expected} actual={actual}")


def _require_prompt(data: dict, expected: str, failures: list[str]) -> None:
    actual = str(data.get("prompt_procedure", ""))
    if actual != expected:
        failures.append(f"semantic_candidate_bad_prompt expected={expected} actual={actual}")
