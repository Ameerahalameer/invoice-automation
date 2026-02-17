"""Tests for timesheet PDF parsers (Format A and Format B)."""

import pytest
from pathlib import Path
from decimal import Decimal
from datetime import date

from invoice_tool.parsers.timesheet_parser import parse_timesheet_pdf
from invoice_tool.models import Category, EngineerLevel

BASE_DIR = Path(__file__).parent.parent

# Format A
SURAJ_PDF = BASE_DIR / "Suraj Negi Timesheet TP2_signed.pdf"

# Format B
ATIF_PDF = BASE_DIR / "Atif_Onshore_EMERSON_time_sheet_30_Dec_2025_QATIF_GOSP01signed.pdf"
ANKIT_PDF = BASE_DIR / "LTA138_BVS_Onshore_TS_Signed_Emerson_Ankit_Modi_20_25_Jan_2021.pdf"

ENGINEER_CONFIG = {
    "SURAJ NEGI": (Category.OFFSHORE, EngineerLevel.SERVICE_FIELD),
    "Suraj Negi": (Category.OFFSHORE, EngineerLevel.SERVICE_FIELD),
    "Atif": (Category.ONSHORE, EngineerLevel.SERVICE_FIELD),
    "Ankit Modi": (Category.ONSHORE, EngineerLevel.SERVICE_FIELD),
}


@pytest.mark.skipif(not SURAJ_PDF.exists(), reason="Suraj timesheet not available")
class TestFormatA:
    def test_parse_suraj(self):
        entries = parse_timesheet_pdf(SURAJ_PDF, ENGINEER_CONFIG)
        assert len(entries) == 11  # 11 days of work

    def test_suraj_name(self):
        entries = parse_timesheet_pdf(SURAJ_PDF, ENGINEER_CONFIG)
        assert all(e.engineer_name == "SURAJ NEGI" for e in entries)

    def test_suraj_total_hours(self):
        entries = parse_timesheet_pdf(SURAJ_PDF, ENGINEER_CONFIG)
        total = sum(e.total_hours for e in entries)
        assert total == Decimal("132")

    def test_suraj_category(self):
        entries = parse_timesheet_pdf(SURAJ_PDF, ENGINEER_CONFIG)
        assert all(e.category == Category.OFFSHORE for e in entries)

    def test_suraj_first_day(self):
        entries = parse_timesheet_pdf(SURAJ_PDF, ENGINEER_CONFIG)
        first = sorted(entries, key=lambda e: e.date)[0]
        assert first.date == date(2026, 1, 10)
        # First day: 6h travel + 6h regular = 12h normal
        assert first.normal_hours == Decimal("12")
        assert first.ot_hours == Decimal("0")
        assert first.hot_hours == Decimal("0")

    def test_no_negative_hours(self):
        entries = parse_timesheet_pdf(SURAJ_PDF, ENGINEER_CONFIG)
        for e in entries:
            assert e.normal_hours >= 0
            assert e.ot_hours >= 0
            assert e.hot_hours >= 0


@pytest.mark.skipif(not ATIF_PDF.exists(), reason="Atif timesheet not available")
class TestFormatB_Atif:
    def test_parse_atif(self):
        entries = parse_timesheet_pdf(ATIF_PDF, ENGINEER_CONFIG)
        assert len(entries) >= 1

    def test_atif_category(self):
        entries = parse_timesheet_pdf(ATIF_PDF, ENGINEER_CONFIG)
        assert all(e.category == Category.ONSHORE for e in entries)


@pytest.mark.skipif(not ANKIT_PDF.exists(), reason="Ankit timesheet not available")
class TestFormatB_Ankit:
    def test_parse_ankit(self):
        entries = parse_timesheet_pdf(ANKIT_PDF, ENGINEER_CONFIG)
        assert len(entries) >= 1

    def test_ankit_category(self):
        entries = parse_timesheet_pdf(ANKIT_PDF, ENGINEER_CONFIG)
        assert all(e.category == Category.ONSHORE for e in entries)

    def test_ankit_name(self):
        entries = parse_timesheet_pdf(ANKIT_PDF, ENGINEER_CONFIG)
        assert all(e.engineer_name == "Ankit Modi" for e in entries)
