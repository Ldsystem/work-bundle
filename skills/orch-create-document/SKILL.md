---
name: orch-create-document
description: 'Create reader-facing orchestration documents from accepted context.'
---

# orch-create-document

## Scope

Create reader-facing orchestration documents from accepted context.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Knowledge Gateway

Before drafting from durable project knowledge, use `keep-summarizing` with `what-is-helpful` gateway mode. Do not directly browse `.work-bundle/knowledge/`.

For v3 knowledge, map reader-facing documents to the `customer_spec` retrieval policy by default. Source context must separate `authority`, `candidate`, `background`, and `blocked` results. Use only authority knowledge returned by that gateway or explicit user-provided source material as factual content. Candidate/background context may inform omissions, caveats, or source notes; blocked context must not shape the document.

## Fit

Use for project overviews, feature explanations, stakeholder briefings, technical reports, onboarding, speeches, presentation notes, value explanations, architecture/process/data-flow explanations for readers, and custom human-readable documents.

Do not use this skill for specs, implementation plans, execution, or handoffs.

## Parameters

Use available parameters: `intent`, `output_language`, `audience`, `source_scope`, `tone`, `detail_level`, `include_sources`, and `title`.

If `title` is absent, derive it from the final document.

## Output

Save under:

```text
.work-bundle/orchestration/docs/[document-title-slug].md
```

Rules:

- save exactly one Markdown file unless multiple files are requested;
- do not create or update an index;
- do not write under `.work-bundle/knowledge/`;
- use clear headings and the requested language, audience, tone, and detail level;
- cite project knowledge paths or note IDs only when sources are requested.

Hard rules:

- stop if the requested output is really a spec, plan, execution task, or handoff;
- stop if durable knowledge is needed but was not retrieved through `keep-summarizing`;
- omit unsupported facts instead of inventing filler;
- never include raw chat logs or private reasoning.

## Contract

Load only when creating or validating:

- `references/assets/orchestration/contract/document-v1.md`

## Validation

Confirm the document is reader-facing, stored under `.work-bundle/orchestration/docs/`, excludes unsupported facts and raw chat logs, uses the requested communication settings, and reports created path, title, source scope, and omitted unsupported areas.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-knowledge-gateway`: `rules/orchestration/orch-knowledge-gateway.md`
- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`

Central `AGENTS.md` owns rule discovery and loading. Load the runtime rules above when their indexed conditions apply.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/orchestration/contract/`

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`).
