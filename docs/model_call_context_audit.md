# Model Call Context Audit

Date: 2026-07-15

This audit checks whether each production model-call family is receiving the right semantic context for its job. The target policy is:

- Extraction calls get source-local evidence plus the decision question, not downstream memo roles.
- Relation calls get pair-local claim cards, exact evidence anchors, relation semantics, and the decision question, not the full map.
- Analyst calls get compact evidence ledgers, answer-frame state, quantities, source quality, and obligations, not raw source documents or writer-facing prose.
- Writer calls get a reader synthesis packet or section-local packet, not broad scaffold/debug artifacts.
- Repair and polish calls get the current output plus only the missing obligations or local guardrails needed to repair the output.
- Deterministic validation can verify and route, but should not silently replace failed model judgment with weaker semantic substitutes.

## Summary

The current pipeline is mostly aligned with the intended split. Whole-document claim extraction, claim consolidation, relation building, analyst adjudication, analyst decision modeling, and section-local synthesis all receive context that is close to ideal for their task. The main risks are concentrated in repair, critique, and polish calls, where the model sometimes receives a large packet or validator-oriented fields that are less useful than a smaller task packet.

Highest priority follow-ups:

1. Replace any remaining semantic fallback/retry downgrade behavior with fail-loud reports or targeted retries.
2. Keep final repair/polish prompts narrow: current memo plus missing obligations, source IDs, protected quantities, and local guardrails only.
3. Expand `model_context_audit.json` so it records upstream map-building prompts, not only final writer prompts.
4. Remove duplicated relation prompt text and keep candidate-routing metadata clearly labeled as routing context, not evidence.
5. Audit packet critique value: it is useful only if its output changes writer-facing guidance or packet construction.

## Production Model Calls

| Stage | Files | Current model context | Verdict | Notes / action |
| --- | --- | --- | --- | --- |
| Whole-document claim extraction | `staged_semantic_whole_doc.py` | One source document with line numbers, source ID/title, decision question, max claim cap, JSON schema. | Good | This is the right place to spend context. It avoids downstream support/counterweight labels and asks for relevance and importance only. |
| Whole-document schema repair | `staged_semantic_whole_doc.py` | Raw extraction, source ID, decision question, output schema. | Good | Correctly schema-focused. It should not receive full source text unless factual repair is desired; current role is reformatting only. |
| Claim consolidation | `staged_semantic_claim_consolidation.py` | Vector-neighbor cluster claim cards, decision question, merge rules. | Good | The model gets only plausible duplicate clusters. Deterministic guards reject over-broad numeric/directional merges. Parse failures are reported by cluster rejection rather than silently changing claims. |
| Relation role prep | `staged_semantic_decision_edges.py` | Claim list plus decision question; asks for relation-building roles before candidate selection. | Adequate, watch size | This can become broad when many claims survive. It is still semantically appropriate because the model is making routing judgments. If runs grow large, split by source/role family and merge deterministically. |
| Relation pair / batch classification | `staged_semantic_sources.py`, `staged_semantic_relation_batches.py` | Pair-local claim cards, exact quotes, relation intent, relation ontology, case and decision question. | Good | Context is appropriately local. Minor cleanup: relation rules duplicate "Fill the relation evidence contract". Candidate score/reason are present but explicitly marked routing metadata. |
| Relation singleton retry after batch failure | `staged_semantic_quality.py`, `staged_semantic_claims_relations.py` | Same pair-local prompt as relation classification. | Context good, policy questionable | This is a retry decomposition, not a semantic fallback, but names and reports still call it fallback. It should be reframed as batch-failure retry and fail loudly when singleton retries fail. |
| Whole-map quality repair | `staged_semantic_map_repair_loop.py` | Candidate map and quality report. | Risky / optional | This is broad and more likely to create semantic drift than targeted repairs. Keep disabled by default or constrain to targeted missing relation/claim repair. |
| Source appraisal | `map_briefing_source_appraisal.py` | One source appraisal packet with source-card excerpts and quality components. | Good | Source-local context is ideal. It avoids deciding the final answer. |
| Model source weighting | `map_briefing_model_source_weighting.py` | One source-local evidence context, decision question, source evidence items. | Good | This is an appropriate per-source judgment call. Good use of model intelligence without full packet overload. |
| Analyst evidence adjudication | `map_briefing_analyst_adjudication.py` | Evidence ledger rows with decision question, stable answer frame, source quality summary, quantities, relation contracts for decision edges. | Good | This is one of the highest-value calls. Context is compact and semantically relevant. Watch for negative instructions accumulating, but the fields are right. |
| Analyst quantity binding | `map_briefing_analyst_quantity_binding.py` | Only quantity candidates requiring model adjudication, decision question, deterministic candidate report. | Good | Good split: deterministic extraction creates candidates; model judges memo relevance and interpretation. Ensure candidate rows include enough claim/group context for ambiguous quantities. |
| Analyst decision model, global or parallel | `map_briefing_analyst_decision_modeling.py`, `map_briefing_analyst_decision_model_parallel.py` | Evidence rows, stable answer frame, obligations/skeleton, quantities, model hints, adjudication. | Good, high leverage | Correct place for global semantic judgment. Recent schema-clean ranking guard is good: diagnostics stay in report, not model payload. |
| Analyst decision model repair | `map_briefing_analyst_decision_repair.py` | Current model summary plus omitted/missing evidence rows. | Good | This is targeted and avoids handing the full ledger back to the model. Keep repair rows compact but include enough source/quantity context. |
| Analyst packet refinement | `map_briefing_analyst_refinement.py` | Synthesis packet plus warning packet. | Medium risk | Useful when warnings are specific. Risk is that warning packets can become validator-shaped rather than writer-shaped. Prefer targeted warning rows with source-bound evidence and desired memo function. |
| Packet critique / refinement, single-call path | `map_briefing_packet_refinement.py` | Packet summary plus sufficiency report; refinement gets accepted critique/adjudication. | Medium risk | Context is compacted, but the critique may spend inference generating warnings that do not alter packet construction. Keep only if its output changes guidance or packet fields. |
| Packet critique, parallel path | `map_briefing_packet_parallel_critique.py` | Local shard summaries, global compact critique view, targeted verification packets. | Good architecture, value depends on output use | The sharded/global/verification structure is context-sane. The value issue is downstream use, not context. If repeated critiques recur without changes, convert critique into writer guidance or remove it from default live path. |
| Decision usefulness | `map_briefing_decision_usefulness.py` | Canonical decision context: answer classification, skeleton, source weighting, argument spine, priority evidence, cruxes, inventory. | Good | This is a good global call because it builds decision support structure rather than prose. The repair prompt is broad but grounded; watch for initial_packet plus context duplication. |
| Reader packet verbalization | `map_briefing_reader_packet_verbalization.py` | Evidence cards with protected numbers and accepted source labels. | Good but optional | Local card wording is a good model task. It should use source IDs or citation keys consistently rather than labels if downstream citation normalization remains fragile. |
| Lightweight writer guidance | `map_briefing_lightweight_guidance.py` | Compact canonical packet evidence, source weighting, priority evidence, boundaries, cruxes, quality summary, quantity summary. | Good | Strong use of a cheap model pass: asks for guidance, not memo rewriting. Avoid exposing packet keys as reader-facing wording. |
| Memo-ready section synthesis | `map_briefing_memo_ready_section_synthesis.py`, `map_briefing_memo_ready_prompt.py` | One section-local writing packet, known source IDs, section role contract, section retention requirements, protected quantity sets. | Good | This is the right synthesis decomposition. The prompt is long but task-specific. Source IDs are intentionally model-visible because the output needs citations. |
| Whole memo synthesis | `map_briefing_memo_ready_finalization.py`, `map_briefing_memo_ready_prompt.py` | Reader synthesis packet derived from canonical writer packet. | Good fallback path, not ideal default if sections work | The packet is compact, but whole-memo synthesis asks the model to solve planning, retention, source binding, and prose at once. Prefer section synthesis plus final polish. |
| Decision-usefulness memo repair | `map_briefing_memo_ready_finalization.py` | Current memo plus missing decision-support rows. | Good | This is appropriately narrow. It should not receive the full packet. |
| Memo-ready packet repair | `map_briefing_memo_ready_finalization.py` | Current memo plus missing obligations, balance cards, canonical repair items, unresolved warnings, source trail projected to IDs. | Good with size watch | This is the right context shape. Keep the limit small and prioritize missing critical obligations over broad warning lists. |
| Final polish, JSON edit path | `map_briefing_memo_json_polish.py`, `map_briefing_memo_ready_finalization.py` | Current memo, guardrails, prose diagnostics. | Good | This is safer than broad rewrite because exact edits can be validated. Guardrails should stay compact and avoid broad packet dump. |
| Paragraph/section polish experiments | `map_briefing_memo_paragraph_polish.py`, `map_briefing_memo_section_polish.py`, `map_briefing_memo_polish_experiments.py` | Selected paragraph/section plus packet-derived checks. | Experimental | These are useful for exploration, but production should use one polish path to avoid redundant model calls and conflicting edits. |
| Spine arbitration | `map_briefing_spine_arbitration.py` | Decision spine only. | Fine / low impact | Local enough. It should stay optional because later analyst model has richer context. |
| Config profile selection | `config_profiles.py` | Case text/profile candidates. | Fine / not memo-critical | This is upstream configuration help. It should never inject domain vocabulary into prompts beyond selected generic profile semantics. |

## Context Gaps To Fix

### 1. Upstream prompts are not covered by the run-level audit

`model_context_audit.json` currently records final writer prompts and selected scaffold prompts. It does not systematically summarize source extraction, consolidation, relation role prep, relation classification, source appraisal, or source weighting prompts. These are some of the most important model contexts.

Recommended change: add a second audit artifact, `model_call_context_inventory.json`, populated from prompt artifacts and progress reports. For each call, record stage, prompt path, prompt chars/tokens, source scope, decision-question presence, raw/debug field hits, source ID policy, and whether the call is local/global/repair/polish.

### 2. "Fallback" naming obscures retry versus downgrade

Some relation paths use "fallback" to mean "retry failed batch as singleton prompts." That is not the same as silently substituting weaker semantic output, but the name makes audit harder and conflicts with fail-loud policy.

Recommended change: rename these reports to `batch_retry_as_singletons` and ensure final failure remains a rejected relation with visible error metadata.

### 3. Broad repair calls should remain targeted

Final repair calls are currently mostly shaped correctly. The risk is that future changes add full packets or validation reports back into repair prompts.

Recommended change: add tests around repair prompt field exclusions: no raw outputs, no packet sufficiency report, no lineage/debug records, no full source texts, no legacy packet fields.

### 4. Packet critique should justify its inference cost

The parallel critique architecture is context-sane, but if its findings are not changing packet construction or writer guidance, it is wasted inference.

Recommended change: telemetry should record `critique_recommendation_count`, `accepted_recommendation_count`, `packet_field_change_count`, `writer_guidance_change_count`, and `final_memo_retention_delta`.

### 5. Analyst stages should preserve answer-frame state

The strongest analyst calls now include `stable_final_answer_frame`, which is good. Any call that asks support/counterweight/relevance questions should include the same answer-frame state or should explicitly avoid polarity labels.

Recommended change: add a prompt-contract check that stages using support/counterweight/answer-relation language include `decision_question` and either `stable_final_answer_frame` or an explicit "no final-answer polarity" policy.

