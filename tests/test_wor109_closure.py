from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evals" / "wor109"
spec = importlib.util.spec_from_file_location("wor109_verify", EVAL / "verify.py")
assert spec and spec.loader
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

def test_wor109_closure_has_exact_fixture_and_manifest_identity() -> None:
    assert verifier.verify() == {"evaluation_id": "wor109-review-stable-orchestration-v1", "fixtures": 14, "changed_surfaces": 35, "verdict": "accepted"}

def test_wor109_fixture_registry_is_closed_and_unique() -> None:
    payload = json.loads((EVAL / "fixtures.json").read_text(encoding="utf-8"))
    assert tuple(row["id"] for row in payload["fixtures"]) == tuple(f"PD-{i:02d}" for i in range(1, 15))
    assert len({row["pytest_node"] for row in payload["fixtures"]}) == 14

def test_wor109_tampered_fixture_is_rejected(tmp_path: Path) -> None:
    payload = json.loads((EVAL / "fixtures.json").read_text(encoding="utf-8"))
    payload["fixtures"] = payload["fixtures"][:-1]
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="exactly PD-01..PD-14"):
        verifier.verify(fixtures_path=path)

def test_wor109_tampered_manifest_is_rejected(tmp_path: Path) -> None:
    payload = copy.deepcopy(json.loads((EVAL / "migration-impact.json").read_text(encoding="utf-8")))
    payload["exclusions"]["WOR-107"]["authorized"] = True
    path = tmp_path / "migration-impact.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="exclusion authorization"):
        verifier.verify(migration_path=path)
