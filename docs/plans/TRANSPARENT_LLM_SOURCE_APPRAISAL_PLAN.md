# Plan: Transparent LLM Source Caveat Appraisal

## Objective
Add an automated, transparent source-appraisal stage that identifies what each document is, then surfaces interpretation caveats that should travel with any claims extracted from that document.

The target end state is that every source first receives an early LLM identification and triage disposition before expensive claim extraction. Every retained source then receives a structured, inspectable `source_caveat_appraisal` artifact produced by a type-specific LLM prompt, validated by deterministic code, and propagated through existing source evidence cards and evidence-quality reports. The system should automate judgments that are hard to encode with rules, while making every caveat, missing-transparency record, suspicious-source flag, quarantine decision, and uncertainty visible to reviewers.

The stage should answer three different questions separately:

- What kind of document is this, and what evidentiary role can it plausibly play?
- What caveats should affect interpretation of claims extracted from this document?
- How directly and safely should this document influence the current decision question?

The early gate should answer a narrower operational question:

- Should this source proceed to normal claim extraction, proceed only as background/context, proceed with caution, or be quarantined before extraction?

## Current Gap
The repo already has several related pieces, but they are not integrated into an automated document-caveat layer:

- `Source` metadata has coarse provenance fields such as `provenance_level`, `evidence_role`, `limitations`, and `needs_upgrade`.
- Case metadata files such as `source_method_metadata.md` and `source_independence.md` manually record evidence type, validity risks, directness, and correlated-source clusters.
- `source_evidence_cards.json` and `evidence_quality_report.json` are already produced in the briefing context pipeline.
- The current evidence-quality report mostly infers quality from card relevance, anchor strength, crude evidence-type text, and limitations.

This means the pipeline can say whether a claim is anchored, but it cannot yet reliably say what kind of document produced the claim or what source-level caveats should constrain interpretation of the claim.

## Non-Goals
- Do not replace claim anchoring or quote validation with source-level appraisal.
- Do not let an unvalidated LLM judgment silently change evidence weight.
- Do not silently delete sources. Hard exclusion must be rare, evidence-backed, logged, and reversible.
- Do not pretend source appraisal can precisely score document quality. The second pass should discover interpretation constraints, not assign a universal quality grade.
- Do not make source appraisal a final truth label; it is a structured model judgment with evidence and review status.
- Do not overfit the prompt lenses to nutrition, LHC, COVID origins, or any one case type.
- Do not require human review for every source before producing artifacts; require visible review flags when the model is uncertain.
- Do not make new source-use gates blocking until they have passed report-only calibration on existing cases.

## Design Principles
- Use the LLM first for semantic identification and routing: document type, source identity, provenance, evidence role, duplicate/junk signals, and decision-specific relevance.
- Use the LLM second for type-specific caveat discovery: method limits, source incentives, transparency gaps, independence risks, reasoning limits, evidentiary directness, and suspicious-source signals that matter for that document type.
- Use deterministic code for schema validation, source IDs, allowed values, quote presence, artifact assembly, routing rules, caveat impact, and gate behavior.
- Minimize token spend in early triage. Use manifest metadata, structural signals, and bounded deterministic snippets first; escalate to a larger packet or full document only when the cheap pass is ambiguous, risky, or would otherwise quarantine a source.
- Reuse the repo's existing model-call parallelism pattern. Source triage and caveat appraisal should run through `model_backends.run_parallel`, preserve input order, use `model_parallelism(backend)` and its `ECM_MODEL_PARALLELISM`/`ECM_OLLAMA_PARALLELISM` overrides, and add stage-specific caps only where prompt size or local Ollama memory requires them.
- Put source appraisal early enough to prevent obvious trash from contaminating extraction, but make the early gate a triage-and-routing stage rather than a silent deletion stage.
- Require evidence for judgments. Every caveat, suspicious flag, or source-use limitation must point to an excerpt, source metadata field, or explicit `not_found` record.
- Prefer caveat lists and downstream handling guidance over aggregate quality scores. If routing needs a categorical impact, derive it deterministically from caveats and report the rule.
- Keep source quality separate from claim quality. A strong source can contain a weak extracted claim, and a risky source can still provide useful context.
- Preserve uncertainty rather than forcing precision. The stage should emit `unknown`, `not_found`, and `human_review_needed` instead of guessing.
- Make appraisals auditable across time by preserving prompts, raw outputs, canonical outputs, validation reports, and downstream routing impacts.

## Inventory And Dependency Map
Before implementation, classify the current artifacts and code paths:

- Source manifest fields: `schema.Source`, case YAML sources, source paths, URLs, source types, provenance fields, limitations.
- Manual metadata: source method tables, independence clusters, stakeholder context, timeline notes.
- Existing source artifacts: `source_evidence_cards`, `source_sufficiency_report`, `evidence_quality_report`, `candidate_evidence_cards`, `source_evidence_graph`.
- Existing quality surfaces: `unseen_quality.source_quality_signals`, UI quality warnings, final review packets, map briefing summaries.
- Model-facing seams: staged semantic source extraction, whole-document source cards, decision-ready context bundle, analyst evidence ledger.
- Existing parallelism seams: `model_backends.run_parallel`, `model_parallelism`, relation batch extraction, whole-document claim extraction, and analyst adjudication chunking.

Dependency order:

```text
case sources
  -> deterministic cheap triage packet assembly
  -> early source triage prompts
  -> raw LLM source identification and triage
  -> deterministic triage validation, document-type normalization, escalation, and disposition
  -> pre-extraction source-use profile and extraction instructions
  -> extraction only for non-quarantined sources
  -> type-specific caveat prompt selection
  -> raw LLM source caveat appraisals
  -> deterministic caveat validation and normalization
  -> optional targeted re-extraction when caveat appraisal finds missed claim classes or sections
  -> source_caveat_appraisal_report.json
  -> source_evidence_cards enrichment
  -> evidence_quality_report enrichment
  -> candidate evidence routing and confidence caps
  -> final memo evidence basis and caveat constraints
  -> final memo reasoning and limitations
  -> UI/review warnings and final evidence packet
```

## Workstreams

1. Source Identification, Caveat Schema, And Prompt Lens Taxonomy
   - Purpose: Define the stable contract for model-produced source identification, triage, and caveat appraisal.
   - Changes: Add Pydantic schemas for `SourceTriage`, `SourceCaveatAppraisal`, `SourceInterpretationCaveat`, `SourceCaveatEvidence`, `SourceCaveatAppraisalReport`, and parse/validation reports.
   - Core fields:
     - `source_id`
     - `triage_packet_scope: cheap | expanded | full_document`
     - `triage_packet_reason`
     - `model_parallelism`
     - `parallelism_source: default | ECM_MODEL_PARALLELISM | ECM_OLLAMA_PARALLELISM | stage_override`
     - `triage_disposition: use | use_with_caution | background_only | quarantine | human_review_needed`
     - `triage_reason`
     - `pre_extraction_profile`
     - `extraction_instructions[]`
     - `sections_likely_worth_extracting[]`
     - `claim_type_cautions[]`
     - `document_type`
     - `document_type_confidence: high | medium | low | unknown`
     - `document_type_alternates[]`
     - `prompt_lens: empirical_study | systematic_review | narrative_review | official_guidance | legal_or_regulatory | news_reporting | advocacy_or_vendor_report | opinion_or_commentary | dataset_or_record | transcript_or_interview | mixed_or_unknown`
     - `evidence_type`
     - `evidence_proximity: primary | synthesis | summary | commentary | official_record | unknown`
     - `claim_use_context: load_bearing_possible | corroboration_only | background_context | stakeholder_framing | provenance_only | human_review_needed`
     - `decision_directness: direct | partial | indirect | unknown`
     - `interpretation_caveats[]`
     - `missing_information[]`
     - `source_incentive_caveats[]`
     - `method_or_reasoning_caveats[]`
     - `directness_caveats[]`
     - `independence_caveats[]`
     - `claim_scope_limits[]`
     - `suspicious_flags[]`
     - `recommended_use: load_bearing_ok | use_with_caution | corroborate_before_use | background_only | exclude | human_review_needed`
     - `caveat_summary`
   - Caveat fields:
     - `caveat_type`
     - `explanation`
     - `basis: excerpt | metadata | not_found | model_uncertain`
     - `evidence_excerpt`
     - `affected_claim_types[]`
     - `downstream_handling`
     - `review_required`
   - Artifacts: Schema definitions, JSON examples, ownership map for deterministic-only versus model-suggested fields.
   - Validation: Unit tests for valid appraisals, invalid enums, missing required evidence, unknown source IDs, unsupported suspicious flags, and unsupported prompt lenses.
   - QA: Golden examples for a peer-reviewed study, systematic review, public explainer, narrative review, vendor/advocacy-style document, anonymous document, legal/regulatory filing, official guidance, and raw dataset.
   - Risks: The schema may become too broad; keep prompt lenses pragmatic and make specialized frameworks such as AMSTAR, PRISMA, GRADE, CASP, AGREE, SIFT, and CRAAP optional references inside lens prompts rather than universal fields.

2. Early LLM Source Triage Gate
   - Purpose: Prevent clear trash, duplicates, irrelevant documents, and non-evidence sources from consuming extraction budget or contaminating maps.
   - Changes: Add a lightweight model call before claim extraction that uses a cheap deterministic triage packet and assigns one of five operational dispositions:
     - `use`: proceed to normal claim extraction.
     - `use_with_caution`: proceed to claim extraction, but inherit warnings and confidence caps.
     - `background_only`: extract only source-level context or bottom-line notes; do not create load-bearing evidential claims by default.
     - `quarantine`: skip claim extraction unless explicitly overridden.
     - `human_review_needed`: do not hard exclude; route to cautious/background handling until reviewed.
   - Cheap triage packet:
     - manifest metadata: source ID, title, URL/path, declared source type, publisher, date, provenance fields, and case-level source notes;
     - extracted title, authors, publisher, date, and document-type hints when available;
     - opening page or opening section;
     - abstract, executive summary, or overview when present;
     - headings/table of contents when available;
     - conclusion, recommendations, or final section when cheaply extractable;
     - references/citations presence and a bounded sample rather than the full bibliography;
     - boilerplate/footer/domain snippets useful for spam, publisher, or provenance detection;
     - deterministic text stats: extracted length, language, extraction quality, duplicate hash/similarity signals, and missing-text signals;
     - fixed beginning/middle/end snippets with stable character or token budgets.
   - Escalation to expanded or full-document triage:
     - `document_type_confidence` is low or the source appears mixed;
     - the model proposes `quarantine`, `exclude`, or `human_review_needed` for any reason other than deterministic empty/unreadable/duplicate evidence;
     - the cheap packet is internally inconsistent, for example metadata says "study" but snippets look like commentary or promotional copy;
     - the source is very short and full text is cheaper than packet construction;
     - the source is unusually high leverage, likely load-bearing, or central to the decision question;
     - extraction quality is poor enough that snippet selection may have hidden relevant context.
   - Quarantine criteria:
     - unreadable, empty, or mostly boilerplate source text;
     - duplicate or near-duplicate of a retained source;
     - no recoverable source identity or provenance;
     - obvious spam, SEO filler, promotional copy, or scraped junk;
     - irrelevant to the decision question;
     - synthetic or AI-generated summary with no citation trail;
     - source text unavailable or detached from the claimed citation.
   - Artifacts:
     - `source_triage_packet.json` per source, recording packet scope, snippets included, omitted sections, token/character budget, and escalation reason.
     - `source_triage_prompt.txt` per source.
     - raw triage output per source.
     - canonical triage record per source.
     - `pre_extraction_source_profile.json`, containing document type, prompt lens, evidence role, provenance cautions, source-use disposition, extraction instructions, and likely useful sections.
     - `source_triage_report.json`.
     - `quarantined_sources.json`.
   - Parallelism:
     - Use `run_parallel` over per-source triage packets so output order remains source-manifest order.
     - Use `model_parallelism(backend)` by default, honoring `ECM_MODEL_PARALLELISM` and the Ollama-specific `ECM_OLLAMA_PARALLELISM`.
     - Add a stage helper such as `source_triage_parallelism(backend)` only if cheap triage needs a different cap; default should remain the shared backend parallelism because packets are intentionally small.
     - Record effective parallelism, backend, packet count, expanded/full-document escalation count, backend errors, and retries in `source_triage_report.json`.
   - Validation: Deterministic code validates source IDs, allowed disposition values, packet scope, escalation triggers, and evidence for any `quarantine` decision.
   - QA: Golden fixtures for obvious spam, duplicate sources, public explainers, useful advocacy reports, contrarian but legitimate sources, and ambiguous sources that should escalate from cheap to expanded triage.
   - Risks: False exclusion is expensive because downstream maps never see the source. Therefore `quarantine` must be rare, auditable, reversible, and stricter than `background_only`. Cheap-packet triage must not silently under-read a source; record packet coverage and escalation decisions.

3. Source-Aware Claim Extraction Placement
   - Purpose: Use the cheap source profile to improve claim extraction without making full caveat appraisal a prerequisite for every source.
   - Changes:
     - Feed `pre_extraction_source_profile.json` into whole-document/source-card claim extraction.
     - Use document-type-specific extraction cautions, for example:
       - legal/regulatory sources: distinguish allegations, procedural claims, exhibits, findings, and rules.
       - news sources: distinguish reported facts, anonymous-source claims, expert quotes, and editorial interpretation.
       - advocacy/vendor reports: distinguish factual claims, stakeholder framing, selective-evidence claims, and promotional assertions.
       - reviews: distinguish the review's own synthesis from included-study findings and cited background.
       - datasets/records: distinguish observed records, derived metrics, and interpretation.
     - Keep extraction inclusive for non-quarantined sources; caveats should tag and route claims, not suppress potentially useful claims too early.
     - Route `background_only` sources to context, provenance, stakeholder framing, and source bottom-line extraction by default, not load-bearing claim extraction.
   - Artifacts:
     - `claim_extraction_source_profiles.json`
     - extraction prompts that include source profile and claim-type cautions
     - extraction report fields showing which profile was applied to each source
   - Validation: Tests assert that extraction prompts receive source profiles, that legal allegations are not extracted as findings, that review/included-study boundaries are preserved, and that background-only sources do not produce default load-bearing claims.
   - QA: Before/after extraction fixtures should show fewer document-type misuse errors without reducing useful claim recall.
   - Risks: Source-aware extraction can become prematurely conservative. The extractor should tag claim roles and cautions, then let downstream caveat routing decide final use.

4. Type-Specific LLM Caveat Appraisal Stage
   - Purpose: Use the model to inspect each full source document and discover caveats that affect interpretation of claims from that document.
   - Changes: Add `map_briefing_source_appraisal.py` or a similarly scoped module.
   - Prompt requirements:
     - Show source manifest metadata, source text or bounded source excerpts, decision question, allowed schema values, and prompt-lens instructions.
     - Select a prompt lens from the first-pass document type; if the type is ambiguous or mixed, use a mixed-document prompt that checks multiple plausible lenses.
     - Include the early triage disposition and ask the model to refine, not blindly confirm, that disposition after reading the source.
     - Include extracted claim summaries or claim types when available, so the caveat pass can bind caveats to the claims that downstream stages may actually use.
     - Ask for exact evidence excerpts for caveats, suspicious flags, method or reasoning limits, source-incentive concerns, independence concerns, and transparency gaps.
     - Require `not_found` for absent funding, methods, authorship, conflicts, or dates.
     - Forbid assigning a universal quality score or judging truth of the whole debate; the task is to identify constraints on how claims from the source should be interpreted.
   - Type-specific prompt lenses:
     - `empirical_study`: methods, sample, measurement, controls, causal identification, statistical uncertainty, generalizability, conflicts, and reproducibility caveats.
     - `systematic_review`: search strategy, inclusion/exclusion criteria, bias assessment, synthesis method, overlap with included studies, and update-date caveats.
     - `narrative_review`: source-selection transparency, selective citation risk, synthesis-versus-opinion boundaries, and usefulness as background rather than independent confirmation.
     - `official_guidance`: issuing authority, evidentiary basis, update date, policy constraints, legal/institutional context, and whether guidance is direct evidence or decision context.
     - `legal_or_regulatory`: jurisdiction, procedural posture, adversarial framing, exhibit support, rule status, and distinction between allegations, findings, and evidence.
     - `news_reporting`: named sourcing, primary-document support, correction/update signals, reporting versus opinion, and dependence on anonymous or secondary sources.
     - `advocacy_or_vendor_report`: incentives, funding, selective evidence risk, methods transparency, factual claims that remain useful, and stakeholder-framing value.
     - `opinion_or_commentary`: author expertise, cited evidence, reasoning quality, rhetorical inflation, and whether the document should be used only for argument/stakeholder framing.
     - `dataset_or_record`: provenance, collection method, completeness, variable definitions, missingness, update cadence, and whether the record directly supports extracted claims.
     - `transcript_or_interview`: speaker identity, firsthand status, context, editing/selection risk, and distinction between testimony, memory, opinion, and factual report.
   - Artifacts:
     - Per-source prompt.
     - Per-source raw model output.
     - Per-source canonical caveat appraisal JSON.
     - Per-source validation report.
     - Combined `source_caveat_appraisal_report.json`.
     - Optional targeted re-extraction requests when appraisal identifies missed sections, claim classes, or document-type distinctions.
   - Parallelism:
     - Use `run_parallel` over retained-source caveat appraisal packets so canonical output order remains stable.
     - Use `model_parallelism(backend)` for command/backends that can handle concurrent calls.
     - For local Ollama and other memory-bound backends, use a stage-specific helper modeled on `claim_extraction_parallelism(backend)`: cap heavy full-document caveat appraisal at `min(model_parallelism(backend), 2)` by default, with an override such as `ECM_SOURCE_APPRAISAL_PARALLELISM`.
     - Cheap or bounded caveat packets may use higher shared backend parallelism; expanded/full-document packets should use the capped heavy-appraisal helper.
     - Record effective parallelism, backend, retained-source count, skipped/quarantined count, retry counts, backend errors, and serial fallback counts in `source_caveat_appraisal_report.json`.
   - Validation: Fake-backend tests and parser tests for conforming output, malformed JSON, missing quote evidence, partial repair, and quarantine.
   - QA: Adversarial fixture where a source has official-looking language but missing authorship/funding; the model should flag transparency gaps without inventing hidden motives. Mixed-document fixtures should trigger multiple relevant caveat lenses without collapsing to one false type.
   - Risks: The LLM may over-flag or under-flag caveats. Keep first release in report-only mode and compare against manual case metadata. Running full appraisal too early can suppress useful extraction; keep it after inclusive source-aware extraction except for high-risk overrides.

5. Deterministic Caveat Validation And Impact Rules
   - Purpose: Make model-produced caveats transparent and bounded before they affect evidence routing.
   - Changes:
     - Validate source IDs against the case manifest.
     - Normalize enums and reject appraisals with unsupported values.
     - Apply a stricter validation path for `quarantine` than for `use_with_caution` or `background_only`.
     - Require evidence excerpts or explicit `not_found` records for every nontrivial caveat, use limitation, or suspicious flag.
     - Distinguish `not_found` from negative evidence.
     - Emit deterministic impact fields such as `confidence_cap`, `routing_penalty`, `load_bearing_allowed`, and `review_required`.
   - Artifacts:
     - `source_caveat_validation_report.json`
     - `source_caveat_impact_report.json`
     - rejected/quarantined appraisal records
   - Validation: Tests for deterministic policy:
     - severe uncorroborated source-incentive caveats route to `background_only` or `human_review_needed`.
     - `triage_disposition=quarantine` prevents extraction only when a deterministic quarantine criterion is met.
     - a document with indirect decision relevance cannot become load-bearing support just because it has few caveats.
     - missing transparency should cap confidence or trigger review but not exclude by itself.
     - multiple sources in one `independence_cluster` do not count as fully independent corroboration.
   - QA: Report-only calibration on existing eggs, LHC, and COVID slice cases before blocking any downstream use.
   - Risks: Deterministic policy can encode arbitrary weights. Store rules in one module and report the exact rule that changed routing.

6. Parallel Execution, Retry, And Progress Reporting
   - Purpose: Apply the repo's existing concurrent model-call machinery to the new source-appraisal stages without creating a parallel orchestration system.
   - Changes:
     - Reuse `model_backends.run_parallel` for source triage and caveat appraisal.
     - Reuse `model_parallelism(backend)` and its existing environment overrides: `ECM_MODEL_PARALLELISM` and `ECM_OLLAMA_PARALLELISM`.
     - Add stage-specific helper functions only where needed, following the existing `claim_extraction_parallelism(backend)` pattern for memory-heavy local Ollama calls.
     - Preserve deterministic input order in all output artifacts even when model calls finish out of order.
     - Add progress/report fields matching existing stages: `parallelism`, `backend`, `total_items`, `completed_count`, `backend_error_count`, `retry_count`, `serial_retry_attempt_count`, `serial_retry_recovered_count`, and `serial_retry_failed_count`.
     - Fall back to serial retry for failed heavy appraisals where practical, mirroring whole-document claim extraction behavior.
   - Artifacts:
     - Parallelism fields in `source_triage_report.json`.
     - Parallelism and retry fields in `source_caveat_appraisal_report.json`.
     - Optional progress artifacts such as `source_triage_progress.json` and `source_caveat_appraisal_progress.json` if the stage is long-running.
   - Validation: Tests should assert that parallel source appraisal preserves input order, honors `ECM_MODEL_PARALLELISM`, honors `ECM_OLLAMA_PARALLELISM`, honors the source-appraisal stage override, caps heavy Ollama appraisal by default, and records effective parallelism in reports.
   - QA: Stress-run with a fake backend that returns out of order or fails selected calls; verify stable artifact order, retry accounting, and no dropped source records.
   - Risks: Increasing parallelism can exhaust local Ollama memory or make failures nondeterministic. Keep heavy prompts capped by default and make the effective parallelism visible in every report.

7. Integration With Source Evidence Cards And Quality Reports
   - Purpose: Propagate source-level appraisal into the existing decision-ready context pipeline.
   - Changes:
     - Run early triage before claim extraction.
     - Build a pre-extraction source profile from triage and pass it into claim extraction.
     - Run claim extraction before the full type-specific caveat appraisal for normal retained sources, so the full appraisal can bind caveats to extracted claim types.
     - Run type-specific caveat appraisal before `build_source_evidence_cards`.
     - Support optional targeted re-extraction when caveat appraisal finds missed sections or claim classes that are likely decision-relevant.
     - Enrich source evidence cards with `source_caveat_appraisal_id`, `document_type`, `prompt_lens`, `decision_directness`, `recommended_use`, `interpretation_caveats`, `claim_scope_limits`, and `appraisal_flags`.
     - Upgrade `build_evidence_quality_report` to combine card-level anchoring with source-level caveats and downstream handling rules.
     - Preserve separate components instead of a single opaque score.
   - Artifacts:
     - enriched `source_evidence_cards.json`
     - enriched `evidence_quality_report.json`
     - appraisal-aware `candidate_evidence_cards.json`
   - Validation: Existing context-schema tests should continue to parse old cards; new tests assert enriched fields when appraisal is present.
   - QA: Stage-value report showing how many cards changed routing because of appraisal and why, plus how many extraction prompts were changed by source profiles and whether targeted re-extraction recovered missed claims.
   - Risks: New fields could break consumers. Use schema `extra="allow"` compatibility and keep old required fields stable.

8. Candidate Evidence Routing, Confidence Caps, And Independence
   - Purpose: Make appraisal influence decisions in a transparent, reversible way.
   - Changes:
     - Adjust candidate routing to consider caveat-derived handling rules without hiding their components.
     - Add `caveat_impact` to candidate evidence cards.
     - Ensure `background_only` sources can produce context, source bottom lines, provenance notes, or stakeholder framing, but not default load-bearing claims.
     - Ensure quarantined sources appear in review artifacts with reasons rather than disappearing from the case.
     - Add confidence caps to decision models and final memo warnings when load-bearing evidence has unresolved caveats, indirect relevance, source-incentive concerns, missing transparency, or correlated support.
     - Formalize independence clusters from LLM appraisal and manual metadata.
   - Artifacts:
     - `source_independence_report.json`
     - `appraisal_routing_report.json`
     - confidence-cap reasons in decision synthesis and argument artifacts
   - Validation: Tests for correlated meta-analysis clusters, public summaries, and high-risk/commentary sources.
   - QA: Metamorphic test: reordering sources should not change appraisal routing; duplicating a source should not create independent corroboration.
   - Risks: Penalizing correlated sources can suppress useful consensus. The report should distinguish "not independent" from "not useful."

9. Final Memo Caveat Reasoning Contract
   - Purpose: Ensure source caveats change final reasoning when they affect load-bearing claims, rather than remaining passive metadata or UI warnings.
   - Changes:
     - Add a final-memo evidence-basis artifact that maps each load-bearing memo claim to supporting candidate evidence cards, source IDs, caveats, confidence caps, independence constraints, and allowed source-use roles.
     - Update final memo prompts and/or analyst packet schemas so the model must reason with caveats before drafting conclusions.
     - Require the memo to distinguish claim-level uncertainty, source-level caveats, decision-directness caveats, and independence/corroboration caveats.
     - Require `background_only` sources to be used only for context, provenance, stakeholder framing, or source bottom lines unless a reviewer override is recorded.
     - Require `corroborate_before_use` sources to have independent corroboration before they support a load-bearing claim; otherwise the memo must state that the claim is insufficiently supported.
     - Require the memo to explain why caveated evidence remains useful when unresolved caveats are present in a load-bearing chain.
     - Require independence caveats to prevent the memo from presenting correlated sources as independent confirmation.
     - Require conclusion-level uncertainty or limitations text when the recommendation depends materially on caveat-heavy evidence.
   - Artifacts:
     - `final_memo_evidence_basis.json`
     - `load_bearing_claim_caveat_map.json`
     - `final_memo_caveat_reasoning_report.json`
     - memo prompt fixtures that include caveat-aware evidence packets
   - Validation: Tests assert that final memo generation receives caveat-bearing evidence basis entries and cannot cite background-only or uncorroborated sources as primary support without an explicit override or limitation.
   - QA:
     - Golden memo fixture where an advocacy report supports useful context but cannot serve as independent empirical confirmation.
     - Golden memo fixture where a systematic review and included study share an independence caveat and cannot be counted as two independent supports.
     - Golden memo fixture where a legal allegation is presented as an allegation, not an established finding.
     - Before/after review: caveat-aware memo should make at least one materially more cautious or better-qualified claim in cases with caveat-heavy evidence.
   - Risks: The memo may bury caveats in a generic limitations paragraph while still reasoning as if the evidence is clean. Validation should inspect claim-to-source mappings, not only final prose.

10. UI And Review Packet Surfaces
   - Purpose: Make source trust visible to reviewers and future agents.
   - Changes:
     - Add source caveat warnings to `unseen_quality.source_quality_signals`.
     - Expose document type, prompt lens, interpretation caveats, recommended use, triage disposition, quarantine status, and suspicious flags in UI source rows or quality warnings.
     - Add the new appraisal artifacts to `map_briefing_artifacts.py` and final review packet links.
     - Include source-appraisal summary in run summaries.
   - Artifacts:
     - UI `qualityWarnings` entries for caveat-heavy sources, transparency gaps, source-use exclusions, and human-review-needed appraisals.
     - Final review packet section: "Source Caveats And Evidence Use."
   - Validation: UI-data build tests and existing UI validation should pass.
   - QA: Reviewer can trace a warning from UI -> source appraisal card -> evidence excerpt -> source text.
   - Risks: Too many warnings can drown out useful signals. Prioritize high-risk, excluded, and load-bearing weak-source warnings.

11. Calibration And Golden-Case Evaluation
   - Purpose: Measure whether the automated appraisal stage improves evidence handling rather than just producing more artifacts.
   - Changes:
     - Create small golden fixtures with expected source-identification and caveat-appraisal behavior.
     - Create early-triage fixtures where only obvious trash is quarantined.
     - Create type-specific prompt fixtures for empirical studies, reviews, official guidance, legal/regulatory documents, news reporting, advocacy/vendor reports, commentary, datasets, and transcripts.
     - Create final-memo fixtures where caveats must change claim wording, evidentiary status, or conclusion uncertainty.
     - Add before/after comparisons on at least three case types.
     - Add report-only gates for suspicious-source and weak-evidence handling.
   - Artifacts:
     - `source_caveat_calibration_report.json`
     - golden fixture files
     - before/after appraisal impact notes
   - Validation:
     - Golden cases must match expected high-level document types, prompt lenses, and caveat classes.
     - Existing cases must not lose source anchoring.
     - High-risk or caveat-heavy source fixtures must be flagged with evidence.
     - Clean peer-reviewed/official sources must not be over-caveated or routed away from appropriate use.
   - QA:
     - Adversarial mutation: remove author/funding/method sections and verify transparency downgrade.
     - Adversarial mutation: add promotional language and verify source-risk or suspicious-flag consideration.
     - Adversarial mutation: make a useful contrarian source look informal and verify it is routed to caution/background, not hard quarantine.
     - Metamorphic mutation: paraphrase the decision question without changing its meaning and verify stable source-use labels.
   - Risks: Golden fixtures can overfit. Keep examples domain-diverse and test invariant behavior, not exact prose.

## Execution Order
1. Define schemas, prompt lenses, and example triage/caveat-appraisal artifacts first, so downstream integration has a stable target.
2. Build cheap triage packet assembly and the early LLM triage gate with fake-backend tests, deterministic validation, escalation behavior, existing `run_parallel` orchestration, and report-only quarantine output.
3. Build pre-extraction source profiles and pass them into claim extraction prompts without changing downstream routing.
4. Build the type-specific caveat appraisal module after extraction with fake-backend tests, deterministic validation, existing `run_parallel` orchestration, and a memory-safe heavy-appraisal parallelism helper.
5. Add optional targeted re-extraction requests when caveat appraisal finds missed sections, claim classes, or document-type distinctions.
6. Add progress/retry/parallelism reports for triage and caveat appraisal.
7. Run triage, source-aware extraction, and appraisal in report-only mode on existing cases and compare against manual metadata files.
8. Enrich source evidence cards and evidence-quality reports without changing routing.
9. Add routing impact in report-only mode and inspect stage-value reports.
10. Add the final memo evidence-basis artifact and caveat reasoning contract in report-only mode.
11. Promote calibrated deterministic impact rules into candidate-card routing, confidence caps, and final memo constraints.
12. Add UI/review surfaces and final review packet summaries.
13. Add calibration fixtures, adversarial tests, metamorphic tests, and caveat-aware memo fixtures.
14. Complete with a source-appraisal completion audit.

## Acceptance Criteria
- Every source in a source-grounded case can receive a structured source caveat appraisal or a visible `appraisal_missing` record.
- Every source receives an early triage disposition or visible `triage_missing` record before extraction routing.
- Every early triage decision records `triage_packet_scope`, packet coverage, and whether expanded/full-document triage was considered or triggered.
- Every non-quarantined source receives a pre-extraction source profile or visible `source_profile_missing` record before claim extraction.
- Claim extraction prompts include source profiles and document-type-specific claim cautions when appraisal is enabled.
- Every retained source receives a type-specific prompt lens, or `mixed_or_unknown` with visible rationale when type classification is ambiguous.
- Full caveat appraisal normally runs after inclusive source-aware claim extraction so caveats can be bound to extracted claim types; exceptions must be recorded as high-risk overrides.
- Targeted re-extraction requests are visible when caveat appraisal identifies likely missed decision-relevant sections, claim classes, or document-type distinctions.
- The pipeline writes prompt, raw output, canonical output, validation report, and combined `source_caveat_appraisal_report.json`.
- The pipeline writes per-source `source_triage_packet.json`, `source_triage_report.json`, and `quarantined_sources.json` when early triage is enabled.
- Triage and caveat appraisal use the repo's shared `run_parallel`/`model_parallelism` pattern and preserve source-manifest order in canonical artifacts.
- Triage and caveat appraisal reports record effective parallelism, backend, item counts, backend errors, retries, and serial fallback counts where applicable.
- Heavy full-document caveat appraisal on local Ollama is capped by default using a stage-specific helper modeled on `claim_extraction_parallelism`, with an explicit stage override for users who have enough memory.
- No appraisal can be accepted if it uses an unknown source ID or unsupported enum value.
- No source can be quarantined unless a deterministic quarantine criterion is satisfied and the reason is visible in review artifacts.
- No source can be quarantined from the cheap packet alone unless the reason is deterministic empty/unreadable text, duplicate/near-duplicate evidence, unavailable source text, or obvious irrelevant/spam evidence visible in the packet; all subtler quarantine candidates must escalate or route to review/caution.
- Every interpretation caveat, suspicious flag, use limitation, or review flag includes source evidence, source metadata evidence, or an explicit `not_found` transparency record.
- The second pass does not emit aggregate document-quality scores; downstream routing uses explicit caveats and deterministic rules.
- Enriched `source_evidence_cards.json` and `evidence_quality_report.json` preserve existing fields while adding appraisal context.
- Candidate evidence routing explains any routing change, confidence cap, or appendix/background-only routing caused by source caveats.
- Every load-bearing final memo claim has a `final_memo_evidence_basis` entry listing supporting source IDs, caveats, confidence caps, independence status, and whether each source is allowed to support that claim.
- No final memo may use a `background_only` source as primary support without an explicit reviewer override recorded in the evidence basis.
- No final memo may use a `corroborate_before_use` source as load-bearing support without independent corroboration or an explicit statement that the claim remains insufficiently supported.
- If final recommendations depend on caveat-heavy evidence, the final memo must surface the relevant caveats in the reasoning or limitations section rather than only in source metadata.
- UI/review packets expose caveat-heavy, excluded, human-review-needed, and load-bearing weak-source warnings.
- Report-only calibration runs on eggs, LHC, and COVID slice cases before any new gate becomes blocking.
- Existing tests pass, plus new tests for schemas, parsing, validation, source-aware extraction prompts, targeted re-extraction requests, parallelism/order preservation, stage parallelism overrides, routing, final memo evidence-basis behavior, UI warnings, and adversarial source fixtures.

## Red-Team Checks
- Failure: The model invents conflicts of interest or source motives.
  - Detection: Validation requires evidence excerpts or `not_found`; unsupported claims are quarantined.
- Failure: The model treats caveat discovery as an implicit quality score.
  - Detection: Schema rejects aggregate quality-score fields; review packets show caveats and deterministic handling rules instead of document grades.
- Failure: The first pass chooses the wrong document type, causing the wrong caveat prompt to run.
  - Detection: Store `document_type_alternates`; low-confidence or mixed classifications use a mixed prompt and require review on load-bearing sources.
- Failure: The model mistakes "disagreeable conclusion" for suspicious source.
  - Detection: Prompt separates source risk from stance; tests include credible sources with opposing conclusions.
- Failure: The early gate falsely quarantines useful adversarial or minority evidence.
  - Detection: Quarantine requires deterministic criteria; contrarian-source fixtures must route to `use_with_caution` or `background_only`, not `quarantine`.
- Failure: Cheap triage saves tokens by under-reading documents and misclassifying sources.
  - Detection: Packet coverage is recorded; low-confidence, mixed, possible-quarantine, high-leverage, and poor-extraction cases must escalate to expanded or full-document triage.
- Failure: Cheap snippets omit the section that would have changed the document type or disposition.
  - Detection: Golden fixtures place decisive type/provenance signals in non-opening sections; stable beginning/middle/end snippets plus heading/summary/conclusion extraction must catch or escalate them.
- Failure: Source appraisal uses an ad hoc concurrency mechanism that diverges from the rest of the repo.
  - Detection: Tests import `model_parallelism` and `run_parallel`, assert env override behavior, and assert order preservation for triage/appraisal outputs.
- Failure: Parallel caveat appraisal exhausts local Ollama memory.
  - Detection: Heavy full-document appraisals default to an Ollama cap, reports record effective parallelism, and stress tests include a memory-bound/failing fake backend.
- Failure: Parallel execution changes artifact order or drops failed sources.
  - Detection: Fake backend returns out of order and fails selected calls; reports must preserve manifest order and include missing/error records.
- Failure: Putting full caveat appraisal before extraction suppresses useful claims too early.
  - Detection: Default pipeline keeps full caveat appraisal after inclusive source-aware extraction; any pre-extraction full appraisal override must be recorded with a high-risk reason and compared against claim recall.
- Failure: Pre-extraction source profiles make extraction too conservative.
  - Detection: Extraction fixtures compare baseline versus source-aware extraction and require preserved useful-claim recall while reducing document-type misuse errors.
- Failure: Post-extraction caveat appraisal finds extraction missed important sections but nothing acts on it.
  - Detection: `source_caveat_appraisal_report.json` can emit targeted re-extraction requests, and stage-value reports count whether those requests recovered claims or were deferred.
- Failure: A public explainer is treated as primary evidence.
  - Detection: Evidence proximity and decision-use rules route explainers to context unless independently corroborated.
- Failure: A systematic review and its included studies are counted as independent support.
  - Detection: Independence cluster report and duplicated-underlying-evidence warnings.
- Failure: A low-caveat but indirect source becomes load-bearing.
  - Detection: `decision_directness=indirect` caps candidate role and confidence.
- Failure: The final memo receives caveats but reasons as if the sources are clean.
  - Detection: `final_memo_caveat_reasoning_report.json` checks each load-bearing claim for caveat-aware wording, allowed source use, confidence caps, and independence constraints.
- Failure: The memo buries source problems in a generic limitations paragraph.
  - Detection: Claim-to-source validation requires relevant caveats to appear near the affected claim, in the claim rationale, or in an explicit conclusion-level uncertainty statement.
- Failure: A background-only or uncorroborated source becomes primary evidence in the final memo.
  - Detection: Final memo evidence-basis validation rejects unsupported primary-use roles unless a reviewer override is present.
- Failure: New warnings create alert fatigue.
  - Detection: UI warning counts and review packet prioritization; only high-risk or load-bearing weak-source issues are top-level.
- Failure: Quarantined sources disappear from the case record.
  - Detection: `quarantined_sources.json`, UI/review warnings, and run summaries must list all quarantined sources and reasons.
- Failure: The source-appraisal stage passes schema tests but does not improve decisions.
  - Detection: Stage-value reports compare before/after routing, confidence caps, and reviewer-visible source caveats.

## Generalizability Checks
- The prompt-lens system must work for clinical studies, legal/regulatory documents, policy briefs, financial models, vendor reports, news explainers, narrative reviews, transcripts, and raw data/official records.
- Prompts must use generic caveat-discovery language, not case-specific vocabulary.
- Domain-specific frameworks such as GRADE, AMSTAR 2, PRISMA, AGREE II, CASP, SIFT, and CRAAP can be referenced as optional caveat lenses, not as required universal fields.
- Appraisal should be stable under source order changes, duplicate source insertion, and harmless source-title changes.
- Early triage should quarantine exact duplicates or obvious junk, but should route weak-looking useful material to `background_only` or `use_with_caution`.
- Cheap triage should classify obvious cases without reading the full document, while ambiguous, high-impact, mixed, or possible-quarantine cases escalate before affecting extraction.
- Appraisal should change when real provenance, method, transparency, or directness information is removed.
- Unseen-case tests should include at least one suspicious/advocacy source, one official-but-indirect source, one strong primary source, and one synthesis source with independence risk.

## Canonical Ledger
Track implementation progress in a ledger that survives multiple commits:

| Slice | Status | Primary Artifact | Verification | Notes |
| --- | --- | --- | --- | --- |
| Schema, prompt lenses, and examples | planned | `source_caveat_appraisal_report` schema | schema unit tests | Keep backward compatibility and avoid aggregate quality scores. |
| Cheap triage packet and early gate | planned | `source_triage_packet`, `source_triage_report`, and `quarantined_sources` | fake-backend, packet coverage, escalation, parallelism, and quarantine policy tests | Use shared `run_parallel`; quarantine is rare, reversible, and not based on under-reading. |
| Pre-extraction source profile | planned | `pre_extraction_source_profile` and `claim_extraction_source_profiles` | extraction prompt and claim-role tests | Improve extraction without suppressing useful claims. |
| Type-specific caveat appraisal stage | planned | per-source caveat artifacts | fake-backend parser and parallelism tests | Use shared `run_parallel`; cap heavy Ollama prompts by default; report-only first. |
| Targeted re-extraction loop | planned | re-extraction requests in caveat reports | missed-section and recovered-claim tests | Optional loop only when appraisal finds likely extraction gaps. |
| Parallel execution and retry reporting | planned | progress and parallelism fields in triage/appraisal reports | order preservation, env override, stage override, retry tests | Reuse repo model backend parallelism. |
| Validation and impact rules | planned | validation and impact reports | deterministic policy tests | No silent routing changes. |
| Context integration | planned | enriched source/cards reports | context schema tests | Preserve old fields. |
| Routing and confidence caps | planned | appraisal routing report | before/after tests | Calibrate before blocking. |
| Final memo caveat reasoning | planned | `final_memo_evidence_basis` and `load_bearing_claim_caveat_map` | memo evidence-basis tests | Caveats must constrain load-bearing claims. |
| UI and review packets | planned | quality warnings/review section | UI-data validation | Prioritize load-bearing risks. |
| Calibration and completion audit | planned | calibration report/audit | golden/adversarial/metamorphic tests | Required before closure. |

## Deferred-Work Policy
- If a document-type-specific rubric is useful but not general enough, record it as a future optional prompt lens rather than embedding it in the core schema.
- If model appraisals are noisy, keep routing in report-only mode and improve prompts or validation before using the outputs.
- If early triage is noisy, disable quarantine impact and keep triage dispositions report-only until calibrated.
- If cheap triage packet coverage is inadequate, escalate that source to expanded/full-document triage or emit `human_review_needed`; do not silently accept low-coverage quarantine or exclusion.
- If final memo caveat integration is noisy, keep caveat-aware memo constraints report-only and emit a reviewer-visible memo-risk report instead of silently changing recommendations.
- If source text is too long for the backend, emit a visible appraisal coverage limit and appraise a deterministic source packet rather than silently truncating.
- If funding/conflicts/authorship are absent, record `not_found`; do not infer misconduct or neutrality.
- Any deferred item must name the affected artifact, risk, owner stage, and whether final synthesis is still allowed.

## Final Review Packet
The plan is complete only when a final audit packet exists with:

- Summary of implemented source-appraisal stages and artifacts.
- Summary of early triage dispositions, quarantined sources, and override policy.
- Before/after examples showing caveat appraisal changed or confirmed evidence use.
- Examples of type-specific prompt lenses discovering different caveats for different document types.
- Examples showing final memo claims changed, qualified, or declined because of source caveats.
- Audit of load-bearing final memo claims against `final_memo_evidence_basis.json`.
- Calibration results on existing cases.
- Golden/adversarial/metamorphic test results.
- Known false-positive and false-negative risks.
- Examples of reviewer traceability from final warning to source excerpt.
- Recommendation for whether appraisal impact rules should remain report-only or become blocking.
