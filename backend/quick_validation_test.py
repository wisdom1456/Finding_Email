#!/usr/bin/env python3
"""
Quick test to verify fallback validation fixes.
"""

import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.data_models import LegalAssessment, DemandLetterEvaluation
from utils.validators import create_fallback_legal_assessment, create_fallback_demand_letter_evaluation

def test_fallback_validation():
    """Test that fallback functions now return valid data for updated models."""
    print("🧪 Testing fallback validation fixes...\n")
    
    # Test LegalAssessment fallback
    print("1. Testing LegalAssessment fallback...")
    try:
        fallback_data = create_fallback_legal_assessment()
        legal_assessment = LegalAssessment.model_validate(fallback_data)
        print(f"   ✅ LegalAssessment validation successful")
        print(f"   - demand_letter_appropriate: {legal_assessment.demand_letter_appropriate} (type: {type(legal_assessment.demand_letter_appropriate).__name__})")
        print(f"   - case_type: {legal_assessment.case_type}")
        assert isinstance(legal_assessment.demand_letter_appropriate, str), "demand_letter_appropriate should be string"
    except Exception as e:
        print(f"   ❌ LegalAssessment validation failed: {e}")
        return False
    
    # Test DemandLetterEvaluation fallback
    print("\n2. Testing DemandLetterEvaluation fallback...")
    try:
        fallback_data = create_fallback_demand_letter_evaluation()
        demand_evaluation = DemandLetterEvaluation.model_validate(fallback_data)
        print(f"   ✅ DemandLetterEvaluation validation successful")
        print(f"   - is_appropriate: {demand_evaluation.is_appropriate} (type: {type(demand_evaluation.is_appropriate).__name__})")
        print(f"   - reasoning: {demand_evaluation.reasoning[:50]}...")
        assert isinstance(demand_evaluation.is_appropriate, str), "is_appropriate should be string"
    except Exception as e:
        print(f"   ❌ DemandLetterEvaluation validation failed: {e}")
        return False
    
    print("\n🎉 All fallback validation tests passed!")
    print("✅ Boolean to string conversion successful")
    print("✅ Pydantic validation error should be resolved")
    return True

if __name__ == "__main__":
    success = test_fallback_validation()
    sys.exit(0 if success else 1)