"""Tests for persistent memory (PartnerMemory)."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
from datetime import date, timedelta
from src.memory import PartnerMemory


@pytest.fixture
def memory():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    mem = PartnerMemory(db_path=tmp.name)
    yield mem
    mem.close()
    os.unlink(tmp.name)


class TestPartnerMemory:
    def test_record_and_retrieve(self, memory):
        memory.record_action("EKO-1001", date(2026, 6, 28), "ESCALATE",
                             status="HIGH_RISK", severity="high")
        history = memory.get_history("EKO-1001")
        assert len(history) == 1
        assert history[0]["action"] == "ESCALATE"

    def test_was_escalated_recently_true(self, memory):
        memory.record_action("EKO-1001", date.today(), "ESCALATE")
        assert memory.was_escalated_recently("EKO-1001", within_days=3) is True

    def test_was_escalated_recently_false(self, memory):
        assert memory.was_escalated_recently("EKO-1001", within_days=3) is False

    def test_reminder_count(self, memory):
        memory.record_action("EKO-1001", date.today(), "SEND_REMINDER")
        memory.record_action("EKO-1001", date.today(), "SEND_REMINDER")
        assert memory.reminder_count("EKO-1001", within_days=7) == 2

    def test_empty_history(self, memory):
        assert memory.get_history("EKO-NONE") == []

    def test_multiple_partners(self, memory):
        memory.record_action("EKO-1001", date.today(), "ESCALATE")
        memory.record_action("EKO-1002", date.today(), "SEND_REMINDER")
        assert len(memory.get_history("EKO-1001")) == 1
        assert len(memory.get_history("EKO-1002")) == 1
