---
id: ks-sensitivity-filter
applies_when:
  - source content is inspected or written
enforcement: must
load: conditional
requires: []
---

# Ks Sensitivity Filter

## Purpose

- Define the authoritative sensitivity exclusion filter for keep-summarizing inspection and persistence work.
- Ensure durable knowledge keeps reusable structure while excluding secrets, private data, raw transcripts, and temporary output.

## Must

- Screen source content and write targets against this exclusion list before any durable write:
  - credentials
  - tokens
  - secrets
  - private keys
  - personal data
  - raw chat transcripts
  - raw chat logs
  - temporary command output
  - raw implementation logs
  - one-off debugging details
- Replace sensitive material with a redacted structural explanation when the durable rule or pattern still matters.
- Treat this rule as the authoritative sensitivity list for keep-summarizing persistence decisions.

## Must Not

- Do not persist excluded material into notes, open questions, context packs, or indexes.
- Do not quote raw transcript content as durable knowledge.
- Do not store secrets or personal data in place of a reusable structural conclusion.
- Do not treat temporary output or one-off debugging detail as durable evidence.

## Validation

- Confirm the inspected content was checked against every exclusion in this rule before any write.
- Confirm the persisted content contains only the reusable conclusion, not the raw sensitive source.
- If it is unclear whether content includes secrets, personal data, or temporary raw output, stop and ask before writing.

## On Violation

- Stop the write or inspection-to-write transition.
- Report the excluded content type, remove or redact it, and resume only after the durable output is sensitivity-safe.
