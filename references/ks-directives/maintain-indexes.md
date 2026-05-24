# maintain-indexes

## Intent

Maintain generated index files from curated Markdown.

## Trigger phrases

- rebuild indexes
- refresh document registry
- reindex

## Use when

After durable note or open-question changes.

## Do not use when

Indexes are already current and no Markdown changed.

## Required inputs

- Project slug.
- Optional: project root path.

## Workflow

1. Run `scripts/ks.py index --project <slug>` after note changes.
2. Run `scripts/ks.py index-open-questions --project <slug>` after open-question changes.
3. Report duplicates, broken links, and missing metadata.

## Rules

- never treat indexes as source of truth
- rebuild after durable note changes
- exclude temporary handoffs unless explicitly included
- preserve stable chunk IDs when headings remain stable
- report duplicate IDs, broken links, and missing metadata
- do not hand-edit generated index files
- do not report persistence complete until index commands have run successfully
- if index rebuild fails, report the failure and do not claim the knowledge repo is updated

## Return

- commands run
- issues found (duplicates, broken links, missing metadata)
