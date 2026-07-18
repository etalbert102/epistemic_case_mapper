from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FinalReaderOutputPaths:
    briefing: Path
    evidence_appendix: Path
    citation_trace: Path
    canonical_decision_writer_packet: Path
    canonical_decision_writer_packet_quality: Path
    source_weight_judgment_report: Path
    argument_spine_quality_report: Path
    canonical_writer_prompt_context_audit: Path
    polish_report: Path
    memo_quality: Path
    curation_report: Path
    briefing_validation: Path
    final_traceability: Path
    final_traceability_markdown: Path
    memo_coherence: Path
    section_role_quality: Path
    pipeline_migration_ledger: Path
    runtime_budget: Path
    stage_value: Path
    final_brief_evaluation: Path
    final_decision_readiness: Path
    final_lineage: Path
    adversarial_memo_qa: Path
    memo_mutation_eval: Path
    memo_semantic_acceptance: Path
    evidence_bundle_reconciliation: Path
    section_rewrite_report: Path
    reader_memo_rewrite_prompt: Path
    reader_memo_rewrite_raw: Path
    reader_memo_rewrite_report: Path
    memo_packet_retention: Path
    packet_first_comparison: Path
    packet_repair_prompt: Path
    packet_repair_raw: Path
    packet_repair_report: Path
    reader_packet_repair_prompt: Path
    reader_packet_repair_raw: Path
    reader_packet_repair_report: Path
    decision_memo_editorial_brief: Path
    decision_memo_editorial_prompt: Path
    decision_memo_editorial_raw: Path
    decision_memo_editorial_report: Path
    memo_ready_synthesis_prompt: Path
    memo_ready_synthesis_raw: Path
    memo_ready_synthesis_report: Path
    evidence_expression_contracts: Path
    evidence_trace: Path
    evidence_reconciliation_report: Path
    evidence_tag_section_reports: Path
    memo_ready_repair_prompt: Path
    memo_ready_repair_raw: Path
    memo_ready_repair_report: Path
    memo_ready_final_polish_prompt: Path
    memo_ready_final_polish_raw: Path
    memo_ready_final_polish_repair_prompt: Path
    memo_ready_final_polish_repair_raw: Path
    memo_ready_final_polish_report: Path
    scoped_metric_report: Path
    final_source_lineage: Path
    source_universe_report: Path
    pipeline_measurement_audit: Path


def final_reader_output_paths(artifacts: Path) -> FinalReaderOutputPaths:
    return FinalReaderOutputPaths(
        briefing=artifacts / "BRIEFING.md",
        evidence_appendix=artifacts / "EVIDENCE_APPENDIX.md",
        citation_trace=artifacts / "CITATION_TRACE.md",
        canonical_decision_writer_packet=artifacts / "canonical_decision_writer_packet.json",
        canonical_decision_writer_packet_quality=artifacts / "canonical_decision_writer_packet_quality_report.json",
        source_weight_judgment_report=artifacts / "source_weight_judgment_report.json",
        argument_spine_quality_report=artifacts / "argument_spine_quality_report.json",
        canonical_writer_prompt_context_audit=artifacts / "canonical_writer_prompt_context_audit.json",
        polish_report=artifacts / "briefing_polish_report.json",
        memo_quality=artifacts / "memo_quality_report.json",
        curation_report=artifacts / "evidence_curation_report.json",
        briefing_validation=artifacts / "briefing_validation_report.json",
        final_traceability=artifacts / "decision_traceability_matrix_final.json",
        final_traceability_markdown=artifacts / "DECISION_TRACEABILITY_MATRIX_FINAL.md",
        memo_coherence=artifacts / "memo_coherence_report.json",
        section_role_quality=artifacts / "section_role_quality_report.json",
        pipeline_migration_ledger=artifacts / "pipeline_migration_ledger.json",
        runtime_budget=artifacts / "runtime_budget_report.json",
        stage_value=artifacts / "stage_value_report.json",
        final_brief_evaluation=artifacts / "final_brief_evaluation.json",
        final_decision_readiness=artifacts / "final_decision_readiness_report.json",
        final_lineage=artifacts / "final_lineage_report.json",
        adversarial_memo_qa=artifacts / "adversarial_memo_qa_report.json",
        memo_mutation_eval=artifacts / "memo_mutation_eval.json",
        memo_semantic_acceptance=artifacts / "memo_semantic_acceptance_report.json",
        evidence_bundle_reconciliation=artifacts / "evidence_bundle_reconciliation_report.json",
        section_rewrite_report=artifacts / "section_rewrite_report.json",
        reader_memo_rewrite_prompt=artifacts / "reader_memo_rewrite_prompt.txt",
        reader_memo_rewrite_raw=artifacts / "reader_memo_rewrite_raw.txt",
        reader_memo_rewrite_report=artifacts / "reader_memo_rewrite_report.json",
        memo_packet_retention=artifacts / "memo_packet_retention_report.json",
        packet_first_comparison=artifacts / "packet_first_comparison_report.json",
        packet_repair_prompt=artifacts / "packet_repair_prompt.txt",
        packet_repair_raw=artifacts / "packet_repair_raw.md",
        packet_repair_report=artifacts / "packet_repair_report.json",
        reader_packet_repair_prompt=artifacts / "reader_packet_repair_prompt.txt",
        reader_packet_repair_raw=artifacts / "reader_packet_repair_raw.md",
        reader_packet_repair_report=artifacts / "reader_packet_repair_report.json",
        decision_memo_editorial_brief=artifacts / "decision_memo_editorial_brief.json",
        decision_memo_editorial_prompt=artifacts / "decision_memo_editorial_prompt.txt",
        decision_memo_editorial_raw=artifacts / "decision_memo_editorial_raw.txt",
        decision_memo_editorial_report=artifacts / "decision_memo_editorial_report.json",
        memo_ready_synthesis_prompt=artifacts / "memo_ready_synthesis_prompt.txt",
        memo_ready_synthesis_raw=artifacts / "memo_ready_synthesis_raw.md",
        memo_ready_synthesis_report=artifacts / "memo_ready_synthesis_report.json",
        evidence_expression_contracts=artifacts / "evidence_expression_contracts.json",
        evidence_trace=artifacts / "evidence_trace.json",
        evidence_reconciliation_report=artifacts / "evidence_reconciliation_report.json",
        evidence_tag_section_reports=artifacts / "evidence_tag_section_reports.json",
        memo_ready_repair_prompt=artifacts / "memo_ready_repair_prompt.txt",
        memo_ready_repair_raw=artifacts / "memo_ready_repair_raw.md",
        memo_ready_repair_report=artifacts / "memo_ready_repair_report.json",
        memo_ready_final_polish_prompt=artifacts / "memo_ready_final_polish_prompt.txt",
        memo_ready_final_polish_raw=artifacts / "memo_ready_final_polish_raw.md",
        memo_ready_final_polish_repair_prompt=artifacts / "memo_ready_final_polish_repair_prompt.txt",
        memo_ready_final_polish_repair_raw=artifacts / "memo_ready_final_polish_repair_raw.md",
        memo_ready_final_polish_report=artifacts / "memo_ready_final_polish_report.json",
        scoped_metric_report=artifacts / "scoped_metric_report.json",
        final_source_lineage=artifacts / "final_source_lineage_report.json",
        source_universe_report=artifacts / "source_universe_report.json",
        pipeline_measurement_audit=artifacts / "pipeline_measurement_audit.json",
    )
