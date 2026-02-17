"""
Session Memory - In-memory conversation state per chat session.

Inspired by OpenClaw's session management. Each Telegram chat_id gets
its own SessionMemory that tracks conversation history, user state,
and current operation context.
"""

import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionMemory:
    """In-session conversation state for a single chat."""

    # Identity
    telegram_chat_id: Optional[int] = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # User info (loaded from DB or set during onboarding)
    restaurant_id: Optional[int] = None
    restaurant_name: Optional[str] = None
    person_name: Optional[str] = None
    person_id: Optional[int] = None
    is_new_user: bool = False
    onboarding_complete: bool = False

    # Conversation state
    messages: list = field(default_factory=list)  # List of Message objects
    last_intent: Optional[str] = None
    last_prompt_log_id: Optional[str] = None

    # Photo handling (for invoice uploads)
    uploaded_photos: list[str] = field(default_factory=list)
    awaiting_photos: bool = False  # True when expecting more photos

    # Operation state
    current_invoice_id: Optional[str] = None  # UUID of invoice being processed
    current_report_id: Optional[str] = None  # UUID of monthly report being built
    pending_confirmation: Optional[str] = None  # What we're waiting for user to confirm

    async def get_user_memory(self) -> Optional[dict]:
        """
        Load persistent user memory from DB.

        Returns dict with restaurant context for prompt injection.
        """
        if not self.restaurant_id:
            return None

        try:
            from frepi_finance.memory.user_memory import load_user_memory
            return await load_user_memory(self.restaurant_id)
        except Exception as e:
            logger.warning(f"Failed to load user memory: {e}")
            return None

    def clear_conversation(self):
        """Clear conversation history but keep user identity."""
        self.messages = []
        self.last_intent = None
        self.last_prompt_log_id = None
        self.uploaded_photos = []
        self.awaiting_photos = False
        self.current_invoice_id = None
        self.current_report_id = None
        self.pending_confirmation = None

    def add_photo(self, file_url: str):
        """Add a photo URL to the upload queue."""
        self.uploaded_photos.append(file_url)
        self.awaiting_photos = True

    def get_and_clear_photos(self) -> list[str]:
        """Get all uploaded photos and clear the queue."""
        photos = self.uploaded_photos.copy()
        self.uploaded_photos = []
        self.awaiting_photos = False
        return photos
