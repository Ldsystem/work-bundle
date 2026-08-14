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
5. Inspect bounded current repository evidence, including upstream/downstream and validation/test impact-radius evidence. For WorkBundle scope, include related active violations by ID, severity, deviation, scope, required resolution, and expected review closure. Exact-current-work conflicts may remain specification-owned.
6. Ask Design Interrogation questions only for unresolved intent that changes requirements, architecture, workflow, API, persistence, validation, execution safety, or user purpose. Evidence class alone does not make an open question blocking.
7. Normalize stable IDs, requirements, constraints, interfaces, acceptance criteria, decisions, open questions, and Knowledge Base Update disposition.
8. Decide execution-workspace policy without provisioning it:

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
