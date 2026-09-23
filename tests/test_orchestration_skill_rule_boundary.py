from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE5_SKILLS = ("orch-execute-plan", "orch-create-handoff", "orch-review-plan")


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_stage5_skills_reference_existing_rules_without_local_loading_algorithm() -> None:
    for name in STAGE5_SKILLS:
        text = read(f"skills/{name}/SKILL.md")
        assert "## Rule Loading (mandatory)" not in text
        for rule_path in re.findall(r"`(rules/orchestration/[^`]+)`", text):
            assert (REPO_ROOT / rule_path).is_file(), f"{name}: {rule_path}"


def test_stage5_skills_end_with_observable_self_checks() -> None:
    for name in STAGE5_SKILLS:
        text = read(f"skills/{name}/SKILL.md")
        self_check = text.rsplit("## Self-check", 1)[-1]
        assert text.count("## Self-check") == 1
        assert self_check.count("- [ ]") >= 4
        assert len(self_check) < 2200


def test_execute_skill_separates_executor_facts_from_reviewer_verdict() -> None:
    text = read("skills/orch-execute-plan/SKILL.md")
    for token in (
        "compiled Truth Basis",
        "path-sorted changed-path manifest",
        "executor-result-v1",
        "distinct reviewer",
        "green tests do not substitute",
        "No receipt, history replay",
    ):
        assert token in text
    assert "does not accept the product" in text
    worker_section, controller_section = text.split("## Controller continuation", 1)
    assert "The controller/orchestrator assesses" not in worker_section
    assert "the controller sends" in controller_section


def test_handoff_skill_owns_only_canonical_factual_continuation() -> None:
    text = read("skills/orch-create-handoff/SKILL.md")
    for token in (
        "executor-result-v1",
        "exact plan/task bindings",
        "Validate the full semantic input",
        "repair the active YAML artifact atomically at the same canonical identity",
        "derived index",
        "lightweight integrity checks",
        "partial effect",
    ):
        assert token in text
    assert "do not create orchestration handoffs" in text


def test_review_skill_separates_product_review_from_compact_final_audit() -> None:
    text = read("skills/orch-review-plan/SKILL.md")
    for token in (
        "exact frozen commit or worktree candidate",
        "Passing tests cannot hide omitted behavior",
        "implementation-review-v3",
        "accepted-task-result-v2",
        "final-workflow-review-v1",
        "Do not reread source for code quality or repeat implementation review",
    ):
        assert token in text


def test_active_rules_keep_semantic_judgment_agent_owned_and_non_recursive() -> None:
    paths = (
        "rules/orchestration/orch-handoff-required.md",
        "rules/orchestration/orch-review-completion.md",
        "rules/orchestration/orch-bounded-closure.md",
        "rules/orchestration/orch-orchestration-boundary.md",
    )
    corpus = "\n".join(read(path) for path in paths).lower()
    for token in (
        "executor-result",
        "implementation review",
        "accepted task result",
        "final workflow review",
        "product decision",
    ):
        assert token in corpus
    for retired in (
        "begin-review-round",
        "publication receipt",
        "current-authority sidecar",
    ):
        assert retired not in corpus
    assert "do not infer admission from review history" in corpus


def test_bounded_closure_rule_selection_depends_only_on_admission_and_blockers() -> None:
    text = read("rules/orchestration/orch-bounded-closure.md")
    metadata = yaml.safe_load(text.split("---", 2)[1])
    triggers = "\n".join(metadata["applies_when"]).lower()
    assert "review round" not in triggers
    assert "fifth" not in triggers
    assert "multi-round" not in triggers
    assert "admission" in triggers
    assert "blocker" in triggers


def test_stage_events_are_diagnostic_only() -> None:
    text = read("scripts/work-bundle/stage_events.py")
    for token in ("operational_metadata_only", "finding_recorded", "artifact_digest"):
        assert token in text
    assert "never issue or reinterpret a" in text
    assert "product-review verdict, artifact qualification, or lifecycle decision" in text


def test_instruction_rules_keep_controller_authority_and_claim_boundaries_explicit() -> None:
    boundary = read("rules/orchestration/orch-orchestration-boundary.md")
    review = read("rules/orchestration/orch-review-completion.md")
    verification = read("rules/verification-evidence-before-claim.md")
    preflight = read("rules/work-bundle/wb-project-context-preflight.md")

    assert "scope, delegation, repair routing, continuation, acceptance, re-entry" in boundary
    assert "does not direct workers, expand scope, deliver changes" in boundary
    assert "reviewer-proposed scope changes" in review
    assert "explicit user authority" in review
    assert "semantic product judgment or a mechanical/workflow fact" in verification
    assert "deterministic helper" in verification and "manufacture or veto" in verification
    assert "Inspect additional members only when" in preflight
    assert "makes candidate identity ambiguous" in preflight


def test_orchestration_pressure_cases_cover_authority_accuracy_and_write_discipline() -> None:
    data = json.loads(read("references/evals/orchestration/evals.json"))
    numbered = {item["id"]: item for item in data["evals"]}
    scenarios = {item["id"]: item for item in data["v4_evals"]}

    assert "unrelated path" in numbered[15]["expected_output"]
    assert "not an automatic semantic veto" in numbered[16]["expected_output"]
    assert "Preserves any already-supported product review judgment" in numbered[64]["expected_output"]
    assert "does not retroactively manufacture or veto product acceptance" in numbered[64]["expected_output"]

    expected = {
        "v4-controller-retains-scope-and-worker-routing": (
            "review as advice",
            "prevents the reviewer from directing the worker or expanding scope",
            "required user decision",
        ),
        "v4-product-correct-supporting-state-defect": (
            "supporting-state defects separately",
            "cannot manufacture or veto acceptance",
        ),
        "v4-strict-prewrite-light-postwrite": (
            "before the authoritative mutation",
            "lightweight integrity checks afterward",
            "rather than a semantic verdict",
        ),
        "v4-explicit-delivery-authority": (
            "withholds every delivery action",
            "explicit user authority",
        ),
    }
    for scenario_id, phrases in expected.items():
        output = scenarios[scenario_id]["expected_output"]
        for phrase in phrases:
            assert phrase in output


def test_instruction_audit_reports_current_rule_loading_heading(tmp_path: Path) -> None:
    for name in ("one", "two"):
        skill = tmp_path / "skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            f"---\nname: {name}\ndescription: Test skill.\n---\n\n"
            "## Rule Loading\n\nRead indexed rules.\n",
            encoding="utf-8",
        )
    result = subprocess.run(
        ["python3", "scripts/wb.py", "instruction-audit", "--root", str(tmp_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["repeated_rule_loading_blocks"][0]["occurrences"] == 2


def test_current_references_do_not_assert_toolkit_role_profiles() -> None:
    workflow = read("references/assets/keep-summarizing/workflow.md")
    scenarios = json.loads(read("references/evals/orchestration/evals.json"))
    assert "role profiles" not in workflow.lower()
    scenario_ids = {item["id"] for item in scenarios["v4_evals"]}
    assert "v4-stable-role-profile-adversarial-boundary" not in scenario_ids
    assert "v4-external-skill-role-identifiers-without-profiles" in scenario_ids
