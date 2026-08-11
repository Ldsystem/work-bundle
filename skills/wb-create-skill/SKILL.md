---
name: wb-create-skill
description: Use WHEN creating or changing a built-in WorkBundle skill so its trigger, observable behavior, pressure scenarios, mechanical contracts, and registration are validated before installation.
---

# Create Skill

Build skills by pressure-testing behavior, then making the smallest general improvement.

## Workflow

1. Define the trigger and observable behavior. Keep all WHEN-to-use guidance in the front-matter description.
2. Write realistic pressure evals before changing the skill. Store scenarios under `references/evals/<area>/evals.json`; this is scenario storage, not proof that an automated LLM harness ran.
3. Run a baseline when the available harness permits it. Otherwise record that the baseline was unavailable; never invent results or claim a fake automated LLM harness.
4. Compare expected and observed behavior, then record the gap.
5. Make the smallest change that addresses the general gap without overfitting one scenario.
6. Rerun the pressure evals through a real available evaluation path and record the outcome.
7. Add at least one adversarial edge that distinguishes the skill from an adjacent or non-triggering case.
8. Compress the instructions: remove repetition and retain only guidance that changes behavior.
9. Run mechanical tests for front matter, name/path agreement, required outputs, references, and any repository-specific contract.
10. Only after scenario, adversarial, compression, and mechanical gates pass, register or install the built-in skill.

Do not substitute scenario presence for execution evidence. When no model runner exists, preserve scenarios for later execution and report only the mechanical validation that actually ran.
