import argparse
import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION_SCRIPT_ROOT = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION_SCRIPT_ROOT))

from handoffs import cmd_write_handoff, index_handoffs
from doctor import check_active_handoff_contract


def text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def orchestration_artifact_text(active_path: str, archived_path: str) -> str:
    active = REPO_ROOT / active_path
    if active.exists():
        return active.read_text(encoding="utf-8")
    return (REPO_ROOT / archived_path).read_text(encoding="utf-8")


def evals(path: str) -> list[dict[str, object]]:
    return json.loads(text(path))["evals"]


def handoff_args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "project_root": str(tmp_path),
        "content_file": str(tmp_path / "handoff-content.txt"),
        "type": "executor-result",
        "status": "active",
        "id": "handoff-exec-20990101-001",
        "title": "Task Result",
        "format": None,
        "related_spec": "spec-001",
        "related_plan": "plan-001",
        "related_phase": "phase-001",
        "related_task": "task-001",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_handoff_helper_indexes_compact_yaml_executor_result(tmp_path: Path) -> None:
    content_file = tmp_path / "handoff-content.txt"
    content_file.write_text(
        "result:\n"
        "  state: completed\n"
        "  summary: Compact helper regression.\n",
        encoding="utf-8",
    )

    cmd_write_handoff(handoff_args(tmp_path, content_file=str(content_file)))
    rows = index_handoffs(handoff_args(tmp_path))

    row = next(item for item in rows if item["id"] == "handoff-exec-20990101-001")
    assert row["type"] == "executor-result"
    assert row["status"] == "active"
    assert row["path"] == (
        ".work-bundle/orchestration/handoff/executor/active/"
        "handoff-exec-20990101-001-task-result.yaml"
    )
    assert row["project"] == tmp_path.name
    assert row["created_at"]
    assert row["updated_at"]
    assert row["related_spec"] == "spec-001"
    assert row["related_plan"] == "plan-001"
    assert row["related_phase"] == "phase-001"
    assert row["related_task"] == "task-001"


def test_handoff_helper_preserves_legacy_markdown_indexing(tmp_path: Path) -> None:
    legacy = (
        tmp_path
        / ".work-bundle"
        / "orchestration"
        / "handoff"
        / "executor"
        / "archived"
        / "handoff-exec-20990101-002-legacy.md"
    )
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "---\n"
        "id: handoff-exec-20990101-002\n"
        "type: executor-result\n"
        "status: archived\n"
        f"project: {tmp_path.name}\n"
        "created_at: 2099-01-01\n"
        "updated_at: 2099-01-02\n"
        "related_spec: spec-legacy\n"
        "related_plan: plan-legacy\n"
        "related_phase: phase-legacy\n"
        "related_task: task-legacy\n"
        "---\n\n"
        "# Legacy Markdown Handoff\n",
        encoding="utf-8",
    )

    rows = index_handoffs(handoff_args(tmp_path))

    row = next(item for item in rows if item["id"] == "handoff-exec-20990101-002")
    assert row["type"] == "executor-result"
    assert row["status"] == "archived"
    assert row["path"] == (
        ".work-bundle/orchestration/handoff/executor/archived/"
        "handoff-exec-20990101-002-legacy.md"
    )
    assert row["project"] == tmp_path.name
    assert row["created_at"] == "2099-01-01"
    assert row["updated_at"] == "2099-01-02"
    assert row["related_spec"] == "spec-legacy"
    assert row["related_plan"] == "plan-legacy"
    assert row["related_phase"] == "phase-legacy"
    assert row["related_task"] == "task-legacy"


def test_handoff_helper_rejects_active_orchestration_handoff_creation(tmp_path: Path) -> None:
    content_file = tmp_path / "handoff-content.txt"
    content_file.write_text("# Retired active orchestration handoff\n", encoding="utf-8")

    args = handoff_args(
        tmp_path,
        content_file=str(content_file),
        type="orchestration",
        id="handoff-orch-20990101-001",
        title="Retired Orchestration Handoff",
    )

    with pytest.raises(SystemExit, match="Active orchestration handoff creation is retired"):
        cmd_write_handoff(args)

    active_orchestration = (
        tmp_path / ".work-bundle" / "orchestration" / "handoff" / "orchestration" / "active"
    )
    assert not list(active_orchestration.glob("handoff-orch-20990101-001*"))


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
    assert "only when Knowledge Base Update disposition is `completed` or `not-needed`" in workflow


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
    assert "neutral-cross-stage" in doctor
    assert "classification/output intent" in doctor
    assert "semantic relevance, authority, polarity, conflict, materiality" in doctor
    assert "Do not convert non-authority results into requirements" in doctor


def test_doctor_skill_keeps_mechanical_checks_separate_from_agent_judgment() -> None:
    doctor_skill = text("skills/orch-doctor/SKILL.md")

    assert "bounded file presence, JSON shape" in doctor_skill
    assert "must not judge" in doctor_skill
    assert "semantic evidence sufficiency" in doctor_skill
    assert "user-purpose drift" in doctor_skill
    assert "materiality" in doctor_skill
    assert "agent-owned evidence loop needs another round" in doctor_skill


def test_doctor_checks_compact_handoffs_and_forbidden_fields_mechanically() -> None:
    doctor = text("scripts/orchestration/doctor.py")
    doctor_skill = text("skills/orch-doctor/SKILL.md")

    assert "FORBIDDEN_EXECUTOR_RESULT_FIELDS" in doctor
    assert "check_active_handoff_contract" in doctor
    assert "active executor-result handoff contains forbidden field" in doctor
    assert "Active orchestration handoff creation is retired" in doctor
    assert "default_format: yaml" in doctor
    assert "Required By Applicability" in doctor
    assert "delegation_evidence:" in doctor
    assert "reason: null | no-index | sync-failed | not-source-code | blocked" in doctor
    assert "sparse YAML" in doctor_skill
    assert "must not judge" in doctor_skill


def test_doctor_rejects_forbidden_executor_fields_and_active_orchestration_handoffs(
    tmp_path: Path,
) -> None:
    orchestration_root = tmp_path / ".work-bundle" / "orchestration"
    executor_root = orchestration_root / "handoff" / "executor" / "active"
    retired_root = orchestration_root / "handoff" / "orchestration" / "active"
    executor_root.mkdir(parents=True)
    retired_root.mkdir(parents=True)
    (executor_root / "handoff-exec-invalid.yaml").write_text(
        "id: handoff-exec-invalid\nrecommended_next_actions: []\n",
        encoding="utf-8",
    )
    (retired_root / "handoff-orch-invalid.md").write_text(
        "# Retired active handoff\n",
        encoding="utf-8",
    )
    issues: list[str] = []

    check_active_handoff_contract(issues, orchestration_root)

    assert any("forbidden field recommended_next_actions" in issue for issue in issues)
    assert any("active orchestration handoff is retired" in issue for issue in issues)


def test_executor_result_contract_forbids_legacy_advice_fields() -> None:
    contract = text("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    forbidden = (
        "suggested_durable_conclusions",
        "durable_candidate_facts",
        "recommended_orchestration_review",
        "recommended_next_actions",
        "delegation",
        "deviations",
        "strategy_advice",
        "knowledge_persistence",
    )

    assert "Forbidden Executor-Result Fields" in contract
    for field in forbidden:
        assert f"{field}:" in contract


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
    skill = text("skills/orch-create-specification/SKILL.md")

    assert "## 3. Initial Shell" in contract
    assert "## 4. Source Context" in contract
    assert "Initial User Purpose Evidence" in contract
    assert "Draft Requirement Breakdown" in contract
    assert "Design Interrogation" in contract
    assert "`authority`, `candidate`, `background`, and `blocked`" in contract
    assert "material non-authority evidence" in contract
    assert "## 11. Open Questions" in contract
    assert "Advised options" in contract
    assert "## 12. Knowledge Base Update" in contract
    assert "Quality gate: verified|blocked" in contract
    assert "Extra evidence loop" in contract
    assert "Run another evidence round whenever a round changes" in contract
    assert "Project Metadata Preflight" in skill
    assert "Run project metadata preflight after shell creation" in skill
    assert "## 3.1 Project Metadata Preflight" in contract
    assert "working_branch" in contract
    assert "last_commit_id" in contract
    assert "branch mismatched" in contract
    assert "no-index` or `not-indexed` fallback" in contract


def test_orchestration_workflow_requires_verified_specification_gate_before_planning() -> None:
    workflow = text("references/assets/orchestration/workflow.md")

    assert "Missing supporting authority notes do not automatically block authoring" in workflow
    assert "Material non-authority evidence stays visible" in workflow
    assert "Quality gate: verified|blocked" in workflow
    assert "blocked quality gate prevents implementation planning" in workflow.lower()
    assert "verified quality gate is required before `orch-create-implementation-plan`" in workflow.lower()


def test_planning_skill_and_contracts_require_rule_skill_allocation() -> None:
    skill = text("skills/orch-create-implementation-plan/SKILL.md")
    plan = text("references/assets/orchestration/contract/plan-v1.md")
    phase = text("references/assets/orchestration/contract/phase-v1.md")
    task = text("references/assets/orchestration/contract/task-v1.md")

    assert "Allocate applicable runtime rules and skills" in skill
    assert "rule/skill allocation coverage" in skill
    for artifact in (plan, phase, task):
        assert "allocated_rules:" in artifact
        assert "allocated_skills:" in artifact
        assert "source:" in artifact
        assert "file-backed" in artifact
        assert "applies_when:" in artifact
    assert "VERIFY-005" in plan
    assert "VERIFY-004" in phase
    assert "not limited to `$work_bundle_root/skills` or `$work_bundle_root/rules`" in skill
    assert "AGENTS.md" in skill
    assert ".agents/skills" in skill
    assert ".codex/skills" in skill
    assert "non-WorkBundle rule/skill sources" in skill
    assert "Before implementation, the executor must load, use, acknowledge, or condition-evaluate" in task


def test_execution_skill_consumes_metadata_baseline_and_allocated_context() -> None:
    skill = text("skills/orch-execute-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")
    handoff = text("references/assets/orchestration/contract/handoff-executor-result-v1.md")

    assert "read allocated rules and skills from the selected task, parent phase, and root plan" in skill
    assert "Give every visible delegated worker the allocated rules and skills" in skill
    assert "working_branch" in skill
    assert "last_commit_id" in skill
    assert "metadata baseline evidence" in skill
    assert "allocated_rules and allocated_skills" in workflow
    assert "Do not assume allocated skills come only from `$work_bundle_root/skills`" in skill
    assert "allocated rules come only from WorkBundle rule indexes" in skill
    assert "according to their declared source" in workflow
    assert "branch mismatch" in workflow
    assert "stale metadata baseline" in workflow
    assert "allocation_evidence:" in handoff
    assert "repository[].metadata" in handoff
    assert "branch_status:" in handoff
    assert "commit_status:" in handoff


def test_review_skill_gates_archive_on_commit_codegraph_and_metadata_update() -> None:
    skill = text("skills/orch-review-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")

    assert "operation_policy.git" in skill
    assert "create an allowed Git commit" in skill
    assert "post-review CodeGraph sync" in skill
    assert "update `.work-bundle/project.yaml` source repository state" in skill
    assert "block archive when a required commit, applicable CodeGraph sync, or project metadata update fails" in skill
    assert "Knowledge update disposition: completed|not-needed" in skill
    assert "Review commit/sync/update gates" in workflow
    assert "project metadata `codegraph.supported: true`" in workflow
    assert "working_branch" in workflow
    assert "last_commit_id" in workflow
    assert "Knowledge update disposition evidence" in workflow


def test_orchestration_gateway_policy_is_not_discovery_stage_gate() -> None:
    skill = text("skills/orch-create-specification/SKILL.md")
    gateway_rule = text("rules/orchestration/orch-knowledge-gateway.md")
    workflow = text("references/assets/orchestration/workflow.md")
    contract = text("references/assets/orchestration/contract/specification-v1.md")
    core = text("scripts/orchestration/core.py")

    for artifact in (skill, workflow, contract):
        assert "neutral" in artifact
        assert "cross-stage" in artifact
        assert "classification" in artifact
        assert "output" in artifact
    assert "polarity-neutral" in gateway_rule
    assert "allowed lifecycle partitions" in gateway_rule
    assert "classification" in gateway_rule

    assert "must not discovery-filter candidates to that lifecycle stage" in skill
    assert "Apply retrieval policy per directive as classification and output-grouping intent, not as a discovery-stage lifecycle filter" in gateway_rule
    assert "not stage-gated discovery filters" in workflow
    assert "classification/output intent rather than a discovery-stage filter" in contract
    assert '"discovery": "neutral-cross-stage"' in core
    assert '"usage": "classification-output-intent"' in core


def test_task002_owned_rules_capture_retrieval_open_question_and_artifact_policy() -> None:
    gateway_rule = text("rules/orchestration/orch-knowledge-gateway.md")
    open_questions_rule = text("rules/orchestration/orch-open-questions.md")
    authoring_rule = text("rules/orchestration/orch-artifact-authoring.md")

    assert "repository metadata preflight blocks source inspection" in gateway_rule
    assert "classification-only until source-repository trust is restored" in gateway_rule
    assert "not as automatic blockers for bounded durable-knowledge discovery" in gateway_rule

    assert "evidence class or polarity alone is not a blocker" in open_questions_rule
    assert "related active violation registry evidence as blocking Open Questions" in open_questions_rule
    assert "does not shape requirements and is not marked blocking solely by evidence class or polarity" in open_questions_rule

    assert "Keep generated plans compact" in authoring_rule
    assert "common contract groups, barrier participant maps" in authoring_rule
    assert "forbidden peer validation" in authoring_rule
    assert "common contracts, accepted prior handoffs, and post-barrier convergence" in authoring_rule


def test_orchestration_gateway_surfaces_conflicts_without_downstream_lookup() -> None:
    skill = text("skills/orch-create-specification/SKILL.md")
    gateway_rule = text("rules/orchestration/orch-knowledge-gateway.md")
    workflow = text("references/assets/orchestration/workflow.md")
    contract = text("references/assets/orchestration/contract/specification-v1.md")

    assert "supporting, opposing, constraining, unresolved/open-question" in skill
    assert "Candidate, background, and blocked evidence is non-shaping by default" in skill
    assert "Treat `blocked` context as non-shaping evidence" in gateway_rule
    assert "future knowledge-base lookup" in skill
    assert "future knowledge-base lookup" in gateway_rule
    assert "must not read `.work-bundle/knowledge/` directly" in workflow
    assert "downstream planning and execution do not need to read `.work-bundle/knowledge/`" in contract


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


def test_orchestration_skills_require_impact_radius_propagation() -> None:
    create_spec = text("skills/orch-create-specification/SKILL.md")
    create_plan = text("skills/orch-create-implementation-plan/SKILL.md")

    assert "recursive impact-radius traversal" in create_spec
    assert "component cursor through upstream components" in create_spec
    assert "downstream components that consume or validate it" in create_spec
    assert "validation/test artifacts in impact-radius traversal" in create_spec
    assert "Record impact-radius evidence compactly" in create_spec
    assert "blocking open question instead of silently narrowing scope" in create_spec

    assert "Carry source-spec impact-radius evidence forward" in create_plan
    assert "affected upstream components, downstream components, and validation/test artifacts" in create_plan
    assert "exact phase and task source files, target files, validation commands, dependencies, and convergence checks" in create_plan
    assert "Reject planning and require source-spec repair" in create_plan
    assert "missing required source-spec impact-radius evidence" in create_plan


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


def test_orchestration_evals_cover_no_stage_gate_conflict_and_downstream_no_lookup() -> None:
    cases = evals("references/evals/orchestration/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "outside the implementation_spec lifecycle" in prompts
    assert "authority evidence materially opposes" in prompts
    assert "downstream plan tasks from a verified specification" in prompts
    assert "neutral cross-stage discovery" in expected
    assert "classification and output-grouping intent" in expected
    assert "does not discovery-filter candidates to implementation_spec lifecycle partitions" in expected
    assert "opposing or constraining evidence" in expected
    assert "does not require downstream knowledge-base lookup" in expected


def test_execute_plan_requires_executor_drift_gap_verification_and_preserves_fallback() -> None:
    skill = text("skills/orch-execute-plan/SKILL.md")
    rule = text("rules/orchestration/orch-handoff-required.md")
    contract = text("references/assets/orchestration/contract/handoff-executor-result-v1.md")

    assert "related specification, root plan, parent phase, and assigned task before handoff" in skill
    assert "repair every task-scoped drift or gap" in skill.lower()
    assert "Record explicit drift/gap verification evidence" in skill
    assert "Do not fail only because multi-agent subagent delegation support is missing" in skill
    assert "single-agent fallback" in skill
    assert "Never allow `prefer_subagent` to bypass visible delegation safety" in skill

    assert "`task_fit_check` naming the related task" in rule
    assert "explicit spec/root-plan/phase/task drift-gap verification evidence" in rule
    assert "task_fit_check:" in contract
    assert "artifacts_checked:" in contract
    assert "result: clean | repaired | unresolved | skipped" in contract


def test_execute_plan_triggers_violation_evaluation_without_chain_of_thought_requirement() -> None:
    skill = text("skills/orch-execute-plan/SKILL.md")

    assert "Trigger `wb-violation-evaluation`" in skill
    assert "execution-time conflicts, violations, errors, failed validations" in skill
    assert "user interruptions, or user corrections" in skill
    assert "WorkBundle process responsibility plausible" in skill
    assert "stop once visible evidence shows WorkBundle" in skill
    assert "do not require chain-of-thought output" in skill
    assert "exhaustive root-cause tracing" in skill
    assert "new upstream/downstream impact evidence or validation/test evidence" in skill


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
    assert "Do not fabricate Git cleanliness evidence for local-project targets" in skill

    assert "If the target root has no `.codegraph/`, record CodeGraph as skipped with reason `no-index`" in skill
    assert "Do not initialize CodeGraph and do not run `codegraph sync`" in skill
    assert "run `codegraph sync <absolute-repository-root>` after the applicable target preflight" in skill
    assert "Then query CodeGraph for the task-relevant symbol" in skill
    assert "post-change `codegraph sync <absolute-repository-root>`" in skill
    assert "sync-failed" in skill

    assert "Each target records `target_kind` and `preflight_kind`" in workflow
    assert "Same-repository sync operations are serialized" in workflow
    assert "local-project targets rerun local-project preflight evidence" in workflow

    assert "include compact CodeGraph evidence when source-code inspection or edits were in scope" in handoff_rule
    assert "explicitly record no-index fallback" in handoff_rule
    assert "root: /absolute/path" in handoff_contract
    assert "applicable: true | false" in handoff_contract
    assert "up_to_date: true | false" in handoff_contract
    assert "reason: null | no-index | sync-failed | not-source-code | blocked" in handoff_contract


def test_execute_plan_requires_visible_delegation_and_allows_helpers_only() -> None:
    skill = text("skills/orch-execute-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")
    handoff_rule = text("rules/orchestration/orch-handoff-required.md")
    handoff_contract = text("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    review_skill = text("skills/orch-review-plan/SKILL.md")

    assert "multi-agent subagent delegation" in skill
    assert "Delegate each task in the wave to a separate visible multi-agent subagent" in skill
    assert "Do not silently delegate to invisible internal spawn work" in skill
    assert "Invisible internal spawn workers and cross-conversation delegation must not own delegated plan, phase, or task implementation work" in skill
    assert "Internal workers may be used only for bounded helper analysis" in skill
    assert "does not replace multi-agent subagent task delegation" in skill
    assert "internal_spawn_used_for_task_delegation: false" in skill

    assert "delegate only to visible multi-agent subagents" in workflow
    assert "Invisible internal spawn work and cross-conversation delegation must not own delegated implementation work" in workflow
    assert "Internal helper workers remain allowed for bounded analysis" in workflow

    assert "`delegation_evidence` only as proof of task ownership delegation" in handoff_rule
    assert "record contradictory delegation evidence such as `internal_spawn_used_for_task_delegation: true`" in handoff_rule
    assert "visible_reference: null" in handoff_contract
    assert "internal_spawn_used_for_task_delegation: false" in handoff_contract
    assert "internal_workers_used_for_support: false" in handoff_contract

    assert "reject review when visible-delegation evidence is missing" in review_skill
    assert "Internal helper-worker use is acceptable only when the handoff shows it did not own delegated task execution" in review_skill


def test_orchestration_scope_does_not_add_execution_context_or_retrieval_dependency() -> None:
    spec = orchestration_artifact_text(
        ".work-bundle/orchestration/spec/active/spec-process-compact-executor-handoff-optimization-20260622.md",
        ".work-bundle/orchestration/spec/archived/spec-process-compact-executor-handoff-optimization-20260622.md",
    )
    plan = orchestration_artifact_text(
        ".work-bundle/orchestration/plan/active/process-orchestration-compact-handoff-v1.md",
        ".work-bundle/orchestration/plan/archived/process-orchestration-compact-handoff-v1.md",
    )
    skill = text("skills/orch-execute-plan/SKILL.md")
    workflow = text("references/assets/orchestration/workflow.md")

    for artifact in (spec, plan):
        assert ".work-bundle/knowledge/" in artifact

    assert ".work-bundle/knowledge/" in skill
    assert "execution remains no-retrieval" in spec
    assert "executors must not read `.work-bundle/knowledge/`" in plan
    assert "Do not create execution-state/context artifacts" not in workflow
    assert ".work-bundle/orchestration/execution-state" not in workflow
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
    assert "visible multi-agent subagents" in prompts
    assert "cross-conversation delegation" in expected
    assert "repairs the task-scoped gap and repeats verification before handoff" in expected
    assert "preserves single-agent fallback" in expected


def test_orchestration_evals_cover_parallelization_and_spec_shell_first() -> None:
    cases = evals("references/evals/orchestration/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "backend and frontend work can run in parallel" in prompts
    assert "long optimization request with supplied screenshots and reference files" in prompts
    assert "boundary artifact first" in expected
    assert "api-contract-first" in expected
    assert "convergence validation task" in expected
    assert "Initial User Purpose Evidence" in expected
    assert "Draft Requirement Breakdown" in expected
    assert "before long evidence gathering" in expected


def test_orchestration_evals_cover_sparse_yaml_and_retired_active_handoffs() -> None:
    cases = evals("references/evals/orchestration/evals.json")
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "sparse YAML" in expected
    assert "active orchestration handoff" in expected
    assert "forbidden executor advice fields" in expected


def test_orchestration_evals_cover_codegraph_and_no_retrieval_fallback() -> None:
    cases = evals("references/evals/orchestration/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "target repository has no .codegraph directory" in prompts
    assert "records that CodeGraph is skipped because the repository is not indexed" in expected
    assert "uses the single-agent fallback for exactly one task" in expected
    assert "keeps execution no-retrieval" in expected
    assert "does not require any additional runtime preference file" in expected


def test_orchestration_workflow_carries_workspace_member_and_credential_boundaries() -> None:
    workflow = text("references/assets/orchestration/workflow.md")
    cases = evals("references/evals/orchestration/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "<workspace-root>/.work-bundle/orchestration/" in workflow
    assert "explicit `--project-root` selects a single-repository root or managed member" in workflow
    assert "Reusable workspace utilities live only under singular `<workspace-root>/script/`" in workflow
    assert "Credential values must never enter specifications, plans, tasks, handoffs" in workflow
    assert "runtime skill registry is external-only" in workflow
    assert "`wb-credential-use` and `wb-migrate-to-multi-repository`" in workflow
    assert "deep directory inside a managed multi-repository workspace member" in prompts
    assert "creates no registry proposal or merge" in expected
    assert "transmits only credential ID, redacted target, requested operation" in expected


def test_keep_summarizing_evals_cover_cross_lifecycle_discovery_and_narrow_authority() -> None:
    cases = evals("references/evals/keep-summarizing/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "customer-design, development-design, implementation, and operation lifecycle partitions" in prompts
    assert "Discovers relevant candidates across all allowed lifecycle partitions before lifecycle and status authority classification" in expected
    assert "allows only authority to shape the implementation plan" in expected
