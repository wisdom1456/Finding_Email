"""
Pydantic models for data structuring and validation.
"""
from pydantic import BaseModel, Field
from typing import List, Optional

class CaseInfo(BaseModel):
    clientName: str
    attorneyName: str
    caseReference: Optional[str] = None

class UploadedFile(BaseModel):
    filename: str
    content_type: str
    size: int

class ProcessedDocument(BaseModel):
    filename: str
    extracted_content: str
    metadata: dict

class AIAnalysis(BaseModel):
    summary: str
    key_facts: List[str]
    parties: List[str]

class UnifiedCase(BaseModel):
    case_info: CaseInfo
    intake_analysis: AIAnalysis
    documents_analysis: List[AIAnalysis]

class FindingsLetter(BaseModel):
    letter_text: str
    download_eml: str
    download_txt: str