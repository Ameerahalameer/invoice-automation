"""Layer 6 — Audit Engine.

Generates full traceability JSON output.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from invoice_tool.models import InvoiceResult


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal values."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def generate_audit_dict(result: InvoiceResult) -> dict:
    """Build audit dictionary from computed invoice result (no file I/O)."""
    engineers = []
    for block in result.engineer_blocks:
        eng_data = {
            "name": block.name,
            "category": block.category.value,
            "engineer_level": block.engineer_level.value,
            "rates": {
                "normal": float(block.normal_rate),
                "ot": float(block.ot_rate),
                "hot": float(block.hot_rate),
            },
            "hours": {
                "normal": float(block.total_normal_hours),
                "ot": float(block.total_ot_hours),
                "hot": float(block.total_hot_hours),
                "total": float(block.total_hours),
            },
            "costs": {
                "normal": float(block.normal_cost),
                "ot": float(block.ot_cost),
                "hot": float(block.hot_cost),
                "total": float(block.total_cost),
            },
            "source_files": sorted({e.source_file for e in block.entries}),
            "entries": [
                {
                    "date": e.date.isoformat(),
                    "normal_hours": float(e.normal_hours),
                    "ot_hours": float(e.ot_hours),
                    "hot_hours": float(e.hot_hours),
                    "total_hours": float(e.total_hours),
                    "source_file": e.source_file,
                }
                for e in sorted(block.entries, key=lambda x: x.date)
            ],
        }
        engineers.append(eng_data)

    return {
        "po_number": result.po_data.contract_number,
        "po_source": result.po_data.source_file,
        "max_contract_amount_usd": float(result.po_data.max_amount_usd),
        "rates_used": {
            "onshore": {
                level.value: {
                    "normal": float(rate_set.normal),
                    "ot": float(rate_set.ot),
                    "hot": float(rate_set.hot),
                }
                for level, rate_set in result.po_data.onshore_rates.items()
            },
            "offshore": {
                level.value: {
                    "normal": float(rate_set.normal),
                    "ot": float(rate_set.ot),
                    "hot": float(rate_set.hot),
                }
                for level, rate_set in result.po_data.offshore_rates.items()
            },
        },
        "engineers": engineers,
        "summary": {
            "total_engineers": len(result.engineer_blocks),
            "total_normal_hours": float(result.total_normal_hours),
            "total_ot_hours": float(result.total_ot_hours),
            "total_hot_hours": float(result.total_hot_hours),
            "total_hours": float(result.total_hours),
            "grand_total_usd": float(result.grand_total),
        },
        "date_range": {
            "start": result.all_dates[0].isoformat() if result.all_dates else None,
            "end": result.all_dates[-1].isoformat() if result.all_dates else None,
            "total_dates": len(result.all_dates),
        },
        "source_files": sorted({
            e.source_file
            for block in result.engineer_blocks
            for e in block.entries
        }),
    }


def generate_audit(result: InvoiceResult, output_path: str | Path) -> Path:
    """Generate audit JSON file from computed invoice result."""
    output_path = Path(output_path)
    audit = generate_audit_dict(result)
    output_path.write_text(json.dumps(audit, indent=2, cls=DecimalEncoder), encoding='utf-8')
    return output_path
