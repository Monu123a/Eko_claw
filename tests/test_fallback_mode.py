"""Tests for the rule-based fallback brain.

When no API key is set, the agent should use the deterministic
rule-based brain and complete the run successfully.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.llm import _classify_rules, brain_label
from src.schemas import Partner
from src import config


def _make_partner(**kw) -> Partner:
    defaults = dict(
        id="EKO-TEST", name="Test Partner", owner="Owner",
        region="Region", segment="Retailer", monthly_volume_inr=10000,
        last_contact_date="2026-06-25", followups_sent=0,
        awaiting_response=False, open_issue=None, notes="Normal partner.",
    )
    defaults.update(kw)
    return Partner(**defaults)


class TestRuleBasedFallback:
    def test_healthy_partner_on_track(self):
        cls = _classify_rules(_make_partner(), days_since_contact=3)
        assert cls.status == config.STATUS_ON_TRACK
        assert cls.source == "rules"

    def test_open_issue_marks_pending(self):
        cls = _classify_rules(
            _make_partner(open_issue="Needs help"), days_since_contact=5
        )
        assert cls.status == config.STATUS_PENDING

    def test_settlement_keyword_marks_high_risk(self):
        cls = _classify_rules(
            _make_partner(open_issue="Settlement pending"), days_since_contact=5
        )
        assert cls.status == config.STATUS_HIGH_RISK
        assert cls.severity == "high"

    def test_long_silence_marks_delayed(self):
        cls = _classify_rules(_make_partner(), days_since_contact=15)
        assert cls.status == config.STATUS_DELAYED

    def test_many_followups_marks_delayed(self):
        cls = _classify_rules(
            _make_partner(followups_sent=4), days_since_contact=5
        )
        assert cls.status == config.STATUS_DELAYED
        assert cls.severity == "high"

    def test_negative_sentiment_from_keywords(self):
        cls = _classify_rules(
            _make_partner(notes="partner is upset and stopped transacting"),
            days_since_contact=5,
        )
        assert cls.sentiment == "negative"

    def test_brain_label_without_keys(self):
        for k in ("LLM_API_KEY", "LLM_BASE_URL", "ANTHROPIC_API_KEY"):
            os.environ.pop(k, None)
        assert "rule-based" in brain_label().lower()

    def test_classification_always_has_source(self):
        cls = _classify_rules(_make_partner(), days_since_contact=3)
        assert cls.source == "rules"
