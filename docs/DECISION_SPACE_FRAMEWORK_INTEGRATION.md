# Decision-Space Framework Integration

Status: judge-facing mechanism map

This project is not just an argument map and not just a faithful summarizer. It is a prototype for preserving operational judgment as evidence moves through an AI-assisted workflow.

The mechanism chain is:

```text
retrieval gate -> claim normalization -> decision-space construction -> judgment anchors -> artifact fidelity -> auditable authority
```

## Mechanism Chain

### 1. Retrieval Gate

What enters the source packet determines what the model and later reviewer can reason about. A fluent answer can be rigorous inside a distorted evidence set.

Current surfaces:

- case manifests and local source files,
- optional intake filter,
- source-universe parity reports in the investigator challenge,
- prompt-only and live-model paths that record source scope.

Reviewer question: can I see which evidence entered the case and what was outside the boundary?

### 2. Claim Normalization

The workflow turns messy source material into standardized claims. That makes comparison possible, but it can also flatten caveats, uncertainty, dissent, or source context.

Current surfaces:

- source-grounded claims,
- stable source IDs and excerpts,
- span and citation validation,
- human-review-needed status for relation and claim judgments.

Reviewer question: did the normalized claim preserve the source's scope, uncertainty, and meaning?

### 3. Decision-Space Construction

The map constructs the available reasoning field: which claims, options, dependencies, caveats, conflicts, and update triggers remain visible before synthesis.

Current surfaces:

- worked-region maps,
- relation graphs,
- similar-but-not-identical sections,
- cruxes and open questions,
- erosion audits against flat syntheses.

Reviewer question: what live interpretation or evidence path would disappear if the map collapsed into prose?

### 4. Judgment Anchors

Claims, relations, cruxes, source roles, and review checklist rows are not just metadata. They are checkpoints that preserve the basis for human judgment.

Current surfaces:

- claim IDs and relation IDs,
- review packets and CSV checklists,
- investigator task queues,
- challenge answer keys and deterministic replay outputs.

Reviewer question: can a reviewer accept, revise, reject, or escalate the local judgment?

### 5. Artifact Fidelity

The artifact itself carries authority because it determines what a reviewer can inspect, contest, and update. Prose is one view over the durable artifact, not the only record.

Current surfaces:

- Markdown maps for inspection,
- JSON exports for reuse,
- validation gates,
- mutation repair diffs,
- held-out-source update ledgers,
- static UI that points back to canonical files.

Reviewer question: did the reviewable structure survive transformation across file formats, repair, and update?

### 6. Auditable Authority

Transparency is weak if no one can intervene. The submission's stronger claim is that stable artifacts give reviewers local operational authority.

Current surfaces:

- local relation repair in the investigator challenge,
- held-out source update that preserves unaffected IDs,
- reviewer packets that separate accept/revise/reject decisions,
- warnings and validation reports that identify where human judgment is still needed.

Reviewer question: can the reviewer change the case locally without regenerating the whole answer?

## LHC Example Through The Chain

Flat synthesis can say that cosmic-ray exposure shows LHC black-hole risk is ruled out. The map preserves the decision-space chain:

- Retrieval gate: the LHC source universe is declared.
- Claim normalization: the velocity caveat and trapping analysis become separate source-grounded claims.
- Decision-space construction: the Earth-survival argument and compact-star argument remain distinct.
- Judgment anchors: `lhc_c004`, `lhc_c012`, `lhc_r003`, and `lhc_r004` identify the load-bearing dependency.
- Artifact fidelity: mutation repair restores a reversed relation without changing unaffected objects.
- Auditable authority: a held-out CERN public FAQ update records added and touched claims while preserving stable IDs.

This is why the project should not be judged mainly on whether it writes prettier prose than a strong model. The matched strong-model comparison shows that a strong model can recover much of the LHC chain when asked directly. The prototype's distinctive value is that the chain persists as a reviewable, updateable artifact.

## What This Adds To The Submission Claim

Demonstrated:

- structure can be preserved across source packets, maps, JSON, Markdown, repair diffs, update ledgers, and review packets,
- selected hidden dependencies are easier to recover from mapped artifacts than from flat baseline prose,
- reviewers have concrete local handles for repair and update.

Still under-tested:

- whether independent reviewers use the handles correctly,
- whether a second operator can build equally useful maps on fresh cases,
- whether the final memo layer can consistently exploit the artifact without losing prose quality.

Not claimed:

- automatic truth,
- exhaustive source discovery,
- final prose superiority over strong models,
- replacement of expert review.
