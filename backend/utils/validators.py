from typing import Any, Dict, List

def stringify_dict(value: Any) -> Any:
    """If the value is a dictionary, convert it to a JSON string."""
    if isinstance(value, dict):
        import json
        return json.dumps(value, indent=2)
    return value

def stringify_list_of_dicts(value: Any) -> Any:
    """If the value is a list of dictionaries, convert each to a JSON string."""
    if isinstance(value, list) and all(isinstance(i, dict) for i in value):
        import json
        return [json.dumps(i, indent=2) for i in value]
    return value

def preprocess_ai_output(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively pre-processes AI output to ensure conformity with Pydantic models.
    Enhanced with robust normalization for validation error prevention.
    """
    def to_list_of_strings(value: Any) -> List[str]:
        if isinstance(value, str):
            if not value.strip():
                return []
            # Handle semicolon or comma-separated values
            if ';' in value:
                return [item.strip() for item in value.split(';') if item.strip()]
            elif ',' in value:
                return [item.strip() for item in value.split(',') if item.strip()]
            elif '.' in value and len(value) > 100:  # Likely multiple sentences
                sentences = value.split('.')
                return [f"{sentence.strip()}." for sentence in sentences[:-1] if sentence.strip()]
            else:
                return [value.strip()]
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value)] if value else []

    def normalize_evidence_strength(value: Any) -> str:
        """Normalize evidence strength values to match enum."""
        if not isinstance(value, str):
            return value
        
        strength_mapping = {
            'High': 'Strong',
            'Very Strong': 'Strong',
            'Very High': 'Strong',
            'Low': 'Weak',
            'Very Low': 'Weak',
            'Medium': 'Moderate',
            'Average': 'Moderate',
            'Excellent': 'Conclusive',
            'Outstanding': 'Conclusive',
            'Definitive': 'Conclusive'
        }
        
        return strength_mapping.get(value, value)

    # Fields that should always be lists of strings
    list_fields = {
        'client_priorities', 'desired_outcomes', 'legal_claims',
        'potential_challenges', 'recommended_actions', 'potential_outcomes', 'relevant_statutes'
    }

    # Fields that need enum normalization
    enum_fields = {
        'overall_evidence_strength': normalize_evidence_strength,
        'urgency_level': lambda x: x,  # Add more enum normalizers as needed
        'case_type': lambda x: x
    }

    def recursive_process(obj):
        if isinstance(obj, dict):
            # Create a copy to avoid modifying the original
            processed_obj = obj.copy()
            
            # Special handling for key_facts and financial_impact at any level
            if 'key_facts' in processed_obj:
                if isinstance(processed_obj['key_facts'], dict):
                    processed_obj['key_facts'] = [f"{k}: {v}" for k, v in processed_obj['key_facts'].items()]
                else:
                    processed_obj['key_facts'] = to_list_of_strings(processed_obj['key_facts'])
            
            if 'financial_impact' in processed_obj and isinstance(processed_obj['financial_impact'], dict):
                impact = processed_obj.get('financial_impact', {})
                processed_obj['financial_impact'] = (
                    f"Total Due: {impact.get('total_due', 'N/A')}, "
                    f"Financial Burden: {impact.get('financial_burden', 'N/A')}"
                )
            
            # Apply enum normalization
            for field, normalizer in enum_fields.items():
                if field in processed_obj and processed_obj[field] is not None:
                    try:
                        processed_obj[field] = normalizer(processed_obj[field])
                    except Exception as e:
                        print(f"VALIDATION: Failed to normalize {field}: {e}")
                        # Keep original value if normalization fails
            
            # Coerce all list_fields at this level
            for field in list_fields:
                if field in processed_obj:
                    try:
                        processed_obj[field] = to_list_of_strings(processed_obj[field])
                    except Exception as e:
                        print(f"VALIDATION: Failed to convert {field} to list: {e}")
                        # Fallback to empty list
                        processed_obj[field] = []
            
            # Recurse into all dict/list values
            for k, v in processed_obj.items():
                processed_obj[k] = recursive_process(v)
            
            return processed_obj
        elif isinstance(obj, list):
            return [recursive_process(item) for item in obj]
        else:
            return obj

    try:
        return recursive_process(data)
    except Exception as e:
        print(f"VALIDATION: Error in preprocess_ai_output: {e}")
        # Return original data if preprocessing fails completely
        return data

def create_fallback_legal_assessment() -> Dict[str, Any]:
    """Creates a fallback LegalAssessment when validation fails."""
    return {
        "case_type": "Legal Matter",
        "claim_viability": "Under Review",
        "overall_evidence_strength": "Moderate",
        "potential_challenges": ["Assessment in progress"],
        "recommended_actions": ["Further analysis required"],
        "demand_letter_appropriate": False,
        "urgency_assessment": "Standard"
    }

def create_fallback_demand_letter_evaluation() -> Dict[str, Any]:
    """Creates a fallback DemandLetterEvaluation when validation fails."""
    return {
        "is_appropriate": False,
        "reasoning": "Evaluation pending completion of case analysis",
        "potential_outcomes": ["To be determined"],
        "relevant_statutes": []
    }

def safe_model_validate(model_class, data: Dict[str, Any], fallback_func=None):
    """
    Safely validates a Pydantic model with graceful degradation.
    Returns either the validated model or a fallback instance.
    """
    try:
        # First try preprocessing the data
        processed_data = preprocess_ai_output(data) if isinstance(data, dict) else data
        return model_class.model_validate(processed_data)
    except Exception as e:
        print(f"VALIDATION: Failed to validate {model_class.__name__}: {e}")
        if fallback_func:
            try:
                fallback_data = fallback_func()
                return model_class.model_validate(fallback_data)
            except Exception as fallback_error:
                print(f"VALIDATION: Fallback validation also failed for {model_class.__name__}: {fallback_error}")
        
        # Return None if everything fails - calling code should handle this
        return None
