"""Core-independent orchestration artifact parsing and bounded input resolution."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any


def _split_top_level(value: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quote and char == "\\":
            escaped = True
            continue
        if char in {'"', "'"}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if quote:
            continue
        if char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == delimiter and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _split_key_value(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise SystemExit(f"Invalid YAML mapping entry: {value}")
    key, raw = value.split(":", 1)
    return key.strip().strip("'\""), raw.strip()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_parse_scalar(part) for part in _split_top_level(inner)]
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        result: dict[str, Any] = {}
        for part in _split_top_level(inner):
            key, raw = _split_key_value(part)
            result[key] = _parse_scalar(raw)
        return result
    if value[:1] == value[-1:] and value[:1] in {'"', "'"}:
        if value.startswith('"'):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def parse_yaml_subset(text: str) -> dict[str, Any]:
    """Parse the compact YAML subset used by orchestration contracts."""

    rows: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        rows.append((indent, raw.strip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(rows) or rows[index][0] < indent:
            return {}, index
        is_list = rows[index][0] == indent and rows[index][1].startswith("- ")
        container: Any = [] if is_list else {}
        while index < len(rows):
            row_indent, content = rows[index]
            if row_indent < indent:
                break
            if row_indent > indent:
                raise SystemExit(f"Invalid YAML indentation near: {content}")
            if is_list:
                if not content.startswith("- "):
                    break
                item_text = content[2:].strip()
                if not item_text:
                    item, index = parse_block(index + 1, indent + 2)
                elif item_text.startswith("{"):
                    item = _parse_scalar(item_text)
                    index += 1
                elif ":" in item_text and not item_text.startswith(("'", '"', "`")):
                    key, raw_value = _split_key_value(item_text)
                    item = {key: _parse_scalar(raw_value)}
                    index += 1
                    if index < len(rows) and rows[index][0] > indent:
                        continuation, index = parse_block(index, indent + 2)
                        if not isinstance(continuation, dict):
                            raise SystemExit(f"Invalid YAML list mapping near: {item_text}")
                        item.update(continuation)
                else:
                    item = _parse_scalar(item_text)
                    index += 1
                container.append(item)
                continue

            if content.startswith("- "):
                break
            key, raw_value = _split_key_value(content)
            index += 1
            if raw_value:
                container[key] = _parse_scalar(raw_value)
            elif index < len(rows) and rows[index][0] > indent:
                container[key], index = parse_block(index, rows[index][0])
            else:
                container[key] = {}
        return container, index

    if not rows:
        return {}
    parsed, index = parse_block(0, rows[0][0])
    if index != len(rows) or not isinstance(parsed, dict):
        raise SystemExit("Expected a YAML mapping")
    return parsed


def _read_structured(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end < 0:
            raise SystemExit(f"Unterminated front matter: {path}")
        return parse_yaml_subset(raw[4:end]), raw[end + 5 :]
    return parse_yaml_subset(raw), ""


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "" or value == {}:
        return []
    return value if isinstance(value, list) else [value]


def _input_path(raw: str | Path, root: Path, allowed: Path, label: str) -> Path:
    path = Path(raw).expanduser()
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not path.is_relative_to(allowed.resolve()):
        raise SystemExit(f"{label} path escapes its allowed root: {path}")
    relative = path.relative_to(root.resolve()).as_posix()
    if relative.startswith(".work-bundle/knowledge/") or relative.startswith("credentials/"):
        raise SystemExit(f"{label} path uses a forbidden protected source: {relative}")
    if not path.is_file():
        raise SystemExit(f"{label} file not found: {path}")
    return path


def _resolve_spec_paths(root: Path, task_data: dict[str, Any], plan_data: dict[str, Any]) -> list[Path]:
    references = _as_list(task_data.get("source_spec")) or _as_list(plan_data.get("source_spec"))
    if not references:
        raise SystemExit("Task/root plan does not declare source_spec")
    spec_root = root / ".work-bundle/orchestration/spec"
    result: list[Path] = []
    for reference in references:
        raw = str(reference)
        if "/" in raw or raw.endswith(".md"):
            result.append(_input_path(raw, root, spec_root, "source specification"))
            continue
        matches: list[Path] = []
        for candidate in sorted(spec_root.glob("*/*.md")):
            data, _ = _read_structured(candidate)
            if str(data.get("id", "")) == raw:
                matches.append(candidate)
        if len(matches) != 1:
            raise SystemExit(f"Expected one source specification for {raw}; found {len(matches)}")
        result.append(matches[0])
    return result
