"""Tests for identity formatting helpers."""

import pytest
from frepi_finance.soul.identity import format_brl, format_percent


class TestFormatBRL:
    def test_small_value(self):
        assert format_brl(42.90) == "R$ 42,90"

    def test_zero(self):
        assert format_brl(0) == "R$ 0,00"

    def test_thousands(self):
        result = format_brl(1234.56)
        assert "R$" in result
        assert "1.234,56" in result

    def test_large_value(self):
        result = format_brl(85000.00)
        assert "R$" in result


class TestFormatPercent:
    def test_normal(self):
        assert format_percent(32.5) == "32,5%"

    def test_zero(self):
        assert format_percent(0) == "0,0%"

    def test_high(self):
        assert format_percent(100.0) == "100,0%"
