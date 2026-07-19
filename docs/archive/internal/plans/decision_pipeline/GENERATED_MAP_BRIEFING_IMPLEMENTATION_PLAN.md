# Generated Map Briefing Implementation Plan

Status: `in_progress`

Goal: make the prototype work as a reusable documents-plus-question pipeline that can generate a source-grounded map, evaluate and repair it, and produce a calibrated decision-support briefing without relying on curated map IDs.

## Implementation Steps

1. Add a first-class `synthesize map-briefing` CLI command.
   - Inputs: generated map JSON, map quality report JSON, decision question, backend, output directory.
   - Outputs: `BRIEFING.md`, `briefing.json`, `briefing_prompt.txt`, `briefing_raw.txt`, `briefing_summary.json`.
   - Reuse the existing structured packet renderer.

2. Add deterministic confidence calibration.
   - Cap confidence from map quality, validation failures, repair status, and quality issues.
   - Record both model and calibrated confidence.

3. Add source display cleanup.
   - Prefer human-readable source titles over source IDs in reader-facing briefing text.
   - Keep raw IDs in machine-readable artifacts.

4. Add source-role enrichment.
   - Infer fallback provenance/evidence roles from source metadata when explicit fields are unspecified.
   - Include enriched source roles in map-quality scaffolds and briefing prompts.

5. Add map prioritization for briefing.
   - Keep raw generated maps unchanged.
   - Produce a prioritized briefing map when claim count is above target or when briefing needs tighter context.
   - Rank by source coverage, claim role, relation degree, and source uniqueness.

6. Add relation quality checks.
   - Flag vague rationales, unsupported labels, weak endpoint basis, and overuse of generic relation types.
   - Include issues in `map_quality_report.json`.

7. Add generated-map erosion audit.
   - Build audit rows directly from the generated map and baseline/flat synthesis when available.
   - Avoid relying on curated claim IDs.

8. Add an end-to-end command for existing packages.
   - `semantic staged brief --region ... --backend ...`
   - Run staged map, quality repair, prioritization, generated audit, and map briefing.

9. Add tests and realistic smoke coverage.
   - Toy repair accepted.
   - Bad repair rejected.
   - Briefing command produces reader-safe output.
   - COVID realistic path succeeds.
   - Under-covered eggs run reports quality risks.

10. Update documentation.
    - Document the documents-plus-question workflow.
    - Explain artifact contracts, confidence caps, quality statuses, and failure modes.
