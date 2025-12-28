"""Document Quality Validation Service.

This module validates the quality of extracted document content and provides
quality scores to help downstream AI understand document reliability.
"""

from __future__ import annotations

import re
from typing import List

from legal_portal.core.data_models import ProcessedDocument, QualityScore
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class DocumentQualityValidator:
    """Validates document extraction quality and assigns quality scores."""

    def __init__(self):
        """Initialize the validator with quality thresholds."""
        self.min_content_length = 50  # Minimum meaningful characters
        self.min_words = 10  # Minimum word count
        self.max_repetition_ratio = 0.3  # Max ratio of repeated chars (OCR errors)

    def validate_document(self, doc: ProcessedDocument) -> QualityScore:
        """Validate a processed document and return quality assessment.

        Args:
        ----
            doc: ProcessedDocument to validate

        Returns:
        -------
            QualityScore with assessment details

        """
        content = doc.content
        issues = []
        recommendations = []
        score = 10.0  # Start with perfect score, deduct for issues

        # Check 0: Detect error message patterns (must come first)
        error_indicators = ["Error:", "[No text content", "truncated", "corrupted", "failed to extract"]
        is_error_content = any(indicator.lower() in content[:500].lower() for indicator in error_indicators)
        if is_error_content:
            issues.append("Document content indicates a processing error or corruption")
            score -= 5.0
            recommendations.append("Verify the original file is a valid, non-corrupted PDF")

        # Check 1: Has meaningful content
        has_content = len(content.strip()) >= self.min_content_length
        if not has_content:
            issues.append("Content too short or empty")
            score -= 5.0
            recommendations.append("Re-upload document or verify file is not corrupted")

        # Check 2: Has sufficient words (not just noise/symbols)
        word_count = len(re.findall(r"\b\w+\b", content))
        has_words = word_count >= self.min_words
        if not has_words:
            issues.append(f"Only {word_count} words found (expected at least {self.min_words})")
            score -= 3.0

        # Check 3: Not overly repetitive (common OCR failure pattern)
        repetition_ratio = self._calculate_repetition_ratio(content)
        if repetition_ratio > self.max_repetition_ratio:
            issues.append(f"High character repetition ({repetition_ratio:.1%}) - possible OCR error")
            score -= 2.0
            recommendations.append("Original document may have poor quality - consider rescanning")

        # Check 4: Contains actual words vs. gibberish
        gibberish_ratio = self._calculate_gibberish_ratio(content)
        if gibberish_ratio > 0.5:
            issues.append(f"High gibberish content ({gibberish_ratio:.1%})")
            score -= 2.0
            recommendations.append("Document extraction failed - verify file is readable")

        # Check 5: Check for OCR/Vision API extraction notes
        ocr_provider_display = None
        if doc.ocr_provider:
            # Use the explicit ocr_provider field if available
            if doc.ocr_provider == "google_vision":
                ocr_provider_display = "Google Cloud Vision"
                issues.append("Extracted via Google Cloud Vision OCR - some formatting may be lost")
                score -= 0.5  # Minor deduction for vision extraction
            elif doc.ocr_provider == "openai":
                ocr_provider_display = "GPT-4o Vision"
                issues.append("Extracted via GPT-4o Vision API - some formatting may be lost")
                score -= 0.5  # Minor deduction for vision extraction
        elif doc.extraction_method:
            # Fallback to extraction_method field for older data
            method_lower = doc.extraction_method.lower()
            if "google" in method_lower or "cloud vision" in method_lower:
                ocr_provider_display = "Google Cloud Vision"
                issues.append("Extracted via Google Cloud Vision OCR - some formatting may be lost")
                score -= 0.5
            elif "vision" in method_lower or "gpt" in method_lower:
                ocr_provider_display = "GPT-4o Vision"
                issues.append("Extracted via GPT-4o Vision API - some formatting may be lost")
                score -= 0.5

        if doc.extraction_quality == "low":
            issues.append("Flagged as low quality by extraction service")
            score -= 2.0

        # Check 6: Truncation detection (ends mid-sentence or mid-word)
        if self._appears_truncated(content):
            issues.append("Content appears truncated (incomplete)")
            score -= 1.5
            recommendations.append("Check if full document was processed")

        # Determine completeness
        is_complete = not self._appears_truncated(content) and len(content) > 100

        # Determine confidence level
        if score >= 8.0:
            confidence = "high"
        elif score >= 5.0:
            confidence = "medium"
        else:
            confidence = "low"

        # Ensure score stays in bounds
        score = max(0.0, min(10.0, score))

        logger.info(
            f"Quality validation for {doc.file_name}: score={score:.1f}, confidence={confidence}",
            extra={
                "document": doc.file_name,
                "score": score,
                "confidence": confidence,
                "issues_count": len(issues),
            },
        )

        return QualityScore(
            document=doc.file_name,
            document_id=doc.document_id,
            score=score,
            has_meaningful_content=has_content and has_words,
            is_complete=is_complete,
            confidence_level=confidence,
            extraction_method=doc.extraction_method,
            ocr_provider=ocr_provider_display or doc.ocr_provider,
            issues=issues,
            recommendations=recommendations,
        )

    def _calculate_repetition_ratio(self, text: str) -> float:
        """Calculate ratio of repeated character sequences."""
        if len(text) < 20:
            return 0.0

        # Count sequences of 3+ repeated characters
        repeated_chars = len(re.findall(r"(.)\1{2,}", text))
        return repeated_chars / len(text)

    def _calculate_gibberish_ratio(self, text: str) -> float:
        """Calculate ratio of gibberish (non-word characters, random symbols)."""
        if len(text) < 20:
            return 0.0

        # Count actual words vs. total characters
        word_chars = sum(len(word) for word in re.findall(r"\b\w+\b", text))
        if len(text) == 0:
            return 1.0

        return 1.0 - (word_chars / len(text))

    def _appears_truncated(self, text: str) -> bool:
        """Check if content appears to be truncated.

        Uses multiple indicators to reduce false positives.
        """
        if len(text) < 50:
            return True  # Too short to be complete

        text_stripped = text.strip()

        # Check for obvious truncation indicators
        truncation_indicators = 0

        # 1. Ends with incomplete word (hyphen mid-word)
        if re.search(r"[-_]\s*$", text_stripped):
            truncation_indicators += 2

        # 2. Ends mid-sentence (no punctuation in last 100 chars)
        # More lenient: also accept colons, semicolons, closing brackets/quotes
        text_end = text_stripped[-100:] if len(text_stripped) > 100 else text_stripped
        has_proper_ending = bool(re.search(r'[.!?:;)\]"\'\}]\s*$', text_end))
        if not has_proper_ending:
            truncation_indicators += 1

        # 3. Very short content (< 200 chars) is likely incomplete
        if len(text_stripped) < 200:
            truncation_indicators += 1

        # 4. Ends with common truncation patterns like "..." or incomplete ellipsis ".."
        if re.search(r"\.\.\s*$", text_stripped) and not re.search(r"\.\.\.\s*$", text_stripped):
            truncation_indicators += 2

        # Require at least 2 indicators to flag as truncated (reduce false positives)
        return truncation_indicators >= 2

    def validate_batch(self, documents: List[ProcessedDocument]) -> dict:
        """Validate multiple documents and return summary statistics.

        Args:
        ----
            documents: List of ProcessedDocuments to validate

        Returns:
        -------
            Dictionary with validation summary and batch_results (doc_name -> dict format)

        """
        if not documents:
            return {
                "total_documents": 0,
                "overall_confidence": "high",
                "overall_average_score": 0.0,
                "low_quality_documents_count": 0,
                "batch_results": {},
            }

        # Validate each document and build batch_results dictionary
        batch_results = {}
        quality_scores = []

        for doc in documents:
            quality_score = self.validate_document(doc)
            quality_scores.append(quality_score)
            # Convert Pydantic model to dict for JSON serialization
            batch_results[doc.file_name] = quality_score.model_dump()

        # Calculate summary statistics
        low_quality_count = sum(1 for q in quality_scores if q.confidence_level == "low")
        avg_score = sum(q.score for q in quality_scores) / len(quality_scores)

        # Determine overall confidence
        if low_quality_count > (len(documents) / 2):
            overall_confidence = "low"
        elif low_quality_count > 0:
            overall_confidence = "medium"
        else:
            overall_confidence = "high"

        summary = {
            "batch_results": batch_results,
            "overall_average_score": avg_score,
            "overall_confidence": overall_confidence,
            "low_quality_documents_count": low_quality_count,
            "total_documents": len(documents),
        }

        # Log with JSON-serializable data only
        logger.info(
            f"Batch validation complete: {len(documents)} documents, avg score: {avg_score:.2f}",
            extra={
                "total_documents": len(documents),
                "average_score": round(avg_score, 2),
                "overall_confidence": overall_confidence,
                "low_quality_count": low_quality_count,
            },
        )

        return summary
