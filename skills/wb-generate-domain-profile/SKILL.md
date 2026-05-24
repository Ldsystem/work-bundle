---
name: wb-generate-domain-profile
description: 'Create, refresh, repair, or validate compact project-domain-profile.yaml from authority context. Work-bundle scoped as wb-generate-domain-profile.'
---

# wb-generate-domain-profile

Produces compact YAML under `references/bootstrap/project-domain-profile.yaml`. It must not browse `.work-bundle/knowledge/` directly and must not use candidate/background/blocked context as authority facts.

## Scripts

Use the unified work-bundle dispatcher:

- Generate/extract profile: `python3 scripts/wb.py generate-domain-profile --input <authority-context> --output references/bootstrap/project-domain-profile.yaml`
- Merge profile: `python3 scripts/wb.py merge-domain-profile --current references/bootstrap/project-domain-profile.yaml --incoming <incoming-profile> --output references/bootstrap/project-domain-profile.yaml`
- Validate profile: `python3 scripts/wb.py validate-domain-profile references/bootstrap/project-domain-profile.yaml`
