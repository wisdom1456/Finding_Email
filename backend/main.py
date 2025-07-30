from fastapi import FastAPI, UploadFile, File, Form, Depends
from typing import List
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from utils.config import settings
from services.document_processor import DocumentProcessor
from services.ai_analyzer import AIAnalyzer
from services.email_generator import EmailGenerator
from utils.data_models import IntakeAnalysis, CaseAnalysis, CombinedAnalysis, EmailResponse

load_dotenv()

app = FastAPI()

# Initialize OpenAI client
client = OpenAI(api_key=settings.openai_api_key)

# CORS configuration
if settings.cors_origins:
    origins = settings.cors_origins.split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

doc_processor = DocumentProcessor()
ai_analyzer = AIAnalyzer(client=client)
email_generator = EmailGenerator(client=client)

@app.post("/api/analyze-intake", response_model=IntakeAnalysis)
async def analyze_intake_form(intake_form: UploadFile = File(...)):
    return await ai_analyzer.analyze_intake(intake_form)

@app.post("/api/analyze-case-documents", response_model=List[CaseAnalysis])
async def analyze_case_documents(case_documents: List[UploadFile] = File(...)):
    processed_docs = await doc_processor.process_documents(case_documents)
    return await ai_analyzer.analyze_case_documents(processed_docs)

@app.post("/api/generate-findings-letter", response_model=EmailResponse)
def generate_findings_letter(analysis: CombinedAnalysis):
    return email_generator.generate_findings_letter(analysis)