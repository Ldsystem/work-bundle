---
name: orch-create-specification
description: 'Create AI-ready implementation specifications under orchestration spec roots.'
---

# orch-create-specification

## Scope

Create AI-ready implementation specifications under orchestration spec roots.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Spec Shell First

Before any long evidence gathering, create the specification artifact shell first.

- Include the front matter required by the specification contract.
- Add `Initial User Purpose Evidence` and `Draft Requirement Breakdown` sections immediately in the initial shell.
- Populate `Initial User Purpose Evidence` only from the current user request and visible supplied artifacts.
- Treat `Draft Requirement Breakdown` as provisional. Revise it after bounded evidence gathering; do not silently replace it.
- Do not begin broad repository exploration until the shell exists.

## Project Metadata Preflight

After the specification shell exists and before durable-knowledge retrieval, broad repository evidence gathering, CodeGraph use, or source inspection, perform project metadata preflight for every target source repository that could affect the specification.

- Read `$project_root/.work-bundle/project.yaml` and identify applicable `source_repositories[]`.
- Use the bootstrap-resolved project registry only as locator evidence; do not treat it as working-state authority.
- For Git-backed repositories, compare actual `working_branch` and actual HEAD commit against metadata `working_branch` and `last_commit_id` using non-mutating Git commands.
- Record CodeGraph support from metadata and `.codegraph/` marker presence. If `.codegraph/` is absent, record `no-index` or `not-indexed` and do not initialize CodeGraph or run `codegraph sync`.
- Stop before extended evidence gathering and add a blocking open question when project metadata is inaccessible, missing required repository fields, contradictory with the registry, stale in a way that affects evidence trust, branch mismatched, or CodeGraph metadata is inconsistent.
- When metadata is valid or a no-index fallback is applicable, carry compact preflight evidence into Source Context so planning and execution can trust the baseline without re-inferring it from conversation memory.

## Knowledge Gateway

Before drafting from durable project knowledge, use `keep-summarizing` with `what-is-helpful` gateway mode. Do not directly browse `.work-bundle/knowledge/`.

For v3 knowledge, formulate polarity-neutral and stage/perspective/status-neutral query anchors from the user purpose, affected artifacts, features, functionality, components, files, APIs, schemas, workflows, and explicit names. Implementation specification work uses `implementation_spec` only as classification and output-grouping intent; it must not discovery-filter candidates to that lifecycle stage before authority classification.

Source context must record the neutral anchors, cross-stage discovery evidence, and agent-owned classification. Separate durable results as `authority`, `candidate`, `background`, and `blocked`, and include material supporting, opposing, constraining, unresolved/open-question, obsolete/replaced, or irrelevant-with-reason evidence when it affects requirements, architecture, workflow, policy, API, persistence, validation, execution behavior, or user-purpose conflict. Label repository evidence by role such as skill, rule, reference, script, test, design, or user input. Only `authority` durable context may shape requirements, constraints, interfaces, acceptance criteria, or downstream task instructions.

Material non-authority durable context (`candidate`, `background`, or `blocked`) must stay visible when it relates to the user purpose, architecture, workflow, policy, API, persistence, validation, execution behavior, or a conflict. Record it as rationale, traceability, conflict evidence, or open-question input; do not promote it into a requirement unless the user resolves it or an approved durable-knowledge workflow later makes it authority. Candidate, background, and blocked evidence is non-shaping by default and remains non-shaping unless user resolution or promoted authority explicitly changes that state. Non-material non-authority context may be summarized as outside scope or omitted.

When the gateway returns no notes that support the current user purpose, do not block solely for that absence. Record the query and evidence gap, analyze the user purpose directly, inspect current repository evidence where possible, and use Design interrogation only for unresolved decisions that repository evidence cannot answer.

The specification is the first execution-chain artifact:

```text
spec -> plan -> phase -> task -> execute -> handoff
```

It must carry enough accepted context for planning and execution without future knowledge-base lookup.

## Requirements

- Use precise, explicit, unambiguous language.
- Distinguish requirements, constraints, assumptions, alternatives, and open questions.
- Create the specification shell before extended evidence gathering so the artifact always has front matter plus `Initial User Purpose Evidence` and `Draft Requirement Breakdown`.
- Run project metadata preflight after shell creation and before broad repository evidence gathering; record branch baseline, commit baseline, registry locator, and CodeGraph no-index evidence in Source Context when applicable.
- Inspect relevant note states and open-question watchpoints through the approved knowledge gateway when durable knowledge affects the scope.
- Surface relevant draft, proposed, conflicting, stale, or missing-evidence context as uncertainty; do not convert it into requirements.
- Include an `Open Questions` section. If relevant uncertainty exists, list ID, question or uncertainty, related scope, source, blocking yes/no, required resolution, and at least one feasible advised option. If none exists, state `None for this specification scope.`
- Treat material unsettled evidence as blocking only when it affects requirements, architecture, workflow, policy, API, persistence, validation, execution behavior, or conflicts with user purpose.
- Include a `Knowledge Base Update` section in every new or repaired specification.
- In `Knowledge Base Update`, allow only these dispositions for new specs: `required`, `not-needed`, `blocked`.
- In `Knowledge Base Update`, require `Expected durable conclusions`, `Evidence sources`, `Responsible follow-up`, `Blocks review/archive`, and `Rationale`.
- Set `Knowledge Base Update` disposition to `required` when accepted Design interrogation conclusions establish new durable orchestration workflow policy or reusable process behavior.
- When no durable update is expected, set `Expected durable conclusions` to `None for this specification scope.`
- Record only disposition and follow-up path in `Knowledge Base Update`; do not instruct agents to write durable notes from the specification.
- Define domain terms and acronyms.
- Include affected modules, files, APIs, schemas, data flows, workflows, compatibility, migration, deployment, testing, and operational constraints when relevant.
- For source-code, script, skill, rule, workflow, API, data-contract, or validation-affecting changes, perform recursive impact-radius traversal before finalizing: move a component cursor through upstream components the current component refers to and downstream components that consume or validate it until no discovered component can block, contradict, or require additional updates.
- Include validation/test artifacts in impact-radius traversal when applicable, including unit tests, contract tests, validators, golden fixtures, rule contract tests, workflow tests, and other referring validation consumers.
- Record impact-radius evidence compactly in source context with current component, upstream components, downstream components, validation/test artifacts, evidence paths, blocking status, and required update classification.
- If recursive upstream/downstream or validation/test impact-radius evidence is inaccessible, ambiguous, or incomplete for a material change, record a blocking open question instead of silently narrowing scope.
- Include examples, edge cases, fallback decisions, and validation expectations when useful.
- Record missing or uncertain context as assumptions or open questions.
- Do not store specifications under `.work-bundle/knowledge/`.

## Extra Evidence Loop

After initial evidence collection and before finalizing the specification, run an agent-owned semantic evidence round. Scripts may support mechanical checks, but scripts must not decide whether the specification has enough evidence.

Each round must check:

1. Drift against the user purpose and resolved user decisions. If drift exists, repair the specification.
2. Gaps in required context, affected files, decisions, constraints, validation, or open questions. If evidence is available, repair the gap.
3. Evidence support for all user requirements. If support is missing but more evidence exists through the approved knowledge gateway or current repository context, collect it through that approved path and update the specification. If no more evidence exists, record the unsupported requirement or decision as a blocking open question.
4. Impact-radius completeness for each changed component: confirm upstream traversal, downstream traversal, and validation/test artifact coverage have reached a non-blocking stopping point, or record the remaining component cursor as a blocking open question.

Use the simple change-driven loop:

```text
Run evidence round
  -> if the round changed, fixed, added, removed, or reclassified anything:
       run another round
  -> if the round changed nothing:
       break
```

Record the result compactly in the specification body:

```text
Extra evidence loop:
- round 1: changed|unchanged|blocked - <drift/gap/evidence result>
- round 2: changed|unchanged|blocked - <drift/gap/evidence result>
Final result: verified|blocked
```

If any round records a blocking open question, the final result and quality gate remain `blocked` until the question is resolved and the loop runs again.

## Design Interrogation

Use Design interrogation when the approved gateway has no supporting note for the user purpose, or when repository evidence still leaves the ultimate design intent under-specified. Inspect repository evidence first; ask the user only for decisions that cannot be resolved from existing files or accepted context.

Ask one question at a time, include the agent's recommended answer, and record the accepted answer or unresolved state in the specification source context or evidence section. Accepted conclusions are source evidence for the specification, but they are not durable knowledge until an approved follow-up persists them.

## Hard Rules

- Stop if the spec cannot be self-contained enough for planning.
- Stop before extended evidence gathering when project metadata preflight reports missing required metadata, branch mismatch, stale baseline that affects evidence trust, registry contradiction, inaccessible target repository, or inconsistent CodeGraph state.
- Stop if durable knowledge is needed but was not retrieved through `keep-summarizing`.
- Stop before downstream implementation planning when `Quality gate: blocked` is recorded.
- Do not implement source changes, edit application/test files, run migrations, apply patches, or execute plan tasks while creating a specification.
- If the user also asks for implementation, finish the specification artifact first, then stop and require an explicit `execute-plan` request.
- Do not defer required execution context to future `.work-bundle/knowledge/` lookup.
- Do not mix implementation plan tasks into the spec; record planning needs as constraints or open questions.
- Do not hide unresolved architecture, data model, API contract, persistence, execution-flow, or authority decisions inside assumptions.
- Do not instruct agents to write durable knowledge directly from the specification; only record disposition, evidence expectations, and the responsible follow-up path.
- Do not reintroduce `wb-select-role-context`; the current contract is no role-context except the explicit deprecation/exclusion note below.
- Do not write raw chat logs, unsupported facts, or hidden reasoning.

## Output

Save under:

```text
.work-bundle/orchestration/spec/active/spec-[purpose]-[slug].md
```

Allowed high-level purpose prefixes: `schema`, `tool`, `data`, `infrastructure`, `process`, `architecture`, `design`.

Use valid Markdown with YAML front matter.

## Contract

Load only when creating or validating:

- `references/assets/orchestration/contract/specification-v1.md`

If the contract lacks explicit sections for source context, execution context, assumptions, alternatives, open questions, or fallback decisions, include those sections anyway.

Every generated specification must also include this section even if the contract/template is stale:

```markdown
## Knowledge Base Update

- **Disposition**: required|not-needed|blocked
- **Expected durable conclusions**:
  - <candidate durable conclusion or `None for this specification scope.`>
- **Evidence sources**:
  - <expected implementation, validation, handoff, or source evidence>
- **Responsible follow-up**: <approved follow-up path or `none`>
- **Blocks review/archive**: yes|no
- **Rationale**: <why the disposition applies>
```

Every generated specification must include a body-level quality gate result. `verified` and `blocked` are quality-gate results only; do not add `verified` to YAML front-matter lifecycle status language.

```markdown
## Quality Gate

Quality gate: verified|blocked

Checked:

- user purpose coverage
- durable knowledge classification
- current repository contract coverage
- affected-file coverage
- assumptions and alternatives
- open questions

Findings:

- <gap or none>

Extra evidence loop:
- round 1: changed|unchanged|blocked - <drift/gap/evidence result>
- round 2: changed|unchanged|blocked - <drift/gap/evidence result>
Final result: verified|blocked
```

## Validation

Confirm the spec is self-contained, cites role-labeled source context, carries execution-relevant authority knowledge and repository evidence into the body, records project metadata preflight evidence or a blocking open question, surfaces material non-authority context without letting it shape requirements, records assumptions/open questions with advised options, includes Design interrogation evidence when unsupported or under-specified purpose required it, includes the required `Knowledge Base Update` section and no-update wording when applicable, records `Quality gate: verified|blocked` in the body, follows naming/location rules, and does not require downstream agents to read `.work-bundle/knowledge/`.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-knowledge-gateway`: `rules/orchestration/orch-knowledge-gateway.md`
- `orch-open-questions`: `rules/orchestration/orch-open-questions.md`
- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-review-completion`: `rules/orchestration/orch-review-completion.md`

## Rule Loading (mandatory)

Before substantive specification work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive orchestration work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or directive summaries as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress orchestration task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/orchestration/contract/`

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`).

> **Deprecation:** The role-context subsystem is deprecated; see spec §0.9 in `spec-process-orch-skill-rule-boundary-optimization-20260611`. Do not invoke it from orch skills.
