---
id: spec-YYYYMMDD-001
title: [Concise Title Describing the Specification's Focus]
project: <project-slug>
status: draft
date_created: [YYYY-MM-DD]
last_updated: [Optional: YYYY-MM-DD]
source_knowledge:
  - .project-knowledge/notes/...
related_handoffs: []
version: [Optional: e.g., 1.0, Date]
tags: [Optional: List of relevant tags or categories, e.g., `infrastructure`, `process`, `design`, `app` etc]
---

# Introduction

[A short concise introduction to the specification and the goal it is intended to achieve.]

## 1. Purpose & Scope

[Provide a clear, concise description of the specification's purpose and the scope of its application. State the intended audience and any assumptions.]

## 2. Definitions

[List and define all acronyms, abbreviations, and domain-specific terms used in this specification.]

## 3. Initial Shell

Before any long evidence gathering, create the specification shell with front matter and these required placeholders:

- `Initial User Purpose Evidence`
- `Draft Requirement Breakdown`

`Initial User Purpose Evidence` must be derived only from the current user request and visible supplied artifacts. `Draft Requirement Breakdown` is provisional and must be revised after bounded evidence gathering; it must not be silently replaced.

## 4. Source Context

[Record the evidence used before drafting. Include durable knowledge gateway results grouped by `authority`, `candidate`, `background`, and `blocked`, plus current repository evidence with path, role, and relevance. Durable knowledge discovery for specification creation must be neutral and cross-stage: record neutral query anchors, candidate sources or retrieval gaps, and the active retrieval policy as classification/output intent rather than a discovery-stage filter. Only `authority` durable knowledge may shape requirements, constraints, acceptance criteria, or downstream tasks.]

When no supporting authority note exists for the user purpose, record the retrieval gap and analyze the purpose from user input and repository evidence. Use Design Interrogation only for unresolved design intent that cannot be answered from current evidence.

When material non-authority evidence appears, record agent-owned polarity and materiality classification as supporting, opposing, constraining, unresolved/open-question, obsolete/replaced, or irrelevant-with-reason evidence. Candidate, background, and blocked evidence must remain non-shaping unless resolved by the user or promoted by accepted authority.

### 4.1 Design Interrogation

[Required when user intent is under-specified, repository evidence conflicts, or no supporting note exists and the purpose cannot be resolved from current evidence.]

- **Trigger**: no-supporting-note|under-specified-purpose|repository-evidence-conflict|none
- **Question**: Ask one design question at a time.
- **Recommended answer**: Provide the advised answer and rationale.
- **User resolution**: Record accepted answer or unresolved.
- **Evidence conclusion**: Record any accepted conclusion as specification evidence.

## 5. Requirements, Constraints & Guidelines

[Explicitly list all requirements, constraints, rules, and guidelines. Use bullet points or tables for clarity.]

- **REQ-001**: Requirement 1
- **SEC-001**: Security Requirement 1
- **[3 LETTERS]-001**: Other Requirement 1
- **CON-001**: Constraint 1
- **GUD-001**: Guideline 1
- **PAT-001**: Pattern to follow 1
- **REQ-SHELL-001**: Create the specification shell before extended evidence gathering, and keep `Initial User Purpose Evidence` and `Draft Requirement Breakdown` visible in the generated artifact.
- **REQ-SHELL-002**: Derive initial user-purpose evidence only from the current user request and visible supplied artifacts.
- **REQ-SHELL-003**: Revise draft requirements after bounded evidence gathering instead of silently replacing them.

## 6. Interfaces & Data Contracts

[Describe the interfaces, APIs, data contracts, or integration points. Use tables or code blocks for schemas and examples.]

## 7. Acceptance Criteria

[Define clear, testable acceptance criteria for each requirement using Given-When-Then format where appropriate.]

- **AC-001**: Given [context], When [action], Then [expected outcome]
- **AC-002**: The system shall [specific behavior] when [condition]
- **AC-003**: [Additional acceptance criteria as needed]
- **AC-SHELL-001**: Given a new specification request, when the artifact is created, then the shell exists first with front matter plus `Initial User Purpose Evidence` and `Draft Requirement Breakdown`.
- **AC-SHELL-002**: Given bounded evidence gathering completes, when the draft is updated, then the original draft requirement breakdown is revised rather than erased without trace.

## 8. Test Automation Strategy

[Define the testing approach, frameworks, and automation requirements.]

- **Test Levels**: Unit, Integration, End-to-End
- **Frameworks**: MSTest, FluentAssertions, Moq (for .NET applications)
- **Test Data Management**: [approach for test data creation and cleanup]
- **CI/CD Integration**: [automated testing in GitHub Actions pipelines]
- **Coverage Requirements**: [minimum code coverage thresholds]
- **Performance Testing**: [approach for load and performance testing]

## 9. Rationale & Context

[Explain the reasoning behind the requirements, constraints, and guidelines. Provide context for design decisions.]

## 10. Dependencies & External Integrations

[Define the external systems, services, and architectural dependencies required for this specification. Focus on **what** is needed rather than **how** it's implemented. Avoid specific package or library versions unless they represent architectural constraints.]

### External Systems
- **EXT-001**: [External system name] - [Purpose and integration type]

### Third-Party Services
- **SVC-001**: [Service name] - [Required capabilities and SLA requirements]

### Infrastructure Dependencies
- **INF-001**: [Infrastructure component] - [Requirements and constraints]

### Data Dependencies
- **DAT-001**: [External data source] - [Format, frequency, and access requirements]

### Technology Platform Dependencies
- **PLT-001**: [Platform/runtime requirement] - [Version constraints and rationale]

### Compliance Dependencies
- **COM-001**: [Regulatory or compliance requirement] - [Impact on implementation]

**Note**: This section should focus on architectural and business dependencies, not specific package implementations. For example, specify "OAuth 2.0 authentication library" rather than "Microsoft.AspNetCore.Authentication.JwtBearer v6.0.1".

## 11. Open Questions

[List unresolved decisions, uncertainty, conflicts, and material non-authority evidence that affects requirements, architecture, workflow, API, persistence, validation, execution behavior, or user purpose.]

Every open question must include:

| Field | Required |
| --- | --- |
| ID | yes |
| Question or uncertainty | yes |
| Related scope | yes |
| Source | yes |
| Blocking | yes |
| Required resolution | yes |
| Advised options | yes |

Candidate, background, blocked, draft, proposed, stale, or otherwise non-authority durable knowledge must not become requirement text. When material, record it as rationale, traceability, conflict evidence, or blocking open-question input.

## 12. Knowledge Base Update

[Record whether this specification is expected to produce durable project knowledge without instructing agents to write durable notes directly.]

- **Disposition**: required|not-needed|blocked
- **Expected durable conclusions**:
  - [List candidate durable conclusions or `None for this specification scope.`]
- **Evidence sources**:
  - [List expected implementation, validation, handoff, or source evidence.]
- **Responsible follow-up**: [Record the approved follow-up path or `none`.]
- **Blocks review/archive**: yes|no
- **Rationale**: [Explain why the disposition applies.]

Set disposition to `required` when accepted Design Interrogation conclusions establish new durable orchestration policy, workflow design, or reusable process behavior.

## 13. Examples & Edge Cases

    ```code
    // Code snippet or data example demonstrating the correct application of the guidelines, including edge cases
    ```

## 14. Validation Criteria

[List the criteria or tests that must be satisfied for compliance with this specification.]

- The generated specification includes front matter and a shell created before extended evidence gathering.
- The generated specification includes `Initial User Purpose Evidence` sourced from the current user request and visible supplied artifacts only.
- The generated specification includes `Draft Requirement Breakdown` and revises it after bounded evidence gathering.
- The specification remains self-contained and does not require broad repository exploration before the shell exists.
- The source context records neutral cross-stage retrieval anchors or a retrieval gap, and any named retrieval policy is used only for classification/output grouping.
- The specification carries accepted authority context forward so downstream planning and execution do not need to read `.work-bundle/knowledge/`.

## 15. Quality Gate

Quality gate: verified|blocked

Checked:

- user purpose coverage
- durable knowledge classification
- current repository contract coverage
- affected-file coverage
- assumptions and alternatives
- open questions

Findings:

- [gap or none]

Extra evidence loop:

- round 1: changed|unchanged|blocked - [drift/gap/evidence result]
- round 2: changed|unchanged|blocked - [drift/gap/evidence result, when needed]
Final result: verified|blocked

Run another evidence round whenever a round changes, fixes, adds, removes, or reclassifies material evidence. If any round records a blocking open question, the quality gate remains `blocked` until the question is resolved and the loop runs again.

## 16. Related Specifications / Further Reading

[Link to related spec 1]
[Link to relevant external documentation]
