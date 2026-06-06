from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_HEADINGS = [
    "## Status History",
    "## Issue Status Summary",
]

REQUIRED_FRONTMATTER_KEYS = (
    "report_id",
    "checker_skill",
    "report_status",
    "checked_at",
    "updated_at",
    "actor",
)

DEFAULT_REPORT_STATUSES = {"draft", "active", "partially_fixed", "closed", "superseded"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value or "work-bundle-integrity-check"


def issue_sidecar_path(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.name}.issues.json")


def status_sidecar_path(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.stem}.status.json")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_issue_sidecar(report_path: Path) -> dict:
    path = issue_sidecar_path(report_path)
    if not path.exists():
        return {"issues": [], "created_at": now_iso(), "updated_at": now_iso()}
    return json.loads(read_text(path))


def save_issue_sidecar(report_path: Path, data: dict) -> None:
    data["updated_at"] = now_iso()
    write_text(issue_sidecar_path(report_path), json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def next_issue_id(issues: list[dict]) -> str:
    max_num = 0
    for item in issues:
        issue_id = str(item.get("issue_id", ""))
        if issue_id.startswith("WBI-"):
            try:
                max_num = max(max_num, int(issue_id.split("-", 1)[1]))
            except ValueError:
                continue
    return f"WBI-{max_num + 1:03d}"


def fill_template(template_text: str, *, title: str, report_id: str, checked_at: str, actor: str) -> str:
    text = template_text.replace("<check-title>", title)
    replacements = {
        "<YYYYMMDD-HHmm>": report_id.removeprefix("wbi-"),
        "<timestamp>": checked_at,
        "<n>": "0",
        "<path>": "unknown",
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    text = text.replace("actor: agent | user | tool", f"actor: {actor}")
    text = text.replace(
        "Summary:\n\n```text\n<Concise summary of the integrity state, highest-risk problems, and recommended repair direction.>\n```",
        "Summary:\n\n```text\nReport scaffold created. Findings and recommendations remain agent-authored.\n```",
    )
    return text


def has_frontmatter(report_text: str) -> bool:
    return report_text.lstrip().startswith("---\n")


def ensure_frontmatter(report_text: str) -> list[str]:
    failures: list[str] = []
    if not has_frontmatter(report_text):
        return ["missing_frontmatter"]
    match = re.match(r"^---\n(.*?)\n---", report_text.lstrip(), re.DOTALL)
    if not match:
        failures.append("invalid_frontmatter_delimiters")
        return failures
    block = match.group(1)
    for key in REQUIRED_FRONTMATTER_KEYS:
        if not re.search(rf"^{re.escape(key)}:\s*\S", block, re.MULTILINE):
            failures.append(f"missing_frontmatter_key:{key}")
    return failures


def ensure_required_headings(report_text: str) -> list[str]:
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in report_text]
    return missing


def ensure_report_structure(report_text: str) -> list[str]:
    return ensure_frontmatter(report_text) + ensure_required_headings(report_text)


def parse_report_status(report_text: str) -> str | None:
    match = re.search(r"^report_status:\s*([a-z_]+)", report_text, re.MULTILINE)
    return match.group(1) if match else None


def insert_under_section(report_text: str, section: str, block: str) -> str:
    marker = f"## {section}\n"
    if marker not in report_text:
        return report_text.rstrip() + f"\n\n{marker}\n{block}\n"
    pivot = report_text.index(marker) + len(marker)
    tail = report_text[pivot:]
    next_header = tail.find("\n## ")
    if next_header == -1:
        insert_at = len(report_text)
    else:
        insert_at = pivot + next_header
    prefix = report_text[:insert_at].rstrip()
    suffix = report_text[insert_at:].lstrip("\n")
    merged = f"{prefix}\n\n{block}\n"
    if suffix:
        merged += f"\n{suffix}"
    return merged

