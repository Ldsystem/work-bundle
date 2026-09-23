---
id: wb-truth-basis-evidence
applies_when:
  - an agent begins source, repository, knowledge, or workflow investigation for WorkBundle-guided work
  - an agent plans, debugs, reviews, repairs, refactors, or implements a WorkBundle-guided change
enforcement: must
load: conditional
requires: []
---

# Truth Basis and Bounded Evidence

## Purpose

Keep one evidence-led decision basis from the first substantive probe through a material change. User purpose and accepted decisions govern; the current implementation describes what exists.

## Must

- Discover the applicable rule indexes and this rule before the first substantive source, repository, knowledge, or workflow probe. Minimal bootstrap needed to locate the workspace, metadata, and indexes may precede the probe.
- Establish or consume one Truth Basis with purpose, as-is evidence, accepted decision authority, expected delta, and conflict status. A fresh investigator may start with provisional as-is evidence and fill it from bounded observations; resolve material conflicts before mutation.
- If an accepted task carries a compiled Truth Basis, consume that authority and investigate only the delegated implementation question. Do not repeat controller knowledge retrieval or reconstruct historical lineage.
- Treat implementation, tests, documentation, and workspace state as evidence, not correctness authority. Reconcile observations with user purpose and accepted decisions.
- Trace only relations that can change ownership, accepted scope, user-visible or contractual behavior, architectural boundaries, validation, or safety. Escalate to targeted knowledge, orchestration lineage, or Git history only when current evidence is contradictory or insufficient for such a decision.
- Repair a demonstrated defect at its first owning layer within authorized scope. Stop exploration when more evidence cannot change the accepted outcome or validation target; state the stopping reason when continuation or review needs it.

## Must Not

- Do not infer requirements from as-is behavior, tests, indexes, receipts, or supporting artifacts alone.
- Do not require a fully populated Truth Basis before the observations that establish its as-is field, or use provisional evidence to authorize material mutation.
- Do not add repeated retrieval, evidence ceremony, or a post-write semantic gate to compensate for shorter entry instructions.
- Do not read or expose credential-store contents, or use another task's source changes as mutation authority.

## Validation

- Confirm index discovery preceded the first substantive probe and the five Truth Basis fields are resolved before material change.
- Confirm the current evidence was assessed against accepted authority, material conflicts were routed, and any historical expansion had a decision-changing reason.
- Confirm the owning layer, bounded validation target, and exploration stop are visible in the task record when material.

## On Violation

Stop the affected probe or mutation, load the missing applicable rule or resolve the material authority conflict, then continue from the bounded question.
