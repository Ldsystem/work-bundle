---
name: orch-create-specification
description: 'Create or repair an AI-ready WorkBundle implementation specification when requirements, architecture, workflow, or durable decisions must be settled before planning.'
---

# orch-create-specification

## Scope

Create the smallest authoritative specification under `.work-bundle/orchestration/spec/active/`. Do not implement source changes or provision execution workspaces.

## Workflow

1. Create the specification shell before extended evidence gathering. Preserve `Initial User Purpose Evidence` and a provisional `Draft Requirement Breakdown` from the request and supplied artifacts.
2. Run project metadata preflight. Record each target repository, expected and actual branch/commit, cleanliness trust, and CodeGraph index or `no-index` state. Repository blockers limit source inspection but do not stop bounded knowledge-gateway classification when it remains accessible.
3. Through `ks-what-is-helpful`, discover with polarity-neutral and stage/perspective/status-neutral query anchors. `implementation_spec` is classification and output-grouping intent, not a discovery-stage lifecycle filter.
4. Classify results as authority, candidate, background, or blocked. Only authority shapes requirements and only accepted authority enters front-matter `source_knowledge` as `path` plus the already-reconciled `constraint`; keep candidate, background, blocked, superseded, supporting, opposing, constraining, unresolved/open-question, obsolete, and irrelevant-with-reason evidence in Source Context when material. Downstream planning allocates `AUTH-NNN` aliases from the accepted list so execution does not require `.work-bundle/knowledge/` reads or expose knowledge paths.
5. Build one bounded current-state impact basis from the requested surface, material upstream dependencies or producers, downstream consumers, validation/test surfaces, and relevant dirty work. Treat a relation as material only when its disposition could change a requirement, constraint, acceptance criterion, user-observable or contractual outcome, architectural boundary, measurable quality target, validation target, or declared boundary. Record `impact_decisions` and give each material relation exactly one disposition: `accepted | excluded | blocking`. An accepted relation must use `projects_to` to name stable requirement, constraint, interface, acceptance-criterion, or validation-target IDs. An excluded relation requires evidence and a reason stronger than user omission. A blocking relation creates a blocking open question. When no material relation exists, record `none_relevant` with the searched boundary, reason, and `stopping_reason`.
6. Stop when further exploration could change none of those surfaces and record the reason. Escalate to targeted Git history, prior work artifacts, execution evidence, or durable knowledge only when current-state evidence is contradictory, ownership is unresolved, regression or causality is material, or a governing legacy decision is suspected. Do not require full-history archaeology or broad knowledge retrieval by default. For WorkBundle scope, include related active defects by ID, severity, deviation, scope, required resolution, and expected review closure. Exact-current-work conflicts may remain specification-owned.
7. Within Design Interrogation, run one compact, evidence-routed product-excellence applicability pass. Record exactly one `excellence_applicability` result: `no_material_opportunity` with a non-empty reason, or `material_opportunities` with one or more proposals. Select dimensions from the task evidence and change shape rather than a universal checklist. Surface an option only when accepting or rejecting it could change a requirement, constraint, acceptance criterion, user-observable or contractual outcome, architectural boundary, measurable quality target, validation target, or declared boundary. Each proposal records user value, evidence, cost, risk, recommendation, and one disposition: `accepted | rejected | deferred | not_material`; unanswered proposals become deferred. Only accepted proposals may project through stable `projects_to` IDs into authoritative requirements, constraints, interfaces, acceptance criteria, or validation targets. Keep all other proposals traceable but excluded from planning, executor briefs, and acceptance obligations. Stop after one compact pass when further exploration could change none of those surfaces, record the reason, and ensure every surfaced proposal has a disposition. Optional proposals do not block unless accepted without complete projection or they expose an unresolved safety or authority conflict governed by existing open-question rules.
8. Ask Design Interrogation questions only for unresolved intent that changes requirements, architecture, workflow, API, persistence, validation, execution safety, or user purpose. Evidence class alone does not make an open question blocking.
9. Normalize stable IDs, requirements, constraints, interfaces, acceptance criteria, decisions, open questions, and Knowledge Base Update disposition.
10. Decide execution-workspace policy without provisioning it:

```yaml
execution_workspace:
  isolation: required | preferred | existing
  profile: default | <named-profile>
  cleanup: after_integration | manual
```

Use `existing` for small/manual work, `preferred` for autonomous multi-task work, and `required` for risky large features or migrations unless evidence supports another choice.

## Semantic convergence

Use `dev-semantic-convergence` with these lenses:

- user-purpose coverage;
- authority and evidence support;
- requirement, constraint, and open-question consistency;
- impact radius;
- impact-decision view, including disposition and `projects_to` agreement;
- excellence-applicability view, including proposal disposition, accepted projection, and non-authoritative exclusion agreement;
- Knowledge Base Update disposition;
- execution-workspace policy when applicable.

Repair only discovered defects and view again. Record:

```yaml
semantic_loop:
  result: converged | blocked
  rounds: 2
  repaired:
    - missing API constraint
```

Do not preserve verbose per-round transcripts.

The caller materializes the impact-decision view. Use `dev-semantic-convergence` to compare and repair it, but keep repository traversal out of `dev-semantic-convergence`.

## Completion gate

The body must contain `Quality gate: verified|blocked`. Planning may proceed only with `verified`, a converged semantic loop, resolved blocking questions, stable IDs, and explicit Knowledge Base Update disposition. Set that disposition to `required` when the work establishes durable reusable decisions; specification authors do not write durable knowledge directly.

## Runtime Rules

- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-knowledge-gateway`: `rules/orchestration/orch-knowledge-gateway.md`
- `orch-open-questions`: `rules/orchestration/orch-open-questions.md`
- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rules above when their indexed conditions apply.

## Boundary

Follow `orch-orchestration-boundary`.
