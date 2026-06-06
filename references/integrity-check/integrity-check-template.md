---
report_id: wbi-<YYYYMMDD-HHmm>
checker_skill: work-bundle-integrity-check
report_status: draft # draft | active | partially_fixed | closed | superseded
checked_at: <timestamp>
updated_at: <timestamp>
actor: agent | user | tool
user_bundle_root: ~/.work-bundle
source_bundle_root: <work-bundle-root>
project_registry: ~/.work-bundle/registry/projects.yaml
scope:
  - ~/.work-bundle/
  - <work-bundle-root>/
out_of_scope:
  - <project-root>/.work-bundle/ unless explicitly requested
---

# Work-Bundle Integrity Check: <check-title>

## Executive Summary

```yaml
total_files_scanned: <n>
orphan_files: <n>
broken_references: <n>
weak_rules: <n>
incomplete_skills: <n>
missing_scripts: <n>
script_responsibility_issues: <n>
compression_loading_issues: <n>
project_registry_issues: <n>
installed_vs_source_drift_issues: <n>
critical_issues: <n>
high_issues: <n>
medium_issues: <n>
low_issues: <n>
```

Summary:

```text
<Concise summary of the integrity state, highest-risk problems, and recommended repair direction.>
```

## Status History

| Timestamp | Actor | From | To | Reason | Evidence |
|---|---|---|---|---|---|

## Issue Status Summary

```yaml
open: <n>
fixed: <n>
dismissed: <n>
converted: <n>
superseded: <n>
```

## Critical Issues

| Issue ID | Issue Status | Severity | Type | Affected File / Area | Risk | Recommended Fix |
|---|---|---|---|---|---|---|

## Orphan File Findings

| Issue ID | File | Root | Issue Status | Classification | Useful | Correct Owner | Recommended Action |
|---|---|---|---|---|---:|---|---|

### WBI-<number>: <file-path>

```yaml
issue_id: WBI-<number>
issue_status: open # open | fixed | dismissed | converted | superseded
severity: critical | high | medium | low
root: user_bundle | source_bundle
file: <relative-path>
classification: useful_unreferenced | obsolete | duplicate | generated_artifact | historical_source | unknown
useful: yes | no | unknown
correct_owner: user-level-bootstrap | source-app-bootstrap | user-level-registry | source-registry | work-bundle-rules | work-bundle-skills | source-documentation | source-templates | knowledge-base | orchestration | none | unknown
recommended_action: link_from_entry | move | archive | remove | keep_ignored | compact_then_link | ask_user
repairable: true | false
repair_mode: edit_reference | move_file | archive_file | delete_file | rewrite_rule | rewrite_skill | ask_user
requires_user_decision: true | false
```

Reason:

```text
<Why this file is or is not useful, why it is currently orphaned, and why the recommended owner is correct.>
```

Recommended fix:

```text
<Concrete fix advice, including exact owner file or registry that should reference this file.>
```

Verification evidence after fix:

```text
<Fill only after the issue is fixed. Include diff summary, updated file path, or validation result.>
```

## Broken References

| Issue ID | Issue Status | Referring File | Missing Target | Severity | Recommended Fix |
|---|---|---|---|---|---|

## Rule Branch Consistency

| Issue ID | Issue Status | Rule File | Rule Status | Problems | Severity | Recommended Fix |
|---|---|---|---|---|---|---|

Check dimensions:

```text
- enable condition
- scope
- restriction strength
- must / should / may language
- forbidden behavior
- precedence
- validation requirement
- source knowledge / rationale
- registry reachability
- conflict with broader rule
```

## Skill Branch Consistency

| Issue ID | Issue Status | Skill | Skill Status | Problems | Severity | Recommended Fix |
|---|---|---|---|---|---|---|

Check dimensions:

```text
- activation condition
- do-not-use condition
- input expectations
- output locations
- workflow/reference links
- script references
- output contract
- forbidden behavior
- overlap with sibling skills
- registry reachability
```

## Script Reference Consistency

| Issue ID | Issue Status | Script | Referenced By | Script Status | Severity | Recommended Fix |
|---|---|---|---|---|---|---|

## Script Responsibility Boundaries

| Issue ID | Issue Status | Script | Responsibility Issue | Severity | Recommended Action | Recommended Fix |
|---|---|---|---|---|---|---|

Responsibility contract:

```text
Scripts may create reports, preserve WBI issue IDs, append agent-authored issues, update issue status, append status history, generate sidecar status summaries, archive reports by explicit request, and validate report-file structure.

Scripts must not own policy, validate integrity as authority, classify orphans, generate recommendations, compare installed/source drift as authority, close issues without evidence, execute project code, or crawl old Project Registry project roots by default.
```

Script boundary rule source:

```text
rules/integrity-check/index.yaml
```

## Work-Bundle Compression and Conditional Loading

| Issue ID | Issue Status | File / Rule | Compression Issue | Runtime Loading Risk | Recommended Action | Recommended Fix |
|---|---|---|---|---|---|---|

Check required targets:

```text
agent-bootstrap
project-domain-profile.yaml
repository-binding.md
roadmap files
```

Startup loading validation:

```yaml
startup_loads_minimal_bootstrap_rules: true | false | unknown
startup_loads_project_registry_metadata: true | false | unknown
startup_loads_latest_working_on_selection: true | false | unknown
startup_loads_skill_rule_registry_metadata: true | false | unknown
startup_loads_active_global_safety_boundaries: true | false | unknown
startup_loads_next_load_routing_rules: true | false | unknown
startup_loads_full_roadmap_files: true | false | unknown
startup_loads_full_project_domain_profile: true | false | unknown
startup_loads_full_repository_binding: true | false | unknown
startup_loads_all_project_notes: true | false | unknown
startup_loads_all_skill_references: true | false | unknown
startup_loads_all_rules: true | false | unknown
```

Compression principles checked:

```text
- rule isolation
- conditional loading
- skill-scope-aware rules
- lazy loading
- metadata-first registries
- compact runtime references
- separation of runtime instruction vs reference detail vs historical design
```

## Registry Consistency

| Issue ID | Issue Status | Registry | Registry Status | Problems | Severity | Recommended Fix |
|---|---|---|---|---|---|---|

Registry loading check:

```yaml
metadata_first: true | false | unknown
heavy_files_embedded_eagerly: true | false | unknown
heavy_files_referenced_lazily: true | false | unknown
startup_safe: true | false | unknown
```

## Project Registry Consistency

Project Registry path:

```text
~/.work-bundle/registry/projects.yaml
```

| Issue ID | Issue Status | Issue Type | Severity | Project | Recommended Fix |
|---|---|---|---|---|---|

Latest-working-on validation:

```yaml
latest_working_on_source: <path or field>
latest_working_on_project: <project slug>
registry_contains_project: true | false
project_status: active | inactive | archived | deprecated | current | unknown
safe_for_initiative_browsing: true | false
problem: <none or summary>
```

## Installed-vs-Source Drift

| Issue ID | Issue Status | File | Drift Type | Severity | Recommended Fix |
|---|---|---|---|---|---|

## Authority / Precedence Conflicts

| Issue ID | Issue Status | Higher Authority | Lower Authority | Conflict | Severity | Recommended Fix |
|---|---|---|---|---|---|---|

## Knowledge Base Updates Required After Fix

| Issue ID | Fixed By | Knowledge / Rule / Skill / Registry Updates Required | Verification Evidence |
|---|---|---|---|

Use this section to prevent stale instruction drift. If a fix changes durable behavior, update the corresponding source of truth, not only the broken file.

Examples:

```text
- If a workflow problem is fixed, update the workflow instruction or skill reference.
- If a rule weakness is fixed, update the rule file and registry metadata.
- If a skill explanation is fixed, update SKILL.md and related references.
- If Project Registry behavior is fixed, update the Project Registry contract and latest-working-on rule.
- If source/install structure changes, update project-structure documentation and install/bootstrap rules.
- If a compression/loading problem is fixed, update bootstrap instructions, registry metadata, skill references, workflow instructions, or source documentation so future agents know what loads by default and what loads on demand.
- If a script responsibility problem is fixed, update the script and `rules/integrity-check/*.yaml` when the responsibility contract changes.
```

## Recommended Fix Plan

Apply fixes in this order:

```text
1. Fix broken bootstrap or runtime authority references.
2. Fix Project Registry issues.
3. Fix script responsibility violations that can mutate files, execute code, close issues, crawl project roots, or own validation authority.
4. Fix context-loading/compression problems that cause token waste.
5. Fix broken references.
6. Resolve installed-vs-source drift.
7. Register useful orphan skills/rules/scripts/templates.
8. Strengthen weak rules.
9. Clarify incomplete skills.
10. Archive or remove obsolete files.
11. Normalize registry entries.
12. Re-run targeted validation.
13. Update report and issue statuses.
```

## Proposed Patch Summary

| Target File | Change Type | Related Issue IDs | Patch Summary |
|---|---|---|---|

## Open Questions

| Question ID | Related Issue IDs | Question | Blocking | Recommended Decision Owner |
|---|---|---|---:|---|

## Closure Checklist

A report can be marked `closed` only when:

```text
All issues are fixed, dismissed, converted, or superseded.
Every fixed issue has verification evidence.
Every fix that changes durable behavior has updated the corresponding knowledge/rule/skill/registry source of truth.
No fixed issue leaves stale instruction, project-structure, workflow, or registry documentation behind.
No fixed compression/loading issue leaves stale bootstrap, registry metadata, skill reference, workflow, or source documentation behind.
No fixed script responsibility issue leaves stale script behavior, script documentation, or `rules/integrity-check/*.yaml` contract behind.
No helper script can mutate files, execute project code, crawl old project roots, close issues, classify orphans, or generate integrity recommendations without explicit agent/user authority.
Startup/bootstrap no longer eagerly loads roadmap files, project-domain-profile.yaml, repository-binding.md, all project notes, all skill references, or all rules unless explicitly required.
```

## Final Validation

```yaml
validation_status: not_run | passed | failed | partial
validated_at: <timestamp>
validated_by: agent | user | tool
remaining_critical_issues: <n>
remaining_high_issues: <n>
remaining_script_responsibility_issues: <n>
remaining_compression_loading_issues: <n>
helper_script_boundaries_safe: true | false | unknown
startup_context_load_safe: true | false | unknown
report_can_close: true | false
reason_if_not_closable: <reason>
```