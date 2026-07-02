# Fuller-Source Prototype Run Notes

Question: For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?

Backend: `ollama:gemma4:12b-mlx`

Purpose: test whether the prototype's weaker output versus the Deep Research baseline was mainly caused by using abstract-heavy source packets rather than fuller cited-source text.

## Source Packet

The run used 11 documents reconstructed from the Deep Research bibliography:

- 7 fuller/fullish source records from Europe PMC XML, PMC HTML, or publisher-accessible HTML.
- 4 abstract-only records where full text was not readily accessible in this run.

See `source_depth_manifest.json` for source depth and character counts.

## Pipeline Settings

The source packet was initialized as an arbitrary document package, then processed with the staged semantic map and map-briefing workflow.

Key budget settings:

- `chunk-lines`: 45
- `max-chunks-per-source`: 2
- `max-total-chunks`: 22
- `max-claims-per-chunk`: 3
- `max-relation-pairs`: 40
- `relation-batch-size`: 5
- `briefing-max-claims`: 20
- `backend-timeout`: 240

The selected configuration profile was `empirical_policy_decision`.

## Map Quality

The generated map had:

- 51 accepted claims
- 37 accepted relations
- all 11 sources represented
- quality status `usable_with_review`
- quality score 78

Recorded quality risks:

- high claim count
- near-duplicate claims
- skipped chunks due to configured chunk budgets

## Output Files

- `PROTOTYPE_BRIEFING.md`: final reader-facing briefing
- `briefing_summary.json`: run metadata
- `map_quality_report.json`: quality checks from the generated map
- `prioritized_map.json`: map slice used for briefing
- `map_prioritization_report.json`: deterministic prioritization report
- `map_briefing_prompt.txt`: final synthesis prompt sent to the backend
- `source_depth_manifest.json`: source acquisition/depth record
