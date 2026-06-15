import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
KS_SKILL_GLOB = "skills/ks-*/SKILL.md"


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


def body_before_runtime_rules(text: str) -> str:
    if "## Runtime Rules" not in text:
        return text
    return text.split("## Runtime Rules", 1)[0]


def boundary_section(text: str) -> str:
    if "## Boundary" not in text:
        return ""
    return text.split("## Boundary", 1)[1].split("\n## ", 1)[0]


def test_all_ks_skills_have_rule_loading() -> None:
    for path in ks_skill_paths():
        text = skill_text(path)
        if "## Runtime Rules" not in text:
            continue
        assert "## Rule Loading (mandatory)" in text, path.name
        runtime_idx = section_line_index(text, "## Runtime Rules")
        loading_idx = section_line_index(text, "## Rule Loading (mandatory)")
        assert loading_idx > runtime_idx, path.name


def test_runtime_rules_paths_exist() -> None:
    for path in ks_skill_paths():
        for rule_path in runtime_rule_paths(skill_text(path)):
            target = REPO_ROOT / rule_path
            assert target.is_file(), f"{path.name} cites missing rule {rule_path}"


def test_boundary_sections_do_not_duplicate_shared_prose() -> None:
    forbidden = (
        "write only under `.work-bundle/knowledge/`",
        "credentials, tokens, personal data",
        "only authority may directly shape",
        "do not treat context packs as canonical",
        "pause keep-summarizing",
    )
    for path in ks_skill_paths():
        text = skill_text(path)
        if "## Boundary" not in text:
            continue
        boundary = boundary_section(text).lower()
        for phrase in forbidden:
            assert phrase not in boundary, f"{path.name} Boundary duplicates shared prose: {phrase}"


def test_boundary_sections_use_pointer_only_template() -> None:
    for path in ks_skill_paths():
        text = skill_text(path)
        if "## Boundary" not in text:
            continue
        boundary = boundary_section(text)
        assert "ks-knowledge-boundary" in boundary, path.name
        assert "Write only under" not in boundary, path.name


def test_oq_citation_fixes() -> None:
    track = skill_text(REPO_ROOT / "skills/ks-track-open-questions/SKILL.md")
    assert "ks-structural-value" in track.split("## Runtime Rules")[1]

    detect = skill_text(REPO_ROOT / "skills/ks-detect-structural-update/SKILL.md")
    assert "ks-perspective-routing" in detect.split("## Runtime Rules")[1]

    guard = skill_text(REPO_ROOT / "skills/ks-guard-scope/SKILL.md")
    manage = skill_text(REPO_ROOT / "skills/ks-manage-lifecycle/SKILL.md")
    assert "ks-git-authority" in guard.split("## Runtime Rules")[1]
    assert "ks-git-authority" in manage.split("## Runtime Rules")[1]


def test_no_ks_doctor_readonly_stub_rule() -> None:
    path = REPO_ROOT / "rules/keep-summarizing/ks-doctor-readonly.md"
    assert not path.is_file(), "removed stub rule still present"


def test_ks_doctor_skill_owns_constraints() -> None:
    doctor = skill_text(REPO_ROOT / "skills/ks-doctor/SKILL.md")
    assert "## Read-Only Constraints (skill-owned)" in doctor
    assert "Files changed: none" in doctor


def test_skill_owned_sections_present() -> None:
    expected = {
        "ks-guard-scope": "Preflight Constraints (skill-owned)",
        "ks-detect-structural-update": "Structural Update Constraints (skill-owned)",
        "ks-what-is-helpful": "Retrieval Workflow (skill-owned)",
        "ks-extract-valuable-points": "Extraction Constraints (skill-owned)",
        "ks-write-knowledge": "Write Constraints (skill-owned)",
        "ks-breakdown-design": "Coverage Constraints (skill-owned)",
        "ks-build-context-pack": "Context Pack Constraints (skill-owned)",
        "ks-track-open-questions": "Open Question Constraints (skill-owned)",
        "ks-resolve-open-question": "Resolution Constraints (skill-owned)",
        "ks-resolve-conflicts": "Conflict Resolution Constraints (skill-owned)",
        "ks-manage-lifecycle": "Lifecycle Constraints (skill-owned)",
    }
    for slug, section in expected.items():
        text = skill_text(REPO_ROOT / "skills" / slug / "SKILL.md")
        assert f"## {section}" in text, slug
