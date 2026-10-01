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

DIAGNOSTIC_LIMIT = 20
ALTERNATIVE_LIMIT = 3


class ArtifactError(SystemExit):
    """Human failure and structured observations from the same safe result."""

    def __init__(self, message: str, diagnostics: list[dict[str, Any]], *, total: int | None = None,
                 write_effect: str = "rejected", index_effect: str = "not-requested"):
        self.diagnostics = diagnostics
        self.diagnostic = self.diagnostics[0] if self.diagnostics else None
        self.diagnostic_count = len(diagnostics) if total is None else total
        self.write_effect = write_effect
        self.index_effect = index_effect
        self.partial_effect = write_effect == "applied"
        super().__init__(message)


def _safe_text(value: Any, limit: int | None = 120) -> str:
    # Escape terminal controls; never render validation exception messages containing instances.
    return json.dumps(str(value), ensure_ascii=True)[1:-1][:limit]


def _pointer(parts: Any) -> str:
    return "".join("/" + _safe_text(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _instance_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "non-json"


def _safe_expected(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, list):
        return [_safe_expected(item) for item in value[:8]]
    if isinstance(value, dict):
        return {"schema_keys": [_safe_text(key) for key in list(value)[:8]]}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "non-json constraint"


def _schema_diagnostic(policy: Mapping[str, Any], error: jsonschema.ValidationError) -> dict[str, Any]:
    parts = list(error.absolute_path)
    expected = error.validator_value
    if error.validator == "required" and isinstance(error.instance, dict):
        missing = [field for field in expected if field not in error.instance]
        if missing:
            # jsonschema emits one error per field but exposes the entire required list.
            # Match schema-owned names only; never render the exception's payload text.
            expected = next((field for field in missing
                             if error.message == f"{field!r} is a required property"), missing[0])
            parts.append(expected)
    elif error.validator == "additionalProperties" and isinstance(error.instance, dict):
        properties = error.schema.get("properties", {})
        patterns = error.schema.get("patternProperties", {})
        unexpected = sorted(str(key) for key in error.instance if key not in properties
                            and not any(re.search(pattern, str(key)) for pattern in patterns))
        expected = {"additional_properties": error.validator_value,
                    "allowed_properties": [_safe_text(field) for field in list(properties)[:8]]}
        if unexpected:
            parts.append(unexpected[0])
    actual_type = _instance_type(error.instance)
    size = len(error.instance) if isinstance(error.instance, (str, list, dict)) else None
    return {
        "code": f"schema.{error.validator}", "family": policy["name"],
        "schema": policy["schema"]["id"], "instance_path": _pointer(parts),
        "schema_path": _pointer(error.absolute_schema_path), "keyword": error.validator,
        "expected": expected if error.validator == "additionalProperties" else _safe_expected(expected),
        "actual_type": actual_type,
        "excerpt": f"<{actual_type}" + (f" length={size}" if size is not None else "") + ">",
    }


def _validation_diagnostics(policy: Mapping[str, Any], errors: Any) -> dict[str, Any] | None:
    leaves: list[tuple[jsonschema.ValidationError, tuple[int, ...]]] = []

    def flatten(error: jsonschema.ValidationError, branch_counts: tuple[int, ...] = ()) -> None:
        if not error.context:
            leaves.append((error, branch_counts))
            return
        branches: dict[Any, list[jsonschema.ValidationError]] = {}
        for child in error.context:
            branch = child.schema_path[0] if child.schema_path else 0
            branches.setdefault(branch, []).append(child)

        def count(error: jsonschema.ValidationError) -> int:
            return sum(count(child) for child in error.context) if error.context else 1

        for children in branches.values():
            size = sum(count(child) for child in children)
            for child in children:
                flatten(child, (*branch_counts, size))

    for error in errors:
        flatten(error)
    if not leaves:
        return None
    # Longest actual instance path, smallest failing branch, stable schema traversal.
    def rank(item: tuple[jsonschema.ValidationError, tuple[int, ...]]) -> Any:
        error, counts = item
        schema_order = tuple((0, part) if isinstance(part, int) else (1, str(part))
                             for part in error.absolute_schema_path)
        return (-len(error.absolute_path), counts or (1,), schema_order)

    leaves.sort(key=rank)
    selected = _schema_diagnostic(policy, leaves[0][0])
    selected["alternatives"] = [_schema_diagnostic(policy, error)
                                for error, _counts in leaves[1:ALTERNATIVE_LIMIT + 1]]
    selected["alternative_count"] = len(leaves) - 1
    return selected


def _raise_schema(policy: Mapping[str, Any], errors: Any) -> None:
    diagnostic = _validation_diagnostics(policy, errors)
    if diagnostic is not None:
        message = (f"Artifact schema validation failed for {policy['name']}: "
                   f"{diagnostic['instance_path'] or '/'}: {diagnostic['keyword']} "
                   f"expected {json.dumps(diagnostic['expected'], ensure_ascii=True)}; "
                   f"found {diagnostic['actual_type']} (schema {diagnostic['schema_path']})")
        raise ArtifactError(message, [diagnostic])


class _MaintainedLoader(yaml.SafeLoader):
    """Safe maintained YAML with date-like orchestration scalars kept as text."""


_MaintainedLoader.yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for _key, _resolvers in list(_MaintainedLoader.yaml_implicit_resolvers.items()):
    _MaintainedLoader.yaml_implicit_resolvers[_key] = [
        resolver for resolver in _resolvers if resolver[0] != "tag:yaml.org,2002:timestamp"
    ]


def _fail(message: str, *, code: str = "artifact.invalid") -> None:
    raise ArtifactError(message, [{"code": code}])


def _yaml_mapping(text: str, *, source: str) -> dict[str, Any]:
    try:
        value = yaml.load(text, Loader=_MaintainedLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        _fail(f"Invalid YAML in {_safe_text(source, 400)}{location}", code="parse.yaml")
    if not isinstance(value, dict):
        _fail(f"Expected a YAML mapping in {source}", code="parse.mapping")
    return value


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    return _yaml_mapping(_read_text(path), source=str(path))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError:
        _fail(f"Invalid UTF-8 artifact at {_safe_text(path, 400)}", code="parse.encoding")


def read_markdown_artifact(path: Path) -> tuple[dict[str, Any], str]:
    text = _read_text(path)
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
        _fail(f"Invalid YAML in {_safe_text(source, 400)}")


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
            _fail(f"Artifact binding mismatch for {name}", code="binding.mismatch")
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
        diagnostic = {"code": "identity.invalid", "family": policy["name"],
                      "schema": policy["schema"]["id"], "instance_path": _pointer([identity_field]),
                      "keyword": "pattern", "expected": policy["identity"]["pattern"],
                      "actual_type": _instance_type(identity)}
        raise ArtifactError(f"Invalid artifact identity for {identity_field}: expected {diagnostic['expected']}", [diagnostic])
    schema_path = _schema_path(catalog_path.resolve(), policy)
    schema = _json_mapping(schema_path)
    _raise_schema(policy, jsonschema.Draft202012Validator(schema).iter_errors(dict(data)))
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
    *, state: str, index_effect: str, partial_effect: bool, digest: str | None = None,
) -> dict[str, Any]:
    return {
        "family": policy["name"],
        "identity": data[policy["identity"]["field"]],
        "path": str(path),
        "schema": policy["schema"]["id"],
        "state": state,
        "digest": digest if digest is not None else hashlib.sha256(path.read_bytes()).hexdigest(),
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
    # Validate the staged representation before replacing authoritative bytes.
    staged = content.decode("utf-8")
    staged_data = (parse_yaml_mapping(staged) if policy["representation"] == "yaml"
                   else parse_markdown_artifact(staged)[0])
    validate_artifact(policy, staged_data, catalog_path=catalog_path, bindings=validated)
    _check_target_conflicts(catalog_path, policy, anchors, path, identity, validated)
    atomic_write_bytes(path, content)
    try:
        intact = path.read_bytes() == content
    except OSError:
        intact = False
    if not intact:
        raise ArtifactError("Artifact was written but its integrity check failed",
                            [{"code": "write.integrity", "path": str(path)}], write_effect="applied")
    index_effect = "not-requested"
    index_diagnostics: list[dict[str, Any]] = []
    diagnostic_count = 0
    if rebuild and policy["index"].get("policy") != "none":
        try:
            rebuild_index(catalog_path, family, anchors)
            index_effect = "rebuilt"
        except (OSError, SystemExit) as exc:
            index_effect = "stale"
            index_path = Path(anchors[str(policy["anchor"])]) / str(policy["index"]["path"])
            index_diagnostics = getattr(exc, "diagnostics", [{"code": "index.io", "path": str(index_path)}])
            diagnostic_count = getattr(exc, "diagnostic_count", len(index_diagnostics))
    result = _result(
        policy, path, staged_data, validated, state=state,
        index_effect=index_effect, partial_effect=index_effect == "stale",
        digest=hashlib.sha256(content).hexdigest(),
    )
    result.update(write_effect="applied", index_diagnostics=index_diagnostics,
                  index_diagnostic_count=diagnostic_count)
    return result


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


def _scan_candidates(
    catalog_path: Path, policy: Mapping[str, Any], anchors: Mapping[str, Path],
    states: Any, *, replacement: Path | None = None,
) -> list[dict[str, Any]]:
    """Declared catalog discovery only; raw identity remains a fact even if schema fails."""
    anchor = Path(anchors[str(policy["anchor"])]).resolve()
    observations: list[dict[str, Any]] = []
    identities: set[str] = set()
    for state in states:
        for candidate in sorted(anchor.glob(_candidate_pattern(policy, str(state)))):
            observation: dict[str, Any] = {"path": candidate, "state": str(state), "data": None}
            observations.append(observation)
            try:
                if policy["representation"] == "yaml":
                    data = read_yaml_mapping(candidate)
                else:
                    data, _body = read_markdown_artifact(candidate)
                observation["data"] = data
                if replacement is not None and candidate == replacement:
                    continue
                bindings = validate_artifact(policy, data, catalog_path=catalog_path, derive_bindings=True)
                identity = str(data[policy["identity"]["field"]])
                expected = canonical_artifact_path(policy, anchors, identity=identity,
                                                   state=str(state), bindings=bindings)
                if candidate.resolve() != expected:
                    _fail(f"wrong canonical placement: expected {expected}", code="location.noncanonical")
                if identity in identities:
                    _fail(f"duplicate identity: {identity}", code="identity.duplicate")
                identities.add(identity)
                observation["bindings"] = bindings
            except (OSError, SystemExit) as exc:
                diagnostic = dict(getattr(exc, "diagnostic", None) or {"code": "read.io"})
                diagnostic.update(path=str(candidate), family=policy["name"], schema=policy["schema"]["id"])
                observation["diagnostic"] = diagnostic
    return observations


def _check_target_conflicts(
    catalog_path: Path, policy: Mapping[str, Any], anchors: Mapping[str, Path],
    target: Path, identity: str, bindings: Mapping[str, str],
) -> None:
    conflicts: list[dict[str, Any]] = []
    occupied_states: set[Path] = set()
    # These are exact catalog-owned locations, not identities inferred from discovery names.
    for state in policy["lifecycle"]["states"]:
        candidate = canonical_artifact_path(policy, anchors, identity=identity,
                                            state=str(state), bindings=bindings)
        if candidate != target and candidate.exists():
            occupied_states.add(candidate)
            conflicts.append({"code": "target.identity-conflict", "path": str(candidate),
                              "family": policy["name"], "schema": policy["schema"]["id"],
                              "state": str(state)})
    for observation in _scan_candidates(catalog_path, policy, anchors,
                                        policy["lifecycle"]["states"], replacement=target):
        candidate = observation["path"]
        if candidate.resolve() in occupied_states:
            continue
        data = observation["data"]
        if data is None:
            continue  # An unreadable current target can be repaired; unrelated names confer no identity.
        actual = data.get(policy["identity"]["field"])
        code = None
        if candidate != target and actual == identity:
            code = "target.identity-conflict"
        elif candidate == target:
            if actual is not None and actual != identity:
                code = "target.identity-conflict"
            else:
                for binding in policy["relationships"]["bindings"]:
                    existing = data.get(binding["field"])
                    if existing is not None and existing != bindings.get(binding["name"]):
                        code = "target.binding-conflict"
                        break
        if code:
            conflicts.append({"code": code, "path": str(candidate), "family": policy["name"],
                              "schema": policy["schema"]["id"], "state": observation["state"]})
    if conflicts:
        raise ArtifactError("Artifact target conflict: " + "; ".join(
            f"{item['code']} at {_safe_text(item['path'], 400)}" for item in conflicts[:DIAGNOSTIC_LIMIT]), conflicts)


def rebuild_index(
    catalog_path: Path, family: str, anchors: Mapping[str, Path]
) -> dict[str, Any]:
    catalog_path = catalog_path.resolve()
    policy = family_policy(load_catalog(catalog_path), family)
    index_policy = policy["index"]
    if index_policy.get("policy") == "none":
        _fail(f"Artifact family has no index policy: {family}")
    anchor = Path(anchors[str(policy["anchor"])]).resolve()
    observations = _scan_candidates(catalog_path, policy, anchors, index_policy["source_states"])
    diagnostics = [item["diagnostic"] for item in observations if "diagnostic" in item]
    if diagnostics:
        raise ArtifactError("Invalid index candidate(s): " + "; ".join(
            f"{item['code']} at {_safe_text(item['path'], None)}" for item in diagnostics), diagnostics)
    rows = [{field: item["data"][field] for field in index_policy["projection"]} for item in observations]
    rows.sort(key=lambda row: str(row[policy["identity"]["field"]]))
    index_relative = _safe_relative(str(index_policy["path"]), label="Artifact index path")
    target = (anchor / index_relative).resolve()
    if target != anchor and anchor not in target.parents:
        _fail(f"Artifact index path escapes anchor: {index_policy['path']}")
    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")
    atomic_write_bytes(target, content)
    return {"path": str(target), "count": len(rows), "digest": hashlib.sha256(content).hexdigest()}
