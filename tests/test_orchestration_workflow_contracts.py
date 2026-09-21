from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

from doctor import cmd_doctor  # noqa: E402
import dispatcher  # noqa: E402


CURRENT_STAGE5_COMMANDS = {
    "write-executor-result",
    "list-executor-results",
    "transition-executor-result",
    "index-executor-results",
    "build-implementation-review-candidate",
    "write-implementation-review",
    "list-implementation-reviews",
    "write-accepted-task-result",
    "list-accepted-task-results",
    "write-final-workflow-review",
    "list-final-workflow-reviews",
    "finalize-reviewed-plan",
}

RETIRED_COMMANDS = {
    "write-handoff",
    "list-handoffs",
    "set-handoff-status",
    "index-handoffs",
    "build-review-package",
    "validate-executor-result",
    "observe-task-validation",
    "begin-review-round",
    "complete-review-round",
    "review-round-status",
    "archive-plan",
    "finalize-accepted-plan",
    "finalize-with-blockers",
}


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_current_dispatcher_exposes_stage5_cutover_without_legacy_aliases() -> None:
    assert CURRENT_STAGE5_COMMANDS <= dispatcher.RECOGNIZED_COMMANDS
    assert RETIRED_COMMANDS.isdisjoint(dispatcher.RECOGNIZED_COMMANDS)
    help_text = dispatcher.build_parser().format_help()
    for command in CURRENT_STAGE5_COMMANDS:
        assert command in help_text
    for command in RETIRED_COMMANDS:
        assert command not in help_text


def test_current_workflow_defines_direct_review_and_compact_final_audit() -> None:
    workflow = read("references/assets/orchestration/workflow.md").lower()
    for family in (
        "executor-result-v1",
        "implementation-review-v3",
        "accepted-task-result-v2",
        "final-workflow-review-v1",
    ):
        assert family in workflow
    assert "task review, a distinct reviewer compares the actual candidate" in workflow
    assert "integrated review compares the exact candidate with every planned feature" in workflow
    assert "does not reread source for code quality or repeat implementation review" in workflow
    for retired in (
        "reviewer-native-receipt",
        "reviewer-process-receipt",
        "current-authority sidecar",
        "begin-review-round",
        "legacy-status-overrides",
    ):
        assert retired not in workflow


def test_executor_result_contract_is_schema_owned_and_non_accepting() -> None:
    contract = read("references/assets/orchestration/contract/handoff-executor-result-v1.md").lower()
    assert "executor-result-v1" in contract
    assert "canonical" in contract
    assert "product verdict" in contract
    assert "filename inference" in contract and "unsupported" in contract
    assert "legacy statuses" in contract


def test_current_orchestration_evals_cover_stage5_boundary() -> None:
    cases = json.loads(read("references/evals/orchestration/evals.json"))["evals"]
    corpus = "\n".join(
        f"{case.get('prompt', '')}\n{case.get('expected_output', '')}" for case in cases
    ).lower()
    for term in (
        "executor-result-v1",
        "implementation-review-v3",
        "accepted-task-result-v2",
        "final-workflow-review-v1",
        "frozen worktree",
    ):
        assert term in corpus


def test_current_doctor_accepts_the_repaired_contract(capsys: pytest.CaptureFixture[str]) -> None:
    cmd_doctor(argparse.Namespace())
    assert capsys.readouterr().out.strip() == "ok"
