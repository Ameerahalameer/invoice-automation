"""Tests for canonical data models."""

import pytest
from decimal import Decimal
from datetime import date

from invoice_tool.models import (
    Category,
    EngineerBlock,
    EngineerLevel,
    RateSet,
    StrictValidationError,
    TimesheetEntry,
)


class TestRateSet:
    def test_valid_rates(self):
        r = RateSet(normal=Decimal("286"), ot=Decimal("372"), hot=Decimal("443"))
        assert r.normal == Decimal("286")
        assert r.ot == Decimal("372")
        assert r.hot == Decimal("443")

    def test_zero_rate_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            RateSet(normal=Decimal("0"), ot=Decimal("372"), hot=Decimal("443"))

    def test_negative_rate_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            RateSet(normal=Decimal("-10"), ot=Decimal("372"), hot=Decimal("443"))


class TestTimesheetEntry:
    def test_total_hours(self):
        entry = TimesheetEntry(
            engineer_name="Test",
            date=date(2026, 1, 10),
            normal_hours=Decimal("8"),
            ot_hours=Decimal("2"),
            hot_hours=Decimal("4"),
            category=Category.ONSHORE,
            engineer_level=EngineerLevel.SERVICE_FIELD,
            source_file="test.pdf",
        )
        assert entry.total_hours == Decimal("14")


class TestEngineerBlock:
    def test_cost_calculations(self):
        entries = [
            TimesheetEntry(
                engineer_name="Test",
                date=date(2026, 1, 10),
                normal_hours=Decimal("10"),
                ot_hours=Decimal("2"),
                hot_hours=Decimal("0"),
                category=Category.ONSHORE,
                engineer_level=EngineerLevel.SERVICE_FIELD,
                source_file="test.pdf",
            ),
            TimesheetEntry(
                engineer_name="Test",
                date=date(2026, 1, 11),
                normal_hours=Decimal("8"),
                ot_hours=Decimal("0"),
                hot_hours=Decimal("4"),
                category=Category.ONSHORE,
                engineer_level=EngineerLevel.SERVICE_FIELD,
                source_file="test.pdf",
            ),
        ]
        block = EngineerBlock(
            name="Test",
            category=Category.ONSHORE,
            engineer_level=EngineerLevel.SERVICE_FIELD,
            entries=entries,
            normal_rate=Decimal("286"),
            ot_rate=Decimal("372"),
            hot_rate=Decimal("443"),
        )
        assert block.total_normal_hours == Decimal("18")
        assert block.total_ot_hours == Decimal("2")
        assert block.total_hot_hours == Decimal("4")
        assert block.normal_cost == Decimal("5148.00")
        assert block.ot_cost == Decimal("744.00")
        assert block.hot_cost == Decimal("1772.00")
        assert block.total_cost == Decimal("7664.00")


class TestStrictValidationError:
    def test_error_message(self):
        e = StrictValidationError(["err1", "err2"])
        assert "2 error(s)" in str(e)
        assert "err1" in str(e)
        assert "err2" in str(e)
        assert e.errors == ["err1", "err2"]
