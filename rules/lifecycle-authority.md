---
id: rule-work-bundle-lifecycle-authority
applies_when:
  - v4 work-bundle operation requires lifecycle-authority
enforcement: must
load: conditional
requires: []
---

# Lifecycle Authority

## Purpose

Keep accepted execution authority compact and monotonic so later lifecycle consumers rely on the accepted result instead of replaying the evidence that originally established it.

## Must

- Follow current source authority and exact execution bindings.
- Enforce acceptance once: strongly validate the bound task result, required review, ownership, repository identity, and harness observations before materializing one compact accepted result.
- Bind the compact accepted result to plan, task, source scope, subagent ownership, validation, review, commit, and tree identities.
- Make dependency release, phase/plan progression, finalization, resume, and archive consume the compact accepted result plus any current harness observation required by freshness policy.
- Invalidate acceptance only when a bound authority, source, scope, ownership, validation, review, commit/tree, or freshness identity materially changes.
- Keep runtime files compact.

## Must Not

- Do not generate `.mdc` files.
- Do not include raw logs or secrets.
- Do not replay transient acceptance evidence or historical handoff chains after the compact accepted result exists.
- Do not make status-only lifecycle progression or append-only evidence records create new plan authority, repeat acceptance, or rerun an otherwise current terminal validation.

## Validation

- Required fields exist and the accepted result is bound to the current source and execution identities.
- Downstream consumers resolve the accepted result directly and reject stale or mismatched authority without reconstructing history.
- Scope is WorkBundle.

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
