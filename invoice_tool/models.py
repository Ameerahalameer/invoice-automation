"""Layer 2 — Canonical Data Model for the invoice automation system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional


class Category(Enum):
    ONSHORE = "onshore"
    OFFSHORE = "offshore"


class EngineerLevel(Enum):
    PRINCIPAL = "principal"
    SENIOR_LEAD = "senior_lead"
    SERVICE_FIELD = "service_field"


@dataclass(frozen=True)
class RateSet:
    """Hourly rates for one engineer level in one category."""
    normal: Decimal
    ot: Decimal
    hot: Decimal

    def __post_init__(self) -> None:
        for name, val in [("normal", self.normal), ("ot", self.ot), ("hot", self.hot)]:
            if val <= 0:
                raise ValueError(f"Rate '{name}' must be positive, got {val}")


@dataclass(frozen=True)
class POData:
    """Extracted and validated PO/Contract data."""
    contract_number: str
    onshore_rates: dict[EngineerLevel, RateSet]
    offshore_rates: dict[EngineerLevel, RateSet]
    onshore_hours_per_day: int
    offshore_hours_per_day: int
    max_amount_usd: Decimal
    source_file: str


@dataclass
class TimesheetEntry:
    """Single day entry from a timesheet (canonical form)."""
    engineer_name: str
    date: date
    normal_hours: Decimal
    ot_hours: Decimal
    hot_hours: Decimal
    category: Category
    engineer_level: EngineerLevel
    source_file: str

    @property
    def total_hours(self) -> Decimal:
        return self.normal_hours + self.ot_hours + self.hot_hours


@dataclass
class EngineerBlock:
    """Aggregated data for one engineer ready for Excel output."""
    name: str
    category: Category
    engineer_level: EngineerLevel
    entries: list[TimesheetEntry] = field(default_factory=list)

    # Rates (set during calculation)
    normal_rate: Decimal = Decimal("0")
    ot_rate: Decimal = Decimal("0")
    hot_rate: Decimal = Decimal("0")

    @property
    def total_normal_hours(self) -> Decimal:
        return sum((e.normal_hours for e in self.entries), Decimal("0"))

    @property
    def total_ot_hours(self) -> Decimal:
        return sum((e.ot_hours for e in self.entries), Decimal("0"))

    @property
    def total_hot_hours(self) -> Decimal:
        return sum((e.hot_hours for e in self.entries), Decimal("0"))

    @property
    def total_hours(self) -> Decimal:
        return self.total_normal_hours + self.total_ot_hours + self.total_hot_hours

    @property
    def normal_cost(self) -> Decimal:
        return (self.total_normal_hours * self.normal_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def ot_cost(self) -> Decimal:
        return (self.total_ot_hours * self.ot_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def hot_cost(self) -> Decimal:
        return (self.total_hot_hours * self.hot_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @property
    def total_cost(self) -> Decimal:
        return self.normal_cost + self.ot_cost + self.hot_cost


@dataclass
class InvoiceResult:
    """Final computed invoice ready for Excel output."""
    po_data: POData
    engineer_blocks: list[EngineerBlock]
    all_dates: list[date]

    @property
    def grand_total(self) -> Decimal:
        return sum((b.total_cost for b in self.engineer_blocks), Decimal("0"))

    @property
    def total_normal_hours(self) -> Decimal:
        return sum((b.total_normal_hours for b in self.engineer_blocks), Decimal("0"))

    @property
    def total_ot_hours(self) -> Decimal:
        return sum((b.total_ot_hours for b in self.engineer_blocks), Decimal("0"))

    @property
    def total_hot_hours(self) -> Decimal:
        return sum((b.total_hot_hours for b in self.engineer_blocks), Decimal("0"))

    @property
    def total_hours(self) -> Decimal:
        return self.total_normal_hours + self.total_ot_hours + self.total_hot_hours


class StrictValidationError(Exception):
    """Raised when strict validation fails."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Strict validation failed with {len(errors)} error(s):\n" +
                         "\n".join(f"  - {e}" for e in errors))
