"""
Price Trend Analysis - Detect and report significant price changes.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from frepi_finance.shared.supabase_client import (
    get_supabase_client,
    fetch_many,
    fetch_one,
    update_one,
    Tables,
)

logger = logging.getLogger(__name__)

# Price change above this % is considered significant
SIGNIFICANT_CHANGE_THRESHOLD = 10.0


async def compute_trends_for_invoice(invoice_id: str, restaurant_id: int) -> list[dict]:
    """
    Compute price trends for all line items in an invoice.

    Compares each item's price against the most recent previous price
    from the same supplier for the same product.

    Returns list of significant changes.
    """
    client = get_supabase_client()

    # Get line items for this invoice
    items = client.table(Tables.INVOICE_LINE_ITEMS).select(
        "id, product_name_raw, unit_price, unit"
    ).eq("invoice_id", invoice_id).execute()

    # Get the invoice's supplier
    invoice = client.table(Tables.INVOICES).select(
        "supplier_name_extracted, invoice_date"
    ).eq("id", invoice_id).limit(1).execute()

    if not invoice.data:
        return []

    supplier_name = invoice.data[0].get("supplier_name_extracted")
    invoice_date = invoice.data[0].get("invoice_date")
    trends = []

    for item in (items.data or []):
        product_name = item.get("product_name_raw")
        current_price = item.get("unit_price")

        if not product_name or not current_price:
            continue

        # Find previous price for same product from same supplier
        prev = client.table(Tables.INVOICE_LINE_ITEMS).select(
            "unit_price"
        ).eq("product_name_raw", product_name).neq(
            "invoice_id", invoice_id
        ).order("created_at", desc=True).limit(1).execute()

        if prev.data:
            prev_price = prev.data[0].get("unit_price")
            if prev_price and prev_price > 0:
                change_pct = ((current_price - prev_price) / prev_price) * 100
                is_significant = abs(change_pct) >= SIGNIFICANT_CHANGE_THRESHOLD

                # Update line item with trend data
                update_data = {
                    "previous_price": prev_price,
                    "price_change_percent": round(change_pct, 2),
                    "price_trend": "up" if change_pct > 0 else "down" if change_pct < 0 else "stable",
                    "is_significant_change": is_significant,
                }
                client.table(Tables.INVOICE_LINE_ITEMS).update(
                    update_data
                ).eq("id", item["id"]).execute()

                if is_significant:
                    trends.append({
                        "product": product_name,
                        "previous_price": prev_price,
                        "current_price": current_price,
                        "change_percent": round(change_pct, 2),
                        "direction": "up" if change_pct > 0 else "down",
                    })
        else:
            # First time seeing this product
            client.table(Tables.INVOICE_LINE_ITEMS).update({
                "price_trend": "new",
            }).eq("id", item["id"]).execute()

    return trends


async def get_product_price_trend(
    restaurant_id: int, product_name: str, months: int = 6
) -> dict:
    """
    Get price history for a product across all invoices.

    Args:
        restaurant_id: Restaurant to query
        product_name: Partial product name to search
        months: How many months of history to look back

    Returns:
        Dict with price history, data points, and overall change percentage
    """
    client = get_supabase_client()

    result = client.table(Tables.INVOICE_LINE_ITEMS).select(
        "unit_price, unit, product_name_raw, created_at, "
        "invoices(supplier_name_extracted, invoice_date)"
    ).ilike("product_name_raw", f"%{product_name}%").order(
        "created_at", desc=True
    ).limit(50).execute()

    history = []
    for item in (result.data or []):
        inv = item.get("invoices", {}) or {}
        history.append({
            "date": inv.get("invoice_date"),
            "supplier": inv.get("supplier_name_extracted"),
            "price": item.get("unit_price"),
            "unit": item.get("unit"),
        })

    # Calculate overall trend
    if len(history) >= 2:
        latest = history[0].get("price", 0) or 0
        oldest = history[-1].get("price", 0) or 0
        if oldest > 0:
            overall_change = ((latest - oldest) / oldest) * 100
        else:
            overall_change = 0
    else:
        overall_change = 0

    return {
        "product": product_name,
        "history": history,
        "data_points": len(history),
        "overall_change_percent": round(overall_change, 2),
    }


async def check_watchlist_alerts(restaurant_id: int) -> list[dict]:
    """
    Check all active watchlist items for price changes.

    Compares the current price (from latest invoices or pricing_history)
    against the stored price on each watchlist entry. Respects alert
    cooldown periods and alert type filters.

    Returns list of alert dicts for items that triggered.
    """
    entries = await fetch_many(
        Tables.PRODUCT_PRICE_WATCHLIST,
        filters={"restaurant_id": restaurant_id, "is_active": True},
    )

    alerts = []
    for entry in entries:
        # Check cooldown period
        last_alert = entry.get("last_alert_sent_at")
        cooldown_hours = entry.get("alert_cooldown_hours", 24)
        if last_alert:
            try:
                last_dt = datetime.fromisoformat(last_alert.replace("Z", "+00:00"))
                if datetime.now(last_dt.tzinfo) - last_dt < timedelta(hours=cooldown_hours):
                    continue
            except (ValueError, TypeError):
                pass

        # Get current price from latest sources
        new_price = await _get_latest_price(entry["master_list_id"])
        stored_price = entry.get("current_price")

        if new_price is None or stored_price is None:
            # Update last checked timestamp even if no price found
            await update_one(
                Tables.PRODUCT_PRICE_WATCHLIST,
                {"id": entry["id"]},
                {"last_checked_at": datetime.utcnow().isoformat()},
            )
            continue

        # Calculate change percentage
        if stored_price == 0:
            continue

        change_pct = ((new_price - stored_price) / stored_price) * 100
        alert_type = entry.get("alert_type", "any_change")
        threshold = entry.get("threshold_percent", 10.0)
        should_alert = False

        if alert_type == "any_change" and abs(change_pct) >= threshold:
            should_alert = True
        elif alert_type == "price_drop" and change_pct <= -threshold:
            should_alert = True
        elif alert_type == "price_increase" and change_pct >= threshold:
            should_alert = True
        elif alert_type == "threshold":
            target = entry.get("target_price")
            if target and new_price >= target:
                should_alert = True

        if should_alert:
            # Get product name for display
            product = await fetch_one(Tables.MASTER_LIST, {"id": entry["master_list_id"]})
            product_name = product.get("product_name", "Unknown") if product else "Unknown"

            alerts.append({
                "watchlist_id": entry["id"],
                "product_name": product_name,
                "old_price": stored_price,
                "new_price": new_price,
                "change_percent": round(change_pct, 2),
                "direction": "up" if change_pct > 0 else "down",
                "alert_type": alert_type,
            })

            # Update watchlist entry with new price and alert timestamp
            await update_one(
                Tables.PRODUCT_PRICE_WATCHLIST,
                {"id": entry["id"]},
                {
                    "current_price": new_price,
                    "last_alert_sent_at": datetime.utcnow().isoformat(),
                    "last_checked_at": datetime.utcnow().isoformat(),
                },
            )
        else:
            # No alert needed, but update current price and last checked
            await update_one(
                Tables.PRODUCT_PRICE_WATCHLIST,
                {"id": entry["id"]},
                {
                    "current_price": new_price,
                    "last_checked_at": datetime.utcnow().isoformat(),
                },
            )

    return alerts


async def _get_latest_price(master_list_id: int) -> Optional[float]:
    """
    Get the latest price for a product from pricing_history or invoices.

    Priority:
    1. pricing_history table (from procurement agent)
    2. Invoice line items (from finance agent)
    """
    # Try pricing_history first
    prices = await fetch_many(
        Tables.PRICING_HISTORY,
        filters={"master_list_id": master_list_id},
        order_by="-effective_date",
        limit=1,
    )
    if prices and prices[0].get("unit_price"):
        return prices[0]["unit_price"]

    # Fallback to invoice line items
    try:
        client = get_supabase_client()
        result = (
            client.table(Tables.INVOICE_LINE_ITEMS)
            .select("unit_price")
            .eq("master_list_id", master_list_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0].get("unit_price")
    except Exception:
        pass

    return None
