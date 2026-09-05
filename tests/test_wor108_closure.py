from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = REPO_ROOT / "evals" / "wor108"
SPEC = importlib.util.spec_from_file_location("wor108_verify", EVAL_ROOT / "verify.py")
assert SPEC is not None and SPEC.loader is not None
wor108_verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wor108_verify)


def test_wor108_closure_registry_has_exact_public_fixture_identities() -> None:
    result = wor108_verify.verify()
    assert result == {
        "evaluation_id": "wor108-legacy-closure-v1",
        "fixtures": 22,
        "changed_surfaces": 39,
        "verdict": "accepted",
    }


def test_wor108_fixture_registry_rejects_missing_identity(tmp_path: Path) -> None:
    fixtures = json.loads((EVAL_ROOT / "fixtures.json").read_text(encoding="utf-8"))
    fixtures["fixtures"] = fixtures["fixtures"][:-1]
    tampered = tmp_path / "fixtures.json"
    tampered.write_text(json.dumps(fixtures), encoding="utf-8")

    with pytest.raises(wor108_verify.VerificationError, match="exactly RF-01..08"):
        wor108_verify.verify(fixtures_path=tampered)


def test_wor108_migration_impact_rejects_final_git_identity(tmp_path: Path) -> None:
    manifest = json.loads((EVAL_ROOT / "migration-impact.json").read_text(encoding="utf-8"))
    tampered_manifest = deepcopy(manifest)
    tampered_manifest["final_tree"] = "0" * 40
    tampered = tmp_path / "migration-impact.json"
    tampered.write_text(json.dumps(tampered_manifest), encoding="utf-8")

    with pytest.raises(wor108_verify.VerificationError, match="closed shape"):
        wor108_verify.verify(migration_path=tampered)
