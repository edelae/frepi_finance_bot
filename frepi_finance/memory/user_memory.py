"""
User Memory - Persistent per-restaurant context backed by database.

Inspired by OpenClaw's USER.md pattern. Loads restaurant profile,
financial context, and learned preferences from the database.
This data is injected into prompts as Layer 1 (User Memory).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def load_user_memory(restaurant_id: int) -> Optional[dict]:
    """
    Load persistent memory for a restaurant.

    Aggregates data from finance_onboarding and restaurants tables
    to build a context dict for prompt injection.

    Args:
        restaurant_id: The restaurant ID

    Returns:
        Dict with restaurant context or None
    """
    from frepi_finance.shared.supabase_client import get_supabase_client, Tables

    client = get_supabase_client()
    memory = {}

    # Load from finance_onboarding
    try:
        result = (
            client.table(Tables.FINANCE_ONBOARDING)
            .select("*")
            .eq("restaurant_id", restaurant_id)
            .eq("status", "completed")
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            onboarding = result.data[0]
            memory["restaurant_name"] = onboarding.get("restaurant_name")
            memory["person_name"] = onboarding.get("person_name")
            memory["is_owner"] = onboarding.get("is_owner")
            memory["city"] = onboarding.get("city")
            memory["state"] = onboarding.get("state")
            memory["savings_opportunity"] = onboarding.get("savings_opportunity")
    except Exception as e:
        logger.warning(f"Failed to load finance onboarding: {e}")

    # Load from restaurants table (shared with procurement agent)
    try:
        result = (
            client.table(Tables.RESTAURANTS)
            .select("restaurant_name, quality_requirements, price_sensitivity")
            .eq("id", restaurant_id)
            .limit(1)
            .execute()
        )
        if result.data:
            restaurant = result.data[0]
            if not memory.get("restaurant_name"):
                memory["restaurant_name"] = restaurant.get("restaurant_name")
            if restaurant.get("price_sensitivity"):
                memory["price_sensitivity"] = restaurant["price_sensitivity"]
    except Exception as e:
        logger.warning(f"Failed to load restaurant data: {e}")

    # Load latest monthly report CMV target
    try:
        result = (
            client.table(Tables.MONTHLY_FINANCIAL_REPORTS)
            .select("cmv_target_percent, cmv_percent, report_month, report_year")
            .eq("restaurant_id", restaurant_id)
            .order("report_year", desc=True)
            .order("report_month", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            report = result.data[0]
            memory["cmv_target"] = report.get("cmv_target_percent", 32.0)
            memory["last_cmv"] = report.get("cmv_percent")
            memory["last_report_period"] = f"{report['report_month']}/{report['report_year']}"
    except Exception as e:
        logger.warning(f"Failed to load monthly report data: {e}")

    return memory if memory else None


async def save_user_memory_field(restaurant_id: int, field: str, value) -> bool:
    """
    Save a specific memory field for a restaurant.

    Args:
        restaurant_id: The restaurant ID
        field: Field name to update
        value: New value

    Returns:
        True if saved successfully
    """
    from frepi_finance.shared.supabase_client import get_supabase_client, Tables

    try:
        client = get_supabase_client()

        # Update in finance_onboarding
        result = (
            client.table(Tables.FINANCE_ONBOARDING)
            .update({field: value})
            .eq("restaurant_id", restaurant_id)
            .eq("status", "completed")
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        logger.error(f"Failed to save memory field {field}: {e}")
        return False
