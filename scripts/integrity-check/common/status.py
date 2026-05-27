from __future__ import annotations

ISSUE_STATUSES = {"open", "fixed", "dismissed", "converted", "superseded"}
REPORT_STATUSES = {"draft", "active", "partially_fixed", "closed", "superseded"}
SEVERITIES = {"critical", "high", "medium", "low"}
ISSUE_TYPES = {
    "orphan",
    "broken_reference",
    "weak_rule",
    "incomplete_skill",
    "missing_script",
    "registry_error",
    "project_registry_error",
    "installed_source_drift",
    "compression_loading",
    "authority_conflict",
    "other",
}


def summarize_issues(issues: list[dict], report_status: str | None) -> dict:
    counts = {name: 0 for name in ISSUE_STATUSES}
    critical_open = 0
    high_open = 0
    for issue in issues:
        status = str(issue.get("issue_status", "")).strip().lower()
        severity = str(issue.get("severity", "")).strip().lower()
        if status in counts:
            counts[status] += 1
        if status == "open" and severity == "critical":
            critical_open += 1
        if status == "open" and severity == "high":
            high_open += 1
    closable = counts["open"] == 0
    blocking = critical_open + high_open
    return {
        "report_status": report_status or "unknown",
        "open_count": counts["open"],
        "fixed_count": counts["fixed"],
        "dismissed_count": counts["dismissed"],
        "converted_count": counts["converted"],
        "superseded_count": counts["superseded"],
        "critical_open_count": critical_open,
        "high_open_count": high_open,
        "blocking_count": blocking,
        "closable": closable and (report_status != "closed" or counts["open"] == 0),
        "boundary_risks": [
            {
                "issue_id": issue.get("issue_id"),
                "severity": issue.get("severity"),
                "issue_status": issue.get("issue_status"),
                "reason": "open high-severity issue requires human decision",
            }
            for issue in issues
            if issue.get("issue_status") == "open"
            and str(issue.get("severity", "")).lower() in {"critical", "high"}
        ],
        "decision_authority": "human",
    }

