---
id: agent-codegraph-first
applies_when:
  - the targeted repository root contains `.codegraph/`
  - task affects source-code files in that targeted repository that CodeGraph indexes with meaningful symbol or relation extraction
  - task requires source-code browsing, inspection, review, planning, repair, refactor, migration, or editing
  - task requires locating symbols, files, call chains, dependencies, module boundaries, implementation paths, or impact radius
  - task is not limited to Markdown rules, skills, references, templates, documentation, or WorkBundle knowledge-only edits
enforcement: must
load: conditional
requires: []
---

# CodeGraph-First Codebase Exploration

## Purpose

Require agents to establish graph-based structural context before broad source browsing or code edits when CodeGraph is available for an existing repository.

## Must

- Use CodeGraph before broad file browsing, grep-heavy exploration, repeated manual reading, or code edits in an indexed repository.
- When the targeted repository root contains `.codegraph/` and CodeGraph is available, run `codegraph sync <repo-root>` after applicable repository preflight and before graph-derived source inspection, delegation context preparation, or editing.
- If `codegraph sync <repo-root>` fails and strict graph gating is not explicitly required, record `sync-failed` and continue only through bounded fallback using direct file reads or text search.
- Query CodeGraph for the relevant symbol, feature, module, package, or architectural area before direct file reading.
- Use returned graph context to identify the minimum set of files that require direct reading.
- Read only the files needed to verify behavior, contracts, and implementation details after graph context is known.
- Use CodeGraph to locate relevant files, packages, classes, functions, methods, interfaces, and configuration entry points.
- Use CodeGraph to trace caller and callee relationships, dependency direction, module boundaries, and impact radius.
- Check CodeGraph before changing public APIs, shared utilities, schemas, DTOs, handlers, services, repositories, jobs, configuration, lifecycle hooks, data models, persistence objects, or cross-module contracts.
- Compare intended changes against existing architecture and determine whether a similar implementation already exists.
- Prepare a compact graph-derived context bundle before delegating implementation to another agent.
- Validate that proposed changes touch the correct layer and do not bypass existing abstractions.
- Use text search only after CodeGraph cannot locate the target or when exact literals, logs, SQL fragments, route strings, property keys, error messages, environment variables, or comments are required.
- Edit only after the structural path and expected impact radius are known.
- For any non-trivial change, record the CodeGraph query or explored symbol or module, relevant upstream callers or entry points, relevant downstream callees or dependencies, files selected for direct reading, and expected impact radius.
- Before finishing, verify that the final change still matches the graph-derived context.
- When changing indexed source in a CodeGraph-enabled repository, run a post-change `codegraph sync <repo-root>` before final graph impact validation and completion.
- Re-check impact through CodeGraph before completion when an edit changes public behavior, public signatures, module boundaries, or dependency direction.

## Must Not

- Do not start with large-scale recursive file reading, broad grep, glob scanning, or random source browsing when CodeGraph is available.
- Do not edit a symbol, public API, shared utility, lifecycle hook, data model, persistence object, or cross-module contract without first checking its relationships and downstream usage through CodeGraph.
- Do not treat lexical search results as sufficient evidence for architectural decisions when graph context is available.
- Do not skip CodeGraph unless CodeGraph is unavailable, returns an explicit tool or runtime error, the target is outside the indexed repository, the task concerns non-code files that CodeGraph does not index meaningfully, or the task requires exact text matching.
- Do not skip CodeGraph silently; state the reason briefly in working notes or the final handoff when falling back.
- Do not run `codegraph sync`, require CodeGraph use, or initialize CodeGraph for a repository root that lacks `.codegraph/`; record no-index fallback instead.
- Do not treat a successful sync as a replacement for repository preflight or as permission to accept unexplained source mutations.

## Validation

- Confirm CodeGraph was skipped with reason `no-index` when the repository root lacked `.codegraph/`.
- Confirm `codegraph sync <repo-root>` was run before graph-derived source exploration or edits when the repository has `.codegraph/` and CodeGraph was available, or confirm `sync-failed` fallback evidence was recorded.
- Confirm CodeGraph was queried before broad source exploration or edits when the repository has `.codegraph/` and CodeGraph MCP or CLI access.
- Confirm direct file reads were selected from graph context rather than from unbounded browsing.
- Confirm text search, when used, was secondary or was justified by exact literal matching needs.
- Confirm non-trivial change evidence records the query or symbol, upstream callers or entry points, downstream dependencies, selected files, and expected impact radius.
- Confirm indexed source changes ran post-change `codegraph sync <repo-root>` before final graph impact validation, or recorded an explicit fallback or not-applicable reason.
- Confirm public behavior, signature, module boundary, or dependency-direction changes were re-checked through CodeGraph before completion.

## On Violation

Stop broad exploration or editing, run the required `codegraph sync <repo-root>` and CodeGraph query when applicable, record the structural context and impact radius, and then continue from the minimum verified file set. If CodeGraph cannot be used or sync fails, record the concrete fallback reason before continuing; if `.codegraph/` is absent, do not initialize CodeGraph and proceed only with no-index fallback evidence.
