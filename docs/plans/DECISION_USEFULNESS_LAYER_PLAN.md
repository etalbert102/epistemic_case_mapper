# Plan: Decision Usefulness Layer

## Objective

Make the final briefing more decision-useful than a strong Deep Research baseline by turning the current evidence-weighted memo pipeline into an explicit decision-support pipeline.

The target end state is not just a readable evidence synthesis. It is a decision instrument that tells a reader:

- what options or stances are live;
- what criteria matter for choosing among them;
- which evidence distinguishes the options;
- what tradeoffs or value judgments drive the recommendation;
- what would change the answer;
- what monitoring or next-evidence triggers should update the decision.

This plan draws on decision-quality practice, GRADE Evidence-to-Decision, multi-criteria decision analysis, Analysis of Competing Hypotheses, decision hygiene, and premortem reasoning. The implementation should remain general across decision questions rather than tuned to the eggs case.

## Current Gap

The current pipeline can produce a coherent, source-weighted memo with traceability and useful evidence-quality caveats. Its main limitation is that it still mostly competes with Deep Research as a synthesis system.

Deep Research may still win on prose and source collection. The prototype should instead win on decision quality: explicit options, criteria, tradeoffs, diagnostic evidence, cruxes, and update triggers.

The active production path now runs roughly:

1. Source documents and decision question.
2. Whole-document source map extraction.
3. Claim consolidation and relation building.
4. Analyst evidence ledger.
5. Analyst adjudication.
6. Analyst decision model.
7. Global decision model.
8. Decision writer packet.
9. Memo-ready packet with `canonical_decision_writer_packet_v1`.
10. Lightweight writer guidance.
11. Memo-ready synthesis.
12. Retention repair, final polish, deterministic presentation, sources, and citation trace.

The missing layer belongs after the canonical packet exists and before final synthesis.

## Non-Goals

- Do not change source collection or source extraction in this plan.
- Do not add domain-specific vocabularies for health, nutrition, infrastructure, or any specific case.
- Do not let deterministic code make semantic decisions about which option is best.
- Do not add a second parallel memo pipeline.
- Do not expose old debug surfaces directly to the final synthesis prompt.
- Do not make new quality gates blocking until their signal is calibrated.
- Do not weaken source IDs, citation traceability, or retention validation to improve prose.

## Design Principles

- Use the active canonical packet as the semantic substrate.
- Models make semantic judgments about options, criteria, tradeoffs, cruxes, and premortems.
- Deterministic code compiles, validates, preserves IDs, audits coverage, and formats artifacts.
- Classical ML/statistics can rank, cluster, and detect coverage gaps without deciding meaning.
- The final synthesis prompt should receive a compact decision-usefulness packet, not many overlapping plans.
- Every new semantic object must preserve source IDs and evidence item IDs.
- QA must measure decision usefulness, not just artifact existence.

## Holistic Pipeline Review

### What The Initial Plan Got Right

- The right integration target is the active canonical writer path, not the older section-first or map-only paths.
- The strongest product move is to make tradeoffs, cruxes, diagnosticity, and update triggers explicit.
- The final memo should be synthesized from a structured decision packet rather than asked to discover decision logic from source summaries.

### What The Initial Plan Was Missing

1. Existing option/crux machinery already exists, but appears to live mostly in older scaffold paths.
   - `build_option_comparison`, `build_crux_contract`, evidence slots, and memo slot repair already have tests.
   - These should be inventoried and reused as inputs or fixtures where appropriate.
   - They should not be blindly exposed to the active final synthesis context.

2. The active semantic owner is now `canonical_decision_writer_packet_v1`.
   - The new layer should attach to the canonical packet and memo-ready packet.
   - It should not bypass `global_decision_model` or `decision_writer_packet`.

3. The pipeline already has source weighting and lightweight writer guidance.
   - The decision-usefulness layer should consume these, not duplicate them.
   - Lightweight guidance should remain about wording and reader-facing caveats; the new layer should own options, criteria, tradeoffs, cruxes, and monitoring triggers.

4. The current final prompt is intentionally compact.
   - Adding the new layer could re-pollute model context if the packet is too large.
   - The prompt should receive a compact `decision_usefulness_for_prompt` projection.

5. Validation must distinguish "decision structure present" from "decision support genuinely useful."
   - A bureaucratic option matrix can make the memo worse.
   - Acceptance must include human-readable memo quality and comparison against direct source synthesis.

6. Some questions are not multi-option decisions.
   - The layer must support factual, classificatory, policy, operational, and threshold questions.
   - It should not force artificial options when the right answer shape is a bounded factual read.

7. Decision usefulness can fail upstream.
   - If the analyst decision model lacks a stable answer frame, the new layer will have weak inputs.
   - The plan needs telemetry that attributes failure to upstream answer frame, option inference, criteria inference, matrix sparsity, synthesis nonuse, or final prose.

## Proposed Artifact

Add `decision_usefulness_packet_v1`.

Suggested shape:

```json
{
  "schema_id": "decision_usefulness_packet_v1",
  "decision_question": "...",
  "answer_shape": "single_stance|multi_option|threshold|classification|insufficient_information",
  "recommended_stance": {
    "stance": "...",
    "confidence": "...",
    "scope": "...",
    "why_this_stance": "...",
    "source_ids": [],
    "evidence_item_ids": []
  },
  "decision_options": [
    {
      "option_id": "option_001",
      "label": "...",
      "description": "...",
      "status": "live|dominated|insufficiently_supported|context_only",
      "source_ids": [],
      "evidence_item_ids": []
    }
  ],
  "decision_criteria": [
    {
      "criterion_id": "criterion_001",
      "label": "...",
      "why_it_matters": "...",
      "criterion_type": "benefit|harm|certainty|scope|feasibility|cost|values|equity|implementation|other",
      "source_ids": [],
      "evidence_item_ids": []
    }
  ],
  "option_criteria_matrix": [
    {
      "option_id": "option_001",
      "criterion_id": "criterion_001",
      "assessment": "favors|weakens|mixed|uncertain|not_applicable",
      "rationale": "...",
      "source_ids": [],
      "evidence_item_ids": []
    }
  ],
  "diagnostic_evidence": [
    {
      "evidence_item_ids": [],
      "source_ids": [],
      "distinguishes": ["option_001", "option_002"],
      "diagnosticity": "high|medium|low",
      "why_diagnostic": "..."
    }
  ],
  "tradeoffs": [
    {
      "tradeoff": "...",
      "choose_a_if": "...",
      "choose_b_if": "...",
      "source_ids": [],
      "evidence_item_ids": []
    }
  ],
  "cruxes_and_thresholds": [
    {
      "crux": "...",
      "current_read": "...",
      "would_change_if": "...",
      "threshold": "...",
      "source_ids": [],
      "evidence_item_ids": []
    }
  ],
  "premortem": [
    {
      "failure_mode": "...",
      "why_plausible": "...",
      "mitigation_or_monitoring": "...",
      "source_ids": [],
      "evidence_item_ids": []
    }
  ],
  "monitoring_triggers": [
    {
      "trigger": "...",
      "would_update": "...",
      "priority": "high|medium|low",
      "source_ids": [],
      "evidence_item_ids": []
    }
  ]
}
```

## Mechanism Split

### Model Work

Use a model for:

- inferring answer shape;
- generating live options or stances;
- deriving decision criteria;
- deciding whether evidence is diagnostic between options;
- formulating tradeoffs and crux thresholds;
- producing premortem failure modes and monitoring triggers;
- turning the packet into natural decision-ready prose.

### Deterministic Code

Use code for:

- schema validation with Pydantic;
- ID validation against canonical packet evidence/source registries;
- deduplicating repeated options or criteria by stable normalized labels;
- computing coverage counts;
- attaching reports and artifacts;
- compacting the packet for final synthesis;
- preserving deterministic source lists and citation trace.

### Classical ML / Statistics

Use classical methods for:

- option/criterion/evidence similarity hints;
- near-duplicate option and criterion detection;
- centrality or diagnosticity priors from relation/evidence graphs;
- matrix sparsity and coverage summaries;
- ranking candidate evidence for model attention.

## Workstreams

### 1. Active Path Inventory

Purpose: prevent duplicate or legacy architecture.

Changes:

- Inventory old option/crux/evidence-slot utilities.
- Classify each as active input, reusable helper, regression fixture, diagnostic-only, or legacy.
- Document exact handoff from `canonical_decision_writer_packet_v1` to the new layer.

Artifacts:

- `decision_usefulness_inventory_report.json`

Validation:

- Report identifies all current option/crux utilities and their status.

QA:

- Test that the final synthesis prompt does not expose legacy `option_comparison` or `crux_contract` unless compiled into the new packet.

Risks:

- Hidden dependencies in older tests may imply behavior that is not active in production.

### 2. Schema And Validators

Purpose: make the new layer inspectable and safe.

Changes:

- Add Pydantic schema for `decision_usefulness_packet_v1`.
- Add validator/report builder.
- Validate source IDs and evidence item IDs against the canonical packet.
- Validate option/criterion matrix references.

Artifacts:

- `decision_usefulness_packet.json`
- `decision_usefulness_quality_report.json`

Validation:

- Invalid IDs become warnings or rejected rows.
- Missing criteria/options are reported, not silently backfilled.

QA:

- Golden fixture with options, criteria, matrix cells, tradeoffs, cruxes, premortem rows, and monitoring triggers.

Risks:

- Overly rigid validation rejects useful model output.

### 3. Deterministic Context Builder

Purpose: give the model only the relevant context.

Changes:

- Build a compact input from canonical packet fields:
  - decision question;
  - answer classification;
  - decision brief skeleton;
  - source weight judgments;
  - evidence-weighted argument spine;
  - priority evidence;
  - counterweight dispositions;
  - scope boundaries;
  - decision cruxes;
  - organized evidence inventory.
- Add optional hints from existing option/crux utilities only if available and source-grounded.

Artifacts:

- `decision_usefulness_context.json`
- `decision_usefulness_prompt.txt`

Validation:

- Context contains source IDs and evidence IDs but not debug reports, parse errors, raw prompts, or old memo plans.

QA:

- Model context audit flags no raw debug/audit pollution.

Risks:

- Too much context can make the model produce generic matrices.

### 4. Model Decision-Usefulness Builder

Purpose: create the semantic decision-support artifact.

Changes:

- Add a model call after canonical packet creation and before lightweight guidance.
- Return JSON only.
- Retry once with repair prompt on schema or ID failures.
- If model fails, emit transparent `not_available` report instead of deterministic semantic backfill.

Artifacts:

- `decision_usefulness_raw.txt`
- `decision_usefulness_parse_report.json`
- `decision_usefulness_repair_prompt.txt`
- `decision_usefulness_repair_raw.txt`

Validation:

- At least one of these must be present for a useful packet:
  - live options;
  - explicit answer threshold;
  - tradeoff;
  - diagnostic evidence row;
  - monitoring trigger.

QA:

- Prompt-backend path creates context and prompt but does not fake semantic judgments.

Risks:

- The model produces generic options like "do nothing" when not decision-relevant.

### 5. Prompt Projection

Purpose: make final synthesis use the decision model without bloating context.

Changes:

- Add `compact_decision_usefulness_for_prompt`.
- Include compact packet in `_reader_synthesis_packet`.
- Modify final synthesis prompt to write a decision memo that includes:
  - option or stance comparison when available;
  - why the recommended stance wins;
  - tradeoff and crux thresholds;
  - monitoring/update triggers;
  - source IDs near claims.

Artifacts:

- `memo_ready_packet_synthesis_prompt.txt` should contain `decision_usefulness`.

Validation:

- Prompt contains compact `decision_usefulness` but not raw model output.

QA:

- Test final prompt includes decision-usefulness fields when present and omits them when unavailable.

Risks:

- More structure may make prose stiff. The prompt should ask for natural decision-ready prose, not a full matrix dump.

### 6. Memo Presentation And Traceability

Purpose: keep reader-facing output polished and auditable.

Changes:

- Do not automatically insert a full option matrix into the memo.
- Let the model write tradeoffs naturally.
- Deterministically link any cited source IDs.
- Optionally add a compact "Decision Logic Trace" artifact separate from the memo.

Artifacts:

- `DECISION_LOGIC_TRACE.md`

Validation:

- Human can trace a memo tradeoff back to packet rows and source IDs.

QA:

- Citation trace and decision trace both resolve source IDs.

Risks:

- Too many traces can overwhelm judges; keep memo readable and traces optional.

### 7. Telemetry And Stage Value

Purpose: attribute quality failures.

Changes:

- Add stage to runtime and stage-value reports.
- Track:
  - option count;
  - criterion count;
  - matrix cell count;
  - diagnostic evidence count;
  - tradeoff count;
  - crux threshold count;
  - monitoring trigger count;
  - invalid model row count;
  - unsupported option count;
  - criteria with no evidence.

Artifacts:

- `decision_usefulness_stage_value_report.json`

Validation:

- Failures are visible as warnings, not hidden fallbacks.

QA:

- Empty or generic packet is flagged even if syntactically valid.

Risks:

- Metrics can reward verbosity; cap rows and score diagnosticity, not just count.

### 8. Evaluation Against Deep Research And Raw Synthesis

Purpose: prove the change improves decision usefulness.

Changes:

- Add comparison rubric focused on decision support:
  - live options visible;
  - criteria visible;
  - tradeoff visible;
  - diagnostic evidence visible;
  - crux/update threshold visible;
  - practical action guidance visible;
  - source traceability preserved;
  - prose remains readable.

Artifacts:

- `decision_usefulness_comparison_report.json`
- `decision_usefulness_eval.md`

Validation:

- Compare:
  - current packet memo without decision-usefulness layer;
  - new packet memo with decision-usefulness layer;
  - raw source synthesis baseline;
  - saved Deep Research baseline.

QA:

- Blind or semi-blind side-by-side review where possible.

Risks:

- The new memo may pass structural metrics but lose on readability. This must be treated as a failed slice.

## Execution Order

1. Inventory active/legacy decision utilities and record how they fit the current canonical path.
2. Add schema, validation, and empty report-only artifact path.
3. Add deterministic context builder from canonical packet.
4. Add model builder and repair loop.
5. Attach packet to memo-ready and canonical packet.
6. Add artifact specs, telemetry, and stage-value reporting.
7. Add compact prompt projection and synthesis prompt changes.
8. Run saved-artifact vertical slice on eggs.
9. Run one unseen or non-health case.
10. Compare against raw synthesis and Deep Research baseline.
11. Only then consider making the layer mandatory in default live runs.

## Acceptance Criteria

- `decision_usefulness_packet.json` is produced after the canonical writer packet.
- The packet contains valid source IDs and evidence item IDs or reports rejected rows.
- Final synthesis prompt includes compact decision-usefulness context.
- The final memo improves decision-usefulness comparison versus the current memo on at least:
  - option/stance clarity;
  - tradeoff clarity;
  - crux/update threshold clarity.
- The memo does not regress on:
  - source grounding;
  - citation traceability;
  - readable prose;
  - final evaluation status.
- Relevant regression tests pass.
- A saved-artifact live model evaluation documents the before/after memo quality.

## Red-Team Checks

- Does the layer hallucinate options not supported by the question or evidence?
- Does it force multi-option framing onto factual questions?
- Does it bury the memo in matrix-like structure?
- Does it duplicate source-weighting and lightweight guidance?
- Does synthesis ignore the new packet?
- Do validators reward generic but useless tradeoffs?
- Does failure become invisible because a deterministic fallback fills fields?
- Does the plan improve only the eggs case?

## Generalizability Checks

Test at least three decision shapes:

- Health/nutrition advice, such as eggs and cardiovascular risk.
- Policy or infrastructure choice, such as facility closure or transit design.
- Technical/product decision, such as adopting a backend or architecture.

Metamorphic checks:

- Reordering evidence should not change option IDs or recommendation.
- Renaming sources should not change semantic option/criteria judgments.
- Removing a diagnostic source should reduce diagnostic evidence coverage and trigger a warning.
- A factual question should not be forced into fake alternatives.
- A multi-option question should not collapse into a single evidence summary.

## Completion Audit

The implementation is complete only when there is a final audit containing:

- implementation commit list;
- artifact path examples;
- prompt excerpts showing compact context;
- before/after memo comparison;
- source ID validation report;
- decision-usefulness quality report;
- known residual weaknesses;
- explicit decision on whether the layer should be default, optional, or report-only.
