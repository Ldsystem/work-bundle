---
name: wb-generate-domain-profile
description: 'Create, refresh, repair, or validate compact project-domain-profile.yaml from authority context. Work-bundle scoped as wb-generate-domain-profile.'
---

# wb-generate-domain-profile

Produces compact YAML under `.work-bundle/orchestration/bootstrap/project-domain-profile.yaml`. It must not browse `.work-bundle/knowledge/` directly and must not use candidate/background/blocked context as authority facts.
