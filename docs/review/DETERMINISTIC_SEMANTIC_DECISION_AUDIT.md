# Deterministic Semantic Decision Audit

This audit flags deterministic code paths that appear to make semantic judgments from labels, keywords, or counts.
Findings are review prompts, not automatic failures.

Total findings: `127`

## hard_missing_from_count

Findings: `7`

- `src/epistemic_case_mapper/map_briefing_context_reports.py:502` `high` for slot in _string_list(existing_sufficiency.get("missing_expected_decision_slots")):
- `src/epistemic_case_mapper/map_briefing_context_reports.py:504` `high` for family in _string_list(existing_sufficiency.get("missing_expected_evidence_families")):
- `src/epistemic_case_mapper/map_briefing_context_reports.py:572` `high` missing = set(_string_list(map_sufficiency.get("missing_expected_evidence_families")))
- `src/epistemic_case_mapper/map_briefing_decision_model.py:204` `high` missing_expected_slots = [slot for slot in expected_slots if slot not in present_slots]
- `src/epistemic_case_mapper/map_briefing_decision_model.py:205` `high` missing_expected_families = [family for family in expected_families if int(families.get(family, 0)) == 0]
- `src/epistemic_case_mapper/map_briefing_decision_model.py:206` `high` obligations = _sufficiency_output_obligations(slots, missing_expected_slots, missing_expected_families)
- `src/epistemic_case_mapper/staged_semantic_quality.py:378` `high` if role_counts.get(role, 0) == 0:

Recommended handling: count-driven missing evidence or slot assertion: Do not assert semantic absence from one label/count source; reconcile with relations, spine fields, and source-backed candidates.

## keyword_semantic_classification

Findings: `62`

- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:80` `medium` if _looks_like_answer_instruction(claim):
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:108` `medium` scoring_terms = _support_terms() if role == "support" else _counterevidence_terms()
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:109` `medium` blocked_terms = _counterevidence_terms() if role == "support" else _support_terms()
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:115` `medium` score = _stance_score(claim, scoring_terms) - 0.5 * _stance_score(claim, blocked_terms)
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:167` `medium` if _looks_like_title_or_heading(claim):
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:169` `medium` if _looks_like_methods_only(claim):
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:171` `medium` if _looks_like_source_metadata(claim):
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:223` `medium` if term not in _counterevidence_terms():
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:452` `medium` if current_read and not _looks_like_answer_instruction(current_read):
- `src/epistemic_case_mapper/map_briefing_canonical_spine.py:459` `medium` if why and not _looks_like_answer_instruction(why):
- `src/epistemic_case_mapper/map_briefing_claim_eligibility.py:9` `medium` if _looks_like_glossary_or_abbreviation_row(compact):
- `src/epistemic_case_mapper/map_briefing_claim_eligibility.py:11` `medium` if _looks_like_reference_or_metadata_row(compact):
- `src/epistemic_case_mapper/map_briefing_claim_eligibility.py:13` `medium` if _looks_like_boilerplate_disclosure(compact):
- `src/epistemic_case_mapper/map_briefing_claim_eligibility.py:15` `medium` if _looks_like_publisher_or_license_boilerplate(compact):
- `src/epistemic_case_mapper/map_briefing_claim_eligibility.py:17` `medium` if _looks_like_administrative_study_context(compact):
- `src/epistemic_case_mapper/map_briefing_claim_eligibility.py:19` `medium` if _looks_like_statistical_method_trivia(compact):
- `src/epistemic_case_mapper/map_briefing_claim_eligibility.py:21` `medium` if _looks_like_truncated_or_orphan_fragment(compact):
- `src/epistemic_case_mapper/map_briefing_context_curation.py:188` `medium` role = _candidate_role(source_card)
- `src/epistemic_case_mapper/map_briefing_decision_model.py:428` `medium` if _looks_like_non_substantive_slot_text(value):
- `src/epistemic_case_mapper/map_briefing_decision_model.py:590` `medium` if _looks_like_method_or_source_limit(text):
- `src/epistemic_case_mapper/map_briefing_decision_model.py:593` `medium` if _looks_like_scope_or_subgroup(text, vocabulary=vocabulary):
- `src/epistemic_case_mapper/map_briefing_decision_model.py:610` `medium` _looks_like_support_evidence(text, vocabulary=vocabulary) or _looks_like_concern_evidence(text, vocabulary=vocabulary)
- `src/epistemic_case_mapper/map_briefing_decision_model.py:665` `medium` if section == "scope_limits" or _looks_like_scope_or_subgroup(text, vocabulary=vocabulary):
- `src/epistemic_case_mapper/map_briefing_decision_model.py:667` `medium` if section == "method_limits" or _looks_like_method_or_source_limit(text):
- `src/epistemic_case_mapper/map_briefing_decision_synthesis.py:555` `medium` return _looks_like_population_or_group(value) or len(words) <= 8
- ... 37 more

Recommended handling: keyword-based support/counterweight/scope classification: Keep keyword classifiers advisory unless another structured signal corroborates them.

## profile_vocabulary_semantics

Findings: `55`

- `src/epistemic_case_mapper/decision_argument_artifacts.py:581` `medium` concepts = set(_string_list(row.get("decision_concepts")))
- `src/epistemic_case_mapper/map_briefing_classical_selection.py:128` `medium` concept_counts = Counter(concept for row in rows for concept in _string_list(row.get("decision_concepts")))
- `src/epistemic_case_mapper/map_briefing_decision_cruxes.py:20` `medium` vocabulary = _profile_vocabulary_for_scaffold(scaffold)
- `src/epistemic_case_mapper/map_briefing_decision_cruxes.py:133` `medium` concepts = set(_strings(left.get("decision_concepts"))) | set(_strings(right.get("decision_concepts")))
- `src/epistemic_case_mapper/map_briefing_decision_cruxes.py:148` `medium` concepts = set(_strings(claim.get("decision_concepts")))
- `src/epistemic_case_mapper/map_briefing_decision_cruxes.py:424` `medium` return profile_vocabulary(profile_id)
- `src/epistemic_case_mapper/map_briefing_decision_model.py:137` `medium` vocabulary = profile_vocabulary(str(evidence_ledger.get("profile_id", DEFAULT_PROFILE_ID)))
- `src/epistemic_case_mapper/map_briefing_decision_model.py:201` `medium` expected_slots = _expected_slots_for_question(question, evidence_ledger, vocabulary=_profile_vocabulary_for_map(candidate_map))
- `src/epistemic_case_mapper/map_briefing_decision_model.py:604` `medium` modifiers.append(f"decision_concept_count:{len(concepts)}")
- `src/epistemic_case_mapper/map_briefing_decision_model.py:620` `medium` concept_markers = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("claim_concept_markers", {})
- `src/epistemic_case_mapper/map_briefing_decision_model.py:662` `medium` for family, markers in _vocabulary_marker_map(vocabulary, "evidence_family_markers").items():
- `src/epistemic_case_mapper/map_briefing_decision_model.py:674` `medium` slot_markers = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("decision_slot_markers", {})
- `src/epistemic_case_mapper/map_briefing_decision_model.py:686` `medium` markers = (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("evidence_slot_markers", {})
- `src/epistemic_case_mapper/map_briefing_decision_model.py:783` `medium` concepts = set(str(concept) for concept in row.get("decision_concepts", []) if isinstance(concept, str))
- `src/epistemic_case_mapper/map_briefing_decision_support_model.py:54` `medium` vocabulary = _profile_vocabulary_for_map(candidate_map)
- `src/epistemic_case_mapper/map_briefing_decision_synthesis.py:178` `medium` concepts = _string_set(row.get("decision_concepts"))
- `src/epistemic_case_mapper/map_briefing_evidence_cards.py:329` `medium` concepts = set(str(item) for item in row.get("decision_concepts", []) if isinstance(item, str))
- `src/epistemic_case_mapper/map_briefing_evidence_partition.py:133` `medium` for rule in (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("crux_label_rules", []):
- `src/epistemic_case_mapper/map_briefing_evidence_partition.py:142` `medium` for rule in (vocabulary or profile_vocabulary(DEFAULT_PROFILE_ID)).get("crux_label_rules", []):
- `src/epistemic_case_mapper/map_briefing_evidence_tables.py:256` `medium` vocabulary = profile_vocabulary(table_profile_id)
- `src/epistemic_case_mapper/map_briefing_evidence_tables.py:489` `medium` vocabulary = _profile_vocabulary_for_map(candidate_map)
- `src/epistemic_case_mapper/map_briefing_evidence_tables.py:592` `medium` vocabulary = _profile_vocabulary_for_map(candidate_map)
- `src/epistemic_case_mapper/map_briefing_evidence_tables.py:599` `medium` concepts = [str(item) for item in row.get("decision_concepts", []) if isinstance(item, str)]
- `src/epistemic_case_mapper/map_briefing_evidence_tables.py:643` `medium` vocabulary = profile_vocabulary(str(evidence_ledger.get("profile_id", DEFAULT_PROFILE_ID)))
- `src/epistemic_case_mapper/map_briefing_evidence_tables.py:676` `medium` concepts = [str(item) for item in row.get("decision_concepts", []) if isinstance(item, str)]
- ... 30 more

Recommended handling: profile vocabulary controls semantic slot assignment: Use vocabulary/profile matches as routing hints, not final evidence sufficiency or memo claims.

## semantic_rejection_gate

Findings: `3`

- `src/epistemic_case_mapper/staged_semantic_claims_relations.py:763` `medium` if _append_semantic_relation_rejection(rejected, relation, packet, batch_id, proposal):
- `src/epistemic_case_mapper/staged_semantic_claims_relations.py:812` `medium` reason = relation_semantic_rejection_reason(relation, packet)
- `src/epistemic_case_mapper/staged_semantic_quality.py:84` `medium` semantic_reason = relation_semantic_rejection_reason(relation, packet)

Recommended handling: deterministic rejection of semantic relation/claim quality: Route semantic rejection to review or model adjudication unless the failure is schema, ID, or source-anchor invalidity.
