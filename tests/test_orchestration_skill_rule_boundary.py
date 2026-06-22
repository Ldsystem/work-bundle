import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ORCH_SKILL_GLOB = "skills/orch-*/SKILL.md"


def orch_skill_paths() -> list[Path]:
    return sorted(REPO_ROOT.glob(ORCH_SKILL_GLOB))


def skill_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def runtime_rule_paths(text: str) -> list[str]:
    return re.findall(r"`(rules/orchestration/[^`]+)`", text)


def test_all_orch_skills_have_rule_loading() -> None:
    for path in orch_skill_paths():
        text = skill_text(path)
        if "## Runtime Rules" not in text:
            continue
        assert "## Rule Loading (mandatory)" in text, path.name
        runtime_idx = text.index("## Runtime Rules")
        loading_idx = text.index("## Rule Loading (mandatory)")
        assert loading_idx > runtime_idx, path.name


def test_runtime_rules_paths_exist() -> None:
    for path in orch_skill_paths():
        for rule_path in runtime_rule_paths(skill_text(path)):
            target = REPO_ROOT / rule_path
            assert target.is_file(), f"{path.name} cites missing rule {rule_path}"


def test_no_role_context_in_orch_skills() -> None:
    for path in orch_skill_paths():
        text = skill_text(path)
        assert "## Role Context" not in text, path.name
        assert "wb-select-role-context" not in text.replace("Do not reintroduce `wb-select-role-context`", ""), path.name
        if "role-context" in text:
            assert "deprecated" in text.lower(), path.name
            assert "Do not invoke it from orch skills" in text, path.name


def test_boundary_sections_do_not_duplicate_m2_prose() -> None:
    forbidden = ("do not write durable", "directly create, edit, promote")
    for path in orch_skill_paths():
        text = skill_text(path)
        if "## Boundary" not in text:
            continue
        boundary = text.split("## Boundary", 1)[1].split("\n## ", 1)[0]
        for phrase in forbidden:
            assert phrase not in boundary.lower(), f"{path.name} Boundary duplicates M2: {phrase}"


def test_no_enforcement_pointer_stub_rules() -> None:
    removed = (
        REPO_ROOT / "rules/orchestration/orch-execute-plan.md",
        REPO_ROOT / "rules/orchestration/orch-doctor-readonly.md",
    )
    for path in removed:
        assert not path.is_file(), f"removed stub rule still present: {path}"


def test_execute_and_doctor_skills_own_constraints() -> None:
    execute = skill_text(REPO_ROOT / "skills/orch-execute-plan/SKILL.md")
    doctor = skill_text(REPO_ROOT / "skills/orch-doctor/SKILL.md")

    assert "## Execution Constraints (skill-owned)" in execute
    assert "repository preflight" in execute.lower() or "clean-worktree preflight" in execute.lower()
    assert "## Read-Only Constraints (skill-owned)" in doctor
    assert "Files changed: none" in doctor


def test_create_specification_keeps_quality_gate_terms_and_rule_loading() -> None:
    skill = skill_text(REPO_ROOT / "skills/orch-create-specification/SKILL.md")

    assert "## Runtime Rules" in skill
    assert "## Rule Loading (mandatory)" in skill
    assert "`orch-orchestration-boundary`" in skill
    assert "Extra evidence loop" in skill
    assert "Quality gate: verified|blocked" in skill
    assert "material non-authority" in skill
    assert "Design Interrogation" in skill


def test_orch_doctor_declares_full_quality_gate_and_forbidden_dependency_checks() -> None:
    skill = skill_text(REPO_ROOT / "skills/orch-doctor/SKILL.md")

    assert "source-evidence roles" in skill
    assert "generated-artifact verification and repair" in skill
    assert "preserve no-retrieval execution" in skill
    assert "CodeGraph-first rule remains conditional" in skill
    assert "active orchestration contracts do not depend on `HABITS.md`" in skill
    assert "deprecated role-selection subsystem" in skill
    assert "must not judge" in skill
    assert "sparse YAML" in skill
    assert "forbidden executor advice fields" in skill
    assert "active orchestration handoffs" in skill
    assert "delegation_evidence" in skill
    assert "`root`, `applicable`, `up_to_date`" in skill
