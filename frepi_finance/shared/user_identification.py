"""
User identification for the finance bot.

Checks finance_onboarding and restaurant_people tables to determine
if a user has completed finance onboarding.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from frepi_finance.shared.supabase_client import get_supabase_client, Tables

logger = logging.getLogger(__name__)


@dataclass
class FinanceUserIdentification:
    """Result of finance user identification."""
    is_known: bool = False
    restaurant_id: Optional[int] = None
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    restaurant_name: Optional[str] = None
    onboarding_complete: bool = False


async def identify_finance_user(telegram_chat_id: int) -> FinanceUserIdentification:
    """
    Identify a user for the finance bot.

    Checks:
    1. finance_onboarding table for completed onboarding
    2. restaurant_people table (shared with procurement) for existing users

    Args:
        telegram_chat_id: The Telegram chat ID

    Returns:
        FinanceUserIdentification with user details
    """
    client = get_supabase_client()
    chat_id_str = str(telegram_chat_id)

    # Check finance_onboarding first
    try:
        result = (
            client.table(Tables.FINANCE_ONBOARDING)
            .select("*")
            .eq("telegram_chat_id", telegram_chat_id)
            .eq("status", "completed")
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            onboarding = result.data[0]
            return FinanceUserIdentification(
                is_known=True,
                restaurant_id=onboarding.get("restaurant_id"),
                person_id=onboarding.get("person_id"),
                person_name=onboarding.get("person_name"),
                restaurant_name=onboarding.get("restaurant_name"),
                onboarding_complete=True,
            )
    except Exception as e:
        logger.warning(f"Error checking finance_onboarding: {e}")

    # Check in-progress onboarding
    try:
        result = (
            client.table(Tables.FINANCE_ONBOARDING)
            .select("*")
            .eq("telegram_chat_id", telegram_chat_id)
            .eq("status", "in_progress")
            .limit(1)
            .execute()
        )
        if result.data:
            onboarding = result.data[0]
            return FinanceUserIdentification(
                is_known=True,
                restaurant_id=onboarding.get("restaurant_id"),
                person_name=onboarding.get("person_name"),
                restaurant_name=onboarding.get("restaurant_name"),
                onboarding_complete=False,
            )
    except Exception as e:
        logger.warning(f"Error checking in-progress onboarding: {e}")

    # Check restaurant_people table (shared with procurement agent)
    try:
        result = (
            client.table(Tables.RESTAURANT_PEOPLE)
            .select("id, restaurant_id, first_name, full_name")
            .eq("whatsapp_number", chat_id_str)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if result.data:
            person = result.data[0]
            return FinanceUserIdentification(
                is_known=True,
                restaurant_id=person.get("restaurant_id"),
                person_id=person["id"],
                person_name=person.get("first_name") or person.get("full_name"),
                onboarding_complete=False,  # Known in procurement but not in finance
            )
    except Exception as e:
        logger.warning(f"Error checking restaurant_people: {e}")

    # Unknown user
    return FinanceUserIdentification(is_known=False)
