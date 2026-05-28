---
name: wb-generate-domain-profile
description: 'Retired legacy skill. Command surface is hard-removed; migrate to wb-initialize-project.'
---

# wb-generate-domain-profile

This skill is retired and no longer an active entry point.

Deterministic migration guidance:

- Use `/wb-initialize-project` as the canonical skill.
- Use `python3 scripts/wb.py generate-project-metadata-profile --input <authority-context> --output references/bootstrap/project-domain-profile.yaml` instead of `generate-domain-profile`.
- Use `python3 scripts/wb.py merge-project-metadata-profile --current references/bootstrap/project-domain-profile.yaml --incoming <incoming-profile> --output references/bootstrap/project-domain-profile.yaml` instead of `merge-domain-profile`.
- Use `python3 scripts/wb.py validate-project-metadata-profile references/bootstrap/project-domain-profile.yaml` instead of `validate-domain-profile`.
- Legacy command invocations fail deterministically with `WB_LEGACY_COMMAND_REMOVED`.
