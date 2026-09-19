---
name: wb-create-script
description: Design, create, or refactor WorkBundle helpers and reusable workspace utilities with explicit responsibility, safe effects, and testable contracts. Not needed merely to run an existing command or interpret its output.
---

# Create a Qualified Script

A script implements a defined operation; it does not decide what the user's work ought to mean. Automate repeatable computation, transformation, checks, and authorized transitions. Leave interpretation of requirements, sufficiency of evidence, and choice of remediation with the responsible agent or caller.

## Establish the contract

Before coding, identify the intended result, existing owning component, inputs, observable outputs, permitted effects, and source of policy. Resolve only ambiguities that would change behavior or authority. A small change can carry this contract in its existing task context; do not create a separate approval artifact by default.

Distinguish three responsibilities:

- **Facts and mechanics:** compute, parse, transform, compare identities, check explicit constraints, and report what happened. These belong in code when reproducible automation helps.
- **Supplied policy:** enforce a documented contract or caller-supplied decision within its authorized scope. Validation and safety guards are legitimate; make their source and effect explicit.
- **Judgment:** decide whether an implementation meets intent, evidence is sufficient, or a repair is appropriate. Do not approximate these decisions with keywords, scores, incidental metadata, or an unrelated successful check.

For example, a checker can report malformed links and passing tests. Neither establishes that a document explains the intended behavior. Conversely, rejecting a write outside an authorized directory is a proper mechanical guard, not forbidden judgment.

## Shape the implementation

- Put behavior in its existing owner; keep command routing separate from reusable operation logic. Avoid duplicating lifecycle policy in adapters or creating a framework for a bounded helper.
- Accept information through explicit inputs or the current authoritative store. For persisted or exchanged records that are reread, indexed, or lifecycle-authoritative, use their maintained versioned schema and artifact-family catalog as the structural authority. Released schemas are immutable; incompatible changes create a new version, and distinct semantic roles use distinct schema families. Do not externalize every ordinary constant or embed project-specific exceptions in generic code.
- Keep structural ownership mechanical: scripts may own schema selection, artifact type and identity, canonical anchor/location, declared parent-child bindings, maintained parsing and serialization, validation, atomic mutation, lifecycle transitions, and derived index projection. Callers own the semantic payload and cannot override those structural fields.
- Parse structure through a maintained format implementation. Search text or directories only when retrieval, index rebuilding, navigation, or diagnostics is the declared operation; treat every hit as a candidate until the canonical structured reader validates it. Do not use regexes, headings, substrings, broad globs, filenames, or successful unrelated checks to infer structural or semantic authority.
- Define output and failure semantics that callers can act on: measured result, affected scope, and any partial effects. A successful exit means the declared operation succeeded, not that the surrounding project is accepted. A refusal identifies the failed condition, not an invented product verdict or mandatory repair workflow.
- Separate inspection from mutation where it helps safe use. Validate effect-bearing inputs before writes; preserve unrelated content. Define overwrite, retry, and partial-failure behavior proportional to the operation. Do not assume every command can be idempotent; make non-repeatable effects explicit.
- Consume existing authoritative results through their supported interface. Recompute only when relevant inputs changed or the contract requires it; do not reconstruct historical activity merely to make an interface convenient.

For workspace utilities or changes to initialization, discovery, or utility indexes, read [Workspace integration](references/workspace-integration.md). Ordinary toolkit helper changes do not need that reference.

## Verify and hand off

Exercise observable behavior against the contract: normal output, a meaningful invalid input, and relevant mutation or retry boundaries. Check that errors neither hide partial effects nor broaden the refused operation. Scale tests to risk; do not impose a fixed ceremony on every helper.

Inspect the decision boundary as an agent: what does each check actually establish, where does policy come from, and is any caller treating a mechanical result as a broader judgment? Tests of prescribed wording cannot answer these questions.

If the boundary is crossed, repair the first owning interface or implementation and recheck the affected behavior. Do not add a second checker to legitimize the first one's unsupported decision. Retain useful checks and accurate facts.

Return the implemented contract, changed files, actual validation results, and any remaining limitation. Do not add acceptance gates, external actions, or workflow stages beyond the user's task.

## Self-check

- Does the script implement facts, explicit supplied policy, or authorized mechanics without deciding semantic correctness, sufficiency, qualification, remediation, or acceptance?
- For every persisted or exchanged record it owns, is there one real versioned schema/catalog/locator/parser path, with no fallback identity, filename inference, or compatibility authority?
- Are searches limited to declared retrieval, index, navigation, or diagnostic jobs, with hits treated as candidates until canonical read and any required agent judgment?
- Are effect-bearing inputs and declared relationships validated before mutation, writes atomic where required, unrelated bytes preserved, and partial effects reported truthfully?
- Do normal, meaningful invalid, retry/mutation, producer, and consumer tests exercise the observable contract rather than prescribed wording?
