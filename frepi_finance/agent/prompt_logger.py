"""
Prompt Logger - Records every prompt composition for feedback loop analysis.

Writes to the prompt_composition_log table in Supabase. This enables:
- Tracking which intents are most common
- Measuring correction rates by intent
- Comparing prompt version effectiveness
- Identifying weak areas for prompt improvement
"""

import logging
from typing import Optional

from frepi_finance.agent.prompt_composer import ComposedPrompt

logger = logging.getLogger(__name__)


async def log_prompt_composition(
    composed: ComposedPrompt,
    restaurant_id: Optional[int],
    telegram_chat_id: Optional[int],
    session_id: Optional[str],
    user_message: str,
    model_used: str = "gpt-4o",
) -> Optional[str]:
    """
    Log a prompt composition to the database.

    Args:
        composed: The composed prompt result
        restaurant_id: Restaurant ID if known
        telegram_chat_id: Telegram chat ID
        session_id: Session identifier
        user_message: The original user message
        model_used: Which model was used

    Returns:
        The log entry ID or None if logging failed
    """
    try:
        from frepi_finance.shared.supabase_client import get_supabase_client, Tables

        client = get_supabase_client()

        data = {
            "restaurant_id": restaurant_id,
            "telegram_chat_id": telegram_chat_id,
            "session_id": session_id,
            "user_message": user_message,
            "detected_intent": composed.detected_intent,
            "intent_confidence": composed.intent_confidence,
            "base_prompt_version": _get_soul_version(),
            "injected_components": [
                {
                    "name": c.name,
                    "layer": c.layer,
                    "token_estimate": c.token_estimate,
                }
                for c in composed.components
            ],
            "context_items_count": len(composed.components),
            "final_prompt_token_estimate": composed.total_token_estimate,
            "model_used": model_used,
        }

        result = client.table(Tables.PROMPT_COMPOSITION_LOG).insert(data).execute()

        if result.data:
            log_id = result.data[0]["id"]
            logger.info(f"📝 Prompt logged: {log_id}")
            return log_id

    except Exception as e:
        # Logging should never break the main flow
        logger.error(f"Failed to log prompt composition: {e}")

    return None


async def log_prompt_result(
    log_id: str,
    execution_time_ms: int,
    tool_calls_made: list[dict],
    response_length: int,
    error_occurred: bool = False,
    error_message: Optional[str] = None,
):
    """
    Update a prompt log entry with execution results.

    Called after the GPT-4 response is received.
    """
    try:
        from frepi_finance.shared.supabase_client import get_supabase_client, Tables

        client = get_supabase_client()

        data = {
            "execution_time_ms": execution_time_ms,
            "tool_calls_made": tool_calls_made,
            "response_length": response_length,
            "error_occurred": error_occurred,
            "error_message": error_message,
        }

        client.table(Tables.PROMPT_COMPOSITION_LOG).update(data).eq("id", log_id).execute()

    except Exception as e:
        logger.error(f"Failed to log prompt result: {e}")


async def log_user_feedback(
    log_id: str,
    feedback: str,
    correction_details: Optional[str] = None,
):
    """
    Log user feedback for a prompt interaction.

    Args:
        log_id: The prompt log entry ID
        feedback: 'positive', 'negative', or 'correction'
        correction_details: What the user corrected
    """
    try:
        from frepi_finance.shared.supabase_client import get_supabase_client, Tables

        client = get_supabase_client()

        data = {
            "user_feedback": feedback,
            "correction_details": correction_details,
        }

        client.table(Tables.PROMPT_COMPOSITION_LOG).update(data).eq("id", log_id).execute()
        logger.info(f"📝 Feedback logged: {feedback} for {log_id}")

    except Exception as e:
        logger.error(f"Failed to log feedback: {e}")


def _get_soul_version() -> str:
    """Get the current SOUL prompt version."""
    try:
        from frepi_finance.soul.soul import SOUL_VERSION
        return SOUL_VERSION
    except ImportError:
        return "unknown"
