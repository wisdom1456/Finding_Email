"""Recommendation Letter Service - Generates letters based on case recommendations.

This service generates professional letters for the four recommendation categories:
- Proceed (engagement confirmation)
- Request Documents
- Settlement Advisory
- Declination
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import markdown2

from legal_portal.core.data_models import (
    DeepAnalysis,
    DocumentSummaryStructured,
    FactMatrix,
    GapAnalysisResult,
    RecommendedLetterType,
)
from legal_portal.services.shared.document_formatter import DocumentFormatterService
from legal_portal.services.shared.html_sanitizer import sanitize_letter_html
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.type_safety import safe_str_required

logger = get_module_logger(__name__)

# Map letter types to prompt file names
LETTER_TYPE_TO_PROMPT = {
    RecommendedLetterType.PROCEED: "proceed_letter_prompt.txt",
    RecommendedLetterType.REQUEST_DOCUMENTS: "request_documents_letter_prompt.txt",
    RecommendedLetterType.SETTLEMENT_ADVISORY: "settlement_advisory_letter_prompt.txt",
    RecommendedLetterType.DECLINATION: "declination_letter_prompt.txt",
}

# Map letter types to display names for logging
LETTER_TYPE_DISPLAY = {
    RecommendedLetterType.PROCEED: "Engagement Confirmation",
    RecommendedLetterType.REQUEST_DOCUMENTS: "Document Request",
    RecommendedLetterType.SETTLEMENT_ADVISORY: "Settlement Advisory",
    RecommendedLetterType.DECLINATION: "Declination",
}


class RecommendationLetterService:
    """Service for generating recommendation-based letters."""

    def __init__(self, openai_client: OpenAIClient) -> None:
        """Initialize the recommendation letter service.

        Args:
            openai_client: OpenAI client for GPT model calls

        """
        self.client = openai_client
        self.prompts_dir = Path(__file__).parent.parent.parent / "prompts"

    def _get_generation_model(self) -> str:
        """Resolve preferred model for recommendation letter generation."""
        return self.client.get_preferred_model("letter_generation", "gpt-5.5")

    def _load_prompt_template(self, letter_type: RecommendedLetterType) -> str:
        """Load the prompt template for the given letter type.

        Args:
            letter_type: The type of letter to generate

        Returns:
            The prompt template content

        Raises:
            ValueError: If the letter type is not supported
            FileNotFoundError: If the prompt file doesn't exist

        """
        if letter_type not in LETTER_TYPE_TO_PROMPT:
            raise ValueError(f"Unsupported letter type: {letter_type}")

        prompt_file = self.prompts_dir / LETTER_TYPE_TO_PROMPT[letter_type]
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_file}")

        return prompt_file.read_text(encoding="utf-8")

    def _build_context_for_letter(
        self,
        letter_type: RecommendedLetterType,
        gap_analysis: GapAnalysisResult,
        deep_analysis: Optional[DeepAnalysis],
        fact_matrix: Optional[FactMatrix],
        document_summaries: Optional[List[DocumentSummaryStructured]],
        attorney_info: Dict[str, Optional[str]],
        client_name: Optional[str],
        jurisdiction: str,
    ) -> Dict[str, str]:
        """Build the context dictionary for letter template filling.

        Args:
            letter_type: The type of letter to generate
            gap_analysis: Gap analysis result with completeness info
            deep_analysis: Deep analysis with case strength info
            fact_matrix: Extracted facts
            document_summaries: Document summaries
            attorney_info: Attorney contact information
            client_name: Client's name
            jurisdiction: Jurisdiction name (e.g., "Florida")

        Returns:
            Dictionary of template variables

        """
        # Base context
        context = {
            "jurisdiction_name": jurisdiction,
            "attorney_name": attorney_info.get("attorney_name") or "[Attorney Name]",
            "firm_name": attorney_info.get("firm_name") or "[Firm Name]",
            "contact_phone": attorney_info.get("contact_phone") or "[Phone]",
            "contact_email": attorney_info.get("contact_email") or "[Email]",
            "client_name": client_name or "[Client Name]",
            "completeness_score": f"{gap_analysis.overall_completeness_score:.0f}",
            "critical_count": str(gap_analysis.critical_count),
            "high_count": str(gap_analysis.high_count),
            "medium_count": str(gap_analysis.medium_count),
        }

        # Case strength from deep analysis
        if deep_analysis:
            context["case_strength"] = deep_analysis.overall_case_strength
            context["key_strengths"] = "\n".join(
                f"- {s}" for s in deep_analysis.key_strengths
            ) or "- To be determined based on complete documentation"
            context["key_challenges"] = "\n".join(
                f"- {c}" for c in deep_analysis.key_challenges
            ) or "- None identified at this time"
        else:
            context["case_strength"] = "To be determined"
            context["key_strengths"] = "- Pending complete analysis"
            context["key_challenges"] = "- Pending complete analysis"

        # Build client context from fact matrix
        if fact_matrix and fact_matrix.parties:
            client_parties = [p for p in fact_matrix.parties if "client" in p.role.lower()]
            if client_parties:
                client_party = client_parties[0]
                context["client_context"] = (
                    f"Name: {client_party.name}\n"
                    f"Role: {client_party.role}\n"
                    f"Contact: {client_party.contact_info or 'On file'}"
                )
            else:
                context["client_context"] = f"Name: {client_name or '[Client Name]'}"
        else:
            context["client_context"] = f"Name: {client_name or '[Client Name]'}"

        # Build case summary from deep analysis or gap analysis
        if deep_analysis and deep_analysis.issue_analyses:
            issues_summary = "; ".join(
                ia.issue_name for ia in deep_analysis.issue_analyses[:3]
            )
            context["case_summary"] = (
                f"Legal Issues: {issues_summary}\n"
                f"Overall Strength: {deep_analysis.overall_case_strength}\n"
                f"Documentation Completeness: {gap_analysis.overall_completeness_score:.0f}%"
            )
        else:
            context["case_summary"] = (
                f"Documentation Completeness: {gap_analysis.overall_completeness_score:.0f}%\n"
                f"Total Gaps Identified: {gap_analysis.total_gaps}"
            )

        # Letter-type specific context
        if letter_type == RecommendedLetterType.REQUEST_DOCUMENTS:
            context["missing_documents"] = self._format_missing_documents(gap_analysis)

        elif letter_type == RecommendedLetterType.DECLINATION:
            context["declination_reasons"] = self._format_declination_reasons(
                gap_analysis, deep_analysis
            )
            context["critical_issues"] = self._format_critical_issues(gap_analysis)
            context["statute_of_limitations"] = self._get_statute_info(jurisdiction)

        return context

    def _format_missing_documents(self, gap_analysis: GapAnalysisResult) -> str:
        """Format the missing documents list from gap analysis.

        Args:
            gap_analysis: Gap analysis result

        Returns:
            Formatted string of missing documents

        """
        missing = []
        for _category, gaps in gap_analysis.gaps_by_category.items():
            for gap in gaps:
                if gap.severity.value in ["critical", "high"]:
                    missing.append(
                        f"- **{gap.title}** ({gap.severity.value}): {gap.description}"
                    )
                    if gap.recommendations:
                        missing.append(f"  - Recommendation: {gap.recommendations[0]}")

        return "\n".join(missing) if missing else "- Specific documentation needs to be discussed"

    def _format_declination_reasons(
        self,
        gap_analysis: GapAnalysisResult,
        deep_analysis: Optional[DeepAnalysis],
    ) -> str:
        """Format the reasons for declining the case.

        Args:
            gap_analysis: Gap analysis result
            deep_analysis: Deep analysis result

        Returns:
            Formatted string of declination reasons

        """
        reasons = []

        if deep_analysis and not deep_analysis.is_viable:
            reasons.append(f"- {deep_analysis.viability_reasoning or 'Case viability concerns'}")

        if gap_analysis.overall_completeness_score < 30:
            reasons.append(
                f"- Insufficient documentation (completeness score: "
                f"{gap_analysis.overall_completeness_score:.0f}%)"
            )

        if gap_analysis.critical_count >= 3:
            reasons.append(
                f"- Multiple critical gaps identified ({gap_analysis.critical_count} critical issues)"
            )

        if not reasons:
            reasons.append(
                "- After careful review, we have determined we cannot effectively pursue this matter"
            )

        return "\n".join(reasons)

    def _format_critical_issues(self, gap_analysis: GapAnalysisResult) -> str:
        """Format the critical issues from gap analysis.

        Args:
            gap_analysis: Gap analysis result

        Returns:
            Formatted string of critical issues

        """
        critical = []
        for _category, gaps in gap_analysis.gaps_by_category.items():
            for gap in gaps:
                if gap.severity.value == "critical":
                    critical.append(f"- {gap.title}: {gap.impact_on_case}")

        return "\n".join(critical) if critical else "- Specific concerns to be discussed"

    def _get_statute_info(self, jurisdiction: str) -> str:
        """Get statute of limitations information for the jurisdiction.

        Args:
            jurisdiction: Jurisdiction name

        Returns:
            Statute of limitations guidance

        """
        # Common limitation periods by jurisdiction
        statute_info = {
            "Florida": (
                "Florida statutes of limitations vary by claim type:\n"
                "- Written contracts: 5 years (Fla. Stat. § 95.11(2)(b))\n"
                "- Oral contracts: 4 years (Fla. Stat. § 95.11(3)(k))\n"
                "- Negligence: 4 years (Fla. Stat. § 95.11(3)(a))\n"
                "- Fraud: 4 years from discovery (Fla. Stat. § 95.031(2)(a))"
            ),
            "New Mexico": (
                "New Mexico statutes of limitations vary by claim type:\n"
                "- Written contracts: 6 years (NMSA § 37-1-3)\n"
                "- Oral contracts: 6 years (NMSA § 37-1-3)\n"
                "- Negligence/Torts: 3 years (NMSA § 37-1-8)\n"
                "- Fraud: 4 years (NMSA § 37-1-4)"
            ),
        }

        return statute_info.get(
            jurisdiction,
            (
                "Statutes of limitations vary by jurisdiction and claim type. "
                "Please consult with an attorney in your jurisdiction immediately to "
                "understand applicable deadlines."
            ),
        )

    async def generate_recommendation_letter(
        self,
        letter_type: RecommendedLetterType,
        gap_analysis: GapAnalysisResult,
        deep_analysis: Optional[DeepAnalysis] = None,
        fact_matrix: Optional[FactMatrix] = None,
        document_summaries: Optional[List[DocumentSummaryStructured]] = None,
        attorney_info: Optional[Dict[str, Optional[str]]] = None,
        client_name: Optional[str] = None,
        jurisdiction: str = "Florida",
    ) -> str:
        """Generate a recommendation letter of the specified type.

        Args:
            letter_type: Type of letter to generate
            gap_analysis: Gap analysis result
            deep_analysis: Optional deep analysis result
            fact_matrix: Optional fact matrix
            document_summaries: Optional document summaries
            attorney_info: Attorney contact information
            client_name: Client's name
            jurisdiction: Jurisdiction name

        Returns:
            Formatted HTML letter

        """
        letter_display = LETTER_TYPE_DISPLAY.get(letter_type, str(letter_type))
        logger.info(f"[REC_LETTER] Generating {letter_display} letter for {client_name or 'client'}")

        attorney_info = attorney_info or {}

        # Collect all tokens from streaming
        markdown_content = ""
        async for token in self.stream_recommendation_letter(
            letter_type=letter_type,
            gap_analysis=gap_analysis,
            deep_analysis=deep_analysis,
            fact_matrix=fact_matrix,
            document_summaries=document_summaries,
            attorney_info=attorney_info,
            client_name=client_name,
            jurisdiction=jurisdiction,
        ):
            markdown_content += token

        # Convert markdown to HTML
        formatted_html = self.render_markdown_to_html(
            markdown_content,
            letter_type=letter_type,
            client_name=client_name,
        )

        logger.info(f"[REC_LETTER] {letter_display} letter generated successfully")
        return formatted_html

    def render_markdown_to_html(
        self,
        markdown_content: str,
        *,
        letter_type: RecommendedLetterType,
        client_name: Optional[str] = None,
    ) -> str:
        """Convert recommendation markdown into formatted HTML."""
        html = sanitize_letter_html(
            markdown2.markdown(
                markdown_content,
                extras=["tables", "smarty-pants", "fenced-code-blocks", "cuddled-lists"],
            )
        )
        return DocumentFormatterService.format_recommendation_letter(
            letter_html=html,
            letter_type=letter_type.value,
            client_name=client_name or "Client",
        )

    def _stream_instructions_for_letter_type(
        self,
        *,
        letter_type: RecommendedLetterType,
        letter_display: str,
    ) -> str:
        """Return model instructions tuned to each recommendation letter intent."""
        if letter_type == RecommendedLetterType.REQUEST_DOCUMENTS:
            return (
                "You are drafting a professional client document request letter for a law firm. "
                "Prioritize plain-language advisory tone, clear action steps, and practical submission guidance. "
                "Be direct about deadlines and evidence needs without sounding adversarial. "
                "Output only the letter content in markdown format."
            )

        return (
            f"You are drafting a professional {letter_display.lower()} letter for a law firm. "
            f"Follow the provided template structure exactly. Use formal legal language. "
            f"Output only the letter content in markdown format."
        )

    async def repair_recommendation_letter_constraints(
        self,
        draft_markdown: str,
        violations: List[Dict[str, Any]],
        *,
        mode: str = "default",
        model: str = "gpt-5.4-mini",
    ) -> str:
        """Apply a constrained repair pass to recommendation letter markdown."""
        if not draft_markdown.strip() or not violations:
            return draft_markdown

        lines: List[str] = []
        for idx, violation in enumerate(violations[:20], start=1):
            lines.append(
                f"{idx}. [{violation.get('severity', 'warning')}] "
                f"{violation.get('rule', 'unknown')}: {violation.get('message', '')}"
            )

        prompt = (
            "Revise this recommendation letter to fix only the listed quality issues.\n"
            "Do not add new facts or legal claims.\n"
            f"Mode: {mode}\n\n"
            "Violations:\n"
            f"{chr(10).join(lines)}\n\n"
            "Draft letter:\n"
            f"{draft_markdown}\n"
        )

        response = await self.client.create_response_async(
            model=model,
            input=prompt,
            instructions=(
                "You are a legal writing editor. Fix only the listed issues and return "
                "the revised recommendation letter in markdown."
            ),
            reasoning_effort="low",
            verbosity="low",
            max_output_tokens=3000,
        )
        revised = safe_str_required(response.get("content"), "")
        return revised or draft_markdown

    async def stream_recommendation_letter(
        self,
        letter_type: RecommendedLetterType,
        gap_analysis: GapAnalysisResult,
        deep_analysis: Optional[DeepAnalysis] = None,
        fact_matrix: Optional[FactMatrix] = None,
        document_summaries: Optional[List[DocumentSummaryStructured]] = None,
        attorney_info: Optional[Dict[str, Optional[str]]] = None,
        client_name: Optional[str] = None,
        jurisdiction: str = "Florida",
    ) -> AsyncGenerator[str, None]:
        """Stream a recommendation letter of the specified type.

        Args:
            letter_type: Type of letter to generate
            gap_analysis: Gap analysis result
            deep_analysis: Optional deep analysis result
            fact_matrix: Optional fact matrix
            document_summaries: Optional document summaries
            attorney_info: Attorney contact information
            client_name: Client's name
            jurisdiction: Jurisdiction name

        Yields:
            String tokens as they are generated

        """
        attorney_info = attorney_info or {}

        # Load the prompt template
        try:
            prompt_template = self._load_prompt_template(letter_type)
        except (ValueError, FileNotFoundError) as e:
            logger.error(f"[REC_LETTER] Failed to load prompt template: {e}")
            yield f"Error: Unable to load template for {letter_type}"
            return

        # Build context
        context = self._build_context_for_letter(
            letter_type=letter_type,
            gap_analysis=gap_analysis,
            deep_analysis=deep_analysis,
            fact_matrix=fact_matrix,
            document_summaries=document_summaries,
            attorney_info=attorney_info,
            client_name=client_name,
            jurisdiction=jurisdiction,
        )

        # Fill in the template
        try:
            filled_prompt = prompt_template.format(**context)
        except KeyError as e:
            logger.error(f"[REC_LETTER] Missing template variable: {e}")
            # Try with partial formatting
            for key, value in context.items():
                prompt_template = prompt_template.replace(f"{{{key}}}", str(value))
            filled_prompt = prompt_template

        # Get model for letter generation
        model = self._get_generation_model()

        letter_display = LETTER_TYPE_DISPLAY.get(letter_type, str(letter_type))
        logger.info(
            f"[REC_LETTER] Streaming {letter_display} letter | "
            f"model={model} prompt_chars={len(filled_prompt)}"
        )

        # Stream the response
        try:
            async for token in self.client.create_response_stream(
                model=model,
                instructions=self._stream_instructions_for_letter_type(
                    letter_type=letter_type,
                    letter_display=letter_display,
                ),
                input=filled_prompt,
                reasoning_effort="medium" if self.client._is_gpt5_model(model) else None,
            ):
                yield token

        except Exception as e:
            logger.error(f"[REC_LETTER] Error streaming letter: {e}", exc_info=True)
            yield f"\n\n[Error generating letter: {str(e)}]"
