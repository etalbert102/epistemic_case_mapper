from __future__ import annotations

from typing import Any, Callable

from epistemic_case_mapper.map_briefing_analyst_evidence_ledger import build_analyst_map_evidence_ledger
from epistemic_case_mapper.map_briefing_decision_packet import build_decision_briefing_packet_bundle
from epistemic_case_mapper.map_briefing_memo_warning_packet import build_memo_warning_packet
from epistemic_case_mapper.map_briefing_packet_refinement import run_packet_critique_and_refinement
from epistemic_case_mapper.map_briefing_role_adjudication import adjudicate_packet_roles
from epistemic_case_mapper.map_briefing_source_bottom_lines import build_source_bottom_line_cards


def attach_decision_briefing_packet(
    prioritized_map: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    question: str,
    backend_config: Any,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None = None,
) -> None:
    from epistemic_case_mapper.map_briefing_readiness import build_packet_quality_gate_report

    _progress(progress, "source_bottom_lines", "started")
    scaffold["source_bottom_line_cards"] = build_source_bottom_line_cards(prioritized_map, scaffold)
    _progress(progress, "source_bottom_lines", "completed", {"card_count": _card_count(scaffold.get("source_bottom_line_cards"))})

    _progress(progress, "packet_assembly", "started")
    scaffold.update(build_decision_briefing_packet_bundle(scaffold, question=question))
    packet = scaffold.get("decision_briefing_packet", {}) if isinstance(scaffold.get("decision_briefing_packet"), dict) else {}
    _progress(progress, "packet_assembly", "completed", _packet_assembly_details(packet, scaffold))

    scaffold.update(
        run_packet_critique_and_refinement(
            packet,
            scaffold.get("packet_sufficiency_report", {}) if isinstance(scaffold.get("packet_sufficiency_report"), dict) else {},
            backend=backend_config.backend,
            backend_timeout=backend_config.timeout,
            backend_retries=backend_config.retries,
            progress=progress,
        )
    )

    _progress(progress, "role_adjudication", "started")
    adjudicated_packet, role_adjudication = adjudicate_packet_roles(
        scaffold.get("decision_briefing_packet", {}) if isinstance(scaffold.get("decision_briefing_packet"), dict) else {}
    )
    scaffold["decision_briefing_packet"] = adjudicated_packet
    scaffold["packet_role_adjudication_report"] = role_adjudication
    scaffold["role_conflict_candidates"] = {"schema_id": "role_conflict_candidates_v1", "candidates": role_adjudication.get("role_conflict_candidates", [])}
    _progress(progress, "role_adjudication", "completed", {"candidate_count": _list_count(role_adjudication.get("role_conflict_candidates"))})

    _progress(progress, "packet_quality_gate", "started")
    scaffold["packet_quality_gate_report"] = build_packet_quality_gate_report(scaffold)
    _progress(progress, "packet_quality_gate", "completed", {"issue_count": _list_count(scaffold["packet_quality_gate_report"].get("issues"))})

    packet = scaffold.get("decision_briefing_packet")
    if isinstance(packet, dict):
        _attach_analyst_packet_flow(prioritized_map, scaffold, packet=packet, question=question, backend_config=backend_config, progress=progress)


def _attach_analyst_packet_flow(
    prioritized_map: dict[str, Any],
    scaffold: dict[str, Any],
    *,
    packet: dict[str, Any],
    question: str,
    backend_config: Any,
    progress: Callable[[str, str, dict[str, Any] | None], None] | None,
) -> None:
    _progress(progress, "warning_packet", "started")
    packet["synthesis_warning_inputs"] = _synthesis_warning_inputs(scaffold)
    scaffold["memo_warning_packet"] = build_memo_warning_packet(packet)
    _progress(progress, "warning_packet", "completed")

    _progress(progress, "analyst_ledger", "started")
    scaffold["analyst_evidence_ledger"] = build_analyst_map_evidence_ledger(
        prioritized_map,
        scaffold,
        question=question,
        memo_warning_packet=scaffold["memo_warning_packet"],
    )
    ledger = scaffold.get("analyst_evidence_ledger", {})
    _progress(progress, "analyst_ledger", "completed", {"row_count": _ledger_row_count(ledger)})
    if not isinstance(ledger, dict):
        return

    _run_analyst_adjudication(scaffold, ledger, backend_config=backend_config, progress=progress)
    _run_analyst_decision_model(scaffold, ledger, backend_config=backend_config, progress=progress)
    _run_analyst_packet_builders(scaffold, packet, ledger, backend_config=backend_config, progress=progress)


def _run_analyst_adjudication(scaffold: dict[str, Any], ledger: dict[str, Any], *, backend_config: Any, progress: Callable[[str, str, dict[str, Any] | None], None] | None) -> None:
    from epistemic_case_mapper.map_briefing_analyst_adjudication import run_analyst_adjudication

    _progress(progress, "analyst_adjudication", "started", {"row_count": _ledger_row_count(ledger)})
    scaffold.update(
        run_analyst_adjudication(
            ledger,
            backend=backend_config.backend,
            backend_timeout=backend_config.timeout,
            backend_retries=backend_config.retries,
        )
    )
    _progress(progress, "analyst_adjudication", "completed", _report_status(scaffold, "analyst_adjudication_report") | {"chunk_count": _chunk_count(scaffold)})


def _run_analyst_decision_model(scaffold: dict[str, Any], ledger: dict[str, Any], *, backend_config: Any, progress: Callable[[str, str, dict[str, Any] | None], None] | None) -> None:
    from epistemic_case_mapper.map_briefing_analyst_decision_modeling import run_analyst_decision_model
    from epistemic_case_mapper.map_briefing_decision_writer_packet import build_decision_writer_packet_bundle
    from epistemic_case_mapper.map_briefing_global_decision_model import build_global_decision_model_bundle

    _progress(progress, "analyst_decision_model", "started", {"row_count": _ledger_row_count(ledger)})
    scaffold.update(
        run_analyst_decision_model(
            ledger=ledger,
            adjudication=scaffold.get("analyst_adjudication", {}),
            backend=backend_config.backend,
            backend_timeout=backend_config.timeout,
            backend_retries=backend_config.retries,
        )
    )
    _progress(progress, "analyst_decision_model", "completed", _analyst_decision_model_details(scaffold))
    _progress(progress, "global_decision_model", "started")
    scaffold.update(
        build_global_decision_model_bundle(
            ledger=ledger,
            analyst_decision_model=scaffold.get("analyst_decision_model", {}),
            analyst_decision_model_report=scaffold.get("analyst_decision_model_report", {}),
            analyst_decision_model_parse_report=scaffold.get("analyst_decision_model_parse_report", {}),
            parallel_report=scaffold.get("analyst_decision_model_parallel_report", {}),
            evidence_routing_report=scaffold.get("evidence_routing_report", {}),
            deferred_evidence_audit=scaffold.get("deferred_evidence_audit", {}),
        )
    )
    _progress(progress, "global_decision_model", "completed", _report_status(scaffold, "global_decision_model_report"))
    _progress(progress, "decision_writer_packet", "started")
    scaffold.update(
        build_decision_writer_packet_bundle(
            global_decision_model=scaffold.get("global_decision_model", {}),
            ledger=ledger,
        )
    )
    _progress(progress, "decision_writer_packet", "completed", _report_status(scaffold, "decision_writer_packet_quality_report"))


def _run_analyst_packet_builders(scaffold: dict[str, Any], packet: dict[str, Any], ledger: dict[str, Any], *, backend_config: Any, progress: Callable[[str, str, dict[str, Any] | None], None] | None) -> None:
    from epistemic_case_mapper.map_briefing_analyst_packet import build_analyst_packet_bundle
    from epistemic_case_mapper.map_briefing_analyst_quantity_binding import run_analyst_quantity_binding
    from epistemic_case_mapper.map_briefing_decision_usefulness import (
        attach_decision_usefulness_to_packet,
        build_decision_usefulness_inventory_report,
        run_decision_usefulness_builder,
    )
    from epistemic_case_mapper.map_briefing_lightweight_guidance import (
        attach_lightweight_guidance_to_packet,
        run_lightweight_writer_guidance,
    )
    from epistemic_case_mapper.map_briefing_model_source_weighting import (
        attach_model_source_weighting_to_packet,
        run_model_source_weight_judgments,
    )
    from epistemic_case_mapper.map_briefing_source_id_projection import project_memo_ready_packet_source_ids

    _progress(progress, "analyst_packet_bundle", "started")
    scaffold.update(build_analyst_packet_bundle(packet=packet, ledger=ledger, adjudication=scaffold.get("analyst_adjudication", {}), decision_model=scaffold.get("analyst_decision_model", {}), memo_warning_packet=scaffold.get("memo_warning_packet", {})))
    _progress(progress, "analyst_packet_bundle", "completed")

    _progress(progress, "analyst_packet_refinement", "started")
    if _decision_writer_packet_ready(scaffold.get("decision_writer_packet"), scaffold.get("decision_writer_packet_quality_report")):
        scaffold.update(_skipped_analyst_packet_refinement_bundle())
    else:
        from epistemic_case_mapper.map_briefing_analyst_refinement import run_analyst_packet_refinement

        scaffold.update(
            run_analyst_packet_refinement(
                synthesis_packet=scaffold.get("analyst_synthesis_packet", {}),
                warning_packet=scaffold.get("memo_warning_packet", {}),
                backend=backend_config.backend,
                backend_timeout=backend_config.timeout,
                backend_retries=backend_config.retries,
            )
        )
    _progress(progress, "analyst_packet_refinement", "completed", _report_status(scaffold, "analyst_packet_refinement_report"))

    _progress(progress, "analyst_quantity_binding", "started")
    scaffold.update(
        run_analyst_quantity_binding(
            synthesis_packet=scaffold.get("analyst_synthesis_packet", {}),
            ledger=ledger,
            backend=backend_config.backend,
            backend_timeout=backend_config.timeout,
            backend_retries=backend_config.retries,
        )
    )
    _progress(progress, "analyst_quantity_binding", "completed", _report_status(scaffold, "analyst_quantity_binding_report"))

    _progress(progress, "analyst_packet_finalization", "started")
    scaffold.update(
        build_analyst_packet_bundle(
            packet=packet,
            ledger=ledger,
            adjudication=scaffold.get("analyst_adjudication", {}),
            decision_model=scaffold.get("analyst_decision_model", {}),
            memo_warning_packet=scaffold.get("memo_warning_packet", {}),
            refinement=scaffold.get("analyst_packet_refinement", {}),
            quantity_binding=scaffold.get("analyst_quantity_binding_report", {}),
        )
    )
    _promote_analyst_packet_as_active(scaffold)
    memo_ready = scaffold.get("memo_ready_packet")
    if isinstance(memo_ready, dict):
        _progress(progress, "source_id_projection", "started")
        scaffold["memo_ready_packet"] = project_memo_ready_packet_source_ids(memo_ready)
        scaffold["source_identity_projection"] = scaffold["memo_ready_packet"].get("source_identity_projection", {})
        _progress(progress, "source_id_projection", "completed", _report_status(scaffold, "source_identity_projection"))
    memo_ready = scaffold.get("memo_ready_packet")
    canonical = memo_ready.get("canonical_decision_writer_packet", {}) if isinstance(memo_ready, dict) else {}
    scaffold["decision_usefulness_inventory_report"] = build_decision_usefulness_inventory_report(
        canonical_packet=canonical if isinstance(canonical, dict) else {},
        scaffold=scaffold,
    )
    _progress(progress, "decision_usefulness", "started")
    decision_usefulness_bundle = run_decision_usefulness_builder(
        canonical_packet=canonical if isinstance(canonical, dict) else {},
        backend=backend_config.backend,
        backend_timeout=backend_config.timeout,
        backend_retries=backend_config.retries,
    )
    scaffold.update(decision_usefulness_bundle)
    if isinstance(memo_ready, dict):
        scaffold["memo_ready_packet"] = attach_decision_usefulness_to_packet(memo_ready, decision_usefulness_bundle)
    memo_ready = scaffold.get("memo_ready_packet")
    canonical = memo_ready.get("canonical_decision_writer_packet", {}) if isinstance(memo_ready, dict) else {}
    _progress(progress, "decision_usefulness", "completed", _report_status(scaffold, "decision_usefulness_report"))

    _progress(progress, "model_source_weighting", "started")
    source_weighting_bundle = run_model_source_weight_judgments(
        memo_ready if isinstance(memo_ready, dict) else {},
        backend=backend_config.backend,
        backend_timeout=backend_config.timeout,
        backend_retries=backend_config.retries,
    )
    scaffold.update(source_weighting_bundle)
    if isinstance(memo_ready, dict):
        scaffold["memo_ready_packet"] = attach_model_source_weighting_to_packet(memo_ready, source_weighting_bundle)
    memo_ready = scaffold.get("memo_ready_packet")
    canonical = memo_ready.get("canonical_decision_writer_packet", {}) if isinstance(memo_ready, dict) else {}
    _progress(progress, "model_source_weighting", "completed", _report_status(scaffold, "model_source_weighting_report"))

    _progress(progress, "lightweight_writer_guidance", "started")
    guidance_bundle = run_lightweight_writer_guidance(
        canonical_packet=canonical if isinstance(canonical, dict) else {},
        scaffold=scaffold,
        backend=backend_config.backend,
        backend_timeout=backend_config.timeout,
        backend_retries=backend_config.retries,
    )
    scaffold.update(guidance_bundle)
    if isinstance(memo_ready, dict):
        scaffold["memo_ready_packet"] = attach_lightweight_guidance_to_packet(memo_ready, guidance_bundle)
    _progress(progress, "lightweight_writer_guidance", "completed", _report_status(scaffold, "lightweight_writer_guidance_report"))
    _progress(progress, "analyst_packet_finalization", "completed", _report_status(scaffold, "active_memo_ready_packet_report"))


def _skipped_analyst_packet_refinement_bundle() -> dict[str, Any]:
    reason = "decision_writer_packet_ready_for_active_memo_packet"
    return {
        "analyst_packet_refinement": {},
        "analyst_packet_refinement_prompt": "",
        "analyst_packet_refinement_raw": "",
        "analyst_packet_refinement_parse_report": {
            "schema_id": "analyst_packet_refinement_parse_report_v1",
            "status": "skipped",
            "reason": reason,
        },
        "analyst_packet_refinement_report": {
            "schema_id": "analyst_packet_refinement_report_v1",
            "status": "skipped",
            "reason": reason,
            "active_path": "decision_writer_packet",
        },
    }


def _promote_analyst_packet_as_active(scaffold: dict[str, Any]) -> None:
    if _promote_decision_writer_packet_as_active(scaffold):
        return
    analyst_packet = scaffold.get("analyst_memo_ready_packet")
    if not isinstance(analyst_packet, dict) or not analyst_packet.get("evidence_items"):
        scaffold["active_memo_ready_packet_report"] = {
            "schema_id": "active_memo_ready_packet_report_v1",
            "status": "missing_active_packet",
            "active_packet": "memo_ready_packet",
            "reason": "analyst_memo_ready_packet_missing_or_empty",
        }
        return
    analyst_quality = scaffold.get("analyst_packet_quality_report")
    scaffold["memo_ready_packet"] = analyst_packet
    if isinstance(analyst_quality, dict):
        scaffold["memo_ready_packet_quality_report"] = {**analyst_quality, "active_packet": "memo_ready_packet"}
    scaffold["active_memo_ready_packet_report"] = {
        "schema_id": "active_memo_ready_packet_report_v1",
        "status": "analyst_active",
        "active_packet": "memo_ready_packet",
        "method": str(analyst_packet.get("method") or "analyst_adjudicated_packet_adapter"),
        "evidence_item_count": _list_count(analyst_packet.get("evidence_items")),
        "source_trail_count": _list_count(analyst_packet.get("source_trail")),
        "downgraded_evidence_item_ids": _analyst_downgraded_evidence_ids(scaffold),
    }


def _promote_decision_writer_packet_as_active(scaffold: dict[str, Any]) -> bool:
    from epistemic_case_mapper.map_briefing_decision_writer_packet import decision_writer_packet_to_memo_ready_packet

    writer_packet = scaffold.get("decision_writer_packet")
    quality = scaffold.get("decision_writer_packet_quality_report")
    if not _decision_writer_packet_ready(writer_packet, quality):
        return False
    memo_ready = decision_writer_packet_to_memo_ready_packet(
        writer_packet if isinstance(writer_packet, dict) else {},
        quality_report=quality if isinstance(quality, dict) else {},
        analyst_adjudication=scaffold.get("analyst_adjudication") if isinstance(scaffold.get("analyst_adjudication"), dict) else {},
        analyst_decision_model=scaffold.get("analyst_decision_model") if isinstance(scaffold.get("analyst_decision_model"), dict) else {},
        analyst_quantity_binding_report=scaffold.get("analyst_quantity_binding_report") if isinstance(scaffold.get("analyst_quantity_binding_report"), dict) else {},
        global_decision_model=scaffold.get("global_decision_model") if isinstance(scaffold.get("global_decision_model"), dict) else {},
        writer_guidance_packet=scaffold.get("writer_guidance_packet") if isinstance(scaffold.get("writer_guidance_packet"), dict) else {},
    )
    scaffold["memo_ready_packet"] = memo_ready
    scaffold["decision_obligation_plan"] = memo_ready.get("decision_obligation_plan", {})
    scaffold["decision_obligation_plan_report"] = {
        "schema_id": "decision_obligation_plan_report_v1",
        "status": "ready" if not memo_ready.get("decision_obligation_plan", {}).get("fallback_requests") else "warning",
        "level_counts": memo_ready.get("decision_obligation_plan", {}).get("level_counts", {}),
        "memo_function_counts": memo_ready.get("decision_obligation_plan", {}).get("memo_function_counts", {}),
        "fallback_request_count": len(memo_ready.get("decision_obligation_plan", {}).get("fallback_requests", [])),
        "conflict_count": len(memo_ready.get("decision_obligation_plan", {}).get("conflicts", [])),
    }
    scaffold["decision_memo_contract"] = memo_ready.get("decision_memo_contract", {})
    scaffold["decision_contract_source_judgment_lineage"] = memo_ready.get("decision_contract_source_judgment_lineage", {})
    scaffold["writer_packet_writeability_report"] = memo_ready.get("writer_packet_writeability_report", {})
    scaffold["writer_packet_fallback_requests"] = {
        "schema_id": "writer_packet_fallback_requests_v1",
        "requests": memo_ready.get("writer_packet_fallback_requests", []),
    }
    scaffold["quantity_obligation_plan"] = memo_ready.get("quantity_obligation_plan", {})
    scaffold["memo_ready_packet_quality_report"] = {
        **(quality if isinstance(quality, dict) else {}),
        "active_packet": "memo_ready_packet",
        "active_packet_source": "decision_writer_packet",
        "writeability_status": memo_ready.get("writer_packet_writeability_report", {}).get("status"),
    }
    scaffold["active_memo_ready_packet_report"] = {
        "schema_id": "active_memo_ready_packet_report_v1",
        "status": "decision_writer_active",
        "active_packet": "memo_ready_packet",
        "method": str(memo_ready.get("method") or "global_decision_writer_packet_adapter"),
        "source_artifact": "decision_writer_packet",
        "evidence_item_count": _list_count(memo_ready.get("evidence_items")),
        "writer_evidence_unit_count": _list_count((writer_packet or {}).get("evidence_units")) if isinstance(writer_packet, dict) else 0,
        "source_trail_count": _list_count(memo_ready.get("source_trail")),
        "downgraded_evidence_item_ids": _analyst_downgraded_evidence_ids(scaffold),
        "writeability_status": memo_ready.get("writer_packet_writeability_report", {}).get("status"),
    }
    return True


def _decision_writer_packet_ready(writer_packet: Any, quality: Any) -> bool:
    if not isinstance(writer_packet, dict) or not writer_packet.get("evidence_units"):
        return False
    if isinstance(quality, dict) and quality.get("status") != "ready":
        return False
    return True


def _analyst_downgraded_evidence_ids(scaffold: dict[str, Any]) -> list[str]:
    synthesis = scaffold.get("analyst_synthesis_packet")
    if not isinstance(synthesis, dict):
        return []
    accounting = synthesis.get("evidence_accounting_summary")
    if not isinstance(accounting, dict):
        return []
    return [str(item) for item in accounting.get("explicitly_downgraded_evidence_item_ids", []) if str(item).strip()]


def _synthesis_warning_inputs(scaffold: dict[str, Any]) -> dict[str, Any]:
    sufficiency = scaffold.get("packet_sufficiency_report") if isinstance(scaffold.get("packet_sufficiency_report"), dict) else {}
    quality = scaffold.get("packet_quality_gate_report") if isinstance(scaffold.get("packet_quality_gate_report"), dict) else {}
    return {
        "packet_sufficiency_issues": sufficiency.get("issues", []),
        "packet_quality_gate_issues": [issue.get("issue_type") for issue in quality.get("issues", []) if isinstance(issue, dict) and issue.get("issue_type")],
    }


def _packet_assembly_details(packet: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    sufficiency = scaffold.get("packet_sufficiency_report") if isinstance(scaffold.get("packet_sufficiency_report"), dict) else {}
    return {
        "bundle_count": _list_count(packet.get("evidence_bundles")),
        "retain_item_count": _list_count(packet.get("must_retain_ledger")),
        "status": sufficiency.get("status", "unknown"),
    }


def _progress(progress: Callable[[str, str, dict[str, Any] | None], None] | None, substage: str, status: str, details: dict[str, Any] | None = None) -> None:
    if progress is not None:
        progress("decision_packet_substage", status, {"substage": substage, **(details or {})})


def _report_status(scaffold: dict[str, Any], key: str) -> dict[str, Any]:
    report = scaffold.get(key)
    return {"status": report.get("status", "unknown")} if isinstance(report, dict) else {"status": "unknown"}


def _analyst_decision_model_details(scaffold: dict[str, Any]) -> dict[str, Any]:
    details = _report_status(scaffold, "analyst_decision_model_report")
    parallel = scaffold.get("analyst_decision_model_parallel_report")
    if isinstance(parallel, dict):
        details.update(
            {
                "method": parallel.get("method", "parallel_grouped_analyst_decision_model"),
                "task_count": parallel.get("task_count", 0),
                "parsed_count": parallel.get("parsed_count", 0),
                "failed_count": parallel.get("failed_count", 0),
            }
        )
    return details


def _chunk_count(scaffold: dict[str, Any]) -> int:
    reports = scaffold.get("analyst_adjudication_chunk_reports")
    return int(reports.get("chunk_count", 0)) if isinstance(reports, dict) else 0


def _ledger_row_count(ledger: Any) -> int:
    return _list_count(ledger.get("rows")) if isinstance(ledger, dict) else 0


def _card_count(value: Any) -> int:
    return int(value.get("card_count", _list_count(value.get("cards")))) if isinstance(value, dict) else 0


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0
