"""Regression tests for PR-11 constants consolidation.

Ensures SERVICE_PRICING_RATES and MODEL_CONTEXT_WINDOWS in constants.py
remain the single canonical source used by all consumers.
"""

from decimal import Decimal


class TestServicePricingRatesCanonical:
    """SERVICE_PRICING_RATES is the single source of truth for pricing."""

    def test_all_required_keys_present(self):
        from legal_portal.core.constants import SERVICE_PRICING_RATES

        expected_keys = {
            "openai_gpt4o",
            "openai_gpt4o_mini",
            "openai_gpt5_2",
            "openai_whisper",
            "vertex_ai_gemini_flash",
            "vertex_ai_video",
            "google_speech_to_text",
        }
        assert set(SERVICE_PRICING_RATES.keys()) == expected_keys

    def test_all_values_are_decimal(self):
        from legal_portal.core.constants import SERVICE_PRICING_RATES

        for key, rates in SERVICE_PRICING_RATES.items():
            for rate_name, rate_value in rates.items():
                assert isinstance(rate_value, Decimal), (
                    f"{key}.{rate_name} is {type(rate_value).__name__}, expected Decimal"
                )

    def test_cost_calculator_uses_canonical_rates(self):
        from legal_portal.core.constants import SERVICE_PRICING_RATES
        from legal_portal.utils.cost_calculator import CostCalculator

        assert CostCalculator.PRICING_RATES is SERVICE_PRICING_RATES

    def test_cost_estimator_uses_canonical_rates(self):
        from legal_portal.core.constants import SERVICE_PRICING_RATES
        from legal_portal.utils.cost_estimator import CostEstimator

        assert CostEstimator.PRICING_RATES is SERVICE_PRICING_RATES

    def test_rates_are_positive(self):
        from legal_portal.core.constants import SERVICE_PRICING_RATES

        for key, rates in SERVICE_PRICING_RATES.items():
            for rate_name, rate_value in rates.items():
                assert rate_value > 0, f"{key}.{rate_name} must be positive"


class TestModelContextWindowsCanonical:
    """MODEL_CONTEXT_WINDOWS is the single source of truth for context limits."""

    def test_required_models_present(self):
        from legal_portal.core.constants import MODEL_CONTEXT_WINDOWS

        for model in ("gpt-5.4", "gpt-5.2", "gpt-5-mini"):
            assert model in MODEL_CONTEXT_WINDOWS, f"{model} missing from MODEL_CONTEXT_WINDOWS"

    def test_token_manager_uses_canonical_windows(self):
        from legal_portal.core.constants import MODEL_CONTEXT_WINDOWS
        from legal_portal.utils.token_manager import TokenManager

        tm = TokenManager()
        for model, limit in MODEL_CONTEXT_WINDOWS.items():
            assert tm.model_limits[model] == limit, (
                f"TokenManager.model_limits[{model}] = {tm.model_limits[model]}, "
                f"expected {limit}"
            )

    def test_values_are_ints_and_positive(self):
        from legal_portal.core.constants import MODEL_CONTEXT_WINDOWS

        for model, limit in MODEL_CONTEXT_WINDOWS.items():
            assert isinstance(limit, int), f"{model} limit is {type(limit).__name__}"
            assert limit > 0, f"{model} limit must be positive"
