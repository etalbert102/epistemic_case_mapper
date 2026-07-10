# Plan: Transparent LLM Source Appraisal

## Objective
Add an automated, transparent source-appraisal stage that evaluates the quality and trustworthiness of each document before its claims are used in evidence cards, briefing packets, or final synthesis.

The target end state is that every source has a structured, inspectable `source_appraisal` artifact produced by an LLM, validated by deterministic code, and propagated through existing source evidence cards and evidence-quality reports. The system should automate judgments that are hard to encode with rules, while making every downgrade, suspicious-source flag, and uncertainty visible to reviewers.

The stage should answer three different questions separately:

- What kind of evidence does this document contain?
- How trustworthy is this source and document as evidence?
- How directly should this document influence the current decision question?

## Current Gap
The repo already has several related pieces, but they are not integrated into an automated document-quality layer:

- `Source` metadata has coarse provenance fields such as `provenance_level`, `evidence_role`, `limitations`, and `needs_upgrade`.
- Case metadata files such as `source_method_metadata.md` and `source_independence.md` manually record evidence type, validity risks, directness, and correlated-source clusters.
- `source_evidence_cards.json` and `evidence_quality_report.json` are already produced in the briefing context pipeline.
- The current evidence-quality report mostly infers quality from card relevance, anchor strength, crude evidence-type text, and limitations.

This means the pipeline can say whether a claim is anchored, but it cannot yet reliably say whether the document itself is a strong study, weak commentary, conflicted advocacy report, public explainer, correlated synthesis, suspicious source, or direct primary evidence.

## Non-Goals
- Do not replace claim anchoring or quote validation with source-level appraisal.
- Do not let an unvalidated LLM judgment silently change evidence weight.
- Do not make source appraisal a final truth label; it is a structured model judgment with evidence and review status.
- Do not overfit the rubric to nutrition, LHC, COVID origins, or any one case type.
- Do not require human review for every source before producing artifacts; require visible review flags when the model is uncertain.
- Do not make new quality gates blocking until they have passed report-only calibration on existing cases.

## Design Principles
- Use the LLM for semantic appraisal: document type, method fit, source incentives, transparency, suspicious-source signals, and decision-specific directness.
- Use deterministic code for schema validation, source IDs, allowed values, quote presence, artifact assembly, routing rules, scoring impact, and gate behavior.
- Require evidence for judgments. Every downgrade, suspicious flag, or high-risk source label must point to an excerpt, source metadata field, or explicit `not_found` record.
- Keep source quality separate from claim quality. A strong source can contain a weak extracted claim, and a risky source can still provide useful context.
- Preserve uncertainty rather than forcing precision. The stage should emit `unknown`, `not_found`, and `human_review_needed` instead of guessing.
- Make appraisals auditable across time by preserving prompts, raw outputs, canonical outputs, validation reports, and downstream score impacts.

## Inventory And Dependency Map
Before implementation, classify the current artifacts and code paths:

- Source manifest fields: `schema.Source`, case YAML sources, source paths, URLs, source types, provenance fields, limitations.
- Manual metadata: source method tables, independence clusters, stakeholder context, timeline notes.
- Existing source artifacts: `source_evidence_cards`, `source_sufficiency_report`, `evidence_quality_report`, `candidate_evidence_cards`, `source_evidence_graph`.
- Existing quality surfaces: `unseen_quality.source_quality_signals`, UI quality warnings, final review packets, map briefing summaries.
- Model-facing seams: staged semantic source extraction, whole-document source cards, decision-ready context bundle, analyst evidence ledger.

Dependency order:

```text
case sources
  -> source appraisal prompts
  -> raw LLM source appraisals
  -> deterministic validation and normalization
  -> source_appraisal_report.json
  -> source_evidence_cards enrichment
  -> evidence_quality_report enrichment
  -> candidate evidence routing and confidence caps
  -> UI/review warnings and final evidence packet
```

## Workstreams

1. Source Appraisal Schema And Rubric
   - Purpose: Define the stable contract for model-produced source appraisal.
   - Changes: Add Pydantic schemas for `SourceAppraisal`, `SourceAppraisalEvidence`, `SourceAppraisalReport`, and parse/validation reports.
   - Core fields:
     - `source_id`
     - `document_type`
     - `evidence_type`
     - `evidence_strength: high | moderate | low | very_low | unknown`
     - `evidence_proximity: primary | synthesis | summary | commentary | official_record | unknown`
     - `source_risk: low | medium | high | unknown`
     - `transparency: high | medium | low | unknown`
     - `decision_directness: direct | partial | indirect | unknown`
     - `independence_risk: low | medium | high | unknown`
     - `method_validity_risks[]`
     - `suspicious_flags[]`
     - `missing_transparency_fields[]`
     - `decision_use: use | use_with_caution | background_only | exclude | human_review_needed`
     - `confidence_rationale`
   - Artifacts: Schema definitions, JSON examples, ownership map for deterministic-only versus model-suggested fields.
   - Validation: Unit tests for valid appraisals, invalid enums, missing required evidence, unknown source IDs, and unsupported suspicious flags.
   - QA: Golden examples for a peer-reviewed study, public explainer, narrative review, vendor/advocacy-style document, anonymous document, and official guidance.
   - Risks: The schema may become too broad; defer domain-specific tools such as AMSTAR, PRISMA, GRADE, CASP, and AGREE into optional rubric tags rather than hard-coded first-pass requirements.

2. LLM Source Appraisal Stage
   - Purpose: Use the model to assess each full source document and its manifest metadata.
   - Changes: Add `map_briefing_source_appraisal.py` or a similarly scoped module.
   - Prompt requirements:
     - Show source manifest metadata, source text or bounded source excerpts, decision question, and allowed rubric values.
     - Ask for exact evidence excerpts for downgrades, suspicious flags, method risks, conflicts, and transparency gaps.
     - Require `not_found` for absent funding, methods, authorship, conflicts, or dates.
     - Forbid judging truth of the whole debate; the task is appraisal of the source as evidence.
   - Artifacts:
     - Per-source prompt.
     - Per-source raw model output.
     - Per-source canonical appraisal JSON.
     - Per-source validation report.
     - Combined `source_appraisal_report.json`.
   - Validation: Fake-backend tests and parser tests for conforming output, malformed JSON, missing quote evidence, partial repair, and quarantine.
   - QA: Adversarial fixture where a source has official-looking language but missing authorship/funding; the model should flag transparency gaps without inventing hidden motives.
   - Risks: The LLM may over-flag or under-flag suspicious sources. Keep first release in report-only mode and compare against manual case metadata.

3. Deterministic Appraisal Validation And Impact Rules
   - Purpose: Make model appraisal transparent and bounded before it affects evidence routing.
   - Changes:
     - Validate source IDs against the case manifest.
     - Normalize enums and reject appraisals with unsupported values.
     - Require evidence excerpts for every nontrivial downgrade or suspicious flag.
     - Distinguish `not_found` from negative evidence.
     - Emit deterministic impact fields such as `confidence_cap`, `routing_penalty`, and `review_required`.
   - Artifacts:
     - `source_appraisal_validation_report.json`
     - `source_appraisal_impact_report.json`
     - rejected/quarantined appraisal records
   - Validation: Tests for deterministic policy:
     - `source_risk=high` plus no corroboration routes to `background_only` or `human_review_needed`.
     - `evidence_strength=high` but `decision_directness=indirect` cannot become load-bearing support.
     - `transparency=unknown` should cap confidence but not exclude by itself.
     - multiple sources in one `independence_cluster` do not count as fully independent corroboration.
   - QA: Report-only calibration on existing eggs, LHC, and COVID slice cases before blocking any downstream use.
   - Risks: Deterministic policy can encode arbitrary weights. Store rules in one module and report the exact rule that changed routing.

4. Integration With Source Evidence Cards And Quality Reports
   - Purpose: Propagate source-level appraisal into the existing decision-ready context pipeline.
   - Changes:
     - Run appraisal before `build_source_evidence_cards`.
     - Enrich source evidence cards with `source_appraisal_id`, `evidence_strength`, `source_risk`, `decision_directness`, `transparency`, `decision_use`, and `appraisal_flags`.
     - Upgrade `build_evidence_quality_report` to combine card-level anchoring with source-level appraisal.
     - Preserve separate components instead of a single opaque score.
   - Artifacts:
     - enriched `source_evidence_cards.json`
     - enriched `evidence_quality_report.json`
     - appraisal-aware `candidate_evidence_cards.json`
   - Validation: Existing context-schema tests should continue to parse old cards; new tests assert enriched fields when appraisal is present.
   - QA: Stage-value report showing how many cards changed routing because of appraisal and why.
   - Risks: New fields could break consumers. Use schema `extra="allow"` compatibility and keep old required fields stable.

5. Candidate Evidence Routing, Confidence Caps, And Independence
   - Purpose: Make appraisal influence decisions in a transparent, reversible way.
   - Changes:
     - Adjust candidate scoring to consider appraisal-derived quality without hiding its components.
     - Add `appraisal_impact` to candidate evidence cards.
     - Add confidence caps to decision models and final memo warnings when load-bearing evidence is weak, indirect, high-risk, or correlated.
     - Formalize independence clusters from LLM appraisal and manual metadata.
   - Artifacts:
     - `source_independence_report.json`
     - `appraisal_routing_report.json`
     - confidence-cap reasons in decision synthesis and argument artifacts
   - Validation: Tests for correlated meta-analysis clusters, public summaries, and high-risk/commentary sources.
   - QA: Metamorphic test: reordering sources should not change appraisal routing; duplicating a source should not create independent corroboration.
   - Risks: Penalizing correlated sources can suppress useful consensus. The report should distinguish "not independent" from "not useful."

6. UI And Review Packet Surfaces
   - Purpose: Make source trust visible to reviewers and future agents.
   - Changes:
     - Add source appraisal warnings to `unseen_quality.source_quality_signals`.
     - Expose source-risk, evidence-strength, and suspicious flags in UI source rows or quality warnings.
     - Add the new appraisal artifacts to `map_briefing_artifacts.py` and final review packet links.
     - Include source-appraisal summary in run summaries.
   - Artifacts:
     - UI `qualityWarnings` entries for high-risk sources, transparency gaps, source-use exclusions, and human-review-needed appraisals.
     - Final review packet section: "Source Appraisal And Evidence Quality."
   - Validation: UI-data build tests and existing UI validation should pass.
   - QA: Reviewer can trace a warning from UI -> source appraisal card -> evidence excerpt -> source text.
   - Risks: Too many warnings can drown out useful signals. Prioritize high-risk, excluded, and load-bearing weak-source warnings.

7. Calibration And Golden-Case Evaluation
   - Purpose: Measure whether the automated appraisal stage improves evidence quality rather than just producing more artifacts.
   - Changes:
     - Create small golden fixtures with expected source-appraisal behavior.
     - Add before/after comparisons on at least three case types.
     - Add report-only gates for suspicious-source and weak-evidence handling.
   - Artifacts:
     - `source_appraisal_calibration_report.json`
     - golden fixture files
     - before/after appraisal impact notes
   - Validation:
     - Golden cases must match expected high-level labels.
     - Existing cases must not lose source anchoring.
     - High-risk source fixtures must be flagged with evidence.
     - Clean peer-reviewed/official sources must not be over-penalized.
   - QA:
     - Adversarial mutation: remove author/funding/method sections and verify transparency downgrade.
     - Adversarial mutation: add promotional language and verify source-risk or suspicious-flag consideration.
     - Metamorphic mutation: paraphrase the decision question without changing its meaning and verify stable source-use labels.
   - Risks: Golden fixtures can overfit. Keep examples domain-diverse and test invariant behavior, not exact prose.

## Execution Order
1. Define schemas and example appraisal artifacts first, so downstream integration has a stable target.
2. Build the LLM appraisal module with fake-backend tests and deterministic validation.
3. Run the stage in report-only mode on existing cases and compare against manual metadata files.
4. Enrich source evidence cards and evidence-quality reports without changing routing.
5. Add routing impact in report-only mode and inspect stage-value reports.
6. Promote calibrated deterministic impact rules into candidate-card scoring and confidence caps.
7. Add UI/review surfaces and final review packet summaries.
8. Add calibration fixtures, adversarial tests, and metamorphic tests.
9. Complete with a source-appraisal completion audit.

## Acceptance Criteria
- Every source in a source-grounded case can receive a structured source appraisal or a visible `appraisal_missing` record.
- The pipeline writes prompt, raw output, canonical output, validation report, and combined `source_appraisal_report.json`.
- No appraisal can be accepted if it uses an unknown source ID or unsupported enum value.
- Every suspicious flag, downgrade, or source-risk label above `low` includes source evidence, source metadata evidence, or an explicit `not_found` transparency record.
- Enriched `source_evidence_cards.json` and `evidence_quality_report.json` preserve existing fields while adding appraisal context.
- Candidate evidence routing explains any score change or appendix/background-only routing caused by source appraisal.
- UI/review packets expose high-risk, excluded, human-review-needed, and load-bearing weak-source warnings.
- Report-only calibration runs on eggs, LHC, and COVID slice cases before any new gate becomes blocking.
- Existing tests pass, plus new tests for schemas, parsing, validation, routing, UI warnings, and adversarial source fixtures.

## Red-Team Checks
- Failure: The model invents conflicts of interest or source motives.
  - Detection: Validation requires evidence excerpts or `not_found`; unsupported claims are quarantined.
- Failure: The model mistakes "disagreeable conclusion" for suspicious source.
  - Detection: Prompt separates source risk from stance; tests include credible sources with opposing conclusions.
- Failure: A public explainer is treated as primary evidence.
  - Detection: Evidence proximity and decision-use rules route explainers to context unless independently corroborated.
- Failure: A systematic review and its included studies are counted as independent support.
  - Detection: Independence cluster report and duplicated-underlying-evidence warnings.
- Failure: A high-quality but indirect source becomes load-bearing.
  - Detection: `decision_directness=indirect` caps candidate role and confidence.
- Failure: New warnings create alert fatigue.
  - Detection: UI warning counts and review packet prioritization; only high-risk or load-bearing weak-source issues are top-level.
- Failure: The source-appraisal stage passes schema tests but does not improve decisions.
  - Detection: Stage-value reports compare before/after routing, confidence caps, and reviewer-visible source caveats.

## Generalizability Checks
- The rubric must work for clinical studies, legal/regulatory documents, policy briefs, financial models, vendor reports, news explainers, narrative reviews, and raw data/official records.
- Prompts must use generic rubric language, not case-specific vocabulary.
- Domain-specific frameworks such as GRADE, AMSTAR 2, PRISMA, AGREE II, CASP, SIFT, and CRAAP can be referenced as optional appraisal lenses, not as required universal fields.
- Appraisal should be stable under source order changes, duplicate source insertion, and harmless source-title changes.
- Appraisal should change when real provenance, method, transparency, or directness information is removed.
- Unseen-case tests should include at least one suspicious/advocacy source, one official-but-indirect source, one strong primary source, and one synthesis source with independence risk.

## Canonical Ledger
Track implementation progress in a ledger that survives multiple commits:

| Slice | Status | Primary Artifact | Verification | Notes |
| --- | --- | --- | --- | --- |
| Schema and examples | planned | `source_appraisal_report` schema | schema unit tests | Keep backward compatibility. |
| LLM appraisal stage | planned | per-source appraisal artifacts | fake-backend parser tests | Report-only first. |
| Validation and impact rules | planned | validation and impact reports | deterministic policy tests | No silent score changes. |
| Context integration | planned | enriched source/cards reports | context schema tests | Preserve old fields. |
| Routing and confidence caps | planned | appraisal routing report | before/after tests | Calibrate before blocking. |
| UI and review packets | planned | quality warnings/review section | UI-data validation | Prioritize load-bearing risks. |
| Calibration and completion audit | planned | calibration report/audit | golden/adversarial/metamorphic tests | Required before closure. |

## Deferred-Work Policy
- If a domain-specific rubric is useful but not general enough, record it as a future optional lens rather than embedding it in the core schema.
- If model appraisals are noisy, keep routing in report-only mode and improve prompts or validation before using the outputs.
- If source text is too long for the backend, emit a visible appraisal coverage limit and appraise a deterministic source packet rather than silently truncating.
- If funding/conflicts/authorship are absent, record `not_found`; do not infer misconduct or neutrality.
- Any deferred item must name the affected artifact, risk, owner stage, and whether final synthesis is still allowed.

## Final Review Packet
The plan is complete only when a final audit packet exists with:

- Summary of implemented source-appraisal stages and artifacts.
- Before/after examples showing source appraisal changed or confirmed evidence use.
- Calibration results on existing cases.
- Golden/adversarial/metamorphic test results.
- Known false-positive and false-negative risks.
- Examples of reviewer traceability from final warning to source excerpt.
- Recommendation for whether appraisal impact rules should remain report-only or become blocking.

