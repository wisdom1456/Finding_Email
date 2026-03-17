"""Generate opposing-party demand letters."""

from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import markdown2

from legal_portal.core.data_models import DeepAnalysis, DocumentSummaryStructured, FactMatrix, Party
from legal_portal.services.shared.document_formatter import DocumentFormatterService
from legal_portal.services.letters.letter_strategy_service import LetterStrategyService
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.markdown_utils import clean_markdown_response
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


class DemandLetterService:
    """Generates professional demand letters targeted at a specific opposing party."""

    JURISDICTION_STATUTE_EXAMPLES = {
        "Florida": "Fla. Stat. § 83.51",
        "New Mexico": "N.M. Stat. Ann. § 57-12-2",
    }

    def __init__(self, openai_client: OpenAIClient) -> None:
        self.client = openai_client

    async def generate_demand_letter(
        self,
        fact_matrix_dict: dict,
        deep_analysis_dict: dict,
        target_party_name: str,
        demand_amount: Optional[float],
        demand_deadline: str,
        specific_demands: List[str],
        attorney_info: Dict[str, Optional[str]],
        client_name: Optional[str] = None,
        document_summaries: Optional[List[dict]] = None,
        jurisdiction: str = "Florida",  # Added jurisdiction parameter
        strategy_object: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a formal demand letter for a specific opposing party."""
        html, _markdown = await self.generate_demand_letter_with_markdown(
            fact_matrix_dict=fact_matrix_dict,
            deep_analysis_dict=deep_analysis_dict,
            target_party_name=target_party_name,
            demand_amount=demand_amount,
            demand_deadline=demand_deadline,
            specific_demands=specific_demands,
            attorney_info=attorney_info,
            client_name=client_name,
            document_summaries=document_summaries,
            jurisdiction=jurisdiction,
            strategy_object=strategy_object,
        )
        return html

    async def generate_demand_letter_with_markdown(
        self,
        fact_matrix_dict: dict,
        deep_analysis_dict: dict,
        target_party_name: str,
        demand_amount: Optional[float],
        demand_deadline: str,
        specific_demands: List[str],
        attorney_info: Dict[str, Optional[str]],
        client_name: Optional[str] = None,
        document_summaries: Optional[List[dict]] = None,
        jurisdiction: str = "Florida",
        strategy_object: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """Generate demand letter and return (html, markdown) for post-processing."""
        markdown_content = ""
        async for token in self.stream_demand_letter(
            fact_matrix_dict=fact_matrix_dict,
            deep_analysis_dict=deep_analysis_dict,
            target_party_name=target_party_name,
            demand_amount=demand_amount,
            demand_deadline=demand_deadline,
            specific_demands=specific_demands,
            attorney_info=attorney_info,
            client_name=client_name,
            document_summaries=document_summaries,
            jurisdiction=jurisdiction,
            strategy_object=strategy_object,
        ):
            markdown_content += token

        markdown_content = self._clean_markdown_response(markdown_content)

        # Convert markdown to HTML
        html = markdown2.markdown(
            markdown_content, extras=["tables", "smarty-pants", "fenced-code-blocks", "cuddled-lists"]
        )

        # Apply professional formatting using DocumentFormatterService
        formatted_html = DocumentFormatterService.format_demand_letter(
            letter_html=html, recipient_name=target_party_name
        )

        return formatted_html, markdown_content

    async def stream_demand_letter(
        self,
        fact_matrix_dict: dict,
        deep_analysis_dict: dict,
        target_party_name: str,
        demand_amount: Optional[float],
        demand_deadline: str,
        specific_demands: List[str],
        attorney_info: Dict[str, Optional[str]],
        client_name: Optional[str] = None,
        document_summaries: Optional[List[dict]] = None,
        jurisdiction: str = "Florida",
        strategy_object: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a formal demand letter for a specific opposing party."""
        fact_matrix = FactMatrix(**fact_matrix_dict)
        deep_analysis = DeepAnalysis(**deep_analysis_dict)
        party = next((p for p in fact_matrix.parties if p.name == target_party_name), None)
        if not party:
            raise ValueError(f"Target party '{target_party_name}' not found in fact matrix.")

        # Convert document summaries if provided
        doc_summaries = []
        if document_summaries:
            for doc_dict in document_summaries:
                try:
                    doc_summaries.append(DocumentSummaryStructured(**doc_dict))
                except Exception as e:
                    logger.warning(f"Failed to parse document summary: {e}")

        prompt = self._build_demand_prompt(
            target_party_name=target_party_name,
            party_context=self._build_party_context(fact_matrix, party),
            analysis_context=self._format_analysis_context(deep_analysis, doc_summaries),
            demand_amount=demand_amount,
            demand_deadline=demand_deadline,
            specific_demands=self._format_demands(specific_demands),
            attorney_name=attorney_info.get("name") or "Attorney",
            firm_name=attorney_info.get("firm") or "",
            contact_phone=attorney_info.get("phone") or "",
            contact_email=attorney_info.get("email") or "",
            client_name=client_name or "Client",
            jurisdiction_name=jurisdiction,
            strategy_object=strategy_object,
        )

        logger.info(f"Streaming demand letter for {target_party_name} in {jurisdiction}")
        model = self.client.get_preferred_model("letter_generation", "gpt-5.4")

        async for token in self.client.create_response_stream(
            model=model,
            instructions=(
                f"You are a senior {jurisdiction} attorney drafting a formal demand letter. "
                "Be professional, assertive, and precise. "
                "Output clean content without markdown code fences or extra formatting. "
                "Use proper HTML-compatible line breaks and structure."
            ),
            input=prompt,
            reasoning_effort="low" if self.client._is_gpt5_model(model) else None,
        ):
            yield token

    def _build_demand_prompt(
        self,
        target_party_name: str,
        party_context: str,
        analysis_context: str,
        demand_amount: Optional[float],
        demand_deadline: str,
        specific_demands: str,
        attorney_name: str,
        firm_name: str,
        contact_phone: str,
        contact_email: str,
        client_name: str,
        jurisdiction_name: str,
        strategy_object: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build demand-letter prompt using normalized context values."""
        statute_example = self.JURISDICTION_STATUTE_EXAMPLES.get(
            jurisdiction_name,
            self.JURISDICTION_STATUTE_EXAMPLES["Florida"],
        )
        demand_amount_text = self._format_demand_amount_for_prompt(demand_amount)

        base_prompt = self._load_template().format(
            target_party_name=target_party_name,
            party_context=party_context,
            analysis_context=analysis_context,
            demand_amount=demand_amount_text,
            demand_deadline=demand_deadline,
            specific_demands=specific_demands,
            attorney_name=attorney_name,
            firm_name=firm_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            client_name=client_name,
            jurisdiction_name=jurisdiction_name,
            statute_example=statute_example,
        )
        directives = self._build_specificity_directives(strategy_object)
        return f"{base_prompt}\n\n{directives}"

    def _format_demand_amount_for_prompt(self, demand_amount: Optional[float]) -> str:
        """Format demand amount and avoid unresolved placeholders in prompts."""
        if demand_amount is None:
            return "To be determined based on currently documented losses."
        return f"${demand_amount:,.2f}"

    def _clean_markdown_response(self, response_text: str) -> str:
        """Strip code fences and normalize streamed markdown output."""
        return clean_markdown_response(response_text)

    def _build_party_context(self, fact_matrix: FactMatrix, party: Party) -> str:
        timeline = [
            event for event in fact_matrix.timeline if party.name.lower() in event.description.lower()
        ]
        financials = [
            item for item in fact_matrix.financial_data if party.name.lower() in item.description.lower()
        ]

        lines = [
            f"Party Name: {party.name}",
            f"Role: {party.role}",
            f"Entity Type: {party.entity_type or 'unspecified'}",
        ]
        if party.contact_info:
            lines.append(f"Contact Info: {party.contact_info}")

        # Add property address if available
        if fact_matrix.property_details and fact_matrix.property_details.address:
            lines.append(f"Property Address: {fact_matrix.property_details.address}")
            if fact_matrix.property_details.property_type:
                lines.append(f"Property Type: {fact_matrix.property_details.property_type}")

        lines.append("\nTimeline Highlights:")
        if timeline:
            for event in timeline:
                # Format date in "on or about [date]" style for formal letters
                date_str = event.date if event.date else "unknown date"
                lines.append(
                    f"- On or about {date_str}: {event.description} (Source: {event.source_document})"
                )
        else:
            lines.append("- No events tied explicitly to this party.")

        lines.append("\nFinancial Exposure:")
        if financials:
            for entry in financials:
                lines.append(
                    f"- {entry.description}: ${entry.amount:,.2f} ({entry.payment_type or 'unspecified'})"
                )
        else:
            lines.append("- No party-specific financial amounts recorded.")

        return "\n".join(lines)

    def _format_analysis_context(
        self,
        deep_analysis: DeepAnalysis,
        document_summaries: Optional[List[DocumentSummaryStructured]] = None,
    ) -> str:
        """Format analysis context with explicit extraction of citations and contract provisions.

        This ensures case citations, statute references, and contract provisions are clearly
        presented to the AI for inclusion in the demand letter's Legal Analysis section.
        """
        context_lines = ["LEGAL ANALYSIS CONTEXT:\n"]

        # Extract contract clauses from document summaries
        contract_clauses = []
        key_quotes = []
        if document_summaries:
            for doc in document_summaries:
                # Check for contract clauses in structured_data
                if doc.structured_data and doc.structured_data.contract_clauses:
                    for clause in doc.structured_data.contract_clauses:
                        contract_clauses.append(
                            {
                                "document": doc.document_name,
                                "clause_id": clause.clause_id,
                                "description": clause.description,
                                "snippet": clause.snippet,
                            }
                        )

                # Extract key quotes that might be contract provisions
                if doc.key_quotes:
                    for quote in doc.key_quotes:
                        key_quotes.append({"document": doc.document_name, "quote": quote})

        # Display contract clauses prominently
        if contract_clauses:
            context_lines.append("\n=== CONTRACT PROVISIONS (MUST QUOTE IN LEGAL ANALYSIS) ===")
            for clause in contract_clauses:
                context_lines.append(f"\nDocument: {clause['document']}")
                if clause["clause_id"]:
                    context_lines.append(f"Section/Article: {clause['clause_id']}")
                context_lines.append(f"Description: {clause['description']}")
                if clause["snippet"]:
                    context_lines.append(f'Verbatim Text: "{clause["snippet"]}"')

        # Display key quotes
        if key_quotes:
            context_lines.append("\n=== KEY QUOTES FROM DOCUMENTS ===")
            for item in key_quotes[:10]:  # Limit to first 10
                context_lines.append(f'\nFrom {item["document"]}: "{item["quote"]}"')

        # Extract all case citations and statute citations across issues
        all_case_citations = []
        all_statute_citations = []

        for issue in deep_analysis.issue_analyses:
            context_lines.append(f"\n=== ISSUE: {issue.issue_name} ===")
            context_lines.append(f"Legal Standard: {issue.legal_standard}")
            context_lines.append(f"Fact Application: {issue.fact_application}")

            # Extract case law citations
            if issue.case_law_support:
                context_lines.append("\nCASE LAW SUPPORT:")
                context_lines.append(issue.case_law_support)
                all_case_citations.append(issue.case_law_support)

            # Extract statute analysis
            if issue.statute_analysis:
                context_lines.append("\nSTATUTE ANALYSIS:")
                context_lines.append(issue.statute_analysis)
                all_statute_citations.append(issue.statute_analysis)

            # Remedies
            context_lines.append(f"\nRemedies Available: {', '.join(issue.remedies_available)}")

            # Supporting evidence
            if issue.supporting_evidence:
                context_lines.append(f"Supporting Evidence: {'; '.join(issue.supporting_evidence)}")

            # Procedural requirements
            if issue.procedural_requirements:
                context_lines.append(f"Procedural Requirements: {issue.procedural_requirements}")

            context_lines.append(f"Confidence Level: {issue.confidence_level}")

        # Overall assessment
        context_lines.append("\n=== OVERALL ASSESSMENT ===")
        context_lines.append(f"Case Strength: {deep_analysis.overall_case_strength}")
        context_lines.append("\nKey Strengths:")
        for strength in deep_analysis.key_strengths:
            context_lines.append(f"  - {strength}")

        context_lines.append("\nKey Challenges:")
        for challenge in deep_analysis.key_challenges:
            context_lines.append(f"  - {challenge}")

        # Summarize available citations for easy reference
        if all_case_citations:
            context_lines.append("\n=== AVAILABLE CASE CITATIONS ===")
            context_lines.append(
                "IMPORTANT: Include these case citations in the Legal Analysis section "
                "of the demand letter."
            )
            for citation in all_case_citations:
                context_lines.append(f"  - {citation}")

        if all_statute_citations:
            context_lines.append("\n=== AVAILABLE STATUTE CITATIONS ===")
            context_lines.append(
                "IMPORTANT: Include these statute citations in the Legal Analysis section "
                "of the demand letter."
            )
            for citation in all_statute_citations:
                context_lines.append(f"  - {citation}")

        return "\n".join(context_lines)

    def _format_demands(self, demands: List[str]) -> str:
        if not demands:
            return "1. Provide full and timely compliance with the outstanding obligations."
        return "\n".join(f"{idx + 1}. {d}" for idx, d in enumerate(demands))

    def _load_template(self) -> str:
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "prompts",
            "demand_letter_prompt.txt",
        )
        with open(template_path, "r", encoding="utf-8") as template_file:
            return template_file.read()

    def _build_specificity_directives(self, strategy_object: Optional[Dict[str, Any]]) -> str:
        """Append late-binding specificity requirements for demand letters."""
        strategy_json = json.dumps(strategy_object or {}, default=str, indent=2)
        return (
            "BALANCED CLIENT STRATEGY DIRECTIVES (LATEST - OVERRIDE EARLIER CONFLICTS):\n"
            "- Keep tone professional and assertive, but not inflammatory.\n"
            "- Avoid artificial internal section labels in the body; maintain smooth professional letter flow.\n"
            "- Include a clear specificity package: target parties, amount mode, deadline, accounting request, "
            "cure ladder, and preservation language.\n"
            "- Present legal theories in strategy_object.ranked_theories priority order.\n"
            "- Lead with the top-ranked theory and tie it to the strongest documentary anchors.\n"
            "- First use of legal terms should include a short plain-language explainer once.\n"
            "- Each major legal paragraph must include at least one factual anchor "
            "(date, amount, document, or communication).\n"
            "- Use readable document labels, not raw upload filenames or internal file keys.\n"
            "- Do not use internal labels or snake_case legal tokens.\n"
            "- Avoid dense stacked parenthetical citations; integrate support naturally in prose.\n"
            "- Avoid unsupported hard accusations.\n"
            "- If amount mode is TBD, do not invent a number.\n\n"
            "STRATEGY OBJECT:\n"
            f"{strategy_json}\n"
        )

    async def build_demand_strategy(
        self,
        *,
        fact_matrix,
        deep_analysis,
        target_party_name: str,
        demand_amount: Optional[float],
        demand_deadline: str,
        specific_demands: Optional[List[str]],
        client_name: str,
        gap_analysis=None,
        timeout_seconds: int = 15,
        allow_model: bool = True,
        model: str = "gpt-5-mini",
    ) -> Dict[str, Any]:
        """Build a demand strategy object for prompt guidance and metadata."""
        strategy_service = LetterStrategyService(self.client)
        return await strategy_service.build_demand_strategy(
            fact_matrix=fact_matrix,
            deep_analysis=deep_analysis,
            target_party_name=target_party_name,
            demand_amount=demand_amount,
            demand_deadline=demand_deadline,
            specific_demands=specific_demands or [],
            client_name=client_name,
            gap_analysis=gap_analysis,
            allow_model=allow_model,
            timeout_seconds=timeout_seconds,
            model=model,
        )
