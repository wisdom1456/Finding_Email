"""Document-related domain models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from legal_portal.core.models.enums import (
    DocumentStatus,
    DocumentType,
    FileType,
    GroupType,
)

__all__ = [
    "DocumentGroup",
    "GroupSummary",
    "FileMetadata",
    "ProcessedDocument",
    "SkippedDocument",
    "KeyDate",
    "KeyAmount",
    "ContractClause",
    "DocumentDate",
    "DocumentAmount",
    "StructuredData",
    "DocumentSummaryStructured",
]


class DocumentGroup(BaseModel):
    """A group of related documents processed as a single unit.

    Groups are ephemeral in-memory structures until Phase D (DB persistence).
    """
    group_id: str
    group_type: GroupType
    label: str  # Human-readable: "Chase Bank Statements (Jan–Jun 2024)"
    member_document_ids: List[str]
    member_document_names: List[str]
    group_metadata: Dict[str, Any] = Field(default_factory=dict)
    authority_score: Optional[int] = None  # Max of members
    canonical_document_id: Optional[str] = None  # Primary doc (e.g., base contract)

    @property
    def member_count(self) -> int:
        return len(self.member_document_ids)


class GroupSummary(BaseModel):
    """Summary of a document group — replaces N individual summaries with 1."""

    group_id: str
    group_type: GroupType
    label: str
    member_count: int
    member_document_names: List[str]
    combined_narrative: str
    key_findings: List[str] = Field(default_factory=list)
    structured_data: Dict[str, Any] = Field(default_factory=dict)
    legal_significance: Optional[str] = None
    key_quotes: List[str] = Field(default_factory=list)
    authority_score: Optional[int] = None
    extraction_quality: str = "high"


class FileMetadata(BaseModel):
    """Metadata about a processed file."""

    file_name: str
    file_type: FileType
    file_size: int
    uploaded_at: datetime = Field(default_factory=datetime.now)
    processing_time_ms: Optional[float] = None

    # EML attachment metadata (populated by eml_processor)
    attachments: Optional[List[Dict[str, Any]]] = None
    attachment_hashes: Optional[List[str]] = None
    body_hash: Optional[str] = None

    model_config = {"populate_by_name": True}

    def __init__(self, **data):
        """Override to handle legacy field names (filename -> file_name, size -> file_size)."""
        # Map legacy field names to new names
        if "filename" in data and "file_name" not in data:
            data["file_name"] = data.pop("filename")
        if "size" in data and "file_size" not in data:
            data["file_size"] = data.pop("size")

        # Ensure file_type is set if not provided (use a default)
        if "file_type" not in data:
            # Try to infer from file_name extension
            file_name = data.get("file_name", "")
            if file_name.lower().endswith(".pdf"):
                data["file_type"] = FileType.PDF
            elif file_name.lower().endswith((".docx",)):
                data["file_type"] = FileType.DOCX
            elif file_name.lower().endswith(".doc"):
                data["file_type"] = FileType.DOC
            elif file_name.lower().endswith(".txt"):
                data["file_type"] = FileType.TXT
            elif file_name.lower().endswith((".png",)):
                data["file_type"] = FileType.PNG
            elif file_name.lower().endswith((".jpg", ".jpeg")):
                data["file_type"] = FileType.JPG
            elif file_name.lower().endswith(".csv"):
                data["file_type"] = FileType.CSV
            elif file_name.lower().endswith(".eml"):
                data["file_type"] = FileType.EML
            else:
                data["file_type"] = FileType.PDF  # Default fallback

        super().__init__(**data)


class ProcessedDocument(BaseModel):
    """Represents a document after content extraction."""

    file_name: str
    content: str
    document_type: DocumentType
    file_type: FileType
    metadata: FileMetadata
    document_id: Optional[str] = None  # NEW: Link back to database record
    page_count: Optional[int] = None
    extraction_method: Optional[str] = None
    extraction_quality: Optional[str] = None  # "high", "medium", "low"
    extraction_error: Optional[str] = None  # NEW: Record extraction errors
    ocr_provider: Optional[str] = None  # NEW: Record which OCR provider was used
    signature_detection: Optional[Dict[str, Any]] = None  # Signature detection metadata (if available)
    attorney_enrichment: Optional[Dict[str, Any]] = None  # Attorney-verified enrichment data (if available)
    registry: Optional[Dict[str, Any]] = None  # Document registry from staged enrichment (if available)
    extracted_at: datetime = Field(default_factory=datetime.now)
    status: DocumentStatus = DocumentStatus.READY


class SkippedDocument(BaseModel):
    """Represents a document that was skipped during analysis."""

    document_id: str
    file_name: str
    reason: str
    error_type: str  # e.g., "DOWNLOAD_FAILED", "CORRUPTED", "EMPTY"
    recommendation: str


class KeyDate(BaseModel):
    """Represents a significant date in the case."""

    date: str = Field(description="Date in YYYY-MM-DD format or 'Month DD, YYYY'")
    event: str = Field(description="What happened on this date")
    source_document: Optional[str] = None


class KeyAmount(BaseModel):
    """Represents a monetary amount in the case."""

    amount: str = Field(description="Formatted as $XXX,XXX.XX")
    description: str = Field(description="What this amount represents")
    source_document: Optional[str] = None


class ContractClause(BaseModel):
    """A specific clause or section from a contract."""

    clause_id: Optional[str] = Field(default=None, description="Section number or ID")
    description: str = Field(description="Summary of the clause content")
    snippet: Optional[str] = Field(default=None, description="Verbatim text snippet")


class DocumentDate(BaseModel):
    """Date extracted from a document."""

    date: str = Field(description="YYYY-MM-DD or Month DD, YYYY")
    event: str = Field(description="Description of the event")
    source: Optional[str] = Field(default=None, description="Page or section reference")


class DocumentAmount(BaseModel):
    """Monetary amount extracted from a document."""

    amount: str = Field(description="Formatted amount (e.g. $1,000.00)")
    description: str = Field(description="What the amount represents")
    source: Optional[str] = Field(default=None, description="Page or section reference")


class StructuredData(BaseModel):
    """Structured data extracted from a document."""

    parties: List[str] = Field(default_factory=list, description="List of parties mentioned")
    dates: List[DocumentDate] = Field(default_factory=list, description="Key dates found")
    amounts: List[DocumentAmount] = Field(default_factory=list, description="Monetary amounts found")
    contract_clauses: List[ContractClause] = Field(default_factory=list, description="Key contract clauses")


class DocumentSummaryStructured(BaseModel):
    """Structured summary of a document for AI analysis.

    This model ensures consistent, complete extraction of legal facts.
    """

    document_id: Optional[str] = Field(default=None, description="Database UUID, stamped at parse time")
    document_name: str
    document_type: str = Field(description="E.g., contract, disclosure, correspondence, evidence")

    @validator("document_name", "document_type", pre=True)
    def reject_boolean_strings(cls, v):
        """Reject boolean values in string fields (from LLM JSON output)."""
        if isinstance(v, bool):
            return ""
        return v

    # Detailed narrative fields (New Schema)
    executive_summary: Optional[str] = Field(default=None, description="High-level overview of the document")
    key_content: Optional[str] = Field(
        default=None, description="Comprehensive narrative of important information"
    )
    important_details: List[str] = Field(
        default_factory=list, description="Critical info, risks, conflicts, or requirements"
    )
    legal_significance: Optional[str] = Field(default=None, description="Why this document matters legally")

    # Evidence & Citations (NEW)
    key_quotes: List[str] = Field(
        default_factory=list, description="Verbatim excerpts from the document that serve as evidence"
    )
    statute_citations: List[str] = Field(
        default_factory=list, description="Relevant Florida statutes (e.g., 'Fla. Stat. § 713.06')"
    )

    # Structured data container
    structured_data: Optional[StructuredData] = Field(
        default=None, description="Organized data points (dates, amounts, parties)"
    )

    # Legacy fields (kept for compatibility, optional)
    parties: List[str] = Field(default_factory=list)
    key_dates: List[KeyDate] = Field(default_factory=list)
    key_amounts: List[KeyAmount] = Field(default_factory=list)
    issues_identified: List[str] = Field(default_factory=list)

    relevance_to_case: str = Field(
        default="Relevance to be determined", description="How this document relates to the client's claims"
    )
    extraction_quality: str = Field(
        default="high", description="Quality of source text: 'high', 'medium', or 'low'"
    )
    extraction_notes: Optional[str] = Field(
        default=None, description="Any issues with source text (e.g., 'Extracted via OCR, may have errors')"
    )

    class Config:
        """Pydantic configuration for DocumentSummaryStructured."""

        extra = "ignore"  # Allow extra fields from AI response without error
