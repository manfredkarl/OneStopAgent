"""Tests for input_handler — pure functions, no Azure credentials required."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from input_handler import parse_assumption_json, build_default_values


class TestParseAssumptionJson:
    def test_valid_single_item(self):
        result = parse_assumption_json('[{"id": "users", "value": 500}]')
        assert result == [{"id": "users", "value": 500}]

    def test_valid_multiple_items(self):
        result = parse_assumption_json(
            '[{"id": "users", "value": 500}, {"id": "storage", "value": 100}]'
        )
        assert len(result) == 2
        assert result[0]["id"] == "users"
        assert result[1]["value"] == 100

    def test_returns_none_for_plain_text(self):
        assert parse_assumption_json("proceed") is None

    def test_returns_none_for_invalid_json(self):
        assert parse_assumption_json("{not: json}") is None

    def test_returns_none_for_json_object(self):
        assert parse_assumption_json('{"id": "x", "value": 1}') is None

    def test_returns_none_for_json_null(self):
        assert parse_assumption_json("null") is None

    def test_returns_none_when_id_missing(self):
        assert parse_assumption_json('[{"value": 1}]') is None

    def test_returns_none_when_value_missing(self):
        assert parse_assumption_json('[{"id": "x"}]') is None

    def test_returns_none_for_array_of_primitives(self):
        assert parse_assumption_json("[1, 2, 3]") is None

    def test_empty_array_returns_empty_list(self):
        result = parse_assumption_json("[]")
        assert result == []

    def test_preserves_extra_fields(self):
        raw = '[{"id": "x", "value": 42, "label": "Extra"}]'
        result = parse_assumption_json(raw)
        assert result is not None
        assert result[0]["label"] == "Extra"


class TestBuildDefaultValues:
    def test_basic_with_unit(self):
        assumptions = [
            {"id": "users", "label": "Daily users", "default": 1000, "unit": "/day"}
        ]
        result = build_default_values(assumptions)
        assert result == [
            {"id": "users", "label": "Daily users", "value": 1000, "unit": "/day"}
        ]

    def test_missing_unit_defaults_to_empty_string(self):
        assumptions = [{"id": "storage", "label": "Storage GB", "default": 100}]
        result = build_default_values(assumptions)
        assert result[0]["unit"] == ""

    def test_multiple_assumptions(self):
        assumptions = [
            {"id": "a", "label": "A", "default": 1, "unit": "x"},
            {"id": "b", "label": "B", "default": 2},
        ]
        result = build_default_values(assumptions)
        assert len(result) == 2
        assert result[0]["value"] == 1
        assert result[1]["value"] == 2
        assert result[1]["unit"] == ""

    def test_empty_list(self):
        assert build_default_values([]) == []

    def test_uses_default_not_current_value(self):
        assumptions = [{"id": "x", "label": "X", "default": 99, "current": 0}]
        result = build_default_values(assumptions)
        assert result[0]["value"] == 99
