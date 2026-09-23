import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_heavy_planning_decomposes_from_production_and_repair_seams() -> None:
    planner = read("skills/orch-create-implementation-plan/SKILL.md")
    rule = read("rules/orchestration/orch-artifact-authoring.md")
    plan = read("references/assets/orchestration/contract/plan-v1.md")
    workflow = read("references/assets/orchestration/workflow.md")

    for text in (planner, rule, plan, workflow):
        assert "minimum orchestration overhead" not in text
        assert "task or phase cardinality" in text
        assert "expected total orchestration cost" in text
        assert "authoritative production path" in text
        assert "production owner" in text
        assert "repair frontier" in text
        assert "speculative" in text
        assert "materially under-decomposed" in text
        assert "reslice only the affected unaccepted authority region" in text
        assert "repeatedly enlarge" in text

    for text in (planner, plan, workflow):
        assert "actual barrier or convergence" in text
        assert "coherent mechanical increment" in text

    assert "helper-only" in planner
    assert "independently owned entry points" in planner
    assert "current repository evidence" in planner


def test_specification_contract_requires_complete_nonredundant_authority() -> None:
    specification = read("skills/orch-create-specification/SKILL.md")

    assert "smallest authoritative specification" not in specification
    assert "complete, nonredundant authoritative specification" in specification
    assert "load-bearing" in specification
    assert "duplicate prose" in specification
    assert "must not be removed merely to make the artifact smaller" in specification


def test_pd_pressure_rows_cover_review_stable_decomposition() -> None:
    payload = json.loads(read("references/evals/orchestration/evals.json"))
    cases = {str(case["id"]): case for case in payload["evals"]}
    expected_ids = {f"PD-{number:02d}" for number in (*range(1, 8), *range(9, 17))}

    assert expected_ids <= cases.keys()

    combined = {
        case_id: f"{cases[case_id]['prompt']} {cases[case_id]['expected_output']}"
        for case_id in expected_ids
    }
    assert "task-count target" in combined["PD-01"]
    assert "authoritative production path" in combined["PD-02"]
    assert "repair frontier" in combined["PD-03"]
    assert "same-owner" in combined["PD-03"]
    assert "coherent mechanical increment" in combined["PD-04"]
    assert "actual barrier" in combined["PD-05"]
    assert "complete, nonredundant" in combined["PD-06"]
    assert "return to the plan" in combined["PD-07"]
    assert "speculative" in combined["PD-09"]
    assert "common oracle and repair path" in combined["PD-10"]
    assert "canonical accepted result" in combined["PD-11"]
    assert "one coherent task" in combined["PD-12"]
    assert "existing stable boundary" in combined["PD-13"]
    assert "Rejects concurrent same-file writers" in combined["PD-14"]
    assert "walking vertical slice" in combined["PD-15"]
    assert "no independently changing axis" in combined["PD-16"]


def test_planning_guidance_separates_ownership_from_bounded_packets() -> None:
    paths = [
        "skills/orch-create-implementation-plan/SKILL.md",
        "rules/orchestration/orch-artifact-authoring.md",
        "references/assets/orchestration/contract/plan-v1.md",
        "references/assets/orchestration/contract/phase-v1.md",
        "references/assets/orchestration/contract/task-v1.md",
        "references/assets/orchestration/workflow.md",
    ]
    texts = {path: read(path) for path in paths}
    for path, content in texts.items():
        assert "production owner" in content, path
        assert "bounded execution packet" in content or "bounded execution packets" in content, path
        assert "accepted result" in content, path
        assert "affected unaccepted authority region" in content or path.endswith("task-v1.md"), path

    planner = texts[paths[0]]
    rule = texts[paths[1]]
    plan = texts[paths[2]]
    workflow = texts[paths[-1]]
    for content in (planner, rule, plan, workflow):
        assert "expected total orchestration cost" in content
        assert "coherent" in content
    assert "walking vertical slice" in planner
    assert "local contract tests" in planner
    assert "reviewer provides advisory" in planner
    assert "controller/orchestrator" in rule
    assert "stable interface" in plan
    assert "Task-size metrics are diagnostic, not gates" in workflow


def test_stage4_contracts_use_schema_owned_yaml_and_direct_semantic_review() -> None:
    planner = read("skills/orch-create-implementation-plan/SKILL.md")
    rule = read("rules/orchestration/orch-artifact-authoring.md")
    workflow = read("references/assets/orchestration/workflow.md")
    contracts = "\n".join(
        read(path)
        for path in [
            "references/assets/orchestration/contract/plan-v1.md",
            "references/assets/orchestration/contract/phase-v1.md",
            "references/assets/orchestration/contract/task-v1.md",
        ]
    )
    for token in ["schema-owned YAML", "root-plan", "phase", "task"]:
        assert token in planner + workflow + contracts
    for token in [
        "distinct reviewer", "verified specification", "ownership", "dependencies",
        "validation", "authority", "scope", "executability",
    ]:
        assert token in planner
    assert "## Self-check" in planner
    assert "Do not create Markdown plan/phase/task compatibility copies" in rule
    assert "tests, doctors, indexes, receipts, handoffs" in planner.lower()
    assert "stage5-required" not in planner


def test_stage4_evals_cover_cutover_semantic_review_and_exact_source_ids() -> None:
    payload = json.loads(read("references/evals/orchestration/evals.json"))
    cases = {str(case["id"]): case for case in payload["evals"]}
    assert {"STG4-01", "STG4-02", "STG4-03", "STG4-04"} <= cases.keys()
    combined = " ".join(
        f"{cases[key]['prompt']} {cases[key]['expected_output']}"
        for key in ("STG4-01", "STG4-02", "STG4-03", "STG4-04")
    )
    for token in ["schema-owned", "distinct semantic reviewer", "REQ-001A", "Stage 5"]:
        assert token in combined
