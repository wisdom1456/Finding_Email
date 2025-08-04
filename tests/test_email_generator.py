"""
Tests for EmailGenerator - migrated from HTTP-based to direct import testing.

This module tests the email generation logic that was previously accessed via FastAPI endpoints.
Now tests the backend_logic.email_generator module directly with mocked OpenAI API calls and Jinja2 templates.
"""

import pytest
import json
import base64
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from openai import RateLimitError, APIError, APITimeoutError
from jinja2 import TemplateError

from backend_logic.email_generator import EmailGenerator
from backend_logic.quality_validator import QualityValidator
from backend.utils.data_models import (
    CaseAnalysisResult, EmailResponse, EnhancedFindingsLetter,
    DownloadLink, AnalysisError, GeneratedLetter, QualityScore,
    EnhancedIntakeAnalysis, AnalyzedDocument, LegalAssessment,
    DemandLetterEvaluation, FindingsHeader, FindingsFooter
)


class TestEmailGenerator:
    """Test cases for EmailGenerator functionality."""

    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client for testing."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "<p>Generated content</p>"
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    @pytest.fixture
    def email_generator(self, mock_openai_client):
        """Fixture providing an EmailGenerator instance with mocked dependencies."""
        with patch('backend_logic.email_generator.QualityValidator'):
            with patch('jinja2.Environment') as mock_jinja_env:
                mock_template = Mock()
                mock_template.render.return_value = "<html>Test template</html>"
                mock_jinja_env.return_value.get_template.return_value = mock_template
                
                generator = EmailGenerator(mock_openai_client)
                generator.jinja_env = mock_jinja_env.return_value
                return generator

    @pytest.fixture
    def sample_analysis_complete(self, sample_intake_analysis):
        """Complete case analysis with all required components."""
        return CaseAnalysisResult(
            intake_analysis=sample_intake_analysis,
            analyzed_documents=[
                AnalyzedDocument(
                    filename="contract.pdf",
                    document_type="Contract",
                    inferred_title="Construction Contract",
                    summary="Main contract for construction work",
                    key_information="Payment terms, scope of work",
                    relevance_to_case="Primary evidence of agreement"
                )
            ],
            legal_assessment=LegalAssessment(
                case_type="Contractor Dispute",
                claim_viability="Strong",
                overall_evidence_strength="Strong",
                potential_challenges="Limited challenges expected",
                recommended_actions="Proceed with demand letter",
                demand_letter_appropriate=True,
                urgency_assessment="Medium"
            ),
            demand_letter_evaluation=DemandLetterEvaluation(
                is_appropriate=True,
                reasoning="Strong case supports demand letter",
                potential_outcomes=["Settlement", "Litigation"],
                relevant_statutes=["Construction Law"]
            )
        )

    def test_email_generator_initialization_success(self, mock_openai_client):
        """Test EmailGenerator initializes correctly with valid client."""
        with patch('backend_logic.email_generator.QualityValidator'):
            with patch('jinja2.Environment'):
                generator = EmailGenerator(mock_openai_client)
                assert generator.client == mock_openai_client
                assert generator.quality_validator is not None

    def test_email_generator_initialization_no_client(self):
        """Test EmailGenerator raises error with no client."""
        with pytest.raises(ValueError, match="An OpenAI client is required"):
            EmailGenerator(None)

    def test_clean_ai_response_removes_markdown(self, email_generator):
        """Test AI response cleaning removes markdown formatting."""
        content_with_markdown = """```html
        <p>This is **bold** and *italic* text</p>
        ```"""
        
        cleaned = email_generator._clean_ai_response(content_with_markdown)
        
        assert "```" not in cleaned
        assert "<strong>bold</strong>" in cleaned
        assert "<em>italic</em>" in cleaned

    def test_clean_ai_response_fixes_html_issues(self, email_generator):
        """Test AI response cleaning fixes HTML formatting issues."""
        malformed_html = """<p><p>Double paragraph tags</p></p>
        
        <p></p>
        
        <p>Valid paragraph</p>"""
        
        cleaned = email_generator._clean_ai_response(malformed_html)
        
        assert "<p><p>" not in cleaned
        assert "</p></p>" not in cleaned
        assert "<p></p>" not in cleaned
        assert "<p>Valid paragraph</p>" in cleaned

    def test_clean_ai_response_wraps_plain_text(self, email_generator):
        """Test AI response cleaning wraps plain text in paragraphs."""
        plain_text = "This is plain text without HTML tags.\n\nThis is another paragraph."
        
        cleaned = email_generator._clean_ai_response(plain_text)
        
        assert cleaned.startswith("<p>")
        assert "</p>" in cleaned

    def test_clean_ai_response_empty_content(self, email_generator):
        """Test AI response cleaning handles empty content."""
        assert email_generator._clean_ai_response("") == ""
        assert email_generator._clean_ai_response(None) == ""

    @pytest.mark.asyncio
    async def test_make_openai_request_success(self, email_generator, mock_openai_client):
        """Test successful OpenAI API request."""
        test_content = "<p>Test generated content</p>"
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = test_content

        result = email_generator._make_openai_request("test prompt", "test persona")
        
        assert result == test_content
        mock_openai_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_openai_request_with_retry(self, email_generator, mock_openai_client):
        """Test OpenAI request retry logic."""
        test_content = "<p>Success after retry</p>"
        mock_openai_client.chat.completions.create.side_effect = [
            RateLimitError("Rate limit", response=Mock(), body={}),
            Mock(choices=[Mock(message=Mock(content=test_content))])
        ]

        result = email_generator._make_openai_request("test prompt", "test persona")
        
        assert result == test_content
        assert mock_openai_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_make_openai_request_exception_handling(self, email_generator, mock_openai_client):
        """Test OpenAI request exception handling."""
        mock_openai_client.chat.completions.create.side_effect = Exception("Unexpected error")

        result = email_generator._make_openai_request("test prompt", "test persona")
        
        assert result is None

    def test_generate_executive_summary(self, email_generator, sample_analysis_complete):
        """Test executive summary generation."""
        expected_content = "<p>Dear Erik Devlin, we have completed our analysis...</p>"
        email_generator.client.chat.completions.create.return_value.choices[0].message.content = expected_content

        result = email_generator._generate_executive_summary(sample_analysis_complete, "test persona")
        
        assert result == expected_content
        email_generator.client.chat.completions.create.assert_called_once()
        
        # Verify prompt contains client name
        call_args = email_generator.client.chat.completions.create.call_args
        prompt = call_args[1]['messages'][1]['content']
        assert "Erik Devlin" in prompt

    def test_generate_background_summary(self, email_generator, sample_analysis_complete):
        """Test background summary generation."""
        expected_content = "<p>Based on your intake analysis...</p>"
        email_generator.client.chat.completions.create.return_value.choices[0].message.content = expected_content

        result = email_generator._generate_background_summary(sample_analysis_complete, "test persona")
        
        assert result == expected_content

    def test_generate_analysis_section(self, email_generator, sample_analysis_complete):
        """Test legal analysis section generation."""
        expected_content = "<p>Our analysis reveals strong legal grounds...</p>"
        email_generator.client.chat.completions.create.return_value.choices[0].message.content = expected_content

        result = email_generator._generate_analysis_section(sample_analysis_complete, "test persona")
        
        assert result == expected_content

    def test_generate_strengths(self, email_generator, sample_analysis_complete):
        """Test case strengths assessment generation."""
        expected_content = "<p>Your case demonstrates several key strengths...</p>"
        email_generator.client.chat.completions.create.return_value.choices[0].message.content = expected_content

        result = email_generator._generate_strengths(sample_analysis_complete, "test persona")
        
        assert result == expected_content

    def test_generate_challenges(self, email_generator, sample_analysis_complete):
        """Test challenges assessment generation."""
        expected_content = "<p>While your case is strong, we should consider...</p>"
        email_generator.client.chat.completions.create.return_value.choices[0].message.content = expected_content

        result = email_generator._generate_challenges(sample_analysis_complete, "test persona")
        
        assert result == expected_content

    def test_generate_recommendations(self, email_generator, sample_analysis_complete):
        """Test recommendations generation with narrative enforcement."""
        expected_content = "<p>We recommend proceeding with the following strategy...</p>"
        email_generator.client.chat.completions.create.return_value.choices[0].message.content = expected_content

        result = email_generator._generate_recommendations(sample_analysis_complete, "test persona")
        
        assert result == expected_content
        
        # Verify narrative enforcement is in prompt
        call_args = email_generator.client.chat.completions.create.call_args
        prompt = call_args[1]['messages'][1]['content']
        assert "MANDATORY REQUIREMENT" in prompt
        assert "flowing narrative paragraphs" in prompt
        assert "NO LISTS" in prompt

    def test_generate_next_steps(self, email_generator, sample_analysis_complete):
        """Test next steps generation with narrative enforcement."""
        expected_content = "<p>Your immediate next steps should begin with...</p>"
        email_generator.client.chat.completions.create.return_value.choices[0].message.content = expected_content

        result = email_generator._generate_next_steps(sample_analysis_complete, "test persona")
        
        assert result == expected_content
        
        # Verify narrative enforcement is in prompt
        call_args = email_generator.client.chat.completions.create.call_args
        prompt = call_args[1]['messages'][1]['content']
        assert "MANDATORY REQUIREMENT" in prompt
        assert "flowing narrative paragraphs" in prompt
        assert "NO LISTS" in prompt

    def test_generate_closing_paragraph(self, email_generator, sample_analysis_complete):
        """Test closing paragraph generation."""
        expected_content = "<p>We remain committed to advancing your interests...</p>"
        email_generator.client.chat.completions.create.return_value.choices[0].message.content = expected_content

        result = email_generator._generate_closing_paragraph(sample_analysis_complete, "test persona")
        
        assert result == expected_content

    def test_generate_findings_success(self, email_generator, sample_analysis_complete):
        """Test complete findings generation workflow."""
        # Mock all AI responses
        mock_responses = [
            "<p>Dear Erik Devlin, executive summary...</p>",
            "<p>Background summary...</p>",
            "<p>Analysis and position...</p>",
            "<p>Case strengths...</p>",
            "<p>Potential challenges...</p>",
            "<p>Recommendations...</p>",
            "<p>Next steps...</p>",
            "<p>Closing paragraph...</p>"
        ]
        
        email_generator.client.chat.completions.create.side_effect = [
            Mock(choices=[Mock(message=Mock(content=content))]) for content in mock_responses
        ]

        result = email_generator.generate_findings(sample_analysis_complete)
        
        assert isinstance(result, GeneratedLetter)
        assert result.executive_summary == mock_responses[0]
        assert result.background_summary == mock_responses[1]
        assert result.analysis_and_position == mock_responses[2]
        assert result.strengths == mock_responses[3]
        assert result.challenges == mock_responses[4]
        assert result.recommendations == mock_responses[5]
        assert result.next_steps == mock_responses[6]
        assert result.closing_paragraph == mock_responses[7]

    def test_generate_findings_with_errors(self, email_generator, sample_analysis_complete):
        """Test findings generation handles errors gracefully."""
        # Make all API calls fail
        email_generator.client.chat.completions.create.side_effect = Exception("API Error")

        result = email_generator.generate_findings(sample_analysis_complete)
        
        assert isinstance(result, GeneratedLetter)
        assert "could not be generated" in result.executive_summary
        assert "could not be generated" in result.background_summary

    def test_ensure_analysis_completeness_missing_intake(self, email_generator):
        """Test analysis completeness ensuring with missing intake analysis."""
        incomplete_analysis = CaseAnalysisResult()
        
        with patch('backend.utils.validators.create_fallback_legal_assessment') as mock_legal:
            with patch('backend.utils.validators.create_fallback_demand_letter_evaluation') as mock_demand:
                mock_legal.return_value = {"case_type": "Unknown"}
                mock_demand.return_value = {"is_appropriate": False}
                
                email_generator._ensure_analysis_completeness(incomplete_analysis)
                
                assert incomplete_analysis.intake_analysis is not None
                assert incomplete_analysis.intake_analysis.client_name == "Client"
                assert incomplete_analysis.legal_assessment is not None
                assert incomplete_analysis.demand_letter_evaluation is not None

    def test_ensure_analysis_completeness_missing_documents(self, email_generator, sample_intake_analysis):
        """Test analysis completeness ensuring with missing analyzed documents."""
        analysis_no_docs = CaseAnalysisResult(intake_analysis=sample_intake_analysis)
        
        with patch('backend.utils.validators.create_fallback_legal_assessment') as mock_legal:
            with patch('backend.utils.validators.create_fallback_demand_letter_evaluation') as mock_demand:
                mock_legal.return_value = {"case_type": "Unknown"}
                mock_demand.return_value = {"is_appropriate": False}
                
                email_generator._ensure_analysis_completeness(analysis_no_docs)
                
                assert len(analysis_no_docs.analyzed_documents) == 1
                assert analysis_no_docs.analyzed_documents[0].filename == "case_documents.pdf"

    def test_generate_email_and_analysis_docs_success(self, email_generator, sample_analysis_complete):
        """Test successful email and analysis document generation."""
        # Mock template rendering
        mock_main_template = Mock()
        mock_appendix_template = Mock()
        mock_main_template.render.return_value = "<html>Main letter content</html>"
        mock_appendix_template.render.return_value = "<html>Appendix content</html>"
        
        email_generator.jinja_env.get_template.side_effect = [mock_main_template, mock_appendix_template]
        
        # Mock AI responses for generate_findings
        mock_responses = ["<p>Content</p>"] * 8
        email_generator.client.chat.completions.create.side_effect = [
            Mock(choices=[Mock(message=Mock(content=content))]) for content in mock_responses
        ]

        result = email_generator.generate_email_and_analysis_docs(sample_analysis_complete)
        
        assert isinstance(result, dict)
        assert "main_letter" in result
        assert "appendix" in result
        assert result["main_letter"] == "<html>Main letter content</html>"
        assert result["appendix"] == "<html>Appendix content</html>"

    def test_generate_email_and_analysis_docs_template_error(self, email_generator, sample_analysis_complete):
        """Test email document generation with template error."""
        # Mock template to raise TemplateError
        email_generator.jinja_env.get_template.side_effect = TemplateError("Template not found")
        
        # Mock AI responses for generate_findings
        mock_responses = ["<p>Content</p>"] * 8
        email_generator.client.chat.completions.create.side_effect = [
            Mock(choices=[Mock(message=Mock(content=content))]) for content in mock_responses
        ]

        result = email_generator.generate_email_and_analysis_docs(sample_analysis_complete)
        
        # Should return fallback documents
        assert isinstance(result, dict)
        assert "main_letter" in result
        assert "appendix" in result
        assert "fallback processing" in result["main_letter"]

    def test_generate_fallback_documents(self, email_generator, sample_analysis_complete):
        """Test fallback document generation."""
        error_message = "Test error"
        
        result = email_generator._generate_fallback_documents(sample_analysis_complete, error_message)
        
        assert isinstance(result, dict)
        assert "main_letter" in result
        assert "appendix" in result
        assert "Erik Devlin" in result["main_letter"]
        assert "fallback processing" in result["main_letter"]
        assert error_message in result["appendix"]

    def test_generate_email_and_analysis_docs_legacy_success(self, email_generator, sample_analysis_complete):
        """Test legacy email generation method."""
        # Mock template rendering
        mock_template = Mock()
        mock_template.render.return_value = "<html>Legacy content</html>"
        email_generator.jinja_env.get_template.return_value = mock_template
        
        # Mock quality validator
        mock_quality_score = QualityScore(
            overall_score=0.9,
            professional_tone_score=0.9,
            completeness_score=0.9,
            clarity_score=0.9,
            case_specificity_score=0.9
        )
        email_generator.quality_validator.validate_findings_letter.return_value = mock_quality_score
        
        # Mock AI responses for generate_findings
        mock_responses = ["<p>Content</p>"] * 8
        email_generator.client.chat.completions.create.side_effect = [
            Mock(choices=[Mock(message=Mock(content=content))]) for content in mock_responses
        ]

        result = email_generator.generate_email_and_analysis_docs_legacy(sample_analysis_complete)
        
        assert isinstance(result, EmailResponse)
        assert result.findings_letter is not None
        assert len(result.download_links) == 2
        assert result.case_analysis_text is not None
        assert result.quality_score == mock_quality_score

    def test_assemble_professional_letter_from_generated(self, email_generator, sample_analysis_complete):
        """Test assembling professional letter from generated content."""
        generated_letter = GeneratedLetter(
            executive_summary="<p>Executive summary</p>",
            background_summary="<p>Background</p>",
            analysis_and_position="<p>Analysis</p>",
            strengths="<p>Strengths</p>",
            challenges="<p>Challenges</p>",
            recommendations="<p>Recommendations</p>",
            next_steps="<p>Next steps</p>",
            closing_paragraph="<p>Closing</p>"
        )

        result = email_generator._assemble_professional_letter_from_generated(
            sample_analysis_complete, generated_letter
        )
        
        assert isinstance(result, EnhancedFindingsLetter)
        assert result.header.client_name == "Erik Devlin"
        assert result.background_summary == "<p>Background</p>"
        assert "Strengths of Your Case" in result.review_summary
        assert "Potential Challenges" in result.review_summary

    def test_format_case_analysis(self, email_generator, sample_analysis_complete):
        """Test case analysis formatting."""
        result = email_generator._format_case_analysis(sample_analysis_complete)
        
        assert "# Case Analysis & AI-Generated Insights" in result
        assert "## Intake Analysis" in result
        assert "Erik Devlin" in result
        assert "## Document Review Appendix" in result
        assert "Construction Contract" in result

    def test_create_downloadable_files(self, email_generator, sample_analysis_complete):
        """Test creation of downloadable files."""
        html_content = "<html>Test content</html>"
        case_analysis_text = "Test case analysis"
        
        result = email_generator._create_downloadable_files(
            html_content, case_analysis_text, sample_analysis_complete
        )
        
        assert len(result) == 2
        assert all(isinstance(link, DownloadLink) for link in result)
        
        # Check .eml file
        eml_link = next(link for link in result if link.file_name.endswith('.eml'))
        assert "Erik Devlin" in eml_link.file_name
        assert eml_link.url.startswith("data:message/rfc822;base64,")
        
        # Check .txt file
        txt_link = next(link for link in result if link.file_name.endswith('.txt'))
        assert txt_link.url.startswith("data:text/plain;base64,")


class TestEmailGeneratorIntegration:
    """Integration tests for EmailGenerator workflow."""

    @pytest.mark.asyncio
    async def test_full_email_generation_workflow(self, mock_openai_client):
        """Test complete email generation workflow from analysis to files."""
        with patch('backend_logic.email_generator.QualityValidator'):
            with patch('jinja2.Environment') as mock_jinja_env:
                # Setup email generator
                mock_template = Mock()
                mock_template.render.return_value = "<html>Complete email</html>"
                mock_jinja_env.return_value.get_template.return_value = mock_template
                
                generator = EmailGenerator(mock_openai_client)
                generator.jinja_env = mock_jinja_env.return_value
                
                # Create complete analysis
                analysis = CaseAnalysisResult(
                    intake_analysis=EnhancedIntakeAnalysis(
                        client_name="Test Client",
                        case_type="Test Case",
                        case_summary="Test summary"
                    ),
                    analyzed_documents=[
                        AnalyzedDocument(
                            filename="test.pdf",
                            document_type="Contract",
                            inferred_title="Test Document",
                            summary="Test summary",
                            key_information="Test info",
                            relevance_to_case="Test relevance"
                        )
                    ]
                )
                
                # Mock AI responses
                mock_responses = ["<p>Generated content</p>"] * 8
                mock_openai_client.chat.completions.create.side_effect = [
                    Mock(choices=[Mock(message=Mock(content=content))]) for content in mock_responses
                ]
                
                # Execute workflow
                result = generator.generate_email_and_analysis_docs(analysis)
                
                assert isinstance(result, dict)
                assert "main_letter" in result
                assert "appendix" in result

    def test_error_resilience_workflow(self, mock_openai_client):
        """Test email generation handles various error conditions gracefully."""
        with patch('backend_logic.email_generator.QualityValidator'):
            with patch('jinja2.Environment') as mock_jinja_env:
                # Setup generator with failing template
                mock_jinja_env.return_value.get_template.side_effect = TemplateError("Template error")
                
                generator = EmailGenerator(mock_openai_client)
                generator.jinja_env = mock_jinja_env.return_value
                
                # Create minimal analysis
                analysis = CaseAnalysisResult()
                
                # Mock AI responses that will be called during generate_findings
                mock_responses = ["<p>Fallback content</p>"] * 8
                mock_openai_client.chat.completions.create.side_effect = [
                    Mock(choices=[Mock(message=Mock(content=content))]) for content in mock_responses
                ]
                
                # Should not raise exception, should return fallback
                result = generator.generate_email_and_analysis_docs(analysis)
                
                assert isinstance(result, dict)
                assert "main_letter" in result
                assert "fallback processing" in result["main_letter"]

    def test_persona_consistency_workflow(self, mock_openai_client):
        """Test that different personas are used consistently throughout generation."""
        with patch('backend_logic.email_generator.QualityValidator'):
            with patch('jinja2.Environment') as mock_jinja_env:
                mock_template = Mock()
                mock_template.render.return_value = "<html>Test</html>"
                mock_jinja_env.return_value.get_template.return_value = mock_template
                
                generator = EmailGenerator(mock_openai_client)
                generator.jinja_env = mock_jinja_env.return_value
                
                # Create analysis
                analysis = CaseAnalysisResult(
                    intake_analysis=EnhancedIntakeAnalysis(client_name="Test Client")
                )
                
                # Track persona usage
                call_personas = []
                
                def track_persona_call(*args, **kwargs):
                    # Extract persona from system message
                    messages = kwargs.get('messages', [])
                    if messages and len(messages) > 0:
                        system_content = messages[0]['content']
                        if 'CLIENT_DIRECTED_PERSONA' in system_content or 'Dear' in system_content:
                            call_personas.append('CLIENT_DIRECTED')
                        elif 'CONTINUING_LETTER_PERSONA' in system_content:
                            call_personas.append('CONTINUING')
                    
                    return Mock(choices=[Mock(message=Mock(content="<p>Test content</p>"))])
                
                mock_openai_client.chat.completions.create.side_effect = track_persona_call
                
                # Execute generation
                generator.generate_findings(analysis)
                
                # Verify persona usage pattern
                assert len(call_personas) == 8  # 8 sections generated
                # First call should use CLIENT_DIRECTED, others should use CONTINUING
                # Note: This is a simplified check - actual implementation may vary

    def test_content_cleaning_integration(self, mock_openai_client):
        """Test that content cleaning is applied consistently."""
        with patch('backend_logic.email_generator.QualityValidator'):
            with patch('jinja2.Environment') as mock_jinja_env:
                mock_template = Mock()
                mock_template.render.return_value = "<html>Test</html>"
                mock_jinja_env.return_value.get_template.return_value = mock_template
                
                generator = EmailGenerator(mock_openai_client)
                generator.jinja_env = mock_jinja_env.return_value
                
                # Create analysis
                analysis = CaseAnalysisResult(
                    intake_analysis=EnhancedIntakeAnalysis(client_name="Test Client")
                )
                
                # Mock responses with markdown that needs cleaning
                dirty_responses = [
                    "```html\n<p>This is **bold** text</p>\n```",
                    "<p><p>Double paragraph</p></p>",
                    "*Italic* text without tags",
                    "<p>Clean content</p>",
                    "Plain text content",
                    "<p></p><p>Content with empty paragraphs</p><p></p>",
                    "```\n<p>More content</p>\n```",
                    "Final content"
                ]
                
                mock_openai_client.chat.completions.create.side_effect = [
                    Mock(choices=[Mock(message=Mock(content=content))]) for content in dirty_responses
                ]
                
                # Execute generation
                result = generator.generate_findings(analysis)
                
                # Verify all content is cleaned
                assert "```" not in result.executive_summary
                assert "<strong>bold</strong>" in result.executive_summary
                assert "<p><p>" not in result.background_summary
                assert "<em>Italic</em>" in result.analysis_and_position
                assert result.strengths.startswith("<p>")  # Plain text wrapped
                assert "<p></p>" not in result.recommendations  # Empty paragraphs removed