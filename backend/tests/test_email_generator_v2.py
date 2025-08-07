from __future__ import annotations

import pytest

from backend.utils.data_models import (
    AnalyzedDocument,
    CaseAnalysisResult,
    EnhancedIntakeAnalysis,
    LegalAssessment,
)
from backend_logic.email_generator import (
    EmailGeneratorV2,
)


# --- Helper: Create a minimal valid CaseAnalysisResult for Devlin ---
def make_valid_devlin_analysis():
    return CaseAnalysisResult(
        intake_analysis=EnhancedIntakeAnalysis(
            client_name="Erik Devlin",
            attorney_name="Attorney Name",
            case_summary="Dispute with contractor over incomplete work.",
            case_type="Construction",
            urgency_level="High",
            key_facts=[
                "Contract signed on 6/9/25 for home renovation.",
                "Contractor failed to complete several items.",
                "Multiple attempts to resolve issues.",
                "Significant financial impact.",
            ],
            legal_claims=["Breach of contract", "Failure to perform"],
        ),
        analyzed_documents=[
            AnalyzedDocument(
                filename="Devlin - Contract for Construction - Highlighted w Items not Completed 6.9.25.pdf",
                document_type="Contract",
                inferred_title="Construction Contract",
                summary="Contract for home renovation, several items not completed.",
                key_information="Contractor failed to complete kitchen and bathroom renovations.",
                relevance_to_case="Central to breach of contract claim.",
            )
        ],
        transcripted_media=[],
        video_insights=[],
        legal_assessment=LegalAssessment(
            case_type="Construction",
            claim_viability="Strong",
            overall_evidence_strength="Strong",
            potential_challenges=[],
            recommended_actions=[
                "Send demand letter",
                "Prepare for possible litigation",
            ],
            demand_letter_appropriate=True,
            urgency_assessment="High",
        ),
        demand_letter_evaluation=None,
        errors=[],
        cost_summary=None,
    )


# --- Helper: Dummy OpenAI client that returns canned responses ---
class DummyOpenAIClient:
    class chat:
        class completions:
            @staticmethod
            def create(model, messages):
                # Always return a non-empty, well-formed HTML string
                class Msg:
                    content = "<p>Test content for section.</p>"

                class Choice:
                    message = Msg()

                class Response:
                    choices = [Choice()]

                return Response()


# --- Test Suite ---


def test_happy_path_devlin():
    """Happy path: All fields populated, HTML well-formed, debug info present."""
    analysis = make_valid_devlin_analysis()
    generator = EmailGeneratorV2(client=DummyOpenAIClient())
    output = generator.generate_email_with_debug(analysis)
    letter = output.letter

    # Assert all essential template fields are not blank
    assert letter.executive_summary.strip() != ""
    assert letter.background_summary.strip() != ""
    assert letter.analysis_and_position.strip() != ""
    assert letter.next_steps.strip() != ""
    assert letter.closing_paragraph.strip() != ""

    # Assert rendered HTML is well-formed (basic check)
    for field in [
        letter.executive_summary,
        letter.background_summary,
        letter.analysis_and_position,
        letter.next_steps,
        letter.closing_paragraph,
    ]:
        assert field.startswith(("<p>", "<h3>", "<"))

    # Assert debug_info contains structure_plan and generated_sections
    debug = output.debug_info
    assert "structure_plan" in debug
    assert "generated_sections" in debug
    assert isinstance(debug["structure_plan"], dict)
    assert isinstance(debug["generated_sections"], dict)


def test_error_handling_fallback(monkeypatch):
    """Simulate a section generation failure and check fallback is used."""
    analysis = make_valid_devlin_analysis()
    generator = EmailGeneratorV2(client=DummyOpenAIClient())

    # Patch _generate_factual_summary_content to return empty string (simulate failure)
    monkeypatch.setattr(
        generator, "_generate_factual_summary_content", lambda *a, **kw: ""
    )

    output = generator.generate_email_with_debug(analysis)
    letter = output.letter

    # Fallback should be used for background_summary (should not be blank)
    assert letter.background_summary.strip() != ""
    # Output is still a complete letter
    assert letter.executive_summary.strip() != ""
    assert letter.next_steps.strip() != ""
    assert letter.closing_paragraph.strip() != ""

    # Check that debug_info.errors contains fallback info
    debug = output.debug_info
    assert any(e.get("fallback_used") for e in debug.get("errors", []))


def test_data_integrity_invalid_input():
    """Invalid input (None or missing fields) triggers correct error or fallback logic."""
    generator = EmailGeneratorV2(client=DummyOpenAIClient())
    # Pass None as analysis
    with pytest.raises(AttributeError):
        generator.generate_email_with_debug(None)
    # Pass analysis missing intake_analysis: should fallback, not error
    analysis = CaseAnalysisResult()
    output = generator.generate_email_with_debug(analysis)
    letter = output.letter
    # Letter should still be generated and not blank
    assert letter.executive_summary.strip() != ""
    assert letter.background_summary.strip() != ""


def test_debug_output_contains_intermediate_data():
    """Debug output includes EmailStructurePlan and generated_sections."""
    analysis = make_valid_devlin_analysis()
    generator = EmailGeneratorV2(client=DummyOpenAIClient())
    output = generator.generate_email_with_debug(analysis)
    debug = output.debug_info
    # Check for structure_plan and generated_sections
    assert "structure_plan" in debug
    assert isinstance(debug["structure_plan"], dict)
    assert "generated_sections" in debug
    assert isinstance(debug["generated_sections"], dict)
    # Should include at least greeting and closing
    assert "greeting" in debug["generated_sections"]
    assert "closing" in debug["generated_sections"]
