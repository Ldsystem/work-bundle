# Workspace integration

- Keep toolkit/source `scripts/` distinct from `$workspace_root/script/`. Permit workspace utilities in both single- and multi-repository modes; preserve existing tracking policy when workspace and source overlap.
- Before creating or running a reusable workspace utility, inspect `$workspace_root/script/index.yaml`. Inspect the referenced utility before first use or after its digest changes. Discovery and validation do not authorize execution.
- Register reusable utilities in that index in the same workflow using its v1 required fields, operation class, and declared credential IDs. Preserve existing entries and user files during initialization and migration.
- Validate the index structurally: complete fields, unique IDs, invocation/dependency shapes, valid operations, paths beneath `script/`, no symlinked utilities, stale paths, orphan utilities, or undeclared credential use. Do not run utilities during index validation.
- Keep credentials, private data, logs, caches, and generated runtime output out of tracked utility state. Use the established credential-use path rather than embedding secrets.
- Route project registration, metadata initialization, and initialization file creation through the existing `scripts/work-bundle/project.py` owner. A skill-specific helper must not introduce a competing generic lifecycle owner.
- Keep doctor results factual and mechanical. A diagnosed structure or wiring fault does not itself authorize repair or determine project correctness.
