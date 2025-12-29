"""Citation Tracking Service.

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
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from legal_portal.services.statute_validation_service import StatuteValidationService

import numpy as np
from openai import OpenAI

from legal_portal.core.data_models import CaseAnalysisResult
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


@dataclass
class CitationThreshold:
    """Adaptive threshold based on case context."""

    base_threshold: float = 0.15  # Default 15%
    quality_adjustment: float = 0.0
    coverage_adjustment: float = 0.0

    @property
    def effective_threshold(self) -> float:
        """Calculate final threshold with adjustments."""
        return max(0.1, min(0.3, self.base_threshold + self.quality_adjustment + self.coverage_adjustment))

    @classmethod
    def from_case_context(
        cls, case_type: Optional[str], is_corpus_covered: bool, document_quality: float
    ) -> "CitationThreshold":
        """Create threshold based on case context.

        Args:
        ----
            case_type: Type of legal case
            is_corpus_covered: Whether case falls within Florida Legal Corpus coverage
            document_quality: Average document quality score (0-10 scale)

        Returns:
        -------
            CitationThreshold configured for case context

        """
        threshold = cls()

        # Adjust based on corpus coverage
        if is_corpus_covered:
            # Corpus-covered cases: can be stricter (expect better matches)
            threshold.coverage_adjustment = +0.05
        else:
            # Non-covered cases: be more lenient
            threshold.coverage_adjustment = -0.05

        # Adjust based on document quality (0-10 scale)
        if document_quality < 5.0:
            # Low quality docs: be more lenient (OCR errors, etc)
            threshold.quality_adjustment = -0.03
        elif document_quality > 8.0:
            # High quality docs: can be stricter
            threshold.quality_adjustment = +0.02

        return threshold


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
    """Service for tracking citations and mapping factual statements to source documents.

    Provides comprehensive citation tracking for legal findings letters to ensure
    all factual statements are properly attributed to their source documents.
    """

    def __init__(self, corpus_service: Optional["StatuteValidationService"] = None):
        """Initialize the citation tracking service.

        Args:
        ----
            corpus_service: Optional statute validation service for corpus-based validation

        """
        self.current_citation_map: Optional[CitationMap] = None
        self._openai_client = None
        self._embedding_cache: Dict[str, List[float]] = {}
        self.corpus_service = corpus_service
        logger.info("CitationTrackingService initialized")

    @property
    def openai_client(self):
        """Lazy load OpenAI client."""
        if self._openai_client is None:
            self._openai_client = OpenAI()
        return self._openai_client

    def _get_embedding(self, text: str) -> List[float]:
        """Get text embedding with caching.

        Args:
        ----
            text: Text to embed

        Returns:
        -------
            List of floats representing the embedding

        """
        # Use first 500 chars to avoid token limits
        text_key = text[:500]

        if text_key not in self._embedding_cache:
            try:
                response = self.openai_client.embeddings.create(
                    model="text-embedding-3-small", input=text_key
                )
                self._embedding_cache[text_key] = response.data[0].embedding
                logger.debug(f"Generated embedding for text (length: {len(text_key)})")
            except Exception as e:
                logger.warning(f"Failed to generate embedding: {e}")
                return []

        return self._embedding_cache[text_key]

    def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity between text embeddings.

        Args:
        ----
            text1: First text to compare
            text2: Second text to compare

        Returns:
        -------
            Similarity score between 0 and 1

        """
        emb1 = self._get_embedding(text1)
        emb2 = self._get_embedding(text2)

        if not emb1 or not emb2:
            return 0.0

        # Cosine similarity
        dot_product = np.dot(emb1, emb2)
        norm_product = np.linalg.norm(emb1) * np.linalg.norm(emb2)

        if norm_product == 0:
            return 0.0

        return float(dot_product / norm_product)

    def _normalize_text(self, text: str) -> str:
        """Normalize text for better matching.

        Args:
        ----
            text: Text to normalize

        Returns:
        -------
            Normalized text

        """
        # Normalize dates
        text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\b", "[DATE]", text)
        text = re.sub(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
            "[DATE]",
            text,
            flags=re.IGNORECASE,
        )

        # Normalize monetary amounts
        text = re.sub(r"\$[\d,]+(\.\d{2})?", "[AMOUNT]", text)

        # Normalize party names (Mr./Mrs./Ms. + Name)
        text = re.sub(r"\b(Mr\.|Mrs\.|Ms\.)\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?", "[PARTY]", text)

        # Normalize common legal terms
        term_map = {
            r"\b(contractor|contract)\b": "contract_party",
            r"\b(abandoned|ceased|terminated|stopped)\b": "work_ceased",
            r"\b(project|work|job)\b": "work",
            r"\b(notice|notification|letter)\b": "notice",
        }

        for pattern, replacement in term_map.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text.lower()

    def create_citation_map(
        self,
        letter_id: str,
        client_name: str,
        letter_content: str,
        case_analysis: CaseAnalysisResult,
        case_type: Optional[str] = None,
        is_corpus_covered: bool = True,
        average_doc_quality: float = 7.0,
    ) -> CitationMap:
        """Create a comprehensive citation map for a findings letter.

        Args:
        ----
            letter_id: Unique identifier for the letter
            client_name: Name of the client
            letter_content: Generated findings letter content
            case_analysis: Complete case analysis with source documents
            case_type: Type of legal case
            is_corpus_covered: Whether case falls within corpus coverage
            average_doc_quality: Average document quality score (0-10 scale)

        Returns:
        -------
            CitationMap with all detected citations and mappings

        """
        import datetime

        logger.info("Creating citation map for findings letter")

        # Extract basic case information
        case_type_str = case_type or (
            case_analysis.intake_analysis.case_type if case_analysis.intake_analysis else "Legal Matter"
        )

        # Extract source documents information
        source_documents = self._extract_source_documents(case_analysis)

        # Create adaptive threshold
        adaptive_threshold = CitationThreshold.from_case_context(
            case_type=case_type_str, is_corpus_covered=is_corpus_covered, document_quality=average_doc_quality
        )

        # Analyze letter content for factual statements
        citations = self._extract_citations(letter_content, source_documents, adaptive_threshold)

        # Create citation map
        citation_map = CitationMap(
            letter_id=letter_id,
            client_name=client_name,
            case_type=case_type_str,
            generation_timestamp=datetime.datetime.now().isoformat(),
            citations=citations,
            source_documents=source_documents,
            letter_content=letter_content,
            metadata={
                "total_citations": len(citations),
                "source_document_count": len(source_documents),
                "high_confidence_citations": len([c for c in citations if c.confidence == "high"]),
                "letter_length": len(letter_content),
                "citation_coverage": self._calculate_citation_coverage(letter_content, citations),
                "adaptive_threshold": adaptive_threshold.effective_threshold,
                "is_corpus_covered": is_corpus_covered,
                "average_doc_quality": average_doc_quality,
            },
        )

        self.current_citation_map = citation_map
        logger.info(
            f"Citation map created with {len(citations)} citations from {len(source_documents)} documents "
            f"(threshold: {adaptive_threshold.effective_threshold:.2f})",
            extra={"letter_id": letter_id, "client_name": client_name, "citation_count": len(citations)},
        )

        return citation_map

    # Legacy method for backwards compatibility
    def create_citation_map_legacy(
        self, case_analysis: CaseAnalysisResult, letter_content: str
    ) -> CitationMap:
        """Create a comprehensive citation map for a findings letter.

        Args:
        ----
            case_analysis: Complete case analysis with source documents
            letter_content: Generated findings letter content

        Returns:
        -------
            CitationMap with all detected citations and mappings

        """
        logger.info("Creating legacy citation map for findings letter")

        # Generate unique ID for this letter
        letter_id = str(uuid4())

        # Extract basic case information
        client_name = (
            case_analysis.intake_analysis.client_name if case_analysis.intake_analysis else "Unknown Client"
        )
        case_type_str = (
            case_analysis.intake_analysis.case_type if case_analysis.intake_analysis else "Legal Matter"
        )

        # Use the new method with default parameters
        return self.create_citation_map(
            letter_id=letter_id,
            client_name=client_name,
            letter_content=letter_content,
            case_analysis=case_analysis,
            case_type=case_type_str,
            is_corpus_covered=True,
            average_doc_quality=7.0,
        )

    def _extract_source_documents(self, case_analysis: CaseAnalysisResult) -> List[Dict[str, Any]]:
        """Extract source document information from case analysis.

        Args:
        ----
            case_analysis: Case analysis with document data

        Returns:
        -------
            List of source document dictionaries

        """
        source_docs = []

        logger.info("Extracting source documents from case analysis")

        # Add intake analysis as a source
        if case_analysis.intake_analysis:
            source_docs.append(
                {
                    "filename": "Client Intake Form",
                    "document_type": "intake",
                    "key_information": getattr(case_analysis.intake_analysis, "summary", ""),
                    "relevance_to_case": "Primary case information and client details",
                }
            )
            logger.debug("Added intake analysis as source document")

        # Add document analyses
        if case_analysis.analyzed_documents:
            logger.info(f"Processing {len(case_analysis.analyzed_documents)} analyzed documents")
        for idx, doc_analysis in enumerate(case_analysis.analyzed_documents):
            # Prefer explicit string attributes for filenames
            filename = getattr(doc_analysis, "file_name", None)
            if not isinstance(filename, str) or not filename:
                filename = getattr(doc_analysis, "filename", None)
            if not isinstance(filename, str) or not filename:
                filename = f"Document_{idx}"
            logger.debug(f"Extracting source document {idx + 1}: {filename}")

            source_docs.append(
                {
                    "filename": filename,
                    "document_type": getattr(doc_analysis, "document_type", "document"),
                    "summary": getattr(doc_analysis, "summary", ""),
                    "key_information": getattr(doc_analysis, "key_information", ""),
                    "relevance_to_case": getattr(doc_analysis, "relevance_to_case", ""),
                    "legal_significance": getattr(doc_analysis, "legal_significance", ""),
                    "citations": getattr(doc_analysis, "citations", []),
                }
            )

        # Add case timeline as a source (if it exists)
        case_timeline = getattr(case_analysis, "case_timeline", None)
        if case_timeline:
            timeline_summary = "; ".join(f"{event['date']}: {event['event']}" for event in case_timeline)
            source_docs.append(
                {
                    "filename": "Case Timeline",
                    "document_type": "timeline",
                    "key_information": timeline_summary,
                    "relevance_to_case": "Chronological overview of case events",
                }
            )
            logger.debug("Added case timeline as source document")

        logger.info(f"Extracted {len(source_docs)} total source documents")
        return source_docs

    def _extract_citations(
        self,
        letter_content: str,
        source_documents: List[Dict[str, Any]],
        adaptive_threshold: CitationThreshold,
    ) -> List[Citation]:
        """Extract citations with adaptive threshold.

        Args:
        ----
            letter_content: The generated findings letter content
            source_documents: Available source documents
            adaptive_threshold: Adaptive threshold configuration

        Returns:
        -------
            List of Citation objects mapping statements to sources

        """
        logger.info(
            f"Using adaptive threshold: {adaptive_threshold.effective_threshold:.2f} "
            f"(base={adaptive_threshold.base_threshold}, "
            f"quality_adj={adaptive_threshold.quality_adjustment:+.2f}, "
            f"coverage_adj={adaptive_threshold.coverage_adjustment:+.2f})"
        )

        citations = []
        text_content = re.sub(r"<[^>]+>", "", letter_content)
        sentences = self._split_into_sentences(text_content)

        logger.info(f"Split letter into {len(sentences)} sentences for analysis")

        factual_count = 0
        for sentence in sentences:
            if self._is_factual_statement(sentence):
                factual_count += 1
                source_match = self._find_best_source_match(
                    sentence, source_documents, threshold=adaptive_threshold.effective_threshold
                )

                if source_match:
                    citation = Citation(
                        id=str(uuid4()),
                        statement=sentence.strip(),
                        source_document=source_match["filename"],
                        page_number=source_match.get("page_number"),
                        confidence=source_match.get("confidence", "medium"),
                        context=source_match.get("context"),
                        document_section=source_match.get("document_section"),
                    )
                    citations.append(citation)

        logger.info(
            f"Identified {factual_count} factual statements, "
            f"created {len(citations)} citations "
            f"(coverage: {len(citations) / factual_count * 100:.1f}%)"
            if factual_count > 0
            else "No factual statements found"
        )

        return citations

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences for citation analysis."""
        # Simple sentence splitting - could be enhanced with NLP
        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]

    def _is_factual_statement(self, sentence: str) -> bool:
        """Determine if a sentence contains factual claims that need citation.

        Args:
        ----
            sentence: Sentence to analyze

        Returns:
        -------
            True if sentence contains factual claims

        """
        # Indicators of factual statements that need citations
        factual_indicators = [
            # Dates and times
            r"\b\d{1,2}/\d{1,2}/\d{4}\b",  # MM/DD/YYYY
            r"\b\d{4}-\d{2}-\d{2}\b",  # YYYY-MM-DD
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
            # Monetary amounts
            r"\$[\d,]+",
            # Specific claims
            r"\b(according to|based on|documented in|evidenced by|stated in|reported in)\b",
            # Contract/legal terms
            r"\b(contract|agreement|lease|deed|policy|statute|regulation)\b",
            # Parties and entities
            r"\b(defendant|plaintiff|client|company|corporation|LLC|Inc\.)\b",
            # Skip opinion/recommendation statements
            r"\b(recommend|suggest|advise|believe|opinion|should|could|might)\b",
        ]

        # Check for factual indicators
        has_factual_content = any(
            re.search(pattern, sentence, re.IGNORECASE) for pattern in factual_indicators[:-1]
        )

        # Skip opinion statements
        has_opinion_content = bool(re.search(factual_indicators[-1], sentence, re.IGNORECASE))

        return has_factual_content and not has_opinion_content

    def _find_best_source_match(
        self, statement: str, source_documents: List[Dict[str, Any]], threshold: float = 0.15
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching source document for a factual statement.

        Args:
        ----
            statement: Factual statement to match
            source_documents: Available source documents
            threshold: Minimum score threshold for matches

        Returns:
        -------
            Best matching source document info or None

        """
        best_match = None
        best_score = 0

        for doc in source_documents:
            score = self._calculate_match_score(statement, doc, use_semantic=True)
            if score > best_score and score > threshold:
                best_score = score
                best_match = {
                    "filename": doc["filename"],
                    "confidence": "high" if score > 0.7 else "medium" if score > 0.5 else "low",
                    "context": doc.get("key_information", ""),
                    "document_section": doc.get("document_type", ""),
                    "match_score": score,
                }

        return best_match

    def _calculate_match_score(
        self, statement: str, document: Dict[str, Any], use_semantic: bool = True
    ) -> float:
        """Enhanced scoring: word overlap + semantic similarity + corpus validation.

        Args:
        ----
            statement: Statement to match
            document: Source document to match against
            use_semantic: Whether to use semantic similarity

        Returns:
        -------
            Match score between 0 and 1

        """
        # 1. Normalize texts
        norm_statement = self._normalize_text(statement)

        # 2. Word-based score (30% weight)
        word_score = 0.0
        fields_to_check = ["summary", "key_information", "relevance_to_case"]

        for field in fields_to_check:
            if document.get(field):
                norm_doc_text = self._normalize_text(document[field])

                statement_words = set(re.findall(r"\b\w+\b", norm_statement))
                field_words = set(re.findall(r"\b\w+\b", norm_doc_text))

                if statement_words and field_words:
                    overlap = len(statement_words.intersection(field_words))
                    field_score = overlap / len(statement_words)
                    word_score = max(word_score, field_score)

        # 3. Semantic similarity score (60% weight)
        semantic_score = 0.0
        if use_semantic:
            for field in fields_to_check:
                if document.get(field):
                    similarity = self._calculate_semantic_similarity(statement, document[field])
                    semantic_score = max(semantic_score, similarity)

        # 4. Document type bonus (10% weight)
        type_bonus = 0.0
        if (
            ("contract" in statement.lower() and document.get("document_type") == "contract")
            or ("timeline" in statement.lower() and document.get("document_type") == "timeline")
            or ("intake" in statement.lower() and document.get("document_type") == "intake")
        ):
            type_bonus = 0.1

        # 5. Corpus validation bonus (if statute mentioned)
        corpus_bonus = 0.0
        if self.corpus_service:
            statute_mentions = re.findall(r"Fla\.\s*Stat\.\s*§\s*(\d+)\.(\d+)", statement, re.IGNORECASE)
            if statute_mentions:
                # Check if statute in corpus
                for chapter, section in statute_mentions:
                    statute_id = f"statute:fl:{chapter}.{section}"
                    if statute_id in self.corpus_service.statutes:
                        corpus_bonus = 0.05  # Boost score if valid statute
                        break

        # Combined score
        if use_semantic:
            final_score = (0.3 * word_score) + (0.6 * semantic_score) + type_bonus + corpus_bonus
        else:
            final_score = word_score + type_bonus + corpus_bonus

        return min(final_score, 1.0)

    def _calculate_citation_coverage(self, letter_content: str, citations: List[Citation]) -> float:
        """Calculate what percentage of factual statements have citations.

        Args:
        ----
            letter_content: Full letter content
            citations: List of citations found

        Returns:
        -------
            Coverage percentage (0.0 to 1.0)

        """
        text_content = re.sub(r"<[^>]+>", "", letter_content)
        sentences = self._split_into_sentences(text_content)
        factual_sentences = [s for s in sentences if self._is_factual_statement(s)]

        if not factual_sentences:
            return 1.0  # No factual statements to cite

        return len(citations) / len(factual_sentences)

    def get_citation_summary(self) -> Dict[str, Any]:
        """Get a summary of the current citation mapping.

        Returns
        -------
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
                "low": len([c for c in cm.citations if c.confidence == "low"]),
            },
            "document_types": list(set([doc.get("document_type", "unknown") for doc in cm.source_documents])),
        }

    def export_citation_map(self, format: str = "dict") -> Any:
        """Export the current citation map in the specified format.

        Args:
        ----
            format: Export format ("dict", "json")

        Returns:
        -------
            Citation map in requested format

        """
        if not self.current_citation_map:
            return None

        if format == "json":
            return json.dumps(asdict(self.current_citation_map), indent=2, default=str)
        return asdict(self.current_citation_map)

    def enhance_master_prompt_with_citations(self, base_prompt: str) -> str:
        """Enhance the master prompt to include citation tracking instructions.

        Args:
        ----
            base_prompt: Original master prompt

        Returns:
        -------
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

    def generate_findings_letter_with_citations(
        self, letter_content: str, case_analysis: CaseAnalysisResult
    ) -> str:
        """Generate a findings letter with embedded citations.

        Args:
        ----
            letter_content: Original findings letter content (without citations)
            case_analysis: Complete case analysis for citation generation

        Returns:
        -------
            Enhanced findings letter with citations embedded

        """
        logger.info("Generating findings letter with citations")

        # Create citation map
        citation_map = self.create_citation_map(case_analysis, letter_content)

        # Create enhanced letter content with citations
        enhanced_content = self._embed_citations_in_letter(letter_content, citation_map)

        # Add citation appendix
        citation_appendix = self._generate_citation_appendix(citation_map)

        # Combine letter and appendix
        final_content = f"""
        {enhanced_content}

        <hr style="margin: 40px 0; border: 1px solid #ccc;">

        {citation_appendix}
        """

        logger.info(
            f"Generated findings letter with {len(citation_map.citations)} citations",
            extra={"citation_count": len(citation_map.citations), "client_name": citation_map.client_name},
        )

        return final_content

    def _embed_citations_in_letter(self, letter_content: str, citation_map: CitationMap) -> str:
        """Embed citation references into the letter content.

        Args:
        ----
            letter_content: Original letter content
            citation_map: Citation mapping data

        Returns:
        -------
            Letter content with embedded citation references

        """
        enhanced_content = letter_content

        # Create a mapping of statements to citation numbers
        citation_refs = {}
        for i, citation in enumerate(citation_map.citations, 1):
            citation_refs[citation.statement] = i

        # Add citation numbers to factual statements
        for statement, ref_num in citation_refs.items():
            # Look for the statement in the content and add superscript citation
            if statement in enhanced_content:
                citation_link = f'<sup><a href="#citation-{ref_num}" style="color: #0066cc; text-decoration: none;">[{ref_num}]</a></sup>'
                enhanced_content = enhanced_content.replace(
                    statement,
                    f"{statement}{citation_link}",
                    1,  # Only replace first occurrence
                )

        return enhanced_content

    def _generate_citation_appendix(self, citation_map: CitationMap) -> str:
        """Generate a citation appendix with all source references.

        Args:
        ----
            citation_map: Citation mapping data

        Returns:
        -------
            HTML formatted citation appendix

        """
        appendix_html = """
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px;">
            <h3 style="color: #343a40; margin-bottom: 20px;">📚 Citations and Source References</h3>
        """

        if not citation_map.citations:
            appendix_html += """
            <p style="color: #6c757d;">No specific citations were identified in this letter.</p>
            """
        else:
            appendix_html += """
            <div style="margin-bottom: 20px;">
                <h4 style="color: #495057;">Referenced Statements</h4>
                <ol style="padding-left: 20px;">
            """

            for i, citation in enumerate(citation_map.citations, 1):
                confidence_color = {"high": "#28a745", "medium": "#ffc107", "low": "#dc3545"}.get(
                    citation.confidence, "#6c757d"
                )

                appendix_html += f"""
                <li id="citation-{i}" style="margin-bottom: 10px;">
                    <strong>Statement:</strong> "{citation.statement}"<br>
                    <strong>Source:</strong> {citation.source_document}
                    {f"<br><strong>Page:</strong> {citation.page_number}" if citation.page_number else ""}
                    <br><strong>Confidence:</strong>
                    <span style="color: {confidence_color}; font-weight: bold;">{citation.confidence.title()}</span>
                    {f"<br><strong>Context:</strong> {citation.context}" if citation.context else ""}
                </li>
                """

            appendix_html += "</ol></div>"

        # Add source documents summary
        appendix_html += """
        <div style="margin-top: 30px;">
            <h4 style="color: #495057;">Source Documents Analyzed</h4>
            <ul style="padding-left: 20px;">
        """

        for doc in citation_map.source_documents:
            appendix_html += f"""
            <li style="margin-bottom: 8px;">
                <strong>{doc["filename"]}</strong>
                <span style="color: #6c757d;">({doc.get("document_type", "document")})</span>
                {f"<br><em>{doc.get('relevance_to_case', '')}</em>" if doc.get("relevance_to_case") else ""}
            </li>
            """

        appendix_html += """
            </ul>
        </div>
        """

        # Add metadata
        appendix_html += f"""
        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
            <h4 style="color: #495057;">Citation Summary</h4>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                <div>
                    <strong>Total Citations:</strong> {len(citation_map.citations)}
                </div>
                <div>
                    <strong>Source Documents:</strong> {len(citation_map.source_documents)}
                </div>
                <div>
                    <strong>Coverage:</strong> {citation_map.metadata.get("citation_coverage", 0):.1%}
                </div>
                <div>
                    <strong>Generated:</strong> {citation_map.generation_timestamp.split("T")[0]}
                </div>
            </div>
        </div>
        </div>
        """

        return appendix_html

    def embed_citations(self, letter_content: str, citation_map: Optional[CitationMap] = None) -> str:
        """Embed citation references into the given letter content."""
        target_map = citation_map or self.current_citation_map
        if not target_map:
            logger.debug("No citation map available for embedding citations")
            return letter_content
        return self._embed_citations_in_letter(letter_content, target_map)

    def generate_citation_appendix_html(self, citation_map: Optional[CitationMap] = None) -> str:
        """Generate citation appendix HTML for the provided map or current context."""
        target_map = citation_map or self.current_citation_map
        if not target_map:
            logger.debug("No citation map available for appendix generation")
            return ""
        return self._generate_citation_appendix(target_map)

    def remove_citations_from_letter(self, letter_content: str) -> str:
        """Remove citation references from letter content to create a clean version.

        This method strips out citation references in formats like:
        - (Source: filename.pdf)
        - (Source: filename.pdf; another_file.docx)
        - [Source: filename.pdf] (legacy format)

        Args:
        ----
            letter_content: Original letter content with citations

        Returns:
        -------
            Clean letter content without citation references

        """
        import re

        # Pattern to match citation references in parentheses or square brackets
        # Matches: (Source: filename.ext), [Source: filename.ext], [Source verification needed], etc.
        # Updated to handle both "Source:" and "Source " (with/without colon)
        citation_pattern = r"[\(\[]\s*Source:?[^\)\]]+[\)\]]"

        # Remove citations and clean up any extra spaces
        clean_content = re.sub(citation_pattern, "", letter_content)

        # Clean up multiple spaces that might be left after removing citations
        clean_content = re.sub(r"\s+", " ", clean_content)

        # Clean up any double periods or other punctuation issues
        clean_content = re.sub(r"\.\.+", ".", clean_content)

        # Clean up spaces before punctuation
        clean_content = re.sub(r"\s+([,.;!?])", r"\1", clean_content)

        return clean_content.strip()

    def clean_filename_hashes(self, letter_content: str) -> str:
        """Remove hash suffixes from filenames in citations.

        This method cleans up filenames by removing the 8-character hash suffix
        that was added for security/uniqueness (e.g., _fb5b8b11).

        Examples:
        --------
        - (Source: Contract_fb5b8b11.pdf) → (Source: Contract.pdf)
        - (Source: Emails_f1823cf4.pdf) → (Source: Emails.pdf)
        - (Source: Document_abc12345.docx) → (Source: Document.docx)

        Args:
        ----
            letter_content: Letter content with citations containing hash suffixes

        Returns:
        -------
            Letter content with clean filenames in citations

        """
        import re

        # Pattern to match hash suffix before file extension
        # Matches: _[8 hex chars].[extension]
        # Example: _fb5b8b11.pdf → .pdf
        hash_pattern = r"_[a-f0-9]{8}(\.[a-zA-Z]{2,5})"

        # Replace hash + extension with just extension
        # This transforms: filename_hash.ext → filename.ext
        clean_content = re.sub(hash_pattern, r"\1", letter_content)

        return clean_content
