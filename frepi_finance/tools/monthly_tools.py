"""
Monthly closure tools - Financial reporting and cashflow.
"""

from typing import Any
from datetime import date

from frepi_finance.shared.supabase_client import get_supabase_client, Tables


MONTHLY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "start_monthly_closure",
            "description": "Start or resume the monthly financial closure process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Year for the report (default: current year)"
                    },
                    "month": {
                        "type": "integer",
                        "description": "Month for the report (1-12, default: previous month)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_revenue",
            "description": "Submit the restaurant's total revenue for the month. This is required to generate the financial report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "total_revenue": {
                        "type": "number",
                        "description": "Total revenue in BRL (e.g., 120000.00)"
                    },
                    "revenue_source": {
                        "type": "string",
                        "enum": ["manual_single", "manual_detailed", "pos_integration"],
                        "description": "How the revenue was provided"
                    },
                    "revenue_breakdown": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "plate_name": {"type": "string"},
                                "quantity": {"type": "integer"},
                                "revenue": {"type": "number"}
                            }
                        },
                        "description": "Optional detailed breakdown by plate/category"
                    }
                },
                "required": ["total_revenue"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_monthly_report",
            "description": "Generate the full monthly financial report with insights and recommendations.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_report_history",
            "description": "Get historical monthly reports for trend comparison.",
            "parameters": {
                "type": "object",
                "properties": {
                    "months": {
                        "type": "integer",
                        "description": "Number of months to look back (default: 6)",
                        "default": 6
                    }
                },
                "required": []
            }
        }
    },
]


async def execute_monthly_tool(tool_name: str, args: dict[str, Any], session) -> dict:
    """Execute a monthly closure tool."""

    if tool_name == "start_monthly_closure":
        today = date.today()
        year = args.get("year", today.year)
        month = args.get("month")
        if month is None:
            # Default to previous month if we're in first 10 days, else current month
            if today.day <= 10:
                month = today.month - 1 if today.month > 1 else 12
                if month == 12 and today.month == 1:
                    year = year - 1
            else:
                month = today.month

        client = get_supabase_client()

        # Check for existing report
        result = client.table(Tables.MONTHLY_FINANCIAL_REPORTS).select("*").eq(
            "restaurant_id", session.restaurant_id
        ).eq("report_year", year).eq("report_month", month).limit(1).execute()

        if result.data:
            report = result.data[0]
            session.current_report_id = report["id"]
            return {
                "exists": True,
                "report_id": report["id"],
                "status": report["status"],
                "year": year,
                "month": month,
                "total_revenue": report.get("total_revenue"),
                "total_purchases": report.get("total_purchases"),
                "cmv_percent": report.get("cmv_percent"),
            }

        # Create new report
        report_data = {
            "restaurant_id": session.restaurant_id,
            "report_year": year,
            "report_month": month,
            "status": "awaiting_revenue",
        }
        result = client.table(Tables.MONTHLY_FINANCIAL_REPORTS).insert(report_data).execute()
        report_id = result.data[0]["id"] if result.data else None
        session.current_report_id = report_id

        # Pre-calculate purchases from invoices
        from frepi_finance.services.cashflow import calculate_monthly_purchases
        purchases = await calculate_monthly_purchases(session.restaurant_id, year, month)

        return {
            "exists": False,
            "report_id": report_id,
            "status": "awaiting_revenue",
            "year": year,
            "month": month,
            "total_purchases": purchases.get("total", 0),
            "invoice_count": purchases.get("invoice_count", 0),
            "supplier_count": purchases.get("supplier_count", 0),
            "needs_revenue": True,
        }

    elif tool_name == "submit_revenue":
        client = get_supabase_client()
        report_id = session.current_report_id

        if not report_id:
            return {"error": "No active monthly report. Call start_monthly_closure first."}

        update_data = {
            "total_revenue": args["total_revenue"],
            "revenue_source": args.get("revenue_source", "manual_single"),
            "status": "complete",
        }

        if args.get("revenue_breakdown"):
            update_data["revenue_breakdown"] = args["revenue_breakdown"]

        client.table(Tables.MONTHLY_FINANCIAL_REPORTS).update(update_data).eq("id", report_id).execute()

        return {
            "success": True,
            "report_id": report_id,
            "total_revenue": args["total_revenue"],
        }

    elif tool_name == "generate_monthly_report":
        report_id = session.current_report_id
        if not report_id:
            return {"error": "No active monthly report. Call start_monthly_closure first."}

        from frepi_finance.services.cashflow import generate_full_report
        report = await generate_full_report(report_id, session.restaurant_id)
        return report

    elif tool_name == "get_report_history":
        client = get_supabase_client()
        months = args.get("months", 6)

        result = client.table(Tables.MONTHLY_FINANCIAL_REPORTS).select(
            "report_month, report_year, total_revenue, total_purchases, cmv_percent, status"
        ).eq(
            "restaurant_id", session.restaurant_id
        ).order("report_year", desc=True).order("report_month", desc=True).limit(months).execute()

        return {"reports": result.data or [], "count": len(result.data or [])}

    return {"error": f"Unknown monthly tool: {tool_name}"}
