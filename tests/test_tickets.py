"""Tests for the ticket system (TicketStore)."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
from src.tickets import TicketStore


@pytest.fixture
def store():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    s = TicketStore(db_path=tmp.name)
    yield s
    s.close()
    os.unlink(tmp.name)


ESCALATION_NOTE = {
    "partner_id": "EKO-1003",
    "partner_name": "Khan Telecom Point",
    "owner": "Imran Khan",
    "region": "Bhopal, MP",
    "segment": "Distributor",
    "status": "HIGH_RISK",
    "severity": "high",
    "sentiment": "negative",
    "confidence": 0.9,
    "days_since_last_contact": 19,
    "open_issue": "Settlement pending",
    "summary": "High-risk partner",
    "pending_actions": ["Verify settlement"],
    "escalation_reasons": ["No contact for 19 days"],
    "recommended_owner": "Finance / Settlements team",
}


class TestTicketStore:
    def test_create_ticket(self, store):
        ticket_id = store.create_ticket(ESCALATION_NOTE)
        assert ticket_id is not None
        assert ticket_id > 0

    def test_has_open_ticket(self, store):
        assert store.has_open_ticket("EKO-1003") is False
        store.create_ticket(ESCALATION_NOTE)
        assert store.has_open_ticket("EKO-1003") is True

    def test_get_open_tickets(self, store):
        store.create_ticket(ESCALATION_NOTE)
        tickets = store.get_open_tickets()
        assert len(tickets) == 1
        assert tickets[0]["partner_id"] == "EKO-1003"

    def test_resolve_ticket(self, store):
        ticket_id = store.create_ticket(ESCALATION_NOTE)
        store.resolve_ticket(ticket_id)
        assert store.has_open_ticket("EKO-1003") is False

    def test_get_ticket(self, store):
        ticket_id = store.create_ticket(ESCALATION_NOTE)
        ticket = store.get_ticket(ticket_id)
        assert ticket["severity"] == "high"
        assert ticket["assigned_to"] == "Finance / Settlements team"
