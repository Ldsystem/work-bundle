---
id: wb-script-instruction
applies_when:
  - user requests creation of a new work-bundle script
  - user requests update of scripts under scripts/
  - agent maintains script dispatchers, doctors, or project initialization scripts
  - user or workflow creates, updates, discovers, or runs a reusable workspace utility under script/
  - a workspace utility is declared in script/index.yaml
enforcement: must
load: conditional
requires: []
---

# Script Instruction

## Purpose

Keep scripts mechanical and bounded so skills, rules, lifecycle design, architecture judgment, and project semantics remain agent-owned or reference-owned.

## Must

- Keep dispatchers limited to argument parsing, command routing, exit codes, and help.
- Keep doctors limited to file presence, directory structure, schema shape, script wiring, and mechanical diagnostics.
- Keep `scripts/work-bundle/project.py` as the canonical owner for project registration, project metadata initialization, and `/wb-initialize-project` file creation.
- Keep commands idempotent and preserve user-authored content.
- Read domain catalogs from references instead of redefining them inside scripts.
- Treat toolkit/source `scripts/` and workspace utility `$workspace_root/script/` as distinct roots with distinct ownership.
- Inspect `$workspace_root/script/index.yaml` before creating or running a reusable workspace utility and inspect the referenced file before first use or after its digest changes.
- Register every reusable workspace utility in `script/index.yaml` in the same workflow with the v1 contract fields, including operation class and declared credential IDs.
- Reject duplicate IDs, stale or escaping paths, orphan reusable utilities, and undeclared credential use mechanically; do not execute a utility as part of validation.
- Parse `script/index.yaml` structurally and reject symlinked utilities, invalid operation values, malformed invocation/dependency shapes, and entries missing the complete v1 required-field set.
- Preserve existing index entries and user utility files during initialize, doctor, and migration.

## Must Not

- Do not make scripts decide whether a specification, plan, rule, workflow, or architecture is semantically correct.
- Do not let skill-specific scripts own generic project lifecycle behavior.
- Do not silently delete user files.
- Do not overwrite non-empty files without explicit force behavior.
- Do not treat index discovery as execution authority or auto-run discovered utilities.
- Do not place credentials, raw private data, chat logs, transient outputs, caches, or generated artifacts in tracked workspace utility state.
- Do not reinterpret toolkit/source helpers under plural `scripts/` as workspace utilities.

## Validation

- Inspect changed scripts for semantic judgment or cross-skill ownership.
- Verify project lifecycle behavior routes through `scripts/work-bundle/project.py`.
- Verify script commands report mechanical diagnostics and remain idempotent.
- Verify every indexed workspace utility path resolves beneath `$workspace_root/script/`, every reusable utility is indexed, and index validation performs no execution.
- Verify mutation, network, credential, and destructive behavior still uses task authority, operation policy, and confirmation gates.

## On Violation

Stop script migration or script creation, report the boundary violation, and move the behavior to the proper owning module, skill, rule, or reference.
