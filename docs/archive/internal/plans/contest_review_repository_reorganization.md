# Contest Review Repository Reorganization

## Goal

Make the repository fast to evaluate against the FLF competition criteria by
creating one unambiguous reviewer path, separating canonical evidence from
implementation history, and removing generated-run clutter from the active
review surface without deleting recoverable files.

## Non-goals

- Do not change case-map or briefing behavior.
- Do not add sources or make new domain claims.
- Do not claim human review or independent validation.
- Do not delete recoverable files; deletion candidates move to
  `for_deletion/`.
- Preserve the manifest-configured `case_map.json`, `report.md`, and `audit.md`
  snapshots required by the reproducibility contract; if relocated, update and
  validate every consumer.

## Required-reading implications

- `AGENTS.md`: generated runs belong under ignored `artifacts/`; curated
  snapshots belong under `examples/`; review status must remain honest.
- `README.md`: preserve a one-command no-model check and a clear first-read
  entry point.
- `docs/archive/internal/WORKFLOW_SPEC.md`: expose ingestion, structure,
  assessment, audit, and synthesis as a workflow rather than a report pile.
- `docs/protocols/epistemic_case_map_v0.md`: keep sources, claims, relations,
  and open questions as the reusable core.
- FLF criteria and rubric: lead with the LHC dependency example, use eggs to
  demonstrate transfer, keep COVID explicitly narrow, show baseline and
  limitation evidence, and make the repository runnable.
- Worked-regions plan: LHC and eggs are the two canonical demonstrations;
  heuristic starter output is not the final judge-facing evidence.
- LHC case manifest: dependency and critique/response structure should be the
  first worked example.
- Eggs case manifest: heterogeneous methods, endpoints, populations, and
  substitution context should be the transfer example.
- COVID case manifest: retain only as an optional adversarial slice, not as a
  full adjudication.

## Starting inventory

- 1,223 tracked files.
- 318 tracked files under `artifacts/`, despite the generated-artifact policy.
- 177 documentation files, including 52 files under `docs/plans/`.
- 63 manifest `judge_paths` and 51 `required_docs`.
- Multiple competing front doors: `START_HERE`, `SUBMISSION_PACKET`,
  `FLF_SUBMISSION_DRAFT`, and `EPISTEMIC_CASE_MAPPER_WRITEUP`.
- A pre-existing submission-reference failure caused by a stale demonstration
  document pointing at absent generated outputs.

## Target review surface

1. `README.md`
2. `docs/START_HERE.md`
3. `docs/submission/WRITEUP.md`
4. LHC worked-map and erosion-audit evidence
5. Compact investigator-challenge results and matched strong-model boundary
6. Eggs transfer example
7. Evidence/limitations and generalizability red team
8. Reproduction and human-review handoff

Supporting material is grouped under `docs/submission/`,
`docs/methodology/`, `docs/guides/`, `docs/validation/`,
`docs/evaluations/`, `docs/review/`, and `docs/reference/`. Development plans,
dated audits, and internal experiments live under `docs/archive/internal/`.

## Relocation decisions

- Promote the current long-form writeup to the sole formal competition entry.
- Keep `docs/START_HERE.md` as the stable short front door.
- Move duplicate submission narratives to `for_deletion/docs/`.
- Move current development plans into the existing internal plan archive.
- Move stale tracked generated runs to `for_deletion/artifacts/`.
- Curate compact investigator-challenge evidence under
  `examples/investigator_challenge/`; move raw prompts and replay inputs to
  `for_deletion/`.
- Keep source corpora, runnable code, tests, and UI in place. Separate
  manifest-configured heuristic snapshots under `examples/starter_snapshots/`
  from the curated case maps.

## Verification

- Validate submission manifest and scanned references.
- Regenerate and check UI data, Tier 1 checklist, artifact index, and reviewer
  start page.
- Run worked-region, full-case, update-demo, baseline, UI, and realism gates.
- Run the reproducibility gate.
- Run the full pytest suite.
- Run `git diff --check` and confirm no generated test scratch remains.

## Progress

- [x] Required context read and implications recorded.
- [x] Repository inventory and path-coupling audit complete.
- [x] Relocation manifest executed.
- [x] Canonical indexes and links updated.
- [x] Generated package surfaces refreshed.
- [x] Validation complete.

Final verification on 2026-07-19:

- full pytest suite: `947 passed`;
- full FLF reproducibility gate with worked regions and blinded baselines:
  passed;
- proof-by-example controls and expected-failure provenance probe: passed;
- active Markdown audit across 107 files: no broken relative links;
- manifest, reference, worked-region, full-case, baseline, UI, realism,
  update-demo, export, generated-index, and judge-smoke checks: passed;
- `git diff --check`: passed (line-ending warnings only).

## Residual risks

- No independent human audit has occurred.
- The quick deterministic demo is not a live-model quality demonstration.
- Historical generated runs moved to `for_deletion/` may still contain useful
  debugging evidence; human confirmation is required before permanent deletion.
