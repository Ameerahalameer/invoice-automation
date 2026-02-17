"""Tests for strict validation engine."""

import pytest
from decimal import Decimal
from datetime import date

from invoice_tool.engine.validator import validate_entries
from invoice_tool.models import (
    Category,
    EngineerLevel,
    POData,
    RateSet,
    StrictValidationError,
    TimesheetEntry,
)


def _make_po() -> POData:
    rate = RateSet(normal=Decimal("286"), ot=Decimal("372"), hot=Decimal("443"))
    return POData(
        contract_number="1535984",
        onshore_rates={EngineerLevel.SERVICE_FIELD: rate},
        offshore_rates={EngineerLevel.SERVICE_FIELD: RateSet(
            normal=Decimal("372"), ot=Decimal("484"), hot=Decimal("577"),
        )},
        onshore_hours_per_day=10,
        offshore_hours_per_day=12,
        max_amount_usd=Decimal("131000"),
        source_file="test_po.pdf",
    )


def _make_entry(**kwargs) -> TimesheetEntry:
    defaults = dict(
        engineer_name="Test",
        date=date(2026, 1, 10),
        normal_hours=Decimal("8"),
        ot_hours=Decimal("0"),
        hot_hours=Decimal("0"),
        category=Category.ONSHORE,
        engineer_level=EngineerLevel.SERVICE_FIELD,
        source_file="test.pdf",
    )
    defaults.update(kwargs)
    return TimesheetEntry(**defaults)


class TestValidator:
    def test_valid_entries_pass(self):
        entries = [_make_entry()]
        result = validate_entries(entries, _make_po())
        assert len(result) == 1

    def test_empty_entries_fail(self):
        with pytest.raises(StrictValidationError, match="No timesheet entries"):
            validate_entries([], _make_po())

    def test_negative_hours_fail(self):
        entries = [_make_entry(normal_hours=Decimal("-1"))]
        with pytest.raises(StrictValidationError, match="negative"):
            validate_entries(entries, _make_po())

    def test_over_24_hours_fail(self):
        entries = [_make_entry(normal_hours=Decimal("20"), ot_hours=Decimal("5"))]
        with pytest.raises(StrictValidationError, match="> 24"):
            validate_entries(entries, _make_po())

    def test_missing_rate_fail(self):
        po = POData(
            contract_number="1535984",
            onshore_rates={},  # no rates
            offshore_rates={},
            onshore_hours_per_day=10,
            offshore_hours_per_day=12,
            max_amount_usd=Decimal("131000"),
            source_file="test_po.pdf",
        )
        entries = [_make_entry()]
        with pytest.raises(StrictValidationError, match="No.*rates"):
            validate_entries(entries, po)

    def test_aggregated_daily_over_24_fail(self):
        entries = [
            _make_entry(normal_hours=Decimal("15")),
            _make_entry(normal_hours=Decimal("10")),  # same date, same engineer
        ]
        with pytest.raises(StrictValidationError, match="aggregated daily total"):
            validate_entries(entries, _make_po())
