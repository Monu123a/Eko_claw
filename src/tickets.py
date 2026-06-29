"""A simple SQLite-backed ticket system — simulates Jira / Zoho.

Each escalation creates a ticket. The ops team can query open tickets,
resolve them, and the agent can check whether a ticket is already open
for a partner before creating a duplicate.
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional


DEFAULT_DB_PATH = os.path.join("data", "tickets.db")


class TicketStore:
    """A simple SQLite-backed ticket system — simulates Jira / Zoho."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_id   TEXT    NOT NULL,
                title        TEXT    NOT NULL,
                severity     TEXT    NOT NULL DEFAULT 'medium',
                status       TEXT    NOT NULL DEFAULT 'OPEN',
                assigned_to  TEXT,
                description  TEXT,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                resolved_at  TEXT
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticket_partner
            ON tickets (partner_id, status)
        """)
        self.conn.commit()

    def create_ticket(self, escalation_note: Dict[str, Any]) -> int:
        """Create a ticket from a structured escalation note. Returns the ticket ID."""
        title = "%s — %s" % (
            escalation_note.get("partner_id", "?"),
            (escalation_note.get("summary") or escalation_note.get("open_issue") or "Escalation")[:120],
        )
        cursor = self.conn.execute(
            "INSERT INTO tickets (partner_id, title, severity, assigned_to, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                escalation_note.get("partner_id", ""),
                title,
                escalation_note.get("severity", "medium"),
                escalation_note.get("recommended_owner", "Partner Success lead"),
                _format_description(escalation_note),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def has_open_ticket(self, partner_id: str) -> bool:
        """Check if the partner already has an open ticket."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tickets WHERE partner_id = ? AND status = 'OPEN'",
            (partner_id,),
        ).fetchone()
        return row["cnt"] > 0

    def get_open_tickets(self) -> List[Dict[str, Any]]:
        """List all open tickets."""
        rows = self.conn.execute(
            "SELECT * FROM tickets WHERE status = 'OPEN' ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve_ticket(self, ticket_id: int) -> None:
        """Mark a ticket as resolved."""
        self.conn.execute(
            "UPDATE tickets SET status = 'RESOLVED', resolved_at = datetime('now') WHERE ticket_id = ?",
            (ticket_id,),
        )
        self.conn.commit()

    def get_ticket(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single ticket by ID."""
        row = self.conn.execute(
            "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self.conn.close()


def _format_description(note: Dict[str, Any]) -> str:
    """Format an escalation note into a human-readable ticket description."""
    lines = [
        "Partner: %s (%s)" % (note.get("partner_name", "?"), note.get("partner_id", "?")),
        "Owner: %s" % note.get("owner", "?"),
        "Region: %s | Segment: %s" % (note.get("region", "?"), note.get("segment", "?")),
        "Status: %s | Severity: %s | Sentiment: %s" % (
            note.get("status", "?"), note.get("severity", "?"), note.get("sentiment", "?")),
        "Confidence: %s" % note.get("confidence", "?"),
        "Days since contact: %s" % note.get("days_since_last_contact", "?"),
        "",
        "Issue: %s" % note.get("open_issue", "N/A"),
        "Summary: %s" % note.get("summary", "N/A"),
        "",
        "Escalation reasons:",
    ]
    for reason in note.get("escalation_reasons", []):
        lines.append("  - %s" % reason)
    pending = note.get("pending_actions", [])
    if pending:
        lines.append("")
        lines.append("Pending actions:")
        for action in pending:
            lines.append("  - %s" % action)
    return "\n".join(lines)
