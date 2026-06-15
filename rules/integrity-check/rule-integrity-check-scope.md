---
id: rule-integrity-check-scope
applies_when:
  - wb-integrity-check runs
enforcement: must
load: conditional
requires: []
---

# Integrity Check Scope

## Purpose

- Define the enforceable contract for `rule-integrity-check-scope`.

## Must

- validate only system roots by default: ~/.work-bundle and <work-bundle-root>
- treat project-local .work-bundle directories as out-of-scope unless explicitly requested
- validate project registry at ~/.work-bundle/registry/projects.yaml as critical authority

## Must Not

- default crawl of project-root .work-bundle
- proactive scan of old project roots from project registry

## Validation

- integrity report scope section records default roots and explicit out-of-scope roots
- critical issue is produced when project registry is missing or malformed

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
