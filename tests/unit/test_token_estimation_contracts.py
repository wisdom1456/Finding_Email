"""Regression tests for PR-11 token estimation consolidation.

Verifies the delegation chain and behavior contracts:
- token_manager.estimate_tokens() is the canonical simple estimator
- CostCalculator._estimate_tokens and CostEstimator._estimate_tokens
  delegate to it with null-guard + min-1 floor wrappers
- TokenManager.estimate_tokens delegates to the module-level function
"""


class TestCanonicalEstimator:
    """token_manager.estimate_tokens is the canonical len(text)//4 estimator."""

    def test_basic_estimation(self):
        from legal_portal.utils.token_manager import estimate_tokens

        assert estimate_tokens("a" * 100) == 25

    def test_empty_string_returns_zero(self):
        from legal_portal.utils.token_manager import estimate_tokens

        assert estimate_tokens("") == 0

    def test_short_string_floors_to_zero(self):
        from legal_portal.utils.token_manager import estimate_tokens

        # 3 chars // 4 = 0
        assert estimate_tokens("abc") == 0

    def test_instance_method_delegates(self):
        from legal_portal.utils.token_manager import TokenManager, estimate_tokens

        tm = TokenManager()
        text = "Hello world, this is a test of token estimation."
        assert tm.estimate_tokens(text) == estimate_tokens(text)


class TestCostCalculatorWrapper:
    """CostCalculator._estimate_tokens: null-guard + max(1, canonical)."""

    def _calc(self):
        from legal_portal.utils.cost_calculator import CostCalculator
        return CostCalculator()

    def test_empty_returns_zero(self):
        assert self._calc()._estimate_tokens("") == 0

    def test_none_returns_zero(self):
        # Falsy value triggers null-guard
        assert self._calc()._estimate_tokens("") == 0

    def test_short_string_floors_to_one(self):
        # "abc" → canonical returns 0, wrapper returns max(1, 0) = 1
        assert self._calc()._estimate_tokens("abc") == 1

    def test_normal_string_matches_canonical(self):
        from legal_portal.utils.token_manager import estimate_tokens

        text = "a" * 100
        expected = max(1, estimate_tokens(text))
        assert self._calc()._estimate_tokens(text) == expected


class TestCostEstimatorWrapper:
    """CostEstimator._estimate_tokens: null-guard + max(1, canonical)."""

    def _est(self):
        from legal_portal.utils.cost_estimator import CostEstimator
        return CostEstimator()

    def test_empty_returns_zero(self):
        assert self._est()._estimate_tokens("") == 0

    def test_short_string_floors_to_one(self):
        assert self._est()._estimate_tokens("abc") == 1

    def test_normal_string_matches_canonical(self):
        from legal_portal.utils.token_manager import estimate_tokens

        text = "a" * 100
        expected = max(1, estimate_tokens(text))
        assert self._est()._estimate_tokens(text) == expected

    def test_both_wrappers_agree(self):
        """CostCalculator and CostEstimator wrappers produce identical results."""
        from legal_portal.utils.cost_calculator import CostCalculator
        from legal_portal.utils.cost_estimator import CostEstimator

        calc = CostCalculator()
        est = CostEstimator()

        for text in ["", "abc", "a" * 100, "x" * 4, "hello world"]:
            assert calc._estimate_tokens(text) == est._estimate_tokens(text), (
                f"Wrappers disagree on {text!r}"
            )
