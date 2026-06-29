"""Persistent memory for the Partner Follow-up Claw.

Tracks what the agent did for each partner on each run so it can
make smarter decisions over time — e.g. avoid duplicate escalations,
detect repeat offenders, and count prior reminders.
"""

import os
import sqlite3
from datetime import date, timedelta
from typing import Any, Dict, List


DEFAULT_DB_PATH = os.path.join("data", "memory.db")


class PartnerMemory:
    """Persistent memory for the Partner Follow-up Claw.

    Tracks what the agent did for each partner on each run so it can
    make smarter decisions over time.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS partner_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_id  TEXT    NOT NULL,
                run_date    TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                status      TEXT,
                severity    TEXT,
                confidence  REAL,
                notes       TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_partner_date
            ON partner_history (partner_id, run_date)
        """)
        self.conn.commit()

    def record_action(self, partner_id: str, run_date: date, action: str,
                      status: str = "", severity: str = "",
                      confidence: float = 0.0, notes: str = "") -> None:
        """Record an action taken for a partner during a run."""
        self.conn.execute(
            "INSERT INTO partner_history (partner_id, run_date, action, status, severity, confidence, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (partner_id, run_date.isoformat(), action, status, severity, confidence, notes),
        )
        self.conn.commit()

    def get_history(self, partner_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent actions for a partner."""
        rows = self.conn.execute(
            "SELECT * FROM partner_history WHERE partner_id = ? ORDER BY created_at DESC LIMIT ?",
            (partner_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def was_escalated_recently(self, partner_id: str, within_days: int = 3) -> bool:
        """Check if the partner was already escalated within the given window."""
        cutoff = (date.today() - timedelta(days=within_days)).isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM partner_history "
            "WHERE partner_id = ? AND action = 'ESCALATE' AND run_date >= ?",
            (partner_id, cutoff),
        ).fetchone()
        return row["cnt"] > 0

    def reminder_count(self, partner_id: str, within_days: int = 7) -> int:
        """Count how many reminders were sent to this partner recently."""
        cutoff = (date.today() - timedelta(days=within_days)).isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM partner_history "
            "WHERE partner_id = ? AND action = 'SEND_REMINDER' AND run_date >= ?",
            (partner_id, cutoff),
        ).fetchone()
        return row["cnt"]

    def get_all_history_summary(self) -> List[Dict[str, Any]]:
        """Return a summary of all partners' action counts."""
        rows = self.conn.execute(
            "SELECT partner_id, action, COUNT(*) as cnt "
            "FROM partner_history GROUP BY partner_id, action ORDER BY partner_id"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
