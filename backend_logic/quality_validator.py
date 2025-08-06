from __future__ import annotations

import re

from backend.utils.data_models import EnhancedFindingsLetter, QualityScore


class QualityValidator:
    """
    Service to validate the quality of the generated findings letter.
    """

    def validate_findings_letter(self, letter: EnhancedFindingsLetter) -> QualityScore:
        """
        Validates the overall quality of the findings letter based on several metrics.
        """
        scores = {
            "professional_tone": self._check_professional_tone(letter),
            "completeness": self._check_completeness(letter),
            "clarity": self._check_clarity(letter),
            "case_specificity": self._check_case_specificity(letter),
        }

        overall_score = sum(scores.values()) / len(scores)

        return QualityScore(
            overall_score=overall_score,
            professional_tone_score=scores["professional_tone"],
            completeness_score=scores["completeness"],
            clarity_score=scores["clarity"],
            case_specificity_score=scores["case_specificity"],
        )

    def _check_professional_tone(self, letter: EnhancedFindingsLetter) -> float:
        """
        Checks for professional language and tone.
        Returns a score from 0.0 to 1.0.
        """

        # More nuanced checks for unprofessional language
        unprofessional_patterns = [
            r"\b(like|you know|stuff|totally|gonna|wanna)\b",  # Common filler words
            r"!",  # Exclamation points are generally unprofessional in this context
            r"\?{2,}",  # Multiple question marks are unprofessional
        ]
        text_to_check = f"{letter.background_summary} {letter.review_summary}"

        # A more lenient check - we allow some matches before penalizing
        unprofessional_count = 0
        for pattern in unprofessional_patterns:
            unprofessional_count += len(
                re.findall(pattern, text_to_check, re.IGNORECASE)
            )

        # Allow up to 2 minor infractions before penalizing the score
        if unprofessional_count > 2:
            return 0.0
        if unprofessional_count > 0:
            return 0.5

        return 1.0

    def _check_completeness(self, letter: EnhancedFindingsLetter) -> float:
        """
        Checks for the completeness of the letter's sections.
        Returns a score from 0.0 to 1.0.
        """
        required_sections = [
            letter.header.client_name,
            letter.background_summary,
            letter.review_summary,
            letter.footer.attorney_name,
        ]

        return sum(1 for section in required_sections if section) / len(
            required_sections
        )

    def _check_clarity(self, letter: EnhancedFindingsLetter) -> float:
        """
        Checks for clarity and readability.
        Here, we're using sentence length as a simple proxy for clarity.
        """
        text = f"{letter.background_summary} {letter.review_summary}"
        sentences = re.split(r"[.!?]", text)

        if not sentences:
            return 0.0

        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)

        # Shorter sentences are often clearer
        if avg_sentence_length > 25:
            return 0.5

        return 1.0

    def _check_case_specificity(self, letter: EnhancedFindingsLetter) -> float:
        """
        Checks if the letter is specific to the case and avoids generic language.
        """
        generic_phrases = ["as you know", "in general", "as a matter of fact"]
        text_to_check = f"{letter.background_summary} {letter.review_summary}"

        found_generic = any(
            phrase in text_to_check.lower() for phrase in generic_phrases
        )

        return 0.0 if found_generic else 1.0
