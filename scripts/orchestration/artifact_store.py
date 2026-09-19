"""Schema-backed structural mechanics for registered orchestration artifacts.

This module reports structural facts and failures.  It does not decide semantic
correctness, evidence sufficiency, qualification, review, or acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import string
import tempfile
from typing import Any, Mapping

import jsonschema
import yaml


_CATALOG_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "references/assets/orchestration/contract/artifact-family-catalog-v1.schema.json"
)


class _MaintainedLoader(yaml.SafeLoader):
    """Safe maintained YAML with date-like orchestration scalars kept as text."""


_MaintainedLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for _key, _resolvers in list(_MaintainedLoader.yaml_implicit_resolvers.items()):
    _MaintainedLoader.yaml_implicit_resolvers[_key] = [
        resolver for resolver in _resolvers if resolver[0] != "tag:yaml.org,2002:timestamp"
    ]


def _fail(message: str) -> None:
    raise SystemExit(message)


def _yaml_mapping(text: str, *, source: str) -> dict[str, Any]:
    try:
        value = yaml.load(text, Loader=_MaintainedLoader)
    except yaml.YAMLError as exc:
        _fail(f"Invalid YAML in {source}: {exc}")
    if not isinstance(value, dict):
        _fail(f"Expected a YAML mapping in {source}")
    return value


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    return _yaml_mapping(path.read_text(encoding="utf-8"), source=str(path))


def read_markdown_artifact(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    return parse_markdown_artifact(text, source=str(path))


def parse_markdown_artifact(text: str, *, source: str = "content") -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        _fail(f"Missing Markdown front matter: {source}")
    end = text.find("\n---\n", 4)
    if end < 0:
        _fail(f"Unterminated front matter: {source}")
    return _yaml_mapping(text[4:end], source=f"{source} front matter"), text[end + 5 :]


def parse_yaml_mapping(text: str, *, source: str = "content") -> dict[str, Any]:
    return _yaml_mapping(text, source=source)


def parse_yaml_value(text: str, *, source: str = "content") -> Any:
    try:
        return yaml.load(text, Loader=_MaintainedLoader)
    except yaml.YAMLError as exc:
        _fail(f"Invalid YAML in {source}: {exc}")


def _json_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"Invalid JSON Schema {path}: {exc}")
    if not isinstance(value, dict):
        _fail(f"Expected JSON Schema mapping: {path}")
    return value


def _schema_path(catalog_path: Path, policy: Mapping[str, Any]) -> Path:
    raw = str(policy["schema"]["path"])
    candidate = Path(raw)
    if candidate.is_absolute():
        _fail(f"Artifact schema path escapes catalog directory: {raw}")
    resolved = (catalog_path.parent / candidate).resolve()
    catalog_root = catalog_path.parent.resolve()
    if resolved != catalog_root and catalog_root not in resolved.parents:
        _fail(f"Artifact schema path escapes catalog directory: {raw}")
    if not resolved.is_file():
        _fail(f"Artifact schema not found: {resolved}")
    return resolved


def _safe_relative(raw: str, *, label: str, reject_glob: bool = False) -> Path:
    path = Path(raw)
    segments = raw.split("/")
    if (
        path.is_absolute()
        or not raw
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in segments)
        or path.as_posix() != raw
    ):
        _fail(f"{label} is not a canonical relative path: {raw}")
    if reject_glob and any(character in raw for character in "*?[]"):
        _fail(f"{label} contains literal glob syntax: {raw}")
    return path


def load_catalog(catalog_path: Path) -> dict[str, Any]:
    catalog_path = catalog_path.resolve()
    catalog = read_yaml_mapping(catalog_path)
    schema = _json_mapping(_CATALOG_SCHEMA)
    try:
        jsonschema.Draft202012Validator(schema).validate(catalog)
    except jsonschema.ValidationError as exc:
        _fail(f"Invalid artifact-family catalog {catalog_path}: {exc.message}")
    names: set[str] = set()
    for policy in catalog["families"]:
        name = str(policy["name"])
        if name in names:
            _fail(f"Duplicate artifact family: {name}")
        names.add(name)
        schema_path = _schema_path(catalog_path, policy)
        artifact_schema = _json_mapping(schema_path)
        expected = str(policy["schema"]["id"])
        if artifact_schema.get("$id") != expected:
            _fail(
                f"Artifact schema identity mismatch for {name}: "
                f"expected {expected}, found {artifact_schema.get('$id', '<missing>')}"
            )
        binding_names = [str(item["name"]) for item in policy["relationships"]["bindings"]]
        binding_fields = [str(item["field"]) for item in policy["relationships"]["bindings"]]
        if len(binding_names) != len(set(binding_names)) or len(binding_fields) != len(set(binding_fields)):
            _fail(f"Incomplete artifact binding policy for {name}: duplicate name or field")
        locator_template = str(policy["locator"]["template"])
        _safe_relative(
            locator_template,
            label=f"Artifact locator policy for {name}",
            reject_glob=True,
        )
        parsed_template = list(string.Formatter().parse(locator_template))
        if any(format_spec or conversion for _literal, _field, format_spec, conversion in parsed_template):
            _fail(f"Incomplete artifact locator policy for {name}: formatting is not supported")
        placeholders = {
            field_name
            for _literal, field_name, _format, _conversion in parsed_template
            if field_name is not None
        }
        locator_variables = set(policy["locator"]["variables"])
        if placeholders != locator_variables:
            _fail(f"Incomplete artifact locator policy for {name}: variables do not match template")
        supported_locator_variables = {"id", "state", *binding_names}
        unsupported_locator_variables = sorted(locator_variables - supported_locator_variables)
        if unsupported_locator_variables:
            _fail(
                f"Incomplete artifact locator policy for {name}: unsupported variables: "
                f"{', '.join(unsupported_locator_variables)}"
            )
        states = set(policy["lifecycle"]["states"])
        transitions = policy["lifecycle"]["transitions"]
        if not set(transitions).issubset(states) or any(
            not set(targets).issubset(states) for targets in transitions.values()
        ):
            _fail(f"Incomplete artifact lifecycle policy for {name}: unknown state")
        if policy["lifecycle"]["authority"] == "location":
            if "id" not in locator_variables:
                _fail(f"Incomplete artifact locator policy for {name}: does not distinguish identity")
            if (len(states) > 1 or any(transitions.values())) and "state" not in locator_variables:
                _fail(
                    f"Incomplete artifact locator policy for {name}: "
                    "does not distinguish lifecycle state"
                )
        index = policy["index"]
        if index.get("policy") != "none":
            _safe_relative(
                str(index["path"]),
                label=f"Artifact index policy for {name}",
                reject_glob=True,
            )
            if (
                not set(index["source_states"]).issubset(states)
                or policy["identity"]["field"] not in index["projection"]
            ):
                _fail(f"Incomplete artifact index policy for {name}")
    return catalog


def family_policy(catalog: Mapping[str, Any], family: str) -> dict[str, Any]:
    matches = [item for item in catalog.get("families", []) if item.get("name") == family]
    if len(matches) != 1:
        _fail(f"Unregistered artifact family: {family}")
    return dict(matches[0])


def _validated_bindings(
    policy: Mapping[str, Any],
    data: Mapping[str, Any],
    bindings: Mapping[str, str] | None,
    *,
    derive_from_data: bool = False,
) -> dict[str, str]:
    supplied = dict(bindings or {})
    result: dict[str, str] = {}
    definitions = policy["relationships"]["bindings"]
    declared_names = {str(binding["name"]) for binding in definitions}
    unknown = sorted(set(supplied) - declared_names)
    if unknown:
        _fail(f"Unknown artifact binding: {', '.join(unknown)}")
    for binding in definitions:
        name = str(binding["name"])
        field = str(binding["field"])
        actual = data.get(field)
        expected = supplied.get(name)
        if derive_from_data and expected is None and actual is not None:
            expected = str(actual)
        if binding["required"] and expected is None:
            _fail(f"Missing required artifact binding: {name}")
        if expected is not None and str(actual) != str(expected):
            _fail(f"Artifact binding mismatch for {name}: expected {expected}, found {actual}")
        if expected is not None:
            result[name] = str(expected)
    return result


def validate_artifact(
    policy: Mapping[str, Any],
    data: Mapping[str, Any],
    *,
    catalog_path: Path,
    bindings: Mapping[str, str] | None = None,
    derive_bindings: bool = False,
) -> dict[str, str]:
    identity_field = str(policy["identity"]["field"])
    identity = data.get(identity_field)
    if not isinstance(identity, str) or re.fullmatch(str(policy["identity"]["pattern"]), identity) is None:
        _fail(f"Invalid artifact identity for {identity_field}: {identity!r}")
    schema_path = _schema_path(catalog_path.resolve(), policy)
    schema = _json_mapping(schema_path)
    try:
        jsonschema.Draft202012Validator(schema).validate(dict(data))
    except jsonschema.ValidationError as exc:
        _fail(f"Artifact schema validation failed for {policy['name']}: {exc.message}")
    return _validated_bindings(
        policy, data, bindings, derive_from_data=derive_bindings
    )


def canonical_artifact_path(
    policy: Mapping[str, Any],
    anchors: Mapping[str, Path],
    *,
    identity: str,
    state: str,
    bindings: Mapping[str, str] | None = None,
) -> Path:
    if re.fullmatch(str(policy["identity"]["pattern"]), identity) is None:
        _fail(f"Invalid artifact identity: {identity}")
    anchor_name = str(policy["anchor"])
    if anchor_name not in anchors:
        _fail(f"Missing artifact anchor: {anchor_name}")
    states = [str(item) for item in policy["lifecycle"]["states"]]
    if state not in states:
        _fail(f"Invalid artifact lifecycle state for {policy['name']}: {state}")
    variables = {"id": identity, "state": state, **dict(bindings or {})}
    declared = set(policy["locator"]["variables"])
    missing = sorted(declared - set(variables))
    if missing:
        _fail(f"Missing artifact locator variables: {', '.join(missing)}")
    try:
        rendered = str(policy["locator"]["template"]).format(**{key: variables[key] for key in declared})
    except (KeyError, ValueError) as exc:
        _fail(f"Invalid artifact locator template for {policy['name']}: {exc}")
    relative = _safe_relative(rendered, label="Artifact locator")
    anchor = Path(anchors[anchor_name]).resolve()
    target = (anchor / relative).resolve()
    if target != anchor and anchor not in target.parents:
        _fail(f"Artifact locator escapes anchor: {rendered}")
    return target


def serialize_artifact(
    policy: Mapping[str, Any], data: Mapping[str, Any], body: str | None = None
) -> bytes:
    encoded = yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=True)
    if policy["representation"] == "yaml":
        if body not in {None, ""}:
            _fail(f"YAML artifact family does not accept a semantic body: {policy['name']}")
        return encoded.encode("utf-8")
    if policy["representation"] == "markdown-front-matter":
        semantic_body = (body or "").rstrip()
        return (f"---\n{encoded}---\n" + (f"{semantic_body}\n" if semantic_body else "")).encode("utf-8")
    _fail(f"Unsupported artifact representation: {policy['representation']}")


def serialize_markdown_mapping(data: Mapping[str, Any], body: str) -> bytes:
    encoded = yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=False)
    return (f"---\n{encoded}---\n" + body).encode("utf-8")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    if existing_mode is None:
        current_umask = os.umask(0)
        os.umask(current_umask)
        creation_mode = 0o666 & ~current_umask
    else:
        creation_mode = existing_mode
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, creation_mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _read_stored(
    catalog_path: Path,
    policy: Mapping[str, Any],
    path: Path,
    *,
    bindings: Mapping[str, str] | None,
    derive_bindings: bool = False,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    if policy["representation"] == "yaml":
        data, body = read_yaml_mapping(path), ""
    else:
        data, body = read_markdown_artifact(path)
    validated = validate_artifact(
        policy,
        data,
        catalog_path=catalog_path,
        bindings=bindings,
        derive_bindings=derive_bindings,
    )
    return data, body, validated


def read_artifact(
    catalog_path: Path,
    family: str,
    anchors: Mapping[str, Path],
    *,
    identity: str,
    state: str,
    bindings: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    catalog_path = catalog_path.resolve()
    policy = family_policy(load_catalog(catalog_path), family)
    path = canonical_artifact_path(
        policy, anchors, identity=identity, state=state, bindings=bindings
    )
    if not path.is_file():
        _fail(f"Artifact not found at canonical location: {path}")
    data, body, validated = _read_stored(catalog_path, policy, path, bindings=bindings)
    if str(data[policy["identity"]["field"]]) != identity:
        _fail(f"Artifact identity does not match canonical location: {path}")
    result = _result(
        policy, path, data, validated, state=state, index_effect="none", partial_effect=False
    )
    result["data"] = data
    result["body"] = body
    return result


def _result(
    policy: Mapping[str, Any], path: Path, data: Mapping[str, Any], bindings: Mapping[str, str],
    *, state: str, index_effect: str, partial_effect: bool,
) -> dict[str, Any]:
    return {
        "family": policy["name"],
        "identity": data[policy["identity"]["field"]],
        "path": str(path),
        "schema": policy["schema"]["id"],
        "state": state,
        "digest": hashlib.sha256(path.read_bytes()).hexdigest(),
        "validated_bindings": dict(bindings),
        "index_effect": index_effect,
        "partial_effect": partial_effect,
    }


def write_artifact(
    catalog_path: Path,
    family: str,
    anchors: Mapping[str, Path],
    data: Mapping[str, Any],
    *,
    state: str,
    bindings: Mapping[str, str] | None = None,
    body: str | None = None,
    rebuild: bool = True,
) -> dict[str, Any]:
    catalog_path = catalog_path.resolve()
    policy = family_policy(load_catalog(catalog_path), family)
    validated = validate_artifact(policy, data, catalog_path=catalog_path, bindings=bindings)
    identity = str(data[policy["identity"]["field"]])
    path = canonical_artifact_path(policy, anchors, identity=identity, state=state, bindings=validated)
    content = serialize_artifact(policy, data, body)
    atomic_write_bytes(path, content)
    stored, _stored_body, stored_bindings = _read_stored(
        catalog_path, policy, path, bindings=validated
    )
    expected = canonical_artifact_path(
        policy, anchors, identity=str(stored[policy["identity"]["field"]]), state=state, bindings=stored_bindings
    )
    if expected != path:
        _fail(f"Stored artifact is in the wrong canonical location: {path}")
    index_effect = "not-requested"
    if rebuild and policy["index"].get("policy") != "none":
        try:
            rebuild_index(catalog_path, family, anchors)
            index_effect = "rebuilt"
        except (OSError, SystemExit) as exc:
            _fail(f"Artifact was written but index rebuild failed (partial effect): {exc}")
    return _result(
        policy, path, stored, stored_bindings, state=state,
        index_effect=index_effect, partial_effect=False,
    )


def transition_artifact(
    catalog_path: Path,
    family: str,
    anchors: Mapping[str, Path],
    *,
    identity: str,
    current_state: str,
    target_state: str,
    bindings: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    catalog_path = catalog_path.resolve()
    policy = family_policy(load_catalog(catalog_path), family)
    source = canonical_artifact_path(policy, anchors, identity=identity, state=current_state, bindings=bindings)
    if not source.is_file():
        _fail(f"Artifact source not found: {source}")
    data, _body, validated = _read_stored(catalog_path, policy, source, bindings=bindings)
    canonical_source = canonical_artifact_path(
        policy, anchors, identity=str(data[policy["identity"]["field"]]), state=current_state, bindings=validated
    )
    if canonical_source != source:
        _fail(f"Artifact source is in the wrong canonical location: {source}")
    if target_state == current_state:
        return _result(policy, source, data, validated, state=current_state, index_effect="none", partial_effect=False)
    allowed = policy["lifecycle"]["transitions"].get(current_state, [])
    if target_state not in allowed:
        _fail(f"Artifact lifecycle transition is not allowed: {current_state} -> {target_state}")
    target = canonical_artifact_path(policy, anchors, identity=identity, state=target_state, bindings=validated)
    if target.exists():
        _fail(f"Artifact lifecycle destination collision: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
    moved, _moved_body, moved_bindings = _read_stored(catalog_path, policy, target, bindings=validated)
    return _result(policy, target, moved, moved_bindings, state=target_state, index_effect="not-rebuilt", partial_effect=False)


def _candidate_pattern(policy: Mapping[str, Any], state: str) -> str:
    template = str(policy["locator"]["template"])
    values = {name: "*" for name in policy["locator"]["variables"]}
    values["state"] = state
    try:
        return template.format(**values)
    except (KeyError, ValueError) as exc:
        _fail(f"Invalid artifact index locator for {policy['name']}: {exc}")


def rebuild_index(
    catalog_path: Path, family: str, anchors: Mapping[str, Path]
) -> dict[str, Any]:
    catalog_path = catalog_path.resolve()
    policy = family_policy(load_catalog(catalog_path), family)
    index_policy = policy["index"]
    if index_policy.get("policy") == "none":
        _fail(f"Artifact family has no index policy: {family}")
    anchor = Path(anchors[str(policy["anchor"])]).resolve()
    rows: list[dict[str, Any]] = []
    identities: set[str] = set()
    for state in index_policy["source_states"]:
        pattern = _candidate_pattern(policy, str(state))
        for candidate in sorted(anchor.glob(pattern)):
            try:
                data, _body, bindings = _read_stored(
                    catalog_path,
                    policy,
                    candidate,
                    bindings=None,
                    derive_bindings=True,
                )
                identity = str(data[policy["identity"]["field"]])
                expected = canonical_artifact_path(
                    policy, anchors, identity=identity, state=str(state), bindings=bindings
                )
                if candidate.resolve() != expected:
                    _fail(f"wrong canonical placement: expected {expected}")
                if identity in identities:
                    _fail(f"duplicate identity: {identity}")
                identities.add(identity)
                rows.append({field: data[field] for field in index_policy["projection"]})
            except (OSError, SystemExit) as exc:
                _fail(f"Invalid index candidate {candidate}: {exc}")
    rows.sort(key=lambda row: str(row[policy["identity"]["field"]]))
    index_relative = _safe_relative(str(index_policy["path"]), label="Artifact index path")
    target = (anchor / index_relative).resolve()
    if target != anchor and anchor not in target.parents:
        _fail(f"Artifact index path escapes anchor: {index_policy['path']}")
    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")
    atomic_write_bytes(target, content)
    return {"path": str(target), "count": len(rows), "digest": hashlib.sha256(content).hexdigest()}
