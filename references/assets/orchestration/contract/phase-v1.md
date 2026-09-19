# Phase v1 semantic contract

The current `phase` family is schema-owned YAML. Supply semantic YAML to `write-phase`; the store injects `artifact_type`, `schema_version`, `id`, `plan_id`, `name`, `status: planned`, `date_created`, and `last_updated` and writes the canonical `.phase.yaml` path.

Semantic input requires `order`, `source_ids`, `depends_on`, `task_index`, `barriers`, `validation`, `completion_criteria`, `allocated_rules`, and `allocated_skills`.

Create a phase only for an actual barrier or convergence boundary. An empty `barriers` array states that no real barrier exists and supports the explicit default phase. Do not optimize task or phase cardinality or introduce speculative splits. Preserve expected total orchestration cost, authoritative production path ownership, one production owner per path, a coherent mechanical increment, and bounded repair frontier. If execution proves work materially under-decomposed, reslice only the affected region rather than repeatedly enlarge a task.

Task ordering and dependencies must agree with `task_index`. Contract-decoupled parallel work names participants, readiness evidence, release conditions, forbidden sibling validation, and a post-barrier convergence owner. Validation and completion criteria remain semantic agent decisions; schema validation only proves declared shape and bindings.
