"""Tests for low-confidence escalation routing.

When the model's confidence is below MIN_CONFIDENCE (0.55), the agent
should escalate to a human rather than act on a shaky read.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import date
from src.schemas import Partner, Classification
from src.agent import FollowUpClaw
from src import config


def _make_partner(**kw) -> Partner:
    defaults = dict(
        id="EKO-TEST", name="Test Partner", owner="Owner",
        region="Region", segment="Retailer", monthly_volume_inr=10000,
        last_contact_date="2026-06-25", followups_sent=0,
        awaiting_response=False, open_issue=None, notes="Fine.",
    )
    defaults.update(kw)
    return Partner(**defaults)


def _make_cls(**kw) -> Classification:
    defaults = dict(
        status=config.STATUS_ON_TRACK, severity="low",
        sentiment="positive", confidence=0.85,
        summary="OK.", pending_actions=[], source="test",
    )
    defaults.update(kw)
    return Classification(**defaults)


def _decide(partner, cls, days):
    claw = FollowUpClaw(reference_date=date(2026, 6, 28), verbose=False)
    return claw._decide(partner, cls, days)


class TestLowConfidence:
    def test_confidence_below_threshold_escalates(self):
        d = _decide(_make_partner(), _make_cls(confidence=0.40), days=3)
        assert d.action == config.ACTION_ESCALATE
        assert any("confidence" in r.lower() or "0.40" in r for r in d.reasons)

    def test_confidence_at_threshold_does_not_escalate(self):
        d = _decide(_make_partner(), _make_cls(confidence=0.55), days=3)
        low_conf_reasons = [r for r in d.reasons if "confidence" in r.lower()]
        assert len(low_conf_reasons) == 0

    def test_confidence_just_below_threshold_escalates(self):
        d = _decide(_make_partner(), _make_cls(confidence=0.54), days=3)
        assert d.action == config.ACTION_ESCALATE

    def test_high_confidence_does_not_trigger_escalation(self):
        d = _decide(_make_partner(), _make_cls(confidence=0.90), days=3)
        assert d.action != config.ACTION_ESCALATE
