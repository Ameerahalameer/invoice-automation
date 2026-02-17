"""Tests for Saudi work week hours splitting logic."""

import pytest
from decimal import Decimal
from datetime import date

from invoice_tool.models import Category, EngineerLevel, TimesheetEntry
from invoice_tool.engine.hours_splitter import split_hours, apply_hours_split


def _make_entry(
    dt: date,
    normal: str = "0",
    ot: str = "0",
    hot: str = "0",
    category: Category = Category.ONSHORE,
) -> TimesheetEntry:
    return TimesheetEntry(
        engineer_name="Test",
        date=dt,
        normal_hours=Decimal(normal),
        ot_hours=Decimal(ot),
        hot_hours=Decimal(hot),
        category=category,
        engineer_level=EngineerLevel.SERVICE_FIELD,
        source_file="test.pdf",
    )


class TestSplitHours:
    """Test split_hours for individual entries."""

    def test_friday_all_hot(self):
        # 2026-01-16 is a Friday
        entry = _make_entry(date(2026, 1, 16), normal="12")
        result = split_hours(entry, standing_hours=10)
        assert result.normal_hours == Decimal("0")
        assert result.ot_hours == Decimal("0")
        assert result.hot_hours == Decimal("12")

    def test_saturday_all_ot(self):
        # 2026-01-17 is a Saturday
        entry = _make_entry(date(2026, 1, 17), normal="10")
        result = split_hours(entry, standing_hours=10)
        assert result.normal_hours == Decimal("0")
        assert result.ot_hours == Decimal("10")
        assert result.hot_hours == Decimal("0")

    def test_weekday_under_standing_all_normal(self):
        # 2026-01-11 is a Sunday (working day)
        entry = _make_entry(date(2026, 1, 11), normal="8")
        result = split_hours(entry, standing_hours=10)
        assert result.normal_hours == Decimal("8")
        assert result.ot_hours == Decimal("0")
        assert result.hot_hours == Decimal("0")

    def test_weekday_at_standing_all_normal(self):
        # 2026-01-12 is a Monday
        entry = _make_entry(date(2026, 1, 12), normal="10")
        result = split_hours(entry, standing_hours=10)
        assert result.normal_hours == Decimal("10")
        assert result.ot_hours == Decimal("0")
        assert result.hot_hours == Decimal("0")

    def test_weekday_over_standing_split_normal_ot(self):
        # 2026-01-13 is a Tuesday
        entry = _make_entry(date(2026, 1, 13), normal="14")
        result = split_hours(entry, standing_hours=10)
        assert result.normal_hours == Decimal("10")
        assert result.ot_hours == Decimal("4")
        assert result.hot_hours == Decimal("0")

    def test_offshore_12h_standing(self):
        # 2026-01-14 is a Wednesday
        entry = _make_entry(date(2026, 1, 14), normal="14", category=Category.OFFSHORE)
        result = split_hours(entry, standing_hours=12)
        assert result.normal_hours == Decimal("12")
        assert result.ot_hours == Decimal("2")
        assert result.hot_hours == Decimal("0")

    def test_zero_hours_unchanged(self):
        entry = _make_entry(date(2026, 1, 16), normal="0")
        result = split_hours(entry, standing_hours=10)
        assert result.normal_hours == Decimal("0")
        assert result.ot_hours == Decimal("0")
        assert result.hot_hours == Decimal("0")

    def test_existing_split_preserved(self):
        """If entry already has OT/HOT > 0, split_hours should NOT change it."""
        # Friday, but entry already has a split from Format A PDF
        entry = _make_entry(date(2026, 1, 16), normal="8", ot="2", hot="4")
        result = split_hours(entry, standing_hours=10)
        assert result.normal_hours == Decimal("8")
        assert result.ot_hours == Decimal("2")
        assert result.hot_hours == Decimal("4")

    def test_thursday_is_working_day(self):
        # 2026-01-15 is a Thursday (last working day of Saudi week)
        entry = _make_entry(date(2026, 1, 15), normal="12")
        result = split_hours(entry, standing_hours=10)
        assert result.normal_hours == Decimal("10")
        assert result.ot_hours == Decimal("2")
        assert result.hot_hours == Decimal("0")

    def test_preserves_metadata(self):
        entry = _make_entry(date(2026, 1, 16), normal="5")
        result = split_hours(entry, standing_hours=10)
        assert result.engineer_name == "Test"
        assert result.date == date(2026, 1, 16)
        assert result.category == Category.ONSHORE
        assert result.engineer_level == EngineerLevel.SERVICE_FIELD
        assert result.source_file == "test.pdf"


class TestApplyHoursSplit:
    """Test apply_hours_split for batch processing."""

    def test_mixed_categories(self):
        entries = [
            _make_entry(date(2026, 1, 14), normal="14", category=Category.ONSHORE),
            _make_entry(date(2026, 1, 14), normal="14", category=Category.OFFSHORE),
        ]
        results = apply_hours_split(entries, onshore_standing=10, offshore_standing=12)
        # Onshore: 14 -> 10N + 4OT
        assert results[0].normal_hours == Decimal("10")
        assert results[0].ot_hours == Decimal("4")
        # Offshore: 14 -> 12N + 2OT
        assert results[1].normal_hours == Decimal("12")
        assert results[1].ot_hours == Decimal("2")

    def test_empty_list(self):
        results = apply_hours_split([])
        assert results == []

    def test_preserves_order(self):
        entries = [
            _make_entry(date(2026, 1, 11), normal="5"),
            _make_entry(date(2026, 1, 12), normal="8"),
            _make_entry(date(2026, 1, 13), normal="12"),
        ]
        results = apply_hours_split(entries)
        assert results[0].date == date(2026, 1, 11)
        assert results[1].date == date(2026, 1, 12)
        assert results[2].date == date(2026, 1, 13)
