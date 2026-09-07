from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "skills" / "dev-create-task-plan" / "SKILL.md"
EVALS_PATH = REPO_ROOT / "references" / "evals" / "development" / "evals.json"


def test_lightweight_plan_allows_one_bounded_pre_mutation_path_amendment() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    for token in [
        "Before the first write",
        "exactly one additional path",
        "same implementation owner",
        "purpose, decision authority, expected delta, impact radius, ownership, validation boundary, and completion claim",
        "materially unchanged",
        "exact path",
        "supporting evidence",
    ]:
        assert token in text


def test_lightweight_plan_escalates_material_under_decomposition() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    for token in [
        "materially under-decomposed",
        "new production or lifecycle owner",
        "independent validation boundary",
        "wide impact",
        "API or workflow decision",
        "second repository",
        "barrier or convergence topology",
        "full orchestration",
        "must not be repeated",
    ]:
        assert token in text


def test_lightweight_scope_pressure_evals_cover_wor109_boundaries() -> None:
    cases = json.loads(EVALS_PATH.read_text(encoding="utf-8"))["evals"]
    by_id = {case["id"]: case for case in cases}
    required = {
        "dev-lightweight-pre-mutation-one-file-amendment",
        "dev-lightweight-amendment-after-mutation",
        "dev-lightweight-material-under-decomposition",
        "dev-lightweight-amendment-lane-separation",
    }

    assert required <= by_id.keys()
    selected = " ".join(
        by_id[case_id][field]
        for case_id in sorted(required)
        for field in ("prompt", "expected_output")
    )
    for token in [
        "exact additional path",
        "before the first write",
        "already mutated",
        "new production owner",
        "independent validation boundary",
        "materially under-decomposed",
        "executor result",
        "one disposable plan",
    ]:
        assert token in selected
