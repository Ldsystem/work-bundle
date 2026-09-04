from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_ROOT = REPO_ROOT.parent / ".work-bundle"
MCP_ROOT = REPO_ROOT.parents[2] / "work-bundle-mcp"


NATIVE_GROUPS = (
    (
        "review-routing",
        "tests/test_orchestration_reviews.py::test_api_001_rejects_unclassified_wrong_layer_and_unauthorized_blocking_advisory",
        "tests/test_orchestration_reviews.py::test_api_001_reslice_pauses_repeated_expansion_and_preserves_evidence",
        "tests/test_orchestration_reviews.py::test_api_002_requires_independent_direct_accepted_review_and_current_target",
    ),
    (
        "reviewer-isolation",
        "tests/test_reviewer_workspace.py::test_bounded_read_search_and_validators_are_allowed",
        "tests/test_reviewer_workspace.py::test_reviewer_operations_mechanically_deny_forbidden_effects",
        "tests/test_reviewer_workspace.py::test_every_denied_request_appends_unique_privacy_safe_event",
    ),
    (
        "evaluation-identity",
        "tests/test_orchestration_evaluations.py::test_pre_invocation_freeze_computes_exact_sources_and_excludes_result_fields",
        "tests/test_orchestration_evaluations.py::test_component_drift_marks_stale_appends_and_preserves_raw",
        "tests/test_orchestration_evaluations.py::test_packaging_only_advance_preserves_source_observation",
    ),
    (
        "completion-provenance",
        "tests/test_completion_provenance.py::test_observation_reuse_requires_complete_identity_and_freshness",
        "tests/test_completion_provenance.py::test_predecessor_extension_uses_public_contract_not_byte_identity",
        "tests/test_completion_provenance.py::test_kernel_failure_owner_lifecycle_preserves_origin_and_blocks_early_release",
        "tests/test_completion_provenance.py::test_failure_resume_and_release_preserve_first_owner_and_emit_native_events",
    ),
    (
        "stage-events",
        "tests/test_stage_events.py::test_api_004_privacy_filter_fails_closed_without_echoing_content",
        "tests/test_stage_events.py::test_api_004_append_is_prefix_preserving_unique_and_monotonic",
        "tests/test_stage_events.py::test_api_004_query_and_export_preserve_order_and_do_not_mutate",
    ),
    (
        "deferred-remote",
        "tests/test_multi_repository_member.py::test_deferred_remote_apply_replay_and_attach_are_portable_and_idempotent",
        "tests/test_multi_repository_member.py::test_deferred_remote_composite_attach_rejects_external_git_common_dir",
    ),
    (
        "semantic-capabilities",
        "tests/test_capability_index.py::test_retrieval_filters_authority_lifecycle_and_freshness",
        "tests/test_capability_index.py::test_retrieval_uses_aliases_and_optional_domain_hints",
        "tests/test_capability_index.py::test_traversal_enforces_node_budget_and_records_frontier",
    ),
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], text=True, capture_output=True, check=True
    ).stdout.strip()


def _repository_identity(root: Path) -> dict[str, str] | None:
    if not (root / ".git").exists():
        return None
    return {
        "head": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "status": _git(root, "status", "--porcelain=v1", "--untracked-files=all"),
    }


def _control_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted((CONTROL_ROOT / "orchestration").rglob("*")):
        if path.is_file() and not path.is_symlink():
            digest.update(path.relative_to(CONTROL_ROOT).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\n")
    return digest.hexdigest()


def native_evidence_chain() -> list[dict[str, str | int]]:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    evidence: list[dict[str, str | int]] = []
    for group in NATIVE_GROUPS:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *group[1:]],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        output = completed.stdout + completed.stderr
        if completed.returncode != 0:
            raise AssertionError(f"native group {group[0]} failed:\n{output}")
        evidence.append(
            {
                "group": group[0],
                "exit_code": completed.returncode,
                "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            }
        )
    verified = subprocess.run(
        [
            sys.executable,
            "evals/wor105/verify.py",
            "--manifest",
            "evals/wor105/freeze-manifest.json",
            "--results",
            "evals/wor105/results.jsonl",
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout) == {"passed": 12, "total": 12, "verdict": "accepted"}
    evidence.append(
        {
            "group": "adversarial-replay",
            "exit_code": verified.returncode,
            "output_sha256": hashlib.sha256(verified.stdout.encode()).hexdigest(),
        }
    )
    return evidence


def native_dogfood_lifecycle() -> dict[str, object]:
    transition = yaml.safe_load(
        (CONTROL_ROOT / "orchestration/docs/wor105/native-transition-record.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert transition["enforcement_transition"] == "bootstrap_policy_to_native"
    assert transition["transition_task"] == "task-b06r"
    assert transition["excluded_work"] == ["WOR-66", "WOR-79", "WOR-107", "work-bundle-mcp mutation"]

    source_before = _repository_identity(REPO_ROOT)
    mcp_before = _repository_identity(MCP_ROOT)
    control_before = _control_digest()
    evidence = native_evidence_chain()
    assert _repository_identity(REPO_ROOT) == source_before
    assert _repository_identity(MCP_ROOT) == mcp_before
    assert _control_digest() == control_before
    assert len(evidence) == 8 and all(item["exit_code"] == 0 for item in evidence)
    return {
        "enforcement_mode": "native",
        "transition_tree": transition["accepted_tree"],
        "evidence": evidence,
        "excluded_work_preserved": True,
    }


def test_native_dogfood_lifecycle() -> None:
    result = native_dogfood_lifecycle()
    assert result["enforcement_mode"] == "native"
    assert result["excluded_work_preserved"] is True
