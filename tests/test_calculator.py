"""Tests for financial calculation engine."""

import pytest
from decimal import Decimal
from datetime import date

from invoice_tool.engine.calculator import calculate_invoice
from invoice_tool.models import (
    Category,
    EngineerLevel,
    POData,
    RateSet,
    TimesheetEntry,
)


def _make_po() -> POData:
    return POData(
        contract_number="1535984",
        onshore_rates={
            EngineerLevel.SERVICE_FIELD: RateSet(
                normal=Decimal("286"), ot=Decimal("372"), hot=Decimal("443"),
            ),
        },
        offshore_rates={
            EngineerLevel.SERVICE_FIELD: RateSet(
                normal=Decimal("372"), ot=Decimal("484"), hot=Decimal("577"),
            ),
        },
        onshore_hours_per_day=10,
        offshore_hours_per_day=12,
        max_amount_usd=Decimal("131000"),
        source_file="test_po.pdf",
    )


class TestCalculator:
    def test_single_engineer(self):
        entries = [
            TimesheetEntry(
                engineer_name="TestEng",
                date=date(2026, 1, 10),
                normal_hours=Decimal("10"),
                ot_hours=Decimal("2"),
                hot_hours=Decimal("0"),
                category=Category.ONSHORE,
                engineer_level=EngineerLevel.SERVICE_FIELD,
                source_file="test.pdf",
            ),
        ]
        result = calculate_invoice(entries, _make_po())
        assert len(result.engineer_blocks) == 1
        block = result.engineer_blocks[0]
        assert block.normal_cost == Decimal("2860.00")
        assert block.ot_cost == Decimal("744.00")
        assert block.total_cost == Decimal("3604.00")
        assert result.grand_total == Decimal("3604.00")

    def test_multiple_engineers(self):
        entries = [
            TimesheetEntry(
                engineer_name="Eng1",
                date=date(2026, 1, 10),
                normal_hours=Decimal("8"),
                ot_hours=Decimal("0"),
                hot_hours=Decimal("0"),
                category=Category.ONSHORE,
                engineer_level=EngineerLevel.SERVICE_FIELD,
                source_file="test.pdf",
            ),
            TimesheetEntry(
                engineer_name="Eng2",
                date=date(2026, 1, 10),
                normal_hours=Decimal("12"),
                ot_hours=Decimal("0"),
                hot_hours=Decimal("0"),
                category=Category.OFFSHORE,
                engineer_level=EngineerLevel.SERVICE_FIELD,
                source_file="test.pdf",
            ),
        ]
        result = calculate_invoice(entries, _make_po())
        assert len(result.engineer_blocks) == 2
        # Eng1: 8 * 286 = 2288
        # Eng2: 12 * 372 = 4464
        assert result.grand_total == Decimal("6752.00")

    def test_date_aggregation(self):
        # Same engineer, same date, two entries -> should aggregate
        entries = [
            TimesheetEntry(
                engineer_name="TestEng",
                date=date(2026, 1, 10),
                normal_hours=Decimal("5"),
                ot_hours=Decimal("0"),
                hot_hours=Decimal("0"),
                category=Category.ONSHORE,
                engineer_level=EngineerLevel.SERVICE_FIELD,
                source_file="file1.pdf",
            ),
            TimesheetEntry(
                engineer_name="TestEng",
                date=date(2026, 1, 10),
                normal_hours=Decimal("3"),
                ot_hours=Decimal("2"),
                hot_hours=Decimal("0"),
                category=Category.ONSHORE,
                engineer_level=EngineerLevel.SERVICE_FIELD,
                source_file="file2.pdf",
            ),
        ]
        result = calculate_invoice(entries, _make_po())
        block = result.engineer_blocks[0]
        assert block.total_normal_hours == Decimal("8")
        assert block.total_ot_hours == Decimal("2")
        assert len(block.entries) == 1  # aggregated to 1 date

    def test_reconciliation(self):
        entries = [
            TimesheetEntry(
                engineer_name="TestEng",
                date=date(2026, 1, 10),
                normal_hours=Decimal("10"),
                ot_hours=Decimal("2"),
                hot_hours=Decimal("0"),
                category=Category.ONSHORE,
                engineer_level=EngineerLevel.SERVICE_FIELD,
                source_file="test.pdf",
            ),
        ]
        result = calculate_invoice(entries, _make_po())
        # Grand total = sum of all engineer totals
        individual_sum = sum(b.total_cost for b in result.engineer_blocks)
        assert result.grand_total == individual_sum
