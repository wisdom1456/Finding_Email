from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from legal_portal.core.data_models import (
    CaseAnalysisResult,
    GeneratedLetter,
)


class ContentExtractionService:
    """A service class for content extraction and fallback generation utilities."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the ContentExtractionService with the application configuration."""
        self.config = config

    # === EXTRACTION METHODS ===

    def extract_key_facts(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract key facts for the factual summary section."""
        facts = []
        if analysis.intake_analysis and analysis.intake_analysis.key_facts:
            if isinstance(analysis.intake_analysis.key_facts, list):
                facts.extend(analysis.intake_analysis.key_facts)
            else:
                facts.append(str(analysis.intake_analysis.key_facts))

        for doc in analysis.analyzed_documents:
            if hasattr(doc, "key_information") and doc.key_information:
                facts.append(doc.key_information)

        return facts[:5]

    def identify_emphasis_items(self, analysis: CaseAnalysisResult) -> Dict[str, str]:
        """Identify items that should be bolded."""
        import re

        emphasis_items = {}

        if analysis.intake_analysis and analysis.intake_analysis.financial_impact:
            financial_info = str(analysis.intake_analysis.financial_impact)
            amounts = re.findall(r"\$[\d,]+\.?\d*", financial_info)
            for i, amount in enumerate(amounts):
                emphasis_items[f"amount_{i + 1}"] = amount

        return emphasis_items

    def extract_legal_issues(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract legal issues for analysis section."""
        issues = []

        if analysis.legal_assessment:
            if analysis.legal_assessment.claim_viability:
                issues.append(f"Claim viability: {analysis.legal_assessment.claim_viability}")

        if analysis.intake_analysis and analysis.intake_analysis.legal_claims:
            issues.extend(analysis.intake_analysis.legal_claims)

        return issues

    def extract_media_evidence_points(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract key points about media evidence."""
        points = []

        for media in analysis.transcripted_media:
            points.append(f"Audio analysis of {media.file_name}")

        for video in analysis.video_insights:
            points.append(f"Video analysis of {video.file_name}")

        return points

    def extract_case_assessment_points(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract points for case assessment section."""
        points = []

        if analysis.legal_assessment:
            if analysis.legal_assessment.claim_viability:
                points.append(f"Claim assessment: {analysis.legal_assessment.claim_viability}")
            if analysis.legal_assessment.overall_evidence_strength:
                points.append(f"Evidence strength: {analysis.legal_assessment.overall_evidence_strength}")

        return points

    def extract_recommendations(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract recommendations for next steps."""
        recommendations = []

        if analysis.legal_assessment and analysis.legal_assessment.recommended_actions:
            if isinstance(analysis.legal_assessment.recommended_actions, list):
                recommendations.extend(analysis.legal_assessment.recommended_actions)
            else:
                recommendations.append(str(analysis.legal_assessment.recommended_actions))

        return recommendations

    def ensure_analysis_completeness(self, analysis: CaseAnalysisResult) -> None:
        """Ensure analysis has required components."""
        from legal_portal.utils.validators import (
            create_fallback_demand_letter_evaluation,
            create_fallback_legal_assessment,
        )

        if not analysis.intake_analysis:
            from legal_portal.core.data_models import EnhancedIntakeAnalysis

            analysis.intake_analysis = EnhancedIntakeAnalysis(
                client_name="Client",
                attorney_name="Attorney",
                case_summary="Legal matter requiring analysis",
                case_type="Legal Case",
                urgency_level="Standard",
            )

        if not analysis.legal_assessment:
            from legal_portal.core.data_models import LegalAssessment

            analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())

        if not analysis.demand_letter_evaluation:
            from legal_portal.core.data_models import DemandLetterEvaluation

            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(
                create_fallback_demand_letter_evaluation()
            )

    # === CASE-SPECIFIC DETAIL EXTRACTION ===

    def extract_case_specific_details(self, analysis: CaseAnalysisResult) -> Dict[str, Any]:
        """Extract specific details from analysis for fallback content generation."""
        import re

        details = {
            "amounts": [],
            "dates": [],
            "parties": [],
            "locations": [],
            "documents": [],
            "key_facts": [],
        }

        # Extract from intake analysis
        if analysis.intake_analysis:
            if (
                hasattr(analysis.intake_analysis, "financial_impact")
                and analysis.intake_analysis.financial_impact
            ):
                # Extract monetary amounts
                amounts = re.findall(r"\$[\d,]+\.?\d*", str(analysis.intake_analysis.financial_impact))
                details["amounts"].extend(amounts)

            if hasattr(analysis.intake_analysis, "key_facts") and analysis.intake_analysis.key_facts:
                if isinstance(analysis.intake_analysis.key_facts, list):
                    details["key_facts"].extend(analysis.intake_analysis.key_facts)
                else:
                    details["key_facts"].append(str(analysis.intake_analysis.key_facts))

        # Extract from analyzed documents
        if analysis.analyzed_documents:
            for doc in analysis.analyzed_documents[:5]:  # Limit to first 5 documents
                details["documents"].append(doc.file_name)
                if hasattr(doc, "key_information") and doc.key_information:
                    details["key_facts"].append(doc.key_information[:200])  # First 200 chars
                if doc.summary:
                    # Extract specific details from document summaries
                    doc_amounts = re.findall(r"\$[\d,]+\.?\d*", doc.summary)
                    details["amounts"].extend(doc_amounts)

                    # Extract dates
                    date_patterns = re.findall(
                        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b[A-Za-z]+ \d{1,2}, \d{4}\b",
                        doc.summary,
                    )
                    details["dates"].extend(date_patterns)

        # Remove duplicates and limit
        details["amounts"] = list(set(details["amounts"]))[:5]
        details["dates"] = list(set(details["dates"]))[:5]
        details["key_facts"] = details["key_facts"][:10]

        return details

    def identify_longest_section(self, letter: GeneratedLetter) -> Optional[str]:
        """Identify the section with the most words."""
        section_word_counts = {}

        # Define sections that can be shortened (exclude closing/greeting)
        shortenable_sections = [
            "background_summary",
            "analysis_and_position",
            "media_summary",
            "strengths",
            "challenges",
            "recommendations",
            "next_steps",
        ]

        for section_key in shortenable_sections:
            content = getattr(letter, section_key, "")
            if content and content.strip():
                word_count = len(self._strip_html_tags(content).split())
                section_word_counts[section_key] = word_count

        if not section_word_counts:
            return None

        # Return the section with the most words
        longest_section = max(section_word_counts.items(), key=lambda x: x[1])
        return longest_section[0]

    def _strip_html_tags(self, html_content: str) -> str:
        """Strip HTML tags and return plain text."""
        if not html_content:
            return ""

        # Remove HTML tags using regex
        clean_text = re.sub(r"<[^>]+>", "", html_content)
        # Clean up extra whitespace
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        return clean_text
