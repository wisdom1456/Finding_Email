#!/usr/bin/env python3
"""
Quick test to verify fallback validation fixes.
"""

from __future__ import annotations

import os
import sys

from utils.logging_config import setup_logging


logger = setup_logging("quick_validation_test")


# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.data_models import DemandLetterEvaluation, LegalAssessment
from utils.validators import (
    create_fallback_demand_letter_evaluation,
    create_fallback_legal_assessment,
)


def test_fallback_validation():
    """Test that fallback functions now return valid data for updated models."""
    logger.warning("🧪 Testing fallback validation fixes...\n")

    # Test LegalAssessment fallback
    logger.warning("1. Testing LegalAssessment fallback...")
    try:
        fallback_data = create_fallback_legal_assessment()
        legal_assessment = LegalAssessment.model_validate(fallback_data)
        logger.info("   ✅ LegalAssessment validation successful")
        logger.info(
            f"   - demand_letter_appropriate: {legal_assessment.demand_letter_appropriate} (type: {type(legal_assessment.demand_letter_appropriate).__name__})"
        )
        logger.info(f"   - case_type: {legal_assessment.case_type}")
        assert isinstance(legal_assessment.demand_letter_appropriate, str), (
            "demand_letter_appropriate should be string"
        )
    except Exception as e:
        logger.error(f"   ❌ LegalAssessment validation failed: {e}")
        return False

    # Test DemandLetterEvaluation fallback
    logger.warning("\n2. Testing DemandLetterEvaluation fallback...")
    try:
        fallback_data = create_fallback_demand_letter_evaluation()
        demand_evaluation = DemandLetterEvaluation.model_validate(fallback_data)
        logger.info("   ✅ DemandLetterEvaluation validation successful")
        logger.info(
            f"   - is_appropriate: {demand_evaluation.is_appropriate} (type: {type(demand_evaluation.is_appropriate).__name__})"
        )
        logger.info(f"   - reasoning: {demand_evaluation.reasoning[:50]}...")
        assert isinstance(demand_evaluation.is_appropriate, str), (
            "is_appropriate should be string"
        )
    except Exception as e:
        logger.error(f"   ❌ DemandLetterEvaluation validation failed: {e}")
        return False

    logger.warning("\n🎉 All fallback validation tests passed!")
    logger.info("✅ Boolean to string conversion successful")
    logger.error("✅ Pydantic validation error should be resolved")
    return True


if __name__ == "__main__":
    success = test_fallback_validation()
    sys.exit(0 if success else 1)
