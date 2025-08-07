"""
Quality validation and enhancement module for legal email generation.

This module provides polish and sanitize functionality to improve email quality
and ensure compliance with content restrictions and word count limits.
"""

from __future__ import annotations

import os
import re
from typing import Optional

import yaml
from openai import OpenAI

from backend_logic.config import get_openai_config


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
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _extract_plain_text(html_content: str) -> str:
    """Extract plain text from HTML content for word counting."""
    if not html_content:
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html_content)
    
    # Decode HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def _count_words(text: str) -> int:
    """Count words in text, excluding punctuation and empty strings."""
    if not text:
        return 0
    
    # Split on whitespace and filter out empty strings and punctuation-only strings
    words = [word.strip('.,!?;:()[]{}""''') for word in text.split()]
    words = [word for word in words if word and not re.match(r'^[^\w]+$', word)]
    
    return len(words)


def _apply_citation_filter(content: str, citation_regex: str) -> str:
    """Apply citation filter regex to remove matching content."""
    if not content or not citation_regex:
        return content
    
    try:
        # Apply the citation filter regex
        filtered_content = re.sub(citation_regex, '', content, flags=re.IGNORECASE)
        
        # Clean up any double spaces left by removals
        filtered_content = re.sub(r'\s+', ' ', filtered_content)
        
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
    sentences = re.split(r'(?<=[.!?])\s+', content)
    
    # Remove sentences from the end until we're under the limit
    trimmed_content = content
    while sentences and _count_words(_extract_plain_text(' '.join(sentences))) > word_limit:
        sentences.pop()
        trimmed_content = ' '.join(sentences)
    
    # Add ellipsis to indicate trimming
    if trimmed_content != content:
        trimmed_content += "..."
        print(f"QUALITY_VALIDATOR: Content trimmed to {_count_words(_extract_plain_text(trimmed_content))} words")
    
    return trimmed_content


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
        else:
            print("QUALITY_VALIDATOR: AI polishing returned empty content, using original")
            return content
            
    except Exception as e:
        print(f"QUALITY_VALIDATOR: AI polishing failed: {e}, using original content")
        return content


def polish_and_sanitize(
    email_draft: str,
    apply_polishing: bool = False,
    client: Optional[OpenAI] = None,
    word_limit: int = 850
) -> str:
    """
    Polish and sanitize email draft according to legal content standards.
    
    This function performs the following operations:
    1. **Polishing (optional)**: Uses AI to rewrite content to match golden sample style
    2. **Citation Filtering**: Removes legal citations using configured regex pattern
    3. **Word Count Validation**: Ensures content is within specified word limit
    4. **Content Trimming**: Trims content if it exceeds word limit
    
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
        citation_filter_regex = config.get('citation_filter_regex', '')
        golden_sample = config.get('golden_sample', '')
        
        # Track processing steps
        processed_content = email_draft
        
        # Step 1: Apply polishing (optional)
        if apply_polishing and client:
            print("QUALITY_VALIDATOR: Applying AI polishing...")
            processed_content = _polish_with_ai(processed_content, golden_sample, client)
        
        # Step 2: Apply citation filtering
        if citation_filter_regex:
            print(f"QUALITY_VALIDATOR: Applying citation filter: {citation_filter_regex}")
            original_length = len(processed_content)
            processed_content = _apply_citation_filter(processed_content, citation_filter_regex)
            
            if len(processed_content) < original_length:
                print(f"QUALITY_VALIDATOR: Removed {original_length - len(processed_content)} characters via citation filter")
        
        # Step 3: Validate and enforce word count
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
        citation_filter_regex = config.get('citation_filter_regex', '')
        
        if citation_filter_regex:
            return _apply_citation_filter(content, citation_filter_regex)
        
        return content
        
    except Exception as e:
        print(f"QUALITY_VALIDATOR: Citation sanitization failed: {e}")
        return content
