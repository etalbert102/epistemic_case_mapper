from __future__ import annotations

import re
from collections import Counter
from typing import Any

from epistemic_case_mapper.main_memo_obligations import (
    build_main_memo_obligation_plan,
    obligation_satisfied_by_text,
)


def build_decision_argument_artifacts(scaffold: dict[str, Any], candidate_map: dict[str, Any]) -> dict[str, Any]:
    matrix = build_evidence_to_decision_matrix(scaffold, candidate_map)
    findings = build_summary_of_findings(scaffold, matrix)
    reads = build_competing_reads(scaffold, findings)
    graph = build_argument_case_graph(scaffold, findings, reads)
    traceability = build_decision_traceability_matrix(scaffold, findings, graph)
    cruxes = build_structured_decision_cruxes(findings, reads)
    return {
        "evidence_to_decision_matrix": matrix,
        "summary_of_findings": findings,
        "competing_reads": reads,
        "argument_case_graph": graph,
        "decision_traceability_matrix": traceability,
        "structured_decision_cruxes": cruxes,
    }


def build_evidence_to_decision_matrix(scaffold: dict[str, Any], candidate_map: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in _ranked_evidence_rows(scaffold):
        item = _matrix_row_from_evidence(row, scaffold, len(rows) + 1)
        key = (str(item["decision_factor"]), _norm(str(item["finding"]))[:120])
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    for item in _argument_rows(scaffold, len(rows) + 1):
        key = (str(item["decision_factor"]), _norm(str(item["finding"]))[:120])
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return {
        "schema_id": "evidence_to_decision_matrix_v1",
        "method": "deterministic_decision_factor_rows_from_weighted_map_and_argument_model",
        "question": str(scaffold.get("question", "")).strip(),
        "row_count": len(rows[:24]),
        "factor_counts": dict(Counter(str(row.get("decision_factor", "unknown")) for row in rows[:24])),
        "rows": rows[:24],
        "audit": {
            "claim_count": len(_claims(candidate_map)),
            "relation_count": len(_relations(candidate_map)),
            "source_count": len(_source_display_names(scaffold)),
        },
    }


def build_summary_of_findings(scaffold: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in matrix.get("rows", []) if isinstance(row, dict)]
    selected = sorted(rows, key=lambda row: (-int(row.get("priority", 0)), str(row.get("row_id", ""))))[:12]
    findings: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        findings.append(
            {
                "finding_id": f"finding_{index:02d}",
                "source_row_id": row.get("row_id"),
                "finding": row.get("finding"),
                "decision_factor": row.get("decision_factor"),
                "population_or_scope": row.get("population_or_scope"),
                "comparator_or_alternative": row.get("comparator_or_alternative"),
                "quantitative_anchor": row.get("quantitative_anchor"),
                "direction": row.get("direction"),
                "certainty": row.get("certainty"),
                "decision_impact": row.get("decision_impact"),
                "main_limitation": row.get("uncertainty_or_caveat"),
                "source_ids": row.get("source_ids", []),
                "claim_ids": row.get("claim_ids", []),
                "relation_ids": row.get("relation_ids", []),
                "quantity_ids": row.get("quantity_ids", []),
            }
        )
    return {
        "schema_id": "summary_of_findings_v1",
        "method": "ranked_decision_relevant_findings_from_evidence_to_decision_matrix",
        "finding_count": len(findings),
        "findings": findings,
    }


def build_competing_reads(scaffold: dict[str, Any], findings: dict[str, Any]) -> dict[str, Any]:
    read_specs = [
        ("favorable_or_beneficial", "Treat the option as favorable or beneficial."),
        ("neutral_or_low_difference", "Treat the option as neutral, limited-difference, or not meaningfully changed."),
        ("unfavorable_or_harmful", "Treat the option as unfavorable, harmful, or not worth adopting."),
        ("conditional_or_scope_dependent", "Treat the answer as conditional on population, comparator, implementation, or uncertainty."),
    ]
    finding_rows = [row for row in findings.get("findings", []) if isinstance(row, dict)]
    reads: list[dict[str, Any]] = []
    for read_id, label in read_specs:
        support = [_finding_signal(row, read_id) for row in finding_rows]
        support = [row for row in support if row]
        reads.append(
            {
                "read_id": read_id,
                "label": label,
                "supporting_findings": [row for row in support if row.get("stance") == "supports"][:5],
                "challenging_findings": [row for row in support if row.get("stance") == "challenges"][:5],
                "diagnostic_score": round(sum(float(row.get("diagnosticity", 0)) for row in support), 3),
            }
        )
    strongest = sorted(reads, key=lambda row: -float(row.get("diagnostic_score", 0)))[:2]
    return {
        "schema_id": "competing_reads_v1",
        "method": "deterministic_ach_style_read_discrimination_from_finding_roles",
        "question": str(scaffold.get("question", "")).strip(),
        "reads": reads,
        "most_diagnostic_reads": [row.get("read_id") for row in strongest],
    }


def build_argument_case_graph(
    scaffold: dict[str, Any],
    findings: dict[str, Any],
    competing_reads: dict[str, Any],
) -> dict[str, Any]:
    argument_model = _dict(scaffold.get("argument_model"))
    top_claim = str(argument_model.get("proposed_answer") or _dict(_dict(scaffold.get("decision_synthesis_model")).get("bottom_line")).get("current_read") or "Current decision read is conditional on the mapped evidence.").strip()
    nodes = [
        _node("claim_top", "top_claim", top_claim, "Decision claim to establish."),
        _node("strategy_evidence", "strategy", "Use ranked findings to connect evidence to the decision read.", "Evidence-to-decision strategy."),
        _node("strategy_competing_reads", "strategy", "Compare competing reads before accepting the top claim.", "Competing-read strategy."),
        _node("context_question", "context", str(scaffold.get("question", "")).strip(), "Decision question."),
    ]
    edges = [
        _edge("strategy_evidence", "claim_top", "supports"),
        _edge("strategy_competing_reads", "claim_top", "supports"),
        _edge("context_question", "claim_top", "context_for"),
    ]
    for finding in findings.get("findings", [])[:10] if isinstance(findings.get("findings"), list) else []:
        if not isinstance(finding, dict):
            continue
        node_id = str(finding.get("finding_id"))
        nodes.append(_node(node_id, "evidence", str(finding.get("finding", "")), str(finding.get("decision_impact", "")), finding))
        relation = "challenges" if str(finding.get("direction")) == "challenges_or_warns" else "supports"
        if str(finding.get("direction")) == "bounds_or_conditions":
            relation = "bounded_by"
        edges.append(_edge(node_id, "claim_top", relation))
    for read in competing_reads.get("reads", []) if isinstance(competing_reads.get("reads"), list) else []:
        if not isinstance(read, dict):
            continue
        node_id = f"read_{read.get('read_id')}"
        nodes.append(_node(node_id, "competing_read", str(read.get("label", "")), f"Diagnostic score: {read.get('diagnostic_score', 0)}."))
        edges.append(_edge(node_id, "strategy_competing_reads", "evaluated_by"))
    for index, counter in enumerate(argument_model.get("strongest_counterarguments", [])[:5], start=1) if isinstance(argument_model.get("strongest_counterarguments"), list) else []:
        if not isinstance(counter, dict):
            continue
        node_id = f"defeater_{index:02d}"
        nodes.append(_node(node_id, "defeater", str(counter.get("statement", "")), str(counter.get("why_it_matters", "")), counter))
        edges.append(_edge(node_id, "claim_top", "challenges"))
    for index, missing in enumerate(argument_model.get("missing_evidence", [])[:5], start=1) if isinstance(argument_model.get("missing_evidence"), list) else []:
        if not isinstance(missing, dict):
            continue
        node_id = f"uncertainty_{index:02d}"
        nodes.append(_node(node_id, "unresolved_uncertainty", str(missing.get("statement", "")), str(missing.get("why_it_matters", "")), missing))
        edges.append(_edge(node_id, "claim_top", "limits_confidence"))
    return {
        "schema_id": "argument_case_graph_v1",
        "method": "goal_structured_argument_case_from_decision_findings",
        "top_claim_node_id": "claim_top",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def build_structured_decision_cruxes(findings: dict[str, Any], competing_reads: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in findings.get("findings", []) if isinstance(row, dict)]
    support = [row for row in rows if _finding_direction(row) == "support"]
    challenge = [row for row in rows if _finding_direction(row) == "challenge"]
    bounds = [row for row in rows if _finding_direction(row) == "boundary"]
    cruxes: list[dict[str, Any]] = []
    for primary, counter in _diagnostic_pairs(support, challenge, limit=2):
        cruxes.append(_structured_crux("evidence_balance", primary, counter))
    for primary, boundary in _diagnostic_pairs(support, bounds, limit=1):
        cruxes.append(_structured_crux("scope_boundary", primary, boundary))
    for boundary, counter in _diagnostic_pairs(bounds, challenge, limit=1):
        cruxes.append(_structured_crux("exception_strength", boundary, counter))
    for read in _diagnostic_read_cruxes(competing_reads, rows):
        cruxes.append(read)
    cruxes = _dedupe_cruxes(cruxes)
    if not cruxes and rows:
        cruxes.extend(_single_finding_crux(row) for row in rows[:3])
    return {
        "schema_id": "structured_decision_cruxes_v1",
        "method": "deterministic_crux_objects_from_findings_and_competing_reads",
        "crux_count": len(cruxes[:4]),
        "most_diagnostic_reads": competing_reads.get("most_diagnostic_reads", []),
        "cruxes": cruxes[:4],
    }


def build_decision_traceability_matrix(
    scaffold: dict[str, Any],
    findings: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    obligations = build_main_memo_obligation_plan(scaffold=scaffold)
    finding_lookup = _finding_lookup(findings)
    graph_lookup = _graph_lookup(graph)
    rows: list[dict[str, Any]] = []
    for index, obligation in enumerate(obligations[:60], start=1):
        finding_ids = _matching_finding_ids(obligation, finding_lookup)
        graph_node_ids = _matching_graph_node_ids(obligation, graph_lookup)
        rows.append(
            {
                "trace_id": f"trace_{index:02d}",
                "requirement_id": obligation.get("obligation_id"),
                "requirement_category": obligation.get("category"),
                "requirement": obligation.get("statement"),
                "target_sections": _target_sections(str(obligation.get("category", ""))),
                "supporting_finding_ids": finding_ids,
                "argument_node_ids": graph_node_ids,
                "source_ids": obligation.get("source_ids", []),
                "claim_ids": obligation.get("claim_ids", []),
                "relation_ids": obligation.get("relation_ids", []),
                "quantity_ids": obligation.get("quantity_ids", []),
                "status": "planned",
                "disposition": "include_or_explicitly_mark_out_of_scope",
                "search_terms": obligation.get("search_terms", []),
            }
        )
    return {
        "schema_id": "decision_traceability_matrix_v1",
        "method": "obligation_to_finding_argument_and_memo_section_traceability",
        "row_count": len(rows),
        "status_counts": {"planned": len(rows)},
        "rows": rows,
    }


def evaluate_traceability_against_memo(matrix: dict[str, Any], memo_text: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in matrix.get("rows", []) if isinstance(matrix.get("rows"), list) else []:
        if not isinstance(row, dict):
            continue
        obligation = {
            "statement": row.get("requirement", ""),
            "search_terms": row.get("search_terms", []),
            "status_override": "source_missing" if row.get("disposition") == "source_missing" else "",
        }
        status = "satisfied" if obligation_satisfied_by_text(obligation, memo_text) else "missing_from_memo"
        rows.append({**row, "status": status, "memo_sections": _sections_containing_terms(memo_text, row.get("search_terms", []))})
    counts = Counter(str(row.get("status", "unknown")) for row in rows)
    return {
        **{key: value for key, value in matrix.items() if key != "rows"},
        "schema_id": "decision_traceability_matrix_v1",
        "method": "final_memo_traceability_presence_check",
        "row_count": len(rows),
        "status_counts": dict(counts),
        "rows": rows,
    }


def render_evidence_to_decision_matrix_markdown(matrix: dict[str, Any]) -> str:
    lines = ["# Evidence To Decision Matrix", "", f"Rows: `{matrix.get('row_count', 0)}`", ""]
    lines.append("| Factor | Direction | Certainty | Finding | Decision Impact |")
    lines.append("|---|---|---|---|---|")
    for row in matrix.get("rows", [])[:24] if isinstance(matrix.get("rows"), list) else []:
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    row.get("decision_factor", ""),
                    row.get("direction", ""),
                    row.get("certainty", ""),
                    row.get("finding", ""),
                    row.get("decision_impact", ""),
                )
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_summary_of_findings_markdown(findings: dict[str, Any]) -> str:
    lines = ["# Summary Of Findings", "", f"Findings: `{findings.get('finding_count', 0)}`", ""]
    for row in findings.get("findings", []) if isinstance(findings.get("findings"), list) else []:
        lines.extend(
            [
                f"## {row.get('finding_id')}: {row.get('decision_factor')}",
                "",
                f"- Finding: {row.get('finding')}",
                f"- Direction: `{row.get('direction')}`",
                f"- Certainty: `{row.get('certainty')}`",
                f"- Quantitative anchor: {row.get('quantitative_anchor') or 'none'}",
                f"- Limitation: {row.get('main_limitation') or 'none recorded'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_competing_reads_markdown(reads: dict[str, Any]) -> str:
    lines = ["# Competing Reads", ""]
    for row in reads.get("reads", []) if isinstance(reads.get("reads"), list) else []:
        lines.extend(
            [
                f"## {row.get('read_id')}",
                "",
                f"{row.get('label')}",
                "",
                f"- Diagnostic score: `{row.get('diagnostic_score')}`",
                f"- Supporting findings: `{len(row.get('supporting_findings', []))}`",
                f"- Challenging findings: `{len(row.get('challenging_findings', []))}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_argument_case_graph_markdown(graph: dict[str, Any]) -> str:
    lines = ["# Argument Case Graph", "", f"Nodes: `{graph.get('node_count', 0)}`", f"Edges: `{graph.get('edge_count', 0)}`", ""]
    for node in graph.get("nodes", [])[:30] if isinstance(graph.get("nodes"), list) else []:
        lines.append(f"- `{node.get('node_id')}` {node.get('node_type')}: {node.get('statement')}")
    lines.extend(["", "## Edges", ""])
    for edge in graph.get("edges", [])[:40] if isinstance(graph.get("edges"), list) else []:
        lines.append(f"- `{edge.get('source')}` --{edge.get('relation')}--> `{edge.get('target')}`")
    return "\n".join(lines).rstrip() + "\n"


def render_decision_traceability_matrix_markdown(matrix: dict[str, Any]) -> str:
    lines = ["# Decision Traceability Matrix", "", f"Rows: `{matrix.get('row_count', 0)}`", ""]
    lines.append("| Requirement | Status | Target Sections | Findings | Argument Nodes |")
    lines.append("|---|---|---|---|---|")
    for row in matrix.get("rows", [])[:60] if isinstance(matrix.get("rows"), list) else []:
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    row.get("requirement", ""),
                    row.get("status", ""),
                    ", ".join(str(value) for value in row.get("target_sections", [])),
                    ", ".join(str(value) for value in row.get("supporting_finding_ids", [])),
                    ", ".join(str(value) for value in row.get("argument_node_ids", [])),
                )
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def compact_decision_argument_artifacts(scaffold: dict[str, Any], title_key: str = "") -> dict[str, Any]:
    artifacts = _dict(scaffold.get("decision_argument_artifacts"))
    findings = _dict(artifacts.get("summary_of_findings")).get("findings", [])
    reads = _dict(artifacts.get("competing_reads")).get("reads", [])
    graph = _dict(artifacts.get("argument_case_graph"))
    traceability = _dict(artifacts.get("decision_traceability_matrix")).get("rows", [])
    cruxes = _dict(artifacts.get("structured_decision_cruxes")).get("cruxes", [])
    title_key = title_key.lower()
    if "decision brief" in title_key:
        finding_limit = 4
    elif "crux" in title_key:
        finding_limit = 6
    else:
        finding_limit = 5
    return {
        "summary_of_findings": findings[:finding_limit] if isinstance(findings, list) else [],
        "competing_reads": reads[:4] if isinstance(reads, list) else [],
        "structured_decision_cruxes": cruxes[:4] if isinstance(cruxes, list) else [],
        "argument_case_top_claim": _top_claim(graph),
        "traceability_requirements": traceability[:8] if isinstance(traceability, list) else [],
    }


def _structured_crux(crux_type: str, primary: dict[str, Any], counter: dict[str, Any]) -> dict[str, Any]:
    if crux_type == "evidence_balance":
        crux = f"Whether {_factor_label(counter)} should materially weaken {_factor_label(primary)}"
    elif crux_type == "scope_boundary":
        crux = f"Whether {_factor_label(counter)} narrows the default read"
    else:
        crux = f"Whether {_factor_label(primary)} is a separate exception or changes the default"
    return {
        "crux": _sentence(crux),
        "why_it_matters": "This determines whether the decision read should stay general, become narrower, or move toward caution.",
        "current_read": "The current read keeps both the supporting evidence and the counterevidence visible; neither is treated as decisive.",
        "would_change_if": "The recommendation would change if the counterevidence applied broadly across the target decision.",
        "supporting_finding_ids": _string_list([primary.get("finding_id")]),
        "challenging_finding_ids": _string_list([counter.get("finding_id")]),
        "source_ids": _dedupe([*_string_list(primary.get("source_ids")), *_string_list(counter.get("source_ids"))]),
        "crux_type": crux_type,
    }


def _finding_direction(row: dict[str, Any]) -> str:
    direction = str(row.get("direction", "")).lower()
    factor = str(row.get("decision_factor", "")).lower()
    text = " ".join([direction, factor])
    if any(term in text for term in ("challenge", "counter", "risk", "warn", "harm", "unfavorable")):
        return "challenge"
    if any(term in text for term in ("bound", "scope", "condition", "exception", "limit", "uncertain")):
        return "boundary"
    if any(term in text for term in ("support", "default", "inform", "favorable", "beneficial")):
        return "support"
    return "boundary"


def _diagnostic_pairs(left: list[dict[str, Any]], right: list[dict[str, Any]], *, limit: int) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for first in left:
        for second in right:
            if not _different_findings(first, second):
                continue
            pairs.append((first, second))
            if len(pairs) >= limit:
                return pairs
    return pairs


def _different_findings(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_text = _norm(str(first.get("finding", "")))
    second_text = _norm(str(second.get("finding", "")))
    if not first_text or not second_text:
        return True
    first_terms = set(first_text.split())
    second_terms = set(second_text.split())
    if not first_terms or not second_terms:
        return True
    overlap = len(first_terms & second_terms) / max(len(first_terms | second_terms), 1)
    return overlap < 0.78


def _diagnostic_read_cruxes(competing_reads: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {str(row.get("finding_id")): row for row in findings if str(row.get("finding_id", "")).strip()}
    rows: list[dict[str, Any]] = []
    reads = [row for row in competing_reads.get("reads", []) if isinstance(row, dict)]
    for read in sorted(reads, key=lambda row: -float(row.get("diagnostic_score", 0) or 0))[:2]:
        support_ids = [str(item.get("finding_id")) for item in read.get("supporting_findings", []) if isinstance(item, dict)]
        challenge_ids = [str(item.get("finding_id")) for item in read.get("challenging_findings", []) if isinstance(item, dict)]
        support = [lookup[item] for item in support_ids if item in lookup]
        challenge = [lookup[item] for item in challenge_ids if item in lookup]
        finding = (support or challenge or findings[:1] or [{}])[0]
        label = _read_label(str(read.get("read_id", "")), str(read.get("label", "")))
        finding_text = _short_phrase(str(finding.get("finding", "")))
        rows.append(
            {
                "crux": _sentence(f"Whether the evidence favors the {label} read rather than the leading alternative"),
                "why_it_matters": "This is the direct choice between plausible decision interpretations.",
                "current_read": "The current read treats the diagnostic evidence as informative but still conditional.",
                "would_change_if": _sentence("The recommendation would change if the diagnostic evidence consistently supported this read across the target scope"),
                "supporting_finding_ids": support_ids[:3],
                "challenging_finding_ids": challenge_ids[:3],
                "source_ids": _string_list(finding.get("source_ids")),
                "crux_type": "competing_read",
            }
        )
    return rows


def _factor_label(row: dict[str, Any]) -> str:
    factor = str(row.get("decision_factor", "")).strip().lower().replace("_", " ")
    direction = _finding_direction(row)
    if factor and factor not in {"unknown", "other"}:
        return factor
    return {
        "support": "supporting evidence",
        "challenge": "counterevidence",
        "boundary": "scope or uncertainty evidence",
    }.get(direction, "decision-relevant evidence")


def _read_label(read_id: str, label: str) -> str:
    normalized = " ".join(part for part in re.split(r"[_\W]+", read_id.lower()) if part)
    if normalized:
        return normalized
    cleaned = re.sub(r"^treat\s+(?:the\s+)?(?:option|answer)\s+as\s+", "", label.lower()).strip(" .")
    return _short_phrase(cleaned) or "competing"


def _dedupe_cruxes(cruxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for crux in cruxes:
        key = _norm(str(crux.get("crux", "")))[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(crux)
    return kept


def _single_finding_crux(row: dict[str, Any]) -> dict[str, Any]:
    text = _short_phrase(str(row.get("finding", "")))
    return {
        "crux": _sentence(f"Whether {text.lower()} is enough to settle the decision"),
        "why_it_matters": "This is the most decision-relevant finding available in the current packet.",
        "current_read": _sentence(f"The current read treats {text.lower()} as important but not automatically decisive"),
        "would_change_if": "The recommendation would change if better evidence showed this finding does not apply to the target decision.",
        "supporting_finding_ids": _string_list([row.get("finding_id")]),
        "challenging_finding_ids": [],
        "source_ids": _string_list(row.get("source_ids")),
        "crux_type": "single_finding",
    }


def _matrix_row_from_evidence(row: dict[str, Any], scaffold: dict[str, Any], index: int) -> dict[str, Any]:
    claim_id = str(row.get("claim_id", "")).strip()
    quantities = _quantities_for_claim(scaffold, claim_id)
    factor = _decision_factor(row)
    return {
        "row_id": f"etd_{index:03d}",
        "decision_factor": factor,
        "finding": _short_text(str(row.get("claim", "")), 360),
        "population_or_scope": _scope_text(row),
        "comparator_or_alternative": _comparator_text(row),
        "quantitative_anchor": "; ".join(quantities[:3]),
        "certainty": _certainty(row, scaffold),
        "direction": _direction(row),
        "decision_impact": _decision_impact(factor, row),
        "uncertainty_or_caveat": _uncertainty(row),
        "priority": _priority(row, quantities),
        "source_ids": [str(row.get("source_id", "")).strip()] if str(row.get("source_id", "")).strip() else [],
        "claim_ids": [claim_id] if claim_id else [],
        "relation_ids": [],
        "quantity_ids": _quantity_ids_for_claim(scaffold, claim_id),
        "source_label": row.get("source"),
    }


def _argument_rows(scaffold: dict[str, Any], start_index: int) -> list[dict[str, Any]]:
    argument_model = _dict(scaffold.get("argument_model"))
    specs = [
        ("strongest_support", "supporting_evidence", "supports_default", 86),
        ("strongest_counterarguments", "counterevidence_or_risk", "challenges_or_warns", 84),
        ("scope_boundaries", "scope_or_subgroup", "bounds_or_conditions", 80),
        ("cruxes", "decision_crux", "bounds_or_conditions", 76),
        ("missing_evidence", "uncertainty_or_gap", "limits_confidence", 70),
    ]
    rows: list[dict[str, Any]] = []
    for key, factor, direction, priority in specs:
        for item in argument_model.get(key, []) if isinstance(argument_model.get(key), list) else []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "row_id": f"etd_{start_index + len(rows):03d}",
                    "decision_factor": factor,
                    "finding": _short_text(str(item.get("statement", "")), 360),
                    "population_or_scope": "",
                    "comparator_or_alternative": "",
                    "quantitative_anchor": "; ".join(str(value) for value in item.get("quantities", [])[:3]) if isinstance(item.get("quantities"), list) else "",
                    "certainty": str(item.get("weight", "medium")),
                    "direction": direction,
                    "decision_impact": str(item.get("why_it_matters", "")),
                    "uncertainty_or_caveat": "; ".join(str(value) for value in item.get("limitations", [])[:2]) if isinstance(item.get("limitations"), list) else "",
                    "priority": priority,
                    "source_ids": item.get("source_ids", []) if isinstance(item.get("source_ids"), list) else [],
                    "claim_ids": item.get("claim_ids", []) if isinstance(item.get("claim_ids"), list) else [],
                    "relation_ids": item.get("relation_ids", []) if isinstance(item.get("relation_ids"), list) else [],
                    "quantity_ids": item.get("quantity_ids", []) if isinstance(item.get("quantity_ids"), list) else [],
                    "source_label": "",
                }
            )
    return rows


def _ranked_evidence_rows(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = _dict(scaffold.get("evidence_weighting_ledger"))
    rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)]
    return sorted(rows, key=lambda row: (-int(row.get("score", 0)), str(row.get("claim_id", ""))))[:24]


def _decision_factor(row: dict[str, Any]) -> str:
    section = str(row.get("section", ""))
    family = str(row.get("evidence_family", ""))
    concepts = set(_string_list(row.get("decision_concepts")))
    slots = set(_string_list(row.get("decision_slots")))
    if section == "conflicting_evidence" or "safety_or_risk" in slots:
        return "counterevidence_or_risk"
    if section == "scope_limits" or "population_scope" in concepts or "high_risk_subgroup" in slots:
        return "scope_or_subgroup"
    if section == "method_limits" or family == "method_or_validity":
        return "method_or_validity"
    if family == "mechanism_or_biomarker" or "mechanism" in slots:
        return "mechanism_or_proxy"
    if "substitution_or_comparator" in slots or "alternative_or_comparator" in concepts:
        return "comparator_or_alternative"
    if family == "guideline_or_recommendation" or "practical_recommendation" in slots:
        return "guidance_or_practical_advice"
    return "direct_or_primary_evidence"


def _direction(row: dict[str, Any]) -> str:
    section = str(row.get("section", ""))
    factor = _decision_factor(row)
    if section == "conflicting_evidence" or factor == "counterevidence_or_risk":
        return "challenges_or_warns"
    if section in {"scope_limits", "method_limits"} or factor in {"scope_or_subgroup", "method_or_validity"}:
        return "bounds_or_conditions"
    return "supports_or_informs"


def _decision_impact(factor: str, row: dict[str, Any]) -> str:
    source = str(row.get("source", "")).strip()
    text = {
        "counterevidence_or_risk": "Could move the decision toward caution or narrower scope.",
        "scope_or_subgroup": "Determines where the answer applies and where separate handling is needed.",
        "method_or_validity": "Limits confidence in how far the finding should travel.",
        "mechanism_or_proxy": "Explains a plausible pathway or proxy endpoint but may not settle hard outcomes.",
        "comparator_or_alternative": "Changes the recommendation depending on what option replaces what.",
        "guidance_or_practical_advice": "Connects evidence to practical recommendation language.",
    }.get(factor, "Informs the default decision read.")
    return text + (f" Source: {source}." if source else "")


def _certainty(row: dict[str, Any], scaffold: dict[str, Any]) -> str:
    weight = str(row.get("weight", "")).lower()
    if weight in {"high", "medium", "low"}:
        return weight
    cap = str(scaffold.get("confidence_cap", "medium")).lower()
    return cap if cap in {"high", "medium", "low"} else "medium"


def _priority(row: dict[str, Any], quantities: list[str]) -> int:
    base = int(row.get("score", 50) or 50)
    if quantities:
        base += 10
    if str(row.get("weight", "")).lower() == "high":
        base += 5
    return base


def _uncertainty(row: dict[str, Any]) -> str:
    noise = row.get("noise", {}) if isinstance(row.get("noise"), dict) else {}
    if noise.get("kind") and noise.get("kind") != "none":
        return f"Extraction quality issue: {noise.get('kind')}."
    if str(row.get("weight", "")).lower() == "low":
        return "Low-weight evidence; avoid overclaiming."
    return ""


def _scope_text(row: dict[str, Any]) -> str:
    slots = row.get("decision_slots", {})
    if isinstance(slots, dict):
        for key in ("high_risk_subgroup", "population_scope", "dose_or_intensity_threshold"):
            value = slots.get(key)
            if isinstance(value, list) and value:
                return _short_text(str(value[0]), 120)
    return ""


def _comparator_text(row: dict[str, Any]) -> str:
    slots = row.get("decision_slots", {})
    if isinstance(slots, dict):
        for key in ("substitution_or_comparator", "alternative_or_comparator"):
            value = slots.get(key)
            if isinstance(value, list) and value:
                return _short_text(str(value[0]), 120)
    text = str(row.get("claim", ""))
    match = re.search(r"\b(?:compared with|compared to|versus|instead of|rather than)\b.{0,90}", text, flags=re.I)
    return _short_text(match.group(0), 120) if match else ""


def _quantities_for_claim(scaffold: dict[str, Any], claim_id: str) -> list[str]:
    if not claim_id:
        return []
    cards = [card for card in _dict(scaffold.get("quantity_ledger")).get("evidence_cards", []) if isinstance(card, dict)]
    quantities: list[str] = []
    for card in cards:
        if str(card.get("claim_id", "")) == claim_id:
            quantities.extend(_string_list(card.get("key_quantities")))
    return _dedupe(quantities)[:6]


def _quantity_ids_for_claim(scaffold: dict[str, Any], claim_id: str) -> list[str]:
    cards = [card for card in _dict(scaffold.get("quantity_ledger")).get("evidence_cards", []) if isinstance(card, dict)]
    return [str(card.get("card_id", "")) for card in cards if str(card.get("claim_id", "")) == claim_id and str(card.get("card_id", "")).strip()][:4]


def _finding_signal(row: dict[str, Any], read_id: str) -> dict[str, Any] | None:
    direction = str(row.get("direction", ""))
    factor = str(row.get("decision_factor", ""))
    finding_id = str(row.get("finding_id", ""))
    if read_id == "conditional_or_scope_dependent" and direction in {"bounds_or_conditions", "limits_confidence"}:
        return _signal(finding_id, "supports", 0.9)
    if read_id == "unfavorable_or_harmful" and direction == "challenges_or_warns":
        return _signal(finding_id, "supports", 0.85)
    if read_id == "favorable_or_beneficial" and direction == "supports_or_informs":
        return _signal(finding_id, "supports", 0.65)
    if read_id == "neutral_or_low_difference" and factor in {"method_or_validity", "comparator_or_alternative"}:
        return _signal(finding_id, "supports", 0.45)
    if read_id in {"favorable_or_beneficial", "neutral_or_low_difference"} and direction == "challenges_or_warns":
        return _signal(finding_id, "challenges", 0.6)
    if read_id == "unfavorable_or_harmful" and direction == "supports_or_informs":
        return _signal(finding_id, "challenges", 0.35)
    return None


def _signal(finding_id: str, stance: str, diagnosticity: float) -> dict[str, Any]:
    return {"finding_id": finding_id, "stance": stance, "diagnosticity": diagnosticity}


def _node(node_id: str, node_type: str, statement: str, rationale: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "statement": _short_text(statement, 360),
        "rationale": _short_text(rationale, 240),
        "payload": payload or {},
    }


def _edge(source: str, target: str, relation: str) -> dict[str, str]:
    return {"source": source, "target": target, "relation": relation}


def _finding_lookup(findings: dict[str, Any]) -> dict[str, str]:
    return {
        str(row.get("finding_id")): " ".join(str(row.get(key, "")) for key in ("finding", "decision_factor", "quantitative_anchor"))
        for row in findings.get("findings", [])
        if isinstance(row, dict)
    }


def _graph_lookup(graph: dict[str, Any]) -> dict[str, str]:
    return {
        str(row.get("node_id")): " ".join(str(row.get(key, "")) for key in ("statement", "node_type", "rationale"))
        for row in graph.get("nodes", [])
        if isinstance(row, dict)
    }


def _matching_finding_ids(obligation: dict[str, Any], lookup: dict[str, str]) -> list[str]:
    return _matching_lookup_ids([str(obligation.get("statement", "")), *_string_list(obligation.get("search_terms"))], lookup)[:5]


def _matching_graph_node_ids(obligation: dict[str, Any], lookup: dict[str, str]) -> list[str]:
    return _matching_lookup_ids([str(obligation.get("statement", "")), *_string_list(obligation.get("search_terms"))], lookup)[:5]


def _matching_lookup_ids(needles: list[str], lookup: dict[str, str]) -> list[str]:
    needle_terms = set(_tokens(" ".join(needles)))
    if not needle_terms:
        return []
    scored: list[tuple[float, str]] = []
    for key, text in lookup.items():
        hay = set(_tokens(text))
        overlap = len(needle_terms.intersection(hay)) / max(1, len(needle_terms))
        if overlap >= 0.18:
            scored.append((overlap, key))
    return [key for _, key in sorted(scored, reverse=True)]


def _target_sections(category: str) -> list[str]:
    return {
        "quantitative_anchor": ["Decision Brief", "Why This Read", "Evidence Carrying the Conclusion"],
        "quantitative_depth": ["Evidence Carrying the Conclusion"],
        "strongest_support": ["Decision Brief", "Why This Read"],
        "strongest_counterargument": ["Why This Read", "Decision Cruxes", "Practical Scope and Exceptions"],
        "scope_boundary": ["Practical Scope and Exceptions", "Decision Brief"],
        "decision_crux": ["Decision Cruxes"],
        "evidence_family_balance": ["Evidence Carrying the Conclusion"],
        "baseline_comparison_concept": ["Limits of the Current Map", "Evidence Carrying the Conclusion"],
    }.get(category, ["Why This Read"])


def _sections_containing_terms(memo_text: str, terms: Any) -> list[str]:
    sections = _split_sections(memo_text)
    matched: list[str] = []
    for title, text in sections:
        normalized = _norm(text)
        if any(_norm(term) and _norm(term) in normalized for term in _string_list(terms)):
            matched.append(title)
    return matched


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown, flags=re.MULTILINE))
    if not matches:
        return [("Document", markdown)]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append((match.group(1).strip(), markdown[start:end]))
    return sections


def _top_claim(graph: dict[str, Any]) -> dict[str, Any]:
    for node in graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []:
        if isinstance(node, dict) and node.get("node_id") == "claim_top":
            return {key: node.get(key) for key in ("node_id", "statement", "rationale")}
    return {}


def _source_display_names(scaffold: dict[str, Any]) -> list[str]:
    names = scaffold.get("source_display_names", {})
    return [str(value) for value in names.values()] if isinstance(names, dict) else []


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    value = candidate_map.get("claims", [])
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    value = candidate_map.get("relations", [])
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for value in values:
        key = _norm(value)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(value)
    return kept


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _norm(text: str) -> str:
    return " ".join(_tokens(text))


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _short_phrase(text: str) -> str:
    words = re.sub(r"\s+", " ", str(text)).strip(" .").split()
    return " ".join(words[:14]).rstrip(" ,.;")


def _sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "!", "?")) else cleaned + "."


def _cell(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.replace("|", "\\|")
    return _short_text(text, 180)
