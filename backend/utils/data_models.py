from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class FileType(str, Enum):
    """
    Enum for supported file types.
    """
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    EML = "eml"
    TXT = "txt"

class DocumentType(str, Enum):
    """
    Enum for document categories.
    """
    INTAKE_FORM = "intake_form"
    CASE_DOCUMENT = "case_document"

class FileMetadata(BaseModel):
    """
    Represents metadata about a file.
    """
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None

class ProcessedDocument(BaseModel):
    """
    Represents a document that has been processed and is ready for AI analysis.
    """
    file_name: str
    content: str
    file_type: FileType
    document_type: DocumentType
    metadata: FileMetadata = Field(default_factory=FileMetadata)

class ProcessedFile(ProcessedDocument):
    """
    Legacy alias for ProcessedDocument.
    """
    pass

class IntakeAnalysis(BaseModel):
    """
    Data model for the structured analysis of an intake form.
    """
    client_name: Optional[str] = Field(None, description="The client's full name.")
    attorney_name: Optional[str] = Field(None, description="The attorney's full name.")
    case_summary: Optional[str] = Field(None, description="A brief summary of the case.")
    key_facts: List[str] = Field(default_factory=list, description="A list of key facts from the intake form.")

class CaseAnalysis(BaseModel):
    """
    Data model for the structured analysis of a case document.
    """
    document_title: str = Field(..., description="The title of the document.")
    document_type: str = Field(..., description="The type of document (e.g., 'Lease Agreement', 'Email Correspondence').")
    key_entities: List[str] = Field(default_factory=list, description="A list of key entities mentioned in the document.")
    summary: str = Field(..., description="A summary of the document's content.")
    timeline_events: List[Dict[str, str]] = Field(default_factory=list, description="A list of timeline events, each with a date and description.")

class CaseAnalysisRequest(BaseModel):
    """
    Request model for analyzing multiple case documents.
    """
    case_documents: List[ProcessedDocument]

class CombinedAnalysis(BaseModel):
    """
    Combined data model for intake and case analysis.
    """
    intake_analysis: IntakeAnalysis
    case_analyses: List[CaseAnalysis]

class FindingsLetter(BaseModel):
    """
    Data model for the generated findings letter.
    """
    subject: str = Field(..., description="The subject of the findings letter.")
    body: str = Field(..., description="The body content of the findings letter.")
    recipients: List[str] = Field(default_factory=list, description="A list of recipient email addresses.")

class DownloadLink(BaseModel):
    """
    Represents a downloadable file link.
    """
    file_name: str
    url: str

class EmailResponse(BaseModel):
    """
    Data model for the email generation response.
    """
    findings_letter: FindingsLetter
    download_links: List[DownloadLink] = Field(default_factory=list)

class CaseResults(BaseModel):
    """
    Represents the final results of a case analysis, including the analysis itself and the generated email.
    """
    analysis: CaseAnalysis
    email: EmailResponse