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


def test_managed_reuse_and_worker_procedure_keep_selection_with_agents() -> None:
    text = MANAGED.read_text(encoding="utf-8")
    for obligation in (
        "selected bodies already read in full", "explicit selected IDs", "loaded body digests",
        "every added, changed, or removed index entry", "agent applicability reassessment",
        "never select rules or declare unselected rules irrelevant", "outside authority identities and version control",
        "consume those carried obligations", "do not repeat controller-wide trigger reconciliation",
    ):
        assert obligation in text


def test_record_writer_guidance_names_supported_request_and_result_fields() -> None:
    text = (ROOT / "references/assets/keep-summarizing/workflow.md").read_text(encoding="utf-8")
    for field in ("effect:", "kind:", "path:", "expected_digest:", "record:", "body:"):
        assert field in text
    for token in ("mutate-knowledge --project <slug> --request-file <request.yaml>", "--dry-run",
                  "canonical_status: replaced", "projection_status: rebuilt|stale", "rebuild_command"):
        assert token in text
    for slug in ("ks-write-knowledge", "ks-manage-lifecycle", "ks-resolve-conflicts",
                 "ks-track-open-questions", "ks-resolve-open-question"):
        skill = (ROOT / "skills" / slug / "SKILL.md").read_text(encoding="utf-8")
        assert "mutate-knowledge --project <slug> --request-file <request.yaml>" in skill
        assert "## Self-check" in skill
    writer = (ROOT / "skills/ks-write-knowledge/SKILL.md").read_text(encoding="utf-8")
    assert "mixed artifact labels alone do not block an already approved bounded workflow follow-up" in writer
    assert "persistence scope, content, or intent unsettled" in writer


def test_canonical_writer_policy_and_skill_routes_are_explicit() -> None:
    text = (ROOT / "rules/orchestration/orch-artifact-authoring.md").read_text(encoding="utf-8")
    routes = {
        "orch-create-specification": ("write-spec",),
        "orch-create-implementation-plan": ("write-plan", "write-phase", "write-task", "amend-task"),
        "orch-create-handoff": ("write-executor-result",),
        "orch-execute-plan": ("write-executor-result",),
        "orch-review-plan": ("write-implementation-review", "write-accepted-task-result", "write-final-workflow-review"),
    }
    for slug, commands in routes.items():
        skill = (ROOT / "skills" / slug / "SKILL.md").read_text(encoding="utf-8")
        for command in commands:
            assert command in text
            assert command in skill
        assert "bootstrap repair" in skill
        assert "## Self-check" in skill
    for token in ("malformed active target", "index_effect: stale", "index_diagnostics", "unregistered specialized families"):
        assert token in text
    reviewer = (ROOT / "skills/dev-code-review/SKILL.md").read_text(encoding="utf-8")
    for token in ("orch-artifact-authoring", "scripts/orch.py write-implementation-review",
                  "reviewer returns advice only", "including bootstrap repair", "## Self-check"):
        assert token in reviewer
    assert "Do not rerun validation" in reviewer
    assert "without canonical writes" in reviewer
    # Presence/mirror checks do not prove writer usage, semantic sufficiency,
    # prompt applicability, or product acceptance.
