"""The Partner Follow-up Claw — an autonomous agent that owns the follow-up workflow.

It runs a bounded, 5-stage pipeline end-to-end:

    INGEST  -> TRIAGE -> DECIDE -> ACT -> REPORT

  1. INGEST   load partner records from the data store
  2. TRIAGE   understand each partner (LLM, with rule-based fallback)
  3. DECIDE   apply explicit escalation policy -> one action per partner
  4. ACT      use tools to draft reminders, create escalation notes, log activity
  5. REPORT   emit a structured JSON report + a human-readable summary

The split between TRIAGE (understanding) and DECIDE (policy) is deliberate:
the model interprets the situation, but the *decision to escalate* is governed
by transparent, auditable rules — including escalating whenever the model is
not confident enough to act safely.
"""

import html as html_lib
import json
import os
from datetime import date
from typing import Any, Dict, List, Optional

from . import config, llm, tools
from .schemas import Partner, Classification, Decision
from .memory import PartnerMemory
from .tickets import TicketStore
from .send_queue import SendQueue


class FollowUpClaw:
    def __init__(self, reference_date: Optional[date] = None,
                 output_dir: str = config.DEFAULT_OUTPUT_DIR,
                 verbose: bool = True):
        self.today = reference_date or date.today()
        self.output_dir = output_dir
        self.verbose = verbose
        self.memory = PartnerMemory()
        self.tickets = TicketStore()
        self.send_queue = SendQueue()

    # --- main entry point ---
    def run(self, data_path: str) -> Dict[str, Any]:
        run_id = "run-%s" % self.today.isoformat()
        run_dir = tools.ensure_run_dir(self.output_dir, run_id)

        self._say("Partner Follow-up Claw  |  reference date: %s  |  brain: %s"
                  % (self.today.isoformat(), llm.brain_label()))
        self._say("-" * 64)

        # 1. INGEST
        partners = self._ingest(data_path)
        tools.write_log(run_dir, {"stage": "INGEST", "partners_loaded": len(partners)})

        records: List[Dict[str, Any]] = []
        for partner in partners:
            record = self._process_partner(partner, run_dir)
            records.append(record)

        # 5. REPORT
        report = self._build_report(run_id, records)
        report_path = tools.write_report(run_dir, report)
        summary_md = self._build_summary(report)
        summary_path = tools.write_summary(run_dir, summary_md)
        html_path = tools.write_html(run_dir, self._build_html(report, run_dir))
        tools.write_log(run_dir, {"stage": "REPORT", "report": report_path})

        # --- dispatch the queue ---
        dispatched = self.send_queue.process_queue()

        self._say("-" * 64)
        self._print_console_summary(report)
        self._say("\nArtifacts written to: %s/" % run_dir)
        self._say("  - report.html       (open in any browser — no server needed)")
        self._say("  - run_report.json   (structured, machine-readable)")
        self._say("  - summary.md        (human-readable brief)")
        self._say("  - activity_log.jsonl(every action the agent took)")
        self._say("  - reminders/        (drafted messages)")
        self._say("  - escalations/      (structured escalation notes)")
        
        if dispatched:
            self._say("\nWhatsApp Dispatch:")
            self._say("  ✅ Processed %d pending messages from the queue." % len(dispatched))

        report["_paths"] = {"report": report_path, "summary": summary_path,
                            "html": html_path, "run_dir": run_dir}
        return report

    # --- stage 1: ingest ---
    def _ingest(self, data_path: str) -> List[Partner]:
        with open(data_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return [Partner(**row) for row in raw]

    # --- per-partner loop: triage -> decide -> act ---
    def _process_partner(self, partner: Partner, run_dir: str) -> Dict[str, Any]:
        days = partner.days_since_contact(self.today)

        # 2. TRIAGE
        cls = llm.classify(partner, days)
        # 3. DECIDE
        decision = self._decide(partner, cls, days)
        # 4. ACT
        artifacts = self._act(partner, cls, decision, days, run_dir)

        self._say("  %-9s %-30s -> %-13s [%s, conf %.2f]" % (
            partner.id, partner.name[:30], decision.action,
            cls.status, cls.confidence))

        return {
            "id": partner.id,
            "name": partner.name,
            "owner": partner.owner,
            "region": partner.region,
            "segment": partner.segment,
            "monthly_volume_inr": partner.monthly_volume_inr,
            "days_since_last_contact": days,
            "classification": cls.to_dict(),
            "decision": decision.to_dict(),
            "artifacts": artifacts,
        }

    # --- stage 3: decide (escalation policy) ---
    def _decide(self, partner: Partner, cls: Classification, days: int) -> Decision:
        reasons: List[str] = []
        escalate = False

        if days >= config.ESCALATE_AFTER_DAYS:
            escalate = True
            reasons.append("No contact for %d days (>= %d)."
                           % (days, config.ESCALATE_AFTER_DAYS))
        if cls.status == config.STATUS_HIGH_RISK or cls.severity == "high":
            escalate = True
            reasons.append("High-risk / high-severity situation flagged in triage.")
        if cls.sentiment == "negative":
            escalate = True
            reasons.append("Negative partner sentiment detected.")
        if (partner.monthly_volume_inr >= config.HIGH_VALUE_VOLUME_INR
                and cls.status in (config.STATUS_DELAYED, config.STATUS_HIGH_RISK)):
            escalate = True
            reasons.append("Key partner (volume INR %s) is stalled."
                           % partner.monthly_volume_inr)
        if (partner.followups_sent >= config.MAX_FOLLOWUPS_BEFORE_ESCALATION
                and partner.awaiting_response):
            escalate = True
            reasons.append("%d follow-ups with no response."
                           % partner.followups_sent)
        # low confidence -> don't risk it, let a human look
        if cls.confidence < config.MIN_CONFIDENCE:
            escalate = True
            reasons.append("Low confidence (%.2f < %.2f) — routing to a human."
                           % (cls.confidence, config.MIN_CONFIDENCE))

        # don't re-escalate if we already did this recently
        if escalate and self.memory.was_escalated_recently(partner.id, within_days=3):
            reasons.append("(Suppressed — already escalated within 3 days.)")
            escalate = False

        if escalate:
            return Decision(action=config.ACTION_ESCALATE, reasons=reasons)

        # not escalating -> check if a gentle reminder makes sense
        if (partner.open_issue or partner.awaiting_response
                or days >= config.REMIND_AFTER_DAYS
                or cls.status in (config.STATUS_PENDING, config.STATUS_DELAYED)):
            return Decision(
                action=config.ACTION_REMIND,
                reasons=["Open thread or due for a check-in; gentle reminder is safe."],
            )

        return Decision(action=config.ACTION_NONE,
                        reasons=["On track, nothing pending."])

    # --- stage 4: act (write artifacts) ---
    def _act(self, partner: Partner, cls: Classification, decision: Decision,
             days: int, run_dir: str) -> Dict[str, Any]:
        artifacts: Dict[str, Any] = {"reminder": None, "escalation": None}

        if decision.action == config.ACTION_REMIND:
            text, source = llm.draft_reminder(partner, cls)
            artifacts["reminder"] = tools.write_reminder(run_dir, partner.id, text)
            # queue for WhatsApp delivery
            self.send_queue.enqueue(partner.id, text, partner_name=partner.name)
            tools.write_log(run_dir, {
                "stage": "ACT", "partner": partner.id, "action": "drafted_reminder",
                "source": source, "path": artifacts["reminder"],
            })
            self.memory.record_action(
                partner.id, self.today, config.ACTION_REMIND,
                status=cls.status, severity=cls.severity, confidence=cls.confidence,
            )

        elif decision.action == config.ACTION_ESCALATE:
            note = {
                "partner_id": partner.id,
                "partner_name": partner.name,
                "owner": partner.owner,
                "region": partner.region,
                "segment": partner.segment,
                "monthly_volume_inr": partner.monthly_volume_inr,
                "status": cls.status,
                "severity": cls.severity,
                "sentiment": cls.sentiment,
                "confidence": cls.confidence,
                "days_since_last_contact": days,
                "open_issue": partner.open_issue,
                "summary": cls.summary,
                "pending_actions": cls.pending_actions,
                "escalation_reasons": decision.reasons,
                "recommended_owner": self._suggest_owner(partner, cls),
                "created_at": self.today.isoformat(),
            }
            artifacts["escalation"] = tools.write_escalation(run_dir, note)
            # create a ticket if there isn't one already
            if not self.tickets.has_open_ticket(partner.id):
                ticket_id = self.tickets.create_ticket(note)
                artifacts["ticket_id"] = ticket_id
            tools.write_log(run_dir, {
                "stage": "ACT", "partner": partner.id, "action": "created_escalation",
                "severity": cls.severity, "path": artifacts["escalation"],
            })
            self.memory.record_action(
                partner.id, self.today, config.ACTION_ESCALATE,
                status=cls.status, severity=cls.severity, confidence=cls.confidence,
            )
        else:
            tools.write_log(run_dir, {
                "stage": "ACT", "partner": partner.id, "action": "no_action",
            })
            self.memory.record_action(
                partner.id, self.today, config.ACTION_NONE,
                status=cls.status, severity=cls.severity, confidence=cls.confidence,
            )
        return artifacts

    @staticmethod
    def _suggest_owner(partner: Partner, cls: Classification) -> str:
        issue = (partner.open_issue or "").lower()
        if any(w in issue for w in ("settlement", "paisa", "payout", "money")):
            return "Finance / Settlements team"
        if any(w in issue for w in ("device", "atm", "fingerprint", "error", "hardware")):
            return "Field Support / Hardware team"
        if partner.monthly_volume_inr >= config.HIGH_VALUE_VOLUME_INR:
            return "Key Account Manager"
        return "Partner Success lead"

    # --- stage 5: report ---
    def _build_report(self, run_id: str,
                      records: List[Dict[str, Any]]) -> Dict[str, Any]:
        def count(action: str) -> int:
            return sum(1 for r in records if r["decision"]["action"] == action)

        return {
            "run_id": run_id,
            "generated_at": "%sT00:00:00" % self.today.isoformat(),
            "reference_date": self.today.isoformat(),
            "brain": llm.brain_label(),
            "totals": {
                "partners_reviewed": len(records),
                "reminders_drafted": count(config.ACTION_REMIND),
                "escalations_created": count(config.ACTION_ESCALATE),
                "no_action": count(config.ACTION_NONE),
            },
            "partners": records,
        }

    def _build_summary(self, report: Dict[str, Any]) -> str:
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
            "## Escalations (need a human)",
            "",
        ]
        esc = [r for r in report["partners"]
               if r["decision"]["action"] == config.ACTION_ESCALATE]
        if not esc:
            lines.append("_None._")
        else:
            for r in esc:
                lines.append("### %s — %s (%s)"
                             % (r["id"], r["name"], r["classification"]["severity"].upper()))
                lines.append("- %s" % r["classification"]["summary"])
                for reason in r["decision"]["reasons"]:
                    lines.append("  - %s" % reason)
                lines.append("")
        lines.append("## Reminders drafted")
        lines.append("")
        rem = [r for r in report["partners"]
               if r["decision"]["action"] == config.ACTION_REMIND]
        if not rem:
            lines.append("_None._")
        else:
            for r in rem:
                lines.append("- **%s** (%s): %s"
                             % (r["name"], r["id"], r["classification"]["summary"]))
        lines.append("")
        return "\n".join(lines)

    # --- HTML report (opens in any browser, no server needed) ---
    def _build_html(self, report: Dict[str, Any], run_dir: str) -> str:
        e = html_lib.escape
        t = report["totals"]
        action_meta = {
            config.ACTION_ESCALATE: ("#e74c3c", "Escalate"),
            config.ACTION_REMIND: ("#f39c12", "Reminder"),
            config.ACTION_NONE: ("#27ae60", "No action"),
        }

        # Decisions table rows
        rows = []
        for r in report["partners"]:
            cls = r["classification"]
            color, label = action_meta.get(r["decision"]["action"], ("#888", "?"))
            rows.append(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%.2f</td>"
                "<td><span class='pill' style='background:%s'>%s</span></td></tr>"
                % (e(r["id"]), e(r["name"]), e(cls["status"]), e(cls["severity"]),
                   cls["confidence"], color, label))

        # Escalation cards
        esc_cards = []
        for r in report["partners"]:
            if r["decision"]["action"] != config.ACTION_ESCALATE:
                continue
            cls = r["classification"]
            reasons = "".join("<li>%s</li>" % e(x) for x in r["decision"]["reasons"])
            pend = "".join("<li>%s</li>" % e(x) for x in cls["pending_actions"])
            esc_cards.append(
                "<div class='card esc'><h3>%s — %s "
                "<span class='sev'>%s</span></h3>"
                "<p>%s</p><p class='muted'>%d days since contact</p>"
                "<b>Why escalated</b><ul>%s</ul>%s</div>"
                % (e(r["id"]), e(r["name"]), e(cls["severity"].upper()),
                   e(cls["summary"]), r["days_since_last_contact"], reasons,
                   ("<b>Pending</b><ul>%s</ul>" % pend) if pend else ""))

        # Reminder cards (read the drafted text from disk)
        rem_cards = []
        for r in report["partners"]:
            if r["decision"]["action"] != config.ACTION_REMIND:
                continue
            text = ""
            path = r["artifacts"].get("reminder")
            if path:
                try:
                    with open(os.path.join(run_dir, path), "r", encoding="utf-8") as fh:
                        text = fh.read().strip()
                except OSError:
                    text = ""
            rem_cards.append(
                "<div class='card rem'><h3>%s — %s</h3><p>%s</p></div>"
                % (e(r["id"]), e(r["name"]), e(text)))

        empty = "<p class='muted'>None.</p>"
        return _HTML_TEMPLATE % {
            "run_id": e(report["run_id"]),
            "brain": e(report["brain"]),
            "reviewed": t["partners_reviewed"],
            "reminders": t["reminders_drafted"],
            "escalations": t["escalations_created"],
            "no_action": t["no_action"],
            "rows": "".join(rows),
            "esc": "".join(esc_cards) or empty,
            "rem": "".join(rem_cards) or empty,
        }

    # --- console output ---
    def _print_console_summary(self, report: Dict[str, Any]) -> None:
        t = report["totals"]
        self._say("SUMMARY  reviewed=%d  reminders=%d  escalations=%d  no_action=%d"
                  % (t["partners_reviewed"], t["reminders_drafted"],
                     t["escalations_created"], t["no_action"]))

    def _say(self, msg: str) -> None:
        if self.verbose:
            print(msg)


_HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Partner Follow-up Claw — %(run_id)s</title>
<style>
  body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       margin:0;background:#f5f6f8;color:#1d2330}
  .wrap{max-width:1000px;margin:0 auto;padding:28px 20px 60px}
  h1{margin:0 0 4px}.sub{color:#6b7280;margin:0 0 24px}
  .metrics{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:28px}
  .m{flex:1;min-width:150px;background:#fff;border-radius:12px;padding:16px 18px;
     box-shadow:0 1px 3px rgba(0,0,0,.08)}
  .m .n{font-size:30px;font-weight:700}.m .l{color:#6b7280;font-size:13px}
  table{width:100%%;border-collapse:collapse;background:#fff;border-radius:12px;
        overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  th,td{text-align:left;padding:10px 14px;border-bottom:1px solid #eef0f3;font-size:14px}
  th{background:#fafbfc;color:#6b7280;font-weight:600}
  .pill{color:#fff;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
  h2{margin:34px 0 12px}
  .cols{display:flex;gap:18px;flex-wrap:wrap}
  .col{flex:1;min-width:300px}
  .card{background:#fff;border-radius:12px;padding:14px 16px;margin-bottom:12px;
        box-shadow:0 1px 3px rgba(0,0,0,.08);border-left:4px solid #ccc}
  .card.esc{border-left-color:#e74c3c}.card.rem{border-left-color:#f39c12}
  .card h3{margin:0 0 6px;font-size:15px}
  .sev{background:#e74c3c;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px}
  .muted{color:#9aa1ad;font-size:13px}.card ul{margin:6px 0 0 18px;padding:0}
  .card li{font-size:13px;margin:2px 0}
  footer{margin-top:30px;color:#9aa1ad;font-size:12px}
</style></head><body><div class="wrap">
  <h1>🐾 Partner Follow-up Claw</h1>
  <p class="sub">Run <b>%(run_id)s</b> &nbsp;·&nbsp; Brain: <b>%(brain)s</b></p>
  <div class="metrics">
    <div class="m"><div class="n">%(reviewed)d</div><div class="l">Partners reviewed</div></div>
    <div class="m"><div class="n">%(reminders)d</div><div class="l">🟡 Reminders drafted</div></div>
    <div class="m"><div class="n">%(escalations)d</div><div class="l">🔴 Escalations</div></div>
    <div class="m"><div class="n">%(no_action)d</div><div class="l">🟢 No action</div></div>
  </div>
  <h2>Decisions</h2>
  <table><thead><tr><th>ID</th><th>Partner</th><th>Status</th><th>Severity</th>
  <th>Confidence</th><th>Action</th></tr></thead><tbody>%(rows)s</tbody></table>
  <div class="cols">
    <div class="col"><h2>🔴 Escalations</h2>%(esc)s</div>
    <div class="col"><h2>🟡 Drafted reminders</h2>%(rem)s</div>
  </div>
  <footer>Generated by the Partner Follow-up Claw — an autonomous agent for Eko's partner workflow.</footer>
</div></body></html>"""
