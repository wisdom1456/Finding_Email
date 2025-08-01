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
    Coerces all relevant fields to lists of strings, even in nested objects.
    """
    def to_list_of_strings(value: Any) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    # Fields that should always be lists of strings
    list_fields = {
        'client_priorities', 'desired_outcomes', 'legal_claims',
        'potential_challenges', 'recommended_actions', 'potential_outcomes', 'relevant_statutes'
    }

    def recursive_process(obj):
        if isinstance(obj, dict):
            # Special handling for key_facts and financial_impact at any level
            if 'key_facts' in obj:
                if isinstance(obj['key_facts'], dict):
                    obj['key_facts'] = [f"{k}: {v}" for k, v in obj['key_facts'].items()]
                else:
                    obj['key_facts'] = to_list_of_strings(obj['key_facts'])
            if 'financial_impact' in obj and isinstance(obj['financial_impact'], dict):
                impact = obj.get('financial_impact', {})
                obj['financial_impact'] = (
                    f"Total Due: {impact.get('total_due', 'N/A')}, "
                    f"Financial Burden: {impact.get('financial_burden', 'N/A')}"
                )
            # Coerce all list_fields at this level
            for field in list_fields:
                if field in obj:
                    obj[field] = to_list_of_strings(obj[field])
            # Recurse into all dict/list values
            for k, v in obj.items():
                obj[k] = recursive_process(v)
            return obj
        elif isinstance(obj, list):
            return [recursive_process(item) for item in obj]
        else:
            return obj

    return recursive_process(data)
