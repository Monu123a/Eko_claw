"""The agent's tools — the side-effecting actions it can take.

Each function performs ONE concrete action and produces a durable, structured
artifact on disk. This is what makes the agent *act* instead of just chat:
every run leaves an auditable trail of logs, reminders, escalation notes, and
a final report.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict


def ensure_run_dir(output_dir: str, run_id: str) -> str:
    """Create outputs/<run_id>/ and its subfolders; return the run dir."""
    run_dir = os.path.join(output_dir, run_id)
    for sub in ("", "reminders", "escalations"):
        os.makedirs(os.path.join(run_dir, sub), exist_ok=True)
    return run_dir


def write_log(run_dir: str, entry: Dict[str, Any]) -> None:
    """Append one structured log line (JSONL) — the running activity trail."""
    entry = dict(entry)
    entry.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    with open(os.path.join(run_dir, "activity_log.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_reminder(run_dir: str, partner_id: str, text: str) -> str:
    """Persist a drafted reminder message; return its relative path."""
    rel = os.path.join("reminders", "%s.txt" % partner_id)
    with open(os.path.join(run_dir, rel), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return rel


def write_escalation(run_dir: str, note: Dict[str, Any]) -> str:
    """Persist a structured escalation note; return its relative path."""
    rel = os.path.join("escalations", "%s.json" % note["partner_id"])
    with open(os.path.join(run_dir, rel), "w", encoding="utf-8") as fh:
        json.dump(note, fh, indent=2, ensure_ascii=False)
    return rel


def write_report(run_dir: str, report: Dict[str, Any]) -> str:
    """Write the machine-readable run report."""
    path = os.path.join(run_dir, "run_report.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return path


def write_summary(run_dir: str, markdown: str) -> str:
    """Write the human-readable summary."""
    path = os.path.join(run_dir, "summary.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    return path


def write_html(run_dir: str, html: str) -> str:
    """Write the self-contained HTML report (opens in any browser, no server)."""
    path = os.path.join(run_dir, "report.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path
