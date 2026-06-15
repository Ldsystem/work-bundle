import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KS_RULE_DIR = REPO_ROOT / "rules" / "keep-summarizing"
EXPECTED_RULE_NAMES = {
    "ks-context-pack-policy.md",
    "ks-git-authority.md",
    "ks-index-maintenance.md",
    "ks-knowledge-boundary.md",
    "ks-note-state-authority.md",
    "ks-off-switches.md",
    "ks-open-question-policy.md",
    "ks-persistence-gate.md",
    "ks-perspective-routing.md",
    "ks-sensitivity-filter.md",
    "ks-structural-value.md",
}

sys.path.insert(0, str(REPO_ROOT / "scripts" / "work-bundle"))
try:
    import rules as rules_module
finally:
    if sys.path and sys.path[0] == str(REPO_ROOT / "scripts" / "work-bundle"):
        sys.path.pop(0)


def ks_rule_paths() -> list[Path]:
    return sorted(KS_RULE_DIR.glob("ks-*.md"))


def rule_document(path: Path) -> tuple[dict[str, object], str]:
    front, body = rules_module.split_front_matter(path.read_text(encoding="utf-8"))
    assert front is not None, f"{path.name} is missing front matter"
    return front, body


def test_ks_rules_exist_at_scoped_markdown_paths() -> None:
    paths = ks_rule_paths()
    assert {path.name for path in paths} == EXPECTED_RULE_NAMES
    assert len(paths) == 11


def test_index_entries_match_ks_rule_ids_and_paths() -> None:
    index_text = (REPO_ROOT / "rules" / "index.yaml").read_text(encoding="utf-8")
    entries = {
        match.group("id"): match.group("path")
        for match in re.finditer(r"^  - id: (?P<id>[^\n]+)\n    path: (?P<path>[^\n]+)$", index_text, re.MULTILINE)
    }
    expected_entries = {
        path.stem: f"keep-summarizing/{path.name}"
        for path in ks_rule_paths()
    }

    assert {rule_id: path for rule_id, path in entries.items() if rule_id.startswith("ks-")} == expected_entries

    for path in ks_rule_paths():
        front, _body = rule_document(path)
        assert front["id"] == path.stem


def test_ks_skills_do_not_cite_legacy_yaml_rules() -> None:
    legacy_pattern = re.compile(r"rules/ks-[^`\s]+\.yaml")
    for path in sorted(REPO_ROOT.glob("skills/ks-*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        assert legacy_pattern.search(text) is None, path.name


def test_ks_rules_have_required_body_sections() -> None:
    required_sections = rules_module.required_body_sections()
    for path in ks_rule_paths():
        _front, body = rule_document(path)
        for section in required_sections:
            assert f"## {section}" in body, f"{path.name} missing {section}"


def test_keep_summarizing_rules_do_not_use_legacy_rule_ks_ids() -> None:
    legacy_prefix = "rule-" + "ks-"
    for path in ks_rule_paths():
        text = path.read_text(encoding="utf-8")
        assert legacy_prefix not in text, path.name
