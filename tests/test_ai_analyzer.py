"""
Tests for AIAnalyzer - migrated from HTTP-based to direct import testing.

This module tests the AI analysis logic that was previously accessed via FastAPI endpoints.
Now tests the backend_logic.ai_analyzer module directly with mocked OpenAI API calls.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from openai import RateLimitError, APIError, APITimeoutError

from backend_logic.ai_analyzer import AIAnalyzer
from backend_logic.document_processor import DocumentProcessor
from backend.utils.data_models import (
    ProcessedDocument, DocumentType, FileType,
    EnhancedIntakeAnalysis, AnalyzedDocument, LegalAssessment,
    DemandLetterEvaluation, CaseAnalysisResult, AnalysisError, AIAnalysisError
)


class TestAIAnalyzer:
    """Test cases for AIAnalyzer functionality."""

    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client for testing."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '{"test": "response"}'
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    @pytest.fixture
    def mock_doc_processor(self):
        """Mock DocumentProcessor for testing."""
        return Mock(spec=DocumentProcessor)

    @pytest.fixture
    def ai_analyzer(self, mock_openai_client, mock_doc_processor):
        """Fixture providing an AIAnalyzer instance with mocked dependencies."""
        return AIAnalyzer(mock_openai_client, mock_doc_processor)

    @pytest.fixture
    def sample_intake_document(self):
        """Sample intake document for testing."""
        return ProcessedDocument(
            file_name="intake_form.pdf",
            content="Client Name: Erik Devlin\nCase Type: Contractor Dispute\nSummary: Construction work incomplete...",
            file_type=FileType.PDF,
            document_type=DocumentType.INTAKE_FORM
        )

    @pytest.fixture
    def sample_case_document(self):
        """Sample case document for testing."""
        return ProcessedDocument(
            file_name="contract.pdf",
            content="CONSTRUCTION CONTRACT between Erik Devlin and LLW Construction...",
            file_type=FileType.PDF,
            document_type=DocumentType.CASE_DOCUMENT
        )

    @pytest.fixture
    def sample_intake_analysis(self):
        """Sample intake analysis for testing."""
        return EnhancedIntakeAnalysis(
            client_name="Erik Devlin",
            case_type="Contractor Dispute",
            case_summary="Construction work incomplete",
            urgency_level="Medium",
            client_priorities=["Completion", "Damages"],
            key_facts=["Incomplete work"],
            legal_claims=["Breach of contract"]
        )

    @pytest.fixture
    def sample_case_analysis(self):
        """Sample case analysis for testing."""
        return CaseAnalysisResult(
            intake_analysis=EnhancedIntakeAnalysis(
                client_name="Erik Devlin",
                case_type="Contractor Dispute",
                case_summary="Contractor dispute case",
                urgency_level="Medium",
                client_priorities=["Completion"],
                key_facts=["Incomplete work"],
                legal_claims=["Breach of contract"]
            ),
            analyzed_documents=[
                AnalyzedDocument(
                    filename="contract.pdf",
                    document_type="Contract",
                    inferred_title="Construction Contract",
                    summary="Standard construction contract",
                    key_information="Payment terms and scope of work",
                    relevance_to_case="Primary evidence of agreement"
                )
            ],
            legal_assessment=LegalAssessment(
                case_type="Contractor Dispute",
                claim_viability="Strong",
                overall_evidence_strength="Strong",
                potential_challenges="Some challenges",
                recommended_actions="Take action",
                demand_letter_appropriate=True,
                urgency_assessment="Medium"
            ),
            demand_letter_evaluation=DemandLetterEvaluation(
                is_appropriate=True,
                reasoning="Good case for demand letter",
                potential_outcomes=["Settlement", "Litigation"],
                relevant_statutes=["Statute 1", "Statute 2"]
            )
        )

    def test_ai_analyzer_initialization(self, mock_openai_client, mock_doc_processor):
        """Test AIAnalyzer initializes correctly."""
        analyzer = AIAnalyzer(mock_openai_client, mock_doc_processor)
        assert analyzer.client == mock_openai_client
        assert analyzer.doc_processor == mock_doc_processor

    @pytest.mark.asyncio
    async def test_make_openai_request_success(self, ai_analyzer, mock_openai_client):
        """Test successful OpenAI API request."""
        test_response = {"client_name": "Test Client", "case_type": "Test Case"}
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(test_response)

        result = await ai_analyzer._make_openai_request("test prompt", "gpt-4o-mini")
        
        assert result == test_response
        mock_openai_client.chat.completions.create.assert_called_once_with(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "test prompt"}],
            temperature=0.2,
            response_format={"type": "json_object"}
        )

    @pytest.mark.asyncio
    async def test_make_openai_request_json_decode_error(self, ai_analyzer, mock_openai_client):
        """Test handling of JSON decode errors."""
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = "Invalid JSON"

        with pytest.raises(AIAnalysisError, match="Failed to parse AI response as JSON"):
            await ai_analyzer._make_openai_request("test prompt", "gpt-4o-mini")

    @pytest.mark.asyncio
    async def test_make_openai_request_rate_limit_retry(self, ai_analyzer, mock_openai_client):
        """Test retry logic for rate limit errors."""
        # First call raises RateLimitError, second succeeds
        test_response = {"success": True}
        mock_openai_client.chat.completions.create.side_effect = [
            RateLimitError("Rate limit exceeded", response=Mock(), body={}),
            Mock(choices=[Mock(message=Mock(content=json.dumps(test_response)))])
        ]

        result = await ai_analyzer._make_openai_request("test prompt", "gpt-4o-mini")
        
        assert result == test_response
        assert mock_openai_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_make_openai_request_api_error_retry(self, ai_analyzer, mock_openai_client):
        """Test retry logic for API errors."""
        test_response = {"success": True}
        mock_openai_client.chat.completions.create.side_effect = [
            APIError(Mock(), "API Error", body={}),
            Mock(choices=[Mock(message=Mock(content=json.dumps(test_response)))])
        ]

        result = await ai_analyzer._make_openai_request("test prompt", "gpt-4o-mini")
        
        assert result == test_response
        assert mock_openai_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_make_openai_request_generic_exception(self, ai_analyzer, mock_openai_client):
        """Test handling of generic exceptions."""
        mock_openai_client.chat.completions.create.side_effect = Exception("Generic error")

        with pytest.raises(AIAnalysisError, match="Error communicating with OpenAI API"):
            await ai_analyzer._make_openai_request("test prompt", "gpt-4o-mini")

    def test_build_intake_prompt(self, ai_analyzer):
        """Test intake prompt building."""
        content = "Sample intake form content"
        prompt = ai_analyzer._build_intake_prompt(content)
        
        assert "SYSTEM" in prompt
        assert content in prompt
        assert "EnhancedIntakeAnalysis" in prompt
        assert "client_name" in prompt
        assert "case_summary" in prompt
        assert "JSON" in prompt

    def test_build_case_document_prompt(self, ai_analyzer, sample_case_document, sample_intake_analysis):
        """Test case document prompt building."""
        prompt = ai_analyzer._build_case_document_prompt(sample_case_document, sample_intake_analysis)
        
        assert "SYSTEM" in prompt
        assert sample_case_document.file_name in prompt
        assert sample_case_document.content in prompt
        assert sample_intake_analysis.client_name in prompt
        assert sample_intake_analysis.case_type in prompt
        assert "AnalyzedDocument" in prompt

    def test_build_final_assessment_prompt(self, ai_analyzer, sample_case_analysis):
        """Test final assessment prompt building."""
        prompt = ai_analyzer._build_final_assessment_prompt(sample_case_analysis)
        
        assert "SYSTEM" in prompt
        assert "LegalAssessment" in prompt
        assert "DemandLetterEvaluation" in prompt
        assert "legal_assessment" in prompt
        assert "demand_letter_evaluation" in prompt

    @pytest.mark.asyncio
    async def test_analyze_intake_success(self, ai_analyzer, sample_intake_document, mock_openai_client):
        """Test successful intake analysis."""
        intake_response = {
            "client_name": "Erik Devlin",
            "case_type": "Contractor Dispute",
            "case_summary": "Test case summary",
            "urgency_level": "Medium",
            "client_priorities": ["Priority 1"],
            "key_facts": ["Fact 1"],
            "legal_claims": ["Claim 1"]
        }
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(intake_response)

        with patch('backend_logic.ai_analyzer.preprocess_ai_output', return_value=intake_response):
            result = await ai_analyzer.analyze_intake(sample_intake_document)
            
            assert isinstance(result, CaseAnalysisResult)
            assert result.intake_analysis is not None
            assert result.intake_analysis.client_name == "Erik Devlin"
            assert result.intake_analysis.case_type == "Contractor Dispute"
            assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_analyze_intake_no_content(self, ai_analyzer):
        """Test intake analysis with no content."""
        empty_doc = ProcessedDocument(
            file_name="empty.pdf",
            content="",
            file_type=FileType.PDF,
            document_type=DocumentType.INTAKE_FORM
        )

        result = await ai_analyzer.analyze_intake(empty_doc)
        
        assert isinstance(result, CaseAnalysisResult)
        assert result.intake_analysis is None
        assert len(result.errors) == 1
        assert "No valid intake content" in result.errors[0].error_message

    @pytest.mark.asyncio
    async def test_analyze_intake_validation_error(self, ai_analyzer, sample_intake_document, mock_openai_client):
        """Test intake analysis with validation error."""
        # Return invalid data that will fail validation
        invalid_response = {"invalid_field": "value"}
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(invalid_response)

        with patch('backend_logic.ai_analyzer.preprocess_ai_output', return_value=invalid_response):
            result = await ai_analyzer.analyze_intake(sample_intake_document)
            
            assert isinstance(result, CaseAnalysisResult)
            # The model is designed to be resilient and create defaults even with invalid data
            assert result.intake_analysis is not None
            assert isinstance(result.intake_analysis, EnhancedIntakeAnalysis)
            # Check that it has default/empty values since the input was invalid
            assert result.intake_analysis.client_name is None
            assert result.intake_analysis.case_type is None
            assert result.intake_analysis.client_priorities == []
            assert result.intake_analysis.key_facts == []

    @pytest.mark.asyncio
    async def test_analyze_case_documents_success(self, ai_analyzer, sample_intake_analysis, mock_openai_client):
        """Test successful case documents analysis."""
        documents = [
            ProcessedDocument(
                file_name="doc1.pdf",
                content="Document 1 content",
                file_type=FileType.PDF,
                document_type=DocumentType.CASE_DOCUMENT
            ),
            ProcessedDocument(
                file_name="doc2.pdf", 
                content="Document 2 content",
                file_type=FileType.PDF,
                document_type=DocumentType.CASE_DOCUMENT
            )
        ]
        
        analyzed_doc_response = {
            "filename": "doc1.pdf",
            "document_type": "Contract",
            "inferred_title": "Test Document",
            "summary": "Test summary",
            "key_information": "Test info",
            "relevance_to_case": "Test relevance"
        }
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(analyzed_doc_response)

        with patch('asyncio.sleep', new_callable=AsyncMock):  # Speed up test by mocking sleep
            results = await ai_analyzer.analyze_case_documents(documents, sample_intake_analysis)
            
            assert len(results) == 2
            assert all(isinstance(result, AnalyzedDocument) for result in results)
            assert results[0].filename == "doc1.pdf"

    @pytest.mark.asyncio
    async def test_analyze_case_documents_with_errors(self, ai_analyzer, sample_intake_analysis, mock_openai_client):
        """Test case documents analysis with some errors."""
        documents = [
            ProcessedDocument(
                file_name="good_doc.pdf",
                content="Good document content",
                file_type=FileType.PDF,
                document_type=DocumentType.CASE_DOCUMENT
            ),
            ProcessedDocument(
                file_name="bad_doc.pdf",
                content="Bad document content",
                file_type=FileType.PDF,
                document_type=DocumentType.CASE_DOCUMENT
            )
        ]
        
        good_response = {
            "filename": "good_doc.pdf",
            "document_type": "Contract",
            "inferred_title": "Good Document",
            "summary": "Good summary",
            "key_information": "Good info",
            "relevance_to_case": "Good relevance"
        }
        
        # First call succeeds, second fails
        mock_openai_client.chat.completions.create.side_effect = [
            Mock(choices=[Mock(message=Mock(content=json.dumps(good_response)))]),
            Exception("Analysis failed")
        ]

        with patch('asyncio.sleep', new_callable=AsyncMock):
            results = await ai_analyzer.analyze_case_documents(documents, sample_intake_analysis)
            
            assert len(results) == 2
            assert isinstance(results[0], AnalyzedDocument)
            assert isinstance(results[1], AnalysisError)
            assert "bad_doc.pdf" in results[1].source

    def test_estimate_tokens(self, ai_analyzer):
        """Test token estimation."""
        text = "This is a test string"  # 22 characters
        tokens = ai_analyzer._estimate_tokens(text)
        assert tokens == 5  # 22 // 4 = 5

    def test_truncate_content_if_needed_no_truncation(self, ai_analyzer):
        """Test content truncation when no truncation is needed."""
        short_content = "Short content"
        result = ai_analyzer._truncate_content_if_needed(short_content, max_tokens=1000)
        assert result == short_content

    def test_truncate_content_if_needed_with_truncation(self, ai_analyzer):
        """Test content truncation when truncation is needed."""
        # Create content that exceeds 10 tokens (40 characters)
        long_content = "A" * 100  # 100 characters = ~25 tokens
        result = ai_analyzer._truncate_content_if_needed(long_content, max_tokens=10)
        
        assert len(result) < len(long_content)
        assert "[... CONTENT TRUNCATED FOR SIZE ...]" in result
        assert result.startswith("A")
        assert result.endswith("A")

    @pytest.mark.asyncio
    async def test_analyze_single_document_success(self, ai_analyzer, sample_case_document, sample_intake_analysis, mock_openai_client):
        """Test successful single document analysis."""
        analyzed_response = {
            "filename": "contract.pdf",
            "document_type": "Contract",
            "inferred_title": "Construction Contract",
            "summary": "Contract summary",
            "key_information": "Key contract info",
            "relevance_to_case": "Primary evidence"
        }
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(analyzed_response)

        result = await ai_analyzer._analyze_single_document(sample_case_document, sample_intake_analysis)
        
        assert isinstance(result, AnalyzedDocument)
        assert result.filename == "contract.pdf"
        assert result.document_type == "Contract"

    @pytest.mark.asyncio
    async def test_analyze_single_document_model_selection(self, ai_analyzer, sample_case_document, sample_intake_analysis, mock_openai_client):
        """Test model selection based on document size."""
        # Create a large document that should trigger gpt-4o-mini
        large_document = ProcessedDocument(
            file_name="large_doc.pdf",
            content="A" * 100000,  # Large content to trigger model switch
            file_type=FileType.PDF,
            document_type=DocumentType.CASE_DOCUMENT
        )
        
        analyzed_response = {
            "filename": "large_doc.pdf",
            "document_type": "Document",
            "inferred_title": "Large Document",
            "summary": "Large document summary",
            "key_information": "Large document info",
            "relevance_to_case": "Relevant"
        }
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(analyzed_response)

        result = await ai_analyzer._analyze_single_document(large_document, sample_intake_analysis)
        
        assert isinstance(result, AnalyzedDocument)
        # Verify that the model was called (we can't easily verify which model without more complex mocking)
        mock_openai_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_single_document_error(self, ai_analyzer, sample_case_document, sample_intake_analysis, mock_openai_client):
        """Test single document analysis error handling."""
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")

        result = await ai_analyzer._analyze_single_document(sample_case_document, sample_intake_analysis)
        
        assert isinstance(result, AnalysisError)
        assert "contract.pdf" in result.source
        assert "Failed to analyze document" in result.error_message

    @pytest.mark.asyncio
    async def test_perform_final_assessment_success(self, ai_analyzer, sample_case_analysis, mock_openai_client):
        """Test successful final assessment."""
        final_assessment_response = {
            "legal_assessment": {
                "case_type": "Contractor Dispute",
                "claim_viability": "Strong",
                "overall_evidence_strength": "Strong",
                "potential_challenges": "Some challenges exist",
                "recommended_actions": "Take these actions",
                "demand_letter_appropriate": True,
                "urgency_assessment": "Medium"
            },
            "demand_letter_evaluation": {
                "is_appropriate": True,
                "reasoning": "Good case for demand letter",
                "potential_outcomes": ["Settlement", "Litigation"],
                "relevant_statutes": ["Statute 1", "Statute 2"]
            }
        }
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = json.dumps(final_assessment_response)

        with patch('backend_logic.ai_analyzer.safe_model_validate') as mock_validate:
            # Mock successful validation
            mock_validate.side_effect = [
                LegalAssessment(**final_assessment_response["legal_assessment"]),
                DemandLetterEvaluation(**final_assessment_response["demand_letter_evaluation"])
            ]
            
            result = await ai_analyzer.perform_final_assessment(sample_case_analysis)
            
            assert isinstance(result, CaseAnalysisResult)
            assert result.legal_assessment is not None
            assert result.demand_letter_evaluation is not None
            assert result.legal_assessment.case_type == "Contractor Dispute"
            assert result.demand_letter_evaluation.is_appropriate is True

    @pytest.mark.asyncio
    async def test_perform_final_assessment_missing_inputs(self, ai_analyzer):
        """Test final assessment with missing inputs."""
        empty_analysis = CaseAnalysisResult()  # No intake_analysis or analyzed_documents
        
        with patch('backend_logic.ai_analyzer.create_fallback_legal_assessment') as mock_legal_fallback:
            with patch('backend_logic.ai_analyzer.create_fallback_demand_letter_evaluation') as mock_demand_fallback:
                mock_legal_fallback.return_value = {
                    "case_type": "Unknown",
                    "claim_viability": "Moderate",
                    "overall_evidence_strength": "Moderate",
                    "potential_challenges": "Unable to assess",
                    "recommended_actions": "Gather more information",
                    "demand_letter_appropriate": False,
                    "urgency_assessment": "Low"
                }
                mock_demand_fallback.return_value = {
                    "is_appropriate": False,
                    "reasoning": "",
                    "potential_outcomes": [],
                    "relevant_statutes": []
                }
                
                result = await ai_analyzer.perform_final_assessment(empty_analysis)
                
                assert isinstance(result, CaseAnalysisResult)
                assert result.legal_assessment is not None
                assert result.demand_letter_evaluation is not None
                assert len(result.errors) == 1
                assert "Cannot perform final assessment" in result.errors[0].error_message

    @pytest.mark.asyncio
    async def test_perform_final_assessment_api_error(self, ai_analyzer, sample_case_analysis, mock_openai_client):
        """Test final assessment with API error."""
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")
        
        with patch('backend_logic.ai_analyzer.create_fallback_legal_assessment') as mock_legal_fallback:
            with patch('backend_logic.ai_analyzer.create_fallback_demand_letter_evaluation') as mock_demand_fallback:
                mock_legal_fallback.return_value = {"case_type": "Unknown"}
                mock_demand_fallback.return_value = {"is_appropriate": False}
                
                result = await ai_analyzer.perform_final_assessment(sample_case_analysis)
                
                assert isinstance(result, CaseAnalysisResult)
                assert result.legal_assessment is not None
                assert result.demand_letter_evaluation is not None
                assert len(result.errors) >= 1


class TestAIAnalyzerIntegration:
    """Integration tests for AIAnalyzer workflow."""

    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client for integration testing."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '{"test": "response"}'
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    @pytest.fixture
    def mock_doc_processor(self):
        """Mock DocumentProcessor for integration testing."""
        return Mock(spec=DocumentProcessor)

    @pytest.mark.asyncio
    async def test_full_analysis_workflow(self, mock_openai_client, mock_doc_processor):
        """Test complete analysis workflow from intake to final assessment."""
        analyzer = AIAnalyzer(mock_openai_client, mock_doc_processor)
        
        # Mock intake document
        intake_doc = ProcessedDocument(
            file_name="intake.pdf",
            content="Client: Erik Devlin, Case: Contractor Dispute",
            file_type=FileType.PDF,
            document_type=DocumentType.INTAKE_FORM
        )
        
        # Mock case documents
        case_docs = [
            ProcessedDocument(
                file_name="contract.pdf",
                content="Construction contract details",
                file_type=FileType.PDF,
                document_type=DocumentType.CASE_DOCUMENT
            )
        ]
        
        # Mock intake analysis response
        intake_response = {
            "client_name": "Erik Devlin",
            "case_type": "Contractor Dispute",
            "case_summary": "Construction dispute",
            "urgency_level": "Medium",
            "client_priorities": ["Completion", "Damages"],
            "key_facts": ["Incomplete work"],
            "legal_claims": ["Breach of contract"]
        }
        
        # Mock case document analysis response
        doc_response = {
            "filename": "contract.pdf",
            "document_type": "Contract",
            "inferred_title": "Construction Contract",
            "summary": "Main contract document",
            "key_information": "Payment terms and scope",
            "relevance_to_case": "Primary evidence"
        }
        
        # Mock final assessment response
        final_response = {
            "legal_assessment": {
                "case_type": "Contractor Dispute",
                "claim_viability": "Strong",
                "overall_evidence_strength": "Strong",
                "potential_challenges": "Limited challenges",
                "recommended_actions": "Proceed with demand letter",
                "demand_letter_appropriate": True,
                "urgency_assessment": "Medium"
            },
            "demand_letter_evaluation": {
                "is_appropriate": True,
                "reasoning": "Strong case",
                "potential_outcomes": ["Settlement"],
                "relevant_statutes": ["Construction Law"]
            }
        }
        
        # Set up mock responses in order
        mock_openai_client.chat.completions.create.side_effect = [
            Mock(choices=[Mock(message=Mock(content=json.dumps(intake_response)))]),
            Mock(choices=[Mock(message=Mock(content=json.dumps(doc_response)))]),
            Mock(choices=[Mock(message=Mock(content=json.dumps(final_response)))])
        ]
        
        with patch('backend_logic.ai_analyzer.preprocess_ai_output', side_effect=[intake_response, doc_response]):
            with patch('backend_logic.ai_analyzer.safe_model_validate') as mock_validate:
                with patch('asyncio.sleep', new_callable=AsyncMock):
                    # Mock validation responses
                    mock_validate.side_effect = [
                        LegalAssessment(**final_response["legal_assessment"]),
                        DemandLetterEvaluation(**final_response["demand_letter_evaluation"])
                    ]
                    
                    # Step 1: Analyze intake
                    analysis = await analyzer.analyze_intake(intake_doc)
                    assert analysis.intake_analysis is not None
                    assert analysis.intake_analysis.client_name == "Erik Devlin"
                    
                    # Step 2: Analyze case documents
                    doc_results = await analyzer.analyze_case_documents(case_docs, analysis.intake_analysis)
                    assert len(doc_results) == 1
                    assert isinstance(doc_results[0], AnalyzedDocument)
                    
                    # Add documents to analysis
                    analysis.analyzed_documents = doc_results
                    
                    # Step 3: Final assessment
                    final_analysis = await analyzer.perform_final_assessment(analysis)
                    assert final_analysis.legal_assessment is not None
                    assert final_analysis.demand_letter_evaluation is not None
                    assert final_analysis.legal_assessment.case_type == "Contractor Dispute"

    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self, mock_openai_client, mock_doc_processor):
        """Test error recovery in analysis workflow."""
        analyzer = AIAnalyzer(mock_openai_client, mock_doc_processor)
        
        # Mock documents
        intake_doc = ProcessedDocument(
            file_name="intake.pdf",
            content="Client: Test Client",
            file_type=FileType.PDF,
            document_type=DocumentType.INTAKE_FORM
        )
        
        # Mock failing API calls
        mock_openai_client.chat.completions.create.side_effect = [
            Exception("API Error"),  # Intake fails
            Exception("API Error"),  # Document analysis fails
            Exception("API Error")   # Final assessment fails
        ]
        
        with patch('backend_logic.ai_analyzer.create_fallback_legal_assessment') as mock_legal_fallback:
            with patch('backend_logic.ai_analyzer.create_fallback_demand_letter_evaluation') as mock_demand_fallback:
                mock_legal_fallback.return_value = {"case_type": "Unknown"}
                mock_demand_fallback.return_value = {"is_appropriate": False}
                
                # All steps should handle errors gracefully
                analysis = await analyzer.analyze_intake(intake_doc)
                assert len(analysis.errors) == 1
                
                doc_results = await analyzer.analyze_case_documents([], EnhancedIntakeAnalysis())
                assert len(doc_results) == 0
                
                final_analysis = await analyzer.perform_final_assessment(analysis)
                assert final_analysis.legal_assessment is not None  # Fallback provided
                assert len(final_analysis.errors) >= 1