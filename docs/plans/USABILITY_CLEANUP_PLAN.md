# Plan: Usability Cleanup

## Objective

Make the prototype easier for a fresh user to run, inspect, and trust without already knowing the repo history.

The target end state is:

- One obvious path from documents and a decision question to a briefing memo.
- Validation commands that agree with the advertised quick start.
- A small, navigable artifact surface.
- Clear recovery guidance when generated files are stale or a model run fails.

## Current Gap

The repo has strong internal instrumentation, but usability is hurt by three things:

- The top-level quick start and the reusable engine path compete for attention.
- `artifacts/` contains many untracked experiment runs that make it hard to find the current outputs.
- Some generated assets can drift from the manifest, causing the advertised demo check to fail.

## Non-Goals

- Do not delete tracked artifacts, checked-in examples, source documents, baseline docs, or review packets.
- Do not change the semantic pipeline, model prompts, or memo-quality behavior.
- Do not hide warnings or make validation less strict.
- Do not tune the system to the eggs case.

## Design Principles

- Prefer one canonical beginner path, with advanced knobs still available.
- Keep generated experiment clutter out of the default reader path.
- Preserve traceability: every run should point to the memo, summary, final review packet, map quality report, and progress files.
- Make failure recovery concrete: tell users which command updates stale generated assets.
- Treat deletion as a bounded cleanup of untracked generated outputs, not a source-history rewrite.

## Inventory And Dependency Map

- Tracked artifacts are identified with `git ls-files artifacts`.
- Untracked artifacts are generated run clutter and may be removed with `git clean -fd artifacts`.
- `ui/data.json` is generated from `submission_manifest.yaml`; if stale, regenerate it with `scripts/build_ui_data.py`.
- `semantic staged brief` is the current end-to-end reusable path.
- `run_flf_demo.py --skip-build` is the advertised package check and should pass after generated assets are refreshed.

## Workstreams

1. Canonical Workflow
   - Purpose: Give users one default path.
   - Changes: Update README and backend docs with a short “documents + question to memo” command sequence.
   - Artifacts: README section and backend guide.
   - Validation: Commands are copy-pasteable and reference existing CLI targets.

2. CLI Discoverability
   - Purpose: Make `--help` useful without reading all docs.
   - Changes: Add examples to the top-level parser and staged-brief parser; print the final review packet path after briefing runs.
   - Artifacts: CLI help text and run output.
   - Validation: `python -m epistemic_case_mapper.cli --help` and `semantic staged brief --help`.

3. Artifact Hygiene
   - Purpose: Remove old experiment clutter while preserving committed evidence.
   - Changes: Delete only untracked files under `artifacts/`; add an artifact policy README.
   - Artifacts: Leaner `artifacts/`, `artifacts/README.md`.
   - Validation: `git status --short --untracked-files=all artifacts` is clean except intended tracked changes.

4. Generated Asset Freshness
   - Purpose: Make advertised checks pass.
   - Changes: Regenerate `ui/data.json`.
   - Artifacts: Current UI data.
   - Validation: `scripts/run_flf_demo.py --skip-build` and `ecm validate package`.

## Execution Order

1. Record this plan.
2. Improve docs and CLI guidance without changing pipeline semantics.
3. Remove untracked artifact clutter after confirming tracked artifacts.
4. Regenerate stale generated assets.
5. Run validation and maintainability checks.
6. Commit the cleanup as one usability slice.

## Acceptance Criteria

- README has one canonical new-case workflow.
- CLI help includes a staged-brief example.
- Staged briefing output prints the final review packet path.
- Untracked old artifact runs are removed while tracked artifacts remain.
- `ui/data.json` is current.
- `run_flf_demo.py --skip-build` passes.
- `ecm validate package` passes.
- Maintainability gate passes.

## Red-Team Checks

- Risk: deleting useful evidence.
  - Check: only remove untracked artifact files; tracked artifacts are preserved by git.
- Risk: docs oversell product polish.
  - Check: keep human-review-needed boundaries and validation caveats visible.
- Risk: CLI examples imply a model is required for every check.
  - Check: document `prompt` backend and show it as the dry-run/default path.
- Risk: generated UI data drifts again.
  - Check: keep `run_flf_demo.py --skip-build` as the advertised freshness gate.

## Generalizability Checks

- The canonical workflow must work for arbitrary local documents, not just existing FLF cases.
- Artifact cleanup policy must apply to any generated run directory.
- CLI guidance must support `prompt`, `command:<cmd>`, and `ollama:<model>` backends.
