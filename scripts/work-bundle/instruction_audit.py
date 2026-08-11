from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
from pathlib import Path
import re

_core_spec = importlib.util.spec_from_file_location("_work_bundle_core", Path(__file__).with_name("core.py"))
if _core_spec is None or _core_spec.loader is None:
    raise ImportError("cannot load Work-Bundle core")
_work_bundle_core = importlib.util.module_from_spec(_core_spec)
_core_spec.loader.exec_module(_work_bundle_core)
out = _work_bundle_core.out
from workspace_resources import _load_yaml


WORD = re.compile(r"\b[\w]+(?:[-'][\w]+)*\b", re.UNICODE)
RULE_LOADING_HEADING = re.compile(r"^## Rule Loading \(mandatory\)\s*$", re.MULTILINE)


def word_count(text: str) -> int:
    return len(WORD.findall(text))


def _front_matter(text: str) -> dict[str, object]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return {}
    try:
        parsed = _load_yaml("\n".join(lines[1:end]) + "\n")
    except (ValueError, TypeError, SyntaxError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rule_loading_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    matches = list(RULE_LOADING_HEADING.finditer(text))
    for match in matches:
        following = re.search(r"^#{1,2} (?!#)", text[match.end():], re.MULTILINE)
        end = match.end() + following.start() if following else len(text)
        blocks.append(text[match.start():end].rstrip() + "\n")
    return blocks


def _instruction_files(root: Path) -> list[tuple[Path, str]]:
    selected: dict[Path, str] = {}
    skills_root = root / "skills"
    rules_root = root / "rules"
    if skills_root.is_dir():
        for path in skills_root.rglob("SKILL.md"):
            if path.is_file() and not path.is_symlink():
                selected[path] = "skill"
    if rules_root.is_dir():
        for path in rules_root.rglob("*.md"):
            if path.is_file() and not path.is_symlink():
                selected[path] = "rule"
    return sorted(selected.items())


def audit_instructions(root: Path, *, soft_threshold_words: int = 500) -> dict[str, object]:
    if soft_threshold_words < 1:
        raise ValueError("WB_INSTRUCTION_AUDIT_THRESHOLD_INVALID")
    root = root.expanduser().resolve()
    files: list[dict[str, object]] = []
    always_loaded: list[str] = []
    always_words = 0
    repeated: dict[str, list[dict[str, object]]] = defaultdict(list)
    for path, kind in _instruction_files(root):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        count = word_count(text)
        front_matter = _front_matter(text)
        description = str(front_matter.get("description") or "") if kind == "skill" else ""
        item: dict[str, object] = {
            "path": relative,
            "kind": kind,
            "word_count": count,
        }
        if kind == "skill":
            item["description_length"] = {
                "characters": len(description),
                "words": word_count(description),
            }
        files.append(item)
        if kind == "rule" and front_matter.get("load") == "always":
            always_loaded.append(relative)
            always_words += count
        for block in _rule_loading_blocks(text):
            digest = hashlib.sha256(block.encode("utf-8")).hexdigest()
            repeated[digest].append({"path": relative, "word_count": word_count(block)})

    repeated_blocks: list[dict[str, object]] = []
    for digest, occurrences in sorted(repeated.items()):
        if len(occurrences) < 2:
            continue
        repeated_blocks.append({
            "sha256": digest,
            "occurrences": len(occurrences),
            "word_count": occurrences[0]["word_count"],
            "files": [str(item["path"]) for item in occurrences],
        })
    threshold_files = [
        {"path": str(item["path"]), "kind": str(item["kind"]), "word_count": int(item["word_count"])}
        for item in files
        if int(item["word_count"]) > soft_threshold_words
    ]
    return {
        "status": "reported",
        "root": str(root),
        "soft_threshold_words": soft_threshold_words,
        "files": files,
        "always_loaded_rules": {
            "files": always_loaded,
            "total_words": always_words,
        },
        "repeated_rule_loading_blocks": repeated_blocks,
        "soft_threshold_files": threshold_files,
    }


def cmd_instruction_audit(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py instruction-audit")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--soft-threshold-words", type=int, default=500)
    parsed = parser.parse_args(argv)
    try:
        result = audit_instructions(parsed.root, soft_threshold_words=parsed.soft_threshold_words)
    except (OSError, ValueError) as exc:
        code = str(exc) if str(exc).startswith("WB_") else "WB_INSTRUCTION_AUDIT_FAILED"
        out({"command": "instruction-audit", "status": "blocked", "failure_code": code})
        return 1
    out({"command": "instruction-audit", **result})
    return 0
