"""A simulated WhatsApp Business API send queue.

Reminders are enqueued here after being drafted. In production, the
``process_queue`` method would call the WhatsApp Business API; here
it simulates a send by marking messages as SENT.

Ready to swap with a real API — just replace ``_simulate_send`` with
an HTTP call to the WhatsApp Business API endpoint.
"""

import os
import sqlite3
from typing import Any, Dict, List


DEFAULT_DB_PATH = os.path.join("data", "send_queue.db")


class SendQueue:
    """A simulated WhatsApp Business API send queue."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS send_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_id  TEXT    NOT NULL,
                partner_name TEXT,
                phone       TEXT,
                message     TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'PENDING',
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                sent_at     TEXT
            )
        """)
        self.conn.commit()

    def enqueue(self, partner_id: str, message: str,
                partner_name: str = "", phone: str = "") -> int:
        """Add a reminder message to the send queue. Returns the queue entry ID."""
        cursor = self.conn.execute(
            "INSERT INTO send_queue (partner_id, partner_name, phone, message) "
            "VALUES (?, ?, ?, ?)",
            (partner_id, partner_name, phone, message),
        )
        self.conn.commit()
        return cursor.lastrowid

    def process_queue(self) -> List[Dict[str, Any]]:
        """Process all pending messages. In production, this calls WhatsApp API."""
        pending = self.conn.execute(
            "SELECT * FROM send_queue WHERE status = 'PENDING' ORDER BY created_at"
        ).fetchall()
        results = []
        for row in pending:
            success = self._simulate_send(dict(row))
            new_status = "SENT" if success else "FAILED"
            self.conn.execute(
                "UPDATE send_queue SET status = ?, sent_at = datetime('now') WHERE id = ?",
                (new_status, row["id"]),
            )
            results.append({"id": row["id"], "partner_id": row["partner_id"], "status": new_status})
        self.conn.commit()
        return results

    def get_queue_status(self) -> Dict[str, int]:
        """Return counts of messages by status."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM send_queue GROUP BY status"
        ).fetchall()
        return {row["status"]: row["cnt"] for row in rows}

    def get_pending(self) -> List[Dict[str, Any]]:
        """Return all pending messages."""
        rows = self.conn.execute(
            "SELECT * FROM send_queue WHERE status = 'PENDING' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _simulate_send(entry: Dict[str, Any]) -> bool:
        """Simulate sending a WhatsApp message.

        In production, replace this with an HTTP call to the WhatsApp Business API.
        """
        print("\n[WhatsApp API] 📲 Sending message to %s (%s):" % (entry["partner_id"], entry["partner_name"]))
        print("  \"%s\"" % entry["message"])
        return True

    def close(self) -> None:
        self.conn.close()
