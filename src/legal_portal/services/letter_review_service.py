"""Letter Review Service - AI-Powered Final Review.

This service performs a final review and cleanup of generated findings letters
to ensure quality, consistency, and professional tone.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from legal_portal.services.statute_validation_service import (
    StatuteValidationService,
    ValidationResult,
)
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)

# Pre-compiled regex for faster replacement
ENCODING_ARTIFACTS = {
    re.compile(r"Â§"): "§",
    re.compile(r"â€“"): "–",
    re.compile(r"â€™"): "’",
}


class LetterReviewService:
    """Provides AI-powered final review and cleanup of findings letters."""

    def __init__(self, client: OpenAIClient, statute_validator: Optional[StatuteValidationService] = None):
        """Initialize with OpenAI client.

        Args:
        ----
            client: An instance of the custom OpenAIClient wrapper.
            statute_validator: Optional StatuteValidationService for citation validation.

        """
        self.client = client
        self.statute_validator = statute_validator or StatuteValidationService()

    def review_and_improve_letter(
        self,
        draft_letter: str,
        intake_summary: Optional[str] = None,
        case_type: Optional[str] = None,
        document_summaries_json: Optional[str] = None,
        quality_context: Optional[str] = None,
        client_name: Optional[str] = None,
    ) -> Tuple[str, Optional[ValidationResult]]:
        """Perform a comprehensive review of the draft letter for quality, accuracy, and tone.

        Returns
        -------
            Tuple of (improved_letter, validation_result)

        """
        logger.info("Performing comprehensive letter review...")

        # 1. Normalize encoding artifacts before AI review
        normalized_letter = self._normalize_encoding(draft_letter)

        prompt = self._build_review_prompt(
            normalized_letter,
            intake_summary,
            case_type,
            document_summaries_json,
            quality_context,
            client_name,
        )

        try:
            response_dict = self.client.create_chat_completion(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior law firm partner reviewing a junior associate's "
                            "draft letter. Your task is to refine it to meet the highest "
                            "professional standards."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=8000,
            )

            reviewed_content = response_dict["content"]

            if not reviewed_content:
                logger.warning("Letter review returned no content; returning original letter.")
                return normalized_letter

            # 2. Clean any code fences from AI response
            cleaned_content = self._clean_code_fences(reviewed_content)

            # 3. Final normalization pass on the AI-reviewed content
            final_letter = self._normalize_encoding(cleaned_content)

            # 4. Remove any editorial notes that the AI may have included
            final_letter = self._remove_editorial_notes(final_letter)

            # 5. Validate statute citations
            validation_result = None
            try:
                validation_result = self.statute_validator.validate_letter(final_letter)
                logger.info(
                    f"Statute validation complete: {validation_result.verified_citations} verified, "
                    f"{validation_result.unverified_citations} unverified, "
                    f"{validation_result.suspicious_citations} suspicious"
                )
            except Exception as val_error:
                logger.error(f"Error during statute validation: {val_error}", exc_info=True)

            logger.info("Comprehensive letter review completed.")
            return final_letter, validation_result

        except Exception as e:
            logger.error(f"Error during letter review: {e}", exc_info=True)
            # On error, return original letter rather than failing
            logger.warning("Returning original letter due to review error")
            return draft_letter, None

    def _normalize_encoding(self, text: str) -> str:
        """Corrects common encoding artifacts in text."""
        for pattern, replacement in ENCODING_ARTIFACTS.items():
            text = pattern.sub(replacement, text)
        return text

    def _clean_code_fences(self, text: str) -> str:
        """Remove markdown code fences from AI response.

        The AI sometimes wraps HTML content in code fences like:
        ```html
        <div>...</div>
        ```

        This method removes those fences so the HTML can be properly formatted.

        Args:
        ----
            text: AI response content potentially wrapped in code fences

        Returns:
        -------
            Cleaned content with code fences removed

        """
        if not text:
            return ""

        cleaned = text.strip()

        # Remove code fences with language specifiers (```html, ```markdown, etc.)
        # Match opening fence with optional language specifier at start
        cleaned = re.sub(r"^\s*```(?:html|markdown|md)?\s*\n?", "", cleaned, flags=re.MULTILINE)

        # Remove closing code fences
        cleaned = re.sub(r"\n?\s*```\s*$", "", cleaned, flags=re.MULTILINE)

        # Clean up any remaining stray code fences (in case of multiple wrappings)
        cleaned = re.sub(r"```(?:html|markdown|md)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?\s*```", "", cleaned)

        cleaned = cleaned.strip()

        # Log if we removed code fences
        if cleaned != text.strip():
            logger.info(
                "Removed code fences from AI response",
                extra={"original_length": len(text), "cleaned_length": len(cleaned)},
            )

        return cleaned

    def _remove_editorial_notes(self, text: str) -> str:
        """Remove editorial notes and internal comments from the letter.

        Detects and removes patterns like:
        - "**Note:** Ensure that..."
        - "[Note: ...]"
        - "Note to attorney:..."

        Args:
        ----
            text: Letter content

        Returns:
        -------
            Cleaned letter content with editorial notes removed

        """
        original_length = len(text)

        # Pattern 1: Bold note at end with specific text about placeholders
        text = re.sub(
            r"\s*\*\*Note:\*\*\s+Ensure that the placeholders[^.]*\.",
            "",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )

        # Pattern 2: Any bracketed [Note: ...]
        text = re.sub(r"\[Note:[^\]]*\]", "", text, flags=re.IGNORECASE)

        # Pattern 3: "Note to attorney:" or similar
        text = re.sub(r"Note to attorney:[^\n]*\n?", "", text, flags=re.IGNORECASE)

        # Pattern 4: Bold **Note:** followed by any content until next paragraph
        text = re.sub(r"\*\*Note:\*\*[^\n]*\n?", "", text, flags=re.IGNORECASE)

        if len(text) < original_length:
            removed_chars = original_length - len(text)
            logger.warning(
                f"Removed {removed_chars} characters of editorial notes from letter. "
                "This indicates the AI did not follow instructions to exclude internal notes."
            )

        return text.strip()

    def _build_review_prompt(
        self,
        draft_letter: str,
        intake_summary: Optional[str] = None,
        case_type: Optional[str] = None,
        document_summaries_json: Optional[str] = None,
        quality_context: Optional[str] = None,
        client_name: Optional[str] = None,
    ) -> str:
        """Perform comprehensive AI review, rewrite, and formatting of draft letter.

        This is a comprehensive pass that:
        - Verifies all facts have source citations
        - Checks for missing required elements (dates, amounts, parties)
        - Rewrites for clarity, tone, and coherence
        - Fixes grammar, spelling, and formatting
        - Ensures consistent professional style
        - Validates statute citation format
        - Removes placeholder text

        Args:
        ----
            draft_letter: The initial generated letter (HTML or Markdown)
            intake_summary: Optional brief case summary for context
            case_type: Optional case type (e.g., "real estate", "contract dispute")
            document_summaries_json: JSON summaries for source verification
            quality_context: Quality assessment results for completeness checks
            client_name: Optional client name for personalized greeting

        Returns:
        -------
            Comprehensively reviewed and rewritten letter

        """
        logger.info("Starting comprehensive letter review and rewrite")

        # Build enhanced context
        context_parts = []
        if case_type:
            context_parts.append(f"Case Type: {case_type}")
        if intake_summary:
            context_parts.append(f"Case Summary: {intake_summary}")

        # Add JSON summaries for source verification
        json_context = ""
        if document_summaries_json:
            json_context = f"""

**STRUCTURED DATA FOR VERIFICATION:**
{document_summaries_json}

Use this to verify that all major facts (dates, amounts, parties) in the letter are cited with sources.
"""

        # Add quality context for completeness
        quality_check = ""
        if quality_context:
            quality_check = f"""

**QUALITY ASSESSMENT:**
{quality_context}

Check that the letter addresses any quality issues or missing data warnings.
"""

        context_str = "\n".join(context_parts) if context_parts else "No additional context provided."

        # NEW: Log context sizes for debugging
        logger.info(
            "Letter review context prepared",
            extra={
                "draft_letter_length": len(draft_letter),
                "intake_summary_length": len(intake_summary) if intake_summary else 0,
                "document_summaries_length": len(document_summaries_json) if document_summaries_json else 0,
                "quality_context_length": len(quality_context) if quality_context else 0,
                "total_context_length": len(context_str) + len(json_context) + len(quality_check),
            },
        )

        client_intro = f" named {client_name}" if client_name else ""
        review_prompt = f"""You are a senior legal editor performing a comprehensive final review
before sending this letter to a client{client_intro}.

**Your task:** Review and REFINE the provided draft letter. The draft contains
detailed analysis based on case documents - your role is to improve clarity, verify
citations, and fix errors WITHOUT removing factual content. Do NOT regenerate the
letter from scratch.

**CRITICAL:** Preserve all specific facts, dates, amounts, party names, and document
references from the draft. Only modify for grammar, clarity, citation format, and
completeness checks.

**COMPREHENSIVE REVIEW CHECKLIST:**

1.  **Source Verification** (CRITICAL)
   - Every major fact (date, amount, party name) should reference its source document
   - Format: "per the Property Disclosure Form" or "as documented in the contract"
   - NEVER add placeholder text like "[Source verification needed]" - if you cannot verify a source, state the fact using cautious language ("based on available information") or omit it
   - Use the structured JSON data below to verify sources

1a. **CORPUS STATUTE VERIFICATION** (CRITICAL)

Check every Florida statute citation against the verified statutes provided above:

✅ VERIFIED STATUTE (from corpus): Can cite confidently without caveats
   - Use format: "Florida Statute § XXX.XX" or "Fla. Stat. § XXX.XX"
   - Reference the statute's relevance context provided above
   - No need for cautious language like "may apply" or "appears to"

❌ UNVERIFIED STATUTE (not in corpus): Use cautious language
   - Format: "Under Florida law" instead of citing specific section
   - OR: Add caveat: "Florida Statute § XXX.XX may apply (verification recommended)"
   - OR: Remove citation if not confident

**Action Required:**
1. List all Florida statute citations in the draft
2. Check each against "VERIFIED FLORIDA STATUTES" section above
3. For unverified statutes: Either remove, generalize, or add caveat
4. For verified statutes: Ensure they're cited confidently with proper format

This prevents hallucinated statute citations while allowing legitimate references.

2. **Completeness Check** (CRITICAL)
   - Verify all required sections are present: Factual Summary, Key Legal Points, Recommended Action
   - Optional fourth section: Strengths Overview (only if case has strong evidence)
   - Check that Key Legal Points uses substantive bullet paragraphs (not just headings)
   - Ensure Recommended Action includes: specific actions, protective framing, call to action
   - Flag missing elements: "[Missing: Recommended Action section]"

2a. **Release/Waiver Analysis Verification** (CRITICAL for client protection)
   - Search document summaries for any mention of "release", "waiver", "concession",
     or "settlement agreement"
   - IF found, verify the Analysis section includes:
     * Clear warning about signing the release
     * Specific explanation of what rights would be waived
     * Strong recommendation to decline or modify release
   - IF release mentioned in documents but NOT analyzed in letter, ADD dedicated
     paragraph to Challenges section:
     "IMPORTANT: You have been offered [amount] in exchange for signing a release.
     We strongly advise against signing this release without legal review, as it
     would waive your right to pursue claims for [specific issues]. The small
     payment does not adequately compensate you for waiving these valuable legal
     remedies."

3. **Tone & Language**
   - Maintain measured, cautious language ("may", "could", "appears", "based on")
   - Keep professional but client-friendly tone
   - Do NOT oversell confidence or make guarantees
   - Remove any overly aggressive or combative language

4. **Grammar & Clarity**
   - Fix any grammar, spelling, or punctuation errors
   - Improve sentence structure for clarity and flow
   - Ensure smooth paragraph transitions for coherence
   - Break up overly long sentences

5. **Consistency & Formatting**
   - Dates consistently formatted (Month DD, YYYY)
   - Dollar amounts consistently formatted ($XXX,XXX.XX)
   - Party names spelled consistently throughout
   - Statute citations in correct format (Florida Statute § XXX.XX)
   - Document references are clear and specific

6. **Placeholder Detection** (BLOCKING - MUST FIX OR FAIL)

   **CRITICAL:** The following are UNACCEPTABLE and make the letter UNPROFESSIONAL:
   - "[Note: ...]", "[Insert...]", "[Your Name]", "[Source verification needed]"
   - "XXX", "TBD", "[PLACEHOLDER]" in any form
   - Generic phrases like "comprehensive analysis is required" WITHOUT actual analysis

   **MANDATORY FIXES - DO NOT SKIP:**

   a) **Signature Placeholders:**
      - If you see "[Your Name]": Replace with the attorney name from context, or use
        "Senior Partner" if not available
      - Use the client_name context if attorney not specified

   b) **Financial Analysis Placeholders:**
      - If you see "[Note: Financial analysis required]" or similar:
        * Look at document_summaries_json for "key_amounts"
        * If amounts exist: Write actual analysis with those amounts
        * If no amounts: Write "Financial assessment pending receipt of [specific
          documents needed]"

   c) **Missing Information Placeholders:**
      - Replace with specific statement: "This information requires [specific document type]"
      - OR: Use available data from JSON to provide substantive content

   **VERIFICATION STEP:**
   Before returning the letter, search the entire text for:
   - Any text within square brackets [...]
   - The strings "XXX", "TBD", "PLACEHOLDER"

   If ANY are found, you FAILED this review. Fix them or output:
   "REVIEW FAILED: Unable to resolve placeholder: [quote the placeholder]"

7. **Structure & Flow**
   - Ensure logical progression from Factual Summary → Key Legal Points → Recommended Action
   - Check that each section builds on previous content
   - Verify action items are specific and actionable
   - Confirm letter stays within 800-1,200 word target (1,500 max)

8. **CLIENT-FRIENDLINESS & VOICE CHECK** (CRITICAL)

   **a) Opening Verification:**
      ✅ CORRECT: "Good afternoon [Client], I hope this message finds you well. Following our review..."
      ❌ FIX: "Thank you for providing your documents. We have completed our review."

      ACTION: If opening doesn't match template, REWRITE to:
      • Start with "Good afternoon [Client],"
      • Add "I hope this message finds you well."
      • Use "Following our review" (not "We have completed")
      • Use "I am providing" (not "we are providing")

   **b) Voice Consistency Check:**
      Search for "we are", "we have", "we will" in attorney action statements.

      ❌ FIX: "We have completed our review"
      ✅ CORRECT: "I have reviewed your documents"

      ❌ FIX: "We recommend that you..."
      ✅ CORRECT: "I recommend that you..."

      NOTE: "We" is acceptable for: "our firm can", "our office", "we can work together"
      ACTION: Replace attorney-action "we" with "I"

   **c) Plain English Before Technical Terms:**
      CHECK: Is plain explanation BEFORE statute citation?

      ❌ BAD: "Florida Statute § 558.004 requires notice..."
      ✅ GOOD: "Before filing suit, you must provide written notice (Florida Statute § 558.004)..."

      ACTION: Reorder to put plain explanation first, citation in parentheses after.

   **d) Real-World Consequences:**
      CHECK: Are consequences explained concretely?

      ❌ BAD: "The subcontractor may file a lien"
      ✅ GOOD: "A lien could lead to foreclosure and forced sale of your home"

      ACTION: Add concrete consequence explanations after each risk.

   **e) Protective Language:**
      CHECK: Action items should use "to protect", "to preserve", "to avoid"

      ❌ BAD: "You should pay the subcontractor"
      ✅ GOOD: "To protect your property from foreclosure, I recommend paying the subcontractor directly"

      ACTION: Frame all recommendations with protective purpose.

   **f) Closing Verification:**
      ✅ CORRECT: "Thank you, and I remain committed to protecting your interests throughout this process."
      ❌ FIX: "We look forward to assisting you with resolving this matter."

      ACTION: Replace generic closing with commitment language using "I remain committed"

9. **FINAL VOICE VERIFICATION:**
   Before returning the letter, verify these elements:
   □ Opens with "Good afternoon [Client],"
   □ Uses "I am providing" (not "we have completed")
   □ Uses "I recommend" for attorney advice (not "we recommend")
   □ Plain English comes before technical citations
   □ At least 2 concrete consequence explanations
   □ Closes with "I remain committed to protecting your interests"

   If ANY checkbox fails, revise before returning.

**WHAT YOU CAN CHANGE:**
- Rewrite sentences for clarity and coherence
- Reorganize within sections for better flow
- Add missing source citations from the JSON data
- Strengthen weak analysis with specific facts
- Improve formatting and consistency
- Add cautious language where needed
- Opening/closing to match enhanced template ("Good afternoon" greeting, "I remain committed" closing)
- Voice to "I" for attorney actions if currently using "we"
- Paragraph formatting to bullets when presenting 3+ facts
- Action item structure to use "Why this protects you" subheadings

**WHAT NOT TO CHANGE:**
- Number and sequence of main sections (Sections 1-3, optional 4)
- Level of caution/conservatism
- Facts not in the original (don't invent new information)
- Main section headings (1. Factual Summary, 2. Key Legal Points, 3. Recommended Action)

**Case Context:**
{context_str}
{json_context}
{quality_check}

**Draft Letter to Review:**
{draft_letter}

**Instructions:** Return the improved letter in the EXACT SAME FORMAT as the input
(HTML if HTML, Markdown if Markdown). Perform a comprehensive rewrite focusing on
completeness, accuracy, and professional quality. If the letter is already excellent,
minimal changes are fine.
"""

        try:
            response_dict = self.client.create_chat_completion(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a meticulous senior legal editor with 20+ years "
                            "experience. You ensure every client letter is complete, "
                            "accurate, and professionally formatted."
                        ),
                    },
                    {"role": "user", "content": review_prompt},
                ],
                max_tokens=10000,  # Increased for comprehensive rewrites
                temperature=0.2,
            )

            improved_letter = response_dict["content"]

            if not improved_letter or len(improved_letter) < 100:
                logger.warning("Review service returned insufficient content, using original")
                return draft_letter

            logger.info(
                "Letter review complete",
                extra={
                    "original_length": len(draft_letter),
                    "improved_length": len(improved_letter),
                    "tokens_used": response_dict["usage"]["total_tokens"],
                },
            )

            return improved_letter

        except Exception as e:
            logger.error(f"Error during letter review: {e}", exc_info=True)
            # On error, return original letter rather than failing
            logger.warning("Returning original letter due to review error")
            return draft_letter

    def validate_letter_quality(self, letter: str) -> dict:
        """Quick validation check for letter quality.

        Args:
        ----
            letter: Letter content to validate

        Returns:
        -------
            Dictionary with validation results including statute validation

        """
        issues = []
        warnings = []

        # Check for placeholders
        placeholder_patterns = ["[Insert", "[TBD", "XXX", "[Fill", "[TODO"]
        for pattern in placeholder_patterns:
            if pattern in letter:
                issues.append(f"Contains placeholder text: {pattern}")

        # Check for minimum length
        if len(letter) < 500:
            issues.append("Letter is too short (< 500 characters)")

        # Check for required sections (basic check)
        required_sections = ["Factual Summary", "Key Legal Points", "Recommended Action"]
        for section in required_sections:
            if section not in letter:
                warnings.append(f"Missing or misnamed section: {section}")

        # Check for statute citations
        statute_citations = re.findall(r"§\s*\d+\.\d+", letter)
        if len(statute_citations) == 0:
            warnings.append("No statute citations found (§ XXX.XX format)")

        # Check for document references
        source_refs = re.findall(r"Source:|based on|according to|per", letter, re.IGNORECASE)
        if len(source_refs) < 2:
            warnings.append("Few or no source document references found")

        # Validate statute citations with corpus
        statute_validation = None
        try:
            statute_validation = self.statute_validator.validate_letter(letter)
            # Add warnings for unverified citations
            if statute_validation.unverified_citations > 0:
                warnings.append(
                    f"{statute_validation.unverified_citations} statute citation(s) could not be verified"
                )
            if statute_validation.suspicious_citations > 0:
                issues.append(
                    f"{statute_validation.suspicious_citations} suspicious statute citation(s) detected"
                )
        except Exception as e:
            logger.error(f"Error during statute validation: {e}", exc_info=True)
            warnings.append("Statute validation failed")

        quality_score = 10.0
        quality_score -= len(issues) * 2.0  # -2 points per issue
        quality_score -= len(warnings) * 0.5  # -0.5 points per warning
        quality_score = max(0.0, quality_score)

        result = {
            "quality_score": round(quality_score, 1),
            "issues": issues,
            "warnings": warnings,
            "has_critical_issues": len(issues) > 0,
            "statute_count": len(statute_citations),
            "source_reference_count": len(source_refs),
            "word_count": len(letter.split()),
        }

        # Add statute validation details if available
        if statute_validation:
            result["statute_validation"] = statute_validation.to_dict()

        return result

    def validate_legal_completeness(
        self,
        letter: str,
        issue_map,  # LegalIssueMap
        analysis,  # DeepAnalysis
    ):
        """Verify all identified legal issues are addressed in letter.

        Args:
        ----
            letter: The generated findings letter
            issue_map: LegalIssueMap with identified issues
            analysis: DeepAnalysis with comprehensive analysis

        Returns:
        -------
            CompletenessReport with:
            - issues_addressed: List[str]
            - issues_missing: List[str]
            - statutes_cited: List[str]
            - statutes_missing: List[str]
            - completeness_score: float (0-1)
            - recommendation: str ("complete" | "needs_revision")
            - warnings: List[str]

        """
        from legal_portal.core.data_models import CompletenessReport

        issues_addressed = []
        issues_missing = []
        warnings = []

        # Check each primary issue from analysis appears in letter
        logger.info(f"Checking completeness for {len(issue_map.primary_issues)} primary issues")

        for issue in issue_map.primary_issues:
            issue_name_lower = issue.issue_name.lower()
            letter_lower = letter.lower()

            # Check if issue name or key terms appear in letter
            found = False

            # Check for issue name
            if issue_name_lower in letter_lower:
                found = True

            # Check for category-specific terms
            if not found and issue.category:
                category_terms = {
                    "contract": ["contract", "breach", "agreement"],
                    "tort": ["negligence", "duty", "breach of duty"],
                    "statutory": [ref.lower() for ref in issue.florida_statute_references if ref],
                }
                if issue.category in category_terms:
                    for term in category_terms[issue.category]:
                        if term in letter_lower:
                            found = True
                            break

            if found:
                issues_addressed.append(issue.issue_name)
                logger.debug(f"Issue addressed: {issue.issue_name}")
            else:
                issues_missing.append(issue.issue_name)
                logger.warning(f"Issue may be missing from letter: {issue.issue_name}")
                warnings.append(f"Issue '{issue.issue_name}' may not be adequately addressed")

        # Check statute citations
        statutes_cited = []
        statutes_missing = []

        for statute_ref in issue_map.relevant_statutes:
            # Clean up statute reference for matching
            statute_clean = statute_ref.replace("§", "").replace("Fla. Stat.", "").strip()

            if statute_ref in letter or statute_clean in letter:
                statutes_cited.append(statute_ref)
            else:
                statutes_missing.append(statute_ref)
                warnings.append(f"Statute {statute_ref} may not be cited")

        # Calculate completeness score
        total_issues = len(issue_map.primary_issues)
        if total_issues > 0:
            completeness_score = len(issues_addressed) / total_issues
        else:
            completeness_score = 1.0  # No issues to address

        # Determine recommendation
        if completeness_score >= 0.9:
            recommendation = "complete"
        elif completeness_score >= 0.7:
            recommendation = "mostly_complete"
            warnings.append(
                f"Letter addresses {completeness_score:.0%} of identified issues. Consider reviewing missing issues."
            )
        else:
            recommendation = "needs_revision"
            warnings.append(
                f"Letter only addresses {completeness_score:.0%} of identified issues. Revision recommended."
            )

        logger.info(
            f"Completeness check complete: {len(issues_addressed)}/{total_issues} issues addressed, "
            f"score={completeness_score:.2f}, recommendation={recommendation}"
        )

        return CompletenessReport(
            issues_addressed=issues_addressed,
            issues_missing=issues_missing,
            statutes_cited=statutes_cited,
            statutes_missing=statutes_missing,
            completeness_score=completeness_score,
            recommendation=recommendation,
            warnings=warnings,
        )
