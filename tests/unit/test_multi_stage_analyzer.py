"""Unit tests for MultiStageAnalyzer Stage 1 context building."""

from __future__ import annotations

import json
import re

import pytest

from legal_portal.core.data_models import DocumentSummaryStructured
from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer


class FakeOpenAIClient:
    """Minimal OpenAI client stub for Stage 1 tests."""

    def __init__(self) -> None:
        self.last_input = ""

    def get_preferred_model(self, *_args, **_kwargs) -> str:
        return "fake-model"

    def create_response(self, **kwargs):
        self.last_input = kwargs.get("input", "")
        return {
            "success": True,
            "content": json.dumps(
                {
                    "parties": [],
                    "timeline": [],
                    "financial_data": [],
                    "key_documents": [],
                    "preliminary_issues": [],
                    "property_details": None,
                    "extraction_notes": None,
                }
            ),
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "finish_reason": "stop",
        }


class TestMultiStageAnalyzer:
    """Validate Stage 1 document context mapping and truncation behavior."""

    @pytest.mark.asyncio
    async def test_extract_fact_matrix_uses_document_name_and_preserves_tail_context(self):
        """Stage 1 should use schema-correct keys and keep tail content (signature pages)."""
        fake_client = FakeOpenAIClient()
        analyzer = MultiStageAnalyzer(openai_client=fake_client)

        tail_marker = "Counterpart Signature Page - DocuSign Envelope ID 1234"
        long_summary = ("A" * 4800) + "\n" + tail_marker

        doc_summary = DocumentSummaryStructured(
            document_name="Subscription Agreement.pdf",
            document_type="Contract",
            key_content=long_summary,
            parties=["Erica Corley", "Ron Curl"],
            key_dates=[{"date": "2023-10-03", "event": "Subscription agreement signed"}],
            key_amounts=[{"amount": "$120,000.00", "description": "Total investment"}],
            important_details=["Executed agreement attached"],
        )

        await analyzer._extract_fact_matrix(
            intake_content="Client intake context",
            document_summaries=[doc_summary],
            jurisdiction="Florida",
        )

        assert fake_client.last_input

        match = re.search(
            r"DOCUMENT SUMMARIES:\n(.*?)\n\nExtract and structure the following facts:",
            fake_client.last_input,
            re.DOTALL,
        )
        assert match, "Could not locate DOCUMENT SUMMARIES block in Stage 1 prompt"

        docs_context = json.loads(match.group(1))
        assert len(docs_context) == 1

        doc_context = docs_context[0]
        assert doc_context["filename"] == "Subscription Agreement.pdf"
        assert doc_context["parties"] == ["Erica Corley", "Ron Curl"]
        assert doc_context["dates"][0]["event"] == "Subscription agreement signed"
        assert tail_marker in doc_context["content_summary"]

    def test_condense_doc_summary_preserves_head_and_tail(self):
        """Long summaries should include both start and end segments."""
        summary = "HEAD-" + ("X" * 7000) + "-TAIL"
        condensed = MultiStageAnalyzer._condense_doc_summary_for_fact_matrix(summary, max_chars=1000, tail_chars=300)

        assert condensed.startswith("HEAD-")
        assert "-TAIL" in condensed
        assert "middle omitted for brevity" in condensed
