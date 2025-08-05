from pydantic import BaseModel, Field, field_validator, validator, model_validator
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
    AUDIO = "audio"
    VIDEO = "video"
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

class AIAnalysisError(Exception):
    """Custom exception for AI analysis errors."""
    pass

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

    @field_validator('key_facts', 'client_priorities', 'desired_outcomes', 'legal_claims', mode='before')
    @classmethod
    def ensure_list_of_strings(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            stripped_v = v.strip()
            if not stripped_v:
                return []
            # Use regex to split by comma or semicolon, handling whitespace
            import re
            items = [item.strip() for item in re.split(r'\s*[,;]\s*', stripped_v) if item.strip()]
            # If splitting results in an empty list but the original string was not empty,
            # it means no delimiters were found, so treat it as a single item.
            return items if items else [stripped_v]
        if isinstance(v, list):
            # Ensure all list items are strings and strip whitespace
            return [str(item).strip() for item in v if str(item).strip()]
        # For other types, convert to string and wrap in list if not empty
        return [str(v)] if v else []

    @field_validator('financial_impact', mode='before')
    @classmethod
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

    @model_validator(mode='before')
    @classmethod
    def normalize_ai_output(cls, data: Any) -> Any:
        """Normalize AI output to handle common validation issues."""
        if not isinstance(data, dict):
            return data
            
        # Create a copy to avoid modifying the original
        normalized = data.copy()
        
        # Map variant enum values for overall_evidence_strength
        if 'overall_evidence_strength' in normalized:
            strength_value = normalized['overall_evidence_strength']
            if isinstance(strength_value, str):
                # Handle common AI variations
                strength_mapping = {
                    'High': 'Strong',
                    'Very Strong': 'Strong',
                    'Very High': 'Strong',
                    'Low': 'Weak',
                    'Very Low': 'Weak',
                    'Medium': 'Moderate',
                    'Average': 'Moderate',
                    'Excellent': 'Conclusive',
                    'Outstanding': 'Conclusive',
                    'Definitive': 'Conclusive'
                }
                normalized['overall_evidence_strength'] = strength_mapping.get(
                    strength_value, strength_value
                )
        
        # Convert string fields to lists when appropriate
        list_conversion_fields = ['potential_challenges', 'recommended_actions']
        for field in list_conversion_fields:
            if field in normalized:
                value = normalized[field]
                if isinstance(value, str) and value.strip():
                    # Convert string to list by splitting on sentences or semicolons
                    if ';' in value:
                        normalized[field] = [item.strip() for item in value.split(';') if item.strip()]
                    elif '.' in value and len(value) > 100:  # Likely multiple sentences
                        sentences = value.split('.')
                        normalized[field] = [f"{sentence.strip()}." for sentence in sentences[:-1] if sentence.strip()]
                    else:
                        normalized[field] = [value.strip()]
                elif not value:  # Handle None, empty string, etc.
                    normalized[field] = []
        
        return normalized

    @field_validator('overall_evidence_strength', mode='before')
    @classmethod
    def validate_evidence_strength(cls, v):
        """Validate and normalize evidence strength values."""
        if v is None:
            return None
        if isinstance(v, str):
            # Additional fallback validation in case model_validator doesn't catch everything
            strength_mapping = {
                'High': EvidenceStrength.STRONG,
                'Very Strong': EvidenceStrength.STRONG,
                'Very High': EvidenceStrength.STRONG,
                'Low': EvidenceStrength.WEAK,
                'Very Low': EvidenceStrength.WEAK,
                'Medium': EvidenceStrength.MODERATE,
                'Average': EvidenceStrength.MODERATE,
                'Excellent': EvidenceStrength.CONCLUSIVE,
                'Outstanding': EvidenceStrength.CONCLUSIVE,
                'Definitive': EvidenceStrength.CONCLUSIVE
            }
            if v in strength_mapping:
                return strength_mapping[v]
            # Try to match to existing enum values
            for strength in EvidenceStrength:
                if v.lower() == strength.value.lower():
                    return strength
            # Default fallback
            print(f"VALIDATION WARNING: Unknown evidence strength '{v}', defaulting to 'Moderate'")
            return EvidenceStrength.MODERATE
        return v

    @field_validator('potential_challenges', mode='before')
    @classmethod
    def validate_potential_challenges(cls, v):
        """Ensure potential_challenges is always a list or convertible to one."""
        if v is None:
            return []
        if isinstance(v, str):
            if not v.strip():
                return []
            # Convert string to list of challenge assessments
            if ';' in v:
                challenges = [item.strip() for item in v.split(';') if item.strip()]
            elif '.' in v and len(v) > 100:
                sentences = v.split('.')
                challenges = [f"{sentence.strip()}." for sentence in sentences[:-1] if sentence.strip()]
            else:
                challenges = [v.strip()]
            
            # Convert to ChallengeAssessment objects
            return [
                ChallengeAssessment(
                    category="General",
                    description=challenge,
                    mitigation_strategy="To be determined",
                    confidence_score=0.7
                ) for challenge in challenges
            ]
        if isinstance(v, list):
            # If it's already a list, ensure all items are ChallengeAssessment objects
            normalized_challenges = []
            for item in v:
                if isinstance(item, dict):
                    try:
                        normalized_challenges.append(ChallengeAssessment.model_validate(item))
                    except Exception:
                        # Create a basic ChallengeAssessment if validation fails
                        normalized_challenges.append(
                            ChallengeAssessment(
                                category="General",
                                description=str(item.get('description', item)),
                                mitigation_strategy="To be determined",
                                confidence_score=0.7
                            )
                        )
                elif isinstance(item, str):
                    normalized_challenges.append(
                        ChallengeAssessment(
                            category="General",
                            description=item,
                            mitigation_strategy="To be determined",
                            confidence_score=0.7
                        )
                    )
                else:
                    normalized_challenges.append(item)  # Assume it's already a ChallengeAssessment
            return normalized_challenges
        return v

    @field_validator('recommended_actions', mode='before')
    @classmethod
    def validate_recommended_actions(cls, v):
        """Ensure recommended_actions is always a list."""
        if v is None:
            return []
        if isinstance(v, str):
            if not v.strip():
                return []
            # Convert string to list
            if ';' in v:
                return [item.strip() for item in v.split(';') if item.strip()]
            elif '.' in v and len(v) > 100:
                sentences = v.split('.')
                return [f"{sentence.strip()}." for sentence in sentences[:-1] if sentence.strip()]
            else:
                return [v.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return [str(v)] if v else []

class DemandLetterEvaluation(BaseModel):
    """Evaluation of whether a demand letter should be sent."""
    is_appropriate: Optional[bool] = Field(None, description="Indicates if a demand letter is recommended.")
    reasoning: Optional[str] = Field(None, description="The reasoning behind the recommendation.")
    potential_outcomes: List[str] = Field(default_factory=list, description="Potential outcomes of sending a demand letter.")
    relevant_statutes: List[str] = Field(default_factory=list, description="A list of relevant statutes to cite in the demand letter.")

# --- Media Processing Models ---

class TranscriptedMedia(BaseModel):
    """Represents a transcribed audio file."""
    file_name: str
    transcript: str
    duration: Optional[float] = None  # Duration in seconds
    language: Optional[str] = None
    confidence: Optional[float] = None
    metadata: FileMetadata = Field(default_factory=FileMetadata)

class VideoInsight(BaseModel):
    """Represents insights extracted from video analysis."""
    file_name: str
    insights: Dict[str, Any]
    transcript: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    text_annotations: List[str] = Field(default_factory=list)
    duration: Optional[float] = None  # Duration in seconds
    confidence: Optional[float] = None
    metadata: FileMetadata = Field(default_factory=FileMetadata)
    
    # Video preservation fields for handling token limit scenarios
    insights_gcs_uri: Optional[str] = Field(None, description="GCS path for full serialized video insights")
    insights_summary: Optional[str] = Field(None, description="Truncated summary for use in prompts")
    original_insights: Optional[Dict[str, Any]] = Field(None, exclude=True, description="Full insights held temporarily in memory")

class MediaProcessingError(BaseModel):
    """Data model for capturing errors during media processing."""
    source: str = Field(..., description="The source of the error (e.g., 'AudioProcessor', 'VideoProcessor').")
    file_name: str = Field(..., description="The name of the file that caused the error.")
    error_message: str = Field(..., description="The detailed error message.")
    error_type: str = Field(..., description="The type of error (e.g., 'TranscriptionError', 'UploadError').")

class CaseAnalysisResult(BaseModel):
    """Combined data model for enhanced intake and case analysis, including error tracking."""
    intake_analysis: Optional[EnhancedIntakeAnalysis] = None
    analyzed_documents: List[AnalyzedDocument] = Field(default_factory=list)
    transcripted_media: List[TranscriptedMedia] = Field(default_factory=list, description="A list of transcribed audio files.")
    video_insights: List[VideoInsight] = Field(default_factory=list, description="A list of video analysis insights.")
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
    media_summary: str = Field(default="", description="Summary of media analysis findings from audio and video files")
    video_analysis_appendix: str = Field(default="", description="Detailed video analysis appendix explaining significance of video content to the case")
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
    errors: List[AnalysisError] = [] # Directly initialize as an empty list

class SavedDocument(BaseModel):
    tmp_path: str
    filename: str