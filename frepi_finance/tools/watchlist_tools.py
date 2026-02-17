"""
Watchlist tools - Price monitoring and alerts.
"""

from typing import Any

from frepi_finance.shared.supabase_client import get_supabase_client, Tables


WATCHLIST_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_to_watchlist",
            "description": "Add a product to the price watchlist for monitoring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "Product name to watch"},
                    "alert_type": {
                        "type": "string",
                        "enum": ["any_change", "price_drop", "price_increase", "competitor_better", "threshold"],
                        "description": "Type of alert to set"
                    },
                    "threshold_percent": {"type": "number", "description": "Alert if change exceeds this %"},
                    "target_price": {"type": "number", "description": "Alert if price crosses this value"}
                },
                "required": ["product_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_watchlist",
            "description": "Remove a product from the price watchlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "watchlist_id": {"type": "string", "description": "UUID of the watchlist entry"}
                },
                "required": ["watchlist_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_watchlist",
            "description": "Get all products currently on the price watchlist.",
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
            "name": "check_watchlist_alerts",
            "description": "Manually check for price alerts on all watchlist items.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


async def execute_watchlist_tool(tool_name: str, args: dict[str, Any], session) -> dict:
    """Execute a watchlist tool."""

    if tool_name == "add_to_watchlist":
        # First, find the product in master_list
        from frepi_finance.tools.db_tools import search_master_list
        search_result = await search_master_list(args["product_name"], session.restaurant_id)

        if not search_result.get("products"):
            return {"error": f"Produto '{args['product_name']}' nao encontrado na lista mestre."}

        product = search_result["products"][0]
        master_list_id = product["id"]

        client = get_supabase_client()
        data = {
            "restaurant_id": session.restaurant_id,
            "master_list_id": master_list_id,
            "alert_type": args.get("alert_type", "any_change"),
            "threshold_percent": args.get("threshold_percent"),
            "target_price": args.get("target_price"),
            "is_active": True,
        }
        result = client.table(Tables.PRODUCT_PRICE_WATCHLIST).insert(data).execute()

        return {
            "success": True,
            "watchlist_id": result.data[0]["id"] if result.data else None,
            "product_name": product.get("product_name", args["product_name"]),
            "alert_type": data["alert_type"],
        }

    elif tool_name == "remove_from_watchlist":
        client = get_supabase_client()
        client.table(Tables.PRODUCT_PRICE_WATCHLIST).update(
            {"is_active": False}
        ).eq("id", args["watchlist_id"]).execute()
        return {"success": True, "removed": args["watchlist_id"]}

    elif tool_name == "get_watchlist":
        client = get_supabase_client()
        result = client.table(Tables.PRODUCT_PRICE_WATCHLIST).select(
            "*, master_list(product_name)"
        ).eq(
            "restaurant_id", session.restaurant_id
        ).eq("is_active", True).execute()

        items = []
        for item in (result.data or []):
            items.append({
                "id": item["id"],
                "product_name": item.get("master_list", {}).get("product_name", "Unknown"),
                "alert_type": item["alert_type"],
                "current_price": item.get("current_price"),
                "target_price": item.get("target_price"),
                "threshold_percent": item.get("threshold_percent"),
                "best_competitor_price": item.get("best_competitor_price"),
            })

        return {"items": items, "count": len(items)}

    elif tool_name == "check_watchlist_alerts":
        from frepi_finance.services.price_trend import check_watchlist_for_alerts
        alerts = await check_watchlist_for_alerts(session.restaurant_id)
        return {"alerts": alerts, "count": len(alerts)}

    return {"error": f"Unknown watchlist tool: {tool_name}"}
