---
name: dev-resolve-blocking-fact
description: Resolve a workspace blocking fact against actual implementation, or choose a scoped repair when source and behavior reveal a concrete defect.
---

# Resolve Blocking Fact

Make an agent-owned semantic diagnosis, not another evidence-completeness review.

## Establish the implementation fact

Read the selected blocker and intended specification/plan, then inspect the relevant current source, Git diff, designed files, tests, and observable behavior. Explain whether the implementation fulfills the intended requirements. Passing tests alone do not establish this; an untested requirement or incorrect test oracle may expose a real gap.

MUST NOT use evidence-version differences, missing receipts/handoffs/stored execution or review records, historical reviewer chains, or other execution-evidence bookkeeping gaps as reasons to reject implementation, retain its blocker, or demand repair. MUST NOT regenerate those artifacts, replay execution, or request a confirming review for this diagnosis. Do not invent historical acceptance.

This exclusion does not excuse broken product behavior: if the specified product itself processes evidence, a demonstrated failure of that feature is still an implementation defect.

Do not create or use diagnostic scripts, semantic scoring, or script-guarded acceptance for this skill. Relevant unit tests and direct reproductions supply facts; the agent makes the judgment. If behavior is unknown, name the precise product question and obtain the smallest useful inspection/reproduction—not a paperwork audit or unrelated suite rerun.

## Act on the judgment

- **Implemented and functioning:** record a new semantic pass for the exact inspected worktree/source, resolve only the selected blocker, accept that worktree as the current semantic implementation outcome, and close this case. Preserve historical reviews and closure outcomes unchanged. Missing native publication is not a veto and must not be represented as native acceptance.
- **Concrete implementation defect:** complete/update the blocking specification with the failed requirement, expected/actual behavior, first owner, and bounded repair scope. Use `dev-create-task-plan` for a bounded mechanical repair; use full orchestration for cross-component, architectural, migration, or dependency-barrier work. Repair the implementation, not its historical envelope. Reassess only affected behavior afterward.

Keep read-only requests read-only. Resolution/repair requires authority for the selected target; an explicit request to resolve it under this skill authorizes the new semantic disposition, not unrelated mutations. For metadata changes or repair admission, read [metadata-resolution.md](references/metadata-resolution.md). Helpers may only apply an already-made decision. Do not remove unrelated blockers, disable admission globally, reopen an exhausted origin flow, or infer permission to push, merge, delete worktrees, or install software.

## Return

Keep the result concise: selected blocker; exact inspected source/worktree (including relevant dirty diff); requirement-to-behavior findings; new semantic outcome; targeted mutation or repair route; any unresolved product question. This is a current judgment, not a native review receipt, historical reclassification, or a new required evidence schema.
