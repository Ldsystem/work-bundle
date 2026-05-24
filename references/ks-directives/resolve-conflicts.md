# resolve-conflicts

## Intent

Resolve overlap or contradiction between curated notes.

## Trigger phrases

- conflicting notes
- merge these notes
- contradictory knowledge

## Use when

Two or more notes disagree or duplicate the same concept.

## Do not use when

There is no identified conflict; use `write-knowledge` for straightforward updates.

## Required inputs

- Conflicting note paths or IDs.
- User preference when known.

## Workflow

1. Compare content and front matter.
2. Choose: `merge`, `replace`, `create-new`, or `ask-user`.
3. Do not silently overwrite contradictory `current` notes.

## Return

- decision taken or recommended
- affected paths
- whether user confirmation is required
