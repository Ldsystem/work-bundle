---
id: orch-knowledge-gateway
applies_when:
  - create-specification needs durable project knowledge before drafting
  - create-implementation-plan needs durable project knowledge or spec repair context
  - create-document needs durable project knowledge before drafting
  - create-handoff needs durable project knowledge for an orchestration handoff outside execution completion
  - review-plan needs durable project knowledge for validation-backed review
enforcement: must
load: conditional
requires: []
---

# Orchestration Knowledge Gateway

## Purpose

Route orchestration access to durable project knowledge through the approved `ks-what-is-helpful` gateway. Orchestration creates derived artifacts; keep-summarizing preserves durable knowledge. This rule does **not** apply during `execute-plan`.

## Must

- Retrieve durable project knowledge through `keep-summarizing` with `what-is-helpful` gateway mode before using knowledge context in orchestration directives covered by this rule.
- Discover relevant candidates across allowed lifecycle partitions before lifecycle and status authority classification.
- Use polarity-neutral and stage/perspective/status-neutral query anchors derived from artifacts, features, functionality, components, files, APIs, schemas, workflows, and explicit names.
- Run bounded gateway discovery for material new findings or requests even when repository metadata preflight blocks source inspection, provided the knowledge base and gateway tooling are accessible; mark those results classification-only until source-repository trust is restored.
- Classify retrieved notes as `authority`, `candidate`, `background`, or `blocked`, and surface material supporting, opposing, constraining, unresolved/open-question, obsolete/replaced, or irrelevant-with-reason evidence when applicable.
- Use only `authority` results to shape requirements, executable tasks, decisions, or review conclusions.
- Keep gateway output to the smallest useful classified result set.
- Apply retrieval policy per directive as classification and output-grouping intent, not as a discovery-stage lifecycle filter:

| Directive | Policy |
| --- | --- |
| `create-specification` | `implementation_spec` |
| `create-implementation-plan` | `implementation_plan` |
| `create-document` | `customer_spec` |
| `create-handoff` (orchestration type) | `implementation_plan` |
| `review-plan` | `implementation_plan` |

- Allow `candidate` and `background` context only as rationale, traceability, or promotion input—not as executable requirements.
- Record material `candidate`, `background`, or `blocked` context as visible rationale, traceability, conflict evidence, or open-question input when it affects requirements, architecture, workflow, API, persistence, validation, execution behavior, or user-purpose conflict.
- Treat non-material `candidate`, `background`, or `blocked` context as source context or omit it from the artifact; do not resolve non-material unsettled notes during `create-specification`.
- Treat `blocked` context as non-shaping evidence that must not drive downstream work; when material, surface it as blocking open-question evidence instead of silently deciding.
- Carry accepted authority context into orchestration artifacts so downstream executors do not need future knowledge-base lookup.
- Treat repository metadata preflight blockers as blockers for broad repository evidence gathering, source inspection, impact-radius traversal, downstream implementation planning, and execution trust, not as automatic blockers for bounded durable-knowledge discovery.

## Must Not

- Browse `.work-bundle/knowledge/` directly as a shortcut from orchestration directives covered by this rule.
- Treat a directive retrieval policy such as `implementation_spec` as a stage-gated discovery filter.
- Prefilter discovery to authority lifecycle stages before full candidate discovery completes.
- Let `candidate`, `background`, or `blocked` results directly shape requirements, tasks, decisions, or review conclusions.
- Convert material or non-material non-authority context into requirements, constraints, acceptance criteria, tasks, decisions, or review conclusions without explicit resolution or accepted authority.
- Block `create-specification` only because non-material unsettled notes exist.
- retrieve durable knowledge during execute-plan; execution agents must not read `.work-bundle/knowledge/` directly.
- Apply this gateway rule to `execute-plan`, executor-result handoffs created during execution, or any execution-stage retrieval.
- Defer required execution context to future `.work-bundle/knowledge/` lookup after planning completes.
- Treat a stale repository commit baseline as proof that durable notes are stale without retrieval classification evidence from note metadata, supersession, current user decisions, or accepted authority.
- Block bounded gateway retrieval solely because source-repository metadata preflight blocks source inspection, when the gateway and knowledge base are otherwise accessible.

## Validation

- Confirm retrieval used the approved gateway with neutral anchors and the named retrieval policy only as classification/output intent for the active directive.
- Confirm retrieval policy did not stage-gate candidate discovery.
- Confirm classification labels appear when retrieved notes shape orchestration work.
- Confirm only authority context shaped requirements, tasks, or review conclusions.
- Confirm no direct `.work-bundle/knowledge/` browsing occurred from the active orchestration directive.
- Confirm repository metadata blockers stopped only repository-trust-dependent work and did not prevent accessible bounded gateway discovery.
- Confirm `execute-plan` and execution-completion handoffs did not invoke this gateway.

## On Violation

Stop the orchestration step, rerun retrieval through `ks-what-is-helpful` with full candidate discovery and narrow authority classification, and remove any requirements or tasks shaped by non-authority or direct-browse context before continuing.
