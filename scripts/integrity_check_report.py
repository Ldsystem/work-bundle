from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

COMMON_PATH = Path(__file__).with_name("integrity-check") / "common"
if str(COMMON_PATH) not in sys.path:
    sys.path.insert(0, str(COMMON_PATH))

from report_io import (  # type: ignore
    DEFAULT_REPORT_STATUSES,
    ensure_report_structure,
    fill_template,
    insert_under_section,
    issue_sidecar_path,
    load_issue_sidecar,
    next_issue_id,
    now_iso,
    parse_report_status,
    read_text,
    save_issue_sidecar,
    slugify,
    status_sidecar_path,
    write_text,
)
from status import ISSUE_STATUSES, ISSUE_TYPES, REPORT_STATUSES, SEVERITIES, summarize_issues  # type: ignore

DEFAULT_TEMPLATE = Path("references/integrity-check/integrity-check-template.md")
DEFAULT_OUTPUT_ROOT = Path(".work-bundle/orchestration/reviews/integrity-checks")
SECTION_MAP = {
    "orphan": "Orphan File Findings",
    "broken_reference": "Broken References",
    "weak_rule": "Rule Branch Consistency",
    "incomplete_skill": "Skill Branch Consistency",
    "missing_script": "Script Reference Consistency",
    "registry_error": "Registry Consistency",
    "project_registry_error": "Project Registry Consistency",
    "installed_source_drift": "Installed-vs-Source Drift",
    "compression_loading": "Work-Bundle Compression and Conditional Loading",
    "authority_conflict": "Authority / Precedence Conflicts",
    "other": "Critical Issues",
}


def _json_out(payload: dict, *, stream=sys.stdout) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _error(message: str, *, code: int = 2) -> int:
    _json_out(
        {
            "status": "boundary_violation" if code == 2 else "failed",
            "message": message,
            "final_decision_owner": "human",
        },
        stream=sys.stderr,
    )
    return code


def _report_id() -> str:
    return "wbi-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")


def _assert_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")


def _create_report(args: argparse.Namespace) -> int:
    template = Path(args.template)
    _assert_exists(template, "template")
    report_id = _report_id()
    checked_at = now_iso()
    title = args.title.strip() or "work-bundle-integrity-check"
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    output_name = f"{report_id.removeprefix('wbi-')}-{slugify(title)}.md"
    report_path = output_root / output_name
    if report_path.exists():
        return _error(f"refusing to overwrite existing report: {report_path}", code=1)

    rendered = fill_template(
        read_text(template),
        title=title,
        report_id=report_id,
        checked_at=checked_at,
        actor=args.actor,
    )
    write_text(report_path, rendered)
    save_issue_sidecar(
        report_path,
        {
            "report_id": report_id,
            "report_path": str(report_path),
            "template_path": str(template),
            "source_instruction": "references/integrity-check/work-bundle-integrity-check.md",
            "report_status": "draft",
            "final_decision_owner": "human",
            "issues": [],
            "created_at": checked_at,
            "updated_at": checked_at,
        },
    )
    _json_out(
        {
            "status": "passed",
            "command": "new",
            "report_path": str(report_path),
            "issue_sidecar": str(issue_sidecar_path(report_path)),
            "final_decision_owner": "human",
        }
    )
    return 0


def _add_issue(args: argparse.Namespace) -> int:
    report = Path(args.report)
    _assert_exists(report, "report")
    if args.severity not in SEVERITIES:
        return _error(f"invalid severity: {args.severity}", code=1)
    if args.issue_type not in ISSUE_TYPES:
        return _error(f"invalid issue type: {args.issue_type}", code=1)
    if not args.agent_authored:
        return _error("add-issue requires explicit agent-authored findings")

    data = load_issue_sidecar(report)
    issues = list(data.get("issues", []))
    issue_id = args.issue_id or next_issue_id(issues)
    if any(item.get("issue_id") == issue_id for item in issues):
        return _error(f"duplicate issue id: {issue_id}", code=1)

    issue = {
        "issue_id": issue_id,
        "issue_status": "open",
        "severity": args.severity,
        "type": args.issue_type,
        "file": args.file or None,
        "root": args.root or None,
        "summary": args.summary.strip(),
        "recommended_fix": args.recommended_fix.strip(),
        "evidence": args.evidence,
        "source_of_truth_updates": args.source_update,
        "requires_human_decision": bool(args.requires_human_decision),
        "status_history": [
            {
                "at": now_iso(),
                "actor": args.actor,
                "from": None,
                "to": "open",
                "reason": "issue recorded",
                "evidence": args.evidence[0],
            }
        ],
    }
    issues.append(issue)
    data["issues"] = issues
    data["report_status"] = "active" if issues else "draft"
    save_issue_sidecar(report, data)

    section = SECTION_MAP.get(args.issue_type, "Critical Issues")
    issue_block = (
        f"### {issue_id}: {issue['summary']}\n\n"
        "```yaml\n"
        f"issue_id: {issue_id}\n"
        "issue_status: open\n"
        f"severity: {issue['severity']}\n"
        f"type: {issue['type']}\n"
        f"file: {issue['file'] or 'null'}\n"
        f"root: {issue['root'] or 'null'}\n"
        f"summary: {issue['summary']}\n"
        f"recommended_fix: {issue['recommended_fix']}\n"
        f"requires_human_decision: {str(issue['requires_human_decision']).lower()}\n"
        "evidence:\n"
        + "".join(f"  - {item}\n" for item in issue["evidence"])
        + "status_history:\n"
        + f"  - at: {issue['status_history'][0]['at']}\n"
        + f"    actor: {args.actor}\n"
        + "    from: null\n"
        + "    to: open\n"
        + "    reason: issue recorded\n"
        + f"    evidence: {issue['evidence'][0]}\n"
        + "```\n"
    )
    updated_report = insert_under_section(read_text(report), section, issue_block)
    write_text(report, updated_report)
    _json_out(
        {
            "status": "passed",
            "command": "add-issue",
            "issue_id": issue_id,
            "report_path": str(report),
            "final_decision_owner": "human",
        }
    )
    return 0


def _update_status(args: argparse.Namespace) -> int:
    report = Path(args.report)
    _assert_exists(report, "report")
    if args.status not in ISSUE_STATUSES - {"open"}:
        return _error(f"invalid target status: {args.status}", code=1)
    if not args.reason.strip():
        return _error("status change requires --reason", code=1)
    if args.status == "fixed" and not args.evidence:
        return _error("fixed status requires --evidence", code=1)

    data = load_issue_sidecar(report)
    issues = list(data.get("issues", []))
    target = next((item for item in issues if item.get("issue_id") == args.issue_id), None)
    if target is None:
        return _error(f"unknown issue id: {args.issue_id}", code=1)
    old_status = target.get("issue_status")
    target["issue_status"] = args.status
    target.setdefault("status_history", []).append(
        {
            "at": now_iso(),
            "actor": args.actor,
            "from": old_status,
            "to": args.status,
            "reason": args.reason.strip(),
            "evidence": "; ".join(args.evidence) if args.evidence else "not-provided",
        }
    )
    if args.source_update:
        target["source_of_truth_updates"] = args.source_update
    save_issue_sidecar(report, data)

    trail = (
        f"| {now_iso()} | {args.actor} | {old_status} | {args.status} | "
        f"{args.reason.strip()} | {'; '.join(args.evidence) if args.evidence else 'n/a'} |\n"
    )
    report_text = read_text(report)
    report_text = insert_under_section(report_text, "Status History", trail.rstrip())
    write_text(report, report_text)
    _json_out(
        {
            "status": "passed",
            "command": "update-status",
            "issue_id": args.issue_id,
            "from": old_status,
            "to": args.status,
            "final_decision_owner": "human",
        }
    )
    return 0


def _summarize_status(args: argparse.Namespace) -> int:
    report = Path(args.report)
    _assert_exists(report, "report")
    data = load_issue_sidecar(report)
    report_status = parse_report_status(read_text(report)) or data.get("report_status")
    summary = summarize_issues(list(data.get("issues", [])), report_status)
    summary["report_path"] = str(report)
    summary["last_updated_at"] = now_iso()
    summary["final_decision_owner"] = "human"
    output = Path(args.output) if args.output else status_sidecar_path(report)
    write_text(output, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _json_out({"status": "passed", "command": "summarize-status", "output": str(output), **summary})
    return 0


def _archive_report(args: argparse.Namespace) -> int:
    report = Path(args.report)
    _assert_exists(report, "report")
    sidecar = issue_sidecar_path(report)
    summary_path = status_sidecar_path(report)
    issues = load_issue_sidecar(report).get("issues", [])
    has_open = any(item.get("issue_status") == "open" for item in issues)
    if has_open and not args.allow_open:
        return _error("refusing to archive report with open issues without --allow-open", code=1)

    archive_root = Path(args.archive_root)
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_report = archive_root / report.name
    if args.move:
        shutil.move(str(report), str(archive_report))
    else:
        shutil.copy2(report, archive_report)

    copied_sidecars: list[str] = []
    for path in (sidecar, summary_path):
        if path.exists():
            target = archive_root / path.name
            if args.move:
                shutil.move(str(path), str(target))
            else:
                shutil.copy2(path, target)
            copied_sidecars.append(str(target))
    _json_out(
        {
            "status": "passed",
            "command": "archive-report",
            "archived_report": str(archive_report),
            "moved": bool(args.move),
            "sidecars": copied_sidecars,
            "final_decision_owner": "human",
        }
    )
    return 0


def _validate_report(args: argparse.Namespace) -> int:
    if args.check_finding_correctness:
        return _error(
            "validate-report only checks structure; finding correctness remains agent/human authority"
        )
    report = Path(args.report)
    _assert_exists(report, "report")
    data = load_issue_sidecar(report)
    issues = list(data.get("issues", []))
    report_text = read_text(report)

    failures: list[str] = []
    warnings: list[str] = []
    structure_failures = ensure_report_structure(report_text)
    for item in structure_failures:
        if item.startswith("##"):
            failures.append(f"missing_heading:{item}")
        else:
            failures.append(f"report_structure:{item}")

    report_status = parse_report_status(report_text)
    if report_status and report_status not in DEFAULT_REPORT_STATUSES:
        failures.append(f"invalid_report_status:{report_status}")
    if report_status == "closed" and any(item.get("issue_status") == "open" for item in issues):
        failures.append("closed_report_has_open_issues")

    seen: set[str] = set()
    for issue in issues:
        issue_id = str(issue.get("issue_id", "")).strip()
        if not issue_id:
            failures.append("missing_issue_id")
            continue
        if issue_id in seen:
            failures.append(f"duplicate_issue_id:{issue_id}")
        seen.add(issue_id)
        status = issue.get("issue_status")
        if status not in ISSUE_STATUSES:
            failures.append(f"invalid_issue_status:{issue_id}:{status}")
        if issue.get("severity") not in SEVERITIES:
            failures.append(f"invalid_severity:{issue_id}:{issue.get('severity')}")
        if issue.get("type") not in ISSUE_TYPES:
            failures.append(f"invalid_type:{issue_id}:{issue.get('type')}")
        if status == "fixed" and not issue.get("status_history"):
            warnings.append(f"fixed_issue_without_status_history:{issue_id}")

    summary = summarize_issues(issues, report_status)
    status = "passed" if not failures else "failed"
    _json_out(
        {
            "status": status,
            "command": "validate-report",
            "report_path": str(report),
            "failures": failures,
            "warnings": warnings,
            "summary": summary,
            "final_decision_owner": "human",
        }
    )
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="integrity_check_report.py",
        description="Deterministic helper CLI for integrity report lifecycle operations.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    new = sub.add_parser("new", help="Create report from local template.")
    new.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    new.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    new.add_argument("--title", default="work-bundle-integrity-check")
    new.add_argument("--actor", default="agent", choices=["agent", "user", "tool"])
    new.set_defaults(handler=_create_report)

    add = sub.add_parser("add-issue", help="Append agent-authored issue to report.")
    add.add_argument("--report", required=True)
    add.add_argument("--issue-id")
    add.add_argument("--severity", required=True, choices=sorted(SEVERITIES))
    add.add_argument("--type", dest="issue_type", required=True, choices=sorted(ISSUE_TYPES))
    add.add_argument("--file")
    add.add_argument("--root", choices=["user_bundle", "source_bundle", "project"])
    add.add_argument("--summary", required=True)
    add.add_argument("--recommended-fix", required=True)
    add.add_argument("--evidence", action="append", required=True)
    add.add_argument("--source-update", action="append", default=[])
    add.add_argument("--actor", default="agent", choices=["agent", "user", "tool"])
    add.add_argument("--requires-human-decision", action="store_true")
    add.add_argument("--agent-authored", action="store_true", default=True)
    add.set_defaults(handler=_add_issue)

    update = sub.add_parser("update-status", help="Update issue status with evidence.")
    update.add_argument("--report", required=True)
    update.add_argument("--issue-id", required=True)
    update.add_argument(
        "--status",
        required=True,
        choices=sorted(ISSUE_STATUSES - {"open"}),
    )
    update.add_argument("--reason", required=True)
    update.add_argument("--evidence", action="append", default=[])
    update.add_argument("--source-update", action="append", default=[])
    update.add_argument("--actor", default="agent", choices=["agent", "user", "tool"])
    update.set_defaults(handler=_update_status)

    summary = sub.add_parser("summarize-status", help="Generate machine-readable status sidecar.")
    summary.add_argument("--report", required=True)
    summary.add_argument("--output")
    summary.set_defaults(handler=_summarize_status)

    archive = sub.add_parser("archive-report", help="Archive report and sidecar files.")
    archive.add_argument("--report", required=True)
    archive.add_argument("--archive-root", required=True)
    archive.add_argument("--allow-open", action="store_true")
    archive.add_argument("--move", action="store_true")
    archive.set_defaults(handler=_archive_report)

    validate = sub.add_parser("validate-report", help="Validate report structure only.")
    validate.add_argument("--report", required=True)
    validate.add_argument("--check-finding-correctness", action="store_true")
    validate.set_defaults(handler=_validate_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(argv)
    return parsed.handler(parsed)


if __name__ == "__main__":
    raise SystemExit(main())

