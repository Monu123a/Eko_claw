"""Tests for handling malformed LLM output.

The agent should gracefully handle bad JSON, missing fields, markdown
fences, and other common LLM output issues without crashing.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.llm import _extract_json, _classification_from_json
from src import config


class TestExtractJson:
    def test_clean_json(self):
        result = _extract_json('{"status": "ON_TRACK", "severity": "low"}')
        assert result["status"] == "ON_TRACK"

    def test_json_with_markdown_fences(self):
        text = '```json\n{"status": "ON_TRACK"}\n```'
        result = _extract_json(text)
        assert result["status"] == "ON_TRACK"

    def test_json_with_plain_fences(self):
        text = '```\n{"status": "PENDING"}\n```'
        result = _extract_json(text)
        assert result["status"] == "PENDING"

    def test_json_embedded_in_prose(self):
        text = 'Here is the result:\n{"status": "DELAYED", "severity": "medium"}\nDone.'
        result = _extract_json(text)
        assert result["status"] == "DELAYED"

    def test_completely_invalid_json_raises(self):
        with pytest.raises(Exception):
            _extract_json("This is not JSON at all.")

    def test_whitespace_padding(self):
        result = _extract_json('  \n  {"x": 1}  \n  ')
        assert result["x"] == 1


class TestClassificationFromJson:
    def test_valid_data(self):
        data = {
            "status": "HIGH_RISK", "severity": "high", "sentiment": "negative",
            "confidence": 0.9, "summary": "Bad situation.",
            "pending_actions": ["Fix it"],
        }
        cls = _classification_from_json(data, source="test")
        assert cls.status == "HIGH_RISK"
        assert cls.severity == "high"
        assert cls.confidence == 0.9

    def test_missing_fields_use_defaults(self):
        cls = _classification_from_json({}, source="test")
        assert cls.status == config.STATUS_PENDING
        assert cls.severity == "medium"
        assert cls.sentiment == "neutral"
        assert cls.confidence == 0.5

    def test_invalid_status_normalized(self):
        cls = _classification_from_json({"status": "BANANA"}, source="test")
        assert cls.status == config.STATUS_PENDING

    def test_case_normalization(self):
        cls = _classification_from_json(
            {"status": "on_track", "severity": "HIGH", "sentiment": "Negative"},
            source="test",
        )
        assert cls.status == "ON_TRACK"
        assert cls.severity == "high"
        assert cls.sentiment == "negative"

    def test_confidence_as_string(self):
        cls = _classification_from_json({"confidence": "0.75"}, source="test")
        assert cls.confidence == 0.75
