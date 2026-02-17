"""
Preference tools - Finance-specific preference collection and correction.

Handles engagement gauge, targeted preferences, drip responses, and corrections.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from frepi_finance.shared.supabase_client import (
    get_supabase_client, Tables, fetch_one, insert_one, update_one,
)

logger = logging.getLogger(__name__)


PREFERENCE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_engagement_choice_finance",
            "description": "Save the user's engagement choice during onboarding. 1=Top 5 (quick), 2=Top 10 (complete), 3=Skip.",
            "parameters": {
                "type": "object",
                "properties": {
                    "choice": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": "1=Top 5, 2=Top 10, 3=Skip"
                    }
                },
                "required": ["choice"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_product_preference_finance",
            "description": "Save a product preference collected during onboarding or drip questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "The product name"
                    },
                    "preference_type": {
                        "type": "string",
                        "enum": ["brand", "price_max", "quality", "supplier", "specification"],
                        "description": "Type of preference"
                    },
                    "value": {
                        "type": "string",
                        "description": "The preference value"
                    }
                },
                "required": ["product_name", "preference_type", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "answer_drip_question",
            "description": "Save the user's response to a drip preference question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "The product being asked about"
                    },
                    "preference_type": {
                        "type": "string",
                        "enum": ["brand", "price_max", "quality", "supplier", "specification"],
                        "description": "Type of preference"
                    },
                    "value": {
                        "type": "string",
                        "description": "The user's answer"
                    },
                    "skip": {
                        "type": "boolean",
                        "description": "True if the user wants to skip this question",
                        "default": False
                    }
                },
                "required": ["product_name", "preference_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_preference_correction",
            "description": "Save when a user corrects a recommendation or suggestion. Always ask WHY they prefer the correction before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "The product name (optional for global corrections)"
                    },
                    "preference_type": {
                        "type": "string",
                        "enum": ["brand", "price_max", "quality", "supplier", "specification"],
                        "description": "Type of preference being corrected"
                    },
                    "original_value": {
                        "type": "string",
                        "description": "What the system suggested"
                    },
                    "corrected_value": {
                        "type": "string",
                        "description": "What the user wants instead"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why the user prefers this (key learning data)"
                    },
                    "context": {
                        "type": "string",
                        "enum": ["onboarding", "drip", "purchase", "manual"],
                        "description": "Where this correction happened"
                    }
                },
                "required": ["preference_type", "corrected_value", "context"]
            }
        }
    },
]


async def execute_preference_tool(tool_name: str, args: dict[str, Any], session) -> dict:
    """Execute a preference tool."""

    if tool_name == "save_engagement_choice_finance":
        return await _save_engagement_choice(args["choice"], session)

    elif tool_name == "save_product_preference_finance":
        return await _save_product_preference(
            args["product_name"], args["preference_type"], args["value"], session
        )

    elif tool_name == "answer_drip_question":
        return await _answer_drip_question(
            args["product_name"],
            args["preference_type"],
            args.get("value"),
            args.get("skip", False),
            session,
        )

    elif tool_name == "save_preference_correction":
        return await _save_preference_correction(
            args.get("product_name"),
            args["preference_type"],
            args.get("original_value"),
            args["corrected_value"],
            args.get("reason"),
            args["context"],
            session,
        )

    return {"error": f"Unknown preference tool: {tool_name}"}


async def _save_engagement_choice(choice: int, session) -> dict:
    """Save engagement choice to finance_onboarding."""
    client = get_supabase_client()
    now = datetime.now(timezone.utc).isoformat()

    # Update finance_onboarding
    client.table(Tables.FINANCE_ONBOARDING).update({
        "engagement_choice": choice,
        "engagement_choice_at": now,
    }).eq(
        "telegram_chat_id", session.telegram_chat_id
    ).eq("status", "in_progress").execute()

    # Create or update engagement_profile if restaurant exists
    if session.restaurant_id:
        depth_map = {1: 5, 2: 10, 3: 0}
        onboarding_depth = depth_map.get(choice, 0)
        depth_signal = {0: 0.0, 5: 0.5, 10: 1.0}.get(onboarding_depth, 0.0)
        initial_score = round(0.15 * depth_signal, 2)

        if initial_score >= 0.65:
            level, drip = "high", 2
        elif initial_score >= 0.35:
            level, drip = "medium", 1
        else:
            level, drip = "low", 0

        # Upsert engagement profile
        existing = await fetch_one(
            Tables.ENGAGEMENT_PROFILE,
            {"restaurant_id": session.restaurant_id},
        )
        if existing:
            await update_one(
                Tables.ENGAGEMENT_PROFILE,
                {"restaurant_id": session.restaurant_id},
                {
                    "onboarding_depth": onboarding_depth,
                    "engagement_score": initial_score,
                    "engagement_level": level,
                    "drip_questions_per_session": drip,
                },
            )
        else:
            await insert_one(Tables.ENGAGEMENT_PROFILE, {
                "restaurant_id": session.restaurant_id,
                "onboarding_depth": onboarding_depth,
                "engagement_score": initial_score,
                "engagement_level": level,
                "drip_questions_per_session": drip,
            })

    choice_labels = {1: "Top 5", 2: "Top 10", 3: "Pular"}
    return {"success": True, "choice": choice, "label": choice_labels.get(choice, "?")}


async def _save_product_preference(
    product_name: str, preference_type: str, value: str, session,
) -> dict:
    """Save a single product preference."""
    if not session.restaurant_id:
        return {"error": "No restaurant linked yet"}

    client = get_supabase_client()

    # Find product in master_list
    result = client.table(Tables.MASTER_LIST).select("id").eq(
        "restaurant_id", session.restaurant_id
    ).ilike("product_name", f"%{product_name}%").limit(1).execute()

    master_list_id = result.data[0]["id"] if result.data else None

    if master_list_id:
        # Build preference update
        pref_data = {}
        source = "onboarding"
        now = datetime.now(timezone.utc).isoformat()

        if preference_type == "brand":
            pref_data["brand_preferences"] = {"brand": value}
            pref_data["brand_preferences_source"] = source
            pref_data["brand_preferences_added_at"] = now
        elif preference_type == "price_max":
            pref_data["price_preference"] = value
            pref_data["price_preference_source"] = source
            pref_data["price_preference_added_at"] = now
        elif preference_type == "quality":
            pref_data["quality_preference"] = {"quality": value}
            pref_data["quality_preference_source"] = source
            pref_data["quality_preference_added_at"] = now

        if pref_data:
            pref_data["restaurant_id"] = session.restaurant_id
            pref_data["master_list_id"] = master_list_id
            pref_data["is_active"] = True

            # Upsert
            existing = client.table(
                Tables.RESTAURANT_PRODUCT_PREFERENCES
            ).select("id").eq(
                "restaurant_id", session.restaurant_id
            ).eq("master_list_id", master_list_id).limit(1).execute()

            if existing.data:
                client.table(Tables.RESTAURANT_PRODUCT_PREFERENCES).update(
                    pref_data
                ).eq("id", existing.data[0]["id"]).execute()
            else:
                client.table(Tables.RESTAURANT_PRODUCT_PREFERENCES).insert(
                    pref_data
                ).execute()

        # Update queue status
        client.table(Tables.PREFERENCE_COLLECTION_QUEUE).update({
            "preference_status": "collected",
        }).eq(
            "restaurant_id", session.restaurant_id
        ).eq("master_list_id", master_list_id).execute()

    return {
        "success": True,
        "product": product_name,
        "type": preference_type,
        "value": value,
    }


async def _answer_drip_question(
    product_name: str,
    preference_type: str,
    value: str | None,
    skip: bool,
    session,
) -> dict:
    """Handle a drip question response."""
    if not session.restaurant_id:
        return {"error": "No restaurant linked"}

    client = get_supabase_client()

    # Update engagement profile counters
    profile = await fetch_one(
        Tables.ENGAGEMENT_PROFILE,
        {"restaurant_id": session.restaurant_id},
    )

    if profile:
        if skip:
            await update_one(
                Tables.ENGAGEMENT_PROFILE,
                {"restaurant_id": session.restaurant_id},
                {"drip_questions_skipped": profile["drip_questions_skipped"] + 1},
            )
        else:
            await update_one(
                Tables.ENGAGEMENT_PROFILE,
                {"restaurant_id": session.restaurant_id},
                {"drip_questions_answered": profile["drip_questions_answered"] + 1},
            )

        # Increment asked counter
        await update_one(
            Tables.ENGAGEMENT_PROFILE,
            {"restaurant_id": session.restaurant_id},
            {"drip_questions_asked": profile["drip_questions_asked"] + 1},
        )

    if not skip and value:
        # Save the actual preference
        return await _save_product_preference(
            product_name, preference_type, value, session
        )

    # Update queue status to skipped
    result = client.table(Tables.MASTER_LIST).select("id").eq(
        "restaurant_id", session.restaurant_id
    ).ilike("product_name", f"%{product_name}%").limit(1).execute()

    if result.data:
        client.table(Tables.PREFERENCE_COLLECTION_QUEUE).update({
            "preference_status": "skipped",
            "asked_count": (profile or {}).get("drip_questions_asked", 0) + 1,
            "last_asked_at": datetime.now(timezone.utc).isoformat(),
        }).eq(
            "restaurant_id", session.restaurant_id
        ).eq("master_list_id", result.data[0]["id"]).execute()

    return {"success": True, "skipped": True, "product": product_name}


async def _save_preference_correction(
    product_name: str | None,
    preference_type: str,
    original_value: str | None,
    corrected_value: str,
    reason: str | None,
    context: str,
    session,
) -> dict:
    """Save a preference correction with reasoning."""
    if not session.restaurant_id:
        return {"error": "No restaurant linked"}

    client = get_supabase_client()

    # Find master_list_id if product given
    master_list_id = None
    if product_name:
        result = client.table(Tables.MASTER_LIST).select("id").eq(
            "restaurant_id", session.restaurant_id
        ).ilike("product_name", f"%{product_name}%").limit(1).execute()
        if result.data:
            master_list_id = result.data[0]["id"]

    # Insert correction record
    correction_data = {
        "restaurant_id": session.restaurant_id,
        "master_list_id": master_list_id,
        "preference_type": preference_type,
        "original_value": json.dumps(original_value) if original_value else None,
        "corrected_value": json.dumps(corrected_value),
        "correction_reason": reason,
        "correction_context": context,
    }

    # Get person_id if available
    if hasattr(session, "person_id") and session.person_id:
        correction_data["person_id"] = session.person_id

    await insert_one(Tables.PREFERENCE_CORRECTIONS, correction_data)

    # Update the actual preference
    if master_list_id:
        await _save_product_preference(
            product_name, preference_type, corrected_value, session
        )

    # Update engagement profile
    profile = await fetch_one(
        Tables.ENGAGEMENT_PROFILE,
        {"restaurant_id": session.restaurant_id},
    )
    if profile:
        updates = {"total_corrections": profile["total_corrections"] + 1}
        if reason:
            updates["corrections_with_reason"] = profile["corrections_with_reason"] + 1
        await update_one(
            Tables.ENGAGEMENT_PROFILE,
            {"restaurant_id": session.restaurant_id},
            updates,
        )

    # Recalculate engagement score after correction
    try:
        from frepi_finance.services.engagement_scoring import recalculate_engagement
        recalculate_engagement(session.restaurant_id)
    except Exception as e:
        logger.warning(f"Failed to recalculate engagement: {e}")

    return {
        "success": True,
        "product": product_name,
        "type": preference_type,
        "corrected_to": corrected_value,
        "has_reason": bool(reason),
    }
