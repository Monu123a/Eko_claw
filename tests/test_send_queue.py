"""Tests for the simulated WhatsApp send queue."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
from src.send_queue import SendQueue


@pytest.fixture
def queue():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    q = SendQueue(db_path=tmp.name)
    yield q
    q.close()
    os.unlink(tmp.name)


class TestSendQueue:
    def test_enqueue(self, queue):
        entry_id = queue.enqueue("EKO-1002", "Hello, checking in!")
        assert entry_id > 0

    def test_get_pending(self, queue):
        queue.enqueue("EKO-1002", "Hello")
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0]["status"] == "PENDING"

    def test_process_queue(self, queue):
        queue.enqueue("EKO-1002", "Hello")
        queue.enqueue("EKO-1003", "Follow up")
        results = queue.process_queue()
        assert len(results) == 2
        assert all(r["status"] == "SENT" for r in results)

    def test_processed_not_pending(self, queue):
        queue.enqueue("EKO-1002", "Hello")
        queue.process_queue()
        assert len(queue.get_pending()) == 0

    def test_queue_status(self, queue):
        queue.enqueue("EKO-1002", "Hello")
        queue.enqueue("EKO-1003", "Follow up")
        queue.process_queue()
        status = queue.get_queue_status()
        assert status.get("SENT", 0) == 2
        assert status.get("PENDING", 0) == 0
