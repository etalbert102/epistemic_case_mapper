# Unseen Case Quality Test Plan

Status: `implemented`

Purpose: test whether the prototype produces useful, inspectable epistemic-map packages on a genuinely new case, not only whether it validates syntactically or works on the original FLF examples.

## 1. Select The Unseen Case

Pick one case that differs from existing examples by domain, evidence shape, stakeholder structure, and uncertainty profile.

Good candidates:

- a local policy dispute, such as whether a city should remove parking minimums
- a technical safety dispute, such as whether passkeys are safer than SMS 2FA for ordinary users
- a public-health evidence question, such as whether schools should install HEPA filtration
- a contested product or regulatory claim, such as whether e-bike subsidies reduce car trips

Selection criteria:

- 6-12 available sources
- at least two perspectives
- real uncertainty or tradeoffs
- not already represented in the package
- small enough to map in one working session

Avoid cases where the answer is trivial or purely factual.

## 2. Freeze The Test Protocol

Before running the prototype, create a protocol with:

- case question
- why this case is meaningfully different from prior cases
- source inclusion rules
- expected reviewer tasks
- time and compute budget
- what counts as success
- what counts as failure
- baseline comparison method

This prevents post-hoc rationalization.

Command:

```bash
ecm quality init --case <case_slug> --title "<case title>" --question "<case question>"
```

This creates:

- `docs/unseen_case_tests/<case_slug>/TEST_PROTOCOL.md`
- `docs/unseen_case_tests/<case_slug>/QUALITY_REVIEW.md`
- `docs/unseen_case_tests/<case_slug>/BASELINE_COMPARISON.md`
- `docs/unseen_case_tests/<case_slug>/SCORECARD.md`

## 3. Build A Source Packet

Create a neutral source packet with:

- 2-3 sources supporting one side
- 2-3 sources supporting another side
- 1-2 sources about implementation or measurement caveats
- 1-2 sources from institutional or technical authorities
- source metadata in `case.yaml`
- local text excerpts where possible

For each source, record:

- source ID
- title
- type
- path or URL
- why included
- known limitations

## 4. Run A Blind Baseline First

Before using the mapper, generate an ordinary flat synthesis from the same source packet.

The baseline should answer:

- what is the likely answer?
- what evidence matters most?
- what uncertainties remain?
- what further work would change the answer?

Keep this baseline isolated from the map artifacts. The goal is to test whether the mapper is meaningfully better than a good off-the-shelf synthesis, not merely whether it is polished.

## 5. Build The Epistemic Package

Use the reusable engine path:

- create `package.yaml`
- create `data/cases/<case>/case.yaml`
- create source text files
- create one worked-region definition
- create a worked map
- create erosion audit
- create full-case scaffold
- create task queue
- run `ecm package prepare`
- run `ecm validate package`

Minimum expected artifacts:

- source-grounded claims
- relations with meaningful types
- crux candidates
- similar-but-not-identical distinctions
- evidence checks
- flat-synthesis losses
- reviewer checklist
- UI package

## 6. Evaluate Quality

Score the output 1-5 on:

- Source fidelity
- Load-bearing visibility
- Crux quality
- Relation usefulness
- Erosion audit quality
- Human reviewability
- Generalizability
- Incremental extensibility
- UI usefulness
- Baseline improvement

The generated `QUALITY_REVIEW.md` enforces this scorecard.

## 7. Human Judge Simulation

Ask a human reviewer, or simulate one strictly, to perform three tasks:

1. Find the strongest reason for the tentative conclusion.
2. Find the most important uncertainty or crux.
3. Identify one claim that may be overstated.

Record:

- time to answer
- whether they used the map, checklist, UI, or source files
- points of confusion
- whether they trusted the artifact more or less after inspection

## 8. Adversarial Review

Red-team the package for:

- unsupported confidence
- source cherry-picking
- relation labels that imply too much
- missing stakeholder perspective
- claims that collapse different measurements
- false precision
- UI hiding uncertainty
- checklist rows too vague to review
- generated docs that feel like rubric theater

Classify each issue as:

- correctness bug
- presentation bug
- methodology weakness
- missing source
- generalizability failure

## 9. Compare To Baseline

Write a direct before/after comparison:

- What did the map preserve that the flat baseline blurred?
- What did the flat baseline do better?
- Which cruxes became clearer?
- Which claims became more inspectable?
- Did the map change the investigator's view?
- Would a judge see the extra structure as worth the complexity?

This is the key evidence of value.

## 10. Acceptance Criteria

The unseen-case test is complete only if the scorecard records each criterion:

- `package_prepare`
- `package_validate`
- `ui_renders`
- `review_checklist_source_spans`
- `no_parser_artifacts`
- `non_obvious_crux`
- `real_flat_synthesis_loss`
- `human_reviewer_can_inspect`
- `better_than_flat_baseline`

Statuses may be `pass`, `fail`, `risk`, or `n/a`, but the evidence cell must explain the status.

## 11. Quality Gate

After the package artifacts and quality docs are complete, run:

```bash
ecm quality gate --case <case_slug>
```

The gate:

- regenerates package-facing assets with `ecm package prepare`
- validates the package manifest, worked regions, and references
- regenerates structured worked-region exports
- checks structured exports, UI data, and review checklist freshness
- validates the completed unseen-case quality documents

For a non-mutating quality-doc-only check, run:

```bash
ecm quality check --case <case_slug>
```

## 12. Deliverables

Each unseen-case run produces:

- `docs/unseen_case_tests/<case_slug>/TEST_PROTOCOL.md`
- `docs/unseen_case_tests/<case_slug>/QUALITY_REVIEW.md`
- `docs/unseen_case_tests/<case_slug>/BASELINE_COMPARISON.md`
- `docs/unseen_case_tests/<case_slug>/SCORECARD.md`
- generated package artifacts
- a short final scorecard
- a list of prototype improvements discovered during the test
