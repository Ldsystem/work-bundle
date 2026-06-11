---
id: wb-script-instruction
applies_when:
  - user requests creation of a new work-bundle script
  - user requests update of scripts under scripts/
  - agent maintains script dispatchers, doctors, or project initialization scripts
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

## Must Not

- Do not make scripts decide whether a specification, plan, rule, workflow, or architecture is semantically correct.
- Do not let skill-specific scripts own generic project lifecycle behavior.
- Do not silently delete user files.
- Do not overwrite non-empty files without explicit force behavior.

## Validation

- Inspect changed scripts for semantic judgment or cross-skill ownership.
- Verify project lifecycle behavior routes through `scripts/work-bundle/project.py`.
- Verify script commands report mechanical diagnostics and remain idempotent.

## On Violation

Stop script migration or script creation, report the boundary violation, and move the behavior to the proper owning module, skill, rule, or reference.
