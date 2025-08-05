import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Add the project root to the Python path
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

# Assume the app and its components are available for import
import app as streamlit_app
from backend_logic.ai_analyzer import AIAnalyzer
from backend.utils.data_models import (
    ProcessedDocument,
    TranscriptedMedia,
    VideoInsight,
    EnhancedIntakeAnalysis,
    CaseAnalysisResult,
    DocumentType,
    AnalysisError,
    MediaProcessingError,
    LegalAssessment,
    DemandLetterEvaluation,
)


@pytest.fixture
def mock_streamlit_files(tmp_path):
    """Fixture to create mock Streamlit UploadedFile objects."""
    def _create_files(file_specs):
        files = []
        for spec in file_specs:
            file_path = tmp_path / spec["name"]
            file_path.write_bytes(spec.get("content", b"fake data"))
            mock_file = MagicMock()
            mock_file.name = spec["name"]
            mock_file.size = spec.get("size", 1024)
            mock_file.type = spec.get("type", "application/octet-stream")
            mock_file.getvalue.return_value = file_path.read_bytes()
            files.append(mock_file)
        return files
    return _create_files

@pytest.fixture(autouse=True)
def mock_dependencies():
    """Automatically mock all external dependencies for integration tests."""
    with patch('streamlit.container'), \
         patch('streamlit.progress'), \
         patch('streamlit.empty'), \
         patch('streamlit.success'), \
         patch('streamlit.error'), \
         patch('backend_logic.document_processor.DocumentProcessor') as MockDocProcessor, \
         patch('backend_logic.audio_processor.AudioProcessor') as MockAudioProcessor, \
         patch('backend_logic.video_processor.VideoProcessor') as MockVideoProcessor, \
         patch('backend_logic.ai_analyzer.AIAnalyzer') as MockAIAnalyzer, \
         patch('backend_logic.email_generator.EmailGenerator') as MockEmailGenerator:
        
        # Configure mocks to return async mocks for async methods
        MockDocProcessor.return_value.process_documents_from_streamlit = AsyncMock()
        MockAudioProcessor.return_value.process_audio_from_streamlit = AsyncMock()
        MockVideoProcessor.return_value.process_video_from_streamlit = AsyncMock()
        MockAIAnalyzer.return_value.analyze_intake = AsyncMock()
        MockAIAnalyzer.return_value.perform_final_assessment = AsyncMock()
        MockAIAnalyzer.return_value._analyze_single_document = AsyncMock()

        yield {
            "doc_processor": MockDocProcessor,
            "audio_processor": MockAudioProcessor,
            "video_processor": MockVideoProcessor,
            "ai_analyzer": MockAIAnalyzer,
            "email_generator": MockEmailGenerator
        }

@pytest.mark.asyncio
async def test_end_to_end_with_mixed_media(mock_dependencies, mock_streamlit_files):
    """Test the end-to-end workflow with a mix of documents, audio, and video."""
    # Setup mock files
    files = mock_streamlit_files([
        {"name": "intake.pdf", "type": "application/pdf"},
        {"name": "evidence.docx", "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        {"name": "meeting.mp3", "type": "audio/mpeg"},
        {"name": "walkthrough.mp4", "type": "video/mp4"}
    ])
    
    # Mock return values for processors
    mock_dependencies["doc_processor"].return_value.process_documents_from_streamlit.return_value = [
        ProcessedDocument(file_name="intake.pdf", content="intake content", document_type=DocumentType.INTAKE_FORM),
        ProcessedDocument(file_name="evidence.docx", content="evidence content", document_type=DocumentType.CASE_DOCUMENT)
    ]
    mock_dependencies["audio_processor"].return_value.process_audio_from_streamlit.return_value = TranscriptedMedia(file_name="meeting.mp3", transcript="audio transcript")
    mock_dependencies["video_processor"].return_value.process_video_from_streamlit.return_value = VideoInsight(file_name="walkthrough.mp4", insights={"scenes": "video scenes"})
    mock_dependencies["ai_analyzer"].return_value.analyze_intake.return_value = CaseAnalysisResult(intake_analysis=EnhancedIntakeAnalysis(client_name="Test Client"))

    # Mock streamlit session state
    with patch('streamlit.session_state', new_callable=MagicMock) as mock_session:
        mock_session.intake_form = files[0]
        mock_session.case_documents = files[1:]
        
        await streamlit_app.process_case_documents()
        
        assert mock_dependencies["ai_analyzer"].return_value.perform_final_assessment.call_count == 1

@pytest.mark.asyncio
async def test_media_summarization_integration():
    """Test that the AI analyzer correctly integrates media summaries."""
    # This requires a more direct test of AIAnalyzer
    ai_analyzer = AIAnalyzer(client=MagicMock(), doc_processor=MagicMock())
    ai_analyzer._make_openai_request = AsyncMock(return_value={"summary": "This is a media summary."})

    analysis_result = CaseAnalysisResult(
        intake_analysis=EnhancedIntakeAnalysis(client_name="Test Client"),
        transcripted_media=[TranscriptedMedia(file_name="test.mp3", transcript="long audio transcript")],
        video_insights=[VideoInsight(file_name="test.mp4", insights={"data": "long video insight"})]
    )

    prompt = await ai_analyzer._build_final_assessment_prompt(analysis_result)

    assert "This is a media summary." in prompt
    assert "long audio transcript" not in prompt


@pytest.mark.asyncio
async def test_email_generation_with_media_insights(mock_dependencies):
    """Test that the final email includes sections for media analysis."""
    final_analysis = CaseAnalysisResult(
        intake_analysis=EnhancedIntakeAnalysis(client_name="Test Client", case_type="Dispute"),
        legal_assessment=LegalAssessment(claim_viability="Strong"),
        demand_letter_evaluation=DemandLetterEvaluation(is_appropriate=True),
        transcripted_media=[TranscriptedMedia(file_name="audio.mp3", transcript="Audio summary")],
        video_insights=[VideoInsight(file_name="video.mp4", insights="Video summary")]
    )
    mock_dependencies["ai_analyzer"].return_value.perform_final_assessment.return_value = final_analysis
    
    email_generator = mock_dependencies["email_generator"].return_value
    email_generator.generate_email_and_analysis_docs.return_value = {
        "main_letter": "<html><body>Media summary included</body></html>",
        "appendix": "<html><body>Appendix content</body></html>"
    }

    # Simulate the end of processing
    with patch('streamlit.session_state', new_callable=MagicMock):
        await streamlit_app.process_case_documents()
        email_generator.generate_email_and_analysis_docs.assert_called_once()


@pytest.mark.asyncio
async def test_error_recovery_with_media_failure(mock_dependencies, mock_streamlit_files):
    """Test recovery when media fails but document processing succeeds."""
    files = mock_streamlit_files([
        {"name": "intake.pdf", "type": "application/pdf"},
        {"name": "evidence.docx", "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        {"name": "bad_audio.mp3", "type": "audio/mpeg"},
    ])
    
    mock_dependencies["doc_processor"].return_value.process_documents_from_streamlit.return_value = [
        ProcessedDocument(file_name="intake.pdf", content="intake content", document_type=DocumentType.INTAKE_FORM),
        ProcessedDocument(file_name="evidence.docx", content="evidence content", document_type=DocumentType.CASE_DOCUMENT)
    ]
    mock_dependencies["audio_processor"].return_value.process_audio_from_streamlit.return_value = MediaProcessingError(file_name="bad_audio.mp3", error_message="processing failed")
    
    with patch('streamlit.session_state', new_callable=MagicMock) as mock_session:
        mock_session.intake_form = files[0]
        mock_session.case_documents = files[1:]
        
        await streamlit_app.process_case_documents()
        
        final_assessment_call_args = mock_dependencies["ai_analyzer"].return_value.perform_final_assessment.call_args[0][0]
        assert len(final_assessment_call_args.errors) == 1
        assert "processing failed" in final_assessment_call_args.errors[0].error_message


@pytest.mark.asyncio
async def test_large_file_handling_and_timeouts(mock_dependencies, mock_streamlit_files):
    """Test how the system handles large files and potential timeouts."""
    files = mock_streamlit_files([
        {"name": "intake.pdf", "type": "application/pdf"},
        {"name": "large_video.mp4", "type": "video/mp4", "size": 1024*1024*100}, # 100MB
    ])
    
    mock_dependencies["video_processor"].return_value.process_video_from_streamlit.side_effect = asyncio.TimeoutError
    
    with patch('streamlit.session_state', new_callable=MagicMock) as mock_session:
        mock_session.intake_form = files[0]
        mock_session.case_documents = files[1:]
        
        await streamlit_app.process_case_documents()
        
        final_assessment_call_args = mock_dependencies["ai_analyzer"].return_value.perform_final_assessment.call_args[0][0]
        assert any("TimeoutError" in e.error_message for e in final_assessment_call_args.errors)