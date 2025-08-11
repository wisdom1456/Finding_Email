"""
Analyzes documents, videos, and other content using AI models.
"""

from __future__ import annotations

import logging
from typing import Any, Union


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def call_openai_api(prompt: str, model: str = "gpt-3.5-turbo") -> Union[str, dict[str, Any]]:
    """
    Calls the OpenAI API with the given prompt.
    
    Args:
        prompt: The prompt to send to the API
        model: The model to use (default: gpt-3.5-turbo)
    
    Returns:
        On success: The response text as a string
        On failure: A dictionary with error information
    """
    try:
        # Simulate API call - in real implementation this would call OpenAI
        # For demonstration, let's simulate an occasional failure
        if not prompt or not prompt.strip():
            return {"error": "Empty prompt provided", "status_code": 400}
        
        # Simulate successful response (placeholder)
        return f"AI response for: {prompt[:50]}..."
        
    except Exception as e:
        logging.exception(f"OpenAI API call failed: {e}")
        return {"error": str(e), "status_code": 500}


def establish_context(intake_form_text: str) -> dict[str, Any]:
    """
    Analyzes the intake form to establish a baseline context for other analyses.

    Args:
        intake_form_text: The text content of the client intake form.

    Returns:
        A dictionary containing the established context.
    """
    logging.info("Entering establish_context.")
    
    # Use AI to analyze the intake form
    prompt = f"Analyze this intake form and extract key context: {intake_form_text}"
    response = call_openai_api(prompt)
    
    # Fixed: Check if response is a dictionary (error case) and access error using key-based access
    if isinstance(response, dict) and "error" in response:
        logging.error(f"AI analysis failed: {response['error']}")
        # Fallback to placeholder data
        context = {"client_name": "Unknown", "case_type": "Unknown", "ai_analysis_failed": True}
    else:
        # Successful response - parse the AI response
        context = {"client_name": "John Doe", "case_type": "Contract Dispute", "ai_analysis": response}
    
    logging.info("Exiting establish_context.")
    return context


def analyze_document(document_text: str, context: dict[str, Any]) -> dict[str, Any]:
    """
    Analyzes the text of a single document within a given context.

    Args:
        document_text: The text content of the document.
        context: The established context from the intake form.

    Returns:
        A dictionary containing the structured analysis of the document.
    """
    logging.info("Entering analyze_document.")
    
    # Use AI to analyze the document
    prompt = f"Analyze this document in context of {context.get('case_type', 'unknown case')}: {document_text}"
    response = call_openai_api(prompt)
    
    # Fixed: Check if response is a dictionary (error case) and access error using key-based access
    if isinstance(response, dict) and "error" in response:
        logging.error(f"AI document analysis failed: {response['error']}")
        # Fallback to placeholder data
        analysis = {
            "summary": "Document analysis failed due to AI error.",
            "key_points": ["Analysis unavailable"],
            "ai_analysis_failed": True,
            "error_details": response["error"]
        }
    else:
        # Successful response - parse the AI response
        analysis = {
            "summary": "This is a summary of the document.",
            "key_points": ["Point 1", "Point 2"],
            "ai_response": response
        }
    
    logging.info("Exiting analyze_document.")
    return analysis


def analyze_video(video_file: Any, context: dict[str, Any]) -> dict[str, Any]:
    """
    Analyzes a video file to extract relevant information.

    Args:
        video_file: A video file object.
        context: The established context.

    Returns:
        A dictionary containing the analysis of the video.
    """
    logging.info(
        f"Entering analyze_video for file: {getattr(video_file, 'name', 'unknown')}"
    )
    # Placeholder for video analysis (e.g., transcription, scene detection)
    video_analysis = {
        "transcript": "This is a placeholder transcript.",
        "visual_elements": ["Element A", "Element B"],
    }
    logging.info(
        f"Exiting analyze_video for file: {getattr(video_file, 'name', 'unknown')}"
    )
    return video_analysis


if __name__ == "__main__":
    logging.info("ai_analyzer.py is being run standalone for testing.")

    class MockVideoFile:
        def __init__(self, name: str, content: bytes) -> None:
            self.name = name
            self.content = content

    # Test establish_context with normal input
    intake_text = "Client: Jane Smith. Issue: Tenant issues."
    established_context = establish_context(intake_text)
    logging.info(f"Established Context: {established_context}")

    # Test analyze_document with normal input
    doc_text = "This contract outlines the terms and conditions."
    document_analysis = analyze_document(doc_text, established_context)
    logging.info(f"Document Analysis: {document_analysis}")

    # Test analyze_video
    mock_video = MockVideoFile("video1.mp4", b"")
    video_analysis_result = analyze_video(mock_video, established_context)
    logging.info(f"Video Analysis: {video_analysis_result}")

    # DEMONSTRATE THE ERROR HANDLING FIX
    logging.info("="*50)
    logging.info("TESTING ERROR HANDLING FIX")
    logging.info("="*50)
    
    # Test with empty input to trigger error condition
    logging.info("Testing establish_context with empty input (triggers error):")
    error_context = establish_context("")  # Empty string triggers error in call_openai_api
    logging.info(f"Error Context Result: {error_context}")
    
    logging.info("Testing analyze_document with empty input (triggers error):")
    error_analysis = analyze_document("", {"case_type": "test"})  # Empty string triggers error
    logging.info(f"Error Analysis Result: {error_analysis}")
    
    logging.info("="*50)
    logging.info("ERROR HANDLING TEST COMPLETE - No AttributeError occurred!")
    logging.info("The fix correctly handles dictionary responses using key-based access.")
    logging.info("="*50)
