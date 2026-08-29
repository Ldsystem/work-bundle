#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "pyyaml==6.0.3",
#   "sqlite-vec==0.1.9",
#   "fastembed==0.8.0",
# ]
# ///
"""Compatibility entrypoint for keep-summarizing helpers."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tomllib
from collections.abc import Mapping, Sequence
from importlib import metadata as importlib_metadata
from pathlib import Path

RUNTIME_DEPENDENCIES = (
    ("yaml", "pyyaml"),
    ("sqlite_vec", "sqlite-vec"),
    ("fastembed", "fastembed"),
)
UV_REEXEC_ENV = "WORK_BUNDLE_KS_UV_REEXEC"


def _declared_runtime_versions() -> dict[str, str]:
    metadata_lines: list[str] = []
    inside_script_metadata = False
    for line in Path(__file__).read_text(encoding="utf-8").splitlines():
        if line == "# /// script":
            inside_script_metadata = True
            continue
        if inside_script_metadata and line == "# ///":
            break
        if inside_script_metadata:
            metadata_lines.append(line.removeprefix("#").lstrip())

    metadata = tomllib.loads("\n".join(metadata_lines))
    versions: dict[str, str] = {}
    for dependency in metadata.get("dependencies", []):
        distribution, separator, version = dependency.partition("==")
        if separator:
            versions[distribution.lower().replace("_", "-")] = version
    return versions


def _missing_runtime_dependencies() -> list[str]:
    declared_versions = _declared_runtime_versions()
    invalid: list[str] = []
    for module_name, distribution_name in RUNTIME_DEPENDENCIES:
        if importlib.util.find_spec(module_name) is None:
            invalid.append(module_name)
            continue
        expected_version = declared_versions.get(distribution_name)
        try:
            actual_version = importlib_metadata.version(distribution_name)
        except importlib_metadata.PackageNotFoundError:
            invalid.append(f"{module_name} ({distribution_name} distribution missing)")
            continue
        if expected_version is None:
            invalid.append(f"{module_name} ({distribution_name} is not pinned)")
        elif actual_version != expected_version:
            invalid.append(
                f"{module_name} ({distribution_name} {actual_version} != {expected_version})"
            )
    return invalid


def _ensure_managed_runtime(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[bool, str | None]:
    missing = _missing_runtime_dependencies()
    if not missing:
        return True, None

    current_environment = dict(os.environ if environ is None else environ)
    missing_list = ", ".join(missing)
    if current_environment.get(UV_REEXEC_ENV) == "1":
        return (
            False,
            "KS_RUNTIME_DEPENDENCY_UNAVAILABLE: uv could not hydrate the declared "
            f"runtime dependencies: {missing_list}",
        )

    uv_path = shutil.which("uv")
    if uv_path is None:
        return (
            False,
            "KS_RUNTIME_DEPENDENCY_UNAVAILABLE: missing runtime dependencies "
            f"({missing_list}); install uv and retry this command",
        )

    current_argv = list(sys.argv if argv is None else argv)
    current_environment[UV_REEXEC_ENV] = "1"
    os.execve(
        uv_path,
        [uv_path, "run", str(Path(__file__).resolve()), *current_argv[1:]],
        current_environment,
    )
    raise RuntimeError("uv runtime re-exec returned unexpectedly")


def _load_main():
    module_path = Path(__file__).resolve().parent / "keep-summarizing" / "dispatcher.py"
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("keep_summarizing_dispatcher", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load keep-summarizing CLI: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def main() -> int:
    ready, error = _ensure_managed_runtime()
    if not ready:
        print(error, file=sys.stderr)
        return 2
    return int(_load_main()())


if __name__ == "__main__":
    raise SystemExit(main())
