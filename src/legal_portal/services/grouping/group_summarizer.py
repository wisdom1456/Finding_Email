"""Group-aware document summarization.

Generates consolidated summaries for document groups, reducing N individual
AI calls to 1 group call. Uses type-specific prompts for optimal extraction.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from legal_portal.core.data_models import DocumentGroup, GroupSummary, GroupType
from legal_portal.utils.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

# Model selection by group type
_GROUP_MODEL = {
    GroupType.BANK_STATEMENTS: "gpt-5.4-mini",
    GroupType.PHOTO_SEQUENCE: "gpt-5.4-mini",
    GroupType.EMAIL_THREAD: "gpt-5.5",
    GroupType.CONTRACT_FAMILY: "gpt-5.5",
}


class GroupSummarizer:
    """Summarizes document groups using type-specific AI prompts."""

    def __init__(self, openai_client: OpenAIClient):
        self.openai_client = openai_client

    async def summarize_group(
        self,
        group: DocumentGroup,
        member_texts: Dict[str, str],
        jurisdiction: str = "",
        intake_context: str = "",
    ) -> GroupSummary:
        """Generate a consolidated summary for a document group.

        Args:
            group: The document group to summarize
            member_texts: Mapping of document_id -> extracted text
            jurisdiction: Legal jurisdiction context
            intake_context: Brief intake form context

        Returns:
            GroupSummary with combined narrative and findings
        """
        prompt = self._build_prompt(group, member_texts, jurisdiction, intake_context)
        model = _GROUP_MODEL.get(group.group_type, "gpt-5.5")

        try:
            result = await self.openai_client.create_chat_completion_async(
                model=model,
                messages=[
                    {"role": "system", "content": self._system_prompt(group.group_type)},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            content = result.get("content", "")
            parsed = json.loads(content)

            return GroupSummary(
                group_id=group.group_id,
                group_type=group.group_type,
                label=group.label,
                member_count=group.member_count,
                member_document_names=group.member_document_names,
                combined_narrative=parsed.get("combined_narrative", ""),
                key_findings=parsed.get("key_findings", []),
                structured_data=parsed.get("structured_data", {}),
                legal_significance=parsed.get("legal_significance"),
                key_quotes=parsed.get("key_quotes", []),
                authority_score=group.authority_score,
                extraction_quality="high",
            )
        except Exception as e:
            logger.warning(
                f"[GROUP_SUMMARIZER] AI summarization failed for {group.group_id}, "
                f"using fallback: {e}"
            )
            return self._build_fallback_summary(group, member_texts)

    def _system_prompt(self, group_type: GroupType) -> str:
        """Return type-specific system prompt."""
        base = (
            "You are a legal document analyst. Summarize the following group of "
            "related documents into a single consolidated summary. "
            "Respond with a JSON object containing: combined_narrative (str), "
            "key_findings (list of str), structured_data (dict), "
            "legal_significance (str or null), key_quotes (list of str)."
        )

        type_guidance = {
            GroupType.BANK_STATEMENTS: (
                " These are bank/financial statements from the same institution and account. "
                "Focus on: total deposits, total withdrawals, ending balances over time, "
                "unusual transactions, patterns relevant to the legal case. "
                "Include structured_data with keys: institution, account_hint, "
                "date_range, total_deposits, total_withdrawals, average_balance."
            ),
            GroupType.EMAIL_THREAD: (
                " These are emails in the same thread. "
                "Focus on: the progression of the conversation, key decisions made, "
                "commitments or agreements, tone changes, legally significant statements. "
                "Preserve chronological order. "
                "Include structured_data with keys: participants, date_range, decision_points."
            ),
            GroupType.CONTRACT_FAMILY: (
                " These are a base contract and its amendments/exhibits/schedules. "
                "Focus on: the original terms, what each amendment changed, "
                "current effective terms, any conflicts between documents. "
                "Include structured_data with keys: original_date, amendment_dates, "
                "key_terms_changed, current_effective_terms."
            ),
            GroupType.PHOTO_SEQUENCE: (
                " These are a sequence of related photographs. "
                "Focus on: what the photos collectively depict, any progression or changes, "
                "relevance to the legal case. "
                "Include structured_data with keys: subject_matter, location_if_apparent, "
                "condition_documented."
            ),
        }

        return base + type_guidance.get(group_type, "")

    def _build_prompt(
        self,
        group: DocumentGroup,
        member_texts: Dict[str, str],
        jurisdiction: str,
        intake_context: str,
    ) -> str:
        """Build the user prompt with all member document texts."""
        parts = [f"Document Group: {group.label}"]
        parts.append(f"Group Type: {group.group_type.value}")
        parts.append(f"Number of documents: {group.member_count}")

        if jurisdiction:
            parts.append(f"Jurisdiction: {jurisdiction}")
        if intake_context:
            parts.append(f"Case Context: {intake_context}")
        if group.group_metadata:
            parts.append(f"Group Metadata: {json.dumps(group.group_metadata)}")

        parts.append("\n--- Documents ---\n")

        for doc_id, doc_name in zip(group.member_document_ids, group.member_document_names):
            text = member_texts.get(doc_id, "")
            # Truncate individual docs to keep prompt manageable
            truncated = text[:4000] if text else "(no text extracted)"
            parts.append(f"### {doc_name}\n{truncated}\n")

        return "\n".join(parts)

    def _build_fallback_summary(
        self,
        group: DocumentGroup,
        member_texts: Dict[str, str],
    ) -> GroupSummary:
        """Build a mechanical fallback summary when AI call fails."""
        # Concatenate first 500 chars of each document
        narrative_parts = []
        for doc_id, doc_name in zip(group.member_document_ids, group.member_document_names):
            text = (member_texts.get(doc_id, "") or "")[:500].strip()
            if text:
                narrative_parts.append(f"{doc_name}: {text}")

        combined = "\n\n".join(narrative_parts) if narrative_parts else "No text available."

        return GroupSummary(
            group_id=group.group_id,
            group_type=group.group_type,
            label=group.label,
            member_count=group.member_count,
            member_document_names=group.member_document_names,
            combined_narrative=f"[Fallback summary — AI unavailable] {combined[:3000]}",
            key_findings=[f"Contains {group.member_count} related {group.group_type.value} documents"],
            authority_score=group.authority_score,
            extraction_quality="low",
        )
