---
name: wb-initialize-project
description: 'Initialize or repair v4 project-local work-bundle structure, bootstrap files, runtime roots, and repository boundary. Canonical work-bundle skill name: wb-initialize-project.'
---

# wb-initialize-project

Use to prepare a project for v4 work-bundle operation. Runtime outputs should be compact and machine-readable.



## Scripts

Use the unified work-bundle dispatcher:

- Inspect initialization and repository model: `python3 scripts/wb.py inspect-project-initialization <project-root>`
- Initialize or repair initialization + repository model: `python3 scripts/wb.py initialize-project <project-root>`
- Validate initialization + repository model: `python3 scripts/wb.py validate-project <project-root> --dry-run`
- Generate project metadata profile artifact: `python3 scripts/wb.py generate-project-metadata-profile --input <authority-context> --output references/bootstrap/project-domain-profile.yaml`
- Merge project metadata profile artifact: `python3 scripts/wb.py merge-project-metadata-profile --current references/bootstrap/project-domain-profile.yaml --incoming <incoming-profile> --output references/bootstrap/project-domain-profile.yaml`
- Validate project metadata profile artifact: `python3 scripts/wb.py validate-project-metadata-profile references/bootstrap/project-domain-profile.yaml`

