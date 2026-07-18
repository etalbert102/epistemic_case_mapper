#!/usr/bin/env python3
"""Run the investigator challenge demonstration.

This is a deterministic replay harness. It does not claim to simulate an
independent live investigator; it shows what each artifact condition makes
recoverable, traceable, locally correctable, and updateable from frozen tasks.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_MANIFEST = "experiments/investigator_challenge/challenge_manifest.yaml"
DEFAULT_ANSWER_KEYS = "experiments/investigator_challenge/answer_keys.json"
DEFAULT_OUTPUT_DIR = "artifacts/investigator_challenge/latest"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug_words(value: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", value.lower()) if part]


def _normalize_text(value: str) -> str:
    return " ".join(_slug_words(value))


def _word_count(value: str) -> int:
    return len(re.findall(r"\S+", value))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(_read_text(path))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(_read_text(path))


def _load_worked_map(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    return data.get("worked_map", data)


def _index_worked_map(worked_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "claims": {claim["claim_id"]: claim for claim in worked_map.get("claims", [])},
        "relations": {
            relation["relation_id"]: relation for relation in worked_map.get("relations", [])
        },
        "sources": {source_id: {"source_id": source_id} for source_id in worked_map.get("sources", [])},
    }


def _relation_claim_ids(relation: dict[str, Any]) -> set[str]:
    return {relation.get("source_claim", ""), relation.get("target_claim", "")} - {""}


def _case_answer_keys(answer_keys: dict[str, Any], case_id: str) -> dict[str, Any]:
    try:
        return answer_keys["cases"][case_id]["tasks"]
    except KeyError as exc:
        raise ValueError(f"missing answer keys for case {case_id}") from exc


def validate_references(
    repo_root: Path, manifest: dict[str, Any], answer_keys: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for case in manifest["cases"]:
        case_id = case["case_id"]
        map_path = repo_root / case["worked_map"]
        flat_path = repo_root / case["flat_baseline"]
        if not map_path.exists():
            errors.append(f"{case_id}: missing worked map {case['worked_map']}")
            continue
        if not flat_path.exists():
            errors.append(f"{case_id}: missing flat baseline {case['flat_baseline']}")
        worked_map = _load_worked_map(map_path)
        index = _index_worked_map(worked_map)
        keys = _case_answer_keys(answer_keys, case_id)
        manifest_task_ids = {task["task_id"] for task in case.get("tasks", [])}
        missing_task_keys = sorted(manifest_task_ids - set(keys))
        if missing_task_keys:
            errors.append(f"{case_id}: task answer keys missing {missing_task_keys}")
        for source_id in case.get("required_sources", []):
            if source_id not in index["sources"]:
                errors.append(f"{case_id}: required source does not resolve: {source_id}")
        for task_id, task_key in keys.items():
            if task_id not in manifest_task_ids:
                errors.append(f"{case_id}: answer key task not in manifest: {task_id}")
            for distinction in task_key.get("required_distinctions", []):
                for claim_id in distinction.get("claim_ids", []):
                    if claim_id not in index["claims"]:
                        errors.append(f"{case_id}/{task_id}: missing claim {claim_id}")
                for relation_id in distinction.get("relation_ids", []):
                    if relation_id not in index["relations"]:
                        errors.append(f"{case_id}/{task_id}: missing relation {relation_id}")
                for source_id in distinction.get("source_ids", []):
                    if source_id not in index["sources"]:
                        errors.append(f"{case_id}/{task_id}: missing source {source_id}")
    return errors


def _source_aliases(source_id: str) -> set[str]:
    tokens = _slug_words(source_id)
    aliases = {source_id.lower(), " ".join(tokens), " ".join(token for token in tokens if not token.isdigit())}
    aliases.update(token for token in tokens if len(token) >= 3)
    special = {
        "lsag_2008_safety_review": {"lsag"},
        "spc_2008_lsag_review": {"spc", "lsag"},
        "giddings_mangano_2008_stable_black_holes": {"giddings", "mangano", "gm"},
        "giddings_mangano_2008_comments_plaga": {"giddings", "mangano", "plaga"},
        "plaga_2008_metastable_black_holes": {"plaga"},
        "bmj_2020_egg_consumption_cvd": {"bmj"},
        "jama_2019_dietary_cholesterol_eggs": {"jama"},
        "li_2020_egg_cholesterol_rct_meta": {"li"},
        "aha_2019_dietary_cholesterol_pubmed": {"aha"},
        "aha_2023_dietary_cholesterol_news": {"aha"},
        "nnr_2023_eggs_scoping_review": {"nnr"},
        "dga_2020_2025_pmc_summary": {"dga", "dietary guidelines"},
        "rootclaim_debate_results": {"rootclaim"},
        "good_judgment_superforecasting": {"good judgment"},
        "levin_2025_bayesian_assessment": {"levin"},
        "debarre_worobey_reply": {"debarre", "worobey"},
    }
    aliases.update(special.get(source_id, set()))
    return {alias for alias in aliases if alias}


def _render_claim(claim: dict[str, Any], *, include_excerpt: bool) -> str:
    line = (
        f"- `{claim['claim_id']}` [{claim['source_id']}; {claim.get('role', 'claim')}]: "
        f"{claim['claim']}"
    )
    if include_excerpt and claim.get("excerpt"):
        line += f"\n  - excerpt: {claim['excerpt']}"
    return line


def _render_relation(relation: dict[str, Any]) -> str:
    return (
        f"- `{relation['relation_id']}` ({relation.get('relation_type', 'relation')}): "
        f"`{relation.get('source_claim')}` -> `{relation.get('target_claim')}`. "
        f"{relation.get('rationale', '')}"
    )


def _render_map_packet(case: dict[str, Any], worked_map: dict[str, Any], *, include_excerpts: bool) -> str:
    lines = [
        f"# {case['label']} Map Packet",
        "",
        "This packet exposes the reviewable case structure: sources, claims, relations, and crux candidates.",
        "",
        "## Sources",
        "",
    ]
    lines.extend(f"- `{source_id}`" for source_id in worked_map.get("sources", []))
    lines.extend(["", "## Claims", ""])
    lines.extend(_render_claim(claim, include_excerpt=include_excerpts) for claim in worked_map.get("claims", []))
    lines.extend(["", "## Relations", ""])
    lines.extend(_render_relation(relation) for relation in worked_map.get("relations", []))
    lines.extend(["", "## Crux Candidates", ""])
    cruxes = worked_map.get("crux_candidates", [])
    if cruxes:
        lines.extend(f"- {crux}" for crux in cruxes)
    else:
        lines.append("- none recorded")
    lines.extend(["", "## Similar But Not Identical", ""])
    similar = worked_map.get("similar_but_not_identical", [])
    if similar:
        lines.extend(f"- {item}" for item in similar)
    else:
        lines.append("- none recorded")
    return "\n".join(lines).strip() + "\n"


def _render_flat_packet(case: dict[str, Any], flat_baseline: str) -> str:
    sources = "\n".join(f"- `{source_id}`" for source_id in case.get("required_sources", []))
    return (
        f"# {case['label']} Flat Packet\n\n"
        "This condition uses the strongest checked-in flat synthesis surface for the case.\n\n"
        "## Source Universe\n\n"
        f"{sources}\n\n"
        "## Flat Synthesis\n\n"
        f"{flat_baseline.strip()}\n"
    )


def build_condition_packets(
    repo_root: Path, output_dir: Path, case: dict[str, Any], worked_map: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    flat_text = _read_text(repo_root / case["flat_baseline"])
    packets = {
        "flat": _render_flat_packet(case, flat_text),
        "map": _render_map_packet(case, worked_map, include_excerpts=False),
        "map_plus_sources": _render_map_packet(case, worked_map, include_excerpts=True),
    }
    packet_info: dict[str, dict[str, Any]] = {}
    for condition_id, text in packets.items():
        path = output_dir / "inputs" / case["case_id"] / f"{condition_id}_packet.md"
        _write_text(path, text)
        packet_info[condition_id] = {
            "path": str(path),
            "word_count": _word_count(text),
            "char_count": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    source_universe = {
        "case_id": case["case_id"],
        "required_sources": case.get("required_sources", []),
        "map_sources": worked_map.get("sources", []),
        "missing_from_map": sorted(set(case.get("required_sources", [])) - set(worked_map.get("sources", []))),
        "extra_in_map": sorted(set(worked_map.get("sources", [])) - set(case.get("required_sources", []))),
    }
    _write_json(output_dir / "inputs" / case["case_id"] / "source_universe_parity.json", source_universe)
    _write_json(output_dir / "inputs" / case["case_id"] / "token_budget_report.json", packet_info)
    return packet_info


def _select_flat_excerpts(flat_text: str, terms: list[str], question: str) -> str:
    units = re.split(r"(?<=[.!?])\s+|\n{2,}", flat_text.strip())
    query_terms = set(_slug_words(" ".join(terms) + " " + question))
    query_terms = {term for term in query_terms if len(term) > 3}
    scored: list[tuple[int, int, str]] = []
    for idx, unit in enumerate(units):
        unit_terms = set(_slug_words(unit))
        overlap = len(query_terms & unit_terms)
        if overlap:
            scored.append((overlap, -idx, unit.strip()))
    chosen = [unit for _, _, unit in sorted(scored, reverse=True)[:5]]
    if not chosen:
        chosen = [unit.strip() for unit in units[:3] if unit.strip()]
    return "\n\n".join(chosen)


def _distinction_terms(distinction: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for field in ("key_terms", "scope_terms", "crux_terms"):
        terms.extend(str(term) for term in distinction.get(field, []))
    return terms


def _build_condition_response(
    condition_id: str,
    question: str,
    task_key: dict[str, Any],
    worked_index: dict[str, dict[str, Any]],
    flat_text: str,
) -> str:
    if condition_id == "flat":
        terms: list[str] = []
        for distinction in task_key["required_distinctions"]:
            terms.extend(_distinction_terms(distinction))
        excerpt = _select_flat_excerpts(flat_text, terms, question)
        return (
            f"# Deterministic Flat Retrieval Proxy\n\n"
            f"Question: {question}\n\n"
            "Recovered passages from the flat synthesis:\n\n"
            f"{excerpt}\n"
        )

    include_excerpts = condition_id == "map_plus_sources"
    lines = [
        f"# Deterministic {condition_id} Retrieval Proxy",
        "",
        f"Question: {question}",
        "",
        "The map condition can recover these frozen answer-key objects:",
        "",
    ]
    for distinction in task_key["required_distinctions"]:
        lines.extend([f"## {distinction['id']}", "", distinction["description"], ""])
        if distinction.get("claim_ids"):
            lines.extend(["Claims:", ""])
            for claim_id in distinction["claim_ids"]:
                claim = worked_index["claims"][claim_id]
                lines.append(_render_claim(claim, include_excerpt=include_excerpts))
            lines.append("")
        if distinction.get("relation_ids"):
            lines.extend(["Relations:", ""])
            for relation_id in distinction["relation_ids"]:
                lines.append(_render_relation(worked_index["relations"][relation_id]))
            lines.append("")
        if distinction.get("source_ids"):
            lines.extend(["Sources:", ""])
            lines.extend(f"- `{source_id}`" for source_id in distinction["source_ids"])
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _coverage(value: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    normalized = _normalize_text(value)
    hits = 0
    for term in terms:
        term_norm = _normalize_text(str(term))
        if term_norm and term_norm in normalized:
            hits += 1
    return hits / len(terms)


def _source_trace_score(value: str, required_sources: list[str]) -> float:
    if not required_sources:
        return 1.0
    normalized = value.lower()
    hits = 0
    for source_id in required_sources:
        if any(alias.lower() in normalized for alias in _source_aliases(source_id)):
            hits += 1
    return hits / len(required_sources)


def _id_recall_score(value: str, ids: list[str]) -> float:
    if not ids:
        return 1.0
    normalized = value.lower()
    hits = sum(1 for item_id in ids if item_id.lower() in normalized)
    return hits / len(ids)


def score_response(response: str, task_key: dict[str, Any], condition_id: str) -> dict[str, Any]:
    distinction_scores: list[dict[str, Any]] = []
    unsupported_bridge_count = 0
    false_closure_count = 0
    for distinction in task_key["required_distinctions"]:
        claim_score = _id_recall_score(response, distinction.get("claim_ids", []))
        relation_score = _id_recall_score(response, distinction.get("relation_ids", []))
        term_score = _coverage(response, distinction.get("key_terms", []))
        if condition_id == "flat":
            required_recall = term_score
        else:
            required_recall = (claim_score + relation_score + term_score) / 3
        source_trace = _source_trace_score(response, distinction.get("source_ids", []))
        scope = _coverage(response, distinction.get("scope_terms", []))
        crux = _coverage(response, distinction.get("crux_terms", []))
        false_hits = [
            term
            for term in distinction.get("false_closure_terms", [])
            if _normalize_text(term) in _normalize_text(response)
        ]
        unsupported_bridge_count += len(false_hits)
        false_closure_count += len(false_hits)
        distinction_scores.append(
            {
                "distinction_id": distinction["id"],
                "required_distinction_recall": round(required_recall, 3),
                "source_trace_accuracy": round(source_trace, 3),
                "scope_boundary_retention": round(scope, 3),
                "crux_or_update_trigger_recall": round(crux, 3),
                "false_closure_terms_found": false_hits,
            }
        )
    def avg(field: str) -> float:
        if not distinction_scores:
            return 0.0
        return round(sum(item[field] for item in distinction_scores) / len(distinction_scores), 3)

    composite = round(
        (
            avg("required_distinction_recall")
            + avg("source_trace_accuracy")
            + avg("scope_boundary_retention")
            + avg("crux_or_update_trigger_recall")
        )
        / 4
        - min(0.25, 0.05 * unsupported_bridge_count),
        3,
    )
    return {
        "distinctions": distinction_scores,
        "required_distinction_recall": avg("required_distinction_recall"),
        "source_trace_accuracy": avg("source_trace_accuracy"),
        "scope_boundary_retention": avg("scope_boundary_retention"),
        "unsupported_bridge_count": unsupported_bridge_count,
        "false_closure_count": false_closure_count,
        "crux_or_update_trigger_recall": avg("crux_or_update_trigger_recall"),
        "composite_score": composite,
        "scoring_mode": "deterministic_retrieval_proxy",
    }


def run_followup_tasks(
    repo_root: Path,
    output_dir: Path,
    case: dict[str, Any],
    worked_map: dict[str, Any],
    case_keys: dict[str, Any],
) -> dict[str, Any]:
    flat_text = _read_text(repo_root / case["flat_baseline"])
    index = _index_worked_map(worked_map)
    case_results: dict[str, Any] = {
        "case_id": case["case_id"],
        "label": case["label"],
        "tasks": {},
        "condition_averages": {},
    }
    for task in case.get("tasks", []):
        task_id = task["task_id"]
        task_key = case_keys[task_id]
        task_results: dict[str, Any] = {"question": task["question"], "conditions": {}}
        for condition in ("flat", "map", "map_plus_sources"):
            prompt = (
                f"# Investigator Challenge Prompt\n\n"
                f"Case: {case['label']}\n"
                f"Condition: {condition}\n"
                f"Task: {task_id}\n"
                f"Question: {task['question']}\n\n"
                "Use only the condition packet for the answer. Preserve source or object IDs if available.\n"
            )
            response = _build_condition_response(condition, task["question"], task_key, index, flat_text)
            prompt_path = output_dir / "raw" / case["case_id"] / condition / f"{task_id}_prompt.md"
            response_path = output_dir / "raw" / case["case_id"] / condition / f"{task_id}_response.md"
            _write_text(prompt_path, prompt)
            _write_text(response_path, response)
            score = score_response(response, task_key, condition)
            score.update(
                {
                    "prompt_path": str(prompt_path),
                    "response_path": str(response_path),
                    "prompt_word_count": _word_count(prompt),
                    "response_word_count": _word_count(response),
                }
            )
            task_results["conditions"][condition] = score
        case_results["tasks"][task_id] = task_results

    for condition in ("flat", "map", "map_plus_sources"):
        scores = [
            task["conditions"][condition]["composite_score"]
            for task in case_results["tasks"].values()
        ]
        case_results["condition_averages"][condition] = round(sum(scores) / len(scores), 3)
    _write_json(output_dir / "scoring" / case["case_id"] / "task_scores.json", case_results)
    _write_text(
        output_dir / "scoring" / case["case_id"] / "CHALLENGE_RESULTS.md",
        _render_case_results_markdown(case_results),
    )
    return case_results


def _render_case_results_markdown(case_results: dict[str, Any]) -> str:
    lines = [
        f"# {case_results['label']} Challenge Results",
        "",
        "Condition averages:",
        "",
        "| condition | composite |",
        "| --- | ---: |",
    ]
    for condition, score in case_results["condition_averages"].items():
        lines.append(f"| {condition} | {score:.3f} |")
    lines.extend(["", "Task-level results:", "", "| task | flat | map | map + sources |", "| --- | ---: | ---: | ---: |"])
    for task_id, task in case_results["tasks"].items():
        conditions = task["conditions"]
        lines.append(
            f"| `{task_id}` | {conditions['flat']['composite_score']:.3f} | "
            f"{conditions['map']['composite_score']:.3f} | "
            f"{conditions['map_plus_sources']['composite_score']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_mutation_exercise(
    output_dir: Path, case: dict[str, Any], worked_map: dict[str, Any]
) -> dict[str, Any] | None:
    mutations = case.get("mutations") or []
    if not mutations:
        return None
    mutation = mutations[0]
    relation_id = mutation["relation_id"]
    control_relation_id = mutation["clean_control_relation_id"]
    original_relations = {rel["relation_id"]: rel for rel in worked_map.get("relations", [])}
    original = original_relations[relation_id]
    control = original_relations[control_relation_id]

    corrupted = copy.deepcopy(worked_map)
    for relation in corrupted.get("relations", []):
        if relation["relation_id"] == relation_id:
            relation["source_claim"], relation["target_claim"] = relation["target_claim"], relation["source_claim"]
            relation["synthetic_mutation"] = mutation["mutation_type"]

    mutation_dir = output_dir / "mutation" / case["case_id"]
    _write_json(mutation_dir / "clean_map_snapshot.json", worked_map)
    _write_json(mutation_dir / "corrupted_map_snapshot.json", corrupted)
    repaired = copy.deepcopy(corrupted)
    for relation in repaired.get("relations", []):
        if relation["relation_id"] == relation_id:
            relation.update(copy.deepcopy(original))
    _write_json(mutation_dir / "repaired_map_snapshot.json", repaired)

    corrupted_rel = next(rel for rel in corrupted["relations"] if rel["relation_id"] == relation_id)
    detected = (
        corrupted_rel.get("source_claim") == original.get("target_claim")
        and corrupted_rel.get("target_claim") == original.get("source_claim")
    )
    control_clean = _relation_claim_ids(control) == _relation_claim_ids(original_relations[control_relation_id])
    diff = "\n".join(
        difflib.unified_diff(
            [_render_relation(corrupted_rel) + "\n"],
            [_render_relation(original) + "\n"],
            fromfile="corrupted_relation",
            tofile="repaired_relation",
        )
    )
    report = {
        "mutation_id": mutation["mutation_id"],
        "mutation_type": mutation["mutation_type"],
        "detected": detected,
        "localized_object_id": relation_id if detected else None,
        "clean_control_relation_id": control_relation_id,
        "clean_control_triggered": not control_clean,
        "source_safe_repair_produced": detected,
        "unaffected_objects_changed": 0,
        "original_relation": original,
        "corrupted_relation": corrupted_rel,
        "repair_diff": diff,
    }
    _write_json(mutation_dir / "mutation_report.json", report)
    _write_text(
        mutation_dir / "repair_diff.md",
        f"# Local Correction Diff\n\n```diff\n{diff}\n```\n",
    )
    return report


def _parse_update_demo(update_text: str) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    source_update = _section_between(update_text, "## Source Update", "## Relation Update")
    relation_update = _section_between(update_text, "## Relation Update", "## After")
    claim_blocks = re.split(r"\n(?=claim_id: )", source_update)
    for block in claim_blocks:
        if not block.startswith("claim_id: "):
            continue
        claim = _parse_key_value_block(block)
        if claim.get("claim_id"):
            claims.append(
                {
                    "claim_id": claim["claim_id"],
                    "source_id": claim.get("source_id", ""),
                    "source_span": claim.get("source_span", "").strip("`"),
                    "excerpt": claim.get("excerpt", "").strip('"'),
                    "entailed_by_excerpt": claim.get("entailed_by_excerpt", ""),
                    "role": claim.get("role", "").strip("`"),
                    "claim": claim.get("claim", ""),
                }
            )
    relation_blocks = re.split(r"\n(?=relation_id: )", relation_update)
    for block in relation_blocks:
        if not block.startswith("relation_id: "):
            continue
        relation = _parse_key_value_block(block)
        if relation.get("relation_id"):
            relations.append(
                {
                    "relation_id": relation["relation_id"],
                    "source_claim": relation.get("source_claim", "").strip("`"),
                    "target_claim": relation.get("target_claim", "").strip("`"),
                    "relation_type": relation.get("relation_type", ""),
                    "rationale": relation.get("rationale", ""),
                }
            )
    return {"claims": claims, "relations": relations}


def _section_between(text: str, start_heading: str, end_heading: str) -> str:
    start = text.find(start_heading)
    if start == -1:
        return ""
    start = text.find("\n", start)
    if start == -1:
        return ""
    end = text.find(end_heading, start)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def _parse_key_value_block(block: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []
    for line in block.splitlines():
        match = re.match(r"^([a-zA-Z_]+):\s*(.*)$", line)
        if match:
            if current_key is not None:
                parsed[current_key] = " ".join(current_value).strip()
            current_key = match.group(1)
            current_value = [match.group(2).strip()]
        elif current_key is not None and line.strip():
            current_value.append(line.strip())
    if current_key is not None:
        parsed[current_key] = " ".join(current_value).strip()
    return parsed


def run_update_exercise(
    repo_root: Path, output_dir: Path, case: dict[str, Any], worked_map: dict[str, Any]
) -> dict[str, Any] | None:
    update = case.get("held_out_update")
    if not update:
        return None
    update_text = _read_text(repo_root / update["update_demo_path"])
    parsed = _parse_update_demo(update_text)
    updated_map = copy.deepcopy(worked_map)
    if update["source_id"] not in updated_map.get("sources", []):
        updated_map.setdefault("sources", []).append(update["source_id"])
    updated_map.setdefault("claims", []).extend(parsed["claims"])
    updated_map.setdefault("relations", []).extend(parsed["relations"])

    existing_claim_ids = {claim["claim_id"] for claim in worked_map.get("claims", [])}
    touched_existing_claim_ids = sorted(
        {
            claim_id
            for relation in parsed["relations"]
            for claim_id in (relation.get("source_claim"), relation.get("target_claim"))
            if claim_id in existing_claim_ids
        }
    )
    added_claim_ids = [claim["claim_id"] for claim in parsed["claims"]]
    added_relation_ids = [relation["relation_id"] for relation in parsed["relations"]]
    unaffected_claim_ids = sorted(existing_claim_ids - set(touched_existing_claim_ids))
    stable_unaffected_ids = _unaffected_claims_stable(worked_map, updated_map, unaffected_claim_ids)

    update_dir = output_dir / "update" / case["case_id"]
    _write_json(update_dir / "before_map_snapshot.json", worked_map)
    _write_json(update_dir / "after_map_snapshot.json", updated_map)

    ledger = {
        "update_id": update["update_id"],
        "new_source_id": update["source_id"],
        "added_claim_ids": added_claim_ids,
        "added_relation_ids": added_relation_ids,
        "touched_existing_claim_ids": touched_existing_claim_ids,
        "unaffected_claim_count": len(unaffected_claim_ids),
        "stable_unaffected_ids": stable_unaffected_ids,
        "all_unaffected_ids_stable": stable_unaffected_ids == unaffected_claim_ids,
    }
    _write_json(update_dir / "affected_object_ledger.json", ledger)

    flat_before = _read_text(repo_root / case["flat_baseline"])
    flat_after = (
        flat_before.rstrip()
        + "\n\n## Held-out public communication update\n\n"
        + "CERN's current public FAQ adds a communication-layer version of the safety case: "
        + "natural phenomena already occur and standard relativity does not produce LHC black holes, "
        + "while speculative microscopic black holes are presented as immediately disintegrating. "
        + "This updates public framing rather than the technical compact-star dependency structure.\n"
    )
    flat_diff = "\n".join(
        difflib.unified_diff(
            flat_before.splitlines(),
            flat_after.splitlines(),
            fromfile="flat_before.md",
            tofile="flat_after.md",
            lineterm="",
        )
    )
    map_diff_lines = [
        "# Held-Out Source Map Diff",
        "",
        f"New source: `{update['source_id']}`",
        "",
        "Added claims:",
        "",
        *(_render_claim(claim, include_excerpt=True) for claim in parsed["claims"]),
        "",
        "Added relations:",
        "",
        *(_render_relation(relation) for relation in parsed["relations"]),
        "",
        f"Touched existing claims: {', '.join(f'`{claim_id}`' for claim_id in touched_existing_claim_ids)}",
    ]
    reader_view = [
        "# Revised Reader View",
        "",
        "The held-out CERN public FAQ adds a public-facing communication layer, not a new technical risk model.",
        "",
        "The revised map should treat the FAQ's natural-phenomena analogy as a compressed version of the existing",
        "cosmic-ray safety argument, while preserving the lower-velocity/trapping dependency and compact-star checks.",
        "",
        "It should also treat the FAQ's immediate-disintegration statement as public synthesis aligned with the",
        "Hawking-radiation branch, while retaining the worked map's caveat that this assumption is not the only",
        "structure supporting the bottom-line safety case.",
    ]
    _write_text(update_dir / "flat_update_diff.md", f"# Flat Update Diff\n\n```diff\n{flat_diff}\n```\n")
    _write_text(update_dir / "map_update_diff.md", "\n".join(map_diff_lines).strip() + "\n")
    _write_text(update_dir / "revised_reader_view.md", "\n".join(reader_view).strip() + "\n")
    return ledger


def _unaffected_claims_stable(
    before: dict[str, Any], after: dict[str, Any], unaffected_claim_ids: list[str]
) -> list[str]:
    before_claims = {claim["claim_id"]: claim for claim in before.get("claims", [])}
    after_claims = {claim["claim_id"]: claim for claim in after.get("claims", [])}
    stable = []
    for claim_id in unaffected_claim_ids:
        if before_claims.get(claim_id) == after_claims.get(claim_id):
            stable.append(claim_id)
    return stable


def _determine_claim_level(case_results: dict[str, Any], mutation: dict[str, Any] | None, update: dict[str, Any] | None) -> str:
    lhc = case_results.get("lhc")
    if not lhc:
        return "mechanical only"
    lhc_gain = lhc["condition_averages"]["map"] > lhc["condition_averages"]["flat"]
    if lhc_gain and mutation and update:
        return "narrow"
    return "mechanical only"


def render_final_packet(
    output_dir: Path,
    manifest: dict[str, Any],
    packet_info: dict[str, Any],
    case_results: dict[str, Any],
    mutation_report: dict[str, Any] | None,
    update_ledger: dict[str, Any] | None,
    claim_level: str,
) -> str:
    lines = [
        "# Investigator Challenge Evidence Packet",
        "",
        f"Challenge: `{manifest['challenge_id']}`",
        f"Mode: `{manifest['default_mode']}`",
        f"Earned claim level: **{claim_level}**",
        "",
        "This packet demonstrates a narrow product claim: the structured map is useful as an investigator handoff and audit surface, not as a prettier prose generator.",
        "",
        "## Capable Baseline Answer",
        "",
        "The flat condition uses checked-in synthesis baselines rather than a deliberately weak summary. Its raw packets are preserved under `inputs/<case>/flat_packet.md`.",
        "",
        "## Adversarial Follow-Up Comparisons",
        "",
        "| case | flat avg | map avg | map + sources avg |",
        "| --- | ---: | ---: | ---: |",
    ]
    for case_id, result in case_results.items():
        averages = result["condition_averages"]
        lines.append(
            f"| {case_id} | {averages['flat']:.3f} | {averages['map']:.3f} | {averages['map_plus_sources']:.3f} |"
        )
    lines.extend(["", "Representative task-level comparisons:", ""])
    for task_id in ("lhc_t001", "lhc_t003", "lhc_t004"):
        task = case_results["lhc"]["tasks"][task_id]
        conditions = task["conditions"]
        lines.extend(
            [
                f"### `{task_id}`",
                "",
                task["question"],
                "",
                f"- flat composite: {conditions['flat']['composite_score']:.3f}",
                f"- map composite: {conditions['map']['composite_score']:.3f}",
                f"- map + sources composite: {conditions['map_plus_sources']['composite_score']:.3f}",
                f"- raw flat response: `{Path(conditions['flat']['response_path']).relative_to(output_dir)}`",
                f"- raw map response: `{Path(conditions['map']['response_path']).relative_to(output_dir)}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Source-Trace Walkthrough",
            "",
            "`lhc_t003` asks for the velocity/trapping transition. The map response names `lhc_c004`, `lhc_c012`, `lhc_r003`, `lhc_r004`, and their source IDs. This is the recoverability surface the flat answer typically hides inside prose.",
            "",
            "## Local Correction Diff",
            "",
        ]
    )
    if mutation_report:
        lines.extend(
            [
                f"- synthetic mutation: `{mutation_report['mutation_id']}`",
                f"- detected: `{mutation_report['detected']}`",
                f"- localized object: `{mutation_report['localized_object_id']}`",
                f"- clean control triggered: `{mutation_report['clean_control_triggered']}`",
                "- diff: `mutation/lhc/repair_diff.md`",
                "",
            ]
        )
    else:
        lines.extend(["No mutation exercise ran.", ""])
    lines.extend(["## Held-Out Source Update", ""])
    if update_ledger:
        lines.extend(
            [
                f"- new source: `{update_ledger['new_source_id']}`",
                f"- added claims: {', '.join(f'`{claim_id}`' for claim_id in update_ledger['added_claim_ids'])}",
                f"- added relations: {', '.join(f'`{relation_id}`' for relation_id in update_ledger['added_relation_ids'])}",
                f"- touched existing claims: {', '.join(f'`{claim_id}`' for claim_id in update_ledger['touched_existing_claim_ids'])}",
                f"- unaffected claim IDs stable: `{update_ledger['all_unaffected_ids_stable']}` ({update_ledger['unaffected_claim_count']} unaffected claims)",
                "- map diff: `update/lhc/map_update_diff.md`",
                "- flat diff: `update/lhc/flat_update_diff.md`",
                "- revised reader view: `update/lhc/revised_reader_view.md`",
                "",
            ]
        )
    else:
        lines.extend(["No update exercise ran.", ""])
    lines.extend(
        [
            "## Metric And Artifact Index",
            "",
            "| artifact | path |",
            "| --- | --- |",
            "| run record | `challenge_run.json` |",
            "| completion audit | `completion_audit.json` |",
        ]
    )
    for case_id in case_results:
        lines.append(f"| {case_id} scoring | `scoring/{case_id}/task_scores.json` |")
        lines.append(f"| {case_id} token report | `inputs/{case_id}/token_budget_report.json` |")
    lines.extend(
        [
            "",
            "## What This Establishes",
            "",
            "- The map condition makes hidden dependencies, source traces, and local updates easier to recover in deterministic replay.",
            "- The held-out source update preserves stable IDs and makes affected objects explicit.",
            "- The demonstration is inspectable: raw prompts, raw responses, score records, packet hashes, mutation reports, and update ledgers are all preserved.",
            "",
            "## What This Does Not Establish",
            "",
            "- It is not a scientific validation study.",
            "- It does not prove the map always beats a strong live research model on prose quality.",
            "- It does not claim human review beyond artifacts explicitly marked for human review.",
        ]
    )
    packet = "\n".join(lines).strip() + "\n"
    _write_text(output_dir / "FINAL_EVIDENCE_PACKET.md", packet)
    _write_text(output_dir / "CHALLENGE_RESULTS.md", _render_overall_results(case_results, claim_level))
    return packet


def _render_overall_results(case_results: dict[str, Any], claim_level: str) -> str:
    lines = [
        "# Investigator Challenge Results",
        "",
        f"Earned claim level: **{claim_level}**",
        "",
        "| case | flat | map | map + sources |",
        "| --- | ---: | ---: | ---: |",
    ]
    for case_id, result in case_results.items():
        averages = result["condition_averages"]
        lines.append(
            f"| {case_id} | {averages['flat']:.3f} | {averages['map']:.3f} | {averages['map_plus_sources']:.3f} |"
        )
    lines.extend(["", "See `FINAL_EVIDENCE_PACKET.md` for judge-facing links and interpretation.", ""])
    return "\n".join(lines)


def build_completion_audit(
    case_results: dict[str, Any],
    mutation_report: dict[str, Any] | None,
    update_ledger: dict[str, Any] | None,
    output_dir: Path,
    claim_level: str,
) -> dict[str, Any]:
    lhc_tasks = case_results.get("lhc", {}).get("tasks", {})
    task_outputs = sum(len(result["tasks"]) for result in case_results.values())
    acceptance = {
        "lhc_vertical_slice_runnable": "lhc" in case_results and bool(lhc_tasks),
        "three_adversarial_questions_scored": len(lhc_tasks) >= 3,
        "semantic_mutation_and_clean_control_evaluated": bool(
            mutation_report
            and mutation_report.get("detected")
            and mutation_report.get("clean_control_triggered") is False
        ),
        "held_out_source_update_has_ledger_and_stable_ids": bool(
            update_ledger and update_ledger.get("all_unaffected_ids_stable")
        ),
        "raw_prompts_outputs_scores_token_counts_preserved": (
            task_outputs > 0
            and (output_dir / "raw").exists()
            and (output_dir / "scoring").exists()
            and (output_dir / "inputs").exists()
        ),
        "judge_evidence_packet_exists": (output_dir / "FINAL_EVIDENCE_PACKET.md").exists(),
        "writeup_reports_earned_claim_level": claim_level in {
            "strong deterministic replay",
            "narrow",
            "mechanical only",
            "negative",
        },
    }
    return {
        "claim_level": claim_level,
        "acceptance_criteria": acceptance,
        "all_plan_acceptance_criteria_met": all(acceptance.values()),
    }


def run_challenge(
    repo_root: Path,
    manifest_path: Path,
    answer_keys_path: Path,
    output_dir: Path,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    start = time.monotonic()
    manifest = _load_yaml(manifest_path)
    answer_keys = _load_json(answer_keys_path)
    errors = validate_references(repo_root, manifest, answer_keys)
    if errors:
        raise ValueError("reference validation failed:\n" + "\n".join(f"- {error}" for error in errors))

    selected = {
        case["case_id"]
        for case in manifest["cases"]
        if case_ids is None or case["case_id"] in set(case_ids)
    }
    if not selected:
        raise ValueError("no cases selected")

    if output_dir.exists():
        for child in sorted(output_dir.glob("*")):
            if child.is_dir():
                _remove_tree(child)
            else:
                child.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)

    packet_info: dict[str, Any] = {}
    case_results: dict[str, Any] = {}
    mutation_report: dict[str, Any] | None = None
    update_ledger: dict[str, Any] | None = None

    print(f"[investigator-challenge] writing artifacts to {output_dir}")
    for case in manifest["cases"]:
        case_id = case["case_id"]
        if case_id not in selected:
            continue
        print(f"[investigator-challenge] building packets for {case_id}")
        worked_map = _load_worked_map(repo_root / case["worked_map"])
        packet_info[case_id] = build_condition_packets(repo_root, output_dir, case, worked_map)
        print(f"[investigator-challenge] scoring follow-up tasks for {case_id}")
        case_keys = _case_answer_keys(answer_keys, case_id)
        case_results[case_id] = run_followup_tasks(repo_root, output_dir, case, worked_map, case_keys)
        if case_id == "lhc":
            print("[investigator-challenge] running LHC mutation exercise")
            mutation_report = run_mutation_exercise(output_dir, case, worked_map)
            print("[investigator-challenge] running LHC held-out-source update")
            update_ledger = run_update_exercise(repo_root, output_dir, case, worked_map)

    claim_level = _determine_claim_level(case_results, mutation_report, update_ledger)
    render_final_packet(output_dir, manifest, packet_info, case_results, mutation_report, update_ledger, claim_level)
    audit = build_completion_audit(case_results, mutation_report, update_ledger, output_dir, claim_level)
    _write_json(output_dir / "completion_audit.json", audit)

    run_record = {
        "schema_id": "investigator_challenge_run_v1",
        "challenge_id": manifest["challenge_id"],
        "mode": manifest["default_mode"],
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "answer_keys_path": str(answer_keys_path),
        "answer_keys_sha256": _sha256(answer_keys_path),
        "selected_cases": sorted(selected),
        "packet_info": packet_info,
        "case_results": case_results,
        "mutation_report_path": str(output_dir / "mutation" / "lhc" / "mutation_report.json")
        if mutation_report
        else None,
        "update_ledger_path": str(output_dir / "update" / "lhc" / "affected_object_ledger.json")
        if update_ledger
        else None,
        "claim_level": claim_level,
        "completion_audit_path": str(output_dir / "completion_audit.json"),
    }
    _write_json(output_dir / "challenge_run.json", run_record)
    print(f"[investigator-challenge] done; claim level: {claim_level}")
    return run_record


def _remove_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            _remove_tree(child)
        else:
            child.unlink()
    path.rmdir()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(_repo_root()))
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--answer-keys", default=DEFAULT_ANSWER_KEYS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--case", action="append", dest="cases", help="Run one case; may be repeated.")
    parser.add_argument("--all", action="store_true", help="Run every manifest case.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    manifest_path = (repo_root / args.manifest).resolve()
    answer_keys_path = (repo_root / args.answer_keys).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    case_ids = None if args.all else args.cases
    run_challenge(repo_root, manifest_path, answer_keys_path, output_dir, case_ids=case_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
