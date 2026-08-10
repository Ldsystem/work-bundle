---
id: wb-credential-use
applies_when:
  - a user explicitly requests an operation that requires a named workspace credential ID
  - a script/index.yaml entry declares one or more credential IDs for a requested utility
  - an orchestration plan or task declares a credential ID, target, and requested operation
enforcement: must
load: conditional
requires:
  - rule-work-bundle-security-exclusion
---

# Credential Use

## Purpose

Require fail-closed, non-visible, locally bounded credential use without making credential availability an authorization grant.

## Must

- Resolve `workspace_root` and the requested credential ID without opening or ingesting credential-store values.
- Invoke `wb-credential-use` locally with credential ID, target, requested operation, purpose, and current-task authorization source only.
- Compare requested operation against the entry maximum and independent task/operation-policy authority before secret access.
- Require an exact target and purpose for high severity; require explicit exact-operation authority for critical or read-write use.
- Use only the least-exposure injection mechanisms allowed by `references/wb-credential-use-contract.yaml` and the bounded consumer.
- Select the declared form-specific adapter before value access and block encrypted SSH-key passphrases, unsupported external providers, and adapter mismatches.
- Return only redacted credential-ID audit evidence and stable redacted failure codes.
- Give delegated agents only credential ID, target, operation, and local workflow instructions; each delegate resolves the credential locally.

## Must Not

- Do not open, print, grep, summarize, copy, delegate, or directly ingest `credentials/credentials.yaml`.
- Do not place credential values in agent-visible, tracked, indexed, durable, process-argument, shell-trace, clipboard, or persistent-environment surfaces.
- Do not use a read-only credential for a write operation or treat read-write capability as mutation authority.
- Do not fall back to a visible prompt or command-line secret argument when safe injection is unavailable.
- Do not return raw child stdout/stderr or use generic exact-string redaction as containment for transformed output.

## Validation

- Confirm task authority, target, severity, operation, store protection, transport, and injection gates pass before secret access.
- Confirm public output contains no value-bearing field and only redacted credential-ID evidence.
- Use synthetic canaries and verify zero visible or tracked occurrences.
- Confirm delegated execution did not transmit credential material between agents.

## On Violation

Stop before secret access or consumer invocation, emit only a stable redacted failure code, and require a safe local workflow or explicit task-authority repair.
