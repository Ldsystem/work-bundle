# help-with-directives

## Intent

Help the user understand which keep-summarizing directive applies and what it will do.

## Trigger phrases

- what directives exist
- which directive to use
- what a directive means
- what will happen next
- how to phrase a request for this skill
- why the agent is waiting for approval or direction

## Use when

The user asks about the skill itself, not about project knowledge content.

## Do not use when

The user wants to search the knowledge base for a task (`what-is-helpful`) or persist notes (`write-knowledge`).

## Required inputs

- The user's goal or confusion in their own words.
- Optional: whether they want read-only discovery or persistence.

## Workflow

1. Read [../directives.md](../directives.md) for routing.
2. Explain directives in user-facing language, not implementation jargon.
3. Name the recommended directive and link to its file.
4. State whether the agent will only plan, persist notes, rebuild indexes, or run scoped Git.
5. Include waiting state and concrete next choices when relevant.

## Return

- recommended directive or directives
- when to use each one
- what input the user should provide
- what output the agent should produce
- whether the agent will only plan, persist notes, rebuild indexes, or run scoped Git
- any waiting state and concrete next choices
- whether open-question watchpoints are relevant

Example response shape:

```text
Use `breakdown-design` when you have a messy design file and want it split into durable knowledge notes.

I need:
- project slug
- design file path
- desired lifecycle-aware leaf perspectives, such as `development-design/architecture/decisions`, `development-design/workflow/data-flow`, and `development-design/workflow/process-flow`
- whether to draft only or apply updates

Output:
- inferred themes
- target notes
- non-persisted open questions, if any
- persistence plan

Waiting for your direction.
Choose one:
1. Draft the breakdown only.
2. Apply the breakdown to the project knowledge repo.
```
