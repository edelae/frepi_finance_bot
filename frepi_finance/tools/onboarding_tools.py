"""
Onboarding tools - Finance-specific user registration.

5-step flow: restaurant_name -> person_name -> relationship -> city_state -> savings_opportunity
"""

from typing import Any

from frepi_finance.shared.supabase_client import (
    get_supabase_client, Tables, fetch_one, insert_one, update_one,
)


ONBOARDING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_onboarding_step",
            "description": "Save a single step of the finance onboarding process. Call this as each piece of information is collected from the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["restaurant_name", "person_name", "is_owner", "relationship", "city", "state", "savings_opportunity", "wants_invoice_upload", "engagement_choice"],
                        "description": "Which onboarding field to save"
                    },
                    "value": {
                        "type": "string",
                        "description": "The value to save for this field"
                    }
                },
                "required": ["field", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_onboarding",
            "description": "Mark the finance onboarding as complete. Call this after all 5 steps are finished.",
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
            "name": "check_existing_user",
            "description": "Check if this Telegram user already exists in the Frepi procurement system.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


async def execute_onboarding_tool(tool_name: str, args: dict[str, Any], session) -> dict:
    """Execute an onboarding tool."""

    if tool_name == "save_onboarding_step":
        field_name = args["field"]
        value = args["value"]

        client = get_supabase_client()

        # Get or create onboarding session
        result = (
            client.table(Tables.FINANCE_ONBOARDING)
            .select("*")
            .eq("telegram_chat_id", session.telegram_chat_id)
            .eq("status", "in_progress")
            .limit(1)
            .execute()
        )

        if result.data:
            # Update existing session
            session_id = result.data[0]["id"]
            update_data = {field_name: value}

            # Map field to next phase
            phase_map = {
                "restaurant_name": "person_name",
                "person_name": "relationship",
                "is_owner": "city_state",
                "relationship": "city_state",
                "city": "savings_opportunity",
                "state": "savings_opportunity",
                "savings_opportunity": "invoice_offer",
                "wants_invoice_upload": "engagement_gauge",
                "engagement_choice": "completed",
            }
            if field_name in phase_map:
                update_data["current_phase"] = phase_map[field_name]

            client.table(Tables.FINANCE_ONBOARDING).update(update_data).eq("id", session_id).execute()

            # Update session memory
            if field_name == "restaurant_name":
                session.restaurant_name = value
            elif field_name == "person_name":
                session.person_name = value

        else:
            # Create new session
            data = {
                "telegram_chat_id": session.telegram_chat_id,
                "status": "in_progress",
                "current_phase": "person_name" if field_name == "restaurant_name" else field_name,
                field_name: value,
            }

            # Link to existing restaurant if known
            if session.restaurant_id:
                data["restaurant_id"] = session.restaurant_id

            result = client.table(Tables.FINANCE_ONBOARDING).insert(data).execute()

        return {"success": True, "field": field_name, "saved": value}

    elif tool_name == "complete_onboarding":
        client = get_supabase_client()

        result = (
            client.table(Tables.FINANCE_ONBOARDING)
            .update({
                "status": "completed",
                "current_phase": "completed",
                "completed_at": "now()",
            })
            .eq("telegram_chat_id", session.telegram_chat_id)
            .eq("status", "in_progress")
            .execute()
        )

        session.is_new_user = False
        session.onboarding_complete = True

        return {"success": True, "message": "Onboarding completed"}

    elif tool_name == "check_existing_user":
        from frepi_finance.shared.user_identification import identify_finance_user

        identification = await identify_finance_user(session.telegram_chat_id)

        return {
            "is_known": identification.is_known,
            "restaurant_id": identification.restaurant_id,
            "person_name": identification.person_name,
            "restaurant_name": identification.restaurant_name,
            "has_procurement_account": identification.is_known and not identification.onboarding_complete,
        }

    return {"error": f"Unknown onboarding tool: {tool_name}"}
