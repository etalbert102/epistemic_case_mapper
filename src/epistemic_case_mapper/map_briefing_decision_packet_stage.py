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


def _run_analyst_packet_builders(scaffold: dict[str, Any], packet: dict[str, Any], ledger: dict[str, Any], *, backend_config: Any, progress: Callable[[str, str, dict[str, Any] | None], None] | None) -> None:
    from epistemic_case_mapper.map_briefing_analyst_packet import build_analyst_packet_bundle
    from epistemic_case_mapper.map_briefing_analyst_quantity_binding import run_analyst_quantity_binding
    from epistemic_case_mapper.map_briefing_analyst_refinement import run_analyst_packet_refinement

    _progress(progress, "analyst_packet_bundle", "started")
    scaffold.update(build_analyst_packet_bundle(packet=packet, ledger=ledger, adjudication=scaffold.get("analyst_adjudication", {}), decision_model=scaffold.get("analyst_decision_model", {}), memo_warning_packet=scaffold.get("memo_warning_packet", {})))
    _progress(progress, "analyst_packet_bundle", "completed")

    _progress(progress, "analyst_packet_refinement", "started")
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
    _progress(progress, "analyst_packet_finalization", "completed", _report_status(scaffold, "active_memo_ready_packet_report"))


def _promote_analyst_packet_as_active(scaffold: dict[str, Any]) -> None:
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
