"""
CMV (Custo de Mercadoria Vendida) tools - Menu items, ingredients, food cost.
"""

from typing import Any

from frepi_finance.shared.supabase_client import get_supabase_client, Tables


CMV_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_menu_item",
            "description": "Add a menu item (dish) to the restaurant's catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Name of the dish"},
                    "sale_price": {"type": "number", "description": "Price charged to customer in BRL"},
                    "category": {
                        "type": "string",
                        "enum": ["entrada", "prato_principal", "sobremesa", "bebida", "acompanhamento"],
                        "description": "Category of the menu item"
                    },
                    "description": {"type": "string", "description": "Optional description of the dish"}
                },
                "required": ["item_name", "sale_price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_ingredient",
            "description": "Add an ingredient to a menu item's recipe card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "menu_item_id": {"type": "string", "description": "UUID of the menu item"},
                    "ingredient_name": {"type": "string", "description": "Name of the ingredient"},
                    "quantity_per_serving": {"type": "number", "description": "Amount needed per serving"},
                    "unit": {
                        "type": "string",
                        "enum": ["kg", "g", "un", "ml", "lt", "cx", "pct"],
                        "description": "Unit of measurement"
                    },
                    "waste_percent": {"type": "number", "description": "Expected waste percentage (default: 0)"}
                },
                "required": ["menu_item_id", "ingredient_name", "quantity_per_serving", "unit"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_food_cost",
            "description": "Calculate the food cost for a specific menu item based on current ingredient prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "menu_item_id": {"type": "string", "description": "UUID of the menu item"}
                },
                "required": ["menu_item_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_unprofitable_items",
            "description": "Get menu items where food cost percentage is above the threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "number", "description": "Food cost % threshold (default: 35)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_cmv_history",
            "description": "Get historical CMV/food cost data for menu items or the whole restaurant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "menu_item_id": {"type": "string", "description": "Specific menu item UUID (optional, omit for all)"},
                    "granularity": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly"],
                        "description": "Time granularity (default: monthly)"
                    },
                    "months": {"type": "integer", "description": "Months to look back (default: 6)"}
                },
                "required": []
            }
        }
    },
]


async def execute_cmv_tool(tool_name: str, args: dict[str, Any], session) -> dict:
    """Execute a CMV tool."""

    if tool_name == "add_menu_item":
        client = get_supabase_client()
        data = {
            "restaurant_id": session.restaurant_id,
            "item_name": args["item_name"],
            "sale_price": args["sale_price"],
            "category": args.get("category"),
            "item_description": args.get("description"),
        }
        result = client.table(Tables.MENU_ITEMS).insert(data).execute()
        item = result.data[0] if result.data else None
        return {
            "success": True,
            "menu_item_id": item["id"] if item else None,
            "item_name": args["item_name"],
            "sale_price": args["sale_price"],
        }

    elif tool_name == "add_ingredient":
        client = get_supabase_client()
        data = {
            "menu_item_id": args["menu_item_id"],
            "ingredient_name": args["ingredient_name"],
            "quantity_per_serving": args["quantity_per_serving"],
            "unit": args["unit"],
            "waste_percent": args.get("waste_percent", 0),
        }
        result = client.table(Tables.MENU_ITEM_INGREDIENTS).insert(data).execute()
        return {
            "success": True,
            "ingredient": args["ingredient_name"],
            "quantity": args["quantity_per_serving"],
            "unit": args["unit"],
        }

    elif tool_name == "calculate_food_cost":
        from frepi_finance.services.cmv_calculator import calculate_menu_item_cost
        result = await calculate_menu_item_cost(args["menu_item_id"])
        return result

    elif tool_name == "get_unprofitable_items":
        threshold = args.get("threshold", 35.0)
        client = get_supabase_client()
        result = client.table(Tables.MENU_ITEMS).select(
            "id, item_name, sale_price, food_cost, food_cost_percent, profitability_tier"
        ).eq(
            "restaurant_id", session.restaurant_id
        ).eq("is_active", True).gt("food_cost_percent", threshold).order(
            "food_cost_percent", desc=True
        ).execute()

        return {
            "threshold": threshold,
            "items": result.data or [],
            "count": len(result.data or []),
        }

    elif tool_name == "get_cmv_history":
        client = get_supabase_client()
        granularity = args.get("granularity", "monthly")
        months = args.get("months", 6)

        query = client.table(Tables.MENU_COST_HISTORY).select("*").eq(
            "restaurant_id", session.restaurant_id
        ).eq("granularity", granularity).order("snapshot_date", desc=True).limit(months * 30)

        if args.get("menu_item_id"):
            query = query.eq("menu_item_id", args["menu_item_id"])

        result = query.execute()
        return {"history": result.data or [], "granularity": granularity}

    return {"error": f"Unknown CMV tool: {tool_name}"}
