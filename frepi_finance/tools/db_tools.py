"""
Database tools - Shared DB operations used across skills.
"""

from typing import Any, Optional

from frepi_finance.shared.supabase_client import get_supabase_client, Tables


DB_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search for products in the master catalog by name. Used to find products for watchlist, CMV, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Product name or description to search"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_restaurant_suppliers",
            "description": "Get the list of known suppliers for this restaurant.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


async def execute_db_tool(tool_name: str, args: dict[str, Any], session) -> dict:
    """Execute a DB tool."""

    if tool_name == "search_products":
        result = await search_master_list(args["query"], session.restaurant_id)
        return result

    elif tool_name == "get_restaurant_suppliers":
        client = get_supabase_client()
        # Get suppliers from invoices
        result = client.table(Tables.INVOICES).select(
            "supplier_name_extracted, supplier_cnpj_extracted, users_seller_id"
        ).eq("restaurant_id", session.restaurant_id).execute()

        # Deduplicate by supplier name
        suppliers = {}
        for inv in (result.data or []):
            name = inv.get("supplier_name_extracted")
            if name and name not in suppliers:
                suppliers[name] = {
                    "name": name,
                    "cnpj": inv.get("supplier_cnpj_extracted"),
                    "seller_id": inv.get("users_seller_id"),
                }

        return {"suppliers": list(suppliers.values()), "count": len(suppliers)}

    return {"error": f"Unknown DB tool: {tool_name}"}


async def search_master_list(query: str, restaurant_id: Optional[int] = None) -> dict:
    """Search the master product list by name."""
    client = get_supabase_client()

    # Simple text search (ilike)
    q = client.table(Tables.MASTER_LIST).select(
        "id, product_name, category, specifications"
    ).ilike("product_name", f"%{query}%").limit(10)

    if restaurant_id:
        q = q.eq("restaurant_id", restaurant_id)

    result = q.execute()
    return {"products": result.data or [], "count": len(result.data or [])}


async def get_recent_context(restaurant_id: int, intent: str) -> Optional[str]:
    """Build a context string with recent data relevant to the intent."""
    client = get_supabase_client()
    lines = []

    if intent in ("invoice_upload", "general"):
        # Recent invoices
        result = client.table(Tables.INVOICES).select(
            "supplier_name_extracted, invoice_date, total_amount"
        ).eq("restaurant_id", restaurant_id).order(
            "invoice_date", desc=True
        ).limit(5).execute()

        if result.data:
            lines.append("Ultimas NFs processadas:")
            for inv in result.data:
                lines.append(
                    f"- {inv.get('invoice_date')}: {inv.get('supplier_name_extracted')} - "
                    f"R$ {inv.get('total_amount', 0):,.2f}"
                )

    if intent in ("watchlist", "general"):
        # Active watchlist count
        result = client.table(Tables.PRODUCT_PRICE_WATCHLIST).select(
            "id", count="exact"
        ).eq("restaurant_id", restaurant_id).eq("is_active", True).execute()

        count = len(result.data) if result.data else 0
        if count > 0:
            lines.append(f"\nProdutos monitorados: {count}")

    if intent in ("monthly_closure", "general"):
        # Latest report
        result = client.table(Tables.MONTHLY_FINANCIAL_REPORTS).select(
            "report_month, report_year, cmv_percent, status"
        ).eq("restaurant_id", restaurant_id).order(
            "report_year", desc=True
        ).order("report_month", desc=True).limit(1).execute()

        if result.data:
            r = result.data[0]
            lines.append(
                f"\nUltimo relatorio: {r['report_month']}/{r['report_year']} - "
                f"CMV: {r.get('cmv_percent', 'N/A')}% ({r['status']})"
            )

    return "\n".join(lines) if lines else None
