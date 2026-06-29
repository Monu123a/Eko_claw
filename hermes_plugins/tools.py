"""Tool handlers for the Hermes plugin.

Thin wrappers around src/ modules. Each handler takes JSON input from
the LLM and returns a JSON string back into the conversation.
"""

import json
import os
import sys
from datetime import date, datetime

# make sure project root is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src import config, llm, tools as src_tools
from src.schemas import Partner, Classification


# shared state across tool calls within one run
_state = {
    "partners": {},      # id -> Partner
    "run_dir": None,
}


def _run_dir() -> str:
    """Return (and lazily create) the current run directory."""
    if _state["run_dir"] is None:
        run_id = "run-%s" % date.today().isoformat()
        _state["run_dir"] = src_tools.ensure_run_dir(config.DEFAULT_OUTPUT_DIR, run_id)
    return _state["run_dir"]


# --- ingest_partners ---
def handle_ingest_partners(data_path: str) -> str:
    """Load partner records from JSON. Returns JSON with partners + count."""
    with open(data_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    partners = [Partner(**row) for row in raw]
    _state["partners"] = {p.id: p for p in partners}

    src_tools.write_log(_run_dir(), {"stage": "INGEST", "partners_loaded": len(partners)})

    return json.dumps({
        "partners": raw,
        "count": len(partners),
    }, ensure_ascii=False)


# --- triage_partner ---
def handle_triage_partner(partner_id: str, reference_date: str) -> str:
    """Classify a single partner. Returns JSON classification."""
    partner = _state["partners"].get(partner_id)
    if not partner:
        return json.dumps({"error": "Partner %s not found. Run ingest_partners first." % partner_id})

    ref = datetime.strptime(reference_date, "%Y-%m-%d").date()
    days = partner.days_since_contact(ref)
    cls = llm.classify(partner, days)

    return json.dumps(cls.to_dict(), ensure_ascii=False)


# --- draft_reminder ---
def handle_draft_reminder(partner_id: str, partner_name: str, owner: str,
                          region: str, summary: str,
                          pending_actions: list = None) -> str:
    """Draft and save a reminder message. Returns JSON with message + path."""
    partner = _state["partners"].get(partner_id)
    if not partner:
        return json.dumps({"error": "Partner %s not found." % partner_id})

    cls = Classification(
        status="PENDING", severity="medium", sentiment="neutral",
        confidence=0.7, summary=summary,
        pending_actions=pending_actions or [], source="hermes",
    )
    text, source = llm.draft_reminder(partner, cls)
    rel_path = src_tools.write_reminder(_run_dir(), partner_id, text)

    src_tools.write_log(_run_dir(), {
        "stage": "ACT", "partner": partner_id,
        "action": "drafted_reminder", "source": source,
    })

    return json.dumps({
        "message": text,
        "source": source,
        "file_path": rel_path,
    }, ensure_ascii=False)


# --- create_escalation ---
def handle_create_escalation(**kwargs) -> str:
    """Create an escalation note and ticket. Returns JSON with paths + ticket ID."""
    partner_id = kwargs.get("partner_id", "")
    partner = _state["partners"].get(partner_id)

    # Determine recommended owner.
    issue = (kwargs.get("open_issue") or "").lower()
    if any(w in issue for w in ("settlement", "paisa", "payout", "money")):
        rec_owner = "Finance / Settlements team"
    elif any(w in issue for w in ("device", "atm", "fingerprint", "error", "hardware")):
        rec_owner = "Field Support / Hardware team"
    elif kwargs.get("monthly_volume_inr", 0) >= config.HIGH_VALUE_VOLUME_INR:
        rec_owner = "Key Account Manager"
    else:
        rec_owner = "Partner Success lead"

    note = {
        "partner_id": partner_id,
        "partner_name": kwargs.get("partner_name", ""),
        "owner": kwargs.get("owner", ""),
        "region": kwargs.get("region", ""),
        "segment": kwargs.get("segment", ""),
        "monthly_volume_inr": kwargs.get("monthly_volume_inr", 0),
        "status": kwargs.get("status", ""),
        "severity": kwargs.get("severity", "medium"),
        "sentiment": kwargs.get("sentiment", "neutral"),
        "confidence": kwargs.get("confidence", 0.0),
        "days_since_last_contact": kwargs.get("days_since_last_contact", 0),
        "open_issue": kwargs.get("open_issue"),
        "summary": kwargs.get("summary", ""),
        "pending_actions": kwargs.get("pending_actions", []),
        "escalation_reasons": kwargs.get("escalation_reasons", []),
        "recommended_owner": rec_owner,
        "created_at": date.today().isoformat(),
    }

    rel_path = src_tools.write_escalation(_run_dir(), note)

    # create ticket if module is available
    ticket_id = None
    try:
        from src.tickets import TicketStore
        store = TicketStore()
        if not store.has_open_ticket(partner_id):
            ticket_id = store.create_ticket(note)
        store.close()
    except Exception:
        pass  # tickets are optional

    src_tools.write_log(_run_dir(), {
        "stage": "ACT", "partner": partner_id,
        "action": "created_escalation", "severity": note["severity"],
    })

    return json.dumps({
        "file_path": rel_path,
        "ticket_id": ticket_id,
        "recommended_owner": rec_owner,
    }, ensure_ascii=False)


# --- generate_report ---
def handle_generate_report(run_id: str, records: list) -> str:
    """Generate final report artifacts. Returns JSON with paths + totals."""
    def count(action: str) -> int:
        return sum(1 for r in records
                   if r.get("decision", {}).get("action") == action)

    report = {
        "run_id": run_id,
        "generated_at": "%sT00:00:00" % date.today().isoformat(),
        "reference_date": date.today().isoformat(),
        "brain": llm.brain_label(),
        "totals": {
            "partners_reviewed": len(records),
            "reminders_drafted": count(config.ACTION_REMIND),
            "escalations_created": count(config.ACTION_ESCALATE),
            "no_action": count(config.ACTION_NONE),
        },
        "partners": records,
    }

    report_path = src_tools.write_report(_run_dir(), report)
    summary_md = _build_summary(report)
    summary_path = src_tools.write_summary(_run_dir(), summary_md)

    return json.dumps({
        "report_path": report_path,
        "summary_path": summary_path,
        "totals": report["totals"],
    }, ensure_ascii=False)


def _build_summary(report: dict) -> str:
    t = report["totals"]
    lines = [
        "# Partner Follow-up — Daily Brief",
        "",
        "**Run:** %s  |  **Brain:** %s" % (report["run_id"], report["brain"]),
        "",
        "- Partners reviewed: **%d**" % t["partners_reviewed"],
        "- Reminders drafted: **%d**" % t["reminders_drafted"],
        "- Escalations created: **%d**" % t["escalations_created"],
        "- On track / no action: **%d**" % t["no_action"],
        "",
    ]
    return "\n".join(lines)


# --- handler registry ---
HANDLERS = {
    "ingest_partners": handle_ingest_partners,
    "triage_partner": handle_triage_partner,
    "draft_reminder": handle_draft_reminder,
    "create_escalation": handle_create_escalation,
    "generate_report": handle_generate_report,
}
