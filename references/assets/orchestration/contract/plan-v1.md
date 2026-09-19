# Root Plan v1 semantic contract

The current `root-plan` family is schema-owned YAML. Supply semantic YAML to `write-plan`; do not add front matter, choose a filename, or repeat injected `artifact_type`, `schema_version`, `id`, `goal`, `purpose`, `component`, `version`, `source_spec_id`, `status`, `date_created`, or `last_updated` fields.

The semantic input requires `source_coverage`, `authority`, `strategy`, `phase_index`, `dependency_graph`, `risks`, `validation_strategy`, `completion_criteria`, `knowledge_base_update`, `semantic_loop`, and `execution_workspace`. Each coverage row names a stable source ID, obligation kind, non-empty phase/task ownership, and validation IDs when validation-bearing. Cite the verified specification by `source_spec_id`; presentation paths such as `.work-bundle/orchestration/spec/active/...` are not authority.

Decompose without optimizing task or phase cardinality. Bound expected total orchestration cost at concrete independently owned production, dependency, validation, review, and repair seams. Every authoritative production path needs a production owner; reject helper-only allocation. Keep a coherent mechanical increment with one owner, oracle, and repair frontier together. Split independently owned entry points only when current repository evidence proves distinct seams. Create a phase only for an actual barrier or convergence boundary; reject speculative splits. When a task is materially under-decomposed, return to the plan and reslice only the affected region; do not repeatedly enlarge it.

Assign parallel tasks only when dependencies are satisfied and write scopes are disjoint. Unsafe parallelization is explicitly blocked by dependency or scope evidence. Contract-decoupled work names a common contract group, barrier participants, readiness, release condition, convergence owner, and post-barrier convergence task.

Every task declares `evidence_capability`. Use `mapped` with a lightest-capable task-local oracle for validation-bearing obligations, or `no_validation_bearing_obligation` with a concrete reason.

Run canonical static task admission before semantic review. Structural success cannot establish source-ID coverage, appropriate decomposition, capable validation, or executability. A distinct reviewer compares the stored tree directly with the verified specification and current source evidence and issues `accept`, `repair`, or `blocked`.

The canonical semantic plan projection is `canonical-yaml-plan-tree-v1`. A status-only or append-only evidence change declared by the schema is excluded at the exact top-level control locations; all other semantics remain identity-bearing. Current plan and specification revisions do not consume post-execution review rounds.
