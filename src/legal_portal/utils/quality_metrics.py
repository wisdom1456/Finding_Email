import re
from typing import Any, Dict, Set


def extract_entities(text: str) -> Set[str]:
    """Basic entity extraction from text using regex (names, capitalized words)."""
    # This is a simple heuristic for metrics, not a replacement for NLP
    entities = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text))
    return {e for e in entities if len(e) > 3}

def calculate_overlap(set1: Set[str], set2: Set[str]) -> float:
    """Calculate Jaccard similarity or simple overlap ratio."""
    if not set1: return 0.0
    intersection = set1.intersection(set2)
    return len(intersection) / len(set1)

def calculate_retention_metrics(stages_data: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate metrics across pipeline stages.
    
    stages_data should contain:
    - raw_text: dict of filename -> content
    - intake_content: string
    - document_summaries: list of summaries
    - case_synthesis: dict
    - final_letter: string
    """
    metrics = {}

    # 1. Fact Retention: Raw -> Summaries
    raw_entities = set()
    for content in stages_data.get("raw_text", {}).values():
        raw_entities.update(extract_entities(content))

    summary_text = " ".join([s.get("executive_summary", "") + " " + s.get("key_content", "")
                            for s in stages_data.get("document_summaries", [])])
    summary_entities = extract_entities(summary_text)

    metrics["entity_retention_raw_to_summaries"] = calculate_overlap(raw_entities, summary_entities)

    # 2. Fact Retention: Summaries -> Case Synthesis
    case_synth = stages_data.get("case_synthesis", {})
    case_synth_text = case_synth.get("case_summary", "") + " " + " ".join(case_synth.get("key_issues", []))
    case_synth_entities = extract_entities(case_synth_text)

    metrics["entity_retention_summaries_to_synthesis"] = calculate_overlap(summary_entities, case_synth_entities)

    # 3. Final Retention: Synthesis -> Final Letter
    final_letter = stages_data.get("final_letter", "")
    final_entities = extract_entities(final_letter)

    metrics["entity_retention_synthesis_to_letter"] = calculate_overlap(case_synth_entities, final_entities)

    # 4. Overall Retention
    metrics["overall_entity_retention"] = calculate_overlap(raw_entities, final_entities)

    return metrics




