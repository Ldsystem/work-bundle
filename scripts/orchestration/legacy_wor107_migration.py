#!/usr/bin/env python3
"""Narrow compatibility validator for the historical WOR-107 stop boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import yaml


ISSUE_ID = "WOR-107"
FAILURE_CODE = "WB_MIGRATION_STOP_BOUNDARY_INVALID"
DEPRECATION_DIAGNOSTIC = (
    "deprecated: assert-migration-stop is a legacy migration compatibility alias"
)


class LegacyMigrationBoundaryError(ValueError):
    pass


def _read_document(path: Path) -> Mapping[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise LegacyMigrationBoundaryError("migration handoff must be a mapping")
    return value


def cmd_assert_migration_stop(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="legacy_wor107_migration.py")
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--required-excluded", nargs="+", required=True)
    parsed = parser.parse_args(argv)
    try:
        instance = _read_document(parsed.instance)
        if instance.get("issue") != ISSUE_ID:
            raise LegacyMigrationBoundaryError(
                f"migration handoff issue must be {ISSUE_ID}"
            )
        excluded = instance.get("excluded_work")
        if not isinstance(excluded, list) or any(
            not isinstance(item, str) for item in excluded
        ):
            raise LegacyMigrationBoundaryError(
                "excluded_work must be a list of strings"
            )
        missing = [item for item in parsed.required_excluded if item not in excluded]
        if missing:
            raise LegacyMigrationBoundaryError(
                f"migration stop boundary missing exclusions: {', '.join(missing)}"
            )
    except (OSError, yaml.YAMLError, LegacyMigrationBoundaryError) as error:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "failure_code": FAILURE_CODE,
                    "detail": str(error),
                },
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "passed",
                "issue": ISSUE_ID,
                "excluded_work": parsed.required_excluded,
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return cmd_assert_migration_stop(argv or [])


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
