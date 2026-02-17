"""
Preference Drip Service - Progressive preference collection after onboarding.

Finance-side implementation. Sneaks 1-2 preference questions into normal sessions
based on engagement level.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from frepi_finance.shared.supabase_client import (
    get_supabase_client, Tables, fetch_one, fetch_many, insert_one, update_one,
)
from frepi_finance.services.engagement_scoring import recalculate_engagement

logger = logging.getLogger(__name__)


@dataclass
class DripQuestion:
    """A single drip question to ask the user."""
    product_name: str
    master_list_id: int
    preference_type: str
    queue_position: int
    importance_tier: str
    known_info: dict


class PreferenceDripService:
    """
    Service for progressive preference collection via drip questions.
    Finance-side implementation (same logic, different DB client).
    """

    def __init__(self):
        self.client = get_supabase_client()

    async def get_drip_questions(self, restaurant_id: int) -> List[DripQuestion]:
        """Get drip questions for this session based on engagement."""
        profile = await fetch_one(
            Tables.ENGAGEMENT_PROFILE,
            {"restaurant_id": restaurant_id},
        )

        if not profile:
            return []

        level = profile.get("engagement_level", "low")
        drip_per_session = profile.get("drip_questions_per_session", 0)

        if drip_per_session == 0 or level in ("low", "dormant"):
            return []

        tier_filter = ["head"]
        if level == "high":
            tier_filter.append("mid_tail")

        queue_items = self.client.table(
            Tables.PREFERENCE_COLLECTION_QUEUE
        ).select("*").eq(
            "restaurant_id", restaurant_id
        ).in_(
            "preference_status", ["pending", "asked_drip"]
        ).in_(
            "importance_tier", tier_filter
        ).order("queue_position").limit(drip_per_session).execute()

        if not queue_items.data:
            return []

        questions = []
        for item in queue_items.data:
            product = self.client.table(Tables.MASTER_LIST).select(
                "id, product_name, brand"
            ).eq("id", item["master_list_id"]).limit(1).execute()

            if not product.data:
                continue

            prod = product.data[0]

            # Get known preferences
            prefs = self.client.table(
                Tables.RESTAURANT_PRODUCT_PREFERENCES
            ).select("*").eq(
                "restaurant_id", restaurant_id
            ).eq("master_list_id", item["master_list_id"]).limit(1).execute()

            known_info = {}
            if prefs.data:
                p = prefs.data[0]
                if p.get("brand_preferences"):
                    known_info["brand"] = p["brand_preferences"]
                if p.get("price_preference"):
                    known_info["price_max"] = p["price_preference"]

            pending = item.get("preferences_pending", [])
            if not pending:
                pending = ["brand", "price_max", "quality"]

            pref_type = pending[0] if pending else "brand"

            questions.append(DripQuestion(
                product_name=prod["product_name"],
                master_list_id=item["master_list_id"],
                preference_type=pref_type,
                queue_position=item["queue_position"],
                importance_tier=item["importance_tier"],
                known_info=known_info,
            ))

            # Mark as asked
            now = datetime.now(timezone.utc).isoformat()
            self.client.table(Tables.PREFERENCE_COLLECTION_QUEUE).update({
                "preference_status": "asked_drip",
                "asked_count": item.get("asked_count", 0) + 1,
                "last_asked_at": now,
            }).eq("id", item["id"]).execute()

        return questions

    def format_drip_context(self, questions: List[DripQuestion]) -> str:
        """
        Format drip questions as context to inject into the prompt.

        Returns:
            Formatted string for Layer 4 injection, or empty string
        """
        if not questions:
            return ""

        lines = [
            "## Perguntas de Preferência (Drip)",
            "Naturalmente, durante a conversa, pergunte sobre:",
        ]

        for q in questions:
            if q.preference_type == "brand":
                lines.append(
                    f"- **{q.product_name}**: Tem marca preferida?"
                )
            elif q.preference_type == "price_max":
                lines.append(
                    f"- **{q.product_name}**: Qual preço máximo aceitável?"
                )
            elif q.preference_type == "quality":
                lines.append(
                    f"- **{q.product_name}**: Prefere premium, padrão ou econômico?"
                )

        lines.append(
            "\nUse `answer_drip_question` para salvar cada resposta. "
            "Se o usuário ignorar, tudo bem."
        )
        return "\n".join(lines)


_drip_service: Optional[PreferenceDripService] = None


def get_drip_service() -> PreferenceDripService:
    """Get the drip service singleton."""
    global _drip_service
    if _drip_service is None:
        _drip_service = PreferenceDripService()
    return _drip_service
