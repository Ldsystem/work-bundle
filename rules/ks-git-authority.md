---
id: rule-ks-git-authority
applies_when:
  - git operation is requested inside knowledge repo
enforcement: must
load: conditional
requires: []
---

# Ks Git Authority

## Purpose

- Define the enforceable contract for `rule-ks-git-authority`.

## Must

- allow scoped normal git operations only under selected knowledge repo

## Must Not

- apply knowledge-repo git authority to source repos or destructive history

## Validation

- required fields exist
- generated skills cite applicable rule

## On Violation

- Stop the operation, report the violated rule, and make the minimal correction before continuing.
