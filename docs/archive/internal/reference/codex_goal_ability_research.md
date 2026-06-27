# Codex Goal Ability Research

Last researched: 2026-06-26.

Sources are official OpenAI developer documentation and cookbook pages. The OpenAI developer-docs MCP server was added locally with:

```bash
codex mcp add openaiDeveloperDocs --url https://developers.openai.com/mcp
```

The MCP tools were not available in this running session without restart, so this note uses official OpenAI web documentation as fallback.

## Relevant Official Sources

- Codex prompting: https://developers.openai.com/codex/prompting
- Follow a goal use case: https://developers.openai.com/codex/use-cases/follow-goals
- Codex app commands: https://developers.openai.com/codex/app/commands
- Codex best practices: https://developers.openai.com/codex/learn/best-practices
- AGENTS.md guide: https://developers.openai.com/codex/guides/agents-md
- PLANS.md / ExecPlans cookbook: https://developers.openai.com/cookbook/articles/codex_exec_plans
- Iterate on difficult problems use case: https://developers.openai.com/codex/use-cases/iterate-on-difficult-problems
- Subagents guide: https://developers.openai.com/codex/subagents
- Codex web / cloud overview: https://developers.openai.com/codex/cloud

## What Goal Mode Is

Codex Goal mode is designed for longer tasks where Codex should keep working toward a persistent objective rather than stopping after one normal turn. In official docs, a goal acts as both the initial prompt and the completion criteria. Codex uses it to choose next actions and decide whether the task is complete.

Goal mode can be started with `/goal` in the app, IDE extension, or CLI. It can be paused, resumed, edited, or cleared. If the feature is not visible, OpenAI documents enabling it through:

```toml
[features]
goals = true
```

or:

```bash
codex features enable goals
```

## When Goal Mode Is Appropriate

Goal mode is best for work with:

- one durable objective,
- a clear success condition,
- a validation loop,
- enough room for Codex to make progress without constant steering,
- artifacts or commands that prove progress.

Official examples include:

- code migrations,
- large refactors,
- deployment retry loops,
- experiments,
- games,
- side projects,
- prompt optimization against an eval suite.

OpenAI cautions against using a goal for a loose list of unrelated work. A good goal is larger than one prompt but smaller than an open-ended backlog.

## What A Good Goal Must Specify

The most relevant pattern for this project is:

- objective: what Codex should achieve,
- constraints: what Codex should not change,
- context: files, docs, issues, logs, or plans to read first,
- validation: commands, reports, tests, or reviewable artifacts that prove progress,
- checkpointing: how often to record progress and what to record,
- stopping condition: what must be true before Codex can stop.

The official "Follow a goal" use case frames the central contract as making sure Codex knows what "done" means before it starts.

## Relationship To Plan Mode

OpenAI recommends planning before difficult or ambiguous work. Plan mode lets Codex gather context, ask clarifying questions, and build a stronger plan before implementation. The app command docs explicitly say `/goal` can be shaped with `/plan` first.

Practical implication:

1. Use `/plan` when the objective is underspecified or strategy-sensitive.
2. Turn the resulting plan into a bounded `/goal` only after the success condition is clear.
3. Do not use `/goal` to discover a vague research agenda unless the first goal is itself a bounded scoping task.

## Relationship To AGENTS.md

AGENTS.md is the durable instruction layer for Codex. Official docs say Codex reads AGENTS.md before doing work and builds an instruction chain from global and project-specific guidance.

OpenAI recommends keeping AGENTS.md practical and encoding:

- repo layout,
- build/test/lint commands,
- engineering conventions,
- PR expectations,
- constraints and do-not rules,
- what done means,
- how work should be verified.

Practical implication:

`epistemic_case_mapper` should eventually add an `AGENTS.md` that tells Codex how to work in this repo, including how to handle source provenance, case maps, generated artifacts, citations, and validation commands.

## Relationship To PLANS.md / ExecPlans

OpenAI's PLANS.md cookbook describes execution plans as self-contained living documents that a coding agent can use for multi-hour problem solving. The key idea is that a plan should contain enough context for a fresh agent or human novice to restart and complete the task without hidden prior context.

Relevant ExecPlan requirements:

- self-contained,
- living document,
- novice-guiding,
- outcome-focused,
- observable behavior, not just code changes,
- progress tracking,
- surprises and discoveries,
- decision log,
- outcomes and retrospective,
- exact commands and expected observations,
- validation and acceptance criteria,
- idempotence and recovery guidance.

Practical implication:

For this repo, substantial changes should be driven by checked-in plan files, not only chat history. That matters because the FLF prototype itself is about preserving structured context across long investigations.

## Relationship To Evals And Iteration

OpenAI's "Iterate on difficult problems" use case recommends giving Codex scripts and reviewable artifacts so it can improve a hard task through repeated measurement. This is most useful when each iteration can be scored, even if success is partly subjective.

Important ingredients:

- scoring command,
- reviewable artifacts,
- one focused improvement per iteration,
- progress log,
- explicit target score or stopping rule,
- inspection of generated artifacts,
- remaining-risk report.

Practical implication:

For FLF work, Codex goal loops should not merely "improve the prototype." They should optimize against a visible artifact and review rubric, for example:

- source coverage,
- claim provenance,
- relation density and correctness,
- preservation of caveats,
- preservation of similar-but-not-identical claims,
- crux identification quality,
- auditor navigability.

## Relationship To Subagents

Codex can use subagents when explicitly asked. The docs describe subagents as useful for parallel exploration or implementing a multi-step feature plan. Codex handles orchestration, waits for results, and consolidates findings.

Constraints:

- subagents are not spawned unless explicitly requested,
- they consume more tokens than a single-agent run,
- they inherit sandbox and approval policy unless configured otherwise.

Practical implication:

Subagents can be useful for this repo when work naturally splits into independent slices, such as:

- one agent reviews LHC source material,
- one agent reviews eggs source material,
- one agent audits the schema,
- one agent evaluates judge-facing usability.

Subagents should not be used for tightly coupled edits to the same files unless write ownership is explicit.

## Relationship To Cloud Work

Codex cloud can run repository tasks remotely, in parallel, using configured environments. OpenAI's Codex web docs describe cloud tasks as useful for background work and parallel delegation.

Practical implication:

Cloud tasks are relevant once this repo has:

- a clean remote,
- reproducible setup,
- test commands,
- source ingestion scripts,
- generated artifacts that can be inspected after a cloud run.

Goal mode plus cloud work is potentially useful for running longer case-map generation or audit loops, but only after the project has stable validation commands.

## Limitations And Risks

Goal mode does not remove the need for a good task specification. It amplifies whatever objective, constraints, and validation loop are provided.

Likely failure modes:

- vague goal produces broad, low-signal churn,
- missing stop condition causes premature completion or overwork,
- no scoring command means Codex cannot tell whether it improved the artifact,
- no source/provenance standard means summaries can become fluent but unauditable,
- no plan ledger means context is trapped in chat history,
- multiple agents can conflict if file ownership is not explicit,
- cloud tasks can diverge if local state is not pushed or setup is not reproducible.

## Implications For The FLF Prototype

The FLF prototype should exploit Codex's goal ability as a workflow pattern, not as a magic capability.

Recommended repo additions:

1. Add `AGENTS.md` with project-specific expectations.
2. Add a `PLANS.md` or `.agent/PLANS.md` standard derived from the agent plan quality guide.
3. Add a case-map audit rubric that can be run or filled repeatedly.
4. Add a deterministic validation command that checks schema validity and artifact completeness.
5. Add example `/goal` prompts for:
   - building one case map,
   - auditing one case map,
   - improving the mapper against a rubric,
   - preparing a judge-facing worked example.

## Example Goal For This Repo

```text
/goal Produce a judge-facing LHC black hole risk case-map demo from the current manifest without stopping until artifacts/lhc_black_holes contains a valid case_map.json, a navigable report.md, and an audit.md that scores the artifact against docs/reference/flf_epistemic_case_study_competition_criteria.md. Before editing, read AGENTS.md, docs/WORKFLOW_SPEC.md, docs/protocols/epistemic_case_map_v0.md, and the LHC case manifest. Keep source provenance explicit, do not invent source claims, run the schema/test validation commands after each meaningful change, and record remaining evidence gaps.
```

## Bottom Line

Codex's goal ability is a durable execution mechanism for long-running, verifiable work. It is strongest when paired with:

- reusable repo instructions,
- self-contained execution plans,
- explicit validation commands,
- reviewable artifacts,
- progress logs,
- clear stop conditions.

For `epistemic_case_mapper`, this is directly aligned with the project thesis: preserve decision-relevant structure outside the transient chat context so both humans and agents can continue the investigation without losing provenance, caveats, cruxes, or unresolved options.
