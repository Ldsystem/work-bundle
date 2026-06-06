import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def evals(path: str) -> list[dict[str, object]]:
    return json.loads(text(path))["evals"]


def test_review_requires_delegate_return_resume_for_structural_updates() -> None:
    directive = text("references/directives/orchestration/review-plan.md")

    assert "## Delegate-Return-Resume Protocol" in directive
    assert "delegate mixed implementation, validation, handoff, and review evidence to `ks-extract-valuable-points`" in directive
    assert "written or updated durable knowledge paths" in directive
    assert "evidence-backed no-write rationale" in directive
    assert "index rebuild status" in directive
    assert "resume knowledge-update disposition evaluation" in directive


def test_review_blocks_archive_when_delegation_is_unavailable_or_incomplete() -> None:
    directive = text("references/directives/orchestration/review-plan.md")
    workflow = text("references/assets/orchestration/workflow.md")

    assert "delegation cannot run in the active environment or returned evidence is incomplete" in directive
    assert "keeps archive blocked if delegation is unavailable or evidence is incomplete" in workflow
    assert "only when knowledge-update disposition is `completed` or `not-needed`" in workflow


def test_orchestration_boundary_permits_delegation_but_forbids_direct_knowledge_writes() -> None:
    boundary = text("rules/orch-orchestration-boundary.yaml")
    review_skill = text("skills/orch-review-plan/migration.md")
    directive = text("references/directives/orchestration/review-plan.md")

    assert "permit cross-skill invocation scheduling or handoff to approved ks-* owners" in boundary
    assert "directly create edit promote delete or index durable knowledge from orch-* skills" in boundary
    assert "may invoke, schedule, or hand off to an approved `ks-*` owner" in review_skill
    assert "must not directly create, edit, promote, delete, or index `.work-bundle/knowledge/**`" in directive


def test_disposition_rule_requires_return_evidence_before_resume() -> None:
    rule = text("rules/orch-knowledge-update-disposition.yaml")

    assert "assess validated implementation and review evidence for structural updates" in rule
    assert "delegate mixed structural evidence to ks-extract-valuable-points" in rule
    assert "validate returned structural-value result durable paths or no-write rationale index rebuild status blockers and completion state" in rule
    assert "treat missing incomplete contradictory or blocked delegation evidence as completed or not-needed" in rule


def test_doctor_uses_active_directive_roots_and_checks_three_workflow_contracts() -> None:
    doctor = text("scripts/orchestration/doctor.py")

    assert '"references" / "directives" / "orchestration"' in doctor
    assert '"references" / "directives" / "keep-summarizing"' in doctor
    assert "orch-repository-clean-preflight" in doctor
    assert "ks-note-state-authority" in doctor
    assert "orch-knowledge-update-disposition" in doctor
    assert "Before execution selection, capability checks, delegation, or implementation changes" in doctor
    assert "Classify only after full candidate discovery" in doctor
    assert "Delegate-Return-Resume Protocol" in doctor


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


def test_keep_summarizing_evals_cover_cross_lifecycle_discovery_and_narrow_authority() -> None:
    cases = evals("references/evals/keep-summarizing/evals.json")
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)

    assert "customer-design, development-design, implementation, and operation lifecycle partitions" in prompts
    assert "Discovers relevant candidates across all allowed lifecycle partitions before lifecycle and status authority classification" in expected
    assert "allows only authority to shape the implementation plan" in expected
