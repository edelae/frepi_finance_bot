"""Tests for the prompt composer."""

import pytest
from frepi_finance.agent.prompt_composer import compose_prompt, ComposedPrompt
from frepi_finance.agent.intent_detector import (
    INTENT_INVOICE,
    INTENT_MONTHLY,
    INTENT_CMV,
    INTENT_GENERAL,
)


class TestPromptComposition:
    def test_general_intent_has_soul_only(self):
        result = compose_prompt(INTENT_GENERAL, 0.5)
        assert isinstance(result, ComposedPrompt)
        assert result.detected_intent == INTENT_GENERAL
        # Should have only SOUL component
        assert len(result.components) == 1
        assert result.components[0].name == "soul"

    def test_invoice_intent_has_skill(self):
        result = compose_prompt(INTENT_INVOICE, 0.85)
        # Should have SOUL + skill
        component_names = [c.name for c in result.components]
        assert "soul" in component_names
        assert f"skill_{INTENT_INVOICE}" in component_names

    def test_with_user_memory(self):
        memory = {
            "restaurant_name": "Teste",
            "person_name": "João",
            "savings_opportunity": "Comprar carnes em quantidade",
        }
        result = compose_prompt(INTENT_GENERAL, 0.5, user_memory=memory)
        component_names = [c.name for c in result.components]
        assert "user_memory" in component_names

    def test_with_db_context(self):
        result = compose_prompt(
            INTENT_MONTHLY, 0.85,
            db_context="## NFs do Mês\n- NF001: R$ 5.000",
        )
        component_names = [c.name for c in result.components]
        assert "db_context" in component_names

    def test_token_estimate_positive(self):
        result = compose_prompt(INTENT_CMV, 0.85)
        assert result.total_token_estimate > 0

    def test_system_message_not_empty(self):
        result = compose_prompt(INTENT_GENERAL, 0.5)
        assert len(result.system_message) > 100

    def test_hash_computed(self):
        result = compose_prompt(INTENT_GENERAL, 0.5)
        assert result.prompt_hash != ""
        assert len(result.prompt_hash) == 16
