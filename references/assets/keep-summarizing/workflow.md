# keep-summarizing Workflow

## Workspace Knowledge Layout

```text
<workspace-root>/
  AGENTS.md
  script/index.yaml              # multi-repository mode only
  credentials/credentials.yaml  # multi-repository mode only; excluded from knowledge access
  <member-project-root>/
  .work-bundle/
  knowledge/
    project.yaml
    notes/
      <lifecycle-stage>/<leaf perspective tree>
    open-questions/
    context-packs/
    indexes/
  orchestration/
    docs/
    spec/
    plan/
    handoff/
```

`<workspace-root>/.work-bundle/knowledge/` is the default durable source of truth for one managed workspace. A nested member cwd resolves upward to the containing workspace; source inspection remains scoped to that member `project_root`. Single-repository mode remains current with `workspace_root == project_root`. Legacy knowledge roots are readable only when explicitly selected for migration or read-only intake.
Handoff artifacts live under `.work-bundle/orchestration/handoff/` and are not durable knowledge.

## V3 Lifecycle Authority Model

Durable notes use lifecycle stage as the first path partition and perspective as the second partition:

```text
notes/<lifecycle-stage>/<perspective-leaf>/
```

Required front matter:

```yaml
lifecycle_stage: tender | investigation | customer_design | bidding | development_design | implementation | deployment | go_live_delivery | operation
perspective: <lifecycle-stage>/<perspective-leaf>
status: draft | proposed | confirmed | implemented | current | superseded | deprecated | rejected
source_type: discussion | tender_doc | investigation_note | design_doc | bid_doc | source_code | handoff | plan_review | deployment_record | delivery_record | runtime_observation
```

`status` is the only maturity and authority field. Do not create or preserve `truth_level`.

Front matter `evidence` is required when evidence affects status, retrieval authority, validation, or promotion. Body evidence may explain rationale, but it does not replace front matter evidence for promoted statuses.

SQLite FTS and vector artifacts are derived from Markdown. FTS handles exact identifiers, rule names, file names, API/schema/table names, and explicit references. Vector retrieval improves semantic recall around note chunks, artifact names, feature/functionality anchors, and summaries. Both are disposable query mechanics, not canonical knowledge.

Retrieval queries must be polarity-neutral and stage/perspective/status-neutral unless those terms are the explicit subject. Build anchors from the requested artifact, feature, functionality, component, file, API, schema, workflow, or explicit name. Scripts return mechanical candidates and metadata such as anchors, source paths, lifecycle/status metadata, FTS rank, vector status or distance, fusion rank, and bounded-expansion paths. Agents classify relevance, authority, polarity, materiality, and blockers; users resolve material conflicts that evidence cannot settle.

JSONL indexes remain maintained machine-readable derived outputs. Agents must not browse `document-registry.jsonl`, `chunk-registry.jsonl`, or `open-question-registry.jsonl` as the primary exploration surface.

Gateway retrieval uses this pipeline:

```text
neutral task query
  -> hybrid candidate discovery through approved query surfaces
     (SQLite FTS + vector status/candidates + bounded mechanical expansion when available)
  -> visibility, sensitivity, and scope filtering
  -> minimum necessary full-body validation
  -> agent classification for relevance + authority + polarity + materiality + blocker status
  -> authority | candidate | background | blocked | supporting | opposing | constraining | watch context
  -> smallest useful classified result
```

Lifecycle limits authority and durable write ownership for the work target; lifecycle does not hide relevant discovery candidates. FTS rank, vector distance, fusion rank, recency, and lifecycle proximity may help discovery or ranking, but they cannot override agent-classified authority. Only `authority` results may directly shape requirements, executable tasks, implementation decisions, or review conclusions. Relevant `candidate`, `background`, `blocked`, opposing, and constraining results remain visible with their uncertainty or incompatibility explained.

For orchestration gateway use, run `scripts/ks.py query --project <slug> --query <neutral-query> --include-background`. When a caller supplies a policy, pass `--target <retrieval-policy>` as a policy hint for later agent classification, not as a discovery-stage filter. Valid policies are `implementation_spec`, `implementation_plan`, `execution`, `customer_spec`, `bidding`, `deployment`, and `operation`.

Orchestration must retrieve durable knowledge through `ks-what-is-helpful` gateway mode and must not browse `.work-bundle/knowledge/**` directly. `orch-execute-plan` remains a no-retrieval stage: execution consumes carried spec, plan, phase, task, declared handoff, and task-scoped source/test context only, and must not invoke the gateway.

## Project Registry

Use `<workspace-root>/.work-bundle/project.yaml` as working-state authority for workspace metadata, member bindings, override inputs, copy restrictions, and resolution priority. Resolve the global project registry from `~/.work-bundle/bootstrap.yaml` only as a bounded cross-workspace locator fallback. Use workspace-root `AGENTS.md`, initialized from `references/assets/template/AGENTS.md`, for WorkBundle runtime entry rules. Resolve stable role context from `roles/` role profiles.

In both workspace modes, reusable workspace utilities live under singular `<workspace-root>/script/` and are reusable only through `script/index.yaml`; toolkit plural `scripts/` remains separate. The protected credential store lives at `<workspace-root>/credentials/credentials.yaml` in both modes and remains local-only. Never read, index, embed, summarize, copy, or expose it. Credential-backed operations belong to `wb-credential-use`, and only credential IDs plus redacted metadata may cross agent-visible surfaces.

## Structural-Value Test

This test is a hard gate. If a candidate point does not pass, do not persist it as durable knowledge.

Save a point only when at least one is true:

- It changes a stable design.
- It clarifies a reusable process flow.
- It clarifies a reusable data flow.
- It clarifies architecture, module boundaries, or deployment shape.
- It defines a code-structure convention.
- It records an important decision or rejected option.
- It captures a reusable pattern.
- It affects future implementation choices.

Do not save:

- one-off bugs
- temporary errors
- raw implementation logs
- exploratory thoughts with no durable conclusion
- guesses, wishes, or weak proposals as accepted knowledge
- agent-generated open questions unless the user confirms they are valuable future work
- credentials, tokens, personal data, or private keys
- raw chat transcripts

Before writing any note, record the passing reason in the agent response or note draft. If the reason is unclear, stop and ask.

## Mandatory Persistence Gate

Before any write, the agent must complete all checks below:

1. Project is resolved to `.work-bundle/knowledge/` or an explicitly selected external legacy source for migration/read-only intake.
2. The selected ks skill allows writing.
3. Target path is under `notes/<lifecycle-stage>/<leaf-perspective>/`, `open-questions/<lifecycle-stage>/<leaf-perspective>/`, or `context-packs/`.
4. The perspective is a lifecycle-aware leaf path from `references/assets/keep-summarizing/perspectives.md`.
5. The content excludes raw chat logs, secrets, credentials, personal data, temporary command output, and one-off debugging details.
6. Lifecycle stage, status, source type, and evidence are valid and justified.
7. Existing related notes were checked for duplicate or conflicting knowledge through approved neutral query surfaces rather than broad JSONL browsing.
8. Required front matter is present before completion.

If any check fails, do not write. Return `Waiting for your direction` with the failed check and concrete next options.

## Canonical Note Policy

Each durable fact should have one canonical note in the most specific leaf perspective. Do not maintain full duplicate `current` notes across perspectives.

When the same durable fact appears in multiple notes:

- choose the canonical perspective that best owns the fact;
- update or propose deprecating duplicate full-body notes;
- keep only a short cross-perspective stub when a secondary perspective needs discoverability;
- make the stub link to the canonical note and avoid restating the full rule;
- ask before changing or deprecating conflicting `current` notes.

Implementation and interface notes may describe code boundaries, API shape, module ownership, integration contracts, or file locations. They must not be the only home for stable domain rules, business semantics, validation rules, lifecycle rules, source-of-truth rules, or process/data-flow rules. Extract those rules into the matching domain, workflow, data, validation, or source-of-truth perspective note, then link back from the implementation-shaped note.

## Context Pack Policy

Context packs are temporary scaffolding for agent startup, not canonical project knowledge.

- Do not use `context-packs/` as an authority during normal knowledge browsing.
- Load context packs only when the user explicitly asks to inspect, refresh, migrate, decompose, or build context packs.
- If a context pack is still useful after 30 days, break it down into atomic perspective notes or refresh it from current canonical notes.
- If a context pack duplicates atomic notes, prefer the atomic notes and treat the pack as stale scaffolding.
- Do not copy context-pack prose into retrieval output unless the task is specifically about context-pack maintenance.

## Breakdown And Extraction Closure

For `ks-breakdown-design` and `ks-extract-valuable-points`, persistence is the default end state, not an optional follow-up.

Hard rule:

- Do not end the current conversation with approved durable points only in the chat.
- Persist each approved durable point as an atomic note or update under `notes/<lifecycle-stage>/<leaf-perspective>/`.
- Persist unsettled but potentially important points as `draft` when they pass the structural-value test and no stronger status is justified.
- Rebuild indexes before reporting completion.
- If required direction is missing, stop immediately with `Waiting for your direction` and ask the minimum blocking questions.
- If the active environment cannot ask blocking questions mid-work, persist all safe points first, save uncertain candidates as `draft`, rebuild indexes, then ask remaining questions in the final response.

This closure rule does not override safety gates: never persist secrets, raw chat logs, personal data, broad-perspective notes, root-level Markdown, or conflicting replacements of `current` notes without explicit direction.

## Open Question Persistence

Agents may generate open questions while reasoning, planning, reviewing, or breaking down designs. Generated open questions are response content by default, not knowledge-base content.

Persisted open questions are standalone watchpoints under `open-questions/`, not durable facts inside `notes/`.

Write an open question to the project knowledge repo only when at least one is true:

- The user provides the question as a future problem, such as `there is a problem to be fixed in future`.
- The agent proposes the question and the user confirms it is worth tracking, such as `record it`, `we will resolve it later`, `we will talk about it later`, or `it's a problem and we will resolve it later`.
- The user explicitly asks to persist open questions for the current task.

Do not write an open question when:

- it is just the agent's uncertainty
- it is a weak guess
- it is a missing fact discovered while preparing reader-facing output through `orch-create-document`
- the user only says `sure`, `good suggestion`, or other weak approval without indicating future tracking value

Persisted open questions must be clearly labeled as accepted future work, not as facts.

If user confirmation is weak or ambiguous, do not persist the open question. Ask for explicit tracking confirmation.

Recommended heading for persisted questions:

```text
Accepted Open Questions
```

Do not use a plain `Open Questions` section in curated notes unless the questions satisfy this persistence rule.

## Open Question Watch Context

When `keep-summarizing` is active for a project, the maintained open-question registry may be used as watch-context metadata. It is not the primary exploration surface and must not replace the approved query surface or material body validation.

Open questions are watch context:

- They remind the agent about accepted unresolved project problems.
- They are not embedded runtime rules.
- They do not constrain implementation as facts.
- They should not appear in reader-facing documents generated through `orch-create-document`.

When current work matches an open question's `trigger_terms`, the agent should say which watchpoint matched and ask the user what to do next:

```text
This touches open question `oq-architecture-step-constraints-model`: Step Constraints Model.

Choose one:
1. Mark it resolved and record the accepted answer.
2. Keep it open and append this context.
3. Split it into a new open question.
4. Ignore it for now.
```

Resolved open questions should keep their standalone note, change `status` to `resolved`, record a resolution summary, and optionally link to a durable note or ADR.

## Confirmation Strength

Speculation is not durable knowledge. Accepted decisions, stable constraints, and reusable patterns are durable knowledge.

Weak signals should not become `current` notes:

```text
sure
good suggestion
sounds good
I think we should do this
we might need this
maybe use this approach
```

Handle weak signals as:

- no save when the idea is temporary or low impact
- `draft` when it may become important
- non-persisted open question in the response when it affects architecture or implementation direction but has not been accepted for tracking

Strong signals may become durable knowledge:

```text
Use this as the design decision.
This is the accepted approach.
Persist this to the knowledge repo.
Record this as an ADR.
Update the architecture notes with this.
This approach is mature now; save it as current.
```

Before saving a weak or ambiguous signal as `current`, ask for confirmation or save it as `draft`.

## Skill-Aligned Flow

For save/update work, align execution with current ks skills:

1. Use `ks-extract-valuable-points` to extract durable points **and** break them down by leaf perspectives.
2. Use `ks-detect-structural-update` to decide save, draft-only, or do-not-save.
3. If save is approved, redirect prepared targets to `ks-write-knowledge`.
4. Rebuild indexes with `ks-maintain-indexes`.

For retrieval work, use `ks-what-is-helpful`:

- standard mode for user-facing discovery and explanation
- gateway mode for orchestrator-facing neutral hybrid candidate discovery followed by explicit authority, candidate, background, blocked, polarity, materiality, and blocker classification
- in either mode, load full note bodies only for materially relevant candidates and return the smallest useful result set

For ambiguous work:

- if the user asks to persist and discover at the same time, perform discovery first, then ask before writing unless the write target and status are explicit
- if the user asks for a human-facing artifact, redirect to `orch-create-document`
- if the user asks to summarize raw conversation, extract durable points only and discard raw transcript shape

## Mode Controls

The user can pause or exit keep-summarizing.

Pause commands:

```text
pause keep-summarizing
do not persist knowledge for now
draft only
```

Pause behavior:

- stop writing durable notes
- continue normal work
- optionally keep temporary notes outside durable knowledge only if requested
- resume when the user says `resume keep-summarizing` or explicitly asks to persist knowledge

Exit commands:

```text
stop keep-summarizing
exit keep-summarizing
normal mode
do not persist knowledge for this conversation
```

Exit behavior:

- stop applying keep-summarizing for the current conversation
- do not write notes, indexes, or Git commits through `keep-summarizing`
- continue as a normal agent unless the user reactivates the skill

When pausing or exiting, acknowledge the new mode clearly.

## Note Metadata

Every curated note should start with front matter:

```yaml
---
id: ks-architecture-module-boundaries
title: Module Boundaries
lifecycle_stage: development_design
perspective: development-design/architecture/component-boundary
status: current
source_type: design_doc
summary: Module responsibility boundaries for future architecture and implementation work.
owner: keep-summarizing
created_at: 2026-05-05
updated_at: 2026-05-05
visibility: private
sensitivity: normal
tags:
  - boundaries
  - architecture
source:
  type: curated
  refs: []
evidence: []
embedding:
  include: true
  chunk_strategy: heading
---
```

Use stable headings:

```text
Summary
Current Facts
Constraints / Rules
Evidence Notes
Related Notes
Accepted Open Questions
```

## Lifecycle

Statuses:

- `draft`: proposed knowledge that has not been accepted as durable truth.
- `proposed`: candidate knowledge with a plausible source but not enough authority.
- `confirmed`: accepted knowledge backed by a concrete artifact.
- `implemented`: implemented knowledge backed by source, handoff, deployment, or validation evidence.
- `current`: current authority agents may use by default.
- `superseded`: replaced by newer knowledge.
- `deprecated`: once true, now no longer recommended.
- `rejected`: considered and rejected; must not shape default work.

Rules:

- Uncertain design work starts as `draft`.
- Explicit user decisions or verified source facts may start as `current`.
- Promoted `confirmed`, `implemented`, and promoted `current` notes require front matter evidence when that evidence affects status or retrieval authority.
- Superseded and deprecated notes should link to replacements.
- Superseded, deprecated, and rejected notes are not default authority.
- Reader-facing documents produced through `orch-create-document` are derived outputs until the user accepts them as curated knowledge.

## Conflict Policy

- `merge`: two notes describe the same durable concept and can be combined.
- `replace`: a newer note supersedes an older one. Deprecate the old note and link to the replacement.
- `create-new`: the new point has a distinct perspective, scope, or lifecycle.
- `ask-user`: notes contradict and the source of truth is unclear.

## Waiting For Direction

When the agent returns a plan, draft, open questions, or unresolved choices instead of applying changes, it must clearly state that it is waiting.

Use this pattern:

```text
Waiting for your direction.

Choose one:
1. <concrete action>
2. <concrete action>
3. <concrete action>

Recommended: <option>, because <short reason>.
```

The agent should not assume the user knows whether the next step is to initialize a repo, answer open questions, approve persistence, or request an implementation plan.

## Git Scope

The skill can use normal Git commands without additional permission only inside the selected durable knowledge repo. Explicitly selected legacy roots are migration/read-only compatibility sources and do not extend Git authority to `.work-bundle/orchestration/` or source repositories.

Allowed by default:

```text
status
diff
log
add
commit
branch
tag
restore
```

Protected operations require explicit user approval:

```text
reset --hard
force-push
branch deletion
deleting durable Markdown
```

Never run Git commands in source repositories under keep-summarizing authority. Source repository Git work requires normal agent permissions outside this skill.

## Security

- Default `visibility` is `private`.
- Default `sensitivity` is `normal`.
- Notes marked `confidential` or `secret` are excluded from embedding export by default.
- Reader-facing documents are created through `orch-create-document` and inherit the highest sensitivity of their source notes there.
- Handoffs inherit source sensitivity and are not indexed by default.
- Store redacted structural explanations instead of secrets.

## Indexing

Index curated Markdown only:

- `notes/**.md`
- accepted context packs
- durable decisions and patterns

Do not index raw conversations, one-off debugging notes, temporary handoffs, obsolete drafts, or sensitive notes excluded by `project.yaml`.

Generated files:

```text
indexes/document-registry.jsonl
indexes/chunk-registry.jsonl
indexes/backlink-map.json
indexes/embedding-manifest.json
indexes/knowledge.sqlite
indexes/<vector-sidecar-artifacts when used>
indexes/open-question-registry.jsonl
```

Indexes are disposable and must be reproducible from Markdown. Vector index artifacts and embedding manifests are derived status/output only; they are not canonical knowledge and do not decide authority, truth, conflict, or blockers.

Completion is not valid after a note or open-question write until the relevant index command has been run and any reported issue has been surfaced.

## V4 Boundary Validation

V4 work-bundle validation may inspect project metadata, agent entry, role profiles, runtime rules, and skill registry references. These checks do not expand durable knowledge ownership: notes remain under `.work-bundle/knowledge/`, and orchestration/runtime artifacts remain under `.work-bundle/orchestration/`.
