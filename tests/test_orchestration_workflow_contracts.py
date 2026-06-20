import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def evals(path: str) -> list[dict[str, object]]:
    return json.loads(text(path))["evals"]


def test_review_requires_delegate_return_resume_for_structural_updates() -> None:
    skill = text("skills/orch-review-plan/SKILL.md")

    assert "## Delegate-Return-Resume Protocol" in skill
    assert "delegate mixed implementation, validation, handoff, and review evidence to `ks-extract-valuable-points`" in skill
    assert "written or updated durable knowledge paths" in skill
    assert "evidence-backed no-write rationale" in skill
    assert "index rebuild status" in skill
    assert "resume knowledge-update disposition evaluation" in skill


def test_review_blocks_archive_when_delegation_is_unavailable_or_incomplete() -> None:
    skill = text("skills/orch-review-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")

    assert "delegation cannot run in the active environment or returned evidence is incomplete" in skill
    assert "keeps archive blocked if delegation is unavailable or evidence is incomplete" in workflow
    assert "only when knowledge-update disposition is `completed` or `not-needed`" in workflow


def test_orchestration_boundary_permits_delegation_but_forbids_direct_knowledge_writes() -> None:
    boundary = text("rules/orchestration/orch-orchestration-boundary.md")
    review_skill = text("skills/orch-review-plan/SKILL.md")

    assert "permit cross-skill invocation scheduling or handoff to approved ks-* owners" in boundary
    assert "directly create edit promote delete or index durable knowledge from orch-* skills" in boundary
    assert "may invoke, schedule, or hand off to an approved `ks-*` owner" in review_skill
    assert "must not directly create, edit, promote, delete, or index `.work-bundle/knowledge/**`" in review_skill


def test_disposition_rule_requires_return_evidence_before_resume() -> None:
    rule = text("rules/orchestration/orch-review-completion.md")

    assert "assess validated implementation and review evidence for structural updates" in rule
    assert "delegate mixed structural evidence to ks-extract-valuable-points" in rule
    assert "validate returned structural-value result durable paths or no-write rationale index rebuild status blockers and completion state" in rule
    assert "treat missing incomplete contradictory or blocked delegation evidence as completed or not-needed" in rule


def test_doctor_checks_complete_quality_gate_contract_structurally() -> None:
    doctor = text("scripts/orchestration/doctor.py")

    assert '"skills"' in doctor
    assert "check_eval_shape" in doctor
    assert "check_forbidden_active_dependencies" in doctor
    assert "index_row_identity" in doctor
    assert 'row.get("plan_id")' in doctor
    assert 'row.get("phase_id")' in doctor
    assert 'row.get("related_task")' in doctor
    assert 'root / "spec" / "active"' in doctor
    assert 'for path in root.glob("**/*.md")' not in doctor
    assert "orch-create-specification" in doctor
    assert "orch-create-implementation-plan" in doctor
    assert "orch-execute-plan" in doctor
    assert "Quality gate: verified|blocked" in doctor
    assert "generated-plan verification pass" in doctor
    assert "related specification, root plan, parent phase, and assigned task before handoff" in doctor
    assert "targeted repository root contains `.codegraph/`" in doctor
    assert "Before execution selection, capability checks, delegation, or implementation changes" in doctor
    assert 'forbidden_runtime_file = "HAB" "ITS.md"' in doctor
    assert "discover across every allowed lifecycle partition" in doctor
    assert "use `retrieval_role` exactly" in doctor
    assert "Do not convert non-authority results into requirements" in doctor


def test_doctor_skill_keeps_mechanical_checks_separate_from_agent_judgment() -> None:
    doctor_skill = text("skills/orch-doctor/SKILL.md")

    assert "bounded file presence, JSON shape" in doctor_skill
    assert "must not judge" in doctor_skill
    assert "semantic evidence sufficiency" in doctor_skill
    assert "user-purpose drift" in doctor_skill
    assert "materiality" in doctor_skill
    assert "agent-owned evidence loop needs another round" in doctor_skill


def test_orchestration_evals_cover_preflight_and_review_delegation_regressions() -> None:
    cases = evals("references/evals/orchestration/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "unrelated untracked file" in prompts
    assert "two target source repositories" in prompts
    assert "new source-of-truth rule" in prompts
    assert "ks-extract-valuable-points cannot run" in prompts
    assert "blocks the entire scheduler wave" in expected
    assert "does not archive" in expected


def test_specification_contract_requires_quality_gate_source_context_and_evidence_loop() -> None:
    contract = text("references/assets/orchestration/contract/specification-v1.md")

    assert "## 3. Source Context" in contract
    assert "Design Interrogation" in contract
    assert "`authority`, `candidate`, `background`, and `blocked`" in contract
    assert "material non-authority evidence" in contract
    assert "## 10. Open Questions" in contract
    assert "Advised options" in contract
    assert "## 11. Knowledge Base Update" in contract
    assert "Quality gate: verified|blocked" in contract
    assert "Extra evidence loop" in contract
    assert "Run another evidence round whenever a round changes" in contract


def test_orchestration_workflow_requires_verified_specification_gate_before_planning() -> None:
    workflow = text("references/assets/orchestration/workflow.md")

    assert "missing supporting authority notes do not automatically block authoring" in workflow
    assert "Material non-authority evidence stays visible" in workflow
    assert "Quality gate: verified|blocked" in workflow
    assert "blocked quality gate prevents implementation planning" in workflow
    assert "verified quality gate is required before `orch-create-implementation-plan`" in workflow


def test_create_implementation_plan_requires_generated_artifact_verification_and_repair() -> None:
    skill = text("skills/orch-create-implementation-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")
    plan_contract = text("references/assets/orchestration/contract/plan-v1.md")
    phase_contract = text("references/assets/orchestration/contract/phase-v1.md")
    task_contract = text("references/assets/orchestration/contract/task-v1.md")

    assert "generated-plan verification pass" in skill
    assert "source-spec ID coverage" in skill
    assert "safe parallelization" in skill
    assert "Repair generated-artifact drift" in skill
    assert "stop for specification repair" in skill

    assert "runs generated-plan verification against the source specification before completion" in workflow
    assert "Generated-artifact drift" in workflow
    assert "Unresolved source-spec defects still stop planning for specification repair" in workflow

    assert "## 8. Generated Artifact Verification" in plan_contract
    assert "DONE-VERIFY-001" in plan_contract
    assert "source-spec ID coverage" in plan_contract
    assert "safe parallelization" in plan_contract
    assert "`create-handoff`" in plan_contract

    assert "## 5. Generated Artifact Verification" in phase_contract
    assert "Task map paths, dependencies, ordering, and safe parallelization flags" in phase_contract
    assert "DONE-VERIFY-001" in phase_contract

    assert "## 7. Generated Artifact Integrity" in task_contract
    assert "task write scope supports the parent phase's safe parallelization decision" in task_contract
    assert "task-scoped `executor-result` handoff" in task_contract


def test_orchestration_evals_cover_create_specification_quality_gate_cases() -> None:
    cases = evals("references/evals/orchestration/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "no durable note supports the current purpose" in prompts
    assert "material candidate knowledge conflicts with the user purpose" in prompts
    assert "quality gate is verified" in prompts
    assert "does not block solely because no supporting note exists" in expected
    assert "does not promote the candidate into requirements" in expected
    assert "records `Quality gate: verified`" in expected


def test_execute_plan_requires_executor_drift_gap_verification_and_preserves_fallback() -> None:
    skill = text("skills/orch-execute-plan/SKILL.md")
    rule = text("rules/orchestration/orch-handoff-required.md")
    contract = text("references/assets/orchestration/contract/handoff-executor-result-v1.md")

    assert "related specification, root plan, parent phase, and assigned task before handoff" in skill
    assert "repair every task-scoped drift or gap" in skill.lower()
    assert "record explicit drift/gap verification evidence" in skill
    assert "Do not fail only because sub-agent support is missing" in skill
    assert "single-agent fallback" in skill
    assert "Never allow `prefer_subagent` to bypass repository preflight" in skill

    assert "dedicated drift/gap verification section" in rule
    assert "post-repair recheck result" in rule
    assert "## 5. Drift / Gap Verification" in contract
    assert "Final drift/gap result: `clean|blocked`" in contract
    assert "HANDOFF-DONE-007" in contract


def test_orchestration_codegraph_policy_does_not_require_habits() -> None:
    governed_paths = [
        "rules/agent-codegraph-first.md",
        "skills/orch-create-specification/SKILL.md",
        "skills/orch-execute-plan/SKILL.md",
        "references/assets/template/AGENTS.md",
    ]

    for path in governed_paths:
        assert "HAB" "ITS" not in text(path), path


def test_orchestration_evals_cover_delegated_executor_verification_and_fallback() -> None:
    cases = evals("references/evals/orchestration/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "delegated sub-agent" in prompts
    assert "repairs the task-scoped gap and repeats verification before handoff" in expected
    assert "preserves single-agent fallback" in expected


def test_orchestration_evals_cover_codegraph_and_no_retrieval_fallback() -> None:
    cases = evals("references/evals/orchestration/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "target repository has no .codegraph directory" in prompts
    assert "records that CodeGraph is skipped because the repository is not indexed" in expected
    assert "uses the single-agent fallback for exactly one task" in expected
    assert "keeps execution no-retrieval" in expected
    assert "does not require any additional runtime preference file" in expected


def test_keep_summarizing_evals_cover_cross_lifecycle_discovery_and_narrow_authority() -> None:
    cases = evals("references/evals/keep-summarizing/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "customer-design, development-design, implementation, and operation lifecycle partitions" in prompts
    assert "Discovers relevant candidates across all allowed lifecycle partitions before lifecycle and status authority classification" in expected
    assert "allows only authority to shape the implementation plan" in expected
