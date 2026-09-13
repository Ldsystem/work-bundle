import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_runtime_rule_paths_exist_without_duplicated_loading_algorithm() -> None:
    for path in sorted(REPO_ROOT.glob("skills/orch-*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for rule_path in re.findall(r"`(rules/orchestration/[^`]+)`", text):
            assert (REPO_ROOT / rule_path).is_file(), f"{path.name}: {rule_path}"
        if path.name == "SKILL.md" and path.parent.name in {
            "orch-create-specification",
            "orch-create-implementation-plan",
            "orch-execute-plan",
            "orch-review-plan",
        }:
            assert "## Rule Loading (mandatory)" not in text
            assert "Central `AGENTS.md` owns rule discovery and loading" in text


def test_obsolete_role_context_surface_is_removed() -> None:
    for relative in [
        "skills/wb-select-role-context/SKILL.md",
        "rules/role-context.md",
        "references/wb-select-role-context-contract.yaml",
        "scripts/work-bundle/role_context.py",
    ]:
        assert not (REPO_ROOT / relative).exists(), relative

    for relative in [
        "skills/orch-create-document/SKILL.md",
        "skills/orch-create-handoff/SKILL.md",
        "references/assets/keep-summarizing/workflow.md",
        "scripts/work-bundle/README.md",
        "scripts/work-bundle/core.py",
        "scripts/work-bundle/dispatcher.py",
        "scripts/work-bundle/metadata_profile.py",
        "scripts/work-bundle/project.py",
        "rules/index.yaml",
    ]:
        text = read(relative).lower()
        assert "wb-select-role-context" not in text, relative
        assert "role-context" not in text, relative
        assert "role context" not in text, relative


def test_specification_uses_compact_semantic_convergence_and_workspace_policy() -> None:
    text = read("skills/orch-create-specification/SKILL.md")
    for token in [
        "dev-semantic-convergence",
        "user-purpose coverage",
        "authority and evidence support",
        "requirement, constraint, and open-question consistency",
        "impact radius",
        "Knowledge Base Update disposition",
        "execution-workspace policy",
        "semantic_loop:",
        "Quality gate: verified|blocked",
        "Initial User Purpose Evidence",
        "Design Interrogation",
        "impact-decision view",
        "accepted | excluded | blocking",
        "none_relevant",
        "stopping_reason",
        "projects_to",
        "excellence-applicability view",
        "no_material_opportunity",
        "material_opportunities",
        "accepted | rejected | deferred | not_material",
    ]:
        assert token in text
    assert "Extra evidence loop" not in text


def test_planner_allocates_methodology_capability_and_bounded_context() -> None:
    text = read("skills/orch-create-implementation-plan/SKILL.md")
    for token in [
        "expected total orchestration cost",
        "independently falsifiable",
        "bounded failure radius",
        "coherent mechanical increment",
        "source-ID coverage",
        "dev-systematic-debugging",
        "dev-test-driven-development",
        "dev-code-review",
        "mechanical",
        "standard",
        "judgment",
        "context_mode: compiled-brief",
        "acceptance_review:",
        "acceptance_review.required: false",
        "Do not infer",
        "soft applicability prose",
        "after_failed_repairs: 2",
        "common contract group",
        "post-barrier convergence task",
        "Truth Basis",
        "earliest ordinary task",
        "cheaply falsify",
        "Do not add a risk score",
        "EXC-",
        "deferred",
        "executor briefs",
    ]:
        assert token in text


def test_execute_skill_uses_compiler_independent_review_and_typed_blockers() -> None:
    text = read("skills/orch-execute-plan/SKILL.md")
    for token in [
        "## Execution Constraints (skill-owned)",
        "## Scheduler-Owned Constraints",
        "## Executor-Owned Constraints",
        "build-task-brief",
        "validate-executor-result",
        "build-review-package",
        "dev-code-review",
        "The scheduler does not perform code-quality review",
        "every implementation and repair task subagent-owned",
        "TaskOwnershipScheduler",
        "TaskOwnershipScheduler.validate_acceptance",
        "there is no controller or single-agent fallback",
        "must not implement or repair task write scope",
        "one scoped rereview",
        "review_required: true",
        "validate initial executor facts without demanding or embedding the future review verdict",
        "stored required-review authority",
        "context-blocked",
        "repository-blocked",
        "decision-blocked",
        "validation-blocked",
        "review-blocked",
        "knowledge-blocked",
        "workspace-blocked",
        "no-index",
        "no-retrieval",
        "Truth Basis",
        "knowledge disposition",
        "task-local evidence",
        "review owns",
    ]:
        assert token in text


def test_task_ownership_contract_is_provider_neutral_and_not_visibility_specific() -> None:
    for relative in [
        "skills/orch-create-handoff/SKILL.md",
        "rules/orchestration/orch-handoff-required.md",
        "references/assets/orchestration/contract/handoff-executor-result-v1.md",
    ]:
        text = read(relative)
        for token in ["delegation_evidence", "owner_kind", "agent", "run", "mechanism"]:
            assert token in text, f"{relative}: {token}"
        for retired in ["visible_reference", "internal_spawn_used_for_task_delegation", "single-agent-fallback"]:
            assert retired not in text, f"{relative}: {retired}"


def test_final_review_is_workflow_audit_not_code_review() -> None:
    text = read("skills/orch-review-plan/SKILL.md")
    for token in [
        "workflow audit",
        "Independent `dev-code-review` owns task-scoped implementation quality",
        "compiled Truth Basis",
        "AUTH constraints",
        "universal task-review evidence",
        "implementation-review agent",
        "explicitly required",
        "review-blocked",
        "knowledge-blocked",
        "repository-blocked",
        "workspace-blocked",
        "repair plan only",
        "repair specification",
        "Do not broadly inspect source",
        "Do not create a repair specification for every failed gate",
        "aggregate accepted task dispositions",
        "accepted `update`, `supersede`, or `reclassify`",
        "rejected task dispositions",
        "archive remains blocked",
        "RuntimeVerificationClassificationV1",
        "invariant_trace",
        "negative_evidence",
        "owning_repair",
        "execution_introduced_bug",
        "implementation_gap",
        "new_feature",
        "uncovered_fixture",
        "evidence_capability",
        "INV/VAL",
        "incapable green",
        "pre-closure oracle-capability check",
        "no_validation_bearing_obligation",
        "none_relevant",
    ]:
        assert token in text


def test_review_enforces_evidence_capability_before_closure() -> None:
    for relative in [
        "skills/orch-review-plan/SKILL.md",
        "rules/orchestration/orch-review-completion.md",
    ]:
        text = read(relative)
        for token in [
            "evidence_capability",
            "INV/VAL",
            "incapable green",
            "wrong-boundary",
            "harness-observed",
            "no_validation_bearing_obligation",
            "none_relevant",
            "pre-closure oracle-capability check",
            "task repair",
            "plan repair",
            "specification repair",
            "RuntimeVerificationClassificationV1",
            "WOR-59 G9 remains the unchanged post-execution classifier",
            "universal browser, E2E, production, or runtime gate",
        ]:
            assert token in text, f"{relative}: {token}"


def test_runtime_verification_classification_contract_routes_the_first_broken_artifact() -> None:
    for relative in [
        "skills/orch-review-plan/SKILL.md",
        "rules/orchestration/orch-review-completion.md",
    ]:
        text = read(relative)
        for token in [
            "RuntimeVerificationClassificationV1",
            "original user request",
            "accepted specification",
            "invariant_trace",
            "negative_evidence",
            "execution_introduced_bug",
            "implementation_gap",
            "new_feature",
            "uncovered_fixture",
            "owning_repair",
            "presentation",
            "wb-defect-evaluation",
            "work-bundle-scoped or mixed",
            "same-scope specification-owned",
            "task repair",
            "plan repair",
            "specification repair",
        ]:
            assert token in text, f"{relative}: {token}"
        assert "unit tests alone" in text
        assert "must not decide the semantic class" in text


def test_durable_owners_state_current_acceptance_and_review_semantics() -> None:
    required = {
        "rules/lifecycle-authority.md": [
            "compact accepted result",
            "acceptance once",
            "historical handoff chains",
            "current harness observation",
        ],
        "rules/repository-boundary.md": [
            "issue-run artifacts",
            "workspace control plane",
            "exact baseline and endpoint",
            "live `HEAD`",
            "historical cleanup",
        ],
        "rules/work-bundle/wb-defect-evaluation.md": [
            "causal class",
            "first owning layer",
            "before responding",
        ],
        "rules/orchestration/orch-artifact-authoring.md": [
            "canonical semantic plan projection",
            "static task admission",
            "status-only",
        ],
        "rules/orchestration/orch-orchestration-boundary.md": [
            "compact accepted result",
            "transient acceptance evidence",
            "historical handoff chains",
        ],
        "rules/orchestration/orch-review-completion.md": [
            "reviewer infrastructure or provider failure",
            "publication-only/control resume",
            "finding-scoped repair review",
            "previous finding/evidence frontier",
        ],
        "skills/orch-create-implementation-plan/SKILL.md": [
            "canonical semantic plan projection",
            "static task admission",
            "status-only or append-only evidence",
        ],
        "skills/orch-execute-plan/SKILL.md": [
            "compact accepted result",
            "acceptance once",
            "preserve the immutable package",
            "affected frontier",
        ],
        "skills/orch-review-plan/SKILL.md": [
            "compact accepted results",
            "historical handoff chains",
            "current harness observations",
        ],
        "references/assets/orchestration/contract/plan-v1.md": [
            "canonical semantic plan projection",
            "static task admission",
            "status-only or append-only evidence",
        ],
    }
    for relative, tokens in required.items():
        text = read(relative)
        for token in tokens:
            assert token in text, f"{relative}: {token}"


def test_workflow_makes_task_review_optional_on_the_chain() -> None:
    text = read("references/assets/orchestration/workflow.md")
    for token in [
        "optional task review",
        "validate-executor-result",
        "optional task review when compiled review_required: true",
        "accepted-result materialization joins executor facts, observations, and stored review authority",
    ]:
        assert token in text
    assert "-> independent dev-code-review" not in text


def test_orchestration_doctor_uses_optional_review_anchors() -> None:
    text = (REPO_ROOT / "scripts/orchestration/doctor.py").read_text(encoding="utf-8")

    assert '"optional task review"' in text
    assert '"acceptance_review.required: true"' in text
    assert '"independent dev-code-review"' not in text


def test_doctor_execute_path_requires_validate_not_universal_review() -> None:
    text = read("scripts/orchestration/doctor.py")
    start = text.index('skill_root / "orch-execute-plan" / "SKILL.md"')
    first_list = text[start:].split("[", 1)[1].split("]", 1)[0]
    assert "validate-executor-result" in first_list
    assert "acceptance_review.verdict: accept" not in first_list
    assert "build-review-package" not in first_list

    review_start = text.index('skill_root / "orch-review-plan" / "SKILL.md"')
    review_list = text[review_start:].split("[", 1)[1].split("]", 1)[0]
    assert "acceptance_review.verdict: accept" not in review_list
    assert "compiled Truth Basis" in review_list


def test_orch_doctor_remains_read_only() -> None:
    text = read("skills/orch-doctor/SKILL.md")
    assert "## Read-Only Constraints (skill-owned)" in text
    assert "Files changed: none" in text


def test_bounded_closure_contract_converges_policy_controller_and_consumers() -> None:
    rule = read("rules/orchestration/orch-bounded-closure.md")
    index = read("rules/index.yaml")
    execute = read("skills/orch-execute-plan/SKILL.md")
    review = read("skills/orch-review-plan/SKILL.md")
    review_rule = read("rules/orchestration/orch-review-completion.md")
    artifact_rule = read("rules/orchestration/orch-artifact-authoring.md")
    boundary_rule = read("rules/orchestration/orch-orchestration-boundary.md")
    planner = read("skills/orch-create-implementation-plan/SKILL.md")
    specification = read("skills/orch-create-specification/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    plan_contract = read("references/assets/orchestration/contract/plan-v1.md")
    specification_contract = read(
        "references/assets/orchestration/contract/specification-v1.md"
    )
    metadata_template = read("references/assets/template/project.yaml")

    assert "id: orch-bounded-closure" in rule
    assert "path: orchestration/orch-bounded-closure.md" in index
    for token in [
        "all executor attempts are terminal",
        "begin-review-round",
        "complete-review-round",
        "review-round-status",
        "finalize-with-blockers",
        "exact request ID and target identity",
        "different target identity",
        "factual controller audit-block",
        "must not impersonate a product verdict",
        "fifth completed round",
        "normal final audit",
        "persist finalization-required state",
        "persist an active workspace blocker",
        "finalize the knowledge disposition",
        "archive the origin specification and plan",
        "release owned bindings",
        "persist terminal closure",
        "must not reopen product work",
    ]:
        assert token in rule, token

    for text in (execute, review, review_rule, workflow):
        assert "post-execution review round" in text
        assert "fifth" in text
        assert "finalize-with-blockers" in text

    for text in (artifact_rule, planner, specification, plan_contract, specification_contract):
        assert "plan and specification revisions do not consume" in text
        assert "review_revision_limit" not in text

    for token in [
        "metadata_version: 3",
        "authority: workspace-working-state",
        "workspace_root: <absolute-path-to-workspace-root>",
        "project_root: <absolute-path-to-project-root>",
        "orchestration_control:",
        "post_execution_review_round_limit: 5",
        "post_execution_review_flows: []",
        "blockers: []",
        "closed_flows: []",
        "implementation_exemptions: []",
    ]:
        assert token in metadata_template, token
    assert "prefer_subagent" not in metadata_template

    for text in (boundary_rule, workflow):
        assert "exhausted flow refuses reconciliation before its blocker is written" in text
        assert "active workspace blocker refuses ordinary new work" in text

    assert "retain the project shim until builtin deployment" in workflow
    assert "remove only that owned shim" in workflow
