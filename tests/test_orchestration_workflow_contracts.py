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
    assert "Do not treat missing, incomplete, contradictory, or blocked delegation evidence as completed or not-needed" in rule


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
    assert "Do not fail only because visible delegation support is missing" in skill
    assert "single-agent fallback" in skill
    assert "Never allow `prefer_subagent` to bypass visible delegation safety" in skill

    assert "dedicated drift/gap verification section" in rule
    assert "post-repair recheck result" in rule
    assert "## 5. Drift / Gap Verification" in contract
    assert "Final drift/gap result: `clean|blocked`" in contract
    assert "HANDOFF-DONE-007" in contract


def test_execute_plan_requires_codegraph_preflight_and_no_index_fallback_contract() -> None:
    skill = text("skills/orch-execute-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")
    handoff_rule = text("rules/orchestration/orch-handoff-required.md")
    handoff_contract = text("references/assets/orchestration/contract/handoff-executor-result-v1.md")

    assert "Before execution selection, capability checks, delegation, or implementation-file modification" in skill
    assert "target_kind=git-backed" in skill
    assert "target_kind=local-project" in skill
    assert "Do not reject an explicitly resolved non-Git local project root solely as `not-git`" in skill
    assert "git status --porcelain=v1 --untracked-files=all" in skill
    assert "does not fabricate Git cleanliness evidence for local-project targets" in skill

    assert "If the target root has no `.codegraph/`, record CodeGraph as skipped with reason `no-index`" in skill
    assert "Do not initialize CodeGraph and do not run `codegraph sync`" in skill
    assert "run `codegraph sync <absolute-repository-root>` after the applicable target preflight" in skill
    assert "Then query CodeGraph for the task-relevant symbol" in skill
    assert "post-change `codegraph sync <absolute-repository-root>`" in skill
    assert "sync-failed" in skill

    assert "Each target records `target_kind` and `preflight_kind`" in workflow
    assert "Same-repository sync operations are serialized" in workflow
    assert "local-project targets rerun local-project preflight evidence" in workflow

    assert "pre-inspection `codegraph sync <repo-root>` command and result" in handoff_rule
    assert "explicitly record no-index fallback" in handoff_rule
    assert "target_kind: git-backed|local-project" in handoff_contract
    assert "pre_inspection_sync:" in handoff_contract
    assert "post_change_sync:" in handoff_contract
    assert "decision_reason: null|no-index|not-source-code|sync-failed|<short reason>" in handoff_contract


def test_execute_plan_requires_visible_delegation_and_allows_helpers_only() -> None:
    skill = text("skills/orch-execute-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")
    handoff_rule = text("rules/orchestration/orch-handoff-required.md")
    handoff_contract = text("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    review_skill = text("skills/orch-review-plan/SKILL.md")

    assert "visible thread/worktree delegation" in skill
    assert "delegated plan, phase, or task ownership will run in a user-visible thread" in skill
    assert "Do not silently delegate to invisible internal spawn work" in skill
    assert "Invisible internal spawn workers must not own delegated plan, phase, or task implementation work" in skill
    assert "Internal workers may be used only for bounded helper analysis" in skill
    assert "does not replace visible thread/worktree task delegation" in skill
    assert "internal_spawn_used_for_task_delegation: false" in skill

    assert "delegate only to visible thread/worktree workers" in workflow
    assert "Invisible internal spawn work must not own delegated implementation work" in workflow
    assert "Internal helper workers remain allowed for bounded analysis" in workflow

    assert "include delegation evidence when a task, phase, or plan was delegated" in handoff_rule
    assert "record contradictory delegation evidence such as `internal_spawn_used_for_task_delegation: true`" in handoff_rule
    assert "visible_reference: \"<thread id, worktree path, or user-visible label>\"|null" in handoff_contract
    assert "internal_spawn_used_for_task_delegation: false" in handoff_contract
    assert "internal_workers_used_for_support:" in handoff_contract

    assert "reject review when visible-delegation evidence is missing" in review_skill
    assert "Internal helper-worker use is acceptable only when the handoff shows it did not own delegated task execution" in review_skill


def test_orchestration_scope_does_not_add_execution_context_or_retrieval_dependency() -> None:
    spec = text(".work-bundle/orchestration/spec/active/spec-process-codegraph-refresh-visible-delegation-20260621.md")
    plan = text(".work-bundle/orchestration/plan/active/process-orchestration-execution-safety-v1.md")
    skill = text("skills/orch-execute-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")

    for artifact in (spec, plan):
        assert ".work-bundle/knowledge/**" in artifact

    assert ".work-bundle/knowledge/" in skill
    assert "Developing the broader execution-context artifact, schema, index, lifecycle, or archive behavior" in spec
    assert "Adding `.work-bundle/orchestration/execution-state/` context files or context indexes" in spec
    assert "DF-001" in plan
    assert "Do not create execution-state/context artifacts" not in workflow
    assert ".work-bundle/orchestration/execution-state" not in workflow
    assert "Execution-context artifact work is absent from the implementation scope" in spec
    assert "Execution must use context already carried by the specification, plan, phase, task, and declared handoffs" in skill
    assert "must not run v3 retrieval queries" in skill


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
