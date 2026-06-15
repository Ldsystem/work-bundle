---
id: ks-git-authority
applies_when:
  - git operation is requested inside the selected durable knowledge repo
  - keep-summarizing git authority is evaluated for a migration or maintenance task
enforcement: must
load: conditional
requires: []
---

# Keep-Summarizing Git Authority

## Purpose

Define the Git boundary for keep-summarizing work. Git authority is limited to the selected durable knowledge repo and only for normal maintenance operations; it does not extend to orchestration artifacts, source repositories, or destructive history changes.

## Must

- scope keep-summarizing Git authority to the selected durable knowledge repo only
- allow only normal Git operations by default:
  - `status`
  - `diff`
  - `log`
  - `add`
  - `commit`
  - `branch`
  - `tag`
  - `restore`
- treat explicitly selected legacy roots as migration or read-only compatibility sources unless the user explicitly expands authority
- require explicit user approval before protected operations:
  - `reset --hard`
  - `force-push`
  - branch deletion
  - deleting durable Markdown

## Must Not

- apply keep-summarizing Git authority to source repositories
- apply keep-summarizing Git authority to `.work-bundle/orchestration/` or other non-knowledge repos by default
- treat destructive history or durable-content deletion as normal Git authority
- infer broader Git permission from read-only migration access to a legacy knowledge root

## Validation

- the repository boundary is the selected durable knowledge repo and not a source repo or orchestration tree
- requested Git commands stay within the default allowed operation list unless the user explicitly approves a protected operation
- legacy migration roots are not used to justify broader Git authority
- destructive or durable-delete operations are blocked until approval is explicit

## On Violation

Stop the Git operation, report whether the problem is out-of-scope repository access or a protected command, and wait for explicit approval or switch back to allowed knowledge-repo operations before continuing.
