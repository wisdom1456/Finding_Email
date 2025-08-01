import sys
import os
import tempfile
import shutil
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from typing import List
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from backend.utils.config import settings
from backend.services.document_processor import DocumentProcessor
from backend.services.ai_analyzer import AIAnalyzer
from backend.services.email_generator import EmailGenerator
from backend.services.task_manager import TaskManager
from backend.services.async_processor import process_documents_async
from backend.utils.data_models import (
    CaseResults,
    AnalysisError,
    DocumentType,
    SavedDocument,
)
from backend.utils.async_models import TaskInitResponse, TaskStatusResponse

# --- App Initialization ---
load_dotenv()
app = FastAPI(title="Legal Document Analysis Pipeline")
task_manager = TaskManager()

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

@app.post(
    "/api/v1/analysis/start-analysis",
    response_model=TaskInitResponse,
    tags=["Asynchronous Analysis"],
    summary="Start an asynchronous document analysis task",
)
async def start_analysis(
    background_tasks: BackgroundTasks,
    intake_form: UploadFile = File(...),
    case_documents: List[UploadFile] = File(...),
    client: OpenAI = Depends(get_openai_client),
    doc_processor: DocumentProcessor = Depends(get_doc_processor),
):
    """
    Initializes a background task for document analysis and immediately returns a task ID.
    """
    task_id = task_manager.create_task()
    temp_dir = tempfile.mkdtemp()
    
    saved_documents = []
    all_files = [intake_form] + case_documents
    
    for upload_file in all_files:
        try:
            temp_file_path = os.path.join(temp_dir, upload_file.filename)
            with open(temp_file_path, "wb") as buffer:
                buffer.write(await upload_file.read())
            
            saved_doc = SavedDocument(tmp_path=temp_file_path, filename=upload_file.filename)
            document_type = DocumentType.INTAKE_FORM if upload_file == intake_form else DocumentType.CASE_DOCUMENT
            # Logic to pass document_type might need adjustment based on final async_processor implementation
            saved_documents.append(saved_doc)
        finally:
            await upload_file.close()

    background_tasks.add_task(
        process_documents_async,
        task_id=task_id,
        saved_documents=saved_documents,
        client=client,
        doc_processor=doc_processor,
        task_manager=task_manager,
        temp_dir_path=temp_dir,
        intake_filename=intake_form.filename
    )
    return TaskInitResponse(task_id=task_id)


@app.get(
    "/api/v1/analysis/status/{task_id}",
    response_model=TaskStatusResponse,
    tags=["Asynchronous Analysis"],
    summary="Get the status of an analysis task",
)
async def get_analysis_status(task_id: str):
    """
    Retrieves the current status of a background analysis task.
    """
    status = task_manager.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@app.get(
    "/api/v1/analysis/results/{task_id}",
    response_model=CaseResults,
    tags=["Asynchronous Analysis"],
    summary="Get the results of a completed analysis task",
)
async def get_analysis_results(task_id: str):
    """
    Retrieves the results of a completed analysis task.
    
    If the task is still processing or has failed, this will return an error.
    """
    status = task_manager.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    if status.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Task is not yet complete. Current status: {status.status}",
        )
    result = task_manager.get_task_result(task_id)
    if not result:
        raise HTTPException(
            status_code=404, detail="Result not found for completed task"
        )
    return result

@app.post(
    "/api/v1/analysis/full-pipeline",
    response_model=CaseResults,
    tags=["Analysis"],
    deprecated=True,
)
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