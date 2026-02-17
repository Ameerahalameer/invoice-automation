"""Hours splitting logic based on Saudi work week conventions.

Business Rules (derived from template analysis):
- Sunday through Thursday: Normal working days
  - First N hours (standing_hours_per_day) = Normal
  - Remaining hours = OT (Work Week Overtime)
- Friday: Holiday/Weekend
  - All hours = HOT (Weekend/Public Holiday)
- Saturday: Weekend
  - For Offshore: All hours = OT (Work Week Overtime)
  - For Onshore: All hours = OT (Work Week Overtime)

Standing hours per day:
- Onshore: 10 hours (8 site + 2 travel)
- Offshore: 12 hours
"""

from __future__ import annotations

from decimal import Decimal

from invoice_tool.models import Category, TimesheetEntry


def split_hours(
    entry: TimesheetEntry,
    standing_hours: int,
) -> TimesheetEntry:
    """Split raw total hours into Normal/OT/HOT based on day of week.

    If the entry already has a meaningful OT/HOT split from the PDF
    (i.e., the PDF explicitly provides columns for Regular/OT/HOT),
    we respect that split and return as-is.

    For Format B timesheets where all hours are lumped into "Normal"
    (HOURS ON SITE + A), we need to apply the split.
    """
    total = entry.normal_hours + entry.ot_hours + entry.hot_hours

    if total == Decimal("0"):
        return entry

    # If the PDF already provided a meaningful split (OT or HOT > 0), keep it
    if entry.ot_hours > 0 or entry.hot_hours > 0:
        return entry

    # All hours are in normal_hours — need to split
    day_of_week = entry.date.weekday()  # Monday=0, Sunday=6
    # Saudi convention: Sunday=6 is working day, Friday=4 is holiday, Saturday=5 is weekend

    standing = Decimal(str(standing_hours))

    if day_of_week == 4:  # Friday
        # All hours are HOT (Weekend/Public Holiday)
        return TimesheetEntry(
            engineer_name=entry.engineer_name,
            date=entry.date,
            normal_hours=Decimal("0"),
            ot_hours=Decimal("0"),
            hot_hours=total,
            category=entry.category,
            engineer_level=entry.engineer_level,
            source_file=entry.source_file,
        )
    elif day_of_week == 5:  # Saturday
        # All hours are OT (Work Week Overtime)
        return TimesheetEntry(
            engineer_name=entry.engineer_name,
            date=entry.date,
            normal_hours=Decimal("0"),
            ot_hours=total,
            hot_hours=Decimal("0"),
            category=entry.category,
            engineer_level=entry.engineer_level,
            source_file=entry.source_file,
        )
    else:
        # Sunday through Thursday: Normal working days
        # First `standing` hours are Normal, rest is OT
        normal = min(total, standing)
        ot = total - normal

        return TimesheetEntry(
            engineer_name=entry.engineer_name,
            date=entry.date,
            normal_hours=normal,
            ot_hours=ot,
            hot_hours=Decimal("0"),
            category=entry.category,
            engineer_level=entry.engineer_level,
            source_file=entry.source_file,
        )


def apply_hours_split(
    entries: list[TimesheetEntry],
    onshore_standing: int = 10,
    offshore_standing: int = 12,
) -> list[TimesheetEntry]:
    """Apply hours splitting to all entries based on their category."""
    result = []
    for entry in entries:
        standing = offshore_standing if entry.category == Category.OFFSHORE else onshore_standing
        result.append(split_hours(entry, standing))
    return result
