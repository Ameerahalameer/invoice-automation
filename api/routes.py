"""API routes for the Invoice Automation Tool."""

from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from invoice_tool.models import Category, EngineerLevel, StrictValidationError
from invoice_tool.parsers import parse_po_pdf, parse_timesheet_pdf
from invoice_tool.engine import validate_entries, calculate_invoice, apply_hours_split
from invoice_tool.excel import generate_excel_report
from invoice_tool.audit import generate_audit_dict

from api.schemas import (
    DateRange,
    EngineerSummary,
    GenerateResponse,
    InvoiceSummary,
)

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    po_pdf: UploadFile = File(..., description="PO/Contract PDF"),
    timesheets: list[UploadFile] = File(..., description="Timesheet PDFs"),
    template: UploadFile = File(..., description="Excel template (.xlsx)"),
    engineer_config: str = Form(..., description="JSON engineer config"),
    strict: bool = Form(True, description="Strict validation mode"),
):
    """Generate invoice report from uploaded files.

    Accepts multipart form with PO PDF, timesheet PDFs, Excel template,
    and JSON engineer configuration. Returns JSON with summary, per-engineer
    breakdown, base64-encoded Excel report, and audit data.
    """
    # Parse engineer config JSON
    try:
        config_data = json.loads(engineer_config)
        eng_config: dict[str, tuple[Category, EngineerLevel]] = {}
        for name, cfg in config_data.items():
            eng_config[name] = (
                Category(cfg["category"]),
                EngineerLevel(cfg["level"]),
            )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return GenerateResponse(
            success=False,
            error_type="config_error",
            errors=[f"Invalid engineer config: {e}"],
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        try:
            # Save PO PDF
            po_path = tmp / "po.pdf"
            po_path.write_bytes(await po_pdf.read())

            # Save timesheet PDFs
            ts_paths = []
            for i, ts in enumerate(timesheets):
                # Preserve original filename for engineer name extraction
                safe_name = ts.filename or f"timesheet_{i}.pdf"
                ts_path = tmp / safe_name
                ts_path.write_bytes(await ts.read())
                ts_paths.append(ts_path)

            # Save template
            template_path = tmp / "template.xlsx"
            template_path.write_bytes(await template.read())

            # Output paths
            out_excel = tmp / "Invoice_Report.xlsx"

            # Step 1: Parse PO
            po_data = parse_po_pdf(po_path)

            # Step 2: Parse timesheets
            all_entries = []
            for ts_path in ts_paths:
                entries = parse_timesheet_pdf(ts_path, eng_config)
                all_entries.extend(entries)

            # Step 3: Apply hours splitting
            all_entries = apply_hours_split(
                all_entries,
                onshore_standing=po_data.onshore_hours_per_day,
                offshore_standing=po_data.offshore_hours_per_day,
            )

            # Step 4: Validate
            validated = validate_entries(all_entries, po_data)

            # Step 5: Calculate
            result = calculate_invoice(validated, po_data)

            # Step 6: Generate Excel
            generate_excel_report(result, template_path, out_excel)
            excel_bytes = out_excel.read_bytes()
            excel_b64 = base64.b64encode(excel_bytes).decode("ascii")

            # Step 7: Generate audit dict
            audit = generate_audit_dict(result)

            # Build response
            engineers = []
            for block in result.engineer_blocks:
                engineers.append(EngineerSummary(
                    name=block.name,
                    category=block.category.value,
                    level=block.engineer_level.value,
                    normal_hours=float(block.total_normal_hours),
                    ot_hours=float(block.total_ot_hours),
                    hot_hours=float(block.total_hot_hours),
                    total_hours=float(block.total_hours),
                    normal_rate=float(block.normal_rate),
                    ot_rate=float(block.ot_rate),
                    hot_rate=float(block.hot_rate),
                    normal_cost=float(block.normal_cost),
                    ot_cost=float(block.ot_cost),
                    hot_cost=float(block.hot_cost),
                    total_cost=float(block.total_cost),
                ))

            summary = InvoiceSummary(
                grand_total_usd=float(result.grand_total),
                total_engineers=len(result.engineer_blocks),
                total_normal_hours=float(result.total_normal_hours),
                total_ot_hours=float(result.total_ot_hours),
                total_hot_hours=float(result.total_hot_hours),
                total_hours=float(result.total_hours),
                contract_number=result.po_data.contract_number,
                date_range=DateRange(
                    start=result.all_dates[0].isoformat() if result.all_dates else None,
                    end=result.all_dates[-1].isoformat() if result.all_dates else None,
                ),
            )

            return GenerateResponse(
                success=True,
                summary=summary,
                engineers=engineers,
                excel_base64=excel_b64,
                audit=audit,
            )

        except StrictValidationError as e:
            return GenerateResponse(
                success=False,
                error_type="validation_error",
                errors=e.errors,
            )
        except Exception as e:
            return GenerateResponse(
                success=False,
                error_type="processing_error",
                errors=[str(e)],
            )
