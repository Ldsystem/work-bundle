---
name: create-specification
description: 'Create a new specification file for the solution, optimized for Generative AI consumption.'
---

# Create Specification

Create an AI-ready specification for `${input:SpecPurpose}`.

## Knowledge Gateway

Before drafting from durable project knowledge, use `keep-summarizing` with `what-is-helpful` gateway mode. Do not directly browse `.work-bundle/knowledge/`.

For v3 knowledge, map implementation specifications to the `implementation_spec` retrieval policy. Source context must separate `authority`, `candidate`, `background`, and `blocked` results. Only `authority` context may shape requirements and contracts; candidate/background context may appear only as rationale, traceability, or promotion input.

The specification is the first execution-chain artifact:

```text
spec -> plan -> phase -> task -> execute -> handoff
```

It must carry enough accepted context for planning and execution without future knowledge-base lookup.

## Requirements

- Use precise, explicit, unambiguous language.
- Distinguish requirements, constraints, assumptions, alternatives, and open questions.
- Inspect relevant note states and open-question watchpoints through the approved knowledge gateway when durable knowledge affects the scope.
- Surface relevant draft, proposed, conflicting, stale, or missing-evidence context as uncertainty; do not convert it into requirements.
- Include an `Open Questions` section. If relevant uncertainty exists, list ID, question or uncertainty, related scope, source, blocking yes/no, and required resolution. If none exists, state `None for this specification scope.`
- Include a `Knowledge Base Update` section in every new or repaired specification.
- In `Knowledge Base Update`, allow only these dispositions for new specs: `required`, `not-needed`, `blocked`.
- In `Knowledge Base Update`, require `Expected durable conclusions`, `Evidence sources`, `Responsible follow-up`, `Blocks review/archive`, and `Rationale`.
- When no durable update is expected, set `Expected durable conclusions` to `None for this specification scope.`
- Record only disposition and follow-up path in `Knowledge Base Update`; do not instruct agents to write durable notes from the specification.
- Define domain terms and acronyms.
- Include affected modules, files, APIs, schemas, data flows, workflows, compatibility, migration, deployment, testing, and operational constraints when relevant.
- Include examples, edge cases, fallback decisions, and validation expectations when useful.
- Record missing or uncertain context as assumptions or open questions.
- Do not store specifications under .work-bundle/knowledge/.

## Hard Rules

- Stop if the spec cannot be self-contained enough for planning.
- Stop if durable knowledge is needed but was not retrieved through `keep-summarizing`.
- Do not implement source changes, edit application/test files, run migrations, apply patches, or execute plan tasks while creating a specification.
- If the user also asks for implementation, finish the specification artifact first, then stop and require an explicit `execute-plan` request.
- Do not defer required execution context to future `.work-bundle/knowledge/` lookup.
- Do not mix implementation plan tasks into the spec; record planning needs as constraints or open questions.
- Do not hide unresolved architecture, data model, API contract, persistence, execution-flow, or authority decisions inside assumptions.
- Do not instruct agents to write durable knowledge directly from the specification; only record disposition, evidence expectations, and the responsible follow-up path.
- Do not write raw chat logs, unsupported facts, or hidden reasoning.

## Output

Save under:

```text
.work-bundle/orchestration/spec/active/spec-[purpose]-[slug].md
```

Allowed high-level purpose prefixes: `schema`, `tool`, `data`, `infrastructure`, `process`, `architecture`, `design`.

Use valid Markdown with YAML front matter.

## Contract

Load only when creating or validating:

- [specification-v1.md](../../assets/orchestration/contract/specification-v1.md)

If the contract lacks explicit sections for source context, execution context, assumptions, alternatives, open questions, or fallback decisions, include those sections anyway.

Every generated specification must also include this section even if the contract/template is stale:

```markdown
## Knowledge Base Update

- **Disposition**: required|not-needed|blocked
- **Expected durable conclusions**:
  - <candidate durable conclusion or `None for this specification scope.`>
- **Evidence sources**:
  - <expected implementation, validation, handoff, or source evidence>
- **Responsible follow-up**: <approved follow-up path or `none`>
- **Blocks review/archive**: yes|no
- **Rationale**: <why the disposition applies>
```

## Validation

Confirm the spec is self-contained, cites source context, carries execution-relevant knowledge into the body, records assumptions/open questions, includes the required `Knowledge Base Update` section and no-update wording when applicable, follows naming/location rules, and does not require downstream agents to read `.work-bundle/knowledge/`.
