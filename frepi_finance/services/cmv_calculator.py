"""
CMV Calculator - Compute food cost per menu item.
"""

import logging
from typing import Optional

from frepi_finance.shared.supabase_client import get_supabase_client, fetch_many, Tables

logger = logging.getLogger(__name__)


async def calculate_menu_item_cost(menu_item_id: str) -> dict:
    """
    Calculate the food cost for a specific menu item.

    Looks up each ingredient's latest price from invoices or pricing_history,
    applies waste factor, and computes total food cost and percentage.
    """
    client = get_supabase_client()

    # Get menu item
    item_result = client.table(Tables.MENU_ITEMS).select("*").eq(
        "id", menu_item_id
    ).limit(1).execute()

    if not item_result.data:
        return {"error": "Menu item not found"}

    menu_item = item_result.data[0]
    sale_price = menu_item.get("sale_price", 0)

    # Get ingredients
    ingredients_result = client.table(Tables.MENU_ITEM_INGREDIENTS).select("*").eq(
        "menu_item_id", menu_item_id
    ).execute()

    ingredients = ingredients_result.data or []
    total_cost = 0.0
    ingredient_details = []

    for ing in ingredients:
        unit_cost = await _get_ingredient_cost(ing)

        if unit_cost is not None:
            cost_per_serving = ing["quantity_per_serving"] * unit_cost
            waste_factor = 1 + (ing.get("waste_percent", 0) / 100)
            adjusted_cost = cost_per_serving * waste_factor
            total_cost += adjusted_cost

            # Update ingredient with latest cost
            client.table(Tables.MENU_ITEM_INGREDIENTS).update({
                "current_unit_cost": unit_cost,
                "cost_per_serving": cost_per_serving,
                "adjusted_cost_per_serving": adjusted_cost,
                "cost_source": "invoice_latest",
                "cost_last_updated": "now()",
            }).eq("id", ing["id"]).execute()

            ingredient_details.append({
                "name": ing["ingredient_name"],
                "quantity": ing["quantity_per_serving"],
                "unit": ing["unit"],
                "unit_cost": unit_cost,
                "cost_per_serving": round(adjusted_cost, 4),
                "waste_percent": ing.get("waste_percent", 0),
            })
        else:
            ingredient_details.append({
                "name": ing["ingredient_name"],
                "quantity": ing["quantity_per_serving"],
                "unit": ing["unit"],
                "unit_cost": None,
                "cost_per_serving": None,
                "error": "Preco nao encontrado",
            })

    # Calculate food cost percentage
    food_cost_pct = (total_cost / sale_price * 100) if sale_price > 0 else 0

    # Determine profitability tier
    if food_cost_pct > 40:
        tier = "negative"
    elif food_cost_pct > 35:
        tier = "low"
    elif food_cost_pct > 28:
        tier = "medium"
    else:
        tier = "high"

    # Update menu item with calculated values
    client.table(Tables.MENU_ITEMS).update({
        "food_cost": round(total_cost, 2),
        "food_cost_percent": round(food_cost_pct, 2),
        "contribution_margin": round(sale_price - total_cost, 2),
        "profitability_tier": tier,
    }).eq("id", menu_item_id).execute()

    return {
        "menu_item": menu_item["item_name"],
        "sale_price": sale_price,
        "food_cost": round(total_cost, 2),
        "food_cost_percent": round(food_cost_pct, 2),
        "contribution_margin": round(sale_price - total_cost, 2),
        "profitability_tier": tier,
        "ingredients": ingredient_details,
    }


async def calculate_restaurant_cmv(
    restaurant_id: int,
    total_revenue: float,
) -> dict:
    """
    Calculate overall restaurant CMV from invoices.

    Returns dict with CMV percentage and breakdown.
    """
    if total_revenue <= 0:
        return {"error": "Revenue must be positive"}

    invoices = await fetch_many(
        Tables.INVOICES,
        filters={"restaurant_id": restaurant_id, "status": "confirmed"},
    )

    total_purchases = sum(inv.get("total_amount", 0) or 0 for inv in invoices)
    cmv_percent = (total_purchases / total_revenue) * 100

    return {
        "total_purchases": total_purchases,
        "total_revenue": total_revenue,
        "cmv_percent": round(cmv_percent, 2),
        "invoice_count": len(invoices),
    }


async def get_category_breakdown(restaurant_id: int) -> dict:
    """
    Break down spending by product category.

    Uses keyword matching against product names from invoice line items
    to classify spending into standard restaurant categories.

    Returns dict with category names and their totals.
    """
    client = get_supabase_client()

    # Get line items from invoices for this restaurant
    result = client.table(Tables.INVOICE_LINE_ITEMS).select(
        "product_name_raw, total_price, invoices(restaurant_id)"
    ).execute()

    # Filter to this restaurant's items
    items = []
    for item in (result.data or []):
        inv = item.get("invoices", {}) or {}
        if inv.get("restaurant_id") == restaurant_id:
            items.append(item)

    # Category classification by keywords
    categories = {
        "Proteinas": 0.0,
        "Hortifruti": 0.0,
        "Mercearia": 0.0,
        "Laticinios": 0.0,
        "Bebidas": 0.0,
        "Outros": 0.0,
    }

    protein_keywords = [
        "carne", "frango", "peixe", "picanha", "alcatra", "costela",
        "file", "linguica", "bacon", "peito", "coxa", "asa", "camarao",
        "salmao", "tilapia", "porco", "bovina",
    ]
    produce_keywords = [
        "tomate", "cebola", "alface", "batata", "cenoura", "limao",
        "alho", "pimentao", "pepino", "abobrinha", "brocolis", "rucula",
        "banana", "laranja", "maca",
    ]
    grocery_keywords = [
        "arroz", "feijao", "oleo", "azeite", "sal", "acucar", "farinha",
        "macarrao", "molho", "tempero", "vinagre", "extrato", "catchup",
    ]
    dairy_keywords = [
        "leite", "queijo", "manteiga", "creme", "iogurte", "requeijao",
        "mussarela", "parmesao", "nata",
    ]
    beverage_keywords = [
        "cerveja", "refrigerante", "suco", "agua", "vinho", "cafe",
        "coca", "guarana", "cha",
    ]

    for item in items:
        name = (item.get("product_name_raw") or "").lower()
        total = item.get("total_price") or 0

        if any(kw in name for kw in protein_keywords):
            categories["Proteinas"] += total
        elif any(kw in name for kw in produce_keywords):
            categories["Hortifruti"] += total
        elif any(kw in name for kw in grocery_keywords):
            categories["Mercearia"] += total
        elif any(kw in name for kw in dairy_keywords):
            categories["Laticinios"] += total
        elif any(kw in name for kw in beverage_keywords):
            categories["Bebidas"] += total
        else:
            categories["Outros"] += total

    return categories


async def _get_ingredient_cost(ingredient: dict) -> Optional[float]:
    """
    Find the latest cost for an ingredient.

    Priority:
    1. Latest invoice line item matching by master_list_id
    2. Latest invoice line item matching by name
    3. pricing_history table (from procurement agent)
    """
    client = get_supabase_client()

    # Try by master_list_id first
    if ingredient.get("master_list_id"):
        result = client.table(Tables.INVOICE_LINE_ITEMS).select(
            "unit_price"
        ).eq("master_list_id", ingredient["master_list_id"]).order(
            "created_at", desc=True
        ).limit(1).execute()

        if result.data and result.data[0].get("unit_price"):
            return result.data[0]["unit_price"]

    # Try by name match
    result = client.table(Tables.INVOICE_LINE_ITEMS).select(
        "unit_price"
    ).ilike("product_name_raw", f"%{ingredient['ingredient_name']}%").order(
        "created_at", desc=True
    ).limit(1).execute()

    if result.data and result.data[0].get("unit_price"):
        return result.data[0]["unit_price"]

    # Try pricing_history (from procurement agent)
    if ingredient.get("master_list_id"):
        result = client.table(Tables.PRICING_HISTORY).select(
            "unit_price"
        ).eq("master_list_id", ingredient["master_list_id"]).is_(
            "end_date", "null"
        ).order("effective_date", desc=True).limit(1).execute()

        if result.data and result.data[0].get("unit_price"):
            return result.data[0]["unit_price"]

    return None
