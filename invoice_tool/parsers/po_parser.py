"""Layer 1 — PO/Contract PDF Parser.

Extracts contract number, onshore/offshore hourly rates for three engineer levels.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from invoice_tool.models import (
    Category,
    EngineerLevel,
    POData,
    RateSet,
    StrictValidationError,
)


def parse_po_pdf(pdf_path: str | Path) -> POData:
    """Parse a PO/Contract PDF and extract rates.

    The price list is expected on the last page (Attachment 2 - Price List).
    It contains two sections: A (Onshore) and B (Offshore), each with
    12 numbered rows (items 1-12).  Items 4-12 are hourly rates.
    """
    pdf_path = Path(pdf_path)
    errors: list[str] = []

    contract_number: str | None = None
    onshore_rates: dict[EngineerLevel, RateSet] = {}
    offshore_rates: dict[EngineerLevel, RateSet] = {}
    onshore_hours_per_day: int = 10  # default from contract
    offshore_hours_per_day: int = 12
    max_amount: Decimal | None = None

    with pdfplumber.open(str(pdf_path)) as pdf:
        # --- Extract contract number from page 1 ---
        first_page_text = pdf.pages[0].extract_text() or ""
        cn_match = re.search(r'ContractNo[.\s]*(\d{7})', first_page_text)
        if cn_match:
            contract_number = cn_match.group(1)
        else:
            errors.append("Contract number not found on page 1")

        # --- Extract max amount ---
        for page in pdf.pages[:4]:
            page_text = page.extract_text() or ""
            amt_match = re.search(r'MaximumAmount\s+([\d,]+\.\d{2})\s*USD', page_text)
            if amt_match:
                max_amount = Decimal(amt_match.group(1).replace(",", ""))
                break

        if max_amount is None:
            errors.append("Maximum contract amount not found")
            max_amount = Decimal("0")

        # --- Find and parse the price list page ---
        price_page = None
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if "Attachment 2 - Price List" in page_text or "Price List" in page_text:
                if "Unit Rate" in page_text:
                    price_page = page
                    break

        if price_page is None:
            errors.append("Price List page (Attachment 2) not found in PDF")
            raise StrictValidationError(errors)

        tables = price_page.extract_tables()
        if not tables:
            errors.append("No tables found on Price List page")
            raise StrictValidationError(errors)

        # Find the main price table (the one with 'No' and 'Unit' headers)
        price_table = None
        for table in tables:
            for row in table:
                if row and row[0] and 'No' in str(row[0]) and any(c and 'Unit' in str(c) for c in row):
                    price_table = table
                    break
            if price_table:
                break

        if price_table is None:
            errors.append("Price table with headers not found")
            raise StrictValidationError(errors)

        # Parse the price table rows
        onshore_hourly: dict[int, Decimal] = {}
        offshore_hourly: dict[int, Decimal] = {}
        current_section: str | None = None

        for row in price_table:
            if not row or not row[0]:
                continue

            item_id = str(row[0]).strip()
            item_desc = str(row[2]).strip() if len(row) > 2 and row[2] else ""
            rate_str = str(row[-1]).strip() if row[-1] else ""

            # Detect section headers
            if item_id == 'A' and 'Onshore' in item_desc:
                current_section = 'onshore'
                # Extract hours per day
                hrs_match = re.search(r'\((\d+)\s*hours', item_desc)
                if hrs_match:
                    onshore_hours_per_day = int(hrs_match.group(1))
                continue
            elif item_id == 'B' and 'Offshore' in item_desc:
                current_section = 'offshore'
                hrs_match = re.search(r'\((\d+)\s*hours', item_desc)
                if hrs_match:
                    offshore_hours_per_day = int(hrs_match.group(1))
                continue

            # Parse hourly rate items (numbered 4-12 with unit HR)
            if current_section and item_id.isdigit():
                item_num = int(item_id)
                unit = str(row[1]).strip() if len(row) > 1 and row[1] else ""

                if unit == 'HR' and item_num >= 4:
                    try:
                        rate = Decimal(rate_str.replace(",", ""))
                    except (InvalidOperation, ValueError):
                        errors.append(f"Non-numeric rate for {current_section} item {item_num}: '{rate_str}'")
                        continue

                    if current_section == 'onshore':
                        onshore_hourly[item_num] = rate
                    else:
                        offshore_hourly[item_num] = rate

        # Map item numbers to engineer levels and rate types
        # Items 4,7,10 = Principal; 5,8,11 = Senior/Lead; 6,9,12 = Service/Field
        # Items 4-6 = Normal; 7-9 = OT; 10-12 = HOT
        level_map = {
            4: EngineerLevel.PRINCIPAL,
            5: EngineerLevel.SENIOR_LEAD,
            6: EngineerLevel.SERVICE_FIELD,
            7: EngineerLevel.PRINCIPAL,
            8: EngineerLevel.SENIOR_LEAD,
            9: EngineerLevel.SERVICE_FIELD,
            10: EngineerLevel.PRINCIPAL,
            11: EngineerLevel.SENIOR_LEAD,
            12: EngineerLevel.SERVICE_FIELD,
        }

        def build_rates(hourly_dict: dict[int, Decimal], section: str) -> dict[EngineerLevel, RateSet]:
            rates: dict[EngineerLevel, RateSet] = {}
            for level in EngineerLevel:
                # Find normal, ot, hot items for this level
                level_items = {n: level_map[n] for n in level_map if level_map[n] == level}
                normal_items = [n for n in level_items if 4 <= n <= 6]
                ot_items = [n for n in level_items if 7 <= n <= 9]
                hot_items = [n for n in level_items if 10 <= n <= 12]

                normal_num = normal_items[0] if normal_items else None
                ot_num = ot_items[0] if ot_items else None
                hot_num = hot_items[0] if hot_items else None

                missing = []
                if normal_num not in hourly_dict:
                    missing.append(f"Normal (item {normal_num})")
                if ot_num not in hourly_dict:
                    missing.append(f"OT (item {ot_num})")
                if hot_num not in hourly_dict:
                    missing.append(f"HOT (item {hot_num})")

                if missing:
                    errors.append(f"{section} {level.value}: missing rates for {', '.join(missing)}")
                    continue

                rates[level] = RateSet(
                    normal=hourly_dict[normal_num],
                    ot=hourly_dict[ot_num],
                    hot=hourly_dict[hot_num],
                )
            return rates

        onshore_rates = build_rates(onshore_hourly, "Onshore")
        offshore_rates = build_rates(offshore_hourly, "Offshore")

    # Validate completeness
    if not contract_number:
        errors.append("Contract number could not be extracted")

    for level in EngineerLevel:
        if level not in onshore_rates:
            errors.append(f"Missing onshore rates for {level.value}")
        if level not in offshore_rates:
            errors.append(f"Missing offshore rates for {level.value}")

    if errors:
        raise StrictValidationError(errors)

    return POData(
        contract_number=contract_number,  # type: ignore[arg-type]
        onshore_rates=onshore_rates,
        offshore_rates=offshore_rates,
        onshore_hours_per_day=onshore_hours_per_day,
        offshore_hours_per_day=offshore_hours_per_day,
        max_amount_usd=max_amount,
        source_file=str(pdf_path),
    )
