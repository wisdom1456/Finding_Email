"""
Citation Tracking Service

This service provides enhanced citation mapping functionality for the Findings Email
to ensure all factual statements are traceable to their source documents.

The service tracks:
- Document sources and page numbers
- Factual statements in the generated letter
- Mapping between statements and source documents
- Enhanced appendix generation with full letter text and detailed references
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from uuid import uuid4

from backend.utils.data_models import CaseAnalysisResult
from utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


@dataclass
class Citation:
    """Individual citation linking a statement to its source."""
    id: str
    statement: str
    source_document: str
    page_number: Optional[str] = None
    confidence: str = "high"  # high, medium, low
    context: Optional[str] = None
    document_section: Optional[str] = None


@dataclass
class CitationMap:
    """Complete citation mapping for a findings letter."""
    letter_id: str
    client_name: str
    case_type: str
    generation_timestamp: str
    citations: List[Citation]
    source_documents: List[Dict[str, Any]]
    letter_content: str
    metadata: Dict[str, Any]


class CitationTrackingService:
    """
    Service for tracking citations and mapping factual statements to source documents.
    
    Provides comprehensive citation tracking for legal findings letters to ensure
    all factual statements are properly attributed to their source documents.
    """

    def __init__(self):
        """Initialize the citation tracking service."""
        self.current_citation_map: Optional[CitationMap] = None
        logger.info("CitationTrackingService initialized")

    def create_citation_map(
        self, 
        case_analysis: CaseAnalysisResult,
        letter_content: str
    ) -> CitationMap:
        """
        Create a comprehensive citation map for a findings letter.
        
        Args:
            case_analysis: Complete case analysis with source documents
            letter_content: Generated findings letter content
            
        Returns:
            CitationMap with all detected citations and mappings
        """
        import datetime
        
        logger.info("Creating citation map for findings letter")
        
        # Generate unique ID for this letter
        letter_id = str(uuid4())
        
        # Extract basic case information
        client_name = (
            case_analysis.intake_analysis.client_name 
            if case_analysis.intake_analysis 
            else "Unknown Client"
        )
        case_type = (
            case_analysis.intake_analysis.case_type 
            if case_analysis.intake_analysis 
            else "Legal Matter"
        )
        
        # Extract source documents information
        source_documents = self._extract_source_documents(case_analysis)
        
        # Analyze letter content for factual statements
        citations = self._extract_citations_from_content(letter_content, source_documents)
        
        # Create citation map
        citation_map = CitationMap(
            letter_id=letter_id,
            client_name=client_name,
            case_type=case_type,
            generation_timestamp=datetime.datetime.now().isoformat(),
            citations=citations,
            source_documents=source_documents,
            letter_content=letter_content,
            metadata={
                "total_citations": len(citations),
                "source_document_count": len(source_documents),
                "high_confidence_citations": len([c for c in citations if c.confidence == "high"]),
                "letter_length": len(letter_content),
                "citation_coverage": self._calculate_citation_coverage(letter_content, citations)
            }
        )
        
        self.current_citation_map = citation_map
        logger.info(
            f"Citation map created with {len(citations)} citations from {len(source_documents)} documents",
            extra={
                "letter_id": letter_id,
                "client_name": client_name,
                "citation_count": len(citations)
            }
        )
        
        return citation_map

    def _extract_source_documents(self, case_analysis: CaseAnalysisResult) -> List[Dict[str, Any]]:
        """
        Extract source document information from case analysis.
        
        Args:
            case_analysis: Case analysis with document data
            
        Returns:
            List of source document dictionaries
        """
        source_docs = []
        
        # Add intake analysis as a source
        if case_analysis.intake_analysis:
            source_docs.append({
                "filename": "Client Intake Form",
                "document_type": "intake",
                "key_information": getattr(case_analysis.intake_analysis, 'summary', ''),
                "relevance_to_case": "Primary case information and client details"
            })
        
        # Add document analyses
        if case_analysis.analyzed_documents:
            for doc_analysis in case_analysis.analyzed_documents:
                source_docs.append({
                    "filename": doc_analysis.filename,
                    "document_type": getattr(doc_analysis, 'document_type', 'document'),
                    "summary": getattr(doc_analysis, 'summary', ''),
                    "key_information": getattr(doc_analysis, 'key_information', ''),
                    "relevance_to_case": getattr(doc_analysis, 'relevance_to_case', ''),
                    "legal_significance": getattr(doc_analysis, 'legal_significance', ''),
                    "citations": getattr(doc_analysis, 'citations', [])
                })
        
        # Add case timeline as a source
        if case_analysis.case_timeline:
            source_docs.append({
                "filename": "Case Timeline",
                "document_type": "timeline",
                "key_information": f"Timeline with {len(case_analysis.case_timeline)} events",
                "relevance_to_case": "Chronological sequence of case events"
            })
        
        return source_docs

    def _extract_citations_from_content(
        self, 
        letter_content: str, 
        source_documents: List[Dict[str, Any]]
    ) -> List[Citation]:
        """
        Extract citations by analyzing letter content for factual statements.
        
        Args:
            letter_content: The generated findings letter content
            source_documents: Available source documents
            
        Returns:
            List of Citation objects mapping statements to sources
        """
        citations = []
        
        # Remove HTML tags for analysis
        text_content = re.sub(r'<[^>]+>', '', letter_content)
        
        # Split into sentences for analysis
        sentences = self._split_into_sentences(text_content)
        
        for sentence in sentences:
            if self._is_factual_statement(sentence):
                # Find best matching source document
                source_match = self._find_best_source_match(sentence, source_documents)
                
                if source_match:
                    citation = Citation(
                        id=str(uuid4()),
                        statement=sentence.strip(),
                        source_document=source_match["filename"],
                        page_number=source_match.get("page_number"),
                        confidence=source_match.get("confidence", "medium"),
                        context=source_match.get("context"),
                        document_section=source_match.get("document_section")
                    )
                    citations.append(citation)
        
        return citations

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences for citation analysis."""
        # Simple sentence splitting - could be enhanced with NLP
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]

    def _is_factual_statement(self, sentence: str) -> bool:
        """
        Determine if a sentence contains factual claims that need citation.
        
        Args:
            sentence: Sentence to analyze
            
        Returns:
            True if sentence contains factual claims
        """
        # Indicators of factual statements that need citations
        factual_indicators = [
            # Dates and times
            r'\b\d{1,2}/\d{1,2}/\d{4}\b',  # MM/DD/YYYY
            r'\b\d{4}-\d{2}-\d{2}\b',      # YYYY-MM-DD
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b',
            
            # Monetary amounts
            r'\$[\d,]+',
            
            # Specific claims
            r'\b(according to|based on|documented in|evidenced by|stated in|reported in)\b',
            
            # Contract/legal terms
            r'\b(contract|agreement|lease|deed|policy|statute|regulation)\b',
            
            # Parties and entities
            r'\b(defendant|plaintiff|client|company|corporation|LLC|Inc\.)\b',
            
            # Skip opinion/recommendation statements
            r'\b(recommend|suggest|advise|believe|opinion|should|could|might)\b'
        ]
        
        # Check for factual indicators
        has_factual_content = any(re.search(pattern, sentence, re.IGNORECASE) for pattern in factual_indicators[:-1])
        
        # Skip opinion statements
        has_opinion_content = bool(re.search(factual_indicators[-1], sentence, re.IGNORECASE))
        
        return has_factual_content and not has_opinion_content

    def _find_best_source_match(
        self, 
        statement: str, 
        source_documents: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best matching source document for a factual statement.
        
        Args:
            statement: Factual statement to match
            source_documents: Available source documents
            
        Returns:
            Best matching source document info or None
        """
        best_match = None
        best_score = 0
        
        for doc in source_documents:
            score = self._calculate_match_score(statement, doc)
            if score > best_score and score > 0.3:  # Minimum confidence threshold
                best_score = score
                best_match = {
                    "filename": doc["filename"],
                    "confidence": "high" if score > 0.7 else "medium" if score > 0.5 else "low",
                    "context": doc.get("key_information", ""),
                    "document_section": doc.get("document_type", ""),
                    "match_score": score
                }
        
        return best_match

    def _calculate_match_score(self, statement: str, document: Dict[str, Any]) -> float:
        """
        Calculate how well a statement matches a source document.
        
        Args:
            statement: Statement to match
            document: Source document to match against
            
        Returns:
            Match score between 0 and 1
        """
        statement_lower = statement.lower()
        score = 0.0
        
        # Check for keyword matches in different document fields
        fields_to_check = ["summary", "key_information", "relevance_to_case", "legal_significance"]
        
        for field in fields_to_check:
            if field in document and document[field]:
                field_content = document[field].lower()
                
                # Simple keyword matching - could be enhanced with semantic similarity
                statement_words = set(re.findall(r'\b\w+\b', statement_lower))
                field_words = set(re.findall(r'\b\w+\b', field_content))
                
                if statement_words and field_words:
                    overlap = len(statement_words.intersection(field_words))
                    field_score = overlap / len(statement_words)
                    score = max(score, field_score)
        
        # Boost score for specific document types
        if "contract" in statement_lower and document.get("document_type") == "contract":
            score += 0.2
        elif "timeline" in statement_lower and document.get("document_type") == "timeline":
            score += 0.2
        elif "intake" in statement_lower and document.get("document_type") == "intake":
            score += 0.2
        
        return min(score, 1.0)  # Cap at 1.0

    def _calculate_citation_coverage(self, letter_content: str, citations: List[Citation]) -> float:
        """
        Calculate what percentage of factual statements have citations.
        
        Args:
            letter_content: Full letter content
            citations: List of citations found
            
        Returns:
            Coverage percentage (0.0 to 1.0)
        """
        text_content = re.sub(r'<[^>]+>', '', letter_content)
        sentences = self._split_into_sentences(text_content)
        factual_sentences = [s for s in sentences if self._is_factual_statement(s)]
        
        if not factual_sentences:
            return 1.0  # No factual statements to cite
        
        return len(citations) / len(factual_sentences)

    def get_citation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current citation mapping.
        
        Returns:
            Summary dictionary with citation statistics
        """
        if not self.current_citation_map:
            return {"error": "No citation map available"}
        
        cm = self.current_citation_map
        
        return {
            "letter_id": cm.letter_id,
            "client_name": cm.client_name,
            "total_citations": len(cm.citations),
            "source_documents": len(cm.source_documents),
            "citation_coverage": cm.metadata.get("citation_coverage", 0),
            "confidence_breakdown": {
                "high": len([c for c in cm.citations if c.confidence == "high"]),
                "medium": len([c for c in cm.citations if c.confidence == "medium"]),
                "low": len([c for c in cm.citations if c.confidence == "low"])
            },
            "document_types": list(set([doc.get("document_type", "unknown") for doc in cm.source_documents]))
        }

    def export_citation_map(self, format: str = "dict") -> Any:
        """
        Export the current citation map in the specified format.
        
        Args:
            format: Export format ("dict", "json")
            
        Returns:
            Citation map in requested format
        """
        if not self.current_citation_map:
            return None
        
        if format == "json":
            return json.dumps(asdict(self.current_citation_map), indent=2, default=str)
        else:
            return asdict(self.current_citation_map)

    def enhance_master_prompt_with_citations(self, base_prompt: str) -> str:
        """
        Enhance the master prompt to include citation tracking instructions.
        
        Args:
            base_prompt: Original master prompt
            
        Returns:
            Enhanced prompt with citation instructions
        """
        citation_instructions = """

CRITICAL CITATION REQUIREMENTS:
When generating the findings letter, you must ensure all factual statements are traceable to source documents. Follow these guidelines:

1. **Document References**: When stating facts, include subtle document references in the format "[Source: Document Name]" or "according to [Document Name]"

2. **Specific Citations**: For contracts, dates, amounts, or legal claims, reference the specific document and section where possible

3. **Timeline References**: When mentioning dates or sequences of events, reference the timeline or specific documents

4. **Evidence Attribution**: All evidence-based statements must be attributable to specific source documents

5. **Page Numbers**: When available, include page references for key facts (e.g., "as documented on page 3 of the lease agreement")

This is essential for legal accuracy and attorney review. Every factual claim in your response should be traceable to the provided source materials.
"""
        
        return base_prompt + citation_instructions