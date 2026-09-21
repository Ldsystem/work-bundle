"""Shared structural contracts for WorkBundle infrastructure metadata."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

import jsonschema
import yaml


CATALOG_RELATIVE_PATH = Path(
    "references/assets/infrastructure/contract/infrastructure-schema-catalog-v1.yaml"
)
CONFIG_ROOT_TOKEN = "$work_bundle_config_root"


class InfrastructureError(RuntimeError):
    """Typed structural failure consumable by public dispatchers."""

    def __init__(self, code: str, message: str, *, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class AnchorContext:
    config_root: Path
    workspace_root: Path
    project_root: Path | None
    workspace_id: str
    repository_id: str | None


@dataclass(frozen=True)
class WorkspaceContext:
    config_root: Path
    workspace_root: Path
    workspace_id: str


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


_UniqueKeyLoader.yaml_implicit_resolvers = deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for first_character, resolvers in list(_UniqueKeyLoader.yaml_implicit_resolvers.items()):
    _UniqueKeyLoader.yaml_implicit_resolvers[first_character] = [
        (tag, expression)
        for tag, expression in resolvers
        if tag != "tag:yaml.org,2002:timestamp"
    ]


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _toolkit_root(toolkit_root: str | Path | None) -> Path:
    return Path(toolkit_root).expanduser().resolve() if toolkit_root else Path(__file__).resolve().parents[2]


def parse_yaml_mapping(text: str, *, source: str) -> dict[str, Any]:
    try:
        loaded = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_YAML_INVALID", f"Invalid YAML in {source}: {exc}", details={"source": source}
        ) from exc
    if not isinstance(loaded, dict):
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_MAPPING_REQUIRED",
            f"Infrastructure document must be a mapping: {source}",
            details={"source": source},
        )
    return loaded


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    source_path = Path(path).expanduser().resolve()
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_READ_FAILED", f"Unable to read {source_path}: {exc}", details={"path": str(source_path)}
        ) from exc
    return parse_yaml_mapping(text, source=str(source_path))


def load_schema_catalog(*, toolkit_root: str | Path | None = None) -> dict[str, Any]:
    root = _toolkit_root(toolkit_root)
    catalog = load_yaml_mapping(root / CATALOG_RELATIVE_PATH)
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("families"), dict):
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_CATALOG_INVALID", "Infrastructure schema catalog must be version 1"
        )
    return catalog


def _schema_for(family: str, *, toolkit_root: str | Path | None) -> dict[str, Any]:
    root = _toolkit_root(toolkit_root)
    catalog = load_schema_catalog(toolkit_root=root)
    descriptor = catalog["families"].get(family)
    if not isinstance(descriptor, dict) or descriptor.get("version") != 1:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_SCHEMA_FAMILY_UNKNOWN", f"Unknown infrastructure schema family: {family}"
        )
    relative = descriptor.get("schema")
    if not isinstance(relative, str) or not relative:
        raise InfrastructureError("WB_INFRASTRUCTURE_CATALOG_INVALID", f"Missing schema path for {family}")
    contract_root = (root / CATALOG_RELATIVE_PATH).parent.resolve()
    schema_path = (contract_root / relative).resolve()
    if schema_path.parent != contract_root:
        raise InfrastructureError("WB_INFRASTRUCTURE_CATALOG_INVALID", f"Schema path escapes catalog: {relative}")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_SCHEMA_READ_FAILED", f"Unable to load schema {schema_path}: {exc}"
        ) from exc
    if not isinstance(schema, dict):
        raise InfrastructureError("WB_INFRASTRUCTURE_SCHEMA_INVALID", f"Schema is not an object: {schema_path}")
    return schema


def _require_unique_strings(values: Sequence[Mapping[str, Any]], key: str, *, family: str) -> None:
    seen: set[str] = set()
    for item in values:
        value = item.get(key)
        if isinstance(value, str) and value in seen:
            raise InfrastructureError(
                "WB_INFRASTRUCTURE_ID_DUPLICATE",
                f"Duplicate {key} {value!r} in {family}",
                details={"family": family, "key": key, "value": value},
            )
        if isinstance(value, str):
            seen.add(value)


def validate_infrastructure_document(
    data: Mapping[str, Any], *, family: str, toolkit_root: str | Path | None = None
) -> dict[str, Any]:
    schema = _schema_for(family, toolkit_root=toolkit_root)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(data)
    except (jsonschema.SchemaError, jsonschema.ValidationError) as exc:
        path = "/".join(str(part) for part in getattr(exc, "absolute_path", ()))
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_SCHEMA_INVALID",
            f"{family} failed structural validation{f' at {path}' if path else ''}: {exc.message}",
            details={"family": family, "path": path},
        ) from exc
    if family == "workspace-project-metadata":
        repositories = data.get("source_repositories", [])
        if isinstance(repositories, list):
            _require_unique_strings(repositories, "id", family=family)
            workspace = data.get("workspace", {})
            mode = workspace.get("mode") if isinstance(workspace, Mapping) else None
            root_count = 0
            member_names: set[str] = set()
            for repository in repositories:
                binding = repository.get("workspace_binding", {})
                binding_type = binding.get("type") if isinstance(binding, Mapping) else None
                if binding_type == "root":
                    root_count += 1
                elif binding_type == "member":
                    name = binding.get("name")
                    if name in member_names:
                        raise InfrastructureError(
                            "WB_INFRASTRUCTURE_ID_DUPLICATE",
                            f"Duplicate workspace member name {name!r}",
                            details={"family": family, "key": "workspace_binding.name", "value": name},
                        )
                    member_names.add(name)
            invalid_topology = (
                (mode == "single-repository" and (len(repositories) != 1 or root_count != 1))
                or (mode == "multi-repository" and root_count != 0)
                or (mode == "composite" and root_count != 1)
            )
            if invalid_topology:
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_SCHEMA_INVALID",
                    f"Repository bindings do not satisfy {mode!r} workspace topology",
                    details={"family": family, "mode": mode},
                )
    elif family == "project-registry":
        projects = data.get("projects", [])
        if isinstance(projects, list):
            _require_unique_strings(projects, "slug", family=family)
    return deepcopy(dict(data))


def load_infrastructure_document(
    path: str | Path, *, family: str, toolkit_root: str | Path | None = None
) -> dict[str, Any]:
    return validate_infrastructure_document(
        load_yaml_mapping(path), family=family, toolkit_root=toolkit_root
    )


def dump_canonical_yaml(data: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(data), allow_unicode=True, default_flow_style=False, sort_keys=True)


def atomic_write_text(path: str | Path, content: str) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_ATOMIC_WRITE_FAILED", f"Unable to atomically write {target}: {exc}"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_ATOMIC_WRITE_FAILED", f"Unable to atomically write {target}: {exc}"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def resolve_config_root(config_root: str | Path | None = None) -> Path:
    return Path(config_root).expanduser().resolve() if config_root else (Path.home() / ".work-bundle").resolve()


def load_bootstrap(
    *, config_root: str | Path | None = None, toolkit_root: str | Path | None = None
) -> dict[str, Any]:
    root = resolve_config_root(config_root)
    return load_infrastructure_document(
        root / "bootstrap.yaml", family="bootstrap-config", toolkit_root=toolkit_root
    )


def resolve_project_registry_path(
    *, config_root: str | Path | None = None, toolkit_root: str | Path | None = None
) -> Path:
    root = resolve_config_root(config_root)
    raw = load_bootstrap(config_root=root, toolkit_root=toolkit_root)["project_registry"]
    if raw == CONFIG_ROOT_TOKEN:
        return root
    prefix = CONFIG_ROOT_TOKEN + "/"
    return ((root / raw[len(prefix) :]) if raw.startswith(prefix) else Path(raw).expanduser()).resolve()


def load_project_registry(
    *, config_root: str | Path | None = None, toolkit_root: str | Path | None = None
) -> dict[str, Any]:
    return load_infrastructure_document(
        resolve_project_registry_path(config_root=config_root, toolkit_root=toolkit_root),
        family="project-registry",
        toolkit_root=toolkit_root,
    )


def find_workspace_root(start: str | Path) -> Path | None:
    candidate = Path(start).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for current in (candidate, *candidate.parents):
        if (current / ".work-bundle/project.yaml").is_file():
            return current
    return None


def resolve_workspace_context(
    *,
    workspace_root: str | Path | None = None,
    project_root: str | Path | None = None,
    cwd: str | Path | None = None,
    config_root: str | Path | None = None,
    toolkit_root: str | Path | None = None,
) -> WorkspaceContext:
    """Resolve workspace authority without asserting source-checkout freshness."""
    selected_project = Path(project_root).expanduser().resolve() if project_root is not None else None
    selected_workspace = Path(workspace_root).expanduser().resolve() if workspace_root is not None else None
    current = Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd().resolve()
    inferred = find_workspace_root(selected_project or current)
    if selected_workspace is None:
        selected_workspace = inferred
    elif selected_project is not None and inferred != selected_workspace:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_ANCHOR_CONFLICT",
            "Workspace and project selectors do not identify the same workspace",
        )
    if selected_workspace is None:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_WORKSPACE_NOT_FOUND", "No containing WorkBundle workspace metadata was found"
        )

    metadata = load_workspace_metadata(selected_workspace, toolkit_root=toolkit_root)
    registry = load_yaml_mapping(
        resolve_project_registry_path(config_root=config_root, toolkit_root=toolkit_root)
    )
    if registry.get("registry_schema_version") != 1 or not isinstance(registry.get("device_bindings"), Mapping):
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_SCHEMA_INVALID",
            "Project registry workspace identity fields are invalid",
        )
    workspace = metadata.get("workspace")
    workspace_id = workspace.get("id") if isinstance(workspace, Mapping) else None
    bindings = registry.get("device_bindings")
    binding = bindings.get(workspace_id) if isinstance(bindings, Mapping) else None
    if not isinstance(binding, Mapping):
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_WORKSPACE_BINDING_MISSING",
            f"No device binding exists for workspace {workspace_id!r}",
            details={"workspace_id": workspace_id},
        )
    if binding.get("slug") != workspace.get("slug"):
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_WORKSPACE_BINDING_CONTRADICTORY",
            "The device binding slug contradicts portable workspace metadata",
        )
    if not isinstance(binding.get("repositories"), Mapping):
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_SCHEMA_INVALID",
            "The device binding repository collection is invalid",
        )
    bound_workspace = Path(str(binding.get("workspace_root", ""))).expanduser().resolve()
    if bound_workspace != selected_workspace:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_WORKSPACE_BINDING_CONTRADICTORY",
            "The device binding workspace root contradicts the selected workspace",
        )
    return WorkspaceContext(
        config_root=resolve_config_root(config_root),
        workspace_root=selected_workspace,
        workspace_id=str(workspace_id),
    )


def load_workspace_metadata(
    workspace_root: str | Path, *, toolkit_root: str | Path | None = None
) -> dict[str, Any]:
    return load_infrastructure_document(
        Path(workspace_root).expanduser().resolve() / ".work-bundle/project.yaml",
        family="workspace-project-metadata",
        toolkit_root=toolkit_root,
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def join_workspace_binding(
    metadata: Mapping[str, Any],
    registry: Mapping[str, Any],
    *,
    expected_workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    workspace = metadata.get("workspace")
    workspace_id = workspace.get("id") if isinstance(workspace, Mapping) else None
    bindings = registry.get("device_bindings")
    binding = bindings.get(workspace_id) if isinstance(bindings, Mapping) else None
    if not isinstance(binding, Mapping):
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_WORKSPACE_BINDING_MISSING",
            f"No device binding exists for workspace {workspace_id!r}",
            details={"workspace_id": workspace_id},
        )
    if binding.get("slug") != workspace.get("slug"):
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_WORKSPACE_BINDING_CONTRADICTORY",
            "The device binding slug contradicts portable workspace metadata",
        )
    actual_workspace = Path(str(binding.get("workspace_root", ""))).expanduser().resolve()
    if expected_workspace_root is not None and actual_workspace != Path(expected_workspace_root).expanduser().resolve():
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_WORKSPACE_BINDING_CONTRADICTORY",
            "The device binding workspace root contradicts the selected workspace",
        )
    portable_repositories = metadata.get("source_repositories")
    bound_repositories = binding.get("repositories")
    if not isinstance(portable_repositories, list) or not isinstance(bound_repositories, Mapping):
        raise InfrastructureError("WB_INFRASTRUCTURE_BINDING_INVALID", "Workspace binding repositories are invalid")
    portable_ids = {repository.get("id") for repository in portable_repositories if isinstance(repository, Mapping)}
    if set(bound_repositories) - portable_ids:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_REPOSITORY_BINDING_CONTRADICTORY",
            "Device binding contains repositories absent from portable metadata",
        )
    normalized_repositories: dict[str, dict[str, Any]] = {}
    mode = workspace.get("mode") if isinstance(workspace, Mapping) else None
    for repository in portable_repositories:
        repository_id = repository.get("id") if isinstance(repository, Mapping) else None
        local = bound_repositories.get(repository_id)
        materialization = repository.get("materialization", {}) if isinstance(repository, Mapping) else {}
        required = materialization.get("required", False) if isinstance(materialization, Mapping) else False
        materialization_state = materialization.get("state") if isinstance(materialization, Mapping) else None
        if not isinstance(local, Mapping):
            if materialization_state in {"deferred", "failed"}:
                continue
            if required:
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_REPOSITORY_BINDING_MISSING",
                    f"No device binding exists for repository {repository_id!r}",
                )
            continue
        project_root = Path(str(local.get("project_root", ""))).expanduser().resolve()
        portable_binding = repository.get("workspace_binding", {})
        root_binding = portable_binding.get("type") == "root"
        expected_project_root = (
            actual_workspace
            if root_binding or mode == "single-repository"
            else (actual_workspace / str(portable_binding.get("path") or portable_binding.get("name") or "")).resolve()
        )
        if project_root != expected_project_root:
            raise InfrastructureError(
                "WB_INFRASTRUCTURE_PROJECT_ROOT_ESCAPE",
                f"Repository {repository_id!r} does not match its portable workspace binding",
                details={"repository_id": repository_id, "project_root": str(project_root)},
            )
        checkout_kind = str(local.get("checkout_kind") or "")
        observed_at = str(local.get("observed_at") or "")
        if not checkout_kind or not observed_at:
            raise InfrastructureError(
                "WB_INFRASTRUCTURE_OBSERVATION_MISSING",
                f"Repository {repository_id!r} device binding lacks checkout or observation evidence",
                details={"repository_id": repository_id},
            )
        portable_locator = repository.get("locator") if isinstance(repository, Mapping) else None
        if checkout_kind == "manual":
            if not isinstance(portable_locator, Mapping) or portable_locator.get("type") != "manual":
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_REPOSITORY_BINDING_CONTRADICTORY",
                    f"Repository {repository_id!r} uses a manual binding without a portable manual locator",
                )
        elif checkout_kind == "unmaterialized-member":
            if any(str(local.get(field) or "") for field in ("observed_branch", "observed_head", "git_common_dir")):
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_REPOSITORY_BINDING_CONTRADICTORY",
                    f"Unmaterialized repository {repository_id!r} carries invented checkout observations",
                )
        else:
            missing_observations = [
                field for field in ("observed_branch", "observed_head", "git_common_dir")
                if not str(local.get(field) or "")
            ]
            if missing_observations:
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_OBSERVATION_MISSING",
                    f"Repository {repository_id!r} device binding lacks checkout observations",
                    details={"repository_id": repository_id, "fields": missing_observations},
                )
        common_raw = str(local.get("git_common_dir") or "")
        if common_raw:
            common_dir = Path(common_raw).expanduser()
            if not common_dir.is_absolute():
                common_dir = project_root / common_dir
            common_dir = common_dir.resolve()
            if not _is_within(common_dir, actual_workspace):
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_GIT_COMMON_DIR_ESCAPE",
                    f"Repository {repository_id!r} git common directory escapes the workspace",
                )
        normalized = deepcopy(dict(local))
        normalized["project_root"] = project_root
        normalized_repositories[str(repository_id)] = normalized
    result = deepcopy(dict(binding))
    result["workspace_root"] = actual_workspace
    result["repositories"] = normalized_repositories
    return result


def resolve_anchor_context(
    *,
    workspace_root: str | Path | None = None,
    project_root: str | Path | None = None,
    cwd: str | Path | None = None,
    config_root: str | Path | None = None,
    toolkit_root: str | Path | None = None,
    member_required: bool = False,
) -> AnchorContext:
    selected_project = Path(project_root).expanduser().resolve() if project_root is not None else None
    selected_workspace = Path(workspace_root).expanduser().resolve() if workspace_root is not None else None
    current = Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd().resolve()
    inferred = find_workspace_root(selected_project or current)
    if selected_workspace is None:
        selected_workspace = inferred
    elif selected_project is not None and inferred is not None and inferred != selected_workspace:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_ANCHOR_CONFLICT", "Workspace and project selectors do not identify the same workspace"
        )
    if selected_workspace is None:
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_WORKSPACE_NOT_FOUND", "No containing WorkBundle workspace metadata was found"
        )
    metadata = load_workspace_metadata(selected_workspace, toolkit_root=toolkit_root)
    registry = load_project_registry(config_root=config_root, toolkit_root=toolkit_root)
    binding = join_workspace_binding(metadata, registry, expected_workspace_root=selected_workspace)
    repositories = binding["repositories"]
    matches: list[tuple[str, Path]] = []
    anchor = selected_project or (current if workspace_root is None else None)
    if anchor is not None:
        for repository_id, local in repositories.items():
            if local.get("checkout_kind") == "unmaterialized-member":
                continue
            candidate = local["project_root"]
            if anchor == candidate or (selected_project is None and _is_within(anchor, candidate)):
                matches.append((repository_id, candidate))
        matches.sort(key=lambda item: len(item[1].parts), reverse=True)
    repository_id: str | None = matches[0][0] if matches else None
    resolved_project: Path | None = matches[0][1] if matches else None
    if selected_project is not None and resolved_project is None:
        unmaterialized = [
            identifier for identifier, local in repositories.items()
            if local.get("checkout_kind") == "unmaterialized-member" and local["project_root"] == selected_project
        ]
        if unmaterialized:
            raise InfrastructureError(
                "WB_INFRASTRUCTURE_REPOSITORY_UNMATERIALIZED",
                f"Selected repository {unmaterialized[0]!r} is explicitly unmaterialized",
                details={"repository_id": unmaterialized[0]},
            )
        raise InfrastructureError(
            "WB_INFRASTRUCTURE_PROJECT_BINDING_MISSING", "Selected project does not match an exact device-bound member"
        )
    if member_required and resolved_project is None:
        candidates = [
            (identifier, local["project_root"])
            for identifier, local in repositories.items()
            if local.get("checkout_kind") != "unmaterialized-member"
        ]
        if len(candidates) != 1:
            if not candidates and any(
                local.get("checkout_kind") == "unmaterialized-member" for local in repositories.values()
            ):
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_REPOSITORY_UNMATERIALIZED",
                    "A member is required but all device-bound repositories are explicitly unmaterialized",
                )
            raise InfrastructureError(
                "WB_INFRASTRUCTURE_MEMBER_AMBIGUOUS",
                "A member is required but the workspace does not have exactly one eligible binding",
                details={"candidate_count": len(candidates)},
            )
        repository_id, resolved_project = candidates[0]
    if resolved_project is not None:
        if not resolved_project.is_dir():
            raise InfrastructureError(
                "WB_INFRASTRUCTURE_PROJECT_ROOT_MISSING",
                f"Selected repository root does not exist: {resolved_project}",
            )
        local = repositories[str(repository_id)]
        if local.get("checkout_kind") == "manual":
            workspace_id = str(metadata["workspace"]["id"])
            return AnchorContext(
                config_root=resolve_config_root(config_root),
                workspace_root=selected_workspace,
                project_root=resolved_project,
                workspace_id=workspace_id,
                repository_id=repository_id,
            )
        for field, command in (
            ("observed_branch", ("branch", "--show-current")),
            ("observed_head", ("rev-parse", "HEAD")),
        ):
            expected = str(local.get(field) or "")
            if not expected:
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_OBSERVATION_MISSING",
                    f"Device observation {field} is missing for repository {repository_id!r}",
                    details={"repository_id": repository_id, "field": field},
                )
            completed = subprocess.run(
                ["git", "-C", str(resolved_project), *command],
                capture_output=True, text=True, check=False,
            )
            if completed.returncode != 0 or completed.stdout.strip() != expected:
                raise InfrastructureError(
                    "WB_INFRASTRUCTURE_OBSERVATION_STALE",
                    f"Device observation {field} is stale for repository {repository_id!r}",
                    details={"repository_id": repository_id, "field": field},
                )
        expected_common = Path(str(local["git_common_dir"])).expanduser()
        if not expected_common.is_absolute():
            expected_common = resolved_project / expected_common
        completed = subprocess.run(
            ["git", "-C", str(resolved_project), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0 or Path(completed.stdout.strip()).resolve() != expected_common.resolve():
            raise InfrastructureError(
                "WB_INFRASTRUCTURE_OBSERVATION_STALE",
                f"Device observation git_common_dir is stale for repository {repository_id!r}",
                details={"repository_id": repository_id, "field": "git_common_dir"},
            )
    workspace_id = str(metadata["workspace"]["id"])
    return AnchorContext(
        config_root=resolve_config_root(config_root),
        workspace_root=selected_workspace,
        project_root=resolved_project,
        workspace_id=workspace_id,
        repository_id=repository_id,
    )
