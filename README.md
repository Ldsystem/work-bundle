# work-bundle

Project home for migrated work-bundle skills, scripts, references, and local orchestration state.

## Structure

- `skills/` - migrated work-bundle skill packages
- `scripts/` - project-level helper scripts
- `references/` - shared design and runtime references
- `.work-bundle/` - local agent knowledge and orchestration bundle

## Skill Links

Install all work-bundle skills into the shared agent skill root:

```bash
bin/install-work-bundle-skills
```

Useful checks:

```bash
bin/work-bundle-skill list
bin/work-bundle-skill validate
bin/install-work-bundle-skills --dry-run
```
