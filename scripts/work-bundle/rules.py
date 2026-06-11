"""Mechanical rule migration, index sync, and validation helpers.

This module performs structure-only checks: front matter keys, body section
headings, index consistency, path placement, line limits, and prohibited fields.
It does not judge semantic rule quality (for example vague ``applies_when``
wording); agents own that via ``wb-create-rule`` skill instructions.
"""

from __future__ import annotations

from core import *


VALIDATION_MANIFEST_REL = "references/wb-create-rule-validation.yaml"

_DEFAULT_REQUIRED_FRONT_MATTER = ["id", "applies_when", "enforcement", "load", "requires"]
_DEFAULT_REQUIRED_BODY_SECTIONS = ["Purpose", "Must", "Must Not", "Validation", "On Violation"]
_DEFAULT_PROHIBITED_RULE_FIELDS = {"scope", "type", "blocks", "severity", "status", "source_authority"}
_DEFAULT_ALLOWED_SCOPES = ["work-bundle", "keep-summarizing", "orchestration", "integrity-check"]
_DEFAULT_ID_PREFIX_SCOPE_MAP = {
    "wb-": "work-bundle",
    "ks-": "keep-summarizing",
    "orch-": "orchestration",
    "rule-integrity-check-": "integrity-check",
}
_DEFAULT_FORBIDDEN_PATH_PREFIXES = ["global"]

_VALIDATION_MANIFEST_CACHE: dict[str, object] | None = None


def _validation_manifest_path() -> Path | None:
    wb_root = resolve_work_bundle_root()
    if wb_root is not None:
        candidate = wb_root / VALIDATION_MANIFEST_REL
        if candidate.is_file():
            return candidate
    script_repo_root = Path(__file__).resolve().parents[2]
    candidate = script_repo_root / VALIDATION_MANIFEST_REL
    return candidate if candidate.is_file() else None


def _parse_nested_yaml_map(text: str, key: str) -> dict[str, str]:
    lines = text.splitlines()
    result: dict[str, str] = {}
    in_section = False
    for line in lines:
        if line.strip() == f"{key}:":
            in_section = True
            continue
        if not in_section:
            continue
        if line and not line.startswith("  "):
            break
        stripped = line.strip()
        if ":" in stripped:
            map_key, map_value = stripped.split(":", 1)
            result[map_key.strip()] = map_value.strip()
    return result


def _parse_nested_yaml_list(text: str, parent_key: str, child_key: str) -> list[str]:
    lines = text.splitlines()
    in_parent = False
    in_child = False
    values: list[str] = []
    for line in lines:
        if line.strip() == f"{parent_key}:":
            in_parent = True
            in_child = False
            continue
        if not in_parent:
            continue
        if line and not line.startswith("  "):
            break
        if line.strip() == f"{child_key}:":
            in_child = True
            continue
        if in_child:
            if line.startswith("  ") and not line.startswith("    "):
                break
            item = line.strip()
            if item.startswith("- "):
                values.append(item[2:].strip().strip('"'))
    return values


def load_validation_manifest() -> dict[str, object]:
    global _VALIDATION_MANIFEST_CACHE
    if _VALIDATION_MANIFEST_CACHE is not None:
        return _VALIDATION_MANIFEST_CACHE

    manifest_path = _validation_manifest_path()
    if manifest_path is None:
        _VALIDATION_MANIFEST_CACHE = {
            "required_front_matter": list(_DEFAULT_REQUIRED_FRONT_MATTER),
            "required_body_sections": list(_DEFAULT_REQUIRED_BODY_SECTIONS),
            "prohibited_rule_fields": sorted(_DEFAULT_PROHIBITED_RULE_FIELDS),
            "allowed_scopes": list(_DEFAULT_ALLOWED_SCOPES),
            "id_prefix_scope_map": dict(_DEFAULT_ID_PREFIX_SCOPE_MAP),
            "forbidden_path_prefixes": list(_DEFAULT_FORBIDDEN_PATH_PREFIXES),
        }
        return _VALIDATION_MANIFEST_CACHE

    text = read(manifest_path)
    parsed = parse_yaml_like(text)
    prefix_map = _parse_nested_yaml_map(text, "id_prefix_scope_map")
    forbidden = _parse_nested_yaml_list(text, "path_rules", "forbidden")
    forbidden_prefixes = [
        item.removeprefix("rules/").removesuffix("/**").split("/")[0]
        for item in forbidden
        if item.startswith("rules/")
    ]
    _VALIDATION_MANIFEST_CACHE = {
        "required_front_matter": yaml_list(parsed.get("required_front_matter"), _DEFAULT_REQUIRED_FRONT_MATTER),
        "required_body_sections": yaml_list(parsed.get("required_body_sections"), _DEFAULT_REQUIRED_BODY_SECTIONS),
        "prohibited_rule_fields": yaml_list(parsed.get("prohibited_rule_fields"), sorted(_DEFAULT_PROHIBITED_RULE_FIELDS)),
        "allowed_scopes": yaml_list(parsed.get("allowed_scopes"), _DEFAULT_ALLOWED_SCOPES),
        "id_prefix_scope_map": prefix_map or dict(_DEFAULT_ID_PREFIX_SCOPE_MAP),
        "forbidden_path_prefixes": forbidden_prefixes or list(_DEFAULT_FORBIDDEN_PATH_PREFIXES),
    }
    return _VALIDATION_MANIFEST_CACHE


def required_front_matter() -> list[str]:
    return yaml_list(load_validation_manifest().get("required_front_matter"), _DEFAULT_REQUIRED_FRONT_MATTER)


def required_body_sections() -> list[str]:
    return yaml_list(load_validation_manifest().get("required_body_sections"), _DEFAULT_REQUIRED_BODY_SECTIONS)


def prohibited_rule_fields() -> set[str]:
    return set(yaml_list(load_validation_manifest().get("prohibited_rule_fields"), sorted(_DEFAULT_PROHIBITED_RULE_FIELDS)))


def allowed_scopes() -> set[str]:
    return set(yaml_list(load_validation_manifest().get("allowed_scopes"), _DEFAULT_ALLOWED_SCOPES))


def id_prefix_scope_map() -> dict[str, str]:
    raw = load_validation_manifest().get("id_prefix_scope_map")
    if isinstance(raw, dict) and raw:
        return {str(key): str(value) for key, value in raw.items()}
    return dict(_DEFAULT_ID_PREFIX_SCOPE_MAP)


def forbidden_path_prefixes() -> set[str]:
    return set(yaml_list(load_validation_manifest().get("forbidden_path_prefixes"), _DEFAULT_FORBIDDEN_PATH_PREFIXES))


def parse_yaml_like(text: str) -> dict[str, object]:
    data: dict[str, object] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.startswith(" ") or ":" not in raw:
            index += 1
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            values: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith("  ") or not lines[index].strip()):
                item = lines[index].strip()
                if item.startswith("- "):
                    values.append(item[2:].strip().strip('"'))
                index += 1
            data[key] = values
            continue
        if value.startswith("[") and value.endswith("]"):
            data[key] = [item.strip().strip('"') for item in value[1:-1].split(",") if item.strip()]
        else:
            data[key] = value.strip('"')
        index += 1
    return data


def split_front_matter(text: str) -> tuple[dict[str, object], str] | tuple[None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text
    return parse_yaml_like(text[4:end]), text[end + 5 :]


def yaml_list(value: object, default: list[str] | None = None) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return default or []


def enforcement_from_legacy(value: object) -> str:
    raw = str(value or "must").strip().lower()
    if raw in {"warning", "should"}:
        return "should"
    return "must"


def title_from_id(rule_id: str) -> str:
    raw = rule_id
    for prefix in ["rule-work-bundle-", "rule-", "wb-", "ks-", "orch-"]:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    return raw.replace("-", " ").title()


def render_rule(front: dict[str, object], body: dict[str, list[str]] | None = None) -> str:
    rule_id = str(front["id"])
    applies_when = yaml_list(front.get("applies_when"), ["rule file is selected by rules/index.yaml"])
    requires = yaml_list(front.get("requires"))
    body = body or {}
    lines = ["---", f"id: {rule_id}", "applies_when:"]
    lines.extend(f"  - {item}" for item in applies_when)
    lines.extend([f"enforcement: {front.get('enforcement', 'must')}", f"load: {front.get('load', 'conditional')}", "requires:"])
    if requires:
        lines.extend(f"  - {item}" for item in requires)
    else:
        lines[-1] = "requires: []"
    lines.extend(["---", "", f"# {title_from_id(rule_id)}", ""])
    sections = {
        "Purpose": body.get("Purpose") or [f"Define the enforceable contract for `{rule_id}`."],
        "Must": body.get("Must") or yaml_list(front.get("required_behavior"), ["Follow this rule when its activation conditions match."]),
        "Must Not": body.get("Must Not") or yaml_list(front.get("prohibited_behavior"), ["Do not bypass this rule when it is selected."]),
        "Validation": body.get("Validation") or yaml_list(front.get("validation"), ["Verify required rule front matter and body sections exist."]),
        "On Violation": body.get("On Violation") or ["Stop the operation, report the violated rule, and make the minimal correction before continuing."],
    }
    for section, items in sections.items():
        lines.extend([f"## {section}", ""])
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def legacy_front_matter(data: dict[str, object]) -> dict[str, object]:
    return {
        "id": data.get("id", "rule-unknown"),
        "applies_when": yaml_list(data.get("applies_when")) or yaml_list(data.get("enable_when")),
        "enforcement": enforcement_from_legacy(data.get("enforcement") or data.get("severity")),
        "load": data.get("load", "conditional"),
        "requires": yaml_list(data.get("requires")),
        "required_behavior": data.get("required_behavior"),
        "prohibited_behavior": data.get("prohibited_behavior"),
        "validation": data.get("validation"),
    }


def migrate_legacy_yaml(path: Path) -> Path | None:
    if path.name == "index.yaml":
        return None
    data = parse_yaml_like(read(path))
    if "id" not in data:
        return None
    target = path.with_suffix(".md")
    write(target, render_rule(legacy_front_matter(data)))
    path.unlink()
    return target


def markdown_rules(root: Path) -> list[Path]:
    return sorted(path for path in root.glob("**/*.md") if path.is_file())


def scoped_rule_id_prefix(rule_id: str) -> str | None:
    for prefix, _scope in sorted(id_prefix_scope_map().items(), key=lambda item: len(item[0]), reverse=True):
        if rule_id.startswith(prefix):
            return prefix
    return None


def expected_scope_for_rule_id(rule_id: str) -> str | None:
    for prefix, scope in sorted(id_prefix_scope_map().items(), key=lambda item: len(item[0]), reverse=True):
        if rule_id.startswith(prefix):
            return scope
    return None


def index_entry(root: Path, path: Path) -> dict[str, object]:
    front, _ = split_front_matter(read(path))
    if front is None:
        front = {}
    return {
        "id": str(front.get("id", path.stem)),
        "path": str(path.relative_to(root)),
        "applies_when": yaml_list(front.get("applies_when")),
        "enforcement": str(front.get("enforcement", "")),
        "load": str(front.get("load", "")),
        "requires": yaml_list(front.get("requires")),
    }


def render_index(root: Path, entries: list[dict[str, object]]) -> str:
    lines = ["rules:"]
    for entry in sorted(entries, key=lambda item: str(item["id"])):
        lines.append(f"  - id: {entry['id']}")
        lines.append(f"    path: {entry['path']}")
        lines.append("    applies_when:")
        for item in yaml_list(entry.get("applies_when")):
            lines.append(f"      - {item}")
        lines.append(f"    enforcement: {entry['enforcement']}")
        lines.append(f"    load: {entry['load']}")
        requires = yaml_list(entry.get("requires"))
        if requires:
            lines.append("    requires:")
            for item in requires:
                lines.append(f"      - {item}")
        else:
            lines.append("    requires: []")
    return "\n".join(lines) + "\n"


def sync_index(root: Path) -> list[dict[str, object]]:
    entries = [index_entry(root, path) for path in markdown_rules(root)]
    write(root / "index.yaml", render_index(root, entries))
    return entries


def cmd_create_rules(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py create-rules")
    parser.add_argument("rules_root")
    parsed = parser.parse_args(args)
    root = Path(parsed.rules_root)
    root.mkdir(parents=True, exist_ok=True)
    migrated = []
    for path in sorted(root.glob("**/*.yaml")):
        if path.name == "index.yaml":
            continue
        migrated_path = migrate_legacy_yaml(path)
        if migrated_path:
            migrated.append(str(migrated_path))
    entries = sync_index(root)
    out({"status": "passed", "migrated": migrated, "rules": [entry["id"] for entry in entries]})
    return 0


def validate_rule_path_placement(root: Path, path: Path) -> list[str]:
    failures: list[str] = []
    rel = path.relative_to(root)
    rel_text = str(rel)
    parts = rel.parts

    if parts and parts[0] in forbidden_path_prefixes():
        failures.append(f"{rel_text}:forbidden_path:{parts[0]}")
        return failures

    if len(parts) == 1:
        front, _ = split_front_matter(read(path))
        rule_id = str(front.get("id", path.stem)) if front else path.stem
        expected_scope = expected_scope_for_rule_id(rule_id)
        if expected_scope is not None:
            if root.name in allowed_scopes() and root.name == expected_scope:
                return failures
            failures.append(f"{rel_text}:scoped_rule_at_root:{rule_id}:{expected_scope}")
        return failures

    if len(parts) == 2:
        scope = parts[0]
        if scope not in allowed_scopes():
            failures.append(f"{rel_text}:invalid_scope_directory:{scope}")
        front, _ = split_front_matter(read(path))
        rule_id = str(front.get("id", path.stem)) if front else path.stem
        expected_scope = expected_scope_for_rule_id(rule_id)
        if expected_scope is not None and expected_scope != scope:
            failures.append(f"{rel_text}:scope_id_mismatch:{rule_id}:{expected_scope}")
        elif expected_scope is None and scoped_rule_id_prefix(rule_id) is None:
            failures.append(f"{rel_text}:cross_cutting_in_scope_directory:{scope}")
        return failures

    failures.append(f"{rel_text}:invalid_path_depth")
    return failures


def validate_rule_file(root: Path, path: Path) -> list[str]:
    failures: list[str] = []
    text = read(path)
    front, body = split_front_matter(text)
    rel = str(path.relative_to(root))
    if front is None:
        return [f"{rel}:missing_front_matter"]
    for field in required_front_matter():
        if field not in front:
            failures.append(f"{rel}:missing_front_matter:{field}")
    for field in prohibited_rule_fields():
        if field in front:
            failures.append(f"{rel}:prohibited_front_matter:{field}")
    if front.get("enforcement") not in {"must", "should"}:
        failures.append(f"{rel}:invalid_enforcement")
    if front.get("load") not in {"always", "conditional", "manual"}:
        failures.append(f"{rel}:invalid_load")
    if not yaml_list(front.get("applies_when")):
        failures.append(f"{rel}:empty_applies_when")
    if len(text.splitlines()) >= 500:
        failures.append(f"{rel}:too_long")
    for section in required_body_sections():
        if f"## {section}" not in body:
            failures.append(f"{rel}:missing_section:{section}")
    failures.extend(validate_rule_path_placement(root, path))
    return failures


def validate_index(root: Path) -> list[str]:
    failures: list[str] = []
    index_path = root / "index.yaml"
    if not index_path.exists():
        return ["index.yaml:missing"]
    text = read(index_path)
    for field in prohibited_rule_fields():
        if re.search(rf"^\s*{re.escape(field)}:", text, re.MULTILINE):
            failures.append(f"index.yaml:prohibited_field:{field}")
    indexed_ids = set(re.findall(r"^\s+- id:\s*(.+?)\s*$", text, re.MULTILINE))
    rule_ids: set[str] = set()
    for path in markdown_rules(root):
        front, _ = split_front_matter(read(path))
        if front and front.get("id"):
            rule_ids.add(str(front["id"]))
            rel_path = str(path.relative_to(root))
            for token in [f"- id: {front['id']}", f"path: {rel_path}"]:
                if token not in text:
                    failures.append(f"index.yaml:missing_or_mismatched:{front['id']}:{token}")
    missing = sorted(rule_ids - indexed_ids)
    extra = sorted(indexed_ids - rule_ids)
    failures.extend(f"index.yaml:missing_rule:{rule_id}" for rule_id in missing)
    failures.extend(f"index.yaml:unknown_rule:{rule_id}" for rule_id in extra)
    return failures


def cmd_validate_rules(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py validate-rules")
    parser.add_argument("rules_root")
    parsed = parser.parse_args(args)
    root = Path(parsed.rules_root)
    failures: list[str] = []
    if list(root.glob("**/*.mdc")):
        failures.append("generated_mdc_present")
    legacy_yaml = [str(path.relative_to(root)) for path in root.glob("**/*.yaml") if path.name != "index.yaml"]
    if legacy_yaml:
        failures.extend(f"legacy_yaml_rule:{path}" for path in legacy_yaml)
    for path in markdown_rules(root):
        failures.extend(validate_rule_file(root, path))
    failures.extend(validate_index(root))
    out({"status": "passed" if not failures else "issues-found", "failures": failures})
    return 0 if not failures else 1
