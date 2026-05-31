# Perspectives

Knowledge base content is for agents. Optimize for precise retrieval, lifecycle-aware context extraction, and predictable downstream generation.

## Core Rules

- One knowledge piece answers one durable question.
- Title must be concise, descriptive, and specific.
- Use the most specific lifecycle-aware leaf path. Broad nodes are containers only.
- Indexes contain exact paths; the tree is kept for deterministic placement, not human reading.
- Tags may connect cross-cutting concerns, but `perspective` must be one primary leaf path.
- Durable notes include a lifecycle stage and status. Only `confirmed`, `implemented`, and `current` may be authority by default.
- Open questions must live under `.work-bundle/knowledge/open-questions/`, not inside durable notes.
- Version history is for knowledge maintenance only; orchestrator must ignore it when creating specs, plans, tasks, handoffs, or execution context.
- Do not add `Examples`, `Release Notes`, `Open Questions`, or `Superseded Theory` sections by default.
- Examples are allowed only when required to explain a durable rule or contract.

## Title Rules

Good:

```text
Dataset Row Identity Uses Configured Identifier Fields
Redis Row Cache Keys Are Built Through CacheKeyBuilder
Replay Task Lifecycle States
API Error Response Shape
```

Bad:

```text
Backend Architecture
Data Model
Frontend Notes
Redis
Key
DTO
```

## V3 Status And Retrieval Roles

`status` is the single maturity and authority field:

```text
draft -> proposed -> confirmed -> implemented -> current
```

Exceptional exits are `superseded`, `deprecated`, and `rejected`.

SQLite FTS may retrieve notes across statuses. Every result must be classified before use:

- `authority`: may shape downstream artifacts.
- `candidate`: useful but requires confirmation or promotion.
- `background`: rationale or traceability only.
- `blocked`: rejected, superseded, contradicted, or unsafe for current authority.

## Tree

```text
.work-bundle/knowledge/notes/
  tender/                       # opportunity/tender inputs before project discovery; weak authority unless confirmed later
    background/                 # customer/domain/commercial context from tender material
    requirements/               # tender-stated requirements
    constraints/                # tender-stated restrictions
    deliverables/               # requested deliverables and submission items
    glossary/                   # tender terminology

  investigation/                # discovery findings: what exists, who uses it, what must be clarified
    scope-of-work/              # discovered work scope and project boundary
    user-portrait/              # user roles, user groups, operator/customer profile
    business-boundary/          # business scope, exclusions, responsibility boundary
    process-flow/               # current/as-is process or discovered target process
    performance-requirement/    # latency, throughput, scale, resource, retention needs
    integration-landscape/      # existing systems, devices, data sources, external dependencies
    risks/                      # discovered uncertainty, delivery risk, technical/business risk
    constraints/                # discovered constraints not necessarily from tender

  customer-design/              # customer-facing design artifacts; not customer-biased authority
    business-boundary/          # agreed customer-visible business boundary and exclusions
    process-flow/               # customer-readable target business process
    functional-modules/         # modules/features described by business role and customer value
    user-flow/                  # user/operator interaction path without implementation detail
    ui-prototype/               # wireframe, prototype, layout intent, visual interaction sketch
    acceptance-criteria/        # customer-facing acceptance intent and validation conditions
    non-goals/                  # explicitly excluded customer-facing scope

  bidding/                      # bid/contract-facing commitments; commercial authority, not implementation design
    committed-scope/            # scope promised in bid or contract response
    exclusions/                 # explicit exclusions and non-commitments
    deliverables/               # committed deliverables
    milestones/                 # committed schedule/milestone points
    assumptions/                # bid assumptions that need confirmation before implementation authority
    risks/                      # bid/delivery risks and caveats

  development-design/           # engineering design prepared for implementation; primary source for specs/plans
    architecture/               # system-level structure and engineering boundaries
      system-boundary/          # system scope, external boundary, ownership
      component-boundary/       # component responsibility and separation
      dependency-direction/     # allowed/forbidden dependencies
      source-of-truth/          # canonical source and ownership rules
      decisions/                # accepted engineering decisions
      patterns/                 # reusable design/implementation patterns
    workflow/                   # engineering workflow/control/data movement design
      process-flow/             # target workflow as designed for implementation
      data-flow/                # data movement, transformation, persistence, cache
      state-lifecycle/          # states, transitions, lifecycle rules
      control-flow/             # execution/orchestration flow
    data/                       # logical/physical data design before implementation proof
      data-model/               # entities, lifecycle fields, domain objects
      schema/                   # table/column/json/measurement/tag design
      identifiers/              # keys, natural IDs, compound IDs, idempotency keys
      relationships/            # cardinality, ownership, references
      lineage/                  # derivation and traceability rules
      migration/                # migration/backfill/rollback design
    interfaces/                 # contracts between systems/modules/agents
      api-contract/             # HTTP/RPC/service DTO contract
      event-contract/           # event/message payload and compatibility
      file-contract/            # import/export file shape
      error-contract/           # error schema, code, exception mapping
      compatibility/            # compatibility across APIs/events/files/data
    implementation/             # implementation approach design, not yet verified source behavior
      backend/                  # backend implementation design rules
      frontend/                 # frontend implementation design rules
      database/                 # database implementation design rules
      cache/                    # cache implementation design rules
      async-messaging/          # async/event processing design rules
    quality/                    # quality gates and validation design
      requirements/             # engineering quality requirements
      validation/               # invariants and data/domain validation
      testing-strategy/         # test levels, gates, ownership
      edge-cases/               # boundary/failure cases to handle
      performance/              # expected bottlenecks, target performance, tradeoffs
      observability/            # logging, metrics, tracing, health design

  implementation/               # implementation result verified from code, handoff, review, or tests
    implemented-features/       # actual completed feature behavior
    reusable-functions/         # reusable utilities/helpers and actual behavior
    module-structure/           # actual module/package/component structure
    code-structure/             # actual file/class/function layout and ownership
    coding-rules/               # implemented/enforced coding conventions
    tests/                      # actual test coverage and test behavior
    known-limitations/          # known implementation limits or unresolved technical debt
    implementation-decisions/   # decisions discovered or finalized during implementation

  deployment/                   # deployment/environment facts and rollout mechanics
    topology/                   # deployed topology and runtime layout
    configuration/              # env vars, config files, defaults, profiles
    packaging/                  # package/build/container/runtime artifacts
    migration/                  # deployment migration/backfill/rollback operations
    backup-restore/             # backup, restore, retention, verification
    resource-limits/            # CPU, memory, disk, network assumptions
    rollout-rollback/           # rollout and rollback procedures
    startup-shutdown/           # startup order, supervision, keepalive, recovery
    security-permission/        # runtime authn/authz, roles, secrets, audit

  go-live-delivery/             # final delivery, acceptance, handover, and cutover records
    acceptance-result/          # acceptance outcome and final validation result
    delivery-scope/             # actually delivered scope
    handover/                   # handover material and responsibility transfer
    training/                   # training material and training records
    final-exclusions/           # exclusions confirmed at delivery
    support-boundary/           # support responsibility and maintenance boundary
    production-cutover/         # cutover action and production activation record

  operation/                    # production/runtime observations and maintenance knowledge
    runtime-observation/        # observed production/runtime facts
    troubleshooting/            # diagnosis steps, commands, known fixes
    incidents/                  # incident records and conclusions
    performance/                # measured performance and optimization results
    maintenance/                # recurring maintenance procedures
    optimization/               # accepted runtime optimization conclusions
    security-audit/             # audit findings and security operation facts
```

## Lifecycle Clarifications

`customer-design` means customer-facing design, not customer-biased design.

Use `customer-design` for artifacts that communicate business intent, user-visible behavior, module shape, UI prototype, acceptance intent, and customer-facing scope. These notes explain what the customer/user expects to see or validate. They are not implementation authority by default.

Use `development-design` when the same idea is translated into engineering authority: architecture, workflow, data flow, data model, API contract, implementation approach, and test strategy.

Use `implementation` only when behavior is verified from source code, handoff, review result, or tests.

Promotion example:

```text
customer-design/functional-modules/report-dashboard.md
  -> describes customer-visible module intent

development-design/architecture/component-boundary/report-dashboard.md
  -> confirms engineering component boundary derived from the customer design

implementation/implemented-features/report-dashboard-filtering.md
  -> records actual implemented behavior after review
```

Earlier lifecycle notes may be retrieved as candidate/background context, but they must not directly become implementation authority without confirmation or promotion.


## Note Format
[note-contract](contract/note-contract-v1.md)

## Orchestrator Rule

For specs/plans/tasks/handoffs/execution context, use only current effective facts, current constraints, current rules, and unresolved open-question records. Ignore note version history and do not carry it into orchestration artifacts.
