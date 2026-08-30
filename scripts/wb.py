#!/usr/bin/env python3
"""Compatibility entrypoint for work-bundle helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))
from invocation_observation import invoke_observed


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
    dispatcher = _load_dispatcher()
    return invoke_observed(
        "wb",
        sys.argv[1:],
        dispatcher.RECOGNIZED_COMMANDS,
        lambda: int(dispatcher.main()),
    )


if __name__ == "__main__":
    raise SystemExit(main())
