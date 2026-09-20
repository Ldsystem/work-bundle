---
name: wb-create-skill
description: Use WHEN creating or changing a built-in WorkBundle skill so its trigger, observable behavior, pressure scenarios, mechanical contracts, and registration are validated before installation.
---

# Create Skill

Build or repair the current skill in place. Preserve the user's purpose and authorization, pressure-test behavior when judgment is material, and make the smallest general improvement.

This WorkBundle workflow specializes the system skill-creator principles of user-intent preservation, proportional specificity, progressive disclosure, and observable behavior; it does not duplicate the general skill-authoring manual.

## Workflow

1. Define the trigger and observable behavior. Keep all WHEN-to-use guidance in the front-matter description.
2. Inspect the current skill and only the supporting resources or callers needed for the requested change. Treat the current implementation as evidence, not authority; correct it when it conflicts with accepted purpose.
3. For a material behavior change, write realistic pressure evals before changing the skill. Store scenarios under `references/evals/<area>/evals.json`; this is scenario storage, not proof that an automated LLM harness ran. A narrow wording or metadata correction does not require invented evaluation ceremony.
4. Run a baseline when a real available harness permits it. Otherwise record that the baseline was unavailable; never invent results or claim a fake automated LLM harness.
5. Compare expected and observed behavior, record the gap, and make the smallest change that addresses the general gap without overfitting one scenario.
6. Keep shared purpose, essential constraints, and routing in `SKILL.md`. Move substantial conditional guidance to an existing or justified supporting reference and load it only when relevant; do not create a router, directory, or duplicate summary when the skill is already clear and compact.
7. Rerun or independently adjudicate the pressure cases through a real available evaluation path. Include an adversarial edge that distinguishes the skill from an adjacent or non-triggering case and report what actually ran.
8. Revisit the draft and compress the instructions: remove repetition and retain only guidance that changes behavior.
9. Run mechanical tests for front matter, name/path agreement, required outputs, references, and any repository-specific contract. These checks establish structure, not semantic quality.
10. Complete any register or install action only when the requested delivery scope authorizes it.

Do not substitute scenario presence for execution evidence. When no model runner exists, preserve scenarios for later execution and report only the mechanical validation that actually ran.

## Self-check

- Does the description discriminate the real trigger without attracting adjacent work, and does the body preserve the user's purpose, scope, and authorization?
- Is the current skill repaired at its canonical path, with no versioned copy, compatibility layer, or duplicated authority?
- Does `SKILL.md` contain only shared decision-changing guidance, with substantial conditional detail routed once and only when justified?
- For each material judgment change, is there a realistic pressure case plus an adversarial or non-triggering case whose expected decision cannot be satisfied by copying phrases from the skill?
- Are structural validation and any actual behavioral evaluation reported separately, without treating scripts, scenario files, or reviewer advice as the semantic verdict?
