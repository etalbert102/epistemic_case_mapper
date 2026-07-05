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
    global_plan_prompt: str,
    section_packets_path: Path | None,
    reader_rewrite_prompt: str,
) -> Path:
    write_json(
        path,
        build_model_context_audit(
            backend=backend,
            legacy_prompt=legacy_prompt,
            global_plan_prompt=global_plan_prompt,
            section_packets_path=section_packets_path,
            reader_rewrite_prompt=reader_rewrite_prompt,
        ),
    )
    return path


def build_model_context_audit(
    *,
    backend: str,
    legacy_prompt: str,
    global_plan_prompt: str,
    section_packets_path: Path | None,
    reader_rewrite_prompt: str,
) -> dict[str, Any]:
    prompt_backend = backend.strip() == "prompt"
    section_records = _section_context_records(section_packets_path)
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
            _prompt_record(
                "global_memo_plan",
                global_plan_prompt,
                status="record_only_prompt_backend" if prompt_backend else "active_model_call",
                sent_to_model=not prompt_backend,
                note="Model plans memo architecture; deterministic fallback is used for prompt backend or parse failure.",
            ),
            {
                "stage": "section_rewrite",
                "status": "record_only_prompt_backend" if prompt_backend else "active_model_calls",
                "sent_to_model": not prompt_backend,
                "section_count": len(section_records),
                "sections": section_records,
            },
            _prompt_record(
                "reader_memo_edit_suggestions",
                reader_rewrite_prompt,
                status="active_model_call" if reader_rewrite_prompt.strip() and not prompt_backend else "not_run",
                sent_to_model=bool(reader_rewrite_prompt.strip()) and not prompt_backend,
                note="Optional exact-edit suggestion pass; deterministic code applies only safe replacements.",
            ),
        ],
        "policy": {
            "model_context": "Only compact task-specific packets should be sent to model calls.",
            "debug_records": "Full packets, prompts, raw outputs, and validation reports remain artifact-facing records.",
            "negative_context": "Model-facing prohibition rules should avoid including facts the model should not mention.",
        },
    }


def _prompt_record(stage: str, prompt: str, *, status: str, sent_to_model: bool, note: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "sent_to_model": sent_to_model,
        "prompt_chars": len(prompt),
        "prompt_words": len(prompt.split()),
        "approx_tokens": max(1, len(prompt) // 4) if prompt else 0,
        "note": note,
    }


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
