---
id: spec-YYYYMMDD-001
title: [Concise Title Describing the Specification's Focus]
project: <project-slug>
status: draft
date_created: [YYYY-MM-DD]
last_updated: [Optional: YYYY-MM-DD]
source_knowledge:
  - path: .work-bundle/knowledge/notes/...
    constraint: [task-relevant accepted decision or constraint]
related_handoffs: []
version: [Optional: e.g., 1.0, Date]
tags: [Optional: List of relevant tags or categories, e.g., `infrastructure`, `process`, `design`, `app` etc]
execution_workspace:
  isolation: required|preferred|existing
  profile: default
  cleanup: after_integration|manual
---

The front-matter `source_knowledge` contains accepted authority only, as established by bounded retrieval and Source Context reconciliation. Each accepted entry carries a provenance `path` and the already-reconciled task-relevant `constraint`. Candidate, background, blocked, and superseded knowledge remains classified in Source Context or Open Questions and must not appear in this carried-authority list. Downstream planning allocates deterministic `AUTH-NNN` aliases by list order so executor packets remain traceable without exposing knowledge paths. The compiler resolves each allocated alias to `AUTH-NNN: <carried constraint>` in the task brief and review package.

# Introduction

[A short concise introduction to the specification and the goal it is intended to achieve.]

## 1. Purpose & Scope

[Provide a clear, concise description of the specification's purpose and the scope of its application. State the intended audience and any assumptions.]

## 2. Definitions

[List and define all acronyms, abbreviations, and domain-specific terms used in this specification.]

## 3. Initial Shell

Before any long evidence gathering, create the specification shell with front matter and these required placeholders:

- `Initial User Purpose Evidence`
- `Draft Requirement Breakdown`

`Initial User Purpose Evidence` must be derived only from the current user request and visible supplied artifacts. `Draft Requirement Breakdown` is provisional and must be revised after bounded evidence gathering; it must not be silently replaced.

## 3.1 Project Metadata Preflight

After the initial shell exists and before broad repository evidence gathering, record project metadata preflight for each target source repository that can affect the specification.

Required evidence:

- `.work-bundle/project.yaml` availability and `metadata_version`.
- Source repository `id`, path, Git capability, expected `working_branch`, actual branch, expected `last_commit_id`, actual HEAD commit, branch status, and commit/baseline status when Git-backed.
- Registry locator consistency when the bootstrap-resolved project registry is used.
- CodeGraph support, `.codegraph/` marker presence, index status, synced commit when available, and `no-index` or `not-indexed` fallback when absent.

If metadata is missing, inaccessible, contradictory, stale in a way that affects evidence trust, branch mismatched, or CodeGraph metadata is inconsistent, add a blocking open question before collecting extended repository evidence.

Metadata blockers may block source inspection, impact traversal, planning, or execution trust. They must not block bounded durable-knowledge gateway retrieval when the knowledge base and gateway tooling are accessible; record that retrieval as classification-only until repository trust is restored.

## 4. Source Context

[Record the evidence used before drafting. Include durable knowledge gateway results grouped by `authority`, `candidate`, `background`, and `blocked`, plus current repository evidence with path, role, and relevance. Durable knowledge discovery for specification creation must be neutral and cross-stage: record neutral query anchors, candidate sources or retrieval gaps, and the active retrieval policy as classification/output intent rather than a discovery-stage filter. Only `authority` durable knowledge may shape requirements, constraints, acceptance criteria, or downstream tasks.]

Source Context must include project metadata preflight evidence or a blocking open question that explains why metadata preflight could not establish a trustworthy branch, commit, registry, and CodeGraph baseline.

For WorkBundle project specifications, Source Context must include related active defect registry evidence when the current scope matches active defects. Each included defect records ID, severity, deviation summary, related scope, required resolution, and expected review closure. Exact-current-work conflicts may be specification-owned instead of requiring separate new defect evidence.

When no supporting authority note exists for the user purpose, record the retrieval gap and analyze the purpose from user input and repository evidence. Use Design Interrogation only for unresolved design intent that cannot be answered from current evidence.

When material non-authority evidence appears, record agent-owned polarity and materiality classification as supporting, opposing, constraining, unresolved/open-question, obsolete/replaced, or irrelevant-with-reason evidence. Candidate, background, blocked, opposing, stale, draft, or proposed evidence must remain non-shaping unless resolved by the user or promoted by accepted authority. Blocking status depends on unresolved impact to requirements, architecture, workflow, policy, API, persistence, validation, execution behavior, or user-purpose safety.

### 4.1 Design Interrogation

[Required when user intent is under-specified, repository evidence conflicts, or no supporting note exists and the purpose cannot be resolved from current evidence.]

- **Trigger**: no-supporting-note|under-specified-purpose|repository-evidence-conflict|none
- **Question**: Ask one design question at a time.
- **Recommended answer**: Provide the advised answer and rationale.
- **User resolution**: Record accepted answer or unresolved.
- **Evidence conclusion**: Record any accepted conclusion as specification evidence.

### 4.2 Impact Decisions

Before verification, record one bounded current-state evidence basis covering the requested surface, material upstream dependencies or producers, downstream consumers, validation/test surfaces, and relevant dirty work.

```yaml
impact_decisions:
  basis:
    requested_surface: [path-or-symbol]
    current_state_sources: [evidence-ref]
    dirty_work: clean | related | unrelated
    stopping_reason: string
  relations:
    - id: IMP-001
      relation: string
      direction: upstream | downstream | validation | cross-cutting
      materiality: string
      disposition: accepted | excluded | blocking
      evidence: [evidence-ref]
      projects_to: [REQ-001, AC-001]
      reason: string
  none_relevant:
    value: false
    searched_boundary: string
    reason: string
```

Treat a relation as material only when its disposition could change a requirement, constraint, acceptance criterion, user-observable or contractual outcome, architectural boundary, measurable quality target, validation target, or declared boundary. Every material relation has exactly one `accepted | excluded | blocking` disposition. `projects_to` is required for accepted relations and must name stable requirements, constraints, interfaces, acceptance criteria, or validation targets. Excluded relations require evidence and a concise reason; "the user did not mention it" is not sufficient. Blocking relations create blocking Open Questions and keep the quality gate blocked.

Use `none_relevant` only after a bounded scan finds no material relation and records its searched boundary, reason, and `stopping_reason`. Stop when further exploration could change none of those surfaces and record the reason. Escalate to targeted Git history, prior work artifacts, execution evidence, or durable knowledge only for contradictory current-state evidence, unresolved ownership, material regression/causality, or a suspected governing legacy decision; do not require full-history archaeology or broad knowledge retrieval by default.

### 4.3 Excellence Applicability

Within Design Interrogation, run one compact pass that selects product-excellence dimensions from the task evidence and change shape rather than a universal checklist. Surface an option only when accepting or rejecting it could change a requirement, constraint, acceptance criterion, user-observable or contractual outcome, architectural boundary, measurable quality target, validation target, or declared boundary. Record exactly one result:

```yaml
excellence_applicability:
  result: no_material_opportunity | material_opportunities
  reason: string
  proposals:
    - id: EXC-001
      dimensions: [usability, architecture]
      user_value: string
      evidence: [evidence-ref]
      cost: low | medium | high
      risk: string
      recommendation: string
      disposition: accepted | rejected | deferred | not_material
      projects_to: [REQ-001, AC-001]
```

Use `no_material_opportunity` only with a non-empty evidence-backed reason and an empty proposal list. `material_opportunities` requires one or more proposals. Each proposal explains user value, evidence, cost, risk, recommendation, and disposition in plain language; unanswered proposals become deferred. Only accepted proposals may project through stable `projects_to` IDs into authoritative requirements, constraints, interfaces, acceptance criteria, or validation targets. Rejected, deferred, and not-material proposals remain traceable but are excluded from planning, executor briefs, and acceptance obligations.

Do not add a lifecycle stage, force a recommendation, or use a universal product-quality checklist. Stop after one compact pass when further exploration could change none of those surfaces, record the reason, and ensure every surfaced proposal has a disposition. A related-but-non-material idea is omitted or recorded `not_material`; it is not promoted merely because it is adjacent. Optional proposals do not block verification unless accepted without complete authoritative projection or they expose an unresolved safety or authority conflict governed by existing open-question rules. Agent judgment owns opportunity materiality and recommendation quality; structural validation does not.

## 5. Requirements, Constraints & Guidelines

[Explicitly list all requirements, constraints, rules, and guidelines. Use bullet points or tables for clarity.]

- **REQ-001**: Requirement 1
- **SEC-001**: Security Requirement 1
- **[3 LETTERS]-001**: Other Requirement 1
- **CON-001**: Constraint 1
- **GUD-001**: Guideline 1
- **PAT-001**: Pattern to follow 1
- **REQ-SHELL-001**: Create the specification shell before extended evidence gathering, and keep `Initial User Purpose Evidence` and `Draft Requirement Breakdown` visible in the generated artifact.
- **REQ-SHELL-002**: Derive initial user-purpose evidence only from the current user request and visible supplied artifacts.
- **REQ-SHELL-003**: Revise draft requirements after bounded evidence gathering instead of silently replacing them.
- **REQ-META-001**: Run project metadata preflight after shell creation and before broad repository evidence gathering; block on missing metadata, branch mismatch, stale baseline affecting evidence trust, registry contradiction, or inconsistent CodeGraph state.
- **REQ-KG-001**: Run bounded durable-knowledge gateway retrieval for material new findings or requests even when repository metadata blockers prevent source inspection, provided the gateway is accessible.
- **REQ-DEF-001**: For WorkBundle project scopes, inspect related active defect registry evidence and carry matching defects into Source Context or Open Questions with review closure expectations.

## 6. Interfaces & Data Contracts

[Describe the interfaces, APIs, data contracts, or integration points. Use tables or code blocks for schemas and examples.]

## 7. Acceptance Criteria

[Define clear, testable acceptance criteria for each requirement using Given-When-Then format where appropriate.]

- **AC-001**: Given [context], When [action], Then [expected outcome]
- **AC-002**: The system shall [specific behavior] when [condition]
- **AC-003**: [Additional acceptance criteria as needed]
- **AC-SHELL-001**: Given a new specification request, when the artifact is created, then the shell exists first with front matter plus `Initial User Purpose Evidence` and `Draft Requirement Breakdown`.
- **AC-SHELL-002**: Given bounded evidence gathering completes, when the draft is updated, then the original draft requirement breakdown is revised rather than erased without trace.

## 8. Test Automation Strategy

[Define the testing approach, frameworks, and automation requirements.]

- **Test Levels**: Unit, Integration, End-to-End
- **Frameworks**: MSTest, FluentAssertions, Moq (for .NET applications)
- **Test Data Management**: [approach for test data creation and cleanup]
- **CI/CD Integration**: [automated testing in GitHub Actions pipelines]
- **Coverage Requirements**: [minimum code coverage thresholds]
- **Performance Testing**: [approach for load and performance testing]

## 9. Rationale & Context

[Explain the reasoning behind the requirements, constraints, and guidelines. Provide context for design decisions.]

## 10. Dependencies & External Integrations

[Define the external systems, services, and architectural dependencies required for this specification. Focus on **what** is needed rather than **how** it's implemented. Avoid specific package or library versions unless they represent architectural constraints.]

### External Systems
- **EXT-001**: [External system name] - [Purpose and integration type]

### Third-Party Services
- **SVC-001**: [Service name] - [Required capabilities and SLA requirements]

### Infrastructure Dependencies
- **INF-001**: [Infrastructure component] - [Requirements and constraints]

### Data Dependencies
- **DAT-001**: [External data source] - [Format, frequency, and access requirements]

### Technology Platform Dependencies
- **PLT-001**: [Platform/runtime requirement] - [Version constraints and rationale]

### Compliance Dependencies
- **COM-001**: [Regulatory or compliance requirement] - [Impact on implementation]

**Note**: This section should focus on architectural and business dependencies, not specific package implementations. For example, specify "OAuth 2.0 authentication library" rather than "Microsoft.AspNetCore.Authentication.JwtBearer v6.0.1".

### 10.1 Execution Workspace Policy

Choose policy only; specification creation does not provision a worktree.

- `existing` for small or manual work that can safely use the accepted checkout.
- `preferred` for multi-task autonomous work that benefits from isolation.
- `required` for risky large features or migrations.
- Name the hydration profile and cleanup policy. Planning carries them into task and executor context; execution owns selection, preparation, hydration, and provenance.

## 11. Open Questions

[List unresolved decisions, uncertainty, conflicts, and material non-authority evidence that affects requirements, architecture, workflow, API, persistence, validation, execution behavior, or user purpose.]

Every open question must include:

| Field | Required |
| --- | --- |
| ID | yes |
| Question or uncertainty | yes |
| Related scope | yes |
| Source | yes |
| Blocking | yes |
| Required resolution | yes |
| Advised options | yes |

Candidate, background, blocked, draft, proposed, stale, opposing, or otherwise non-authority durable knowledge must not become requirement text. When material, record it as rationale, traceability, conflict evidence, or open-question input. Related active defects that affect the specification scope are blocking open questions unless the user or accepted evidence resolves them. Non-authority or opposing evidence is blocking only when the unresolved decision affects implementation or review safety.

## 12. Knowledge Base Update

[Record whether this specification is expected to produce durable project knowledge without instructing agents to write durable notes directly.]

- **Disposition**: required|not-needed|blocked
- **Expected durable conclusions**:
  - [List candidate durable conclusions or `None for this specification scope.`]
- **Evidence sources**:
  - [List expected implementation, validation, handoff, or source evidence.]
- **Responsible follow-up**: [Record the approved follow-up path or `none`.]
- **Blocks review/archive**: yes|no
- **Rationale**: [Explain why the disposition applies.]

Set disposition to `required` when accepted Design Interrogation conclusions establish new durable orchestration policy, workflow design, or reusable process behavior.

Do not instruct specification authors or executors to write durable knowledge directly. Review must settle carried unsettled evidence through the approved `ks-*` follow-up path or record an evidence-backed no-write disposition before archive.

## 13. Examples & Edge Cases

    ```code
    // Code snippet or data example demonstrating the correct application of the guidelines, including edge cases
    ```

## 14. Validation Criteria

[List the criteria or tests that must be satisfied for compliance with this specification.]

- The generated specification includes front matter and a shell created before extended evidence gathering.
- The generated specification includes `Initial User Purpose Evidence` sourced from the current user request and visible supplied artifacts only.
- The generated specification includes `Draft Requirement Breakdown` and revises it after bounded evidence gathering.
- The specification remains self-contained and does not require broad repository exploration before the shell exists.
- The source context records neutral cross-stage retrieval anchors or a retrieval gap, and any named retrieval policy is used only for classification/output grouping.
- The specification carries accepted authority context forward so downstream planning and execution do not need to read `.work-bundle/knowledge/`.
- The specification records project metadata preflight evidence including `working_branch`, `last_commit_id`, branch status, baseline status, and CodeGraph no-index fallback when applicable.
- WorkBundle project specifications record related active defects and expected review closure when applicable.
- Material non-authority or opposing evidence is visible without shaping requirements unless resolved by user decision or accepted authority.

## 15. Quality Gate

Quality gate: verified|blocked

Checked:

- user purpose coverage
- durable knowledge classification
- current repository contract coverage
- affected-file coverage
- assumptions and alternatives
- open questions

Semantic convergence lenses:

- user-purpose coverage
- authority and evidence support
- requirement, constraint, and open-question consistency
- impact radius
- impact-decision view, including disposition and `projects_to` agreement
- Knowledge Base Update disposition
- execution-workspace policy when applicable

```yaml
semantic_loop:
  result: converged | blocked
  rounds: 2
  repaired:
    - missing or contradictory item
```

Use `dev-semantic-convergence`: repair only discovered defects and view again. An unchanged view converges; a blocking question keeps the quality gate `blocked`.

## 16. Related Specifications / Further Reading

[Link to related spec 1]
[Link to relevant external documentation]
