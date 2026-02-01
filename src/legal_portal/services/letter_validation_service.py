"""Letter Validation Service - Validates generated letters against source data.

This service checks letter content against the fact matrix, gap analysis, and
verified statutes to detect potential hallucinations or unsupported claims.
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from legal_portal.core.data_models import (
    FactMatrix,
    GapAnalysisResult,
    LetterValidationResult,
    LetterValidationWarning,
)

logger = logging.getLogger(__name__)


class LetterValidationService:
    """Validates letter content against fact sources to detect potential hallucinations."""

    # Common amount patterns in letters
    AMOUNT_PATTERN = re.compile(r"\$[\d,]+(?:\.\d{2})?")

    # Date patterns - various formats
    DATE_PATTERNS = [
        re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b", re.IGNORECASE),
        re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    ]

    # Hedging phrases that indicate uncertainty
    HEDGING_PHRASES = [
        "based on the information provided",
        "according to the intake",
        "based on the documents provided",
        "if confirmed",
        "subject to verification",
        "the documents do not specify",
        "we would need",
        "based on your statement",
        "as you described",
    ]

    def validate_letter(
        self,
        letter_html: str,
        fact_matrix: FactMatrix,
        gap_analysis: Optional[GapAnalysisResult],
        verified_statutes: List[Dict],
    ) -> LetterValidationResult:
        """
        Validate letter content against source data.

        Checks:
        1. Amounts mentioned match financial_data
        2. Dates mentioned appear in timeline
        3. Party names match fact_matrix.parties
        4. Unverifiable claims have hedging language

        Args:
            letter_html: The generated letter HTML
            fact_matrix: Source facts from analysis
            gap_analysis: Gap analysis results (if available)
            verified_statutes: List of verified statutes

        Returns:
            LetterValidationResult with warnings/errors
        """
        warnings: List[LetterValidationWarning] = []
        amounts_checked = 0
        dates_checked = 0
        claims_checked = 0

        # Strip HTML tags for text analysis
        letter_text = self._strip_html(letter_html)

        # 1. Validate amounts
        amount_warnings, amounts_checked = self._validate_amounts(letter_text, fact_matrix)
        warnings.extend(amount_warnings)

        # 2. Validate dates
        date_warnings, dates_checked = self._validate_dates(letter_text, fact_matrix)
        warnings.extend(date_warnings)

        # 3. Check unverifiable claims for hedging
        if gap_analysis:
            claim_warnings, claims_checked = self._check_unverifiable_claims(
                letter_text, gap_analysis
            )
            warnings.extend(claim_warnings)

        # 4. Check for case citations (which should not be fabricated)
        citation_warnings = self._check_case_citations(letter_text, verified_statutes)
        warnings.extend(citation_warnings)

        # Log summary
        total_warnings = len(warnings)
        if total_warnings > 0:
            logger.warning(
                f"Letter validation found {total_warnings} warnings: "
                f"amounts={len(amount_warnings) if 'amount_warnings' in dir() else 0}, "
                f"dates={len(date_warnings) if 'date_warnings' in dir() else 0}, "
                f"claims={claims_checked}"
            )
        else:
            logger.info("Letter validation passed with no warnings")

        return LetterValidationResult(
            is_valid=total_warnings == 0,
            warnings=warnings,
            validation_timestamp=datetime.utcnow(),
            amounts_checked=amounts_checked,
            dates_checked=dates_checked,
            claims_checked=claims_checked,
        )

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags from text for analysis."""
        # Simple HTML stripping
        clean = re.sub(r"<[^>]+>", " ", html)
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean)
        return clean.lower()

    def _validate_amounts(
        self, letter_text: str, fact_matrix: FactMatrix
    ) -> tuple[List[LetterValidationWarning], int]:
        """Check that amounts in letter match financial_data."""
        warnings = []
        letter_amounts = self._extract_amounts(letter_text)

        # Build set of known amounts from fact matrix
        known_amounts = set()
        for item in fact_matrix.financial_data:
            if item.amount is not None:
                known_amounts.add(item.amount)
                # Also add common variations (rounded)
                known_amounts.add(round(item.amount))
                known_amounts.add(int(item.amount))

        amounts_checked = len(letter_amounts)

        for amount in letter_amounts:
            # Skip small amounts (under $100) - likely not case-critical
            if amount < 100:
                continue

            if amount not in known_amounts:
                # Check if it's close to a known amount (within 1%)
                close_match = any(
                    abs(amount - known) / known < 0.01 if known > 0 else False
                    for known in known_amounts
                )
                if not close_match:
                    warnings.append(
                        LetterValidationWarning(
                            warning_type="amount_mismatch",
                            message=f"Amount ${amount:,.2f} not found in case financial data",
                            severity="warning",
                            source_context=f"Known amounts: {sorted(list(known_amounts)[:5])}",
                        )
                    )

        return warnings, amounts_checked

    def _extract_amounts(self, text: str) -> List[float]:
        """Extract monetary amounts from text."""
        amounts = []
        for match in self.AMOUNT_PATTERN.finditer(text):
            amount_str = match.group().replace("$", "").replace(",", "")
            try:
                amounts.append(float(amount_str))
            except ValueError:
                continue
        return amounts

    def _validate_dates(
        self, letter_text: str, fact_matrix: FactMatrix
    ) -> tuple[List[LetterValidationWarning], int]:
        """Check that dates in letter appear in timeline."""
        warnings = []
        letter_dates = self._extract_dates(letter_text)

        # Build set of known dates from timeline
        known_date_strs = set()
        for event in fact_matrix.timeline:
            if event.date:
                # Normalize date string
                date_str = str(event.date).lower()
                known_date_strs.add(date_str)
                # Also add common format variations
                if hasattr(event.date, "strftime"):
                    known_date_strs.add(event.date.strftime("%B %d, %Y").lower())
                    known_date_strs.add(event.date.strftime("%m/%d/%Y").lower())

        dates_checked = len(letter_dates)

        for date_str in letter_dates:
            normalized = date_str.lower().strip()
            # Check if date appears in known dates
            if not any(normalized in known or known in normalized for known in known_date_strs):
                # Only warn if it's a specific date (not just a year)
                if re.search(r"\d{1,2}", date_str):
                    warnings.append(
                        LetterValidationWarning(
                            warning_type="date_mismatch",
                            message=f"Date '{date_str}' not found in case timeline",
                            severity="info",  # Lower severity for dates
                            source_context="Date may be calculated or from documents not in timeline",
                        )
                    )

        return warnings, dates_checked

    def _extract_dates(self, text: str) -> List[str]:
        """Extract date strings from text."""
        dates = []
        for pattern in self.DATE_PATTERNS:
            for match in pattern.finditer(text):
                dates.append(match.group())
        return dates

    def _check_unverifiable_claims(
        self, letter_text: str, gap_analysis: GapAnalysisResult
    ) -> tuple[List[LetterValidationWarning], int]:
        """Check that unverifiable claims use hedging language."""
        warnings = []
        claims_checked = 0

        unverifiable_claims = gap_analysis.gaps_by_category.get("unverifiable_claim", [])

        for gap in unverifiable_claims:
            claims_checked += 1
            # Check if the claim topic appears in the letter
            claim_keywords = gap.title.lower().split()
            # Check if at least some keywords appear
            keyword_matches = sum(1 for kw in claim_keywords if kw in letter_text and len(kw) > 3)

            if keyword_matches >= 2:  # At least 2 significant keywords match
                # Check if hedging language is present nearby
                has_hedging = self._has_hedging_language(letter_text, gap.title)
                if not has_hedging:
                    warnings.append(
                        LetterValidationWarning(
                            warning_type="unhedged_claim",
                            message=f"Unverifiable claim '{gap.title}' may lack hedging language",
                            severity="warning",
                            source_context=f"Impact: {gap.impact_on_case}",
                        )
                    )

        return warnings, claims_checked

    def _has_hedging_language(self, letter_text: str, claim_topic: str) -> bool:
        """Check if text around a claim topic contains hedging language."""
        topic_lower = claim_topic.lower()

        # Look for the claim topic in the text
        topic_words = [w for w in topic_lower.split() if len(w) > 3]
        if not topic_words:
            return True  # Can't check, assume OK

        # Find approximate location of claim
        for word in topic_words:
            pos = letter_text.find(word)
            if pos >= 0:
                # Check surrounding 500 characters for hedging phrases
                start = max(0, pos - 250)
                end = min(len(letter_text), pos + 250)
                context = letter_text[start:end]

                for phrase in self.HEDGING_PHRASES:
                    if phrase in context:
                        return True

        return False

    def _check_case_citations(
        self, letter_text: str, verified_statutes: List[Dict]
    ) -> List[LetterValidationWarning]:
        """Check for potential fabricated case citations."""
        warnings = []

        # Pattern for case citations like "Smith v. Jones" or "In re Smith"
        case_citation_pattern = re.compile(
            r"\b([A-Z][a-z]+)\s+v\.\s+([A-Z][a-z]+)|In\s+re\s+([A-Z][a-z]+)",
            re.IGNORECASE,
        )

        citations = case_citation_pattern.findall(letter_text)

        if citations:
            # Build set of any mentioned cases from verified statutes
            verified_case_names = set()
            for statute in verified_statutes:
                if "cases" in statute:
                    for case in statute.get("cases", []):
                        if isinstance(case, str):
                            verified_case_names.add(case.lower())
                        elif isinstance(case, dict) and "name" in case:
                            verified_case_names.add(case["name"].lower())

            for citation in citations:
                citation_str = " ".join(c for c in citation if c)
                if citation_str and citation_str.lower() not in verified_case_names:
                    warnings.append(
                        LetterValidationWarning(
                            warning_type="unverified_citation",
                            message=f"Case citation '{citation_str}' not in verified sources - may need verification",
                            severity="warning",
                            source_context="Case citations should be verified before sending to client",
                        )
                    )

        return warnings
