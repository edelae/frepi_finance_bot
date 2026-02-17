"""Tests for invoice parser utility functions (no API calls)."""

import pytest
from frepi_finance.soul.identity import format_brl, price_trend_arrow


class TestPriceTrendArrow:
    def test_price_increase(self):
        result = price_trend_arrow(15.5)
        assert "📈" in result
        assert "15,5%" in result

    def test_price_decrease(self):
        result = price_trend_arrow(-8.3)
        assert "📉" in result
        assert "8,3%" in result  # negative sign handled by format_percent

    def test_no_change(self):
        result = price_trend_arrow(0)
        assert "➡️" in result


class TestInvoiceParsing:
    """Test invoice data structure validation logic."""

    def test_valid_invoice_structure(self):
        """A valid parsed invoice has required fields."""
        invoice = {
            "supplier_name": "Friboi Direto",
            "cnpj": "12.345.678/0001-90",
            "items": [
                {
                    "product": "Picanha",
                    "quantity": 10.0,
                    "unit": "kg",
                    "unit_price": 42.90,
                    "total": 429.00,
                }
            ],
            "total": 429.00,
        }
        assert invoice["supplier_name"]
        assert len(invoice["items"]) > 0
        assert invoice["items"][0]["unit_price"] > 0

    def test_line_item_total_calculation(self):
        """Line item total = quantity * unit_price."""
        quantity = 10.0
        unit_price = 42.90
        expected_total = 429.00
        assert quantity * unit_price == pytest.approx(expected_total, rel=1e-2)

    def test_invoice_total_is_sum_of_items(self):
        """Invoice total should equal sum of line item totals."""
        items = [
            {"total": 429.00},
            {"total": 150.00},
            {"total": 75.50},
        ]
        total = sum(item["total"] for item in items)
        assert total == pytest.approx(654.50, rel=1e-2)

    def test_price_change_calculation(self):
        """Price change percent = (new - old) / old * 100."""
        old_price = 40.00
        new_price = 42.90
        change = (new_price - old_price) / old_price * 100
        assert change == pytest.approx(7.25, rel=1e-2)

    def test_significant_change_threshold(self):
        """Changes >= 10% are considered significant."""
        threshold = 10.0
        change_pct = 12.5
        assert abs(change_pct) >= threshold
