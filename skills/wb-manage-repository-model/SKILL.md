---
name: wb-manage-repository-model
description: 'Retired legacy skill. Command surface is hard-removed; migrate to wb-initialize-project.'
---

# wb-manage-repository-model

This skill is retired and no longer an active entry point.

Deterministic migration guidance:

- Use `/wb-initialize-project` as the canonical skill.
- Use `python3 scripts/wb.py inspect-project-initialization <project-root>` instead of `inspect-repository-model`.
- Use `python3 scripts/wb.py initialize-project <project-root>` instead of `repository-model`.
- Use `python3 scripts/wb.py validate-project <project-root> --dry-run` instead of `validate-repository-model`.
- Legacy command invocations fail deterministically with `WB_LEGACY_COMMAND_REMOVED`.
