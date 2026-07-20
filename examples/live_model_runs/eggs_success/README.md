# Eggs Live-Model Success

Status: `machine-generated-human-review-needed`

Backend: `ollama:gemma4:12b-mlx`

Decision question: How should a synthesis preserve the relationship between
observational CVD outcome evidence, randomized lipid-marker evidence,
guideline framing, and population/context caveats for egg consumption?

## Result

- Semantic candidate validation: pass.
- Pipeline quality: `usable_with_review`, score 78.
- Final structure: 26 claims, 22 relations, 15 crux candidates, 7 sources.
- Backend calls: 7 completed, 0 backend errors.
- Quality repair: accepted targeted relation repair; 7 proposed relations
  accepted and 1 correctly returned as `none`.

## Remaining Review Risks

- The map is one claim above the configured maximum of 25.
- Near-duplicate pairs remain: `eggs_c011`/`eggs_c029` and
  `eggs_c020`/`eggs_c021`.
- The run selected seven source chunks and skipped 83 under its configured
  chunk budget.
- No independent human accepted the claims, relations, or prioritization.

Start with [generated_map.json](generated_map.json), then inspect
[run_summary.json](records/run_summary.json),
[map_quality_report.json](records/map_quality_report.json), and the
`transcripts/` directory. These files are copied without edits from the live
run.
