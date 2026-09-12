# Targeted metadata changes

Use the containing workspace's `.work-bundle/project.yaml`, not a member's private metadata. These are mechanical edits after the agent's judgment and target authorization; no helper establishes semantic sufficiency. No special resolution CLI is required.

## Resolve a passing target

1. Re-read the exact selected entry in `orchestration_control.blockers`; preserve a recoverable copy before mutation. If the target is ambiguous or changed concurrently, resolve that mutation ambiguity without reopening the semantic diagnosis.
2. Set only that entry's `status` to `resolved` and append a concise `resolution` describing the new agent judgment and its operator authority. Include the current reviewed repository commit/tree and relevant diff identity for uncommitted changes. Keep device-local worktree paths in the response/runtime note, not portable metadata. Retain the original reason, baseline, specification reference, and origin flow.
3. Preserve unrelated blockers, unknown fields, historical reviews, closed-flow outcomes, and round counters. Read back the target and diff to confirm only intended fields changed. Report semantic worktree acceptance; do not claim native acceptance or silently archive unrelated artifacts.

A resolution is a later fact, not a rewrite of why the earlier flow closed with blockers. Record enough to identify the judgment honestly; do not add an evidence-envelope validator or make this suggested record shape an acceptance gate.

## Admit a concrete repair

Diagnosis itself is read-only and needs no ordinary execution admission. Once an actual defect is established, choose the repair path by its scope, not by the old flow's version or missing receipts.

For an authorized repair while the blocker remains active, preserve an exact metadata backup and use the existing `orchestration_control.implementation_exemptions` list. Add only the selected `blocker_id`, the actual repair `flow_id`, `status: active`, and the scoped operator authority. Keep the blocker active until its implementation is resolved. Use the same flow ID at ordinary dispatch; do not relabel execution as diagnosis/finalization. An exhausted origin flow stays exhausted—an explicitly authorized remediation flow is distinct, not a reset of its counter.

Unrelated active blockers still apply. If one prevents dispatch, report that specific authority restriction; do not clear it or broaden the exemption. Missing historical receipts for the selected target are never a reason to create more repair work.

On abort, restore the backed-up selected blocker and retire only the owned exemption, preserving newer unrelated metadata. On successful repair, retire the exemption and apply the new semantic resolution; if a restoration helper is used, restore first so it cannot overwrite that new resolution. Do not restore the whole metadata file over concurrent changes.

If a helper refuses solely because it wants historical execution evidence, do not manufacture that evidence or repeat a review. Apply the authorized targeted metadata edit directly while preserving the existing shape and unrelated fields. Stop only for a concrete unresolved product question, target ambiguity, or missing mutation authority.
