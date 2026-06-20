---
id: orch-open-questions
applies_when:
  - a specification is created or repaired
  - an implementation plan is created from a specification
enforcement: must
load: conditional
requires: []
---

# Orchestration Open Questions Gate

## Purpose

Expose uncertainty explicitly in specifications and block planning while blocking open questions remain unresolved. Open questions are not facts and must not silently become requirements or executable tasks.

## Must

- Inspect relevant knowledge notes and open-question watchpoints through the approved knowledge gateway when durable knowledge affects specification scope.
- Include an `Open Questions` section in every specification.
- When relevant uncertainty exists, list each item with ID, question or uncertainty, related scope, source, blocking yes/no, required resolution, and advised options.
- Treat material draft, proposed, conflicting, stale, missing-evidence, candidate, background, or blocked knowledge as a blocking open question when it affects requirements, architecture, workflow, API, persistence, validation, execution behavior, or conflict with user purpose.
- Treat non-material unsettled knowledge as out of `create-specification` resolution scope; it may remain source context or be omitted, but it must not block planning.
- When no relevant uncertainty exists, state `None for this specification scope.` in the Open Questions section.
- Inspect the source specification `Open Questions` section first before creating any implementation plan.
- Refuse planning when unresolved open questions remain and return an actionable table with ID, question or uncertainty, blocking status, and required resolution.
- Require explicit user resolution and a revised specification before planning resumes after a refusal.

## Must Not

- Treat draft, proposed, conflicting, stale, or missing-evidence notes as current authority.
- Treat candidate, background, blocked, draft, proposed, conflicting, stale, or missing-evidence notes as requirements or executable tasks without explicit resolution or accepted authority.
- Require user resolution for non-material unsettled notes during `create-specification`.
- Bury blocking uncertainty inside assumptions or requirement prose.
- Omit relevant open questions from a specification.
- Infer answers silently during planning.
- Choose an unresolved alternative to continue planning.
- Downgrade blocking questions to continue planning.
- Create partial plans for unresolved scope.
- Convert unresolved uncertainty into requirements, constraints, or executable tasks.

## Validation

- Confirm the specification includes an Open Questions section with ID, source, scope, blocking classification, required resolution, and advised options for each listed uncertainty, or an explicit none statement.
- Confirm planning either cites no unresolved questions or returns the required refusal table before any plan artifact is written.
- Confirm no plan task depends on silently inferred answers to listed open questions.

## On Violation

Stop specification or planning work, surface the unresolved uncertainty in the Open Questions section or refusal table, and require explicit resolution plus specification repair before planning or execution continues.
