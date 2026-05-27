# Work-Bundle Integrity Check: <check-title>

## Metadata

```yaml
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
```

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
| <timestamp> | agent | - | draft | Initial report generated. | <report path> |

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
| WBI-001 | open | critical | <type> | <path or area> | <risk> | <fix> |

## Orphan File Findings

| Issue ID | File | Root | Issue Status | Classification | Useful | Correct Owner | Recommended Action |
|---|---|---|---|---|---:|---|---|
| WBI-<number> | <path> | user_bundle \| source_bundle | open | useful_unreferenced \| obsolete \| duplicate \| generated_artifact \| historical_source \| unknown | yes \| no \| unknown | <owner> | <action> |

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
| WBI-<number> | open | <path> | <missing path> | critical \| high \| medium \| low | <fix> |

## Rule Branch Consistency

| Issue ID | Issue Status | Rule File | Rule Status | Problems | Severity | Recommended Fix |
|---|---|---|---|---|---|---|
| WBI-<number> | open | <path> | active \| draft \| deprecated \| unknown | <problem summary> | high | <fix> |

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
| WBI-<number> | open | <skill-name or path> | active \| draft \| deprecated \| unknown | <problem summary> | high | <fix> |

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
| WBI-<number> | open | <script path> | <referring file> | exists \| missing \| wrong_path \| undocumented | high | <fix> |

## Script Responsibility Boundaries

| Issue ID | Issue Status | Script | Responsibility Issue | Severity | Recommended Action | Recommended Fix |
|---|---|---|---|---|---|---|
| WBI-<number> | open | <script path> | owns_policy \| validates_integrity_as_authority \| classifies_orphans \| generates_recommendations \| auto_repairs_without_request \| closes_without_evidence \| executes_project_code \| crawls_project_roots \| mutates_without_explicit_mode \| missing_report_status_support \| missing_issue_status_support | critical \| high \| medium \| low | restrict_to_report_helper \| remove_validator_authority \| require_agent_authored_findings \| add_explicit_repair_mode \| add_evidence_requirement \| remove_execution_path \| add_scope_guard \| update_script_design_reference | <fix> |

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
| WBI-<number> | open | <path> | eager_global_load \| missing_enable_condition \| global_rule_should_be_skill_scoped \| heavy_file_loaded_at_startup \| roadmap_loaded_too_early \| profile_loaded_too_early \| repository_binding_loaded_too_early \| metadata_missing \| split_recommended \| compact_reference_needed | none \| low \| medium \| high | isolate_rule \| add_enable_condition \| move_to_skill_scope \| add_lazy_load_boundary \| replace_with_metadata_stub \| split_file \| create_compact_reference \| archive_verbose_source | <fix> |

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
| WBI-<number> | open | <registry path> | valid \| malformed \| stale \| missing | <problem summary> | high | <fix> |

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
| WBI-<number> | open | missing_registry \| invalid_yaml \| missing_project_id \| duplicate_project_id \| missing_project_root \| broken_project_root \| invalid_status \| stale_latest_working_on \| archived_selected \| workspace_boundary_violation \| project_bundle_path_mismatch \| initiative_scope_violation | critical \| high \| medium \| low | <project slug or -> | <fix> |

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
| WBI-<number> | open | <path> | missing_install \| stale_install \| runtime_only \| source_only_unregistered \| shadowed_definition \| deprecated_active \| path_mismatch | high | <fix> |

## Authority / Precedence Conflicts

| Issue ID | Issue Status | Higher Authority | Lower Authority | Conflict | Severity | Recommended Fix |
|---|---|---|---|---|---|---|
| WBI-<number> | open | <path> | <path> | <conflict summary> | critical \| high | <fix> |

## Knowledge Base Updates Required After Fix

| Issue ID | Fixed By | Knowledge / Rule / Skill / Registry Updates Required | Verification Evidence |
|---|---|---|---|
| WBI-<number> | <fix summary or artifact> | <source-of-truth updates required> | <evidence after fix> |

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
| <path> | edit \| move \| archive \| remove \| create \| split \| compact \| add_lazy_load_boundary \| add_enable_condition | WBI-<number> | <summary> |

## Open Questions

| Question ID | Related Issue IDs | Question | Blocking | Recommended Decision Owner |
|---|---|---|---:|---|
| OQ-WBI-<number> | WBI-<number> | <question> | yes \| no | user \| maintainer \| agent |

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