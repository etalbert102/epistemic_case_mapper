# Epistemic Case Mapper

Status: project overview, prepared 2026-07-18

## Executive summary

The Epistemic Case Mapper is an AI-assisted research workflow for turning a bounded set of sources into a structured, reviewable account of a contested question. Its purpose is not simply to write a better summary. It is to preserve the parts of a case that ordinary synthesis often compresses away: where a claim came from, what supports or challenges it, which caveats limit it, where apparently similar claims differ, what the live cruxes are, and what evidence would change the assessment.

The primary problem is **reasoning-structure loss during AI-assisted evidence transformation and synthesis**. A synthesis can be fluent, useful, and broadly correct while discarding the structure that a later investigator would need to inspect, contest, update, or reuse it. The project’s corresponding design goal is **epistemic artifact fidelity**: preserving operative reasoning structure, provenance, and reviewable form as evidence moves through ingestion, claim normalization, mapping, prioritization, and prose generation.

For example, the sentence “cosmic-ray exposure shows that LHC black-hole risk is ruled out” captures the broad conclusion of a safety argument, but omits a load-bearing dependency: Earth-survival evidence is not sufficient by itself if collider-produced objects could be slower and more easily trapped than cosmic-ray products. The immediate failure is a loss of inferential structure through abstraction. The mapper represents the velocity caveat, trapping analysis, compact-star evidence, and relations among them as separate reviewable objects.

**Decision-space erosion** is an important downstream condition, not the name for every omission or compression. In this project, it means that a workflow removes or fails to preserve a decision-relevant option, interpretation, evidence path, escalation path, or reviewable context relative to a declared baseline before accountable review. Reasoning-structure loss becomes decision-space erosion when it makes such an alternative materially less visible or recoverable. Deliberate scoping and prioritization are not erosion when their criteria are explicit, reproducible, reviewable, and leave material alternatives recoverable.

The current repository demonstrates this approach on three different case shapes:

- LHC black-hole safety, a mostly closed technical-risk case;
- eggs and cardiovascular health, a heterogeneous evidence case involving observational outcomes, randomized biomarkers, guidelines, and subgroup effects;
- a deliberately narrow COVID-origins slice, used to test whether Bayesian disagreement can be represented without pretending to settle the full controversy.

The result is a runnable reference prototype with source manifests, structured maps, Markdown and JSON exports, comparison baselines, structure-loss and erosion-audit surfaces, reviewer packets, validation tools, resumable processing stages, and a static inspection UI. A newer synthesis layer can also turn mapped evidence into a decision-oriented memo through an explicit intermediate decision model. That layer is implemented but remains provisional: no current memo run is part of the curated judge evidence, so this submission does not make an empirical memo-quality or memo-retention claim.

For the FLF Epistemic Case Study Competition, the prototype is best understood as a structure-preserving epistemic handoff layer spanning parts of ingestion, structure, and assessment. It is designed to help investigations travel, compound, and survive disagreement across people and tools. Its contest claim is therefore not that it has discovered every failure in AI research, but that it makes one important class of failures inspectable and gives investigators a reusable artifact on which later work can build.

## The problem

Most AI research systems optimize for a readable answer. That is valuable for immediate understanding, but it is a weak format for compounding investigation. Once evidence has been blended into prose, a later reviewer may struggle to answer basic questions:

- Which source supports this sentence?
- Is this a source claim or the synthesizer’s inference?
- Does a cited study measure the outcome at issue or only a proxy?
- Are two sources actually disagreeing, or studying different populations, interventions, or endpoints?
- Which premise is carrying the conclusion?
- What observation would materially change the answer?
- Can one local part be corrected without rewriting the whole report?

These failures can arise at several distinct stages. Retrieval determines which evidence can enter the investigation. Claim normalization makes heterogeneous evidence operational but can flatten scope, uncertainty, dissent, or provenance. Synthesis can smooth conflicts or collapse multiple frames into one. Higher-level abstraction can preserve the conclusion while hiding a premise or dependency needed to evaluate it. Treating all of these as “decision-space erosion” obscures where the failure occurred and what would fix it.

Provenance alone does not solve this. A paragraph may cite the right documents and still flatten distinctions among them. Nor is the mapper simply an argument-diagramming tool: it combines argument structure with source-local excerpts, scope boundaries, uncertainty, evidence roles, open questions, and an explicit differential audit of what a flat synthesis preserved, flattened, omitted, or distorted.

The governing design question is therefore:

> Can an AI-assisted workflow preserve reasoning structure and epistemic artifact fidelity while still producing prioritized outputs that people can inspect, contest, update, and reuse?

## What an epistemic case map contains

The core schema is intentionally small. A map is built from four main objects:

1. **Sources** — documents, datasets, transcripts, expert statements, or notes, recorded with stable identifiers and provenance.
2. **Claims** — atomic or near-atomic propositions tied to source-local spans and excerpts.
3. **Relations** — typed connections among claims, including `supports`, `challenges`, `refines`, `similar_to`, `depends_on`, `crux_for`, and `in_tension_with`.
4. **Open questions and cruxes** — gaps, unresolved assumptions, missing perspectives, or observations that would change the assessment.

Production-oriented artifacts add further structure: source-quality metadata, evidence types, quantitative anchors, scope boundaries, counterarguments, update triggers, review status, and telemetry about model failures or rejected objects.

Stable IDs are central to the design. A reviewer can accept, revise, reject, or extend one claim or relation without having to regenerate the entire narrative. The map is consequently both a representation of the current case and an interface for future work. Prose is one view over this durable epistemic artifact rather than the sole record of the investigation.

## How the workflow operates

The reusable workflow proceeds through six layers:

```mermaid
flowchart LR
    A[Bounded source packet] --> B[Intake and provenance]
    B --> C[Claims and source anchors]
    C --> D[Relations, caveats, and cruxes]
    D --> E[Validated case map]
    E --> F[Decision model and briefing]
    E --> G[Baseline comparison and structure-loss audit]
    F --> H[Human review packet]
    G --> H
```

### 1. Bound the question and corpus

A case begins with a decision question and a specified set of local documents. The system does not silently retrieve additional evidence. An optional intake filter records readability, relevance, citation-density, source-type, date, correction, and traceability signals before documents enter the mapping pipeline. Exclusion remains an explicit user choice.

### 2. Create stable source records

The package initializer copies the source packet into a reproducible case layout, assigns stable source identifiers, records provenance, and creates starter artifacts. This establishes the evidence boundary before semantic interpretation begins.

### 3. Extract source-grounded claims

For realistic packets, the staged mapper splits documents into source-local spans. A model selects span IDs and proposes claim classifications; deterministic code then supplies the exact source ID, span, and excerpt. Unknown spans, malformed objects, and unsupported references are rejected and logged. This division reduces the opportunity for a model to invent quotations or silently move a claim across sources.

### 4. Map relations and cruxes

The system constructs bounded candidate claim pairs and asks a model to classify their relationship or return no relation. Relation endpoints and types are validated against the map and its ontology. Models can also propose cruxes, caveats, similar-but-not-identical claims, and open questions. These remain candidate judgments until review.

### 5. Validate and package the map

Deterministic validators check schema conformance, exact excerpt recovery, source membership, relation endpoints, artifact freshness, package references, and reproducibility. Outputs include JSON for reuse, Markdown for inspection, warnings and task queues for follow-up, and a static UI for browsing. Explicit handoff points at `documents`, `map`, and `briefing` allow another investigator to resume from saved work.

### 6. Compare, synthesize, and review

The map can be compared with a flat synthesis to identify distinctions that were preserved, flattened, omitted, or distorted. This is first a structure-loss audit. A finding should be labeled decision-space erosion only when the missing structure reduces the visibility or recoverability of a decision-relevant option, interpretation, evidence path, caveat, or review boundary relative to the declared comparison baseline.

A decision-briefing pipeline then compiles the accepted evidence into an intermediate argument or decision model and a canonical writer packet. Source-preserving prioritization is necessary here: the workflow should reduce reviewer burden while recording what was deprioritized, why, and how it can be recovered. The final model writes from that bounded packet, after which deterministic retention checks verify that mandatory evidence, quantities, scope conditions, and citations survived. The system emits a final review packet rather than treating fluent prose as proof of correctness.

## Division of labor between models, code, and people

The mapper treats AI judgment as necessary but not authoritative.

Language models perform bounded semantic tasks: proposing claims, normalizing language, identifying relations, surfacing cruxes, comparing a map with a baseline, appraising evidence roles, and drafting or repairing synthesis. These are tasks for which simple rules are too brittle. Claim normalization is treated as necessary but risky because a clean standardized claim can silently lose source scope, uncertainty, or dissent.

Deterministic code owns the boundaries around that judgment: source ingestion, stable IDs, span catalogs, prompt construction, schema parsing, excerpt verification, relation ontologies, artifact assembly, freshness checks, telemetry, and validation gates. A Pydantic schema can prove that an object has the right shape; it cannot prove that a relation is epistemically correct. The code therefore validates what can be validated mechanically and exposes the rest as review obligations.

Humans remain responsible for the final substantive decisions: whether a claim is faithfully entailed, whether a relation label captures the actual inference, whether the source packet is balanced, and whether the map’s prioritization reflects the decision at hand. The current checked-in maps are marked `human-review-needed`; passing the test suite establishes internal consistency, not external correctness.

## What the demonstrations show

The strongest evidence for the project is qualitative but concrete.

In the **LHC black-hole case**, the map preserves the dependency between the low-velocity trapping caveat and the use of compact astronomical bodies as safety evidence. A flat answer can reach the right bottom line without leaving this dependency inspectable. Scripted blinded local-model baselines preserve different subsets of the chain. A reported `gpt-5.6-sol` response also recovered much of it, although its invocation transcript was not retained and it is not treated as performance evidence. The evidence therefore does not support a claim that strong models cannot reconstruct the reasoning. The demonstrated value is persistence and addressability: the dependency already exists as stable objects that can be inspected and revised without re-deriving it from prose. It becomes evidence of decision-space preservation if the missing branch would otherwise remove a live interpretation or investigation path from review.

In the **eggs and cardiovascular-health case**, the map keeps several evidence roles separate: long-term observational cardiovascular outcomes, randomized effects on lipid markers, guideline interpretations, substitution context, baseline intake, and high-risk subgroups. This directly tests claim-normalization fidelity and conflict retention: a biomarker result, a population association, and a policy recommendation should not be blended into one undifferentiated conclusion.

In the **COVID-origins slice**, the map separates a debate result, critiques of the debate process, aggregate and minority forecasts, formal Bayesian decompositions, geographic assumptions, and later phylogenetic objections. This is a `seed`-mode representational stress test built from investigator-authored notes and excerpts, not verified source copies. It tests whether the format can keep loci of disagreement distinct; it does not provide source-grounded evidence or a full origins adjudication.

The deterministic investigator challenge is likewise an artifact-mechanics
demonstration, not a performance benchmark. Its map responses materialize
frozen answer-key objects, its mutation exercise restores a known relation from
a clean snapshot, and its update exercise applies a prewritten delta. Those
operations show addressability, stable-ID preservation, and change locality.
They do not show that an investigator independently recovered the objects, that
the system performed semantic repair, or that it derived an update from a newly
read source.

The checked-in submission snapshot contains 53 curated claims, 48 relations, nine crux candidates, and 19 findings recorded under the current erosion-audit schema across the three worked regions. Eight blinded local-model baselines provide additional comparison surfaces for the LHC and eggs regions. These counts demonstrate artifact depth, not accuracy scores. The findings still require item-level review to distinguish general structure loss from the narrower subset that qualifies as baseline-relative decision-space erosion.

The decision-briefing implementation adds a second, still provisional surface. It can carry an explicit decision model, bounded quantities, counterweights, scope conditions, and retention obligations into a memo, and its gates expose missing obligations as machine-readable failures. Earlier saved runs motivated this architecture but are not part of the curated judge evidence. The current evidence therefore supports inspectable stage contracts and controlled handoff, not a claim about final-answer performance.

## Implementation and use

The project is a Python 3.11 package with a single `ecm` command-line interface. The shortest reusable path is:

```bash
ecm --repo-root /path/to/package case filter-sources \
  --question "What should a careful reader conclude?" \
  --docs doc_a.txt doc_b.md

ecm --repo-root /path/to/package --package package.yaml case init \
  --case-id my_case \
  --title "My Case" \
  --question "What should a careful reader conclude?" \
  --docs doc_a.txt doc_b.md

ecm --repo-root /path/to/package --package package.yaml semantic staged brief \
  --region my_case_initial_region \
  --backend ollama:<installed-model>
```

Live execution can use a local command backend or an Ollama model. Backend calls, prompts, intermediate artifacts, and non-publication diagnostics are retained for inspection. The CLI also exposes package validation, JSON export, UI generation, baselines, synthesis, review-packet generation, unseen-case quality checks, and automated stress evaluation.

Canonical artifacts are file-based and portable. Markdown supports direct human inspection; JSON supports downstream tooling; CSV review checklists record item-level decisions; generated telemetry records what failed or fell back. The static UI is deliberately only a viewing layer, so canonical evidence and review state do not become trapped in an opaque application database.

## Strengths

The prototype’s main strengths are:

- **Traceability:** claims point to stable source IDs, spans, and exact local excerpts.
- **Epistemic artifact fidelity:** reasoning structure, provenance, review state, and writer obligations persist across workflow stages.
- **Local revisability:** stable claim and relation IDs let reviewers change one piece without rewriting the whole case.
- **Disagreement preservation:** caveats, counterarguments, similar claims, and cruxes remain first-class objects.
- **Separation of concerns:** models make semantic proposals while code enforces evidence and package boundaries.
- **Inspectable failure:** malformed output, invalid references, fallbacks, missing evidence, and quality warnings become artifacts rather than disappearing behind polished prose.
- **Reproducibility:** checked-in examples, logged model calls, resumable stages, and package gates make the workflow critiqueable.
- **Transfer-oriented design:** the three demonstration cases differ materially in evidence type and controversy shape, and generic code paths avoid case-specific vocabulary.

## Limitations and risks

The Epistemic Case Mapper is not a truth machine, an exhaustive literature-review system, or a substitute for domain expertise.

Its most important limitation is the absence of completed independent human review. Source-grounded excerpts constrain fabrication, but they do not establish that claims were atomized correctly, relations were labeled correctly, or the corpus was balanced. A faithful map of a biased source packet can still mislead. Because the workflow begins from a bounded corpus, it preserves structure within that boundary but does not by itself solve upstream retrieval quality or option-set construction.

The maps can also preserve too much. Structure preservation is useful only when paired with explicit, source-preserving prioritization; otherwise the reviewer receives a better-organized form of overload. Conversely, a model or curator can omit a decisive perspective before the validator ever sees it. Mechanical validation is strongest at checking internal consistency and weakest at establishing completeness. The system must therefore expose selection criteria, deprioritized material, and recovery paths rather than treating every narrowing as either harmless or erosive.

Relation labels carry interpretation. Calling one claim a challenge, dependency, or crux can smuggle in a stronger inference than the cited source warrants. Every important relation therefore needs domain review even when its endpoints are perfectly grounded.

The evaluation base remains small and partly author-curated. Three case shapes provide a useful transfer check, but they are not evidence of broad generalization, and the strongest regions were selected because they demonstrate the method well. No second operator has yet built or revised a fresh case independently. The scripted blinded local-model baselines are informative comparators, not a paper-grade quantitative benchmark; the original same-context baselines are illustrative only.

The review packets create a surface for accepting, revising, or rejecting judgments, but the repository has not yet demonstrated that an independent reviewer’s decisions reliably propagate through later maps and briefings. Visibility without operational influence would amount to an audit surface rather than a complete review control.

Finally, the decision-memo layer remains a work in progress. Its architecture now makes missing obligations and weak evidence visible, but a good packet does not guarantee a first-rate memo. Backend capability, source coverage, upstream appraisal, and final synthesis still materially affect output quality.

## Recommended next steps

The highest-value next step is not another layer of automation. It is a small, recorded external review: a domain-informed reviewer should accept, revise, or reject a defined sample of claims, relations, cruxes, and structure-loss findings. The exercise should also test whether those decisions persist into regenerated maps and briefings. This would show whether the artifacts lower review cost, localize disagreement, and give review operational influence.

A second operator should then apply the workflow to a fresh, mundane contested question using a predeclared source packet. That would provide a cleaner test of transfer, usability, and hidden author dependence. The evaluation should record time, revision counts, unsupported-claim rates, relation disagreements, and which mapped distinctions changed the final assessment.

Further product work should focus on reviewer decision persistence, conflict handling, and selective prioritization without weakening provenance. Further evaluation should use mechanism-specific tasks: dependency recovery for LHC, claim-normalization and endpoint-boundary retention for eggs, conflict and frame retention for COVID, source recovery across all cases, and local update propagation after a reviewer correction. Decision-space erosion should be evaluated separately with a declared baseline and a measure of whether live options, interpretations, or evidence paths remain visible and recoverable.

## Bottom line

The Epistemic Case Mapper’s core contribution is a change in what counts as a successful AI research output. A readable answer is not enough when the work must be audited, extended, disputed, or handed to another investigator. The project treats sources, claims, relations, caveats, cruxes, prioritization decisions, and review obligations as a durable epistemic artifact, then uses prose as one view over that structure rather than as the structure itself.

The prototype demonstrates that reasoning-structure preservation and epistemic artifact fidelity are technically workable across several case shapes. It can reveal structure that flat synthesis makes difficult to inspect and can diagnose downstream decision-space erosion when lost structure removes live alternatives from review. It also documents its present boundary honestly: the maps still need independent human review, generalization remains under-tested, and better structure does not automatically produce better prose. That combination—a concrete, compounding handoff method plus visible unresolved risks—is the strongest current case for the project and the clearest fit with the FLF competition.

## Suggested reading and demo path

- `docs/START_HERE.md` — five-minute orientation.
- `docs/submission/PROOF_BY_EXAMPLE.md` — compact before/after examples and runnable checks.
- `examples/lhc_black_holes/worked_region_cosmic_ray_map.md` — clearest mapped dependency.
- `examples/eggs/worked_region_observational_vs_rct_map.md` — evidence-type and subgroup boundaries.
- `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md` — bounded adversarial disagreement.
- `docs/submission/EVIDENCE_AND_LIMITATIONS.md` — full risk register.
- `docs/submission/REPRODUCE.md` — deterministic and live-model paths.
- `docs/guides/RUNNING_THE_PIPELINE.md` — runnable workflow details.
- `docs/review/REVIEWER_START_HERE.md` — human-review handoff.
