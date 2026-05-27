# work-bundle-integrity-check

Use this skill to audit the `work-bundle` system itself, not individual project knowledge bases by default.

Runtime enforcement rules are extracted under `rules/integrity-check/` and indexed by `rules/integrity-check/index.yaml`.

Primary goals:

```text
- detect orphan files, broken references, stale registries, incomplete skills, weak rules, invalid scripts
- validate Project Registry and latest-working-on safety
- detect installed-vs-source drift between `~/.work-bundle/` and `<work-bundle-root>/`
- detect excessive context loading and recommend work-bundle compression
- validate integrity-check helper scripts stay within report/status/file-management responsibilities and do not become policy validators
- write lifecycle-tracked integrity reports back into the work-bundle knowledge base
```

## Scope

Default roots:

```text
~/.work-bundle/
<work-bundle-root>/
```

Required runtime authority:

```text
~/.work-bundle/registry/projects.yaml
```

Out of scope by default:

```text
<project-root>/.work-bundle/
```

Do not validate individual project-scoped `.work-bundle/` directories unless the user explicitly asks. Project bundles may be sampled only to verify that global work-bundle rules describe a valid project-level installation contract.

## Output

Write reports to:

```text
~/.work-bundle/knowledge/integrity-checks/<YYYYMMDD-HHmm>-work-bundle-integrity-check.md
```

Use `integrity-check-template.md` as the report template.

Do not overwrite previous reports.

## Authority Order

Treat these as authority layers, highest first:

```text
1. User-level bootstrap/runtime loader in `~/.work-bundle/`
2. Project Registry: `~/.work-bundle/registry/projects.yaml`
3. Source bootstrap rules: `<work-bundle-root>/app-bootstrap/`
4. User-level registries: `~/.work-bundle/registries/`
5. Source registries: `<work-bundle-root>/registries/`
6. Global work-bundle rules
7. Work-bundle skill registry
8. Individual skill `SKILL.md` files
9. Skill reference files
10. Skill scripts
11. Knowledge notes and generated reports
```

A file is reachable only if referenced directly or indirectly from an accepted authority entry point for its root.

Runtime files under `~/.work-bundle/` must be reachable from runtime loader, Project Registry, active registry, active rule, active skill, or latest-working-on contract.

Source files under `<work-bundle-root>/` must have a clear source owner: registry, manifest, docs index, template index, skill, rule, or script reference.

## Lifecycle

Report status:

```text
draft | active | partially_fixed | closed | superseded
```

Issue status:

```text
open | fixed | dismissed | converted | superseded
```

A report may be closed only when every issue is:

```text
fixed | dismissed | converted | superseded
```

Every transition must record timestamp, actor, previous status, new status, reason, and evidence.

## Core Checks

For every discovered file, answer:

```text
Is it reachable?
Is it useful?
Which authority should own/reference it?
Should it be removed, archived, ignored, compacted, split, or lazy-loaded?
Does it force unnecessary context loading?
What exact fix is recommended?
What source-of-truth files must be updated after the fix?
Does any helper script exceed its allowed responsibility?
Does any script attempt to own policy, validation judgment, orphan classification, compression judgment, or repair authority?
```

## Workflow

### 1. Inventory

Build an inventory for both default roots when available.

Record:

```yaml
root: user_bundle | source_bundle
path: <relative-path>
type: rule | skill | script | registry | knowledge | orchestration | documentation | template | unknown
install_state: installed_only | source_only | mirrored | generated | unknown
runtime_role: active_runtime | source_definition | packaging_asset | documentation | generated_report | archive | unknown
```

Classify by path and content. Do not rely only on extension.

### 2. Reference Graph

Detect references from:

```text
markdown links
plain paths
script paths
skill references
registry entries
Project Registry entries
front matter references
```

Normalize paths. Report broken references separately from orphan files.

### 3. Orphan Files

A file is orphaned when it is not reachable from any accepted authority entry point for its root.

Classify:

```yaml
orphan_status: useful_unreferenced | obsolete | duplicate | generated_artifact | historical_source | unknown
recommended_action: link_from_entry | move | archive | remove | keep_ignored | compact_then_link | ask_user
```

Do not treat unreferenced files as removable by default.

### 4. Ownership

Use one primary owner per useful orphan:

```text
user-level bootstrap/runtime loader
source app-bootstrap rule
user-level registry
source registry
global work-bundle rule
work-bundle skill
source documentation
source template
knowledge base
orchestration artifact
```

Fix advice must state:

```text
Add reference from <owner-file> to <target-file> because <reason>.
```

### 5. Rule Branches

For every rule, verify:

```text
clear enable/load condition
clear scope
must/should/may restriction strength
forbidden behavior
precedence rule
validation requirement
source rationale when applicable
registry/bootstrap reachability
no conflict with higher authority
no duplicate rule without purpose
```

Rules that only apply to one skill must be skill-scoped, not globally loaded.

### 6. Skill Branches

For every skill, verify:

```text
concise `SKILL.md` or equivalent entry
activation condition
do-not-use condition
input expectations
output locations
workflow/reference links
script references
output contract
forbidden behavior
no hidden/unregistered dependency
no responsibility overlap with sibling skills
```

### 7. Script References

For every referenced script, verify:

```text
script exists
path resolves from referring file
purpose is documented
invocation role is obvious
script is not orphaned if executable
```

Do not execute scripts unless explicitly requested.

### 8. Script Responsibility Boundaries

Validate helper scripts against `rules/integrity-check/index.yaml`.

Core rule:

```text
Scripts support report creation, issue bookkeeping, status updates, sidecar summaries, report archiving, and report-file structure checks only.
```

Scripts must not perform or replace the integrity check.

Allowed script responsibilities:

```text
create a new report from `integrity-check-template.md`
allocate or preserve stable WBI issue IDs
append agent-authored issues to report sections
update issue status after agent/user verification
append status history
normalize report metadata/front matter
generate machine-readable sidecar status summaries
archive generated reports when explicitly requested
validate report-file structure only
```

Forbidden script responsibilities:

```text
own policy or interpretation
validate rule strength as authority
validate skill completeness as authority
validate registries as authority
validate Project Registry correctness as authority
build a reference graph and treat it as final judgment
classify orphan files as useful/removable by itself
generate compression/loading recommendations without agent-authored findings
compare installed/source drift as authority
generate recommendations without agent-authored findings
close issues without agent/user-provided evidence
execute project scripts or arbitrary shell commands
crawl old Project Registry project roots by default
```

Classify script responsibility issues:

```yaml
script_responsibility_issue: owns_policy | validates_integrity_as_authority | classifies_orphans | generates_recommendations | auto_repairs_without_request | closes_without_evidence | executes_project_code | crawls_project_roots | mutates_without_explicit_mode | missing_report_status_support | missing_issue_status_support
recommended_action: restrict_to_report_helper | remove_validator_authority | require_agent_authored_findings | add_explicit_repair_mode | add_evidence_requirement | remove_execution_path | add_scope_guard | update_script_design_reference
severity: critical | high | medium | low
```

Severity guidance:

```text
critical:
  Script can mutate files, execute code, close issues, or crawl project roots without explicit request.

high:
  Script owns policy, validates integrity as authority, classifies orphans, or generates recommendations independently.

medium:
  Script lacks report lifecycle/status support, evidence requirement, or explicit repair-mode boundary.

low:
  Script has naming, metadata, or documentation mismatch with `rules/integrity-check/index.yaml`.
```

Fix advice must update both the script and `rules/integrity-check/*.yaml` when the responsibility contract changes.

### 9. Project Registry

Validate directly:

```text
~/.work-bundle/registry/projects.yaml
```

Missing, unreadable, malformed, or bootstrap-unreachable Project Registry is `critical`.

Verify:

```text
valid YAML
stable project id/slug/name
unique active project identifiers
resolvable project root for active projects
clear status: active | inactive | archived | deprecated | current
latest-working-on references an existing registry entry
archived/deprecated project is not latest-working-on unless explicitly allowed
project root respects workspace boundaries unless marked external
project-level `.work-bundle/` path matches project root when recorded
old projects are not browsed proactively unless selected or explicitly requested
```

Issue types:

```text
missing_registry | invalid_yaml | missing_project_id | duplicate_project_id | missing_project_root | broken_project_root | invalid_status | stale_latest_working_on | archived_selected | workspace_boundary_violation | project_bundle_path_mismatch | initiative_scope_violation
```

### 10. Registry Consistency

Check all registries under both roots.

Verify:

```text
entries point to existing files
registered skills/rules/scripts exist
disabled/deprecated entries are marked
paths are normalized
archived files are not active
registry metadata is compact enough for startup use
heavy files are referenced lazily, not embedded eagerly
```

### 11. Installed-vs-Source Drift

When both roots exist, compare installed runtime files with source definitions.

Classify drift:

```text
missing_install | stale_install | runtime_only | source_only_unregistered | shadowed_definition | deprecated_active | path_mismatch
```

Report drift separately from ordinary orphan files.

### 12. Work-Bundle Compression

Detect token-waste caused by excessive eager loading.

Core rule:

```text
Agents must not be forced to understand the whole work-bundle or the whole latest-working-on project at startup.
```

Startup may load only:

```text
minimal bootstrap rules
Project Registry metadata
latest-working-on selection
skill/rule registry metadata
active global safety boundaries
next-load routing rules
```

Startup must not load:

```text
full roadmap files
full project-domain-profile.yaml
full repository-binding.md
all project notes
all skill references
all workflow documents
all rules regardless of applicability
historical plans, handoffs, or archived designs
```

Check:

```text
rule isolation
conditional loading
skill-scope-aware rules
lazy loading
metadata-first registries
compact runtime references
separation of runtime instruction vs reference detail vs historical design
```

Special restrictions:

```text
agent-bootstrap:
  Load only bootstrap boundary, registry metadata, latest-working-on metadata, and next-step routing rules.

project-domain-profile.yaml:
  Load only after project selection and only when the task needs domain assumptions, terminology, architecture constraints, or domain-specific rules.

repository-binding.md:
  Load only for repository/file-path mapping, coding-agent handoff, code search, or artifact-to-repo binding.

roadmap files:
  Load only for roadmap planning, backlog review, implementation ordering, or roadmap consistency checks.
```

Classify compression findings:

```yaml
compression_issue: eager_global_load | missing_enable_condition | global_rule_should_be_skill_scoped | heavy_file_loaded_at_startup | roadmap_loaded_too_early | profile_loaded_too_early | repository_binding_loaded_too_early | metadata_missing | split_recommended | compact_reference_needed
recommended_action: isolate_rule | add_enable_condition | move_to_skill_scope | add_lazy_load_boundary | replace_with_metadata_stub | split_file | create_compact_reference | archive_verbose_source
runtime_loading_risk: none | low | medium | high
```

### 13. Write-Back and Closure

The report must be written as durable work-bundle knowledge.

Do not mutate source rules, skills, registries, scripts, or compact files unless explicitly asked.

When an issue is fixed, update both:

```text
1. issue/report status and verification evidence
2. affected source of truth: instruction, project-structure doc, workflow file, rule, skill, registry, Project Registry contract, bootstrap rule, or loading rule
```

If a compression/loading issue is fixed, update the affected bootstrap instruction, registry metadata, skill reference, workflow instruction, or source documentation so future agents know what loads by default and what loads on demand.

## Severity

```text
critical:
  broken authority path, missing bootstrap rule, missing/malformed Project Registry, stale latest-working-on, missing required skill file, unsafe authority contradiction, or helper script that can mutate files/execute code/close issues/crawl project roots without explicit request

high:
  useful orphan rule/skill/script, broken script reference, weak global restriction, registry inconsistency, eager loading that forces large unnecessary context, or helper script that owns policy/validation/orphan/compression judgment

medium:
  incomplete skill explanation, missing rationale, duplicate rule, unclear ownership, missing load condition, rule that should be skill-scoped but is not in a high-cost path, or helper script missing report lifecycle/status/evidence boundaries

low:
  formatting issue, naming inconsistency, minor stale reference, generated artifact in acceptable but suboptimal location
```

## Fix Advice Rules

Advice must be concrete and local.

Good:

```text
Move `project-domain-profile.yaml` out of startup load. Add registry metadata with `load_when: project_selected && task_requires_domain_context`, and update `agent-bootstrap` to load only metadata during startup.
```

Bad:

```text
Make bootstrap smaller.
```

Good:

```text
Remove orphan-classification authority from `scripts/integrity_check_report.py`; allow it only to append agent-authored orphan findings and preserve WBI IDs. Update `rules/integrity-check/*.yaml` to keep script responsibility limited to report/status bookkeeping.
```

Bad:

```text
Make the script safer.
```

Good:

```text
Add `rules/workspace-boundary.md` to `registries/rule-registry.md` under global rules because it constrains all agent file access.
```

Bad:

```text
Improve organization.
```

## Constraints

```text
Do not treat all unreferenced files as removable.
Do not promote generated artifacts into authority paths unless they define accepted rules, skills, bootstrap behavior, or runtime compact instructions.
Do not rewrite files unless explicitly asked.
Do not execute scripts unless explicitly asked.
Do not treat `<project-root>/.work-bundle/` as the primary validation target.
Do not validate individual project knowledge bases unless explicitly asked.
Do not inspect old project directories from the Project Registry unless explicitly asked.
For initiative checks, inspect only system roots, Project Registry metadata, and latest-working-on selection.
```

## Completion Criteria

```text
Inventory built for `~/.work-bundle/` and `<work-bundle-root>/` when available.
Reference graph built for both roots.
Orphans classified with usefulness and owner recommendations.
Rules checked for restriction strength, scope, load conditions, and discoverability.
Skills checked for explanation quality, output contracts, and script correctness.
Scripts checked for reference correctness.
Helper scripts checked against `rules/integrity-check/index.yaml` for responsibility boundaries, explicit repair mode, evidence requirements, and no policy/validation authority.
Registries checked for active/stale/broken entries and metadata-first loading.
Project Registry validated for schema, project paths, statuses, latest-working-on, and initiative scope safety.
Installed-vs-source drift classified.
Compression/loading boundaries checked, including rule isolation, conditional loading, skill-scope-aware rules, and lazy-load restrictions for agent-bootstrap, project-domain-profile.yaml, repository-binding.md, and roadmap files.
Integrity report written to `~/.work-bundle/knowledge/integrity-checks/` using `integrity-check-template.md`.
If updating after fixes, every fixed issue links to verification evidence and source-of-truth updates.
Final response summarizes only critical/high findings and gives the report path.
```