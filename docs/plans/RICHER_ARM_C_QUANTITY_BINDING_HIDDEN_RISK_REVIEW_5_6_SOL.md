# Hidden-Risk Review: Richer Arm C Quantity Binding Plan

Reviewer: `codex exec -m gpt-5.6-sol`
Mode: read-only red-team review

## Prompt

Assume `docs/plans/RICHER_ARM_C_QUANTITY_BINDING_PLAN.md` is implemented faithfully and all listed unit tests and artifact checks pass. Find hidden risks where the production memo still fails to become meaningfully more decision-useful. Focus on mechanism failures, false-positive acceptance criteria, model judgment not being used at the right place, semantic information still lost between stages, and ways the memo could become more numeric but not more useful.

## Verdict

Revise before production promotion. The plan should improve numeric retention, but it still permits a structurally valid, fully traceable memo to misuse the numbers and become less decision-useful.

This is already visible in an accepted experiment: the memo describes `1.25` as both a pooled relative risk and an LDL "hazard ratio," while the associated confidence interval crosses 1.0. The evaluation nevertheless reports zero quantity/source warnings and passes.

## Hidden Failure Modes

- Quantity presence is mistaken for semantic correctness. The canonical quantity contract currently retains only value, interpretation, role, and source IDs; statistic type, endpoint, unit, comparator, population, time horizon, direction, and uncertainty pairing can disappear. The plan does not explicitly require these fields to survive into the actual section prompt and validator.
- Atomic IDs can detach quantities that belong together. A point estimate, confidence interval, exposure increment, and endpoint may become separately selectable. The model can quote the estimate without uncertainty, pair it with another interval, or relabel an RR as an HR while all selected IDs remain valid.
- The model selects numbers, but no stage owns the judgment about their permissible inference. `warrant` and `decision_effect` are free prose. Nothing validates statistical significance, causal versus observational interpretation, surrogate versus clinical endpoints, relative versus absolute effect, or whether the number actually changes the decision.
- Frozen-answer validation can suppress legitimate epistemic updating. If selected quantities materially contradict the frozen answer or confidence, "no drift" rewards rationalization rather than escalation.
- Coverage is circular. "Quantity coverage improves for selected evidence" lets Arm C improve its score by declining difficult anchors or demoting evidence. Analyst-approved quantities become obligations only when their evidence is selected; accounting an item as demoted is not equivalent to correctly weighing it.
- Conflicting estimates can remain traceable but unsynthesized. The memo may cherry-pick one estimate or list several without explaining differences in population, design, endpoint, or uncertainty. That is numeric density, not calibration.
- Preserved dependencies may still be inert. Parallel section writers can receive `depends_on_move_ids` without actually resolving cross-section premises. Field survival therefore does not prove that the practical recommendation follows from the evidence.
- Source grounding remains weaker than the numeric precision suggests. Missing source IDs, lineage fan-out, semantic duplicates, and conflicting estimates must be blocking semantic tests where they bear on decision use, not only generalization checks.

## Why The Current Acceptance Criteria Might Miss Them

- Validators test number surfaces and IDs, not whether the number is correctly named, interpreted, paired, or applied.
- "Fields survive into prompts" does not test whether the writer uses them correctly.
- "More selected quantities" uses a model-controlled denominator.
- Traceability can pass when the correct source is cited for the wrong endpoint or inference.
- Move count and move-type diversity are weak proxies for genuine argument structure.
- "Manually reads as more decision-grade" lacks a rubric, blinding, independent reviewer, and blocking error taxonomy.
- Eggs plus one unrelated replay is too small to expose confidence-interval pairing, absolute-versus-relative risk, conflicting estimates, qualitative cases, and surrogate-endpoint failures.

## Highest-ROI Plan Revisions

1. Replace quantity atoms with indivisible quantity-assertion bundles containing: estimate and interval, statistic type, unit/denominator, endpoint, population, exposure/comparator, time horizon, direction, source ID and span, uncertainty interpretation, and allowed/forbidden inference.
2. Make Arm C select a bundle and state its intended use: which claim it calibrates, the warranted decision update, uncertainty reading, and language that must not be implied. Deterministic code should validate identities; model or human judgment should validate inference.
3. Add blocking semantic-realization tests: RR/HR swaps, endpoint/subgroup swaps, detached confidence interval, omitted units, confidence interval crossing the null described as significant, observational association rendered causally, and surrogate outcomes converted into clinical recommendations.
4. Protect analyst `must_use` evidence and conflict sets from silent demotion. If selected anchors contradict the frozen answer or confidence, return to analyst adjudication instead of enforcing no drift.
5. Replace numeric-coverage promotion with a blinded task rubric: can a reader identify the effect size, uncertainty, applicable population, strongest counterweight, action threshold, and what would change the answer? Any material statistic/endpoint/significance error should block promotion.

## Production Risk Rating

**High: 4/5.** The architecture is auditable, but its likely residual failure is especially dangerous: polished, source-tagged quantitative prose that passes every gate while conveying the wrong statistical or decision meaning.

Verification was read-only: plan, prior review, current projection/quantity code, and saved accepted artifacts were inspected; no files were edited and no tests were run by the reviewer.
