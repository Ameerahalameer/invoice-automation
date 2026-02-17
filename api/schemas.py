"""Pydantic response models for the Invoice API."""

from __future__ import annotations

from pydantic import BaseModel


class EngineerSummary(BaseModel):
    name: str
    category: str
    level: str
    normal_hours: float
    ot_hours: float
    hot_hours: float
    total_hours: float
    normal_rate: float
    ot_rate: float
    hot_rate: float
    normal_cost: float
    ot_cost: float
    hot_cost: float
    total_cost: float


class DateRange(BaseModel):
    start: str | None = None
    end: str | None = None


class InvoiceSummary(BaseModel):
    grand_total_usd: float
    total_engineers: int
    total_normal_hours: float
    total_ot_hours: float
    total_hot_hours: float
    total_hours: float
    contract_number: str
    date_range: DateRange


class GenerateResponse(BaseModel):
    success: bool
    summary: InvoiceSummary | None = None
    engineers: list[EngineerSummary] | None = None
    excel_base64: str | None = None
    audit: dict | None = None
    error_type: str | None = None
    errors: list[str] | None = None
