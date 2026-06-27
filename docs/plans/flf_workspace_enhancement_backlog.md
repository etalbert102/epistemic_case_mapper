# FLF Workspace Enhancement Backlog

Purpose: record reusable ideas found in the wider workspace so the FLF prototype can incorporate them systematically instead of relying on chat history.

Status key:

- `pending`: not started.
- `in_progress`: implementation started but not validated.
- `done`: implemented and validated in this repo.
- `deferred`: intentionally postponed with rationale.

## Implementation Order

1. Add judge-facing walkthrough and controlled flat-baseline comparison.
2. Add prompt inventory and reproducibility gate.
3. Upgrade source-span and provenance support.
4. Add workflow telemetry for decision-space erosion.
5. Extend the regulatory/full-document protocol once the LHC and eggs worked regions are stable.

## Enhancement Items

| ID | Status | Enhancement | Workspace Source | FLF Criteria Improved | Acceptance Check |
| --- | --- | --- | --- | --- | --- |
| `enh_001` | done | Add an end-to-end FLF auditor walkthrough showing source subset, case map, flat synthesis, erosion audit, and reviewer decision. | `../decision_space_harness/docs/END_TO_END_AUDITOR_WALKTHROUGH_EXAMPLE.md` | Judge usability, assessment, adversarial scrutiny | `docs/FLF_AUDITOR_WALKTHROUGH_EXAMPLE.md` exists and walks one LHC or eggs region from source text to audit decision. |
| `enh_002` | done | Align all prototype language on `decision-space erosion`, `decision-space preservation`, and related canonical terms. | `../decision_space_harness/docs/TERMINOLOGY_ALIGNMENT.md`; `../decision_space_writing/context/glossary/canonical-terms.md`; `../decision_space_writing/context/concepts/decision-space-erosion.md` | Clear problem framing, conceptual novelty | The reproducibility gate finds no deprecated compression terminology in docs, source, or scripts. |
| `enh_003` | done | Upgrade source support from `heuristic_sentence` to stable source spans with offsets and text hashes where feasible. | `../rule_decomposer/README.md`; `../rule_decomposer/docs/technical_spec.md` | Ingestion, provenance, auditability | Generated claims include reproducible span metadata or an explicit `span_unavailable` reason. |
| `enh_004` | done | Add a lightweight FLF reproducibility gate. | `../decision_space_harness/docs/REPRODUCIBILITY_GATE.md` | Repeatability, compounding, judge confidence | `PYTHONPATH=src python3 scripts/reproducibility_gate.py` regenerates examples, validates snapshots, and checks deterministic metadata incorporation. |
| `enh_005` | done | Create prompt inventory for source mapping, relation extraction, flat baseline, erosion audit, and reviewer handoff prompts. | `../decision_space_harness/docs/PROMPT_INVENTORY.md` | Method transparency, repeatability | `docs/PROMPT_INVENTORY.md` records every prompt/procedure used in worked-region generation and baseline comparisons. |
| `enh_006` | done | Add workflow telemetry for where claims, options, relations, and cruxes enter, merge, get filtered, or disappear. | `../algorithmic_triage/outputs/reports/algorithmic_triage_clean_null_memo.md`; `../decision_space_writing/context/mechanisms/retrieval-gated-reasoning.md` | Assessment, failure localization, adversarial audit | Artifacts record enough intermediate counts or trace notes to distinguish source insufficiency, mapping failure, synthesis erosion, and unsupported invention. |
| `enh_007` | done | Incorporate full-document regulatory task protocol for the second experiment. | `../decision_space_harness/docs/FEDERAL_REGULATION_BENCHMARK_EXPANSION_PLAN.md` | Generality, realism, scale | Regulatory plan states full-document input policy, anchor role, option derivation hierarchy, and deterministic chunking/retrieval policy. |
| `enh_008` | done | Add provenance tag discipline: tags describe what was actually retrieved or supplied, not confidence. | `../claude-for-legal/regulatory-legal/CLAUDE.md` | Source trust, reviewer clarity | Source/provenance tags distinguish local source, user-provided, model-generated proposal, and human-reviewed status without implying unsupported confidence. |
| `enh_009` | done | Add advisory-output authority boundary: LLM proposals are not approved claims until validated against source spans or human review. | `../rule_decomposer/README.md`; `../rule_decomposer/docs/source_specs/llm_instruction_rule_decomposer_technical_spec.md` | Trustworthiness, adversarial scrutiny | Workflow docs and schema distinguish proposal, source-supported, interpretation candidate, and human-reviewed states. |
| `enh_010` | done | Add human-review packet pattern with accept/revise/reject/needs-discussion decisions for curated maps. | `../rule_decomposer/README.md` | Human extensibility, compounding | Human-review artifacts let a reviewer inspect source excerpts, relation rationales, and export decisions or notes. |
| `enh_011` | done | Add current-state ledger for what the prototype actually does today versus planned/claimed capability. | `../happy/docs/research/unsupervised-development-guidelines-and-skills.md` | Judge trust, maintainability | `docs/CURRENT_STATE.md` lists implemented, partially implemented, and not-yet-implemented capabilities with validation evidence. |
| `enh_012` | done | Add role/process guidance for agent-assisted prototype work: developer, verifier, reviewer, process cleanup. | `../happy/docs/research/unsupervised-development-guidelines-and-skills.md`; `../happy/docs/research/agent-teams-claude-code.md` | Repeatable workflow, maintainability | `AGENTS.md` or a workflow doc states when to use implementation, verification, and review passes. |

## Detailed Notes

### Auditor Walkthrough

The decision-space harness walkthrough cleanly separates pre-output label audit from post-output erosion audit. The FLF version should make the same separation:

- first inspect whether the case-map labels are source-supported,
- then compare a flat synthesis against frozen map items,
- then count only losses that survive an adversarial fairness check.

This prevents the prototype from quietly editing the map after seeing a baseline.

### Terminology Alignment

Use:

- `decision-space erosion`: loss or non-preservation of decision-relevant options, frames, conflicts, constraints, or reviewable context before accountable review.
- `decision-space preservation`: workflow goal of keeping those structures visible, grounded, and auditable.
- `decision-space erasure`: reserve for terminal cases where alternatives practically disappear before review.
- `behavioral compression`: use only when formal options remain visible but behavior converges around a path.

### Stable Source Spans

The current scaffold uses `heuristic_sentence`. That is acceptable for a starter map, but a stronger FLF artifact should preserve:

- source ID,
- normalized source checksum,
- span start/end offsets where possible,
- excerpt hash,
- local excerpt,
- extraction method,
- review status.

### Reproducibility Gate

The first FLF gate should be smaller than the decision-space harness gate but should check:

- schemas validate,
- examples regenerate deterministically,
- metadata files are incorporated,
- source-grounded URL sources have retrieval dates,
- prompt inventory exists once prompts are used,
- worked-region files exist once the worked-region plan is executed.

### Telemetry Boundary Lesson

The algorithmic-triage null-result memo is a warning that final outputs alone may be too far downstream. For FLF, the prototype should log or report the intermediate map state so reviewers can see whether a failure happened during:

- source selection,
- source-span extraction,
- claim normalization,
- relation mapping,
- crux selection,
- synthesis,
- final audit.

### Regulatory Full-Document Protocol

For the regulatory slice, full documents should be the main synthesis input. Audit anchors should verify labels but should not become the primary model input unless the condition is explicitly an excerpt-budget ablation.

### Provenance Tags

Do not let tags imply more confidence than earned. A tag records provenance and review state:

- local source text,
- user-provided source,
- model-generated proposal,
- source-supported after validation,
- human-reviewed.

## Completion Tracking

Before treating the prototype as FLF-ready, update this section with final statuses:

- [x] `enh_001` auditor walkthrough implemented.
- [x] `enh_002` terminology aligned.
- [x] `enh_003` stable source-span support implemented with normalized offsets and hashes.
- [x] `enh_004` reproducibility gate implemented.
- [x] `enh_005` prompt inventory implemented.
- [x] `enh_006` workflow telemetry implemented for deterministic extraction, relation mapping, and open-question mapping.
- [x] `enh_007` regulatory full-document protocol incorporated as a protocol document.
- [x] `enh_008` provenance tags implemented on claims and documented.
- [x] `enh_009` advisory-output authority boundary implemented in schema/docs as review-state distinctions.
- [x] `enh_010` human-review packet pattern implemented.
- [x] `enh_011` current-state ledger implemented.
- [x] `enh_012` role/process guidance implemented.
