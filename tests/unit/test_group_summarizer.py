"""Tests for GroupSummarizer service."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from legal_portal.core.data_models import DocumentGroup, GroupSummary, GroupType
from legal_portal.services.group_summarizer import GroupSummarizer


def _make_group(group_type=GroupType.BANK_STATEMENTS, member_count=3):
    ids = [f"doc_{i}" for i in range(member_count)]
    names = [f"doc_{i}.pdf" for i in range(member_count)]
    return DocumentGroup(
        group_id="grp_test",
        group_type=group_type,
        label=f"Test Group ({member_count} docs)",
        member_document_ids=ids,
        member_document_names=names,
        authority_score=68,
    )


def _make_member_texts(group):
    return {doc_id: f"Content of {name}" for doc_id, name in
            zip(group.member_document_ids, group.member_document_names)}


class TestGroupSummarizer:
    @pytest.mark.asyncio
    async def test_successful_summarization(self):
        mock_client = MagicMock()
        mock_client.create_chat_completion_async = AsyncMock(return_value={
            "content": json.dumps({
                "combined_narrative": "Three bank statements showing steady income.",
                "key_findings": ["Total deposits: $15,000", "No overdrafts"],
                "structured_data": {"institution": "Chase", "total_deposits": 15000},
                "legal_significance": "Demonstrates financial stability.",
                "key_quotes": ["Account balance: $5,200"],
            }),
            "usage": {"total_tokens": 500},
            "model": "gpt-5-mini",
        })

        summarizer = GroupSummarizer(openai_client=mock_client)
        group = _make_group()
        texts = _make_member_texts(group)

        result = await summarizer.summarize_group(group, texts)

        assert isinstance(result, GroupSummary)
        assert result.group_id == "grp_test"
        assert result.combined_narrative == "Three bank statements showing steady income."
        assert len(result.key_findings) == 2
        assert result.extraction_quality == "high"
        assert result.authority_score == 68

    @pytest.mark.asyncio
    async def test_fallback_on_ai_failure(self):
        mock_client = MagicMock()
        mock_client.create_chat_completion_async = AsyncMock(
            side_effect=Exception("API error")
        )

        summarizer = GroupSummarizer(openai_client=mock_client)
        group = _make_group()
        texts = _make_member_texts(group)

        result = await summarizer.summarize_group(group, texts)

        assert isinstance(result, GroupSummary)
        assert result.extraction_quality == "low"
        assert "[Fallback summary" in result.combined_narrative

    @pytest.mark.asyncio
    async def test_model_selection_by_type(self):
        mock_client = MagicMock()
        mock_client.create_chat_completion_async = AsyncMock(return_value={
            "content": json.dumps({
                "combined_narrative": "Email thread summary.",
                "key_findings": [],
                "structured_data": {},
                "legal_significance": None,
                "key_quotes": [],
            }),
            "usage": {"total_tokens": 300},
            "model": "gpt-5.4",
        })

        summarizer = GroupSummarizer(openai_client=mock_client)
        group = _make_group(group_type=GroupType.EMAIL_THREAD, member_count=2)
        texts = _make_member_texts(group)

        await summarizer.summarize_group(group, texts)

        # Email threads should use gpt-5.4
        call_args = mock_client.create_chat_completion_async.call_args
        assert call_args.kwargs.get("model") or call_args[1].get("model") == "gpt-5.4"

    def test_fallback_summary_content(self):
        summarizer = GroupSummarizer(openai_client=MagicMock())
        group = _make_group(member_count=2)
        texts = {"doc_0": "First document content", "doc_1": "Second document content"}

        result = summarizer._build_fallback_summary(group, texts)

        assert result.extraction_quality == "low"
        assert "doc_0.pdf" in result.combined_narrative
        assert result.member_count == 2

    def test_system_prompt_varies_by_type(self):
        summarizer = GroupSummarizer(openai_client=MagicMock())

        bank_prompt = summarizer._system_prompt(GroupType.BANK_STATEMENTS)
        email_prompt = summarizer._system_prompt(GroupType.EMAIL_THREAD)

        assert "deposits" in bank_prompt.lower()
        assert "thread" in email_prompt.lower()
        assert bank_prompt != email_prompt
