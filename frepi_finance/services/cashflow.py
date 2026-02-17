"""
Cashflow Service - Monthly financial calculations and report generation.
"""

import logging
from datetime import datetime
from typing import Optional

from frepi_finance.shared.supabase_client import (
    get_supabase_client,
    fetch_many,
    fetch_one,
    update_one,
    Tables,
)

logger = logging.getLogger(__name__)


async def calculate_monthly_purchases(
    restaurant_id: int, year: int, month: int
) -> dict:
    """
    Calculate total purchases from invoices for a given month.

    Groups invoices by supplier and returns totals with supplier breakdown.
    """
    client = get_supabase_client()

    # Build date range
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    result = client.table(Tables.INVOICES).select(
        "id, supplier_name_extracted, total_amount, invoice_date"
    ).eq("restaurant_id", restaurant_id).gte(
        "invoice_date", start_date
    ).lt("invoice_date", end_date).in_(
        "status", ["parsed", "confirmed"]
    ).execute()

    invoices = result.data or []
    total = sum(inv.get("total_amount", 0) or 0 for inv in invoices)

    # Group by supplier
    by_supplier = {}
    for inv in invoices:
        name = inv.get("supplier_name_extracted", "Desconhecido")
        if name not in by_supplier:
            by_supplier[name] = {"name": name, "total": 0, "count": 0}
        by_supplier[name]["total"] += inv.get("total_amount", 0) or 0
        by_supplier[name]["count"] += 1

    suppliers = sorted(by_supplier.values(), key=lambda x: x["total"], reverse=True)

    return {
        "total": round(total, 2),
        "invoice_count": len(invoices),
        "supplier_count": len(suppliers),
        "by_supplier": suppliers,
    }


async def generate_cashflow_data(
    restaurant_id: int,
    year: int,
    month: int,
) -> dict:
    """
    Generate cashflow data for a given month.

    Groups purchases by supplier and by week for visualization.
    """
    invoices = await fetch_many(
        Tables.INVOICES,
        filters={"restaurant_id": restaurant_id, "status": "confirmed"},
    )

    # Filter by month (handling both date formats)
    month_invoices = []
    for inv in invoices:
        inv_date = inv.get("invoice_date")
        if inv_date:
            try:
                parsed = datetime.strptime(inv_date, "%d/%m/%Y")
                if parsed.year == year and parsed.month == month:
                    month_invoices.append({**inv, "_parsed_date": parsed})
            except (ValueError, TypeError):
                try:
                    parsed = datetime.strptime(str(inv_date), "%Y-%m-%d")
                    if parsed.year == year and parsed.month == month:
                        month_invoices.append({**inv, "_parsed_date": parsed})
                except (ValueError, TypeError):
                    pass

    # Group by supplier
    by_supplier = {}
    for inv in month_invoices:
        supplier = inv.get("supplier_name_extracted", "Desconhecido")
        if supplier not in by_supplier:
            by_supplier[supplier] = {"total": 0.0, "count": 0}
        by_supplier[supplier]["total"] += inv.get("total_amount", 0) or 0
        by_supplier[supplier]["count"] += 1

    # Group by week
    by_week = {}
    for inv in month_invoices:
        parsed_date = inv["_parsed_date"]
        week_num = (parsed_date.day - 1) // 7 + 1
        week_key = f"Semana {week_num}"
        if week_key not in by_week:
            by_week[week_key] = 0.0
        by_week[week_key] += inv.get("total_amount", 0) or 0

    total = sum(inv.get("total_amount", 0) or 0 for inv in month_invoices)

    return {
        "total_purchases": total,
        "invoice_count": len(month_invoices),
        "by_supplier": by_supplier,
        "by_week": by_week,
    }


async def generate_full_report(report_id: str, restaurant_id: int) -> dict:
    """
    Generate a complete monthly financial report with insights.

    Calculates purchases from invoices, computes CMV against reported revenue,
    compares with previous month, and generates actionable insights.
    """
    client = get_supabase_client()

    # Get the report record
    report_result = client.table(Tables.MONTHLY_FINANCIAL_REPORTS).select("*").eq(
        "id", report_id
    ).limit(1).execute()

    if not report_result.data:
        return {"error": "Report not found"}

    report = report_result.data[0]
    year = report["report_year"]
    month = report["report_month"]
    revenue = report.get("total_revenue", 0)

    # Calculate purchases for the month
    purchases = await calculate_monthly_purchases(restaurant_id, year, month)

    # CMV calculation
    cmv_pct = (purchases["total"] / revenue * 100) if revenue > 0 else 0
    cmv_target = report.get("cmv_target_percent", 32.0)

    if cmv_pct <= cmv_target:
        cmv_status = "on_target"
    elif cmv_pct <= 40:
        cmv_status = "above_target"
    else:
        cmv_status = "critical"

    # Get previous month for comparison
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    prev_report = client.table(Tables.MONTHLY_FINANCIAL_REPORTS).select(
        "total_revenue, total_purchases, cmv_percent"
    ).eq("restaurant_id", restaurant_id).eq(
        "report_year", prev_year
    ).eq("report_month", prev_month).limit(1).execute()

    mom_change = None
    if prev_report.data and prev_report.data[0].get("total_purchases"):
        prev_purchases = prev_report.data[0]["total_purchases"]
        if prev_purchases > 0:
            mom_change = round(
                ((purchases["total"] - prev_purchases) / prev_purchases) * 100, 1
            )

    # Generate insights
    insights = []
    if purchases["by_supplier"]:
        top_supplier = purchases["by_supplier"][0]
        pct_of_total = (
            (top_supplier["total"] / purchases["total"] * 100)
            if purchases["total"] > 0
            else 0
        )
        insights.append(
            f"Maior fornecedor: {top_supplier['name']} ({pct_of_total:.0f}% das compras, "
            f"R$ {top_supplier['total']:,.2f})"
        )

    if cmv_status == "critical":
        insights.append(
            f"CMV em {cmv_pct:.1f}% - muito acima da meta de {cmv_target}%. "
            "Revise precos do cardapio ou negocie com fornecedores."
        )
    elif cmv_status == "above_target":
        insights.append(
            f"CMV em {cmv_pct:.1f}% - acima da meta de {cmv_target}%. "
            "Monitore os produtos com maior variacao de preco."
        )

    if mom_change is not None and mom_change > 5:
        insights.append(f"Compras subiram {mom_change}% em relacao ao mes anterior.")

    # Update report in database
    update_data = {
        "total_purchases": purchases["total"],
        "purchase_breakdown": purchases["by_supplier"],
        "invoice_count": purchases["invoice_count"],
        "supplier_count": purchases["supplier_count"],
        "cmv_percent": round(cmv_pct, 2),
        "cmv_target_percent": cmv_target,
        "cmv_status": cmv_status,
        "insights": insights,
        "month_over_month_change": mom_change,
        "status": "complete",
        "generated_at": "now()",
    }

    client.table(Tables.MONTHLY_FINANCIAL_REPORTS).update(
        update_data
    ).eq("id", report_id).execute()

    return {
        "report_id": report_id,
        "period": f"{month:02d}/{year}",
        "revenue": revenue,
        "purchases": purchases["total"],
        "cmv_percent": round(cmv_pct, 2),
        "cmv_target": cmv_target,
        "cmv_status": cmv_status,
        "invoice_count": purchases["invoice_count"],
        "supplier_count": purchases["supplier_count"],
        "top_suppliers": purchases["by_supplier"][:5],
        "mom_change": mom_change,
        "insights": insights,
    }
