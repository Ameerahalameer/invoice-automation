"""Phase 2 — Streamlit drag-and-drop UI.

Calls the same core engine as the CLI. No business logic here.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from invoice_tool.audit import generate_audit
from invoice_tool.engine import calculate_invoice, validate_entries, apply_hours_split
from invoice_tool.excel import generate_excel_report
from invoice_tool.models import Category, EngineerLevel, StrictValidationError
from invoice_tool.parsers import parse_po_pdf, parse_timesheet_pdf


def _default_engineer_config() -> dict[str, tuple[Category, EngineerLevel]]:
    return {
        "SURAJ NEGI": (Category.OFFSHORE, EngineerLevel.SERVICE_FIELD),
        "Suraj Negi": (Category.OFFSHORE, EngineerLevel.SERVICE_FIELD),
        "Atif": (Category.ONSHORE, EngineerLevel.SERVICE_FIELD),
        "Ankit Modi": (Category.ONSHORE, EngineerLevel.SERVICE_FIELD),
    }


def main() -> None:
    st.set_page_config(page_title="Invoice Automation Tool", layout="wide")
    st.title("Invoice Automation Tool")
    st.markdown("Generate financial-grade invoice reports from PO + Timesheets + Template.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Inputs")
        po_file = st.file_uploader("Upload PO/Contract PDF", type=["pdf"], key="po")
        ts_files = st.file_uploader(
            "Upload Timesheet PDFs", type=["pdf"],
            accept_multiple_files=True, key="ts",
        )
        template_file = st.file_uploader("Upload Excel Template", type=["xlsx"], key="template")

    with col2:
        st.subheader("Engineer Configuration")
        st.markdown("Map engineer names to category and level.")

        config_json = st.text_area(
            "Engineer Config (JSON)",
            value=json.dumps({
                "SURAJ NEGI": {"category": "offshore", "level": "service_field"},
                "Atif": {"category": "onshore", "level": "service_field"},
                "Ankit Modi": {"category": "onshore", "level": "service_field"},
            }, indent=2),
            height=200,
        )

    strict = st.checkbox("Strict Mode (recommended)", value=True)

    if st.button("Generate Report", type="primary", disabled=not (po_file and ts_files and template_file)):
        try:
            # Parse engineer config
            try:
                config_data = json.loads(config_json)
                engineer_config = {
                    name: (Category(cfg["category"]), EngineerLevel(cfg["level"]))
                    for name, cfg in config_data.items()
                }
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                st.error(f"Invalid engineer config: {e}")
                return

            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir = Path(tmpdir)

                # Save uploaded files
                po_path = tmpdir / po_file.name
                po_path.write_bytes(po_file.getvalue())

                ts_paths = []
                for ts in ts_files:
                    p = tmpdir / ts.name
                    p.write_bytes(ts.getvalue())
                    ts_paths.append(p)

                template_path = tmpdir / template_file.name
                template_path.write_bytes(template_file.getvalue())

                out_path = tmpdir / "Invoice_Report.xlsx"
                audit_path = tmpdir / "Audit.json"

                with st.spinner("Parsing PO/Contract..."):
                    po_data = parse_po_pdf(po_path)
                    st.success(f"PO parsed: Contract #{po_data.contract_number}")

                with st.spinner("Parsing timesheets..."):
                    all_entries = []
                    for ts_path in ts_paths:
                        entries = parse_timesheet_pdf(ts_path, engineer_config)
                        st.info(f"  {ts_path.name}: {len(entries)} entries")
                        all_entries.extend(entries)

                with st.spinner("Applying hours splitting..."):
                    all_entries = apply_hours_split(
                        all_entries,
                        onshore_standing=po_data.onshore_hours_per_day,
                        offshore_standing=po_data.offshore_hours_per_day,
                    )

                with st.spinner("Validating..."):
                    validated = validate_entries(all_entries, po_data)
                    st.success("Validation passed!")

                with st.spinner("Calculating financials..."):
                    result = calculate_invoice(validated, po_data)

                with st.spinner("Generating Excel..."):
                    generate_excel_report(result, template_path, out_path)

                with st.spinner("Generating audit..."):
                    generate_audit(result, audit_path)

                st.success(f"Grand Total: ${result.grand_total:,.2f}")

                # Download buttons
                col_a, col_b = st.columns(2)
                with col_a:
                    st.download_button(
                        "Download Excel Report",
                        data=out_path.read_bytes(),
                        file_name="Invoice_Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                with col_b:
                    st.download_button(
                        "Download Audit JSON",
                        data=audit_path.read_text(encoding='utf-8'),
                        file_name="Audit.json",
                        mime="application/json",
                    )

                # Show summary
                st.subheader("Invoice Summary")
                for block in result.engineer_blocks:
                    with st.expander(f"{block.name} ({block.category.value})"):
                        st.write(f"Normal: {block.total_normal_hours}h x ${block.normal_rate} = ${block.normal_cost}")
                        st.write(f"OT: {block.total_ot_hours}h x ${block.ot_rate} = ${block.ot_cost}")
                        st.write(f"HOT: {block.total_hot_hours}h x ${block.hot_rate} = ${block.hot_cost}")
                        st.write(f"**Subtotal: ${block.total_cost}**")

        except StrictValidationError as e:
            st.error("Strict Validation Failed!")
            for err in e.errors:
                st.error(f"  - {err}")

        except Exception as e:
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
