#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "pyyaml==6.0.3",
#   "jsonschema==4.25.1",
# ]
# ///
"""Compatibility entrypoint for work-bundle helpers."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Mapping, Sequence

RUNTIME_DEPENDENCIES = (("yaml", "pyyaml"), ("jsonschema", "jsonschema"))
UV_REEXEC_ENV = "WORK_BUNDLE_PUBLIC_UV_REEXEC"

SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))
from invocation_observation import invoke_observed


def _missing_runtime_dependencies() -> list[str]:
    return [distribution for module, distribution in RUNTIME_DEPENDENCIES if importlib.util.find_spec(module) is None]


def _ensure_managed_runtime(
    *, argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None
) -> tuple[bool, str | None]:
    missing = _missing_runtime_dependencies()
    if not missing:
        return True, None
    environment = dict(os.environ if environ is None else environ)
    if environment.get(UV_REEXEC_ENV) == "1":
        return False, "WB_RUNTIME_DEPENDENCY_UNAVAILABLE: uv could not hydrate " + ", ".join(missing)
    uv = shutil.which("uv")
    if uv is None:
        return False, "WB_RUNTIME_DEPENDENCY_UNAVAILABLE: install uv to provide " + ", ".join(missing)
    arguments = list(sys.argv if argv is None else argv)
    environment[UV_REEXEC_ENV] = "1"
    os.execve(uv, [uv, "run", str(Path(__file__).resolve()), *arguments[1:]], environment)
    return False, "WB_RUNTIME_DEPENDENCY_UNAVAILABLE: uv re-execution returned unexpectedly"


def _load_dispatcher():
    module_path = SCRIPT_ROOT / "work-bundle" / "dispatcher.py"
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("work_bundle_dispatcher", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load work-bundle CLI: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ready, failure = _ensure_managed_runtime()
    if not ready:
        print(failure, file=sys.stderr)
        return 1
    dispatcher = _load_dispatcher()
    return invoke_observed(
        "wb",
        sys.argv[1:],
        dispatcher.RECOGNIZED_COMMANDS,
        lambda: int(dispatcher.main()),
    )


if __name__ == "__main__":
    raise SystemExit(main())
