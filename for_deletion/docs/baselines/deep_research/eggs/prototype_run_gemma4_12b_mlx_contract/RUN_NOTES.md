# Briefing-Contract Prototype Run Notes

Purpose: rerun the eggs Deep Research source-held comparison after adding a domain-neutral briefing contract.

Implementation change tested:

- The scaffold now includes `briefing_contract_v1`.
- The contract contains an inferred answer frame, scope ledger, evidence-direction ledger, support-signal profile, and active overstatement lints.
- The model is instructed to write from the contract rather than from a mixed map.
- Deterministic repair softens generic overstatements such as `safe`, `clearly`, and `potentially beneficial` when the contract does not support them.
- Reader cleanup removes map-internal phrases such as `Claim A`, `Claim B`, `mapped claim`, and `Both claims`.

Input map:

- Same generated map as the first and sectioned prototype runs.
- Claims: `39`
- Relations: `27`
- Map quality: `usable_with_review`, score `88`

Briefing result:

- Backend: `ollama:gemma4:12b-mlx`
- Confidence: `medium`
- The final bottom line no longer says `potentially beneficial`.
- The final prose contains no `safe`, `safely`, `clearly`, `Claim A`, `Claim B`, or `mapped claim` markers.
- Concern evidence remains out of `Main Support`.

Saved artifacts:

- `PROTOTYPE_BRIEFING.md`
- `briefing_summary.json`
- `map_briefing_prompt.txt`
- `prioritized_map.json`
- `map_prioritization_report.json`

