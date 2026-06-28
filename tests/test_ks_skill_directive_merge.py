import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
KS_SKILL_GLOB = "skills/ks-*/SKILL.md"
EXPECTED_KS_SKILLS = {
    "ks-breakdown-design",
    "ks-build-context-pack",
    "ks-detect-structural-update",
    "ks-doctor",
    "ks-extract-valuable-points",
    "ks-guard-scope",
    "ks-maintain-indexes",
    "ks-manage-lifecycle",
    "ks-resolve-conflicts",
    "ks-resolve-open-question",
    "ks-track-open-questions",
    "ks-what-is-helpful",
    "ks-write-knowledge",
}
FORMER_ROLE_CONTEXT_SKILLS = {
    "ks-breakdown-design",
    "ks-extract-valuable-points",
    "ks-resolve-conflicts",
    "ks-resolve-open-question",
    "ks-track-open-questions",
}


def ks_skill_paths() -> list[Path]:
    return sorted(REPO_ROOT.glob(KS_SKILL_GLOB))


def skill_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def runtime_rule_paths(text: str) -> list[str]:
    paths = re.findall(r"`(rules/keep-summarizing/[^`]+)`", text)
    return [path for path in paths if "*" not in path and "?" not in path]


def section_line_index(text: str, heading: str) -> int:
    match = re.search(rf"^{re.escape(heading)}$", text, re.MULTILINE)
    assert match is not None, f"missing section {heading}"
    return match.start()


def test_expected_ks_skills_without_meta_skill() -> None:
    names = {path.parent.name for path in ks_skill_paths()}
    assert names == EXPECTED_KS_SKILLS
    assert "ks-help-with-directives" not in names


def test_no_directive_paths_or_directive_reference_sections() -> None:
    for path in ks_skill_paths():
        text = skill_text(path)
        assert "references/directives/keep-summarizing" not in text, path.name
        assert "## Directive Reference" not in text, path.name


def test_all_ks_skills_have_rule_loading_after_runtime_rules() -> None:
    for path in ks_skill_paths():
        text = skill_text(path)
        if "## Runtime Rules" not in text:
            continue
        assert "## Rule Loading (mandatory)" in text, path.name
        runtime_idx = section_line_index(text, "## Runtime Rules")
        loading_idx = section_line_index(text, "## Rule Loading (mandatory)")
        assert loading_idx > runtime_idx, path.parent.name


def test_runtime_rules_paths_exist() -> None:
    for path in ks_skill_paths():
        for rule_path in runtime_rule_paths(skill_text(path)):
            target = REPO_ROOT / rule_path
            assert target.is_file(), f"{path.name} cites missing rule {rule_path}"


def test_no_help_with_directives_strings_in_skills() -> None:
    for path in ks_skill_paths():
        text = skill_text(path)
        assert "help-with-directives" not in text, path.name
        assert "ks-help-with-directives" not in text, path.name


def test_no_role_context_in_former_role_context_skills() -> None:
    for path in ks_skill_paths():
        if path.parent.name not in FORMER_ROLE_CONTEXT_SKILLS:
            continue
        text = skill_text(path)
        assert "## Role Context" not in text, path.name
        assert "wb-select-role-context" not in text, path.name


def test_directive_tree_removed() -> None:
    directive_root = REPO_ROOT / "references/directives/keep-summarizing"
    if directive_root.exists():
        remaining = list(directive_root.glob("*.md"))
        assert remaining == [], f"directive files remain: {remaining}"


def test_workflow_and_evals_use_orch_skill_names() -> None:
    workflow = (REPO_ROOT / "references/assets/keep-summarizing/workflow.md").read_text(
        encoding="utf-8"
    )
    evals = (REPO_ROOT / "references/evals/keep-summarizing/evals.json").read_text(
        encoding="utf-8"
    )
    for blob in (workflow, evals):
        assert "orchestrator create-document" not in blob
        assert "orchestrator create-handoff" not in blob
        assert "`orchestrator` `create-document`" not in blob
    assert "orch-create-document" in workflow
    assert "orch-create-document" in evals
