from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRIBUTOR = ROOT / "AGENTS.md"
MANAGED = ROOT / "references/assets/template/AGENTS.md"
INDEX = ROOT / "rules/index.yaml"


def test_managed_entry_exposes_three_scopes_and_rule_failure_semantics() -> None:
    text = MANAGED.read_text(encoding="utf-8")

    for path in (
        "$work_bundle_root/rules/index.yaml",
        "$work_bundle_config_root/rules/index.yaml",
        "$workspace_root/.work-bundle/rules/index.yaml",
    ):
        assert path in text
    for required in (
        "load: always",
        "load: conditional",
        "load: manual",
        "applies_when",
        "enforcement: must",
        "requires",
        "duplicate rule ID",
        "dependency cycle",
        "missing selected rule body",
        "Never silently skip an applicable `must` rule",
    ):
        assert required in text
    assert "before loading rule bodies or making a substantive" in text


def test_investigator_discovers_combined_rule_and_worker_consumes_carried_basis() -> None:
    text = MANAGED.read_text(encoding="utf-8")
    rules = {entry["id"]: entry for entry in yaml.safe_load(INDEX.read_text(encoding="utf-8"))["rules"]}
    combined = rules["wb-truth-basis-evidence"]

    assert combined["load"] == "conditional"
    assert combined["enforcement"] == "must"
    assert any("investigation" in trigger for trigger in combined["applies_when"])
    assert any("implements" in trigger for trigger in combined["applies_when"])
    assert "Discover it before the first substantive probe" in text
    assert "minimal bootstrap" in text
    assert "consumes its carried Truth Basis" in text
    assert "does not repeat controller-wide knowledge retrieval" in text
    assert "Controllers own scope, delegation, repair routing, continuation, and acceptance" in text
    assert "reviewers give independent advice" in text


def test_entry_points_have_distinct_owners_and_non_deferrable_safety() -> None:
    contributor = CONTRIBUTOR.read_text(encoding="utf-8")
    managed = MANAGED.read_text(encoding="utf-8")

    assert contributor != managed
    assert "WorkBundle toolkit contributors" in contributor
    assert "focused behavior tests" in contributor
    assert "preserve unrelated source and user content" in contributor.lower()
    assert "WorkBundle managed workspace" in managed
    assert "credential values" in managed
    assert "Cross-task messages do not grant repository or worktree mutation authority" in managed
    assert "Do not rewrite another task's files" in contributor
