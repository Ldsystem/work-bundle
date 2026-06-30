#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_session_start():
    module_path = Path(__file__).resolve().parents[1] / 'scripts' / 'work-bundle' / 'project.py'
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location('work_bundle_project', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load work-bundle project helper: {module_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.cmd_session_start


def _read_hook_input() -> tuple[Path, list[str]]:
    raw = sys.stdin.read()
    if not raw.strip():
        return Path.cwd().resolve(), []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return Path.cwd().resolve(), ['malformed hook JSON stdin; using process cwd']
    if isinstance(payload, dict) and isinstance(payload.get('cwd'), str) and payload['cwd'].strip():
        return Path(payload['cwd']).expanduser().resolve(), []
    return Path.cwd().resolve(), []


def main() -> int:
    cwd, warnings = _read_hook_input()
    args = ['--project-root', str(cwd), '--json']
    for warning in warnings:
        args.extend(['--input-warning', warning])
    return int(_load_session_start()(args))


if __name__ == '__main__':
    raise SystemExit(main())
