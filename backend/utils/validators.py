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
    """Pre-processes AI output to ensure conformity with Pydantic models."""
    
    def to_list_of_strings(value: Any) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        if value is None:
            return []
        return value

    if isinstance(data.get('key_facts'), dict):
        data['key_facts'] = [f"{k}: {v}" for k, v in data['key_facts'].items()]
    else:
        data['key_facts'] = to_list_of_strings(data.get('key_facts'))

    if isinstance(data.get('financial_impact'), dict):
        impact = data.get('financial_impact', {})
        data['financial_impact'] = (
            f"Total Due: {impact.get('total_due', 'N/A')}, "
            f"Financial Burden: {impact.get('financial_burden', 'N/A')}"
        )
    
    # Ensure list fields are correctly formatted
    for field in ['client_priorities', 'desired_outcomes', 'legal_claims', 'potential_challenges', 'recommended_actions', 'potential_outcomes', 'relevant_statutes']:
        if field in data:
            data[field] = to_list_of_strings(data[field])
            
    return data
