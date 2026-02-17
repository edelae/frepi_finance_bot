"""
Supabase client for database operations.

Provides connection management and base operations for Frepi Finance tables.
Shares the same Supabase instance as the procurement agent.
"""

from typing import Any, Optional

from supabase import create_client, Client

from frepi_finance.config import get_config


_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Get the Supabase client instance."""
    global _client
    if _client is None:
        config = get_config()
        _client = create_client(config.supabase_url, config.supabase_key)
    return _client


def reset_client():
    """Reset the client (useful for testing)."""
    global _client
    _client = None


class Tables:
    """Table name constants."""

    # ===== Existing tables (shared with procurement agent, READ-ONLY from finance) =====
    MASTER_LIST = "master_list"
    SUPPLIERS = "suppliers"
    RESTAURANTS = "restaurants"
    RESTAURANT_PEOPLE = "restaurant_people"
    SUPPLIER_MAPPED_PRODUCTS = "supplier_mapped_products"
    PRICING_HISTORY = "pricing_history"
    PURCHASE_ORDERS = "purchase_orders"

    # ===== Finance-specific tables =====
    FINANCE_ONBOARDING = "finance_onboarding"
    INVOICES = "invoices"
    INVOICE_LINE_ITEMS = "invoice_line_items"
    MENU_ITEMS = "menu_items"
    MENU_ITEM_INGREDIENTS = "menu_item_ingredients"
    MENU_COST_HISTORY = "menu_cost_history"
    PRODUCT_PRICE_WATCHLIST = "product_price_watchlist"
    MONTHLY_FINANCIAL_REPORTS = "monthly_financial_reports"
    PROMPT_COMPOSITION_LOG = "prompt_composition_log"

    # Preference & engagement tables (shared across agents)
    PREFERENCE_COLLECTION_QUEUE = "preference_collection_queue"
    ENGAGEMENT_PROFILE = "engagement_profile"
    PREFERENCE_CORRECTIONS = "preference_corrections"


async def fetch_one(table: str, filters: dict[str, Any]) -> Optional[dict]:
    """Fetch a single record from a table."""
    client = get_supabase_client()
    query = client.table(table).select("*")
    for column, value in filters.items():
        query = query.eq(column, value)
    result = query.limit(1).execute()
    if result.data:
        return result.data[0]
    return None


async def fetch_many(
    table: str,
    filters: Optional[dict[str, Any]] = None,
    order_by: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """Fetch multiple records from a table."""
    client = get_supabase_client()
    query = client.table(table).select("*")
    if filters:
        for column, value in filters.items():
            if isinstance(value, list):
                query = query.in_(column, value)
            else:
                query = query.eq(column, value)
    if order_by:
        if order_by.startswith("-"):
            query = query.order(order_by[1:], desc=True)
        else:
            query = query.order(order_by)
    if limit:
        query = query.limit(limit)
    result = query.execute()
    return result.data or []


async def insert_one(table: str, data: dict[str, Any]) -> dict:
    """Insert a single record into a table."""
    client = get_supabase_client()
    result = client.table(table).insert(data).execute()
    if result.data:
        return result.data[0]
    raise Exception(f"Insert failed: {result}")


async def update_one(
    table: str, filters: dict[str, Any], data: dict[str, Any]
) -> Optional[dict]:
    """Update a single record in a table."""
    client = get_supabase_client()
    query = client.table(table).update(data)
    for column, value in filters.items():
        query = query.eq(column, value)
    result = query.execute()
    if result.data:
        return result.data[0]
    return None


async def execute_rpc(function_name: str, params: dict[str, Any]) -> Any:
    """Execute a Supabase RPC function."""
    client = get_supabase_client()
    result = client.rpc(function_name, params).execute()
    return result.data


async def test_connection() -> bool:
    """Test the database connection."""
    try:
        client = get_supabase_client()
        result = client.table(Tables.RESTAURANTS).select("id").limit(1).execute()
        return True
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False
