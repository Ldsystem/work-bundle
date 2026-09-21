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

Keep completion claims evidence-bound without turning mechanical closure checks into product verdicts.

## Must

- Name the exact claim and classify it as a semantic product judgment or a mechanical/workflow fact.
- Obtain fresh, claim-relevant evidence after the latest material change, using the lightest capable evidence that can disprove the claim.
- Product claims require agent assessment against user purpose and accepted obligations; tests, schemas, scripts, indexes, and receipts are supporting observations.
- Mechanical claims verify closure facts only. Resolve `Knowledge Base Update` for terminal claims; its disposition does not create or reverse a product decision.
- State only the status that evidence supports and name its supporting observation.

## Must Not

- Do not reuse stale evidence or substitute executor assertions or historical handoff replay.
- Do not turn partial evidence into a broader passing, fixed, or complete claim.
- Do not let a deterministic helper, post-write check, supporting-state defect, or ceremony manufacture or veto semantic correctness when the product remains reviewable.
- Do not make a terminal claim while required durable knowledge remains unresolved.

## Validation

- Match each claim to current evidence and its semantic or mechanical owner.
- Confirm agent ownership of product claims, bounded mechanical checks, supported status, and resolved terminal `Knowledge Base Update` evidence.

## On Violation

Withdraw or narrow the claim, run the missing capable check, and report only supported status and blockers.
