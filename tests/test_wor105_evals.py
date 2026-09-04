from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = REPO_ROOT / "evals" / "wor105"


def _load(name: str, filename: str):
    path = EVAL_ROOT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_manifest_runs_and_independent_verifier_accepts_twelve(tmp_path: Path) -> None:
    runner = _load("wor105_runner", "run.py")
    verifier = _load("wor105_verifier", "verify.py")
    output = tmp_path / "results.jsonl"

    results = runner.run_manifest(EVAL_ROOT / "freeze-manifest.json", output)
    summary = verifier.verify_results(EVAL_ROOT / "freeze-manifest.json", output)

    assert len(results) == 12
    assert summary == {"passed": 12, "total": 12, "verdict": "accepted"}
    adv01 = results[0]
    assert len(adv01["proof"]["denial_classes"]) == 5
    assert len(set(adv01["proof"]["event_ids"])) == 2


def test_independent_verifier_rejects_missing_proof_and_relation_drift(tmp_path: Path) -> None:
    runner = _load("wor105_runner_mutation", "run.py")
    verifier = _load("wor105_verifier_mutation", "verify.py")
    output = tmp_path / "results.jsonl"
    runner.run_manifest(EVAL_ROOT / "freeze-manifest.json", output)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    rows[0]["proof"].pop("validator_output_sha256")
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="proof keys"):
        verifier.verify_results(EVAL_ROOT / "freeze-manifest.json", output)

    runner.run_manifest(EVAL_ROOT / "freeze-manifest.json", output)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    rows[7]["proof"]["reuse_of"] = "different-observation"
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="ADV-08 reuse"):
        verifier.verify_results(EVAL_ROOT / "freeze-manifest.json", output)


def test_verifier_rejects_fixture_or_evaluator_identity_drift(tmp_path: Path) -> None:
    runner = _load("wor105_runner_identity", "run.py")
    verifier = _load("wor105_verifier_identity", "verify.py")
    output = tmp_path / "results.jsonl"
    runner.run_manifest(EVAL_ROOT / "freeze-manifest.json", output)
    manifest = json.loads((EVAL_ROOT / "freeze-manifest.json").read_text(encoding="utf-8"))
    manifest["components"]["fixtures"]["sha256"] = "0" * 64
    drifted = tmp_path / "manifest.json"
    drifted.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(verifier.VerificationError, match="fixture aggregate"):
        verifier.verify_results(drifted, output)


def test_runner_does_not_import_verifier_or_copy_expected_as_decision() -> None:
    source = (EVAL_ROOT / "run.py").read_text(encoding="utf-8")
    assert "import verify" not in source
    assert 'actual_decision = fixture["expected_decision"]' not in source
