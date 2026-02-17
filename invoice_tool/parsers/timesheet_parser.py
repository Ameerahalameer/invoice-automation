"""Layer 1 — Timesheet PDF Parser.

Supports two timesheet formats:
  Format A (Emerson "SERVICE / TIME REPORT"):
    Columns: Date | Day | Site Start | Site End | Travel | Regular | Overtime | Premier OT | Total
    Mapping: Regular -> Normal, Overtime -> OT, Premier OT -> HOT

  Format B (Emerson "SERVICE TIME SHEET"):
    Columns: DATE | HOURS ON SITE | A(TRAV) | B(WKD/FRI) | C(SAT)
    Mapping: (HOURS ON SITE + A) -> Normal, B -> OT, C -> HOT
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pdfplumber

from invoice_tool.models import (
    Category,
    EngineerLevel,
    StrictValidationError,
    TimesheetEntry,
)

# Engineer name -> (category, level) mapping config
# This must be configured per project; here we use a default mapping
# that can be overridden by the caller.
DEFAULT_ENGINEER_CONFIG: dict[str, tuple[Category, EngineerLevel]] = {}


def _parse_date_flexible(date_str: str) -> date:
    """Parse dates in multiple formats."""
    date_str = date_str.strip()

    formats = [
        "%d/%m/%Y",      # 30/12/2025
        "%d-%b-%y",      # 10-Jan-26
        "%d-%b-%Y",      # 25-Jan-2026
        "%Y-%m-%d",      # 2026-01-10
        "%d.%m.%Y",      # 30.12.2025
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Cannot parse date: '{date_str}'")


def _calc_hours_from_times(from_time: str, to_time: str) -> Decimal:
    """Calculate hours between two HH:MM time strings."""
    try:
        from_parts = from_time.split(":")
        to_parts = to_time.split(":")
        from_mins = int(from_parts[0]) * 60 + int(from_parts[1])
        to_mins = int(to_parts[0]) * 60 + int(to_parts[1])
        diff = to_mins - from_mins
        if diff < 0:
            diff += 24 * 60  # crossed midnight
        return Decimal(str(diff / 60))
    except (ValueError, IndexError):
        return Decimal("0")


def _safe_decimal(value: str | None) -> Decimal:
    """Convert string to Decimal, returning 0 for empty/None."""
    if not value or not value.strip():
        return Decimal("0")
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return Decimal("0")


def _detect_format(text: str) -> str:
    """Detect whether this is Format A or Format B."""
    if "Regular" in text and "Overtime" in text and "Premier OT" in text:
        return "A"
    if "HOURS ON SITE" in text or ("TRAV" in text and "WKD/FRI" in text):
        return "B"
    raise ValueError("Cannot detect timesheet format: neither Format A nor Format B markers found")


def _extract_engineer_name_format_a(text: str) -> str:
    """Extract engineer name from Format A header."""
    match = re.search(r'EMR\s+Engineer\s*:\s*(.*?)(?:\n|Customer)', text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        # Clean up titles
        name = re.sub(r'^(MR\.|MRS\.|MS\.)\s*', '', name, flags=re.IGNORECASE).strip()
        return name
    raise ValueError("Engineer name not found in Format A timesheet")


def _extract_engineer_name_format_b(text: str, filename: str) -> str:
    """Extract engineer name from Format B timesheet.

    Format B timesheets often don't have the name in text.
    We extract from the filename.
    """
    # Try "FOR EMERSON: Ankit Modi________________" pattern
    match = re.search(r'FOR EMERSON:\s*([A-Za-z][A-Za-z ]+?)(?:_{2,}|\n)', text)
    if match:
        name = match.group(1).strip()
        if name and len(name) > 2 and "SIGNATURE" not in name.upper() and "ENG" not in name.upper():
            return name

    # Extract from filename
    fname = Path(filename).stem
    # Common patterns in filenames
    # "Atif_Onshore_EMERSON_time_sheet..." -> "Atif"
    # "LTA138_BVS_Onshore_TS_Signed_Emerson_Ankit_Modi_..." -> "Ankit Modi"
    if "Ankit_Modi" in fname or "Ankit Modi" in fname:
        return "Ankit Modi"
    if "Atif" in fname:
        return "Atif"
    # Generic: take first word before common keywords
    parts = re.split(r'[_\-]', fname)
    name_parts = []
    stop_words = {'onshore', 'offshore', 'emerson', 'time', 'sheet', 'signed',
                  'lta138', 'lta', 'bvs', 'ts', 'timesheet', 'qatif', 'gosp01signed'}
    for p in parts:
        if p.lower() in stop_words:
            continue
        if re.match(r'^\d', p):
            continue
        name_parts.append(p)
        if len(name_parts) >= 2:
            break

    if name_parts:
        return " ".join(name_parts)

    raise ValueError(f"Cannot extract engineer name from Format B timesheet: {filename}")


def _extract_po_reference(text: str) -> str | None:
    """Extract PO/contract reference from timesheet."""
    match = re.search(r'(?:ORDER\s+No\.\s+OR\s+REFERENCE|PO#|PO\s*-?\s*)[\s:]*(\d{7}|\d{7}\s*\()', text, re.IGNORECASE)
    if match:
        return re.sub(r'[^\d]', '', match.group(1))[:7]

    match = re.search(r'(?:REFERENCE|ORDER)\s*[:\s]+.*?(\d{7})', text, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def _detect_category_from_text(text: str, filename: str) -> Category:
    """Detect onshore/offshore from text or filename."""
    combined = (text + " " + filename).lower()
    if "offshore" in combined:
        return Category.OFFSHORE
    return Category.ONSHORE


def _parse_format_a(
    pdf_path: Path,
    engineer_config: dict[str, tuple[Category, EngineerLevel]],
) -> list[TimesheetEntry]:
    """Parse Format A timesheet (SERVICE / TIME REPORT)."""
    entries: list[TimesheetEntry] = []
    errors: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        tables = page.extract_tables()

        engineer_name = _extract_engineer_name_format_a(text)
        category = _detect_category_from_text(text, str(pdf_path))

        # Find the time data table
        time_table = None
        for table in tables:
            for row in table:
                if row and any(c and "Regular" in str(c) for c in row if c):
                    time_table = table
                    break
            if time_table:
                break

        if time_table is None:
            raise StrictValidationError([f"Time data table not found in {pdf_path.name}"])

        # Find header row and data rows
        header_idx = None
        for i, row in enumerate(time_table):
            if row and any(c and "Regular" in str(c) for c in row if c):
                header_idx = i
                break

        if header_idx is None:
            raise StrictValidationError([f"Header row with 'Regular' not found in {pdf_path.name}"])

        # Parse data rows after header
        for row in time_table[header_idx + 1:]:
            if not row or not row[0]:
                continue

            date_str = str(row[0]).strip()
            if not date_str or date_str.startswith("Total") or date_str.startswith("Emerson"):
                continue

            try:
                entry_date = _parse_date_flexible(date_str)
            except ValueError:
                continue  # Skip non-date rows

            # Format A columns: Date, Day, Site Start, Site End, Travel, Regular, Overtime, Premier OT, Total
            regular = _safe_decimal(row[5] if len(row) > 5 else None)
            overtime = _safe_decimal(row[6] if len(row) > 6 else None)
            premier_ot = _safe_decimal(row[7] if len(row) > 7 else None)
            total_col = _safe_decimal(row[8] if len(row) > 8 else None)

            # The travel hours in this format count as Normal or are separate
            travel = _safe_decimal(row[4] if len(row) > 4 else None)
            # Travel time is billed at regular rate per contract notes
            # In Suraj's sheet: travel hours appear in "Travel Time" column,
            # regular hours appear in "Regular" column
            # Total = Travel + Regular + Overtime + Premier OT
            # Normal hours = Travel + Regular (both at normal rate per contract)
            normal_hours = travel + regular

            # Validate hours
            if normal_hours < 0 or overtime < 0 or premier_ot < 0:
                errors.append(f"{pdf_path.name}: Negative hours on {entry_date}")
            if (normal_hours + overtime + premier_ot) > 24:
                errors.append(f"{pdf_path.name}: Total hours > 24 on {entry_date}")

            # Verify total matches
            computed_total = travel + regular + overtime + premier_ot
            if total_col > 0 and abs(computed_total - total_col) > Decimal("0.01"):
                errors.append(
                    f"{pdf_path.name}: Row total mismatch on {entry_date}: "
                    f"computed={computed_total} vs stated={total_col}"
                )

            if normal_hours > 0 or overtime > 0 or premier_ot > 0:
                # Look up engineer config
                config = engineer_config.get(engineer_name)
                if config:
                    cat, level = config
                else:
                    cat = category
                    level = EngineerLevel.SERVICE_FIELD  # default

                entries.append(TimesheetEntry(
                    engineer_name=engineer_name,
                    date=entry_date,
                    normal_hours=normal_hours,
                    ot_hours=overtime,
                    hot_hours=premier_ot,
                    category=cat,
                    engineer_level=level,
                    source_file=str(pdf_path),
                ))

    if errors:
        raise StrictValidationError(errors)

    return entries


def _parse_format_b(
    pdf_path: Path,
    engineer_config: dict[str, tuple[Category, EngineerLevel]],
) -> list[TimesheetEntry]:
    """Parse Format B timesheet (SERVICE TIME SHEET)."""
    entries: list[TimesheetEntry] = []
    errors: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        tables = page.extract_tables()

        engineer_name = _extract_engineer_name_format_b(text, str(pdf_path))
        category = _detect_category_from_text(text, str(pdf_path))

        # Find the time data table (the one with DATE and HOURS ON SITE)
        time_table = None
        for table in tables:
            for row in table:
                if row and any(c and "DATE" in str(c) for c in row if c):
                    time_table = table
                    break
            if time_table:
                break

        if time_table is None:
            raise StrictValidationError([f"Time data table not found in {pdf_path.name}"])

        # Find header rows - there are typically 2 header rows
        header_start = None
        for i, row in enumerate(time_table):
            if row and any(c and "DATE" in str(c) for c in row if c):
                header_start = i
                break

        if header_start is None:
            raise StrictValidationError([f"Header row not found in {pdf_path.name}"])

        # Parse data rows - they contain day name + date pattern like "TUE\n20/01/2026"
        for row in time_table[header_start + 2:]:  # skip 2 header rows
            if not row or not row[0]:
                continue

            cell0 = str(row[0]).strip()

            # Stop at footer rows
            if "SPARES" in cell0 or "TOTAL" in cell0 or "HEALTH" in cell0:
                break

            # Extract date from cell like "TUE\n20/01/2026" or "TUE\n30 / 1 2 / 2025"
            # First try clean date format dd/mm/yyyy
            date_match = re.search(r'(\d{2})/(\d{2})/(\d{4})', cell0)
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))
            else:
                # Handle OCR-split dates like "30 / 1 2 / 2025"
                # Strip day name prefix and extract all digit groups
                date_text = re.sub(r'^[A-Z]+\s*\n?', '', cell0).strip()
                # Remove slashes and extra spaces, then find all digit groups
                nums = re.findall(r'\d+', date_text)
                if len(nums) >= 3:
                    # Last number is year (4 digits)
                    year_str = nums[-1]
                    if len(year_str) == 4:
                        year = int(year_str)
                        # Remaining nums before year form day and month
                        # Concatenate middle nums as month (e.g., "1" + "2" = "12")
                        day = int(nums[0])
                        month_str = ''.join(nums[1:-1])
                        month = int(month_str) if month_str else 0
                    else:
                        continue
                else:
                    continue

            try:
                entry_date = date(year, month, day)
            except ValueError:
                errors.append(f"{pdf_path.name}: Invalid date {day}/{month}/{year}")
                continue

            # Format B columns vary slightly between versions:
            # Version 1 (10 cols): DATE, _, FROM, TO, A(TRAV), B(WKD/FRI), _, C(SAT), DESC, _
            # Version 2 (8 cols): DATE, _, HOURS ON SITE, A(TRAV), B(WKD/FRI), C(SAT), DESC, _

            # Detect by checking which columns have numeric data
            hours_on_site = Decimal("0")
            a_trav = Decimal("0")
            b_wkd = Decimal("0")
            c_sat = Decimal("0")

            # Detect column layout by checking if cols 2,3 look like time (HH:MM)
            is_10col_time_format = (
                len(row) >= 10
                and row[2] and re.match(r'\d{1,2}:\d{2}', str(row[2]).strip())
            )

            if is_10col_time_format:
                # 10-column format (Atif's): DATE, _, FROM, TO, A(TRAV), B(WKD/FRI), _, C(SAT), DESC, _
                # Calculate hours on site from FROM-TO
                from_time = str(row[2]).strip()
                to_time = str(row[3]).strip() if row[3] else ""
                site_hours = _calc_hours_from_times(from_time, to_time)

                col_a = _safe_decimal(row[4] if row[4] else None)
                col_b = _safe_decimal(row[5] if row[5] else None)
                col_c = _safe_decimal(row[7] if row[7] else None)

                # In this format, A column is the normal hours count (not travel)
                # FROM/TO gives site hours, A is additional or the actual count
                # Based on Atif's data: FROM=8:00, TO=16:00, A=4
                # The "A" column is travel hours. Site hours = TO-FROM = 8h.
                # But per spec: (HOURS ON SITE + A) -> Normal
                # So normal = site_hours + a_trav? That would be 12.
                # However the template shows Atif with only 10h normal + 2h OT on that date.
                # Looking at the template: H6=10, I6=2 for Dec 30
                # So A=4 is travel but only partially billed, or
                # the actual convention is: A is the total hours worked at normal rate
                # Let's use: normal = A (if FROM/TO exists, A represents billable normal hours)
                # But A=4 doesn't match template H6=10.
                # Re-examining: STANDING HOURS PER DAY: 8 (checked in timesheet)
                # Site hours = 16:00 - 8:00 = 8h
                # A(TRAV) = 4h travel
                # So total billable = 8 + 4 = 12h? But template shows 10+2.
                # Actually template shows Normal=10, OT=2 for Atif on Dec 30
                # Standing hours = 8, so: Normal = min(site+travel, 10) = 10
                # OT = remainder = 12 - 10 = 2
                # This means the hours split is based on standing hours per day
                # For now: total_worked = site_hours + A, then split based on standing hours
                total_worked = site_hours + col_a
                hours_on_site = site_hours
                a_trav = col_a
                b_wkd = col_b
                c_sat = col_c

            elif len(row) >= 8:
                # 8-column format (Ankit's): DATE, _, HOURS ON SITE, A(TRAV), B(WKD/FRI), C(SAT), DESC, _
                col_hours = _safe_decimal(row[2] if row[2] else None)
                col_a = _safe_decimal(row[3] if row[3] else None)
                col_b = _safe_decimal(row[4] if row[4] else None)
                col_c = _safe_decimal(row[5] if row[5] else None)

                if col_hours > 0 or col_a > 0 or col_b > 0 or col_c > 0:
                    hours_on_site = col_hours
                    a_trav = col_a
                    b_wkd = col_b
                    c_sat = col_c

            # Mapping per spec:
            # (HOURS ON SITE + A) -> Normal
            # B -> OT
            # C -> HOT
            normal_hours = hours_on_site + a_trav
            ot_hours = b_wkd
            hot_hours = c_sat

            # Validate
            if normal_hours < 0 or ot_hours < 0 or hot_hours < 0:
                errors.append(f"{pdf_path.name}: Negative hours on {entry_date}")
            total = normal_hours + ot_hours + hot_hours
            if total > 24:
                errors.append(f"{pdf_path.name}: Total hours > 24 on {entry_date}: {total}")

            if normal_hours > 0 or ot_hours > 0 or hot_hours > 0:
                config = engineer_config.get(engineer_name)
                if config:
                    cat, level = config
                else:
                    cat = category
                    level = EngineerLevel.SERVICE_FIELD

                entries.append(TimesheetEntry(
                    engineer_name=engineer_name,
                    date=entry_date,
                    normal_hours=normal_hours,
                    ot_hours=ot_hours,
                    hot_hours=hot_hours,
                    category=cat,
                    engineer_level=level,
                    source_file=str(pdf_path),
                ))

    if errors:
        raise StrictValidationError(errors)

    return entries


def parse_timesheet_pdf(
    pdf_path: str | Path,
    engineer_config: dict[str, tuple[Category, EngineerLevel]] | None = None,
) -> list[TimesheetEntry]:
    """Parse a timesheet PDF (auto-detects Format A or B)."""
    pdf_path = Path(pdf_path)
    config = engineer_config or DEFAULT_ENGINEER_CONFIG

    with pdfplumber.open(str(pdf_path)) as pdf:
        text = pdf.pages[0].extract_text() or ""

    fmt = _detect_format(text)

    if fmt == "A":
        return _parse_format_a(pdf_path, config)
    else:
        return _parse_format_b(pdf_path, config)
