# Executor Result v1

`executor-result-v1` is the canonical factual continuation record created after executing one plan task. Its machine structure, identity, bindings, location, lifecycle, and index projection are owned by `artifact-family-catalog-v4.yaml` and `executor-result-v1.schema.json`.

The agent-authored semantic content records implemented scope, changed paths, focused validation observations, unresolved product blockers, task fit, repository and CodeGraph observations, delegation provenance, and task-local knowledge disposition.

An executor result never issues a product verdict. It contains no implementation-review decision, accepted-result decision, final-audit conclusion, repair recommendation, or knowledge-write authorization. A distinct reviewer compares the exact frozen implementation directly with the verified specification and plan.

Before creation, active repair, or transition, validate the entire schema, identity, plan/task bindings, canonical path, and requested lifecycle operation. Create or repair the active artifact atomically at the same canonical identity; allocate a new identity only for a genuinely distinct result, and never rewrite a transitioned result. After the write, perform only lightweight integrity checks and rebuild the disposable index projection. If an index update fails after the canonical write, report the partial effect truthfully.

Missing or defective executor-result structure blocks continuation that requires that artifact. It does not veto direct product review when the exact implementation candidate, verified specification/plan, and claim-relevant observations are independently available.

Historical handoffs, embedded legacy statuses, filename inference, lifecycle override sidecars, and fallback indexes are unsupported. Current adapters neither inspect nor migrate their instances.
