"""
GPT-4 Function Calling Tools for Frepi Finance Agent.

Defines all tool schemas and the central dispatcher.
"""

from typing import Any

from .onboarding_tools import ONBOARDING_TOOLS, execute_onboarding_tool
from .invoice_tools import INVOICE_TOOLS, execute_invoice_tool
from .monthly_tools import MONTHLY_TOOLS, execute_monthly_tool
from .cmv_tools import CMV_TOOLS, execute_cmv_tool
from .watchlist_tools import WATCHLIST_TOOLS, execute_watchlist_tool
from .db_tools import DB_TOOLS, execute_db_tool

# All tools available to GPT-4
ALL_TOOLS = (
    ONBOARDING_TOOLS
    + INVOICE_TOOLS
    + MONTHLY_TOOLS
    + CMV_TOOLS
    + WATCHLIST_TOOLS
    + DB_TOOLS
)

# Tool name to executor mapping
_TOOL_EXECUTORS = {}


def _register_tools(tools_list, executor):
    """Register tool names to their executor function."""
    for tool in tools_list:
        name = tool["function"]["name"]
        _TOOL_EXECUTORS[name] = executor


_register_tools(ONBOARDING_TOOLS, execute_onboarding_tool)
_register_tools(INVOICE_TOOLS, execute_invoice_tool)
_register_tools(MONTHLY_TOOLS, execute_monthly_tool)
_register_tools(CMV_TOOLS, execute_cmv_tool)
_register_tools(WATCHLIST_TOOLS, execute_watchlist_tool)
_register_tools(DB_TOOLS, execute_db_tool)


async def execute_tool(tool_name: str, args: dict[str, Any], session) -> dict:
    """
    Execute a tool by name with arguments.

    Args:
        tool_name: The function name from GPT-4
        args: The parsed arguments
        session: The SessionMemory for context

    Returns:
        Tool result as dict
    """
    executor = _TOOL_EXECUTORS.get(tool_name)
    if executor is None:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return await executor(tool_name, args, session)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}"}
