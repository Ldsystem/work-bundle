---
id: ks-persistence-gate
applies_when:
  - an agent prepares a durable knowledge note, context pack, or open-question write
enforcement: must
load: conditional
requires: []
---

# Ks Persistence Gate

## Purpose

- Separate agent-owned persistence decisions from the declared record transaction's necessary mechanical checks.
- Keep unresolved meaning or authority outside canonical mutation.

## Must

- Before requesting a record effect, the agent decides structural value, relevance, authority, conflict disposition, sensitivity meaning, lifecycle intent, and evidence sufficiency. Apply `ks-structural-value`, `ks-perspective-routing`, `ks-sensitivity-filter`, and `ks-open-question-policy` where their conditions apply.
- Resolve the managed knowledge root and persistence authorization through `ks-knowledge-boundary` and the selected skill. An explicitly approved workflow follow-up already supplies write intent within its scope; do not require redundant permission at the mutation boundary.
- For notes and accepted open questions, supply the exact single-record request to `scripts/ks.py mutate-knowledge`. The command validates request shape, identity/path/perspective, current state, transition, expected digest, collisions, declared evidence/links, and staged serialization before atomic canonical replacement.
- Keep only effect-driving content, front matter, target path, declared effect, and expected digest in the request. Keep internal reasoning outside it.
- Context packs retain their specialized procedure under `ks-context-pack-policy`; the record transaction does not add a context-pack kind.

## Must Not

- Do not guess a missing project root, directive, lifecycle stage, status, source type, evidence set, or target path.
- Do not bypass duplicate or conflict review.
- Do not directly patch canonical note or open-question files to bypass a rejected transaction.
- Do not continue to a write while an agent-owned decision is unresolved or a necessary command check fails.
- Do not replace the required failure response with silent refusal or partial persistence.

## Validation

- Confirm the responsible agent settled meaning, authority, evidence, and intent before requesting the effect.
- Confirm sensitivity review is handled through `ks-sensitivity-filter` and structural-value review is handled through `ks-structural-value` instead of restating those full lists here.
- Confirm the command returned the declared canonical effect and truthful projection status; structural success is not a semantic verdict.
- Repair a mechanically invalid request from known authorized inputs. Return `Waiting for your direction` only when a missing decision or unresolved authority needs user input, with the concrete next options.

## On Violation

- Stop the affected mutation and report the failed semantic precondition or mechanical condition. Correct known request data through the command; ask only for the missing decision that prevents safe continuation.
