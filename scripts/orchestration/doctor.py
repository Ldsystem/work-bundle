"""Read-only structural doctor for the current orchestration surface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifact_store import family_policy, load_catalog


CATALOG = (
    Path(__file__).resolve().parents[2]
    / "references/assets/orchestration/contract/artifact-family-catalog-v5.yaml"
)
STAGE5_FAMILIES = (
    "executor-result",
    "implementation-review",
    "accepted-task-result",
    "final-workflow-review",
)
CURRENT_COMMANDS = {
    "write-executor-result", "list-executor-results", "transition-executor-result",
    "index-executor-results", "build-implementation-review-candidate",
    "write-implementation-review", "list-implementation-reviews",
    "write-accepted-task-result", "list-accepted-task-results",
    "write-final-workflow-review", "list-final-workflow-reviews",
    "finalize-reviewed-plan",
}
RETIRED_COMMANDS = {
    "write-handoff", "list-handoffs", "set-handoff-status", "index-handoffs",
    "build-review-package", "validate-executor-result", "observe-task-validation",
    "begin-review-round", "complete-review-round", "review-round-status",
    "finalize-accepted-plan", "finalize-with-blockers", "archive-plan",
}


def _require_terms(issues: list[str], path: Path, terms: tuple[str, ...]) -> None:
    if not path.is_file():
        issues.append(f"missing current contract: {path}")
        return
    text = path.read_text(encoding="utf-8")
    for term in terms:
        if term not in text:
            issues.append(f"{path} missing current contract term: {term}")


def cmd_doctor(_args: argparse.Namespace) -> None:
    issues: list[str] = []
    root = Path(__file__).resolve().parents[2]
    try:
        catalog = load_catalog(CATALOG)
        for family in STAGE5_FAMILIES:
            policy = family_policy(catalog, family)
            if policy["representation"] != "yaml" or policy["lifecycle"]["authority"] != "location":
                issues.append(f"current family policy is not schema/location owned: {family}")
    except (OSError, SystemExit) as error:
        issues.append(f"invalid current artifact-family catalog: {error}")

    from dispatcher import RECOGNIZED_COMMANDS

    missing = sorted(CURRENT_COMMANDS - RECOGNIZED_COMMANDS)
    retained = sorted(RETIRED_COMMANDS & RECOGNIZED_COMMANDS)
    if missing:
        issues.append(f"missing current orchestration commands: {', '.join(missing)}")
    if retained:
        issues.append(f"retired orchestration commands remain public: {', '.join(retained)}")

    for name in ("orch-execute-plan", "orch-create-handoff", "orch-review-plan"):
        _require_terms(
            issues,
            root / "skills" / name / "SKILL.md",
            ("## Self-check", "- [ ]"),
        )
    _require_terms(
        issues,
        root / "references/assets/orchestration/contract/handoff-executor-result-v1.md",
        ("executor-result-v1", "canonical", "product verdict"),
    )
    evals = root / "references/evals/orchestration/evals.json"
    try:
        cases = json.loads(evals.read_text(encoding="utf-8")).get("evals")
        if not isinstance(cases, list) or not cases:
            issues.append("orchestration evals do not contain current cases")
    except (OSError, json.JSONDecodeError) as error:
        issues.append(f"invalid orchestration evals: {error}")

    _require_terms(
        issues,
        root / "scripts/work-bundle/stage_events.py",
        ("operational_metadata_only", "finding_recorded", "artifact_digest"),
    )
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("ok")
