"""
Quality validation and enhancement module for legal email generation.

This module provides polish and sanitize functionality to improve email quality
and ensure compliance with content restrictions and word count limits.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Optional

import yaml

from backend_logic.config import get_openai_config


if TYPE_CHECKING:
    from openai import OpenAI


class ContentValidationError(Exception):
    """Raised when content validation fails."""


def _load_config() -> dict:
    """Load configuration from universal_legal_config.yaml."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = current_dir
    
    # Navigate up until we find the project root
    while project_root != "/" and not (
        os.path.exists(os.path.join(project_root, "app.py"))
        and os.path.exists(os.path.join(project_root, "backend"))
    ):
        project_root = os.path.dirname(project_root)
    
    if project_root == "/":
        project_root = os.getcwd()
    
    config_path = os.path.join(project_root, "backend", "config", "templates", "universal_legal_config.yaml")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _extract_plain_text(html_content: str) -> str:
    """Extract plain text from HTML content for word counting."""
    if not html_content:
        return ""
    
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html_content)
    
    # Decode HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    
    return text.strip()


def _count_words(text: str) -> int:
    """Count words in text, excluding punctuation and empty strings."""
    if not text:
        return 0
    
    # Split on whitespace and filter out empty strings and punctuation-only strings
    words = []
    for word in text.split():
        # Remove common punctuation from each end, one character at a time
        cleaned_word = word.strip()
        for punct in '.,!?;:()[]{}""''':
            cleaned_word = cleaned_word.strip(punct)
        if cleaned_word and not re.match(r"^[^\w]+$", cleaned_word):
            words.append(cleaned_word)
    
    return len(words)


def _apply_citation_filter(content: str, citation_regex: str) -> str:
    """Apply citation filter regex to remove matching content."""
    if not content or not citation_regex:
        return content
    
    try:
        # Apply the citation filter regex
        filtered_content = re.sub(citation_regex, "", content, flags=re.IGNORECASE)
        
        # Clean up any double spaces left by removals
        filtered_content = re.sub(r"\s+", " ", filtered_content)
        
        return filtered_content.strip()
        
    except re.error as e:
        print(f"QUALITY_VALIDATOR: Warning - Invalid regex pattern '{citation_regex}': {e}")
        return content


def _trim_content_to_limit(content: str, word_limit: int = 850) -> str:
    """Trim content to meet word limit by removing sentences from the end."""
    if not content:
        return content
    
    plain_text = _extract_plain_text(content)
    current_word_count = _count_words(plain_text)
    
    if current_word_count <= word_limit:
        return content
    
    print(f"QUALITY_VALIDATOR: Content exceeds {word_limit} words ({current_word_count}), trimming...")
    
    # Split content into sentences
    sentences = re.split(r"(?<=[.!?])\s+", content)
    
    # Remove sentences from the end until we're under the limit
    trimmed_content = content
    while sentences and _count_words(_extract_plain_text(" ".join(sentences))) > word_limit:
        sentences.pop()
        trimmed_content = " ".join(sentences)
    
    # Add ellipsis to indicate trimming
    if trimmed_content != content:
        trimmed_content += "..."
        print(f"QUALITY_VALIDATOR: Content trimmed to {_count_words(_extract_plain_text(trimmed_content))} words")
    
    return trimmed_content


def enforce_word_count_truncation(html_content: str, max_word_count: int) -> str:
    """
    Truncate HTML content to specified word count at the last complete sentence.
    
    This function strips HTML tags, counts words, and if the count exceeds the maximum,
    truncates the text at the last full sentence before the limit.
    
    Args:
        html_content: The HTML content to process
        max_word_count: Maximum number of words allowed
        
    Returns:
        Truncated HTML content that meets the word count requirement
    """
    if not html_content or not html_content.strip():
        return html_content
    
    # Extract plain text to count words
    plain_text = _extract_plain_text(html_content)
    current_word_count = _count_words(plain_text)
    
    # If already within limit, return original content
    if current_word_count <= max_word_count:
        print(f"QUALITY_VALIDATOR: Content within word limit ({current_word_count}/{max_word_count})")
        return html_content
    
    print(f"QUALITY_VALIDATOR: Enforcing word count limit - truncating from {current_word_count} to {max_word_count} words")
    
    # Split the plain text into sentences for intelligent truncation
    sentences = re.split(r"(?<=[.!?])\s+", plain_text)
    
    # Build truncated content sentence by sentence
    truncated_sentences = []
    running_word_count = 0
    
    for sentence in sentences:
        sentence_word_count = _count_words(sentence)
        
        # If adding this sentence would exceed the limit, stop here
        if running_word_count + sentence_word_count > max_word_count:
            break
            
        truncated_sentences.append(sentence)
        running_word_count += sentence_word_count
    
    # Rejoin the sentences
    truncated_text = " ".join(truncated_sentences)
    
    # If we truncated content, add ellipsis
    if len(truncated_sentences) < len(sentences):
        truncated_text += "..."
    
    # Now we need to preserve HTML formatting for the truncated content
    # We'll use a simple approach: if the original had HTML tags, apply basic formatting
    if "<p>" in html_content or "<strong>" in html_content or "<ul>" in html_content:
        # Preserve paragraph structure by wrapping in <p> tags
        truncated_html = f"<p>{truncated_text}</p>"
    else:
        truncated_html = truncated_text
    
    final_word_count = _count_words(_extract_plain_text(truncated_html))
    print(f"QUALITY_VALIDATOR: ✅ Word count enforced - final count: {final_word_count}/{max_word_count}")
    
    return truncated_html


def replace_hedging_language(text_content: str) -> str:
    """
    Replace hedging language with stronger alternatives while preserving quoted text.
    
    This function uses regular expressions to find and replace instances of hedging
    words (e.g., "may", "might", "potentially", "could") with stronger alternatives.
    Replacement does NOT occur within quoted text.
    
    Args:
        text_content: The text content to process
        
    Returns:
        Text with hedging language replaced by stronger alternatives
    """
    if not text_content or not text_content.strip():
        return text_content
    
    # Define hedging word replacements based on context
    hedging_replacements = {
        r"\bmay\b": "will",
        r"\bmight\b": "will",
        r"\bcould\b": "will",
        r"\bpotentially\b": "",  # Remove entirely
        r"\bpossibly\b": "",    # Remove entirely
        r"\bperhaps\b": "",     # Remove entirely
        r"\blikely\b": "",      # Remove as it's still hedging
        r"\bprobably\b": "",    # Remove as it's still hedging
        r"\bmay be able to\b": "can",
        r"\bmight be able to\b": "can",
        r"\bcould be able to\b": "can",
        r"\bmay result in\b": "will result in",
        r"\bmight result in\b": "will result in",
        r"\bcould result in\b": "will result in",
        r"\bmay have\b": "has",
        r"\bmight have\b": "has",
        r"\bcould have\b": "has",
        r"\bmay include\b": "includes",
        r"\bmight include\b": "includes",
        r"\bcould include\b": "includes"
    }
    
    print("QUALITY_VALIDATOR: Applying hedging language replacement...")
    
    # Split content to identify quoted sections (preserving them)
    # Match content within quotes: "..." or '...'
    quoted_pattern = r'(["\'])([^"\']*?)\1'
    quoted_sections = re.findall(quoted_pattern, text_content)
    
    # Create placeholders for quoted sections to preserve them
    protected_content = text_content
    placeholders = {}
    
    for i, (quote_char, quoted_text) in enumerate(quoted_sections):
        placeholder = f"__QUOTED_SECTION_{i}__"
        full_quote = f"{quote_char}{quoted_text}{quote_char}"
        placeholders[placeholder] = full_quote
        protected_content = protected_content.replace(full_quote, placeholder, 1)
    
    # Apply hedging language replacements to non-quoted content
    processed_content = protected_content
    replacements_made = 0
    
    for pattern, replacement in hedging_replacements.items():
        matches = re.findall(pattern, processed_content, re.IGNORECASE)
        if matches:
            replacements_made += len(matches)
            processed_content = re.sub(pattern, replacement, processed_content, flags=re.IGNORECASE)
    
    # Restore quoted sections
    for placeholder, original_quote in placeholders.items():
        processed_content = processed_content.replace(placeholder, original_quote)
    
    # Clean up extra whitespace that might result from removing words
    processed_content = re.sub(r"\s+", " ", processed_content)
    processed_content = processed_content.strip()
    
    if replacements_made > 0:
        print(f"QUALITY_VALIDATOR: ✅ Replaced {replacements_made} instances of hedging language")
    else:
        print("QUALITY_VALIDATOR: No hedging language found to replace")
    
    return processed_content


def _polish_with_ai(content: str, golden_sample: str, client: Optional[OpenAI] = None) -> str:
    """
    Polish content using AI to match the golden sample style.
    
    Args:
        content: The content to polish
        golden_sample: The golden sample to match
        client: Optional OpenAI client instance
        
    Returns:
        Polished content or original content if polishing fails
    """
    if not client:
        print("QUALITY_VALIDATOR: No OpenAI client provided, skipping polishing step")
        return content
    
    if not golden_sample:
        print("QUALITY_VALIDATOR: No golden sample available, skipping polishing step")
        return content
    
    try:
        config = get_openai_config()
        
        prompt = f"""Rewrite the following text so it sounds exactly like the sample provided; keep all facts unchanged.

GOLDEN SAMPLE STYLE:
{golden_sample}

CONTENT TO REWRITE:
{content}

REQUIREMENTS:
- Maintain the exact same factual content
- Match the tone and style of the golden sample
- Preserve all specific names, dates, amounts, and legal details
- Keep the same HTML formatting if present
- Do not add or remove any substantive information"""

        response = client.chat.completions.create(
            model=config["model"],
            messages=[
                {"role": "system", "content": "You are a professional legal writing editor focused on style consistency."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Lower temperature for more consistent style matching
            max_tokens=config["max_tokens"]
        )
        
        polished_content = response.choices[0].message.content
        
        if polished_content and polished_content.strip():
            print("QUALITY_VALIDATOR: Content successfully polished with AI")
            return polished_content.strip()
        print("QUALITY_VALIDATOR: AI polishing returned empty content, using original")
        return content
            
    except (OSError, ValueError, AttributeError, KeyError) as e:
        print(f"QUALITY_VALIDATOR: AI polishing failed: {e}, using original content")
        return content


def process_section_content(
    content: str,
    section_name: str,
    apply_polishing: bool = False,
    client: Optional[OpenAI] = None
) -> str:
    """
    Process individual email section content with post-processing functions.
    
    This function applies both word-count enforcement and hedging language replacement
    to individual sections based on their configured limits.
    
    Args:
        content: The section content to process
        section_name: Name of the section (for word count lookup)
        apply_polishing: Whether to apply AI-based polishing (default: False)
        client: Optional OpenAI client for polishing step
        
    Returns:
        Processed section content that meets all quality requirements
        
    Raises:
        ContentValidationError: If content cannot be processed to meet requirements
    """
    if not content or not content.strip():
        return content
    
    print(f"QUALITY_VALIDATOR: Processing section '{section_name}'...")
    
    try:
        # Load configuration to get section-specific word limits
        config = _load_config()
        word_counts = config.get("word_counts", {})
        section_word_limit = word_counts.get(section_name, 150)  # Default to 150 if not specified
        
        processed_content = content
        
        # Step 1: Apply hedging language replacement
        print(f"QUALITY_VALIDATOR: Applying hedging language replacement for '{section_name}'...")
        processed_content = replace_hedging_language(processed_content)
        
        # Step 2: Apply polishing (optional)
        if apply_polishing and client:
            golden_sample = config.get("golden_sample", "")
            print(f"QUALITY_VALIDATOR: Applying AI polishing for '{section_name}'...")
            processed_content = _polish_with_ai(processed_content, golden_sample, client)
        
        # Step 3: Apply citation filtering
        citation_filter_regex = config.get("citation_filter_regex", "")
        if citation_filter_regex:
            print(f"QUALITY_VALIDATOR: Applying citation filter for '{section_name}'...")
            processed_content = _apply_citation_filter(processed_content, citation_filter_regex)
        
        # Step 4: Apply deadline bolding for Next Steps section
        if section_name == "next_steps":
            print(f"QUALITY_VALIDATOR: Applying deadline bolding for '{section_name}'...")
            processed_content = bold_deadlines_in_next_steps(processed_content)
        
        # Step 5: Enforce word count truncation
        print(f"QUALITY_VALIDATOR: Enforcing word count limit for '{section_name}' ({section_word_limit} words)...")
        processed_content = enforce_word_count_truncation(processed_content, section_word_limit)
        
        return processed_content
        
    except Exception as e:
        error_msg = f"Section processing failed for '{section_name}': {e}"
        print(f"QUALITY_VALIDATOR: ❌ {error_msg}")
        raise ContentValidationError(error_msg) from e


def polish_and_sanitize(
    email_draft: str,
    apply_polishing: bool = False,
    client: Optional[OpenAI] = None,
    word_limit: int = 850
) -> str:
    """
    Polish and sanitize email draft according to legal content standards.
    
    This function performs the following operations:
    1. **Hedging Language Replacement**: Replaces weak language with stronger alternatives
    2. **Polishing (optional)**: Uses AI to rewrite content to match golden sample style
    3. **Citation Filtering**: Removes legal citations using configured regex pattern
    4. **Word Count Validation**: Ensures content is within specified word limit
    5. **Content Trimming**: Trims content if it exceeds word limit
    
    Args:
        email_draft: The full email draft content to process
        apply_polishing: Whether to apply AI-based polishing (default: False)
        client: Optional OpenAI client for polishing step
        word_limit: Maximum word count allowed (default: 850)
        
    Returns:
        Processed email content that meets all quality requirements
        
    Raises:
        ContentValidationError: If content cannot be processed to meet requirements
    """
    if not email_draft or not email_draft.strip():
        raise ContentValidationError("Email draft is empty or invalid")
    
    print("QUALITY_VALIDATOR: Starting polish and sanitize process...")
    
    try:
        # Load configuration
        config = _load_config()
        citation_filter_regex = config.get("citation_filter_regex", "")
        golden_sample = config.get("golden_sample", "")
        
        # Track processing steps
        processed_content = email_draft
        
        # Step 1: Apply hedging language replacement
        print("QUALITY_VALIDATOR: Applying hedging language replacement...")
        processed_content = replace_hedging_language(processed_content)
        
        # Step 2: Apply polishing (optional)
        if apply_polishing and client:
            print("QUALITY_VALIDATOR: Applying AI polishing...")
            processed_content = _polish_with_ai(processed_content, golden_sample, client)
        
        # Step 3: Apply citation filtering
        if citation_filter_regex:
            print(f"QUALITY_VALIDATOR: Applying citation filter: {citation_filter_regex}")
            original_length = len(processed_content)
            processed_content = _apply_citation_filter(processed_content, citation_filter_regex)
            
            if len(processed_content) < original_length:
                print(f"QUALITY_VALIDATOR: Removed {original_length - len(processed_content)} characters via citation filter")
        
        # Step 4: Apply deadline bolding for Next Steps content (detect based on content patterns)
        if ("next steps" in email_draft.lower() or "recommended next steps" in email_draft.lower() or
            ("within" in email_draft.lower() and "days" in email_draft.lower())):
            print("QUALITY_VALIDATOR: Applying deadline bolding to Next Steps content...")
            processed_content = bold_deadlines_in_next_steps(processed_content)
        
        # Step 5: Validate and enforce word count
        plain_text = _extract_plain_text(processed_content)
        current_word_count = _count_words(plain_text)
        
        print(f"QUALITY_VALIDATOR: Current word count: {current_word_count}/{word_limit}")
        
        if current_word_count > word_limit:
            print(f"QUALITY_VALIDATOR: Content exceeds word limit ({current_word_count} > {word_limit}), applying aggressive trimming...")
            processed_content = _trim_content_to_limit(processed_content, word_limit)
            
            # Verify final word count with multiple attempts if needed
            final_plain_text = _extract_plain_text(processed_content)
            final_word_count = _count_words(final_plain_text)
            
            # If still over limit, apply more aggressive trimming
            trim_attempts = 0
            max_attempts = 3
            while final_word_count > word_limit and trim_attempts < max_attempts:
                trim_attempts += 1
                # Reduce target by 10% each attempt to ensure we get under the limit
                aggressive_limit = int(word_limit * (0.9 ** trim_attempts))
                print(f"QUALITY_VALIDATOR: Attempt {trim_attempts}: Aggressive trimming to {aggressive_limit} words")
                processed_content = _trim_content_to_limit(processed_content, aggressive_limit)
                final_plain_text = _extract_plain_text(processed_content)
                final_word_count = _count_words(final_plain_text)
            
            if final_word_count > word_limit:
                raise ContentValidationError(
                    f"CRITICAL: Unable to reduce content to {word_limit} words after {max_attempts} attempts. "
                    f"Final count: {final_word_count}. The content generation process must produce shorter sections."
                )
        
        # Final validation
        final_word_count = _count_words(_extract_plain_text(processed_content))
        print(f"QUALITY_VALIDATOR: ✅ Processing complete. Final word count: {final_word_count}/{word_limit}")
        
        return processed_content
        
    except Exception as e:
        error_msg = f"Quality validation failed: {e}"
        print(f"QUALITY_VALIDATOR: ❌ {error_msg}")
        raise ContentValidationError(error_msg) from e


def validate_email_word_count(email_content: str, word_limit: int = 850) -> tuple[bool, int]:
    """
    Validate that email content is within word count limits.
    
    Args:
        email_content: The email content to validate
        word_limit: Maximum word count allowed (default: 850)
        
    Returns:
        Tuple of (is_valid, actual_word_count)
    """
    if not email_content:
        return True, 0
    
    plain_text = _extract_plain_text(email_content)
    word_count = _count_words(plain_text)
    
    return word_count <= word_limit, word_count


def bold_deadlines_in_next_steps(html_content: str) -> str:
    """
    Apply regex safety-net to ensure all deadlines in Next Steps section are bolded.
    
    This function uses regular expressions to find date and time-related phrases
    that are not already wrapped in <strong> tags and wraps them in <strong> tags.
    
    Args:
        html_content: The HTML content to process
        
    Returns:
        HTML content with all deadlines properly bolded
    """
    if not html_content or not html_content.strip():
        return html_content
    
    print("QUALITY_VALIDATOR: Applying deadline bolding safety-net...")
    
    # Define the regex pattern to match calendar intervals and absolute dates
    # This matches patterns like:
    # - "within 14 days", "within 30 days"
    # - "by August 21, 2025", "by December 1, 2024"
    deadline_pattern = r"(\bwithin\s+\d+\s+days?\b|\bby\s+\w+\s+\d{1,2},\s+\d{4}\b)"
    
    # Find all matches that are NOT already within <strong> tags
    def replace_unbolded_deadlines(match):
        deadline_text = match.group(1)
        # Check if this deadline is already within strong tags by looking at surrounding context
        return f"<strong>{deadline_text}</strong>"
    
    # First, we need to identify which deadlines are already bolded
    # We'll use a more sophisticated approach to avoid double-bolding
    
    # Split the content to work with sections between strong tags
    import re
    
    # Find all existing <strong>...</strong> sections to preserve them
    strong_sections = []
    strong_pattern = r"<strong>(.*?)</strong>"
    
    # Replace existing strong sections with placeholders to protect them
    def preserve_strong_section(match):
        strong_sections.append(match.group(0))
        return f"__STRONG_PLACEHOLDER_{len(strong_sections)-1}__"
    
    # Preserve existing strong tags
    protected_content = re.sub(strong_pattern, preserve_strong_section, html_content, flags=re.IGNORECASE | re.DOTALL)
    
    # Now apply deadline bolding to the protected content
    matches_found = 0
    def process_deadline_match(match):
        nonlocal matches_found
        matches_found += 1
        deadline_text = match.group(1)
        return f"<strong>{deadline_text}</strong>"
    
    processed_content = re.sub(deadline_pattern, process_deadline_match, protected_content, flags=re.IGNORECASE)
    
    # Restore the original strong sections
    for i, strong_section in enumerate(strong_sections):
        placeholder = f"__STRONG_PLACEHOLDER_{i}__"
        processed_content = processed_content.replace(placeholder, strong_section)
    
    if matches_found > 0:
        print(f"QUALITY_VALIDATOR: ✅ Bolded {matches_found} deadline(s) in Next Steps section")
    else:
        print("QUALITY_VALIDATOR: No unbolded deadlines found to process")
    
    return processed_content


def apply_citation_sanitization(content: str) -> str:
    """
    Apply citation sanitization to remove legal citations from content.
    
    Args:
        content: Content to sanitize
        
    Returns:
        Sanitized content with citations removed
    """
    try:
        config = _load_config()
        citation_filter_regex = config.get("citation_filter_regex", "")
        
        if citation_filter_regex:
            return _apply_citation_filter(content, citation_filter_regex)
        
        return content
        
    except Exception as e:
        print(f"QUALITY_VALIDATOR: Citation sanitization failed: {e}")
        return content


class WeaknessesValidationError(Exception):
    """Raised when the weaknesses field validation fails."""


def validate_weaknesses_field(generated_letter) -> None:
    """
    Validate that the generated letter has a non-empty weaknesses field.
    
    This validation function checks if the weaknesses field in the generated letter
    contains actual content and is not empty or filled with placeholder text.
    
    Args:
        generated_letter: The generated letter object with weaknesses field
        
    Raises:
        WeaknessesValidationError: If weaknesses field is empty or contains placeholder text
    """
    if not generated_letter:
        raise WeaknessesValidationError("Generated letter object is None or empty")
    
    # Check if the letter has a weaknesses field
    if not hasattr(generated_letter, "challenges"):
        raise WeaknessesValidationError("Generated letter missing 'challenges' field (weaknesses)")
    
    weaknesses_content = getattr(generated_letter, "challenges", "")
    
    # Check if weaknesses field is empty
    if not weaknesses_content or not weaknesses_content.strip():
        raise WeaknessesValidationError("Potential Challenges section is empty - email generation must include both strengths and challenges")
    
    # Extract plain text to check for meaningful content
    plain_text = _extract_plain_text(weaknesses_content).strip()
    
    if not plain_text:
        raise WeaknessesValidationError("Potential Challenges section contains no meaningful text")
    
    # Check for placeholder text patterns
    placeholder_patterns = [
        r"^(?:no\s+)?(?:challenges?|weaknesses?|issues?|concerns?)\s*(?:identified|found|available)?\.?$",
        r"^(?:potential\s+)?(?:challenges?|considerations?)\s+(?:under\s+)?(?:florida\s+)?law\.?$",
        r"^(?:strategic\s+)?considerations?\s+for\s+this\s+case\.?$",
        r"^(?:assessment\s+)?(?:reveals?\s+)?(?:considerations?\s+)?(?:under\s+)?(?:florida\s+)?law\.?$"
    ]
    
    for pattern in placeholder_patterns:
        if re.match(pattern, plain_text.lower()):
            raise WeaknessesValidationError(f"Potential Challenges section contains placeholder text: '{plain_text[:100]}...'")
    
    # Check for minimum content length (at least 50 characters of meaningful text)
    if len(plain_text) < 50:
        raise WeaknessesValidationError(f"Potential Challenges section too short ({len(plain_text)} chars) - must contain substantial analysis")
    
    # Check for minimum word count (at least 10 words)
    word_count = _count_words(plain_text)
    if word_count < 10:
        raise WeaknessesValidationError(f"Potential Challenges section too brief ({word_count} words) - must contain detailed analysis")
    
    print(f"QUALITY_VALIDATOR: ✅ Weaknesses validation passed - {word_count} words, {len(plain_text)} characters")


def validate_email_completeness(generated_letter) -> None:
    """
    Comprehensive validation of email completeness including strengths and challenges.
    
    Args:
        generated_letter: The generated letter object to validate
        
    Raises:
        WeaknessesValidationError: If validation fails
    """
    print("QUALITY_VALIDATOR: Starting comprehensive email completeness validation...")
    
    # Validate weaknesses field specifically
    validate_weaknesses_field(generated_letter)
    
    # Additional validation for strengths field
    if hasattr(generated_letter, "strengths"):
        strengths_content = getattr(generated_letter, "strengths", "")
        if strengths_content and strengths_content.strip():
            strengths_plain_text = _extract_plain_text(strengths_content).strip()
            strengths_word_count = _count_words(strengths_plain_text)
            print(f"QUALITY_VALIDATOR: ✅ Strengths validation passed - {strengths_word_count} words")
        else:
            print("QUALITY_VALIDATOR: ⚠️ Strengths field is empty")
    
    print("QUALITY_VALIDATOR: ✅ Email completeness validation passed")
