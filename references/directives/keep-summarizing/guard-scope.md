# guard-scope

## Intent

Enforce project knowledge boundaries, sensitivity metadata, and embedding exclusions.

## Trigger phrases

- check knowledge scope
- sensitivity check
- is this path allowed

## Use when

Before any write, index export, or Git operation in the knowledge repo.

## Workflow

Verify:

- selected project resolves to `.work-bundle/knowledge/` or an explicitly selected external legacy root for migration/read-only intake
- registry data, when used, comes from `~/.work-bundle/registry/projects.yaml`, `KS_PROJECT_REGISTRY`, or `--registry-file`, and is treated as local runtime state
- target path is inside the selected knowledge repo
- Git command is allowlisted
- note has `visibility` and `sensitivity`
- embedding export excludes blocked statuses and sensitivities
- reader-facing documents are redirected to `orch-create-document` and inherit source sensitivity there

Fail if:

- the target path is under `.work-bundle/orchestration/`
- the target path is outside the selected knowledge repo
- the note target is not under `notes/<lifecycle-stage>/<leaf-perspective>/`
- the open-question target is not under `open-questions/<lifecycle-stage>/<leaf-perspective>/`
- the target perspective is broad or missing
- the write would create Markdown at the knowledge root
- the operation would copy raw source files, raw design files, transcripts, logs, credentials, tokens, or personal data into knowledge
- Git is requested outside the selected knowledge repo

## Return

- pass or fail per check
- blocking issues and required user action
