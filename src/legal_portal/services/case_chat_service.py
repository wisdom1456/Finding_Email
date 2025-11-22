"""Service for case-specific AI chat with complete context."""

from __future__ import annotations

from typing import Dict, List

from legal_portal.core.data_models import ProcessingResult
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


class CaseChatService:
    """Provides conversational responses about a case with full factual context."""

    def __init__(self, openai_client: OpenAIClient):
        self.client = openai_client

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
        lines: List[str] = [
            "You are an AI legal assistant with full knowledge of this case.",
            "Answer questions using the facts, timeline, financial data, and legal analysis provided.",
            "Always cite specific documents conversationally (e.g., 'According to the Contract dated...').",
            "If the data does not include the answer, say so clearly.",
            "---",
            "",
        ]

        if analysis_result.case_analysis:
            try:
                case_analysis = analysis_result.case_analysis
                if isinstance(case_analysis, str):
                    import json

                    case_analysis = json.loads(case_analysis)
                lines.append("## Case Summary")
                lines.append(case_analysis.get("case_summary", "Summary unavailable."))
                lines.append(f"Practice Area: {case_analysis.get('practice_area', 'N/A')}")
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
                    lines.append(
                        f"- {issue.get('issue_name', 'Unnamed Issue')} "
                        f"(confidence: {issue.get('confidence', 'unknown')})"
                    )
                lines.append("")

        lines.append("---")
        lines.append("Answer the user's question in a professional, conversational tone.")

        return "\n".join(lines)
