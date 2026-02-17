"""CLI entry point — Phase 1.

Usage:
    python -m invoice_tool \
        --po-pdf "Contract.pdf" \
        --timesheets "Timesheets/*.pdf" \
        --template "Template.xlsx" \
        --out "Invoice_Report.xlsx" \
        --audit-out "Audit.json" \
        --strict
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import typer

from invoice_tool.models import Category, EngineerLevel, StrictValidationError


def generate(
    po_pdf: str = typer.Option(..., "--po-pdf", help="Path to PO/Contract PDF"),
    timesheets: str = typer.Option(..., "--timesheets", help="Glob pattern for timesheet PDFs"),
    template: str = typer.Option(..., "--template", help="Path to Excel template"),
    out: str = typer.Option("Invoice_Report.xlsx", "--out", help="Output Excel file path"),
    audit_out: str = typer.Option("Audit.json", "--audit-out", help="Output audit JSON file path"),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Enable strict validation (default: True)"),
    engineer_config_file: str = typer.Option(None, "--engineer-config", help="JSON file mapping engineer names to category/level"),
) -> None:
    """Generate invoice report from PO PDF, timesheet PDFs, and Excel template."""
    from invoice_tool.parsers import parse_po_pdf, parse_timesheet_pdf
    from invoice_tool.engine import validate_entries, calculate_invoice, apply_hours_split
    from invoice_tool.excel import generate_excel_report
    from invoice_tool.audit import generate_audit
    import json

    # Resolve paths
    po_path = Path(po_pdf)
    template_path = Path(template)
    out_path = Path(out)
    audit_path = Path(audit_out)

    # Expand timesheet glob
    ts_files = sorted(glob.glob(timesheets))
    if not ts_files:
        typer.echo(f"ERROR: No timesheet files found matching: {timesheets}", err=True)
        raise typer.Exit(1)

    typer.echo(f"PO PDF: {po_path}")
    typer.echo(f"Template: {template_path}")
    typer.echo(f"Timesheets ({len(ts_files)}):")
    for f in ts_files:
        typer.echo(f"  - {f}")
    typer.echo(f"Strict mode: {strict}")
    typer.echo("")

    # Load engineer config
    engineer_config: dict[str, tuple[Category, EngineerLevel]] = {}
    if engineer_config_file:
        config_data = json.loads(Path(engineer_config_file).read_text(encoding='utf-8'))
        for name, cfg in config_data.items():
            engineer_config[name] = (
                Category(cfg["category"]),
                EngineerLevel(cfg["level"]),
            )
    else:
        # Default config based on actual data
        engineer_config = _default_engineer_config()

    try:
        # Step 1: Parse PO
        typer.echo("Parsing PO/Contract PDF...")
        po_data = parse_po_pdf(po_path)
        typer.echo(f"  Contract #: {po_data.contract_number}")
        typer.echo(f"  Onshore rates: {len(po_data.onshore_rates)} levels")
        typer.echo(f"  Offshore rates: {len(po_data.offshore_rates)} levels")

        # Step 2: Parse timesheets
        typer.echo("\nParsing timesheet PDFs...")
        all_entries = []
        for ts_path in ts_files:
            typer.echo(f"  Parsing: {Path(ts_path).name}...")
            entries = parse_timesheet_pdf(ts_path, engineer_config)
            typer.echo(f"    -> {len(entries)} entries extracted")
            all_entries.extend(entries)

        typer.echo(f"\n  Total entries: {len(all_entries)}")

        # Step 2.5: Apply hours splitting
        typer.echo("\nApplying hours splitting (Saudi work week rules)...")
        all_entries = apply_hours_split(
            all_entries,
            onshore_standing=po_data.onshore_hours_per_day,
            offshore_standing=po_data.offshore_hours_per_day,
        )

        # Step 3: Validate
        typer.echo("\nRunning strict validation...")
        validated_entries = validate_entries(all_entries, po_data)
        typer.echo("  Validation PASSED")

        # Step 4: Calculate
        typer.echo("\nCalculating financials...")
        result = calculate_invoice(validated_entries, po_data)

        for block in result.engineer_blocks:
            typer.echo(f"  {block.name} ({block.category.value}):")
            typer.echo(f"    Normal: {block.total_normal_hours}h x ${block.normal_rate} = ${block.normal_cost}")
            typer.echo(f"    OT:     {block.total_ot_hours}h x ${block.ot_rate} = ${block.ot_cost}")
            typer.echo(f"    HOT:    {block.total_hot_hours}h x ${block.hot_rate} = ${block.hot_cost}")
            typer.echo(f"    Subtotal: ${block.total_cost}")

        typer.echo(f"\n  GRAND TOTAL: ${result.grand_total}")

        # Step 5: Generate Excel
        typer.echo(f"\nGenerating Excel report: {out_path}...")
        generate_excel_report(result, template_path, out_path)
        typer.echo(f"  Excel report saved to: {out_path}")

        # Step 6: Generate Audit
        typer.echo(f"\nGenerating audit file: {audit_path}...")
        generate_audit(result, audit_path)
        typer.echo(f"  Audit file saved to: {audit_path}")

        typer.echo("\nSUCCESS: Invoice report generated.")

    except StrictValidationError as e:
        typer.echo(f"\nSTRICT VALIDATION FAILED:", err=True)
        for error in e.errors:
            typer.echo(f"  ERROR: {error}", err=True)
        if strict:
            typer.echo("\nReport NOT generated (strict mode).", err=True)
            raise typer.Exit(1)
        else:
            typer.echo("\nWARNING: Continuing in non-strict mode...", err=True)

    except Exception as e:
        typer.echo(f"\nFATAL ERROR: {e}", err=True)
        raise typer.Exit(1)


def _default_engineer_config() -> dict[str, tuple[Category, EngineerLevel]]:
    """Default engineer configuration based on known project data."""
    return {
        "SURAJ NEGI": (Category.OFFSHORE, EngineerLevel.SERVICE_FIELD),
        "Suraj Negi": (Category.OFFSHORE, EngineerLevel.SERVICE_FIELD),
        "Atif": (Category.ONSHORE, EngineerLevel.SERVICE_FIELD),
        "Ankit Modi": (Category.ONSHORE, EngineerLevel.SERVICE_FIELD),
    }


if __name__ == "__main__":
    typer.run(generate)
