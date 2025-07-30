from fastapi import FastAPI, UploadFile, File, Form
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

from services.document_processor import DocumentProcessor
from services.ai_analyzer import AIAnalyzer
from services.email_generator import EmailGenerator

app = FastAPI()

@app.post("/api/legal-analysis-upload")
async def legal_analysis_upload(
    clientName: Optional[str] = Form(None),
    attorneyName: Optional[str] = Form(None),
    caseReference: Optional[str] = Form(None),
    files: List[UploadFile] = File(...)
):
    doc_processor = DocumentProcessor()
    ai_analyzer = AIAnalyzer()
    email_generator = EmailGenerator()

    case_info = {
        "clientName": clientName,
        "attorneyName": attorneyName,
        "caseReference": caseReference
    }

    processed_docs = await doc_processor.process_files(files)
    analysis_result = await ai_analyzer.analyze_case(processed_docs, case_info)
    email_response = email_generator.create_findings_email(analysis_result)

    return email_response