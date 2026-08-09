---
name: wb-credential-use
description: Use a named WorkBundle workspace credential for an explicitly authorized operation without exposing its value. Invoke when a task, workspace utility, or orchestration artifact names a credential ID, exact target, purpose, and read-only or read-write operation.
---

# WorkBundle Credential Use

Resolve `workspace_root` and load `rules/work-bundle/wb-credential-use.md` plus `rules/security-exclusion.md` before any credential operation.

Never open, print, grep, summarize, or directly ingest `credentials/credentials.yaml`. Use only the bounded helper in `scripts/work-bundle/credential.py`. Pass credential ID, exact target, requested operation, purpose, and current-task authorization; never pass credential values between agents or through command arguments.

Run metadata-only discovery with `python3 scripts/wb.py credential-list --workspace-root <workspace-root>`. Reject missing authorization, target mismatch, read-only/write mismatch, unsafe transport, unsafe injection, excess permissions, extra files, symlinks, and malformed schemas before value access.

Select the adapter by credential form before accessing a value: password files use a path reference; username/password uses a protected file descriptor; unprotected SSH key paths use a path reference; passphrases use stdin; environment references use only a child-scoped environment; and supported external references use the existing keychain or agent. Block encrypted SSH-key passphrases, unsupported providers, adapter overrides, command-line transport, and any consumer that cannot use the selected mechanism.

Suppress raw child stdout/stderr and return only the adapter-result fields declared by `references/wb-credential-use-contract.yaml`. Do not claim a generic one-value environment supports multipart credentials, expose tracebacks, mutate the parent environment, or add show/get/dump/debug commands.

Use synthetic credentials for validation and assert zero occurrences across stdout, stderr, process arguments, artifacts, indexes, handoffs, and Git diff.
