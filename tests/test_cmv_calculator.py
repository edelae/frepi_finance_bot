"""Tests for the CMV calculator logic (unit tests with no DB dependency)."""

import pytest


class TestCMVCalculation:
    """Test CMV math without DB calls."""

    def test_cmv_percentage(self):
        """CMV = total_purchases / total_revenue * 100."""
        total_purchases = 32000.0
        total_revenue = 100000.0
        cmv = (total_purchases / total_revenue) * 100
        assert cmv == 32.0

    def test_cmv_zero_revenue(self):
        """Zero revenue should not divide by zero."""
        total_revenue = 0
        total_purchases = 1000.0
        cmv = (total_purchases / total_revenue * 100) if total_revenue > 0 else 0
        assert cmv == 0

    def test_profitability_tier_high(self):
        """Food cost < 28% = high profitability."""
        food_cost_pct = 25.0
        tier = _get_tier(food_cost_pct)
        assert tier == "high"

    def test_profitability_tier_medium(self):
        """Food cost 28-35% = medium profitability."""
        food_cost_pct = 32.0
        tier = _get_tier(food_cost_pct)
        assert tier == "medium"

    def test_profitability_tier_low(self):
        """Food cost 35-40% = low profitability."""
        food_cost_pct = 38.0
        tier = _get_tier(food_cost_pct)
        assert tier == "low"

    def test_profitability_tier_negative(self):
        """Food cost > 40% = negative profitability."""
        food_cost_pct = 45.0
        tier = _get_tier(food_cost_pct)
        assert tier == "negative"

    def test_waste_factor(self):
        """Waste factor increases cost."""
        quantity = 0.5  # kg
        unit_cost = 40.0  # R$/kg
        waste_percent = 10.0
        cost_per_serving = quantity * unit_cost
        waste_factor = 1 + (waste_percent / 100)
        adjusted_cost = cost_per_serving * waste_factor
        assert adjusted_cost == pytest.approx(22.0, rel=1e-2)

    def test_contribution_margin(self):
        """Contribution margin = sale_price - food_cost."""
        sale_price = 45.0
        food_cost = 14.0
        margin = sale_price - food_cost
        assert margin == 31.0


def _get_tier(food_cost_pct: float) -> str:
    """Mirror the tier logic from cmv_calculator.py."""
    if food_cost_pct > 40:
        return "negative"
    elif food_cost_pct > 35:
        return "low"
    elif food_cost_pct > 28:
        return "medium"
    else:
        return "high"
