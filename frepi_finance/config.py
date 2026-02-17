"""
Configuration management for Frepi Finance Agent.

Loads environment variables and provides typed access to configuration values.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


@dataclass
class Config:
    """Application configuration."""

    # API Keys
    openai_api_key: str
    supabase_url: str
    supabase_key: str

    # Telegram (separate bot token for finance agent)
    telegram_bot_token: str
    telegram_webhook_url: Optional[str] = None

    # Application settings
    log_level: str = "INFO"
    environment: str = "development"

    # OpenAI model settings
    chat_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Price validation
    price_freshness_days: int = 30

    @classmethod
    def from_env(cls) -> "Config":
        """Create Config from environment variables."""
        load_env()

        return cls(
            # Required keys
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            supabase_url=os.environ.get("SUPABASE_URL", ""),
            supabase_key=os.environ.get("SUPABASE_KEY", ""),
            telegram_bot_token=os.environ.get("TELEGRAM_FINANCE_BOT_TOKEN", ""),
            # Optional keys
            telegram_webhook_url=os.environ.get("TELEGRAM_WEBHOOK_URL"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            environment=os.environ.get("ENVIRONMENT", "development"),
            # Model settings
            chat_model=os.environ.get("CHAT_MODEL", "gpt-4o"),
            embedding_model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1536")),
            price_freshness_days=int(os.environ.get("PRICE_FRESHNESS_DAYS", "30")),
        )

    def validate(self) -> list[str]:
        """Validate required configuration values. Returns list of missing keys."""
        missing = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_key:
            missing.append("SUPABASE_KEY")
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_FINANCE_BOT_TOKEN")
        return missing


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config():
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
