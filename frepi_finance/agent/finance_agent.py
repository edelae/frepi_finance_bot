"""
Frepi Finance Agent - GPT-4 powered restaurant financial intelligence.

Uses OpenAI's function calling with layered prompt composition.
Every interaction goes through: intent detection → prompt composition → GPT-4 → tool execution → logging.
"""

import json
import time
import logging
from typing import Optional
from dataclasses import dataclass, field

from openai import OpenAI

from frepi_finance.config import get_config
from frepi_finance.agent.intent_detector import detect_intent
from frepi_finance.agent.prompt_composer import compose_prompt
from frepi_finance.agent.prompt_logger import (
    log_prompt_composition,
    log_prompt_result,
)
from frepi_finance.tools import ALL_TOOLS, execute_tool

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A message in the conversation."""
    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list] = None
    name: Optional[str] = None


class FinanceAgent:
    """Main Finance Agent powered by GPT-4."""

    def __init__(self):
        config = get_config()
        self.client = OpenAI(api_key=config.openai_api_key)
        self.model = config.chat_model

    async def process_message(
        self,
        user_message: str,
        session,  # SessionMemory
        has_photo: bool = False,
    ) -> str:
        """
        Process a user message through the full pipeline:
        1. Detect intent
        2. Compose prompt (with logging)
        3. Call GPT-4
        4. Execute tool calls
        5. Log results

        Args:
            user_message: The user's message
            session: The session memory object
            has_photo: Whether message includes a photo

        Returns:
            The agent's response text
        """
        start_time = time.time()

        # Step 1: Detect intent
        intent_result = detect_intent(
            message=user_message,
            has_photo=has_photo,
            is_new_user=session.is_new_user,
        )

        # Step 2: Compose prompt
        user_memory = await session.get_user_memory() if session.restaurant_id else None
        db_context = await self._build_db_context(session, intent_result.intent)
        drip_context = await self._build_drip_context(session, intent_result.intent)

        composed = compose_prompt(
            intent=intent_result.intent,
            intent_confidence=intent_result.confidence,
            user_memory=user_memory,
            db_context=db_context,
            drip_context=drip_context,
        )

        # Step 3: Set system prompt if new conversation or intent changed
        if not session.messages or session.last_intent != intent_result.intent:
            # Replace system message
            session.messages = [
                msg for msg in session.messages if msg.role != "system"
            ]
            session.messages.insert(0, Message(role="system", content=composed.system_message))
            session.last_intent = intent_result.intent

        # Add user message
        session.messages.append(Message(role="user", content=user_message))

        # Log prompt composition
        log_id = await log_prompt_composition(
            composed=composed,
            restaurant_id=session.restaurant_id,
            telegram_chat_id=session.telegram_chat_id,
            session_id=session.session_id,
            user_message=user_message,
            model_used=self.model,
        )
        session.last_prompt_log_id = log_id

        # Step 4: Call GPT-4
        tool_calls_log = []
        response = await self._call_gpt4(session)

        # Handle tool calls
        while response.choices[0].message.tool_calls:
            tool_calls = response.choices[0].message.tool_calls

            # Add assistant message with tool calls
            session.messages.append(Message(
                role="assistant",
                content=response.choices[0].message.content or "",
                tool_calls=[{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                } for tc in tool_calls]
            ))

            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                logger.info(f"🔧 TOOL CALL: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:200]})")

                result = await execute_tool(tool_name, tool_args, session)
                tool_calls_log.append({
                    "tool": tool_name,
                    "args_summary": str(tool_args)[:100],
                })

                session.messages.append(Message(
                    role="tool",
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=tool_call.id,
                    name=tool_name,
                ))

            # Call GPT-4 again with tool results
            response = await self._call_gpt4(session)

        # Step 5: Get final response and log
        assistant_message = response.choices[0].message.content or ""
        session.messages.append(Message(role="assistant", content=assistant_message))

        elapsed_ms = int((time.time() - start_time) * 1000)

        if log_id:
            await log_prompt_result(
                log_id=log_id,
                execution_time_ms=elapsed_ms,
                tool_calls_made=tool_calls_log,
                response_length=len(assistant_message),
            )

        logger.info(
            f"✅ RESPONSE: {len(assistant_message)} chars, "
            f"{elapsed_ms}ms, {len(tool_calls_log)} tool calls"
        )

        return assistant_message

    async def _call_gpt4(self, session):
        """Make a call to GPT-4."""
        messages = []
        for msg in session.messages:
            m = {"role": msg.role, "content": msg.content}
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            if msg.name:
                m["name"] = msg.name
            messages.append(m)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=ALL_TOOLS,
            tool_choice="auto",
            temperature=0.7,
        )
        return response

    async def _build_drip_context(self, session, intent: str) -> Optional[str]:
        """Build drip preference context if applicable."""
        if not session.restaurant_id or intent == "onboarding":
            return None

        try:
            from frepi_finance.services.preference_drip import get_drip_service

            drip_service = get_drip_service()
            questions = await drip_service.get_drip_questions(session.restaurant_id)
            if questions:
                return drip_service.format_drip_context(questions)
        except Exception as e:
            logger.warning(f"Failed to build drip context: {e}")

        return None

    async def _build_db_context(self, session, intent: str) -> Optional[str]:
        """Build dynamic DB context string based on intent."""
        if not session.restaurant_id:
            return None

        try:
            from frepi_finance.tools.db_tools import get_recent_context

            return await get_recent_context(session.restaurant_id, intent)
        except Exception as e:
            logger.warning(f"Failed to build DB context: {e}")
            return None


# Global agent instance
_agent: Optional[FinanceAgent] = None


def get_finance_agent() -> FinanceAgent:
    """Get the global finance agent instance."""
    global _agent
    if _agent is None:
        _agent = FinanceAgent()
    return _agent


async def finance_chat(user_message: str, session, has_photo: bool = False) -> str:
    """
    Convenience function to chat with the finance agent.

    Args:
        user_message: The user's message
        session: SessionMemory instance
        has_photo: Whether message includes a photo

    Returns:
        The agent's response
    """
    agent = get_finance_agent()
    return await agent.process_message(user_message, session, has_photo)
