from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))
import evaluation_identity  # noqa: E402

from evaluation_identity import (  # noqa: E402
    EvaluationIdentityError,
    complete_evaluation_identity,
    freeze_evaluation_identity,
    invalidate_changed_components,
    validate_evaluation_transition,
)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=True).stdout.strip()


def test_validation_source_identity_excludes_observation_artifacts(evaluator):
    root = evaluator["root"]
    before = evaluation_identity.validation_source_identity(root)
    assert before["tree"] == git(root, "rev-parse", "HEAD^{tree}")
    receipt = root / ".work-bundle/runtime/observations/result.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"passed":true}')
    commit_all(evaluator, "record observation artifact")
    assert evaluation_identity.validation_source_identity(root) == before
    receipt.write_text('{"passed":true,"summary":"reworded"}')
    assert evaluation_identity.validation_source_identity(root) == before


def test_validation_source_identity_covers_dirty_untracked_and_declared_ignored_inputs(evaluator):
    root = evaluator["root"]
    before = evaluation_identity.validation_source_identity(root)
    evaluator["runner"].write_text("changed source")
    dirty = evaluation_identity.validation_source_identity(root)
    assert dirty != before
    extra = root / "new-helper.py"
    extra.write_text("new task-created helper")
    assert evaluation_identity.validation_source_identity(root) != dirty
    git(root, "config", "core.excludesFile", str(root.parent / "ignore-patterns"))
    (root.parent / "ignore-patterns").write_text("ignored-input.txt\n")
    ignored = root / "ignored-input.txt"
    ignored.write_text("v1")
    first = evaluation_identity.validation_source_identity(root, input_paths=["ignored-input.txt"])
    ignored.write_text("v2")
    assert evaluation_identity.validation_source_identity(root, input_paths=["ignored-input.txt"]) != first


def test_validation_source_identity_preserves_every_index_stage(evaluator):
    root = evaluator["root"]
    first = git(root, "rev-parse", "HEAD:runner.py")
    other = git(root, "rev-parse", "HEAD:verifier.py")
    def unmerged(ours):
        entries = f"0 {'0' * 40}\trunner.py\n100644 {first} 1\trunner.py\n100644 {ours} 2\trunner.py\n100644 {other} 3\trunner.py\n"
        subprocess.run(["git", "-C", str(root), "update-index", "--index-info"], input=entries, text=True, check=True)
    unmerged(first)
    before = evaluation_identity.validation_source_identity(root)
    unmerged(other)
    assert evaluation_identity.validation_source_identity(root) != before


def commit_all(evaluator: dict[str, Path], message: str) -> None:
    git(evaluator["root"], "add", ".")
    git(evaluator["root"], "commit", "-q", "-m", message)


@pytest.fixture
def evaluator(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "product"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "config", "user.name", "Tests")
    contents = {
        "spec.md": "accepted specification\n", "task.md": "task b03\n",
        "instructions.md": "run exact fixtures\n", "fixture.json": '{"case":"ADV-05"}\n',
        "runner.py": "def run():\n    return {'actual': 'accepted'}\n",
        "verifier.py": "def verify():\n    return True\n",
        "semantic.json": '{"schema":"semantic-v1"}\n',
        "evidence.json": '{"capabilities":["direct"]}\n',
        "invocation.json": '{"request":"case"}\n', "response.json": '{"actual":"accepted"}\n',
        "trace.json": '{"events":[]}\n', "adjudication.json": '{"verdict":"accepted"}\n',
    }
    for name, content in contents.items():
        (root / name).write_text(content, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "fixture")
    return {"root": root, **{name.split(".")[0]: root / name for name in contents}}


def freeze(evaluator: dict[str, Path], *, frozen_at: str = "2026-09-04T01:00:00Z"):
    return freeze_evaluation_identity(
        evaluation_id="evaluation-b03-001", product_root=evaluator["root"],
        specification_id="spec-20260904-001", specification_revision="1.5",
        specification_file=evaluator["spec"], task_files=[evaluator["task"]],
        instruction_files=[evaluator["instructions"]], fixture_files=[evaluator["fixture"]],
        runner_file=evaluator["runner"], runner_entrypoint="run",
        verifier_file=evaluator["verifier"], verifier_entrypoint="verify",
        semantic_schema_files=[evaluator["semantic"]], evidence_capability_files=[evaluator["evidence"]],
        frozen_at=frozen_at,
    )


def complete(evaluator: dict[str, Path], frozen=None):
    return complete_evaluation_identity(
        frozen or freeze(evaluator), invocation_file=evaluator["invocation"],
        raw_response_file=evaluator["response"], raw_trace_file=evaluator["trace"],
        adjudication_file=evaluator["adjudication"], invocation_started_at="2026-09-04T01:01:00Z",
        completed_at="2026-09-04T01:02:00Z",
    )


def test_pre_invocation_freeze_computes_exact_sources_and_excludes_result_fields(evaluator: dict[str, Path]) -> None:
    frozen = freeze(evaluator)
    payload = frozen.to_dict()
    assert payload["frozen_at"] == "2026-09-04T01:00:00Z"
    assert payload["product"]["revision"] == git(evaluator["root"], "rev-parse", "HEAD")
    assert payload["product"]["tree"] == git(evaluator["root"], "rev-parse", "HEAD^{tree}")
    assert set(payload) == {"evaluation_id", "frozen_at", "product", "specification", "task_set", "instruction", "fixture", "runner", "verifier", "semantic_schema", "evidence_capabilities"}
    assert not {"invocation_digest", "raw_response_digest", "raw_trace_digest", "adjudication_digest", "packaging"} & payload.keys()


def test_freeze_rejects_missing_exact_file_and_post_freeze_source_drift(evaluator: dict[str, Path]) -> None:
    original = evaluator["fixture"]
    evaluator["fixture"] = evaluator["root"] / "missing.json"
    with pytest.raises(EvaluationIdentityError, match="exact file"):
        freeze(evaluator)
    evaluator["fixture"] = original
    frozen = freeze(evaluator)
    evaluator["fixture"].write_text('{"case":"changed"}\n', encoding="utf-8")
    with pytest.raises(EvaluationIdentityError, match="drift"):
        complete(evaluator, frozen)


@pytest.mark.parametrize("mutation", ["tracked", "untracked"])
def test_freeze_rejects_dirty_or_untracked_product_worktree(evaluator: dict[str, Path], mutation: str) -> None:
    if mutation == "tracked":
        evaluator["invocation"].write_text('{"request":"changed"}\n', encoding="utf-8")
    else:
        (evaluator["root"] / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    with pytest.raises(EvaluationIdentityError, match="clean.*worktree"):
        freeze(evaluator)


@pytest.mark.parametrize("runner_source", [
    "from verifier import verify\ndef run():\n    return verify()\n",
    "import grading\ndef run():\n    return True\n",
    "import importlib\ndef run():\n    return importlib.import_module('verifier').verify()\n",
    "def grade_result():\n    return True\ndef run():\n    return grade_result()\n",
    "def run():\n    return expected_decision == actual_decision\n",
])
def test_ast_rejects_verifier_dependency_and_grading_semantics(evaluator: dict[str, Path], runner_source: str) -> None:
    evaluator["runner"].write_text(runner_source, encoding="utf-8")
    commit_all(evaluator, "malicious runner")
    with pytest.raises(EvaluationIdentityError, match="runner.*(verifier|grading)"):
        freeze(evaluator)


def test_ast_rejects_transitive_dependency_and_requires_separate_entrypoint(evaluator: dict[str, Path]) -> None:
    helper = evaluator["root"] / "helper.py"
    helper.write_text("from verifier import verify\n", encoding="utf-8")
    evaluator["runner"].write_text("import helper\ndef run():\n    return True\n", encoding="utf-8")
    commit_all(evaluator, "transitive verifier dependency")
    with pytest.raises(EvaluationIdentityError, match="runner.*verifier"):
        freeze(evaluator)
    evaluator["runner"].write_text("def run():\n    return True\n", encoding="utf-8")
    commit_all(evaluator, "restore runner")
    evaluator["verifier"] = evaluator["runner"]
    with pytest.raises(EvaluationIdentityError, match="separate entrypoint"):
        freeze(evaluator)


@pytest.mark.parametrize("runner_import", ["import pkg.helper", "from pkg import helper"])
def test_ast_recurses_into_package_module_imports(evaluator: dict[str, Path], runner_import: str) -> None:
    package = evaluator["root"] / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helper.py").write_text("from verifier import verify\ndef invoke():\n    return verify()\n", encoding="utf-8")
    evaluator["runner"].write_text(f"{runner_import}\ndef run():\n    return True\n", encoding="utf-8")
    commit_all(evaluator, "package verifier dependency")
    with pytest.raises(EvaluationIdentityError, match="runner.*verifier"):
        freeze(evaluator)


def test_completion_binds_outputs_and_timestamps_to_prior_freeze(evaluator: dict[str, Path]) -> None:
    frozen = freeze(evaluator)
    completed = complete(evaluator, frozen)
    assert completed.status == "valid"
    assert completed.freeze_digest == frozen.freeze_digest
    assert completed.invocation_started_at == "2026-09-04T01:01:00Z"
    assert completed.completed_at == "2026-09-04T01:02:00Z"
    assert completed.raw_response_digest and completed.raw_trace_digest and completed.adjudication_digest
    assert completed.to_api_dict()["product"] == frozen.to_dict()["product"]
    with pytest.raises(EvaluationIdentityError, match="prior freeze"):
        complete_evaluation_identity(None, invocation_file=evaluator["invocation"], raw_response_file=evaluator["response"], raw_trace_file=evaluator["trace"], adjudication_file=evaluator["adjudication"], invocation_started_at="2026-09-04T01:01:00Z", completed_at="2026-09-04T01:02:00Z")


def test_completion_orders_fractional_timestamps_by_parsed_instant(evaluator: dict[str, Path]) -> None:
    frozen = freeze(evaluator, frozen_at="2026-09-04T01:00:00.1Z")
    completed = complete_evaluation_identity(
        frozen, invocation_file=evaluator["invocation"], raw_response_file=evaluator["response"],
        raw_trace_file=evaluator["trace"], adjudication_file=evaluator["adjudication"],
        invocation_started_at="2026-09-04T01:00:00.10Z", completed_at="2026-09-04T01:00:00.100Z",
    )
    assert completed.status == "valid"


def test_component_drift_marks_stale_appends_and_preserves_raw(evaluator: dict[str, Path]) -> None:
    previous = complete(evaluator)
    evaluator["instructions"].write_text("changed instructions\n", encoding="utf-8")
    commit_all(evaluator, "instruction drift")
    current = invalidate_changed_components(previous, freeze(evaluator, frozen_at="2026-09-04T02:00:00Z"), affected_run_ids=["run-001"], reason="instruction changed", timestamp="2026-09-04T02:01:00Z", invalidation_id="invalidation-001")
    assert current.status == "stale"
    assert current.invalidations[-1]["changed_component"] == "instruction"
    assert current.raw_response_digest == previous.raw_response_digest
    assert current.raw_trace_digest == previous.raw_trace_digest
    validate_evaluation_transition(previous, current)


@pytest.mark.parametrize(
    ("component", "source_key"),
    [
        ("product", "root"), ("specification", "spec"), ("tasks", "task"),
        ("instruction", "instructions"), ("fixture", "fixture"), ("runner", "runner"),
        ("verifier", "verifier"), ("semantic_schema", "semantic"),
        ("evidence_capabilities", "evidence"),
    ],
)
def test_each_frozen_component_has_independent_append_only_invalidation(
    evaluator: dict[str, Path], component: str, source_key: str,
) -> None:
    previous = complete(evaluator)
    if component == "product":
        (evaluator["root"] / "unrelated.txt").write_text("new product revision\n", encoding="utf-8")
        git(evaluator["root"], "add", "unrelated.txt")
        git(evaluator["root"], "commit", "-q", "-m", "product drift")
    elif component == "runner":
        evaluator[source_key].write_text("def run():\n    return {'actual': 'changed'}\n", encoding="utf-8")
    elif component == "verifier":
        evaluator[source_key].write_text("def verify():\n    return False\n", encoding="utf-8")
    else:
        evaluator[source_key].write_text(f"changed {component}\n", encoding="utf-8")
    if component != "product":
        commit_all(evaluator, f"{component} drift")
    current = invalidate_changed_components(
        previous, freeze(evaluator, frozen_at="2026-09-04T02:00:00Z"),
        affected_run_ids=["run-001"], reason=f"{component} changed",
        timestamp="2026-09-04T02:01:00Z", invalidation_id=f"invalidation-{component}",
    )
    changed_components = [item["changed_component"] for item in current.invalidations]
    assert component in changed_components
    assert changed_components == ["product"] if component == "product" else ["product", component]
    assert current.status == "stale"
    assert current.raw_response_digest == previous.raw_response_digest
    assert current.raw_trace_digest == previous.raw_trace_digest
    validate_evaluation_transition(previous, current)


def test_transition_rejects_history_rewrite_and_unrelated_field_change(evaluator: dict[str, Path]) -> None:
    previous = complete(evaluator)
    evaluator["instructions"].write_text("changed instructions\n", encoding="utf-8")
    commit_all(evaluator, "instruction drift")
    current = invalidate_changed_components(previous, freeze(evaluator, frozen_at="2026-09-04T02:00:00Z"), affected_run_ids=["run-001"], reason="instruction changed", timestamp="2026-09-04T02:01:00Z", invalidation_id="invalidation-001")
    with pytest.raises(EvaluationIdentityError, match="prefix"):
        validate_evaluation_transition(current, replace(current, invalidations=()))
    with pytest.raises(EvaluationIdentityError, match="raw_response_digest"):
        validate_evaluation_transition(current, replace(current, raw_response_digest="f" * 64))


def test_invalid_status_is_reserved_for_evidence_corruption(evaluator: dict[str, Path]) -> None:
    previous = complete(evaluator)
    with pytest.raises(EvaluationIdentityError, match="evidence corruption"):
        validate_evaluation_transition(previous, replace(previous, status="invalid"))


def test_packaging_only_advance_preserves_source_observation(evaluator: dict[str, Path]) -> None:
    previous = complete(evaluator)
    packaging = {"repository": "package", "revision": "e" * 40, "tree": "f" * 40}
    current = invalidate_changed_components(previous, freeze(evaluator, frozen_at="2026-09-04T02:00:00Z"), affected_run_ids=["run-001"], reason="packaging advanced", timestamp="2026-09-04T02:01:00Z", invalidation_id="invalidation-packaging", packaging=packaging)
    assert current.status == "valid" and current.invalidations == ()
    assert current.product == previous.product
    assert current.invocation_digest == previous.invocation_digest
    assert current.raw_response_digest == previous.raw_response_digest
    assert current.packaging == packaging
    validate_evaluation_transition(previous, current)


def test_cli_freeze_computes_inputs_and_transition_requires_prior(evaluator: dict[str, Path]) -> None:
    args = [sys.executable, str(REPO_ROOT / "scripts/wb.py"), "evaluation-identity-freeze", "--evaluation-id", "evaluation-b03-001", "--product-root", str(evaluator["root"]), "--specification-id", "spec-20260904-001", "--specification-revision", "1.5", "--specification-file", str(evaluator["spec"]), "--task-file", str(evaluator["task"]), "--instruction-file", str(evaluator["instructions"]), "--fixture-file", str(evaluator["fixture"]), "--runner-file", str(evaluator["runner"]), "--runner-entrypoint", "run", "--verifier-file", str(evaluator["verifier"]), "--verifier-entrypoint", "verify", "--semantic-schema-file", str(evaluator["semantic"]), "--evidence-capability-file", str(evaluator["evidence"]), "--frozen-at", "2026-09-04T01:00:00Z"]
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "raw_response_digest" not in json.loads(result.stdout)
    no_prior = subprocess.run([sys.executable, str(REPO_ROOT / "scripts/wb.py"), "evaluation-identity-transition"], text=True, capture_output=True, check=False)
    assert no_prior.returncode != 0
    assert "--previous" in no_prior.stderr
