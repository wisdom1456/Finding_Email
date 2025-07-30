from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Body
from typing import List, Optional
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from backend.utils.config import settings
from backend.services.document_processor import DocumentProcessor
from backend.services.ai_analyzer import AIAnalyzer
from backend.services.email_generator import EmailGenerator
from backend.utils.data_models import (
    CombinedAnalysis,
    CaseResults,
    AnalysisError,
    EnhancedCaseAnalysis,
    DocumentType
)

# --- App Initialization ---
load_dotenv()
app = FastAPI(title="Legal Document Analysis Pipeline")

# --- CORS Configuration ---
if settings.cors_origins:
    origins = settings.cors_origins.split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- Dependency Injection ---
def get_openai_client():
    return OpenAI(api_key=settings.openai_api_key)

def get_doc_processor():
    return DocumentProcessor()

@app.post("/api/v1/analysis/full-pipeline", response_model=CaseResults, tags=["Analysis"])
async def run_full_analysis_pipeline(
    intake_form: UploadFile = File(...),
    case_documents: List[UploadFile] = File(...),
    client: OpenAI = Depends(get_openai_client),
    doc_processor: DocumentProcessor = Depends(get_doc_processor)
):
    """
    Executes the full document analysis pipeline:
    1. Processes intake form and case documents.
    2. Runs AI analysis on the intake form.
    3. Analyzes case documents with intake context.
    4. Performs a final legal assessment.
    5. Generates a findings email.
    Returns a comprehensive CaseResults object including any errors.
    """
    ai_analyzer = AIAnalyzer(client, doc_processor)
    email_generator = EmailGenerator(client)
    
    # 1. Process all documents first
    all_files = [intake_form] + case_documents
    processed_docs = await doc_processor.process_documents(all_files)

    intake_doc = next((doc for doc in processed_docs if doc.document_type == DocumentType.INTAKE_FORM), None)
    other_docs = [doc for doc in processed_docs if doc.document_type == DocumentType.CASE_DOCUMENT]

    if not intake_doc:
        raise HTTPException(status_code=400, detail="An intake form is required but was not found or processed.")

    # 2. Start building the combined analysis
    analysis_result = await ai_analyzer.analyze_intake(intake_doc)
    if not analysis_result.intake_analysis:
        # If intake fails, we can't proceed with context-aware analysis
        analysis_result.errors.append(AnalysisError(source="Pipeline", error_message="Halting due to critical failure in intake analysis."))
        return CaseResults(analysis=analysis_result)

    # 3. Analyze case documents
    case_analysis_results = await ai_analyzer.analyze_case_documents(other_docs, analysis_result.intake_analysis)
    
    for res in case_analysis_results:
        if isinstance(res, EnhancedCaseAnalysis):
            analysis_result.case_analyses.append(res)
        elif isinstance(res, AnalysisError):
            analysis_result.errors.append(res)

    # 4. Perform final assessment
    final_analysis = await ai_analyzer.perform_final_assessment(analysis_result)

    # 5. Generate email and analysis documents
    email_response = email_generator.generate_email_and_analysis_docs(final_analysis)

    return CaseResults(analysis=final_analysis, email=email_response)