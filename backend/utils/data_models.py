from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime
from decimal import Decimal
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

class CriminalEvidenceCategory(str, Enum):
    """
    Enum for specific criminal law evidence categories focused on DUI/arrest procedures.
    
    These categories follow the chronological flow of a typical DUI arrest and are designed
    to help legal professionals identify constitutional issues, procedural violations, and
    potential defense strategies in criminal cases.
    """
    DRIVING_PATTERN_REASON_FOR_STOP = "Driving Pattern & Reason for Stop"
    EMERGENCY_LIGHTS_VEHICLE_PULLOVER = "Emergency Lights & Vehicle Pullover"
    INITIAL_ROADSIDE_APPROACH_OBSERVATIONS = "Initial Roadside Approach & Observations"
    PRELIMINARY_QUESTIONING_ADMISSIONS = "Preliminary Questioning & Admissions"
    EXIT_ORDER_PRETEST_OBSERVATIONS = "Exit Order & Pre-Test Observations"
    FIELD_SOBRIETY_TESTS = "Field Sobriety Tests"
    PORTABLE_BREATH_TEST = "Portable Breath Test"
    ARREST_DECISION_HANDCUFFING = "Arrest Decision & Handcuffing"
    MIRANDA_WARNINGS_CUSTODIAL_INTERROGATION = "Miranda Warnings & Custodial Interrogation"
    IMPLIED_CONSENT_CHEMICAL_TEST_REQUEST = "Implied Consent & Chemical Test Request"
    CHEMICAL_TEST_ADMINISTRATION = "Chemical Test Administration"
    TRANSPORT_TO_STATION_JAIL = "Transport to Station/Jail"
    BOOKING_PROCESSING = "Booking & Processing"
    RIGHT_TO_COUNSEL_PHONE_CALLS = "Right to Counsel & Phone Calls"
    POST_BOOKING_OBSERVATION_MEDICAL = "Post-Booking Observation & Medical"
    VEHICLE_TOW_INVENTORY_SEARCH = "Vehicle Tow & Inventory Search"

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

# --- Criminal Evidence Models ---

class TimeRange(BaseModel):
    """
    Represents a time range within video evidence with confidence scoring.
    
    Used to pinpoint specific moments in criminal proceedings that are legally significant.
    Time stamps help attorneys identify exactly when constitutional violations or
    procedural errors occurred during arrests, interrogations, or evidence collection.
    """
    start_time: str = Field(..., description="Start timestamp in format 'MM:SS' or 'HH:MM:SS'")
    end_time: str = Field(..., description="End timestamp in format 'MM:SS' or 'HH:MM:SS'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0 for timestamp accuracy")

class CriminalEvidenceItem(BaseModel):
    """
    Represents a single piece of criminal evidence extracted from video analysis.
    
    This model structures evidence according to criminal law requirements, focusing on
    constitutional compliance, procedural accuracy, and defense strategy considerations.
    Each evidence item corresponds to specific moments in criminal proceedings that
    could impact case outcomes.
    """
    category: CriminalEvidenceCategory = Field(..., description="The specific category of criminal evidence")
    time_range: TimeRange = Field(..., description="When this evidence occurs in the video timeline")
    description: str = Field(..., description="Detailed description of what occurs during this time period")
    key_observations: List[str] = Field(default_factory=list, description="Specific observations relevant to legal analysis")
    legal_significance: str = Field(..., description="Why this evidence matters for the case outcome")
    constitutional_issues: List[str] = Field(default_factory=list, description="Potential constitutional violations or procedural concerns")
    evidence_strength: str = Field(..., description="Assessment of evidence strength: 'strong', 'moderate', or 'weak'")

    @field_validator('evidence_strength')
    @classmethod
    def validate_evidence_strength(cls, v: str) -> str:
        """Validate evidence strength values."""
        allowed_values = {'strong', 'moderate', 'weak'}
        if v.lower() not in allowed_values:
            raise ValueError(f"Evidence strength must be one of: {allowed_values}")
        return v.lower()

class CriminalVideoAnalysis(BaseModel):
    """
    Comprehensive analysis of video evidence for criminal law cases.
    
    This model structures video analysis specifically for criminal defense and prosecution,
    identifying constitutional issues, procedural compliance, and strategic considerations.
    The analysis follows chronological flow of criminal proceedings to help attorneys
    build comprehensive case strategies.
    """
    evidence_items: List[CriminalEvidenceItem] = Field(default_factory=list, description="List of extracted criminal evidence items")
    timeline_summary: str = Field(..., description="Chronological summary of events captured in the video")
    constitutional_compliance_overview: str = Field(..., description="Overall assessment of constitutional compliance during proceedings")
    missing_categories: List[CriminalEvidenceCategory] = Field(default_factory=list, description="Expected evidence categories not found in the video")

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

class EnhancedVideoInsight(VideoInsight):
    """
    Enhanced video insight model that extends VideoInsight with criminal law analysis capabilities.
    
    This model maintains full backward compatibility with the existing VideoInsight model while
    adding specialized criminal analysis fields. When is_criminal_case is True, the criminal_analysis
    field provides structured evidence extraction following criminal law procedures and constitutional
    requirements for DUI arrests, interrogations, and evidence collection.
    
    The criminal analysis helps attorneys identify:
    - Constitutional violations (4th, 5th, 6th Amendment issues)
    - Procedural compliance with arrest protocols
    - Field sobriety test administration quality
    - Miranda warnings and custodial interrogation compliance
    - Evidence chain of custody issues
    - Potential suppression motion opportunities
    """
    criminal_analysis: Optional[CriminalVideoAnalysis] = Field(
        None,
        description="Specialized criminal law analysis when video contains arrest/interrogation footage"
    )
    is_criminal_case: bool = Field(
        False,
        description="Flag indicating whether this video contains criminal law proceedings"
    )

class MediaProcessingError(BaseModel):
    """Data model for capturing errors during media processing."""
    source: str = Field(..., description="The source of the error (e.g., 'AudioProcessor', 'VideoProcessor').")
    file_name: str = Field(..., description="The name of the file that caused the error.")
    error_message: str = Field(..., description="The detailed error message.")
    error_type: str = Field(..., description="The type of error (e.g., 'TranscriptionError', 'UploadError').")

# --- Cost Tracking Models ---

class ServiceCost(BaseModel):
    """Individual service cost breakdown."""
    service_name: str = Field(..., description="Service name (e.g., 'OpenAI GPT-4o', 'Vertex AI')")
    operation_type: str = Field(..., description="Type of operation (e.g., 'document_analysis', 'video_processing')")
    units_consumed: int = Field(..., description="Units consumed (tokens, minutes, etc.)")
    unit_type: str = Field(..., description="Unit type (tokens, minutes, requests)")
    rate_per_unit: Decimal = Field(..., description="Cost per unit in USD")
    total_cost: Decimal = Field(..., description="Total cost for this service")
    file_name: Optional[str] = Field(None, description="Associated file name if applicable")

class CostEstimate(BaseModel):
    """Pre-processing cost estimation."""
    estimated_document_costs: List[ServiceCost] = Field(default_factory=list)
    estimated_media_costs: List[ServiceCost] = Field(default_factory=list)
    total_estimated_cost: Decimal = Field(Decimal('0.00'), description="Total estimated cost")
    confidence_level: float = Field(0.8, description="Estimation confidence (0.0-1.0)")
    estimation_timestamp: datetime = Field(default_factory=datetime.now)

class ActualCosts(BaseModel):
    """Actual costs incurred during processing."""
    document_analysis_costs: List[ServiceCost] = Field(default_factory=list)
    media_processing_costs: List[ServiceCost] = Field(default_factory=list)
    total_actual_cost: Decimal = Field(Decimal('0.00'), description="Total actual cost")
    processing_timestamp: datetime = Field(default_factory=datetime.now)

class CostSummary(BaseModel):
    """Complete cost summary for a case."""
    case_id: str = Field(..., description="Unique case identifier")
    cost_estimate: Optional[CostEstimate] = None
    actual_costs: Optional[ActualCosts] = None
    cost_variance: Optional[Decimal] = Field(None, description="Difference between estimated and actual")
    cost_variance_percentage: Optional[float] = Field(None, description="Variance as percentage")

class CaseAnalysisResult(BaseModel):
    """
    Combined data model for enhanced intake and case analysis, including error tracking.
    
    Supports both regular video insights and enhanced criminal law video analysis.
    The video_insights field accepts both VideoInsight and EnhancedVideoInsight objects,
    allowing for seamless integration of criminal evidence analysis while maintaining
    backward compatibility with existing workflows.
    """
    intake_analysis: Optional[EnhancedIntakeAnalysis] = None
    analyzed_documents: List[AnalyzedDocument] = Field(default_factory=list)
    transcripted_media: List[TranscriptedMedia] = Field(default_factory=list, description="A list of transcribed audio files.")
    video_insights: List[Union[VideoInsight, EnhancedVideoInsight]] = Field(
        default_factory=list,
        description="A list of video analysis insights, supporting both regular and enhanced criminal law analysis."
    )
    legal_assessment: Optional[LegalAssessment] = None
    demand_letter_evaluation: Optional[DemandLetterEvaluation] = None
    errors: List[AnalysisError] = Field(default_factory=list, description="A list of errors encountered during analysis.")
    cost_summary: Optional[CostSummary] = Field(None, description="Cost tracking information")

# --- Email Structure Planning Models ---

class SectionPlan(BaseModel):
    """
    Plan for a single section in the email generation structure.
    Designed to support the Master Email Orchestrator pattern for professional attorney communications.
    """
    number: int = Field(..., description="Section number in the email (1, 2, 3, etc.)")
    header: str = Field(..., description="Section header text in ALL CAPS (e.g., 'FACTUAL SUMMARY')")
    legal_citation: Optional[str] = Field(None, description="Florida statute citation if applicable (e.g., 'Fla. Stat. Chapter 558')")
    key_points: List[str] = Field(default_factory=list, description="Key points that will become bullet points in the section")
    emphasis_items: Dict[str, str] = Field(default_factory=dict, description="Items to bold with their values (e.g., {'contract_amount': '$128,355.77'})")
    content_requirements: List[str] = Field(default_factory=list, description="Specific content requirements for this section")

class EmailStructurePlan(BaseModel):
    """
    Master plan for the entire email structure before generation begins.
    Implements the orchestrated approach outlined in the Email Style Refinement Plan.
    """
    subject_line: str = Field(..., description="Specific subject line for the case (e.g., 'Legal Review and Recommended Next Steps – Construction Dispute')")
    greeting: str = Field(..., description="Personalized greeting (e.g., 'Good afternoon Mr. Devlin and Ms. Bell,')")
    sections: List[SectionPlan] = Field(default_factory=list, description="List of planned sections in order")
    closing: str = Field(..., description="Professional sign-off without repetitive elements")
    case_context: Dict[str, Any] = Field(default_factory=dict, description="Context that needs to be tracked across sections")

class GenerationContext(BaseModel):
    """
    Context tracker to prevent redundancy during email generation.
    Maintains state across all sections to ensure consistency and avoid repetition.
    """
    greeting_given: bool = Field(False, description="Whether the greeting has been provided")
    closing_given: bool = Field(False, description="Whether the closing has been provided")
    mentioned_items: List[str] = Field(default_factory=list, description="Items already mentioned to prevent repetition")
    section_numbers_used: List[int] = Field(default_factory=list, description="Section numbers already used")
    client_name_mentioned: bool = Field(False, description="Whether client name has been mentioned")
    case_details_mentioned: List[str] = Field(default_factory=list, description="Case details already covered")

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