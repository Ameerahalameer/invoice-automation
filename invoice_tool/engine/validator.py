"""Layer 3 — Strict Validation Engine.

Validates all extracted data before financial calculations.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from invoice_tool.models import (
    Category,
    EngineerLevel,
    POData,
    StrictValidationError,
    TimesheetEntry,
)


def validate_entries(
    entries: list[TimesheetEntry],
    po_data: POData,
) -> list[TimesheetEntry]:
    """Validate all timesheet entries against PO data.

    In strict mode, ANY warning is treated as an error and stops processing.
    Returns the validated entries if all checks pass.
    """
    errors: list[str] = []

    if not entries:
        errors.append("No timesheet entries extracted from any PDF")
        raise StrictValidationError(errors)

    # --- Per-entry validation ---
    for entry in entries:
        # No negative hours
        if entry.normal_hours < 0:
            errors.append(
                f"{entry.engineer_name} on {entry.date}: negative normal_hours={entry.normal_hours} "
                f"(source: {entry.source_file})"
            )
        if entry.ot_hours < 0:
            errors.append(
                f"{entry.engineer_name} on {entry.date}: negative ot_hours={entry.ot_hours} "
                f"(source: {entry.source_file})"
            )
        if entry.hot_hours < 0:
            errors.append(
                f"{entry.engineer_name} on {entry.date}: negative hot_hours={entry.hot_hours} "
                f"(source: {entry.source_file})"
            )

        # No hours > 24 per day per entry
        if entry.total_hours > 24:
            errors.append(
                f"{entry.engineer_name} on {entry.date}: total hours={entry.total_hours} > 24 "
                f"(source: {entry.source_file})"
            )

        # Hours must be numeric (guaranteed by Decimal type, but check for NaN-like)
        for attr in ("normal_hours", "ot_hours", "hot_hours"):
            val = getattr(entry, attr)
            if not val.is_finite():
                errors.append(
                    f"{entry.engineer_name} on {entry.date}: {attr} is not finite "
                    f"(source: {entry.source_file})"
                )

    # --- Per-engineer-per-date aggregation validation ---
    daily_totals: dict[tuple[str, object], Decimal] = defaultdict(Decimal)
    for entry in entries:
        key = (entry.engineer_name, entry.date)
        daily_totals[key] += entry.total_hours

    for (name, dt), total in daily_totals.items():
        if total > 24:
            errors.append(
                f"{name} on {dt}: aggregated daily total={total} > 24 across all source files"
            )

    # --- Rate availability validation ---
    engineer_categories: set[tuple[Category, EngineerLevel]] = set()
    for entry in entries:
        engineer_categories.add((entry.category, entry.engineer_level))

    for category, level in engineer_categories:
        rates = po_data.onshore_rates if category == Category.ONSHORE else po_data.offshore_rates
        if level not in rates:
            errors.append(
                f"No {category.value} rates found for engineer level {level.value} in PO"
            )

    # --- Source file traceability ---
    source_files = {entry.source_file for entry in entries}
    if not source_files:
        errors.append("No source files recorded in entries")

    if errors:
        raise StrictValidationError(errors)

    return entries
