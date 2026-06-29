"""Tests for the escalation policy in agent._decide().

Every rule in config.py is tested individually to ensure the policy
is transparent, auditable, and correct.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import date
from src.schemas import Partner, Classification, Decision
from src.agent import FollowUpClaw
from src import config


def _make_partner(**overrides) -> Partner:
    defaults = dict(
        id="EKO-TEST", name="Test Partner", owner="Test Owner",
        region="Test Region", segment="Retailer",
        monthly_volume_inr=10000, last_contact_date="2026-06-20",
        followups_sent=0, awaiting_response=False,
        open_issue=None, notes="Test notes.",
    )
    defaults.update(overrides)
    return Partner(**defaults)


def _make_cls(**overrides) -> Classification:
    defaults = dict(
        status=config.STATUS_ON_TRACK, severity="low",
        sentiment="positive", confidence=0.85,
        summary="All good.", pending_actions=[], source="test",
    )
    defaults.update(overrides)
    return Classification(**defaults)


def _decide(partner, cls, days):
    claw = FollowUpClaw(reference_date=date(2026, 6, 28), verbose=False)
    return claw._decide(partner, cls, days)


class TestNoAction:
    def test_healthy_partner_no_action(self):
        d = _decide(_make_partner(), _make_cls(), days=3)
        assert d.action == config.ACTION_NONE

    def test_on_track_no_issue(self):
        d = _decide(
            _make_partner(open_issue=None, awaiting_response=False),
            _make_cls(status=config.STATUS_ON_TRACK), days=2,
        )
        assert d.action == config.ACTION_NONE


class TestReminder:
    def test_open_issue_triggers_reminder(self):
        d = _decide(
            _make_partner(open_issue="Needs help"),
            _make_cls(status=config.STATUS_PENDING, severity="low", confidence=0.85), days=3,
        )
        assert d.action == config.ACTION_REMIND

    def test_awaiting_response_triggers_reminder(self):
        d = _decide(
            _make_partner(awaiting_response=True),
            _make_cls(status=config.STATUS_PENDING, confidence=0.85), days=3,
        )
        assert d.action == config.ACTION_REMIND

    def test_days_past_remind_threshold(self):
        d = _decide(
            _make_partner(),
            _make_cls(status=config.STATUS_ON_TRACK, confidence=0.85),
            days=config.REMIND_AFTER_DAYS,
        )
        assert d.action == config.ACTION_REMIND


class TestSilenceEscalation:
    def test_14_days_silence_escalates(self):
        d = _decide(_make_partner(), _make_cls(), days=14)
        assert d.action == config.ACTION_ESCALATE
        assert any("14" in r for r in d.reasons)

    def test_13_days_does_not_escalate_on_silence(self):
        d = _decide(_make_partner(), _make_cls(), days=13)
        assert d.action != config.ACTION_ESCALATE


class TestHighRiskEscalation:
    def test_high_risk_status_escalates(self):
        d = _decide(
            _make_partner(),
            _make_cls(status=config.STATUS_HIGH_RISK), days=3,
        )
        assert d.action == config.ACTION_ESCALATE

    def test_high_severity_escalates(self):
        d = _decide(
            _make_partner(),
            _make_cls(severity="high"), days=3,
        )
        assert d.action == config.ACTION_ESCALATE


class TestSentimentEscalation:
    def test_negative_sentiment_escalates(self):
        d = _decide(
            _make_partner(),
            _make_cls(sentiment="negative"), days=3,
        )
        assert d.action == config.ACTION_ESCALATE

    def test_neutral_sentiment_does_not_escalate(self):
        d = _decide(_make_partner(), _make_cls(sentiment="neutral"), days=3)
        assert d.action != config.ACTION_ESCALATE


class TestKeyPartnerEscalation:
    def test_high_volume_delayed_escalates(self):
        d = _decide(
            _make_partner(monthly_volume_inr=60000),
            _make_cls(status=config.STATUS_DELAYED), days=3,
        )
        assert d.action == config.ACTION_ESCALATE

    def test_low_volume_delayed_does_not_escalate(self):
        d = _decide(
            _make_partner(monthly_volume_inr=5000),
            _make_cls(status=config.STATUS_DELAYED, severity="low", confidence=0.85), days=3,
        )
        assert d.action != config.ACTION_ESCALATE


class TestRepeatedNoResponse:
    def test_3_followups_no_response_escalates(self):
        d = _decide(
            _make_partner(followups_sent=3, awaiting_response=True),
            _make_cls(confidence=0.85), days=3,
        )
        assert d.action == config.ACTION_ESCALATE

    def test_2_followups_does_not_escalate(self):
        d = _decide(
            _make_partner(followups_sent=2, awaiting_response=True),
            _make_cls(confidence=0.85), days=3,
        )
        assert d.action != config.ACTION_ESCALATE
