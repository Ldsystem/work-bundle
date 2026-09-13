"""Packaging/discovery checks only; semantic behavior uses agent-run scenarios."""
from pathlib import Path
import json
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
NAME = "dev-resolve-blocking-fact"


def test_skill_package_is_compact_and_has_resolvable_guidance():
    folder = ROOT / "skills" / NAME
    text = (folder / "SKILL.md").read_text()
    metadata = yaml.safe_load(text.split("---", 2)[1])
    assert metadata["name"] == NAME
    assert 0 < len(metadata["description"]) <= 1024
    assert len(text.split()) < 650
    assert (folder / "references/metadata-resolution.md").is_file()
    assert not list(folder.rglob("*.py"))
    assert not list(folder.rglob("*.sh"))


def test_builtin_discovery_validation_and_targeted_install(tmp_path):
    def invoke(*args):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin/work-bundle-skill"), *args],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)

    assert NAME in invoke("list")["skills"]
    assert invoke("validate", "--name", NAME)["ok"]
    invoke("--home", str(tmp_path), "enable", "--name", NAME)
    installed = tmp_path / ".agents/skills" / NAME
    assert installed.is_symlink()
    assert installed.resolve() == ROOT / "skills" / NAME
    assert list(installed.parent.iterdir()) == [installed]


def test_pressure_scenarios_are_well_formed_not_semantic_proof():
    cases = json.loads((ROOT / "references/evals/blocking-fact/evals.json").read_text())["evals"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert len(cases) == 9
    assert all(case["prompt"] and case["expected_output"] for case in cases)


def test_existing_admission_consumes_targeted_resolution_and_exemptions(tmp_path):
    # Decisions below are supplied fixture facts, not diagnoses made by this test.
    sys.path.insert(0, str(ROOT / "scripts/orchestration"))
    import bounded_closure

    metadata = tmp_path / ".work-bundle/project.yaml"
    metadata.parent.mkdir()
    for name in ("b1.md", "b2.md"):
        (tmp_path / name).write_text("# Selected product requirements\n")
    old_closure = {"origin_plan": "old-flow", "closure_outcome": "closed_with_blockers"}
    control = {
        "schema_version": 1,
        "post_execution_review_round_limit": 5,
        "blockers": [
            {"id": "B1", "status": "active", "specification": "b1.md", "reason": "missing receipt"},
            {"id": "B2", "status": "active", "specification": "b2.md", "reason": "unrelated"},
        ],
        "closed_flows": [old_closure.copy()],
        "implementation_exemptions": [],
    }
    data = {"metadata_version": 4, "orchestration_control": control, "custom": {"keep": True}}

    def save():
        metadata.write_text(yaml.safe_dump(data))

    def admit(operation="ordinary_new", flow="repair-B1"):
        return bounded_closure.require_orchestration_admission(tmp_path, operation=operation, flow_id=flow)

    save()
    assert admit("read_only")["status"] == "admitted"
    control["implementation_exemptions"] = [{"blocker_id": "B1", "flow_id": "repair-B1", "status": "active"}]
    save()
    with pytest.raises(bounded_closure.BoundedClosureError, match="blocker=B2"):
        admit()
    # Supply a later agent decision only for B1, without a receipt or review file.
    control["implementation_exemptions"] = []
    control["blockers"][0].update(status="resolved", resolution={"judgment": "semantic pass"})
    save()
    with pytest.raises(bounded_closure.BoundedClosureError, match="blocker=B2"):
        admit()
    reread = yaml.safe_load(metadata.read_text())
    assert reread["custom"] == {"keep": True}
    assert reread["orchestration_control"]["closed_flows"] == [old_closure]
    # An independent explicit exemption for B2 demonstrates B1 no longer gates admission.
    control["implementation_exemptions"] = [{"blocker_id": "B2", "flow_id": "repair-B1", "status": "active"}]
    save()
    assert admit()["status"] == "admitted"
    with pytest.raises(bounded_closure.BoundedClosureError, match="blocker=B2"):
        admit(flow="unrelated-flow")
