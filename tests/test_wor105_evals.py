from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess

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


def _manifest_for_current_runner(tmp_path: Path) -> Path:
    manifest = json.loads((EVAL_ROOT / "freeze-manifest.json").read_text(encoding="utf-8"))
    manifest["components"]["runner"]["sha256"] = hashlib.sha256(
        (EVAL_ROOT / "run.py").read_bytes()
    ).hexdigest()
    target = tmp_path / "current-runner-manifest.json"
    target.write_text(json.dumps(manifest), encoding="utf-8")
    return target


def test_frozen_manifest_runs_and_independent_verifier_accepts_twelve(tmp_path: Path) -> None:
    runner = _load("wor105_runner", "run.py")
    verifier = _load("wor105_verifier", "verify.py")
    output = tmp_path / "results.jsonl"
    manifest_path = _manifest_for_current_runner(tmp_path)

    results = runner.run_manifest(manifest_path, output)
    summary = verifier.verify_results(manifest_path, output)

    assert len(results) == 12
    assert summary == {"passed": 12, "total": 12, "verdict": "accepted"}
    adv01 = results[0]
    assert len(adv01["proof"]["denial_classes"]) == 5
    assert len(set(adv01["proof"]["event_ids"])) == 2


def test_independent_verifier_rejects_missing_proof_and_relation_drift(tmp_path: Path) -> None:
    runner = _load("wor105_runner_mutation", "run.py")
    verifier = _load("wor105_verifier_mutation", "verify.py")
    output = tmp_path / "results.jsonl"
    manifest_path = _manifest_for_current_runner(tmp_path)
    runner.run_manifest(manifest_path, output)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    rows[0]["proof"].pop("validator_output_sha256")
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="schema required fields"):
        verifier.verify_results(manifest_path, output)

    runner.run_manifest(manifest_path, output)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    rows[7]["proof"]["reuse_of"] = "different-observation"
    rows[7]["adjudication_sha256"] = hashlib.sha256(
        json.dumps(rows[7]["proof"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises(verifier.VerificationError, match="ADV-08 reuse"):
        verifier.verify_results(manifest_path, output)


def test_verifier_rejects_fixture_or_evaluator_identity_drift(tmp_path: Path) -> None:
    runner = _load("wor105_runner_identity", "run.py")
    verifier = _load("wor105_verifier_identity", "verify.py")
    output = tmp_path / "results.jsonl"
    manifest_path = _manifest_for_current_runner(tmp_path)
    runner.run_manifest(manifest_path, output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"]["fixtures"]["sha256"] = "0" * 64
    drifted = tmp_path / "manifest.json"
    drifted.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(verifier.VerificationError, match="fixture aggregate"):
        verifier.verify_results(drifted, output)


def test_verifier_enforces_normative_result_schema_types(tmp_path: Path) -> None:
    runner = _load("wor105_runner_schema", "run.py")
    verifier = _load("wor105_verifier_schema", "verify.py")
    output = tmp_path / "results.jsonl"
    manifest_path = _manifest_for_current_runner(tmp_path)
    runner.run_manifest(manifest_path, output)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    rows[7]["proof"]["subprocess_invocation_count"] = "1"
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")

    with pytest.raises(verifier.VerificationError, match="schema constant"):
        verifier.verify_results(manifest_path, output)


def test_runner_does_not_import_verifier_or_copy_expected_as_decision() -> None:
    source = (EVAL_ROOT / "run.py").read_text(encoding="utf-8")
    assert "import verify" not in source
    assert 'actual_decision = fixture["expected_decision"]' not in source


def test_runner_invokes_one_native_probe_for_every_fixture(tmp_path: Path, monkeypatch) -> None:
    runner = _load("wor105_runner_native_calls", "run.py")
    calls: list[list[str]] = []

    def observed_run(command, **kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", observed_run)
    results = runner.run_manifest(_manifest_for_current_runner(tmp_path), tmp_path / "results.jsonl")

    assert len(calls) == 12
    assert all(command[:3] == [runner.sys.executable, "-m", "pytest"] for command in calls)
    assert all(item["passed"] for item in results)


def test_runner_rejects_a_probe_that_reports_zero_native_invocations(tmp_path: Path, monkeypatch) -> None:
    runner = _load("wor105_runner_zero_calls", "run.py")
    monkeypatch.setattr(
        runner,
        "_run_native_probe",
        lambda fixture_id: runner.NativeProbe(fixture_id, 0, "", ""),
    )

    with pytest.raises(runner.EvaluationError, match="zero native invocations"):
        runner.run_manifest(_manifest_for_current_runner(tmp_path), tmp_path / "results.jsonl")
