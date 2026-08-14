from __future__ import annotations

from pathlib import Path
import json


REPO_ROOT = Path(__file__).resolve().parents[1]


def skill_text(name: str) -> str:
    return (REPO_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


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
    ]:
        assert token in text


def test_development_pressure_evals_cover_grounding_and_adversarial_boundary() -> None:
    cases = json.loads(
        (REPO_ROOT / "references/evals/development/evals.json").read_text(encoding="utf-8")
    )["evals"]
    assert len(cases) >= 6
    prompts = "\n".join(case["prompt"] for case in cases)
    expected = "\n".join(case["expected_output"] for case in cases)
    for token in ["lightweight", "contradicts", "failing test", "bug", "Tests pass", "configuration-only"]:
        assert token in prompts
    for token in [
        "Truth Basis",
        "conflict_status",
        "GROUND",
        "root-cause",
        "test-oracle",
        "knowledge_disposition",
        "does not force TDD",
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
