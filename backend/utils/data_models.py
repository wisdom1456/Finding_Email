from pydantic import BaseModel, Field, field_validator, validator
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from .validators import stringify_dict

# --- Enums for Type Safety and Consistency ---

class FileType(str, Enum):
    """Enum for supported file types."""
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    EML = "eml"
    TXT = "txt"
    IMAGE = "image"
    UNSUPPORTED = "unsupported"

class DocumentType(str, Enum):
    """Enum for document categories."""
    INTAKE_FORM = "intake_form"
    CASE_DOCUMENT = "case_document"
    UNKNOWN = "unknown"

class CaseType(str, Enum):
    """Enum for legal case types."""
    LANDLORD_TENANT = "Landlord/Tenant Dispute"
    CONTRACT = "Contract Dispute"
    PERSONAL_INJURY = "Personal Injury"
    FAMILY_LAW = "Family Law"
    OTHER = "Other"

class UrgencyLevel(str, Enum):
    """Enum for case urgency levels."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

class EvidenceStrength(str, Enum):
    """Enum for evidence strength assessment."""
    WEAK = "Weak"
    MODERATE = "Moderate"
    STRONG = "Strong"
    CONCLUSIVE = "Conclusive"

# --- Core Data Processing Models ---

class FileMetadata(BaseModel):
    """Represents metadata about a file."""
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None

class ProcessedDocument(BaseModel):
    """Represents a document that has been processed and is ready for AI analysis."""
    file_name: str
    content: str
    file_type: FileType
    document_type: DocumentType = DocumentType.UNKNOWN
    metadata: FileMetadata = Field(default_factory=FileMetadata)

class AnalysisError(BaseModel):
    """Data model for capturing errors during AI analysis."""
    source: str = Field(..., description="The source of the error (e.g., 'IntakeAnalysis', 'doc_id:123').")
    error_message: str = Field(..., description="The detailed error message.")
    details: Optional[Any] = Field(None, description="Additional error details, can be a dict or a list of validation errors.")

# --- Resilient Pydantic Models for AI Analysis ---

class EnhancedIntakeAnalysis(BaseModel):
    """Data model for the enhanced, structured analysis of an intake form."""
    client_name: Optional[str] = Field(None, description="The client's full name.")
    attorney_name: Optional[str] = Field(None, description="The attorney's full name.")
    case_summary: Optional[str] = Field(None, description="A brief summary of the case.")
    case_type: Optional[str] = Field(None, description="The type of legal case.")
    urgency_level: Optional[str] = Field(None, description="The urgency level of the case.")
    client_priorities: List[str] = Field(default_factory=list, description="A list of the client's stated priorities.")
    desired_outcomes: List[str] = Field(default_factory=list, description="A list of the client's desired outcomes.")
    key_facts: Union[List[str], str] = Field(default_factory=list, description="A list of key facts from the intake form.")
    parties_involved: List[Dict[str, str]] = Field(default_factory=list, description="A list of parties involved and their roles.")
    financial_impact: Union[Optional[str], Dict[str, Any]] = Field(None, description="The estimated financial impact of the case.")
    legal_claims: List[str] = Field(default_factory=list, description="Potential legal claims identified from the intake.")

    @validator('key_facts', 'client_priorities', 'desired_outcomes', 'legal_claims', pre=True)
    def ensure_list_of_strings(cls, v):
        if isinstance(v, str):
            # Handles simple comma-separated strings or a single string
            return [item.strip() for item in v.split(',') if item.strip()] if ',' in v else [v]
        if v is None:
            return []
        return v

    @validator('financial_impact', pre=True)
    def clean_financial_impact(cls, v):
        return stringify_dict(v)


class AnalyzedDocument(BaseModel):
    """Represents a single document's AI-driven analysis."""
    filename: str
    document_type: str  # e.g., 'Contract', 'Email', 'Image'
    inferred_title: str
    summary: str
    key_information: str
    relevance_to_case: str

class ChallengeAssessment(BaseModel):
    """Represents a single potential legal challenge."""
    category: Optional[str] = Field(None, description="The category of the challenge.")
    description: Optional[str] = Field(None, description="A detailed description of the challenge.")
    mitigation_strategy: Optional[str] = Field(None, description="A potential strategy to mitigate the challenge.")
    confidence_score: Optional[float] = Field(None, description="A score from 0.0 to 1.0 indicating the likelihood of this challenge impacting the case.")

class LegalAssessment(BaseModel):
    """Overall legal assessment combining insights from all documents."""
    case_type: Optional[str] = Field(None, description="The overall determined case type.")
    claim_viability: Optional[str] = Field(None, description="An assessment of the viability of the legal claim.")
    overall_evidence_strength: Optional[EvidenceStrength] = Field(None, description="The combined strength of all evidence.")
    potential_challenges: Union[List[ChallengeAssessment], str] = Field(default_factory=list, description="A list of all identified potential challenges.")
    recommended_actions: Union[List[str], str] = Field(default_factory=list, description="A list of recommended next steps for the case.")
    demand_letter_appropriate: Optional[bool] = Field(None, description="Whether sending a demand letter is appropriate.")
    urgency_assessment: Optional[str] = Field(None, description="The overall assessment of the case's urgency.")

class DemandLetterEvaluation(BaseModel):
    """Evaluation of whether a demand letter should be sent."""
    is_appropriate: Optional[bool] = Field(None, description="Indicates if a demand letter is recommended.")
    reasoning: Optional[str] = Field(None, description="The reasoning behind the recommendation.")
    potential_outcomes: List[str] = Field(default_factory=list, description="Potential outcomes of sending a demand letter.")
    relevant_statutes: List[str] = Field(default_factory=list, description="A list of relevant statutes to cite in the demand letter.")

class CaseAnalysisResult(BaseModel):
    """Combined data model for enhanced intake and case analysis, including error tracking."""
    intake_analysis: Optional[EnhancedIntakeAnalysis] = None
    analyzed_documents: List[AnalyzedDocument] = Field(default_factory=list)
    legal_assessment: Optional[LegalAssessment] = None
    demand_letter_evaluation: Optional[DemandLetterEvaluation] = None
    errors: List[AnalysisError] = Field(default_factory=list, description="A list of errors encountered during analysis.")

# --- Email Generation Models ---

class GeneratedLetter(BaseModel):
    """
    Structured model for the final separated content for the Jinja2 template.
    This holds the professional, well-formatted legal letter content.
    """
    executive_summary: str = Field(..., description="Executive summary of the case and recommendations")
    background_summary: str = Field(..., description="Background context from intake analysis")
    analysis_and_position: str = Field(..., description="Legal analysis and position in flowing prose")
    strengths: str = Field(..., description="Strengths of the case in sophisticated legal prose")
    challenges: str = Field(..., description="Potential challenges and risks in legal prose")
    recommendations: str = Field(..., description="Numbered list of recommendations as HTML")
    next_steps: str = Field(..., description="Numbered list of next steps as HTML")
    closing_paragraph: str = Field(..., description="Professional closing paragraph for the findings letter")

class FindingsHeader(BaseModel):
    """Structured data for the email header."""
    date: Optional[str] = None
    client_name: Optional[str] = None
    client_address: Optional[str] = None
    case_reference: Optional[str] = None

class FindingsFooter(BaseModel):
    """Structured data for the email footer."""
    attorney_name: Optional[str] = None
    firm_name: Optional[str] = None
    firm_address: Optional[str] = None
    contact_info: Optional[str] = None

class EnhancedFindingsLetter(BaseModel):
    """Represents a professionally structured findings letter with all required sections."""
    header: FindingsHeader = Field(default_factory=FindingsHeader)
    reviewed_documents: List[str] = Field(default_factory=list, description="A list of the document titles that were reviewed.")
    background_summary: Optional[str] = Field(None, description="Context from intake analysis.")
    review_summary: Optional[str] = Field(None, description="Legal analysis and case facts.")
    assessment_challenges: List[ChallengeAssessment] = Field(default_factory=list)
    next_steps_recommendations: List[str] = Field(default_factory=list)
    demand_letter_section: Optional[DemandLetterEvaluation] = None
    footer: FindingsFooter = Field(default_factory=FindingsFooter)

class DownloadLink(BaseModel):
    """Represents a download link for a generated file."""
    file_name: str
    url: str

class QualityScore(BaseModel):
    """Data model for the quality score of the findings letter."""
    overall_score: float
    professional_tone_score: float
    completeness_score: float
    clarity_score: float
    case_specificity_score: float

class EmailResponse(BaseModel):
    """Data model for the email generation response."""
    findings_letter: Optional[EnhancedFindingsLetter] = None
    download_links: List[DownloadLink] = Field(default_factory=list)
    case_analysis_text: Optional[str] = Field(None, description="The formatted text of the case analysis document.")
    quality_score: Optional[QualityScore] = None

class CaseResults(BaseModel):
    """Top-level model for returning the complete analysis results."""
    analysis: CaseAnalysisResult = Field(default_factory=CaseAnalysisResult)
    email: Optional[EmailResponse] = None
    generated_letter: Optional[GeneratedLetter] = None
    errors: List[AnalysisError] = Field(default_factory=list)

    @field_validator('analysis', 'email', 'generated_letter', 'errors', mode='before')
    def set_default(cls, v):
        return v or {}

class SavedDocument(BaseModel):
    tmp_path: str
    filename: str