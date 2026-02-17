"""
Engagement Scoring Service - Calculates and updates engagement scores.

Finance-side implementation with same logic as procurement side.
"""

import logging
from typing import Optional

from frepi_finance.shared.supabase_client import get_supabase_client, Tables

logger = logging.getLogger(__name__)


def recalculate_engagement(restaurant_id: int) -> Optional[dict]:
    """
    Recalculate the engagement score and level for a restaurant.

    Formula:
      score = (
          0.15 * onboarding_depth_signal +
          0.30 * drip_response_rate +
          0.25 * correction_signal +
          0.15 * session_frequency_signal +
          0.15 * reasoning_signal
      )
    """
    client = get_supabase_client()

    result = client.table(Tables.ENGAGEMENT_PROFILE).select(
        "*"
    ).eq("restaurant_id", restaurant_id).limit(1).execute()

    if not result.data:
        return None

    profile = result.data[0]

    depth = profile.get("onboarding_depth", 0)
    depth_signal = {0: 0.0, 5: 0.5, 10: 1.0}.get(depth, 0.0)

    answered = profile.get("drip_questions_answered", 0)
    skipped = profile.get("drip_questions_skipped", 0)
    total_drip = answered + skipped
    drip_response_rate = answered / total_drip if total_drip > 0 else 0.0

    corrections = profile.get("total_corrections", 0)
    correction_signal = min(corrections / 5.0, 1.0)

    sessions_30d = profile.get("sessions_last_30d", 0)
    session_frequency_signal = min(sessions_30d / 10.0, 1.0)

    with_reason = profile.get("corrections_with_reason", 0)
    reasoning_signal = with_reason / corrections if corrections > 0 else 0.0

    score = round(
        0.15 * depth_signal
        + 0.30 * drip_response_rate
        + 0.25 * correction_signal
        + 0.15 * session_frequency_signal
        + 0.15 * reasoning_signal,
        2,
    )
    score = max(0.0, min(1.0, score))

    if score >= 0.65:
        level, drip_per_session = "high", 2
    elif score >= 0.35:
        level, drip_per_session = "medium", 1
    elif score >= 0.10:
        level, drip_per_session = "low", 0
    else:
        level, drip_per_session = "dormant", 0

    client.table(Tables.ENGAGEMENT_PROFILE).update({
        "engagement_score": score,
        "engagement_level": level,
        "drip_questions_per_session": drip_per_session,
    }).eq("restaurant_id", restaurant_id).execute()

    logger.info(
        f"Engagement recalculated for restaurant {restaurant_id}: "
        f"score={score}, level={level}, drip={drip_per_session}"
    )

    return {
        "score": score,
        "level": level,
        "drip_per_session": drip_per_session,
    }


def increment_session_count(restaurant_id: int):
    """Increment the session counter for engagement tracking."""
    client = get_supabase_client()

    result = client.table(Tables.ENGAGEMENT_PROFILE).select(
        "sessions_last_30d"
    ).eq("restaurant_id", restaurant_id).limit(1).execute()

    if result.data:
        from datetime import datetime, timezone

        current = result.data[0].get("sessions_last_30d", 0)
        client.table(Tables.ENGAGEMENT_PROFILE).update({
            "sessions_last_30d": current + 1,
            "last_session_at": datetime.now(timezone.utc).isoformat(),
        }).eq("restaurant_id", restaurant_id).execute()
