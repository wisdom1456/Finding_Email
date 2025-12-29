"""Service for case-specific AI chat with complete context."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from legal_portal.core.data_models import ProcessingResult
from legal_portal.services.statute_recommendation_service import (
    StatuteRecommendationService,
)
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


class CaseChatService:
    """Provides conversational responses about a case with full factual context."""

    def __init__(self, openai_client: OpenAIClient, jurisdiction: str = "Florida"):
        self.client = openai_client
        self.jurisdiction = jurisdiction
        self._statute_service: Optional[StatuteRecommendationService] = None

    @property
    def statute_service(self) -> StatuteRecommendationService:
        """Lazy-load the statute recommendation service."""
        if self._statute_service is None:
            self._statute_service = StatuteRecommendationService(jurisdiction=self.jurisdiction)
        return self._statute_service

    async def send_message(
        self,
        user_message: str,
        analysis_result: ProcessingResult,
        conversation_history: List[Dict[str, str]],
    ) -> str:
        """Send a message to the AI assistant with case context."""
        system_message = self._build_system_message(analysis_result)
        messages = (
            [{"role": "system", "content": system_message}]
            + conversation_history
            + [{"role": "user", "content": user_message}]
        )

        logger.info(f"Case chat request with {len(conversation_history)} prior messages")

        model = self.client.get_preferred_model("case_chat", "gpt-4o")
        response = self.client.create_chat_completion(
            model=model,
            messages=messages,
            temperature=0.4,
            max_tokens=1500,
        )

        return response["content"]

    def _build_system_message(self, analysis_result: ProcessingResult) -> str:
        """Assemble complete case context into a single system message."""
        # Jurisdiction-specific citation guidance
        citation_format = "Fla. Stat. § [chapter].[section] (e.g., Fla. Stat. § 83.51)"
        if self.jurisdiction == "New Mexico":
            citation_format = (
                "N.M. Stat. Ann. § [chapter]-[section] (e.g., N.M. Stat. Ann. § 57-12-2) "
                "or Rule [number] NMRA"
            )

        lines: List[str] = [
            f"You are an AI legal assistant with full knowledge of this case and {self.jurisdiction} law.",
            "Answer questions using the facts, timeline, financial data, and legal analysis provided.",
            f"When relevant, cite {self.jurisdiction} statutes from the verified corpus provided below.",
            f"Use proper citation format: '{citation_format}'.",
            "Always cite specific documents conversationally (e.g., 'According to the Contract dated...').",
            "If the data does not include the answer, say so clearly.",
            f"If a question falls outside {self.jurisdiction} state civil law, note this limitation.",
            "---",
            "",
        ]

        practice_area = None
        case_summary = None
        legal_issues_list: List[str] = []

        if analysis_result.case_analysis:
            try:
                case_analysis = analysis_result.case_analysis
                if isinstance(case_analysis, str):
                    case_analysis = json.loads(case_analysis)
                practice_area = case_analysis.get("practice_area")
                case_summary = case_analysis.get("case_summary", "Summary unavailable.")
                lines.append("## Case Summary")
                lines.append(case_summary)
                lines.append(f"Practice Area: {practice_area or 'N/A'}")
                lines.append("")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(f"Failed to parse case_analysis for chat: {exc}")

        lines.append("## Parties")
        for party in analysis_result.opposing_parties:
            lines.append(f"- {party.name} ({party.role})")
        lines.append("")

        if analysis_result.multi_stage_result:
            fact_matrix = analysis_result.multi_stage_result.get("fact_matrix", {})
            timeline = fact_matrix.get("timeline", [])[:15]
            financial_data = fact_matrix.get("financial_data", [])[:10]

            if timeline:
                lines.append("## Timeline Highlights")
                for event in timeline:
                    lines.append(
                        f"- {event.get('date', 'Unknown date')}: {event.get('description', '')}"
                        f" [Source: {event.get('source_document', 'Unknown')}]"
                    )
                lines.append("")

            if financial_data:
                lines.append("## Financial Summary")
                for item in financial_data:
                    amount = item.get("amount")
                    if isinstance(amount, (int, float)):
                        summary = f"${amount:,.2f} [{item.get('payment_type', 'unknown')}]"
                    else:
                        summary = item.get("payment_type", "unknown")
                    lines.append(f"- {item.get('description', 'Amount')} - {summary}")
                lines.append("")

            issue_map = analysis_result.multi_stage_result.get("issue_map", {})
            issues = issue_map.get("primary_issues", [])[:5]
            if issues:
                lines.append("## Primary Legal Issues")
                for issue in issues:
                    issue_name = issue.get("issue_name", "Unnamed Issue")
                    legal_issues_list.append(issue_name)
                    lines.append(f"- {issue_name} " f"(confidence: {issue.get('confidence', 'unknown')})")
                lines.append("")

        # Add jurisdiction-specific statute context based on practice area
        statute_context = self._get_relevant_statute_context(
            practice_area=practice_area,
            case_facts=case_summary or "",
            legal_issues=legal_issues_list if legal_issues_list else None,
        )
        if statute_context:
            lines.append(f"## {self.jurisdiction} Statutes Reference")
            lines.append(statute_context)
            lines.append("")

        lines.append("---")
        lines.append("Answer the user's question in a professional, conversational tone.")
        lines.append(
            f"When citing {self.jurisdiction} statutes, use the verified statutes above when applicable."
        )

        return "\n".join(lines)

    def _get_relevant_statute_context(
        self,
        practice_area: Optional[str] = None,
        case_facts: str = "",
        legal_issues: Optional[List[str]] = None,
    ) -> str:
        """Get relevant Florida statute context for the system prompt.

        Args:
        ----
            practice_area: The case's practice area (e.g., "Landlord-Tenant")
            case_facts: Summary of case facts
            legal_issues: List of identified legal issues

        Returns:
        -------
            Formatted statute context string for the system prompt

        """
        try:
            # Get statute recommendations based on case context
            recommendations = self.statute_service.recommend_statutes(
                case_facts=case_facts,
                legal_issues=legal_issues,
                case_type=practice_area,
                limit=10,  # Include up to 10 relevant statutes
            )

            if not recommendations:
                logger.info("No relevant statutes found for case context")
                return ""

            # Format the recommendations for the prompt
            context = self.statute_service.get_statute_context_for_prompt(
                recommendations=recommendations,
                max_statutes=8,  # Include up to 8 in the actual context
            )

            logger.info(
                f"Added {len(recommendations)} {self.jurisdiction} statutes to chat context",
                extra={"practice_area": practice_area, "statute_count": len(recommendations)},
            )

            return context

        except Exception as exc:
            logger.warning(f"Failed to get statute context: {exc}")
            return ""
