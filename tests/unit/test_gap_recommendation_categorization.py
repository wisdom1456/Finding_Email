"""Tests for GapAnalysisService._generate_recommendation categorization.

Why this exists: production audit (2026-05-19) of 52 historical
recommendations showed 29 viable-but-declined cases — the `critical >= 3`
clause in the NOT_VIABLE rule was overriding deep_analysis viability for
cases that had legal merit but missing documents. The fix removes that
clause; viable-but-under-documented cases now route to
NEEDS_DOCUMENTATION with a request_documents letter (the productive
next action) instead of NOT_VIABLE with a declination letter.

These tests pin both ends of the change:
  - Truly not-viable cases still decline (correct)
  - Viable cases with many critical gaps DO NOT decline (the fix)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from legal_portal.core.models.analysis_models import (
    CaseRecommendationCategory,
    RecommendedLetterType,
)
from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService


def _mk_gap(score: float, critical: int, high: int) -> MagicMock:
    """Build a minimal GapAnalysisResult-shaped object for the categorizer."""
    g = MagicMock()
    g.overall_completeness_score = score
    g.critical_count = critical
    g.high_count = high
    return g


def _mk_deep(is_viable: bool, strength: str = "moderate", reasoning: str = "") -> MagicMock:
    d = MagicMock()
    d.is_viable = is_viable
    d.overall_case_strength = strength
    d.viability_reasoning = reasoning
    return d


def _categorize(score, critical, high, is_viable=True, strength="moderate"):
    """Run the categorizer the way the production service does."""
    svc = GapAnalysisService.__new__(GapAnalysisService)  # bypass __init__
    return svc._generate_recommendation(
        gap_analysis=_mk_gap(score, critical, high),
        deep_analysis=_mk_deep(is_viable=is_viable, strength=strength),
    )


# ── NOT_VIABLE: only when deep agrees ───────────────────────────────────────

def test_deep_says_not_viable_routes_to_declination():
    rec = _categorize(score=70, critical=1, high=1, is_viable=False)
    assert rec.category == CaseRecommendationCategory.NOT_VIABLE
    assert rec.suggested_letter_type == RecommendedLetterType.DECLINATION


def test_score_below_30_routes_to_declination_regardless_of_viability():
    # Truly under-documented case (< 30% score) still declines.
    rec = _categorize(score=25, critical=2, high=2, is_viable=True)
    assert rec.category == CaseRecommendationCategory.NOT_VIABLE


# ── The fix: viable-but-critical no longer declines ─────────────────────────

def test_viable_case_with_3_critical_no_longer_declines():
    # Pre-fix: critical >= 3 alone declined viable cases.
    # Post-fix: routes to needs_documentation since critical >= 1 AND high >= 2.
    rec = _categorize(score=65, critical=3, high=2, is_viable=True)
    assert rec.category == CaseRecommendationCategory.NEEDS_DOCUMENTATION
    assert rec.suggested_letter_type == RecommendedLetterType.REQUEST_DOCUMENTS


def test_viable_case_with_5_critical_routes_to_needs_documentation():
    # The Paul-Beiter-first-snapshot shape: viable=True, score>30, critical=5, high=7.
    # Used to decline; now correctly routes to docs request.
    rec = _categorize(score=58, critical=5, high=7, is_viable=True)
    assert rec.category == CaseRecommendationCategory.NEEDS_DOCUMENTATION
    assert rec.suggested_letter_type == RecommendedLetterType.REQUEST_DOCUMENTS


def test_viable_case_with_many_critical_still_routes_correctly():
    # Even a very critical-heavy case stays needs_documentation when viable.
    rec = _categorize(score=55, critical=7, high=10, is_viable=True)
    assert rec.category == CaseRecommendationCategory.NEEDS_DOCUMENTATION


# ── NEEDS_DOCUMENTATION: original behavior preserved ─────────────────────────

def test_low_score_routes_to_needs_documentation():
    rec = _categorize(score=55, critical=0, high=1, is_viable=True)
    assert rec.category == CaseRecommendationCategory.NEEDS_DOCUMENTATION


def test_critical_1_plus_high_2_routes_to_needs_documentation():
    rec = _categorize(score=70, critical=1, high=2, is_viable=True)
    assert rec.category == CaseRecommendationCategory.NEEDS_DOCUMENTATION


# ── SETTLEMENT and STRONG_CASE: unchanged ───────────────────────────────────

def test_weak_strength_routes_to_settlement():
    rec = _categorize(score=70, critical=0, high=0, is_viable=True, strength="weak")
    assert rec.category == CaseRecommendationCategory.SETTLEMENT_RECOMMENDED


def test_strong_clean_case_routes_to_proceed():
    rec = _categorize(score=85, critical=0, high=1, is_viable=True, strength="strong")
    assert rec.category == CaseRecommendationCategory.STRONG_CASE
    assert rec.suggested_letter_type == RecommendedLetterType.PROCEED
