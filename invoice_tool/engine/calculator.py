"""Layer 4 — Financial Calculation Engine.

All monetary calculations done in Python with Decimal precision.
Excel only receives final verified numbers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from invoice_tool.models import (
    Category,
    EngineerBlock,
    InvoiceResult,
    POData,
    StrictValidationError,
    TimesheetEntry,
)


def calculate_invoice(
    entries: list[TimesheetEntry],
    po_data: POData,
) -> InvoiceResult:
    """Build InvoiceResult with all financial calculations done in Python."""
    errors: list[str] = []

    # Group entries by engineer
    by_engineer: dict[str, list[TimesheetEntry]] = defaultdict(list)
    for entry in entries:
        by_engineer[entry.engineer_name].append(entry)

    engineer_blocks: list[EngineerBlock] = []

    for name, eng_entries in sorted(by_engineer.items()):
        # All entries for one engineer should have the same category and level
        categories = {e.category for e in eng_entries}
        levels = {e.engineer_level for e in eng_entries}

        if len(categories) > 1:
            errors.append(f"Engineer {name} has mixed categories: {categories}")
        if len(levels) > 1:
            errors.append(f"Engineer {name} has mixed levels: {levels}")

        category = eng_entries[0].category
        level = eng_entries[0].engineer_level

        # Look up rates
        rates_dict = po_data.onshore_rates if category == Category.ONSHORE else po_data.offshore_rates
        if level not in rates_dict:
            errors.append(f"No rates for {name} ({category.value}, {level.value})")
            continue

        rate_set = rates_dict[level]

        # Aggregate entries by date (in case same engineer has multiple entries per day)
        by_date: dict[date, TimesheetEntry] = {}
        for entry in sorted(eng_entries, key=lambda e: e.date):
            if entry.date in by_date:
                existing = by_date[entry.date]
                by_date[entry.date] = TimesheetEntry(
                    engineer_name=name,
                    date=entry.date,
                    normal_hours=existing.normal_hours + entry.normal_hours,
                    ot_hours=existing.ot_hours + entry.ot_hours,
                    hot_hours=existing.hot_hours + entry.hot_hours,
                    category=category,
                    engineer_level=level,
                    source_file=f"{existing.source_file}; {entry.source_file}",
                )
            else:
                by_date[entry.date] = entry

        block = EngineerBlock(
            name=name,
            category=category,
            engineer_level=level,
            entries=list(by_date.values()),
            normal_rate=rate_set.normal,
            ot_rate=rate_set.ot,
            hot_rate=rate_set.hot,
        )

        engineer_blocks.append(block)

    if errors:
        raise StrictValidationError(errors)

    # Collect all unique dates
    all_dates = sorted({e.date for entry_list in by_engineer.values() for e in entry_list})

    result = InvoiceResult(
        po_data=po_data,
        engineer_blocks=engineer_blocks,
        all_dates=all_dates,
    )

    # --- Final reconciliation ---
    # Verify grand total = sum of all engineer totals
    individual_sum = sum((b.total_cost for b in engineer_blocks), Decimal("0"))
    if individual_sum != result.grand_total:
        errors.append(
            f"Grand total mismatch: sum of engineers={individual_sum} vs computed={result.grand_total}"
        )

    # Verify hour totals
    total_normal = sum((b.total_normal_hours for b in engineer_blocks), Decimal("0"))
    total_ot = sum((b.total_ot_hours for b in engineer_blocks), Decimal("0"))
    total_hot = sum((b.total_hot_hours for b in engineer_blocks), Decimal("0"))

    if total_normal != result.total_normal_hours:
        errors.append(f"Normal hours mismatch: {total_normal} vs {result.total_normal_hours}")
    if total_ot != result.total_ot_hours:
        errors.append(f"OT hours mismatch: {total_ot} vs {result.total_ot_hours}")
    if total_hot != result.total_hot_hours:
        errors.append(f"HOT hours mismatch: {total_hot} vs {result.total_hot_hours}")

    if errors:
        raise StrictValidationError(errors)

    return result
