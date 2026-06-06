#!/usr/bin/env python3
"""Compatibility entrypoint for orchestration helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_main():
    module_path = Path(__file__).resolve().parent / "orchestration" / "dispatcher.py"
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("orchestration_dispatcher", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load orchestration CLI: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def main() -> int:
    return int(_load_main()())


if __name__ == "__main__":
    raise SystemExit(main())
