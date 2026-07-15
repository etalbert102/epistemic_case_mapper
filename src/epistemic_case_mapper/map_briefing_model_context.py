from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json


def write_model_context_audit(
    path: Path,
    *,
    backend: str,
    legacy_prompt: str,
    section_packets_path: Path | None,
    reader_rewrite_prompt: str,
    active_prompts: dict[str, str] | None = None,
    active_prompt_paths: dict[str, Path | None] | None = None,
    prompt_artifact_root: Path | None = None,
) -> Path:
    write_json(
        path,
        build_model_context_audit(
            backend=backend,
            legacy_prompt=legacy_prompt,
            section_packets_path=section_packets_path,
            reader_rewrite_prompt=reader_rewrite_prompt,
            active_prompts=active_prompts,
            active_prompt_paths=active_prompt_paths,
            prompt_artifact_root=prompt_artifact_root,
        ),
    )
    return path


def build_model_context_audit(
    *,
    backend: str,
    legacy_prompt: str,
    section_packets_path: Path | None,
    reader_rewrite_prompt: str,
    active_prompts: dict[str, str] | None = None,
    active_prompt_paths: dict[str, Path | None] | None = None,
    prompt_artifact_root: Path | None = None,
) -> dict[str, Any]:
    prompt_backend = backend.strip() == "prompt"
    section_records = _section_context_records(section_packets_path)
    active_records = _active_prompt_records(
        active_prompts=active_prompts or {},
        active_prompt_paths=active_prompt_paths or {},
        prompt_backend=prompt_backend,
    )
    upstream_inventory = build_model_call_context_inventory(prompt_artifact_root, prompt_backend=prompt_backend)
    return {
        "schema_id": "model_context_audit_v1",
        "backend": backend,
        "stages": [
            _prompt_record(
                "whole_briefing_legacy_prompt",
                legacy_prompt,
                status="record_only_legacy_prompt",
                sent_to_model=False,
                note="Retained as a compatibility/debug artifact; section-first synthesis is the active path.",
            ),
            {
                "stage": "section_rewrite",
                "status": "record_only_prompt_backend" if prompt_backend else "active_model_calls",
                "sent_to_model": not prompt_backend,
                "section_count": len(section_records),
                "sections": section_records,
            },
            {
                "stage": "active_model_prompts",
                "status": "record_only_prompt_backend" if prompt_backend else "audited",
                "sent_to_model": not prompt_backend,
                "prompt_count": len(active_records),
                "polluted_prompt_count": sum(1 for row in active_records if row.get("pollution_flags")),
                "oversized_prompt_count": sum(1 for row in active_records if "oversized_model_context" in row.get("pollution_flags", [])),
                "prompts": active_records,
            },
            {
                "stage": "upstream_model_call_inventory",
                "status": "record_only_prompt_backend" if prompt_backend else "audited",
                "sent_to_model": not prompt_backend,
                "prompt_count": len(upstream_inventory),
                "polluted_prompt_count": sum(1 for row in upstream_inventory if row.get("pollution_flags")),
                "oversized_prompt_count": sum(1 for row in upstream_inventory if "oversized_model_context" in row.get("pollution_flags", [])),
                "prompts": upstream_inventory,
            },
            _prompt_record(
                "reader_memo_edit_suggestions",
                reader_rewrite_prompt,
                status="active_model_call" if reader_rewrite_prompt.strip() and not prompt_backend else "not_run",
                sent_to_model=bool(reader_rewrite_prompt.strip()) and not prompt_backend,
                note="Optional exact-edit suggestion pass; deterministic code applies only safe replacements.",
                extra={
                    "pollution_flags": _reader_rewrite_prompt_pollution_flags(reader_rewrite_prompt),
                    "context_policy": "Final memo editors should receive memo text, protected spans, and pass-specific diagnostics; broad scaffold records should stay validator-only.",
                },
            ),
        ],
        "policy": {
            "model_context": "Only compact task-specific packets should be sent to model calls.",
            "debug_records": "Full packets, prompts, raw outputs, and validation reports remain artifact-facing records.",
            "negative_context": "Model-facing prohibition rules should avoid including facts the model should not mention.",
            "active_prompt_audit": "Prompt records flag stage-inappropriate debug fields in report-only mode; stable evidence IDs are allowed when the model must return structured references.",
            "upstream_prompt_inventory": "Upstream prompt artifacts should be inventoried by path so extraction, relation, source appraisal, and source weighting calls are visible in run artifacts.",
        },
    }


def build_model_call_context_inventory(root: Path | None, *, prompt_backend: bool = False) -> list[dict[str, Any]]:
    if root is None or not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*_prompt.txt")):
        stage = _prompt_artifact_stage(path)
        if not stage:
            continue
        prompt = _read_prompt_path(path)
        if not prompt.strip():
            continue
        records.append(_upstream_prompt_record(stage, prompt, path=path, sent_to_model=not prompt_backend))
    direct_prompts = {
        "map_quality_repair": root / "map_quality_repair_prompt.txt",
    }
    for stage, path in direct_prompts.items():
        if not path.exists():
            continue
        prompt = _read_prompt_path(path)
        if prompt.strip():
            records.append(_upstream_prompt_record(stage, prompt, path=path, sent_to_model=not prompt_backend))
    return records


def _prompt_artifact_stage(path: Path) -> str:
    parts = set(path.parts)
    name = path.name
    if "claim_sources" in parts and name.endswith("_repair_prompt.txt"):
        return "source_claim_schema_repair"
    if "claim_sources" in parts and name.endswith("_prompt.txt"):
        return "source_claim_extraction"
    if "claim_consolidation_clusters" in parts:
        return "claim_consolidation"
    if "relation_pairs" in parts:
        return "relation_pair_classification"
    if "relation_batches" in parts:
        return "relation_batch_classification"
    if "map_repair_relations" in parts:
        return "relation_repair_pair"
    return ""


def _upstream_prompt_record(stage: str, prompt: str, *, path: Path, sent_to_model: bool) -> dict[str, Any]:
    return {
        **_active_prompt_record(stage, prompt, sent_to_model=sent_to_model, path=path),
        "context_scope": _context_scope(stage),
        "decision_question_present": "decision question" in prompt.lower(),
        "source_id_policy": _source_id_policy(stage),
    }


def _context_scope(stage: str) -> str:
    if stage in {"source_claim_extraction", "source_claim_schema_repair", "source_appraisal", "source_weighting"}:
        return "source_local"
    if stage in {"relation_pair_classification", "relation_repair_pair"}:
        return "pair_local"
    if stage == "relation_batch_classification":
        return "small_batch_local"
    if stage == "claim_consolidation":
        return "cluster_local"
    return "global_or_repair"


def _source_id_policy(stage: str) -> str:
    if stage.startswith("source_"):
        return "single_source_id_required"
    if stage.startswith("relation_"):
        return "claim_ids_and_source_ids_must_be_preserved"
    return "preserve_supplied_ids"


def _active_prompt_records(
    *,
    active_prompts: dict[str, str],
    active_prompt_paths: dict[str, Path | None],
    prompt_backend: bool,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for stage, prompt in sorted(active_prompts.items()):
        text = str(prompt or "")
        if not text.strip():
            continue
        records.append(_active_prompt_record(stage, text, sent_to_model=not prompt_backend))
        seen.add(stage)
    for stage, path in sorted(active_prompt_paths.items()):
        if stage in seen or path is None:
            continue
        text = _read_prompt_path(path)
        if not text.strip():
            continue
        records.append(_active_prompt_record(stage, text, sent_to_model=not prompt_backend, path=path))
    return records


def _active_prompt_record(stage: str, prompt: str, *, sent_to_model: bool, path: Path | None = None) -> dict[str, Any]:
    flags = _active_prompt_pollution_flags(stage, prompt)
    return {
        "stage": stage,
        "sent_to_model": sent_to_model,
        "prompt_chars": len(prompt),
        "prompt_words": len(prompt.split()),
        "approx_tokens": max(1, len(prompt) // 4),
        "path": str(path) if path else None,
        "pollution_flags": flags,
        "field_hits": _field_hits(prompt),
    }


def _read_prompt_path(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


def _active_prompt_pollution_flags(stage: str, prompt: str) -> list[str]:
    text = prompt.lower()
    flags: list[str] = []
    if len(prompt) > 120_000:
        flags.append("oversized_model_context")
    if len(prompt) > 80_000 and any(name in stage for name in ("quantity", "repair", "polish", "synthesis")):
        flags.append("stage_context_likely_too_broad")
    if "excluded_evidence_log" in text or "lineage_report" in text:
        flags.append("writer_debug_record_visible")
    if "packet_sufficiency_report" in text or "packet_critique_adjudication_report" in text:
        flags.append("validator_report_visible")
    if "skipped_prompt_backend" in text:
        flags.append("skipped_backend_report_visible")
    if "deterministic_memo_use" in text or "deterministic_warnings" in text:
        flags.append("deterministic_judgment_label_visible")
    if '"legacy_' in text or "legacy mandatory" in text:
        flags.append("legacy_compatibility_payload_visible")
    if "raw output" in text or '"raw"' in text or "raw_" in text:
        flags.append("raw_or_debug_language_visible")
    if _polarity_context_missing(text):
        flags.append("answer_frame_context_missing_for_polarity_labels")
    return list(dict.fromkeys(flags))


def _polarity_context_missing(text: str) -> bool:
    polarity_terms = (
        "load_bearing_primary_support",
        "load_bearing_counterweight",
        "supports_answer",
        "challenges_answer",
        "answer_relation",
    )
    if not any(term in text for term in polarity_terms):
        return False
    answer_frame_terms = (
        "stable_final_answer_frame",
        "balanced_answer_frame",
        "classification_target_policy",
        "current_best_answer",
        "no final-answer polarity",
        "do not infer support",
    )
    return not any(term in text for term in answer_frame_terms)


def _field_hits(prompt: str) -> dict[str, int]:
    text = prompt.lower()
    fields = (
        "deterministic_memo_use",
        "deterministic_warnings",
        "excluded_evidence_log",
        "lineage_report",
        "packet_sufficiency_report",
        "packet_critique_adjudication_report",
        "skipped_prompt_backend",
        "legacy_mandatory_items",
        "raw",
        "source_excerpt",
        "local_quantity_context",
    )
    return {field: text.count(field) for field in fields if text.count(field)}


def _prompt_record(
    stage: str,
    prompt: str,
    *,
    status: str,
    sent_to_model: bool,
    note: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "stage": stage,
        "status": status,
        "sent_to_model": sent_to_model,
        "prompt_chars": len(prompt),
        "prompt_words": len(prompt.split()),
        "approx_tokens": max(1, len(prompt) // 4) if prompt else 0,
        "note": note,
    }
    if extra:
        record.update(extra)
    return record


def _section_context_records(section_packets_path: Path | None) -> list[dict[str, Any]]:
    if not section_packets_path or not section_packets_path.exists():
        return []
    try:
        payload = json.loads(section_packets_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    records: list[dict[str, Any]] = []
    for packet in payload.get("packets", []) if isinstance(payload.get("packets"), list) else []:
        if isinstance(packet, dict):
            records.append(_section_context_record(packet))
    return records


def _section_context_record(packet: dict[str, Any]) -> dict[str, Any]:
    debug_packet = packet.get("packet", {}) if isinstance(packet.get("packet"), dict) else {}
    model_packet = packet.get("model_packet", {}) if isinstance(packet.get("model_packet"), dict) else {}
    debug_text = json.dumps(debug_packet, ensure_ascii=False, sort_keys=True)
    model_text = json.dumps(model_packet, ensure_ascii=False, sort_keys=True)
    ratio = round(len(model_text) / len(debug_text), 3) if debug_text and debug_text != "{}" else None
    return {
        "title": packet.get("title"),
        "has_model_packet": bool(model_packet),
        "debug_packet_chars": len(debug_text),
        "model_packet_chars": len(model_text),
        "model_to_debug_char_ratio": ratio,
        "model_packet_keys": sorted(model_packet.keys()),
        "debug_packet_keys": sorted(debug_packet.keys()),
        "pollution_flags": _model_packet_pollution_flags(model_packet),
    }


def _model_packet_pollution_flags(model_packet: dict[str, Any]) -> list[str]:
    text = json.dumps(model_packet, ensure_ascii=False, sort_keys=True).lower()
    flags: list[str] = []
    if "section_synthesis_packet" in text:
        flags.append("debug_packet_name_visible")
    if "anchor_terms_to_avoid_repeating" in text:
        flags.append("negative_anchor_terms_visible")
    if re.search(r"\b(?:claim|relation|source)_id\b", text):
        flags.append("raw_identifier_field_visible")
    if re.search(r"\b(?:raw_|debug_|_section_synthesis|section_synthesis_packet)", text):
        flags.append("internal_identifier_language_visible")
    return flags


def _reader_rewrite_prompt_pollution_flags(prompt: str) -> list[str]:
    """Flag broad scaffold/debug context that should not be model-visible to final editors."""
    text = prompt.lower()
    flags: list[str] = []
    broad_contract_fields = {
        "answer_frame": "answer_frame_visible",
        "decision_frame": "decision_frame_visible",
        "option_comparison": "option_comparison_visible",
        "practical_actions": "practical_actions_visible",
        "required_evidence": "required_evidence_visible",
        "required_gaps": "required_gaps_visible",
        "required_cruxes": "required_cruxes_visible",
        "decision_memo_slots": "slot_model_visible",
        "section_synthesis_packet": "section_packet_visible",
        "model_section_packet": "section_model_packet_visible",
    }
    for field, flag in broad_contract_fields.items():
        if f'"{field}"' in text or field in text:
            flags.append(flag)
    if "evidence contract:" in text and any(flag.endswith("_visible") for flag in flags):
        flags.append("broad_evidence_contract_visible")
    if "anchor_terms_to_avoid_repeating" in text:
        flags.append("negative_anchor_terms_visible")
    if re.search(r"\b(?:claim|relation|source)_id\b", text):
        flags.append("raw_identifier_field_visible")
    if re.search(r"\b(?:raw_|debug_|_section_synthesis|section_synthesis_packet)", text):
        flags.append("internal_identifier_language_visible")
    return list(dict.fromkeys(flags))
