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
        assert "reslice only the affected region" in text
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
    expected_ids = {f"PD-{number:02d}" for number in (*range(1, 8), 9, 10)}

    assert expected_ids <= cases.keys()

    combined = {
        case_id: f"{cases[case_id]['prompt']} {cases[case_id]['expected_output']}"
        for case_id in expected_ids
    }
    assert "task-count target" in combined["PD-01"]
    assert "authoritative production path" in combined["PD-02"]
    assert "repair frontier" in combined["PD-03"]
    assert "coherent mechanical increment" in combined["PD-04"]
    assert "actual barrier" in combined["PD-05"]
    assert "complete, nonredundant" in combined["PD-06"]
    assert "return to the plan" in combined["PD-07"]
    assert "speculative" in combined["PD-09"]
    assert "independently owned entry points" in combined["PD-10"]
