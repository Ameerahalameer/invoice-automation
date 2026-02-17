"""Tests for PO/Contract PDF parser."""

import pytest
from pathlib import Path
from decimal import Decimal

from invoice_tool.parsers.po_parser import parse_po_pdf
from invoice_tool.models import EngineerLevel

BASE_DIR = Path(__file__).parent.parent

PO_PDF = BASE_DIR / "Contract No. 1535984.pdf"


@pytest.mark.skipif(not PO_PDF.exists(), reason="PO PDF not available")
class TestPOParser:
    def test_contract_number(self):
        po = parse_po_pdf(PO_PDF)
        assert po.contract_number == "1535984"

    def test_onshore_rates_complete(self):
        po = parse_po_pdf(PO_PDF)
        assert EngineerLevel.PRINCIPAL in po.onshore_rates
        assert EngineerLevel.SENIOR_LEAD in po.onshore_rates
        assert EngineerLevel.SERVICE_FIELD in po.onshore_rates

    def test_offshore_rates_complete(self):
        po = parse_po_pdf(PO_PDF)
        assert EngineerLevel.PRINCIPAL in po.offshore_rates
        assert EngineerLevel.SENIOR_LEAD in po.offshore_rates
        assert EngineerLevel.SERVICE_FIELD in po.offshore_rates

    def test_onshore_service_field_rates(self):
        po = parse_po_pdf(PO_PDF)
        rates = po.onshore_rates[EngineerLevel.SERVICE_FIELD]
        assert rates.normal == Decimal("286")
        assert rates.ot == Decimal("372")
        assert rates.hot == Decimal("443")

    def test_offshore_service_field_rates(self):
        po = parse_po_pdf(PO_PDF)
        rates = po.offshore_rates[EngineerLevel.SERVICE_FIELD]
        assert rates.normal == Decimal("372")
        assert rates.ot == Decimal("484")
        assert rates.hot == Decimal("577")

    def test_onshore_principal_rates(self):
        po = parse_po_pdf(PO_PDF)
        rates = po.onshore_rates[EngineerLevel.PRINCIPAL]
        assert rates.normal == Decimal("381")
        assert rates.ot == Decimal("495")
        assert rates.hot == Decimal("591")

    def test_offshore_senior_lead_rates(self):
        po = parse_po_pdf(PO_PDF)
        rates = po.offshore_rates[EngineerLevel.SENIOR_LEAD]
        assert rates.normal == Decimal("421")
        assert rates.ot == Decimal("547")
        assert rates.hot == Decimal("653")

    def test_hours_per_day(self):
        po = parse_po_pdf(PO_PDF)
        assert po.onshore_hours_per_day == 10
        assert po.offshore_hours_per_day == 12

    def test_max_amount(self):
        po = parse_po_pdf(PO_PDF)
        assert po.max_amount_usd == Decimal("131000")
