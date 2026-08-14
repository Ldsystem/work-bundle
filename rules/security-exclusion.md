---
id: rule-work-bundle-security-exclusion
applies_when:
  - a task, script index entry, plan, or handoff identifies a credential requirement
  - initialization, doctor, migration, discovery, indexing, or validation touches credential-store structure or redacted credential-use evidence
  - an operation could expose credential material through agent-visible or tracked surfaces
enforcement: must
load: conditional
requires: []
---

# Credential Security Exclusion

## Purpose

Prevent credential material from entering agent-visible, tracked, indexed, delegated, or durable WorkBundle surfaces.

## Must

- Permit `$workspace_root/credentials/credentials.yaml` in both single- and multi-repository modes as a protected local-only store and the only permitted file in `credentials/`.
- Enforce directory mode `0700` and file mode `0600` where POSIX permissions apply; otherwise require an explicit equivalent protection or blocking diagnostic.
- Keep `credentials/` ignored by Git and excluded from knowledge, orchestration content, registries, metadata content, indexes, CodeGraph, archives, caches, and backups.
- Pass only credential ID, redacted target, requested operation, and authorization context to `wb-credential-use`; let its bounded local helper own value access and injection.
- Prefer credential references and least-exposure consumer mechanisms; fail closed before value access when authorization, schema, target, severity, operation, permissions, transport, or injection checks fail.
- Suppress raw child output and expose only the closed adapter-result contract; exact-string replacement is not sufficient containment for transformed or encoded output.
- Use synthetic canaries only for tests and require zero occurrence across visible outputs and Git/index artifacts.

## Must Not

- Do not open, print, grep, summarize, directly ingest, or copy credential-store content.
- Do not place credentials in chat, prompts, subagent messages, tool arguments/results, command lines, process listings, terminal output, logs, exceptions, screenshots, clipboard, handoffs, specs, plans, indexes, or fixtures.
- Do not pass secrets as command-line arguments, enable shell tracing, interpolate them into command text, persist them in environment variables, or relay them as data over a network.
- Do not infer mutation authority from `operation: read-write`; task scope and operation policy remain required.
- Do not present one generic environment variable as support for multipart credentials or consumers that require another adapter.

## Validation

- In both workspace modes, verify credential store shape and permissions without returning value-bearing fields.
- Verify Git ignore behavior and exclusion from all generic discovery and index surfaces.
- Verify `read-only` rejects write use and critical or read-write use requires exact current-task authority.
- Verify all public evidence is credential-ID-only and redacted and synthetic canary leakage count is zero.

## On Violation

Stop before credential-value access or consumer invocation, return only a stable redacted failure code, and repair the structural or authorization gate without exposing credential material.
