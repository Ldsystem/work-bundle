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

Prevent completion language from outrunning the evidence available for the exact result being reported.

## Must

- Name the exact claim before selecting evidence.
- Use capable evidence: the check must be able to disprove the claim, not merely inspect an adjacent property.
- Obtain fresh, claim-relevant evidence after the latest material change.
- State only the status that evidence supports, including partial, failed, or blocked status.
- For terminal, review, or archive claims, resolve the source artifact's `Knowledge Base Update` disposition to `completed` or `not-needed`, with supporting evidence.
- Report the command, check, artifact, or observation that supports the claim.

## Must Not

- Do not reuse stale evidence after a relevant change.
- Do not extrapolate from partial evidence to a broader passing, clean, fixed, or complete claim.
- Do not make a terminal or archive claim while required durable knowledge remains unresolved.
- Do not treat absence of a visible error as proof of success.

## Validation

- Match each completion claim to fresh evidence capable of testing it.
- Confirm the reported status does not exceed the tested scope.
- Confirm terminal claims include resolved `Knowledge Base Update` evidence when applicable.

## On Violation

Withdraw or narrow the unsupported claim, run the missing capable check, and report the supported status plus any blocker.
