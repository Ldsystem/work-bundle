---
id: rule-work-bundle-repository-boundary
applies_when:
  - v4 work-bundle operation requires repository-boundary
enforcement: must
load: conditional
requires: []
---

# Repository Boundary

## Purpose

Separate durable product source from workspace execution evidence and bind historical checks to immutable repository identities.

## Must

- Follow source authority and resolve the selected repository before inspection, mutation, validation, or commit.
- Keep issue-run artifacts, execution manifests, task packets, and transient review evidence in the workspace control plane, never in product source.
- Treat historical cleanup as removal or generic promotion of proven legacy residue, not as authority to create new issue-named files or maintain a historical manifest as a live inventory.
- Bind historical validation to an exact baseline and endpoint commit/tree pair and require ancestry when the contract depends on a repository interval.
- Reject an open-ended live `HEAD` endpoint for reusable historical validation; current-head checks must state that current binding explicitly and remain non-reusable across source changes.
- Keep runtime files compact.

## Must Not

- Do not generate `.mdc` files.
- Do not include raw logs or secrets.
- Do not store issue-run artifacts under source `evals/`, source tests, or another product directory.
- Do not mutate historical accepted evidence merely because later repository files exist.

## Validation

- Required fields exist and source/runtime placement follows the repository boundary.
- Historical checks name the exact baseline and endpoint; reusable checks contain no live `HEAD` endpoint.
- Source contains no newly created issue-run artifacts.

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
