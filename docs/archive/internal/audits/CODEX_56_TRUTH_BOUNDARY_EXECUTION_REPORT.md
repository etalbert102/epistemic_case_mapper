Implemented all four requested slices.

- Slice 1: Complete via saved eggs replay plus documented live-replay blocker. Baseline: [truth_boundary_phase_zero_baseline.json](https://github.com/etalbert102/epistemic_case_mapper/blob/main/artifacts/truth_boundary_phase_zero/truth_boundary_phase_zero_baseline.json) and [memo review](https://github.com/etalbert102/epistemic_case_mapper/blob/main/artifacts/truth_boundary_phase_zero/truth_boundary_baseline_memo_review.md).
- Slice 2: Complete. Readiness now fails closed for unknown/unaccepted synthesis, repair, or polish; final lineage is append-only, and reader-output availability is separate from decision readiness.
- Slice 3: Complete. Reader source lists use active packet sources only; unavailable active identity removes the unverifiable source section rather than listing all case sources.
- Slice 4: Complete. Added focused unit and integration regressions.

Changed production files:

- [map_briefing_readiness.py](https://github.com/etalbert102/epistemic_case_mapper/blob/main/src/epistemic_case_mapper/map_briefing_readiness.py)
- [map_briefing_final_outputs.py](https://github.com/etalbert102/epistemic_case_mapper/blob/main/src/epistemic_case_mapper/map_briefing_final_outputs.py)
- [map_briefing_final_output_paths.py](https://github.com/etalbert102/epistemic_case_mapper/blob/main/src/epistemic_case_mapper/map_briefing_final_output_paths.py)
- [map_briefing_memo_metadata.py](https://github.com/etalbert102/epistemic_case_mapper/blob/main/src/epistemic_case_mapper/map_briefing_memo_metadata.py)
- [map_briefing_reader_polish.py](https://github.com/etalbert102/epistemic_case_mapper/blob/main/src/epistemic_case_mapper/map_briefing_reader_polish.py)

Tests/docs changed:

- `tests/test_map_briefing_readiness.py`
- `tests/test_reader_memo_metadata.py`
- `tests/test_map_briefing.py`
- `tests/test_map_briefing_decision_contracts.py`
- [DECISION_MEMO_TRUTH_BOUNDARY_HARDENING_PLAN.md](https://github.com/etalbert102/epistemic_case_mapper/blob/main/docs/plans/DECISION_MEMO_TRUTH_BOUNDARY_HARDENING_PLAN.md)

Verification:

- Focused suite: **52 passed**
- Saved-eggs fault replay: `blocked`, `decision_ready=false`, `reader_output_available=true`
- Saved-eggs source regression: exactly **7 active sources**, not all 12
- JSON validation, `py_compile`, and `git diff --check` passed
- `.venv` was absent, so the documented `PYTHONPATH=src python3` fast path was used.

Residual risks:

- Fresh current-HEAD Ollama replay was blocked by sandbox access to `127.0.0.1`; the saved full replay predates current HEAD and this is recorded.
- Quantity tuple semantics and `AnalystDecisionModel v2` remain explicitly deferred.
- No human review was claimed.
- Pre-existing dirty gap-closer, evidence-anchoring, citation, and related test changes were preserved untouched.