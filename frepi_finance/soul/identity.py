"""
IDENTITY - Bot identity and formatting standards.
"""

BOT_NAME = "Frepi Financeiro"
BOT_EMOJI = "📊"
BOT_SHORT_NAME = "Frepi"

# Emoji standards for consistent messaging
EMOJIS = {
    "success": "✅",
    "warning": "⚠️",
    "error": "❌",
    "money": "💰",
    "chart_up": "📈",
    "chart_down": "📉",
    "target": "🎯",
    "receipt": "🧾",
    "report": "📋",
    "graph": "📊",
    "fire": "🔥",
    "thinking": "🤔",
    "wave": "👋",
    "camera": "📸",
}

# Currency formatting for Brazilian Real
def format_brl(value: float) -> str:
    """Format a number as Brazilian Real (R$ 1.234,56)."""
    if value < 0:
        return f"-R$ {abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_percent(value: float) -> str:
    """Format a number as percentage with Brazilian decimal separator."""
    return f"{value:.1f}%".replace(".", ",")

def price_trend_arrow(change_percent: float) -> str:
    """Return an arrow emoji based on price change direction."""
    if change_percent > 0:
        return f"📈 +{format_percent(change_percent)}"
    elif change_percent < 0:
        return f"📉 {format_percent(change_percent)}"
    else:
        return "➡️ 0%"
