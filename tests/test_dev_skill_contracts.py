from __future__ import annotations

from pathlib import Path
import json


REPO_ROOT = Path(__file__).resolve().parents[1]


def skill_text(name: str) -> str:
    return (REPO_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_wb_initialize_skill_matches_live_cli() -> None:
    text = skill_text("wb-initialize-project")
    epilog = (REPO_ROOT / "scripts" / "work-bundle" / "core.py").read_text(encoding="utf-8")

    assert "`init-project <root> --mode <single-repository|multi-repository> [--workspace-root <workspace-root>]" in text
    assert "init-project <project-root> --mode <single-repository|multi-repository> [--workspace-root <workspace-root>]" in epilog
    assert "`doctor-project <root> [--workspace-root" not in text
    assert "`validate-project <root> [--workspace-root" not in text
    assert "`doctor-project <root> [--repair] [--force]`" in text
    assert "`validate-project <root> [--dry-run]`" in text
    assert "Existing command names and `--project-root` remain supported for single-repository projects." not in text


def test_semantic_convergence_contract_is_bounded_and_reports_compact_result() -> None:
    text = skill_text("dev-semantic-convergence")

    assert len(text.split()) < 500
    for token in [
        "DRAFT",
        "VIEW",
        "caller-defined lenses",
        "drift",
        "gap",
        "contradiction",
        "unsupported claim",
        "repair only",
        "unchanged",
        "converged",
        "blocker",
        "semantic_loop:",
        "result:",
        "rounds:",
        "repaired:",
        "Truth Basis",
        "purpose",
        "as-is evidence",
        "decision authority",
        "expected delta",
        "conflict status",
    ]:
        assert token in text
    assert "semantic artifacts" in text


def test_systematic_debugging_requires_root_cause_before_fix() -> None:
    text = skill_text("dev-systematic-debugging")

    for token in [
        "Reproduce",
        "root cause",
        "working and broken",
        "one hypothesis",
        "minimal experiment",
        "root-cause fix",
        "Verify",
        "documented containment",
        "Truth Basis",
        "purpose",
        "as-is evidence",
        "decision authority",
        "expected delta",
        "conflict status",
        "scope grows",
        "multiple repositories",
        "full orchestration",
    ]:
        assert token in text
    assert "Do not implement a fix before establishing the root cause" in text


def test_tdd_contract_names_cycle_applicability_and_exemptions() -> None:
    text = skill_text("dev-test-driven-development")

    for token in [
        "RED",
        "verify RED",
        "GREEN",
        "verify GREEN",
        "REFACTOR",
        "new or changed executable behavior",
        "bug fixes after diagnosis",
        "behavior-changing refactors",
        "generated code",
        "configuration-only",
        "documentation, rules, or skills",
        "non-testable mechanical artifacts",
        "behavior-preserving refactor",
        "characterization coverage",
        "GROUND",
        "revalidate truth and impact",
    ]:
        assert token in text


def test_code_review_contract_is_independent_and_emits_exact_shape() -> None:
    text = skill_text("dev-code-review")

    for token in [
        "task fit",
        "rules and methodology",
        "correctness and edge cases",
        "unnecessary complexity",
        "validation evidence",
        "reviewer_independent: true | false",
        "verdict: accept | repair | blocked",
        "reviewed_head: <commit-or-tree-identity>",
        "severity: blocking | advisory",
        "scope: specification | correctness | quality | validation | rule",
        "finding: <compact evidence-backed text>",
        "grounded intent",
        "decision authority",
        "test oracle",
        "knowledge disposition",
    ]:
        assert token in text


def test_mechanical_task_plan_contract_escalates_and_uses_exact_sections() -> None:
    text = skill_text("dev-create-task-plan")

    for token in [
        ".work-bundle/runtime/dev-plans/",
        "architecture, API, data-model, or workflow decision",
        "wide impact radius",
        "multiple repositories",
        "migration or deployment",
        "durable knowledge",
        "parallel barriers",
        "# Mechanical Execution Plan",
        "## Goal",
        "## Truth Basis",
        "Purpose:",
        "As-is evidence:",
        "Decision authority:",
        "Expected delta:",
        "Conflict status: clear | escalate",
        "## Method",
        "tdd | systematic-debugging | direct | loop-coding",
        "Bug work starts with `systematic-debugging` until diagnosis",
        "testable repair then transitions to `tdd`",
        "## Capability",
        "## Files",
        "Read:",
        "Modify:",
        "Test:",
        "## Interfaces",
        "Consumes:",
        "Produces:",
        "## Steps",
        "1. Baseline",
        "2. Change",
        "3. Verify",
        "4. If verification fails",
        "5. Commit if permitted",
        "## Completion evidence",
        "## Knowledge disposition",
        "none | update | supersede | reclassify",
        "verify RED",
        "verify GREEN",
        "ks-what-is-helpful",
        "lightweight completion owner",
        "none relevant",
        "no-write",
    ]:
        assert token in text


def test_mechanical_task_plan_freezes_envelope_not_strategy() -> None:
    text = skill_text("dev-create-task-plan")

    assert "implementation direction are already settled" not in text
    for token in [
        "settled even if the internal algorithm is not chosen",
        "Eligibility does not require the internal implementation strategy to be settled",
        "Keep one disposable `.work-bundle/runtime/dev-plans/` artifact",
        "Do not import executor-result",
        "`Completed`",
        "review package",
        "archive helper",
        "Knowledge Base Update",
        "`Files.Read`",
        "`Files.Test`",
        "initial evidence anchors",
        "`Files.Modify`",
        "mutation envelope",
        "Additional bounded reads",
        "Writes outside",
        "As-is evidence may be expanded",
        "may not be silently changed",
        "conflict_status: escalate",
        "exact claim",
        "observed result",
        "pre-edit baseline",
        "remaining blockers",
        "Intended checks without observed results are not completion evidence",
        "Capability is a floor",
        "Stronger models",
        "Weaker capability",
    ]:
        assert token in text


def test_development_pressure_evals_cover_grounding_and_adversarial_boundary() -> None:
    cases = json.loads(
        (REPO_ROOT / "references/evals/development/evals.json").read_text(encoding="utf-8")
    )["evals"]
    ids = {case["id"] for case in cases}
    for required_id in [
        "dev-lightweight-algorithm-not-settled",
        "dev-lightweight-write-outside-modify",
        "dev-lightweight-asis-expand-vs-conflict",
        "dev-lightweight-unsupported-completion-claim",
        "dev-lightweight-capability-floor-extra-ok",
    ]:
        assert required_id in ids
    assert len(cases) >= 17
    prompts = "\n".join(case["prompt"] for case in cases)
    expected = "\n".join(case["expected_output"] for case in cases)
    for token in [
        "lightweight",
        "contradicts",
        "failing test",
        "bug",
        "multi-repository",
        "Tests pass",
        "configuration-only",
        "relevant authority",
        "none relevant",
        "durable update",
        "algorithm is not yet chosen",
        "write outside",
        "intended checks",
        "stronger model",
    ]:
        assert token in prompts
    for token in [
        "Truth Basis",
        "conflict_status",
        "GROUND",
        "root-cause",
        "test-oracle",
        "knowledge_disposition",
        "does not force TDD",
        "silently widening debugging scope",
        "ks-what-is-helpful",
        "lightweight completion owner",
        "no-write",
        "does not require a settled implementation strategy",
        "not completion evidence",
        "Capability is a floor",
        "presence is not executed agent-behavior proof",
    ]:
        assert token in expected


def test_create_skill_contract_uses_pressure_first_iteration_and_real_gates() -> None:
    text = skill_text("wb-create-skill")

    for token in [
        "observable behavior",
        "pressure evals before",
        "baseline",
        "record the gap",
        "smallest change",
        "adversarial edge",
        "compress",
        "mechanical tests",
        "register or install",
        "references/evals/",
        "evals.json",
        "scenario storage",
        "automated LLM harness",
        "WHEN",
    ]:
        assert token in text
