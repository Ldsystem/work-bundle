---
id: verification-evidence-before-claim
applies_when:
  - an agent is about to state that code, a task, a workflow, a review, an archive, or a knowledge update is complete, fixed, passing, clean, validated, or resolved
enforcement: must
load: always
requires: []
---

# Verification Evidence Before Claim

## Purpose

Keep completion claims evidence-bound.

## Must

- Name the exact claim before selecting evidence.
- Use capable evidence that can disprove the claim.
- Obtain fresh, claim-relevant evidence after the latest material change.
- For a deterministic accepted identity, verify strongly once and persist the compact observation. Later lifecycle consumers reuse that current harness observation while its identity and freshness hold; progression alone does not rerun it.
- State only the status that evidence supports, including partial, failed, or blocked status.
- For terminal, review, or archive claims, resolve `Knowledge Base Update` to `completed` or `not-needed` with evidence.
- Report the command, check, artifact, or observation that supports the claim.

## Must Not

- Do not reuse stale evidence after a relevant change.
- Do not replay executor assertions, transient acceptance evidence, or historical handoff chains in place of a current harness observation.
- Do not turn partial evidence into a broader passing, clean, fixed, or complete claim.
- Do not make a terminal or archive claim while required durable knowledge remains unresolved.
- Do not treat absence of a visible error as proof of success.

## Validation

- Match each completion claim to capable, current evidence.
- Confirm the reported status does not exceed the tested scope.
- Confirm applicable terminal claims include resolved `Knowledge Base Update` evidence.

## On Violation

Withdraw or narrow the claim, run the missing capable check, and report only the supported status and blockers.
