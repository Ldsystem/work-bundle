from __future__ import annotations

import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/work-bundle"))


def fixture(relation="positive", actor="controller"):
    return {"id": relation, "relation": relation, "actor": actor, "stage": "implementation",
            "observable_signals": {"operation": ["edit"]}, "selected_rule_ids": ["example"],
            "carried_rule_ids": ["example"] if actor == "worker" else []}


def test_discovery_fixture_shapes_cover_agent_authored_positive_negative_adjacent_worker():
    from instruction_audit import validate_discovery_fixtures
    payload = {"fixtures": [fixture("positive"), fixture("negative"), fixture("adjacent"), fixture("worker", "worker")]}
    assert validate_discovery_fixtures(payload) == []
    # Meaning of the signals and selected IDs remains with the author/reviewer.
    payload["fixtures"][0]["observable_signals"] = {"operation": ["no matching keyword"]}
    assert validate_discovery_fixtures(payload) == []


def test_discovery_fixture_shape_rejects_invalid_and_duplicate_records():
    from instruction_audit import validate_discovery_fixtures
    item = fixture("worker", "worker")
    item["carried_rule_ids"] = "example"
    failures = validate_discovery_fixtures({"fixtures": [item, item]})
    assert any("duplicate_id" in failure for failure in failures)
    assert any("carried_rule_ids" in failure for failure in failures)
    assert validate_discovery_fixtures({"fixtures": "wrong"})


def test_discovery_fixture_public_route_reports_only_shape(tmp_path):
    import yaml
    root = tmp_path / "toolkit"
    root.mkdir()
    path = tmp_path / "fixtures.yaml"
    path.write_text(yaml.safe_dump({"fixtures": [fixture()]}))
    argv = [sys.executable, str(ROOT / "scripts/wb.py"), "instruction-audit", "--root", str(root),
            "--discovery-fixtures", str(path)]
    result = subprocess.run(argv, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)["discovery_fixtures"]
    assert report == {"status": "shape-valid", "failures": [], "semantic_assessment": "agent-owned"}
    path.write_text("fixtures: wrong\n")
    result = subprocess.run(argv, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)["discovery_fixtures"]["failures"] == ["discovery_fixtures:fixtures_list_required"]


def test_repository_cases_have_valid_shape_and_existing_rule_references():
    import yaml
    from instruction_audit import validate_discovery_fixtures
    payload = yaml.safe_load((ROOT / "tests/fixtures/instruction_discovery_v1.yaml").read_text())
    assert validate_discovery_fixtures(payload) == []
    known = {entry["id"] for entry in yaml.safe_load((ROOT / "rules/index.yaml").read_text())["rules"]}
    assert {case["relation"] for case in payload["fixtures"]} == {"positive", "negative", "adjacent", "worker"}
    for case in payload["fixtures"]:
        assert case["observable_signals"]["prompt"]
        assert set(case["selected_rule_ids"]) <= known
        assert set(case["carried_rule_ids"]) <= known
    # These checks establish fixture integrity, not the meaning of any prompt,
    # applicability decision, or semantic coverage of the instruction corpus.
