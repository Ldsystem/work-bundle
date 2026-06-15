---
name: orch-review-plan
description: 'Review completed implementation and archive or create repair specifications.'
---

# orch-review-plan

## Scope

Review completed implementation and archive or create repair specifications.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/orchestration/review-plan.md` for directive-specific behavior.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-knowledge-gateway`: `rules/orchestration/orch-knowledge-gateway.md`
- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`
- `orch-review-completion`: `rules/orchestration/orch-review-completion.md`

## Rule Loading (mandatory)

Before directive-specific work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive orchestration work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or directive summaries as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress orchestration task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Review Delegation

Determine whether validated implementation and review evidence is a structural update. For mixed implementation, validation, handoff, and review evidence, delegate knowledge maintenance to `ks-extract-valuable-points`; use `ks-breakdown-design` only for design-file-only evidence.

Provide the reviewed specification, plan, relevant handoffs, validation evidence, changed project files or symbols, expected durable conclusions, target project identity, and current disposition to the delegated owner.

Disposition and archive gates: follow `orch-review-completion` (`rules/orchestration/orch-review-completion.md`).

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`). You may invoke, schedule, or hand off to an approved `ks-*` owner and consume its result per that rule.

> **Deprecation:** The role-context subsystem is deprecated; see spec §0.9 in `spec-process-orch-skill-rule-boundary-optimization-20260611`. Do not invoke it from orch skills.
