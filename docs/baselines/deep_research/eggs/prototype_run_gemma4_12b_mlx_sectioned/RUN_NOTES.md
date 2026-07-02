# Section-Aware Prototype Run Notes

Purpose: rerun the eggs Deep Research source-held comparison after changing the briefing layer to mechanically partition evidence before model synthesis.

Implementation change tested:

- Claims and relations are deterministically assigned to `main_support`, `conflicting_evidence`, `scope_limits`, and `method_limits`.
- Relation types guide section placement: `challenges` / `in_tension_with` go to conflict, `depends_on` / `refines` go to scope, `crux_for` goes to crux/scope.
- Concern-shaped evidence is repaired out of `main_support` and moved to `conflicting_evidence`.
- Reader cleanup removes explicit `Claim A` / `Claim B` phrasing from model output.

Input map:

- Same generated map as `prototype_run_gemma4_12b_mlx`.
- Claims: `39`
- Relations: `27`
- Map quality: `usable_with_review`, score `88`

Briefing result:

- Backend: `ollama:gemma4:12b-mlx`
- Confidence: `medium`
- The `Main Support` section no longer contains the obvious concern evidence from Zhong, Li, or Spence.
- Explicit `Claim A` / `Claim B` leakage was removed.

Saved artifacts:

- `PROTOTYPE_BRIEFING.md`
- `briefing_summary.json`
- `map_briefing_prompt.txt`
- `prioritized_map.json`
- `map_prioritization_report.json`

