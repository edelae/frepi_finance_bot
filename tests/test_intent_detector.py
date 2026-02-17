"""Tests for the intent detector."""

import pytest
from frepi_finance.agent.intent_detector import (
    detect_intent,
    INTENT_INVOICE,
    INTENT_MONTHLY,
    INTENT_CMV,
    INTENT_WATCHLIST,
    INTENT_ONBOARDING,
    INTENT_GENERAL,
)


class TestInvoiceIntent:
    def test_photo_triggers_invoice(self):
        result = detect_intent("qualquer coisa", has_photo=True)
        assert result.intent == INTENT_INVOICE
        assert result.confidence >= 0.9

    def test_nf_keyword(self):
        result = detect_intent("Quero enviar uma NF")
        assert result.intent == INTENT_INVOICE

    def test_nota_fiscal(self):
        result = detect_intent("Tenho uma nota fiscal para enviar")
        assert result.intent == INTENT_INVOICE

    def test_menu_option_1(self):
        result = detect_intent("1")
        assert result.intent == INTENT_INVOICE


class TestMonthlyIntent:
    def test_fechamento(self):
        result = detect_intent("Quero fazer o fechamento do mês")
        assert result.intent == INTENT_MONTHLY

    def test_faturamento(self):
        result = detect_intent("Meu faturamento foi R$ 80.000")
        assert result.intent == INTENT_MONTHLY

    def test_relatorio_mensal(self):
        result = detect_intent("Preciso do relatório mensal")
        assert result.intent == INTENT_MONTHLY

    def test_menu_option_2(self):
        result = detect_intent("2")
        assert result.intent == INTENT_MONTHLY


class TestCMVIntent:
    def test_cmv_keyword(self):
        result = detect_intent("Qual é o CMV do meu restaurante?")
        assert result.intent == INTENT_CMV

    def test_cardapio(self):
        result = detect_intent("Quero analisar meu cardápio")
        assert result.intent == INTENT_CMV

    def test_prato(self):
        result = detect_intent("Quanto custa o prato de picanha?")
        assert result.intent == INTENT_CMV

    def test_ficha_tecnica(self):
        result = detect_intent("Preciso criar a ficha técnica")
        assert result.intent == INTENT_CMV

    def test_menu_option_3(self):
        result = detect_intent("3")
        assert result.intent == INTENT_CMV


class TestWatchlistIntent:
    def test_acompanhar(self):
        result = detect_intent("Quero acompanhar o preço da picanha")
        assert result.intent == INTENT_WATCHLIST

    def test_monitorar(self):
        result = detect_intent("Monitorar preço do arroz")
        assert result.intent == INTENT_WATCHLIST

    def test_menu_option_4(self):
        result = detect_intent("4")
        assert result.intent == INTENT_WATCHLIST


class TestOnboardingIntent:
    def test_new_user(self):
        result = detect_intent("Olá", is_new_user=True)
        assert result.intent == INTENT_ONBOARDING
        assert result.confidence >= 0.9


class TestGeneralIntent:
    def test_greeting(self):
        result = detect_intent("Olá, tudo bem?")
        assert result.intent == INTENT_GENERAL

    def test_random_question(self):
        result = detect_intent("Como funciona o sistema?")
        assert result.intent == INTENT_GENERAL
