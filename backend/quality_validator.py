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
from utils.logging_config import setup_logging
logger = setup_logging('quality_validator')



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
    
    # Remove HTML tags (handles both direct tags and encoded HTML tags)
    text = re.sub(r"<[^>]+>", "", html_content) 
    text = re.sub(r"<[^>]+>", "", text)
    
    # Decode HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&", "&")
    text = text.replace("<", "<")
    text = text.replace(">", ">")
    text = text.replace(""", '"')
    text = text.replace("'", "'")
    
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    
    return text.strip()


def _count_words(text: str) -> int:
    """
    Count words in text, excluding punctuation and empty strings.
    
    This function splits the text by whitespace and then filters out any empty strings
    or strings that consist only of punctuation. It also removes common punctuation
    from the ends of words to ensure accurate counting.
    """
    if not text:
        return 0
    
    # Split on whitespace and filter out empty strings and punctuation-only strings
    words = []
    # Using specific punctuation to strip consistently for word count
    punctuation_to_strip = '.,!?;:()[]{}":\'' 
    for word in text.split():
        cleaned_word = word.strip()
        # Remove common punctuation from each end, iteratively
        for punct in punctuation_to_strip:
            cleaned_word = cleaned_word.strip(punct)
        if cleaned_word and not re.match(r"^[^\w]+$", cleaned_word): # Ensure it's not just punctuation
            words.append(cleaned_word)
    
    return len(words)


def _apply_citation_filter(content: str, citation_regex: str) -> str:
    """
    Apply citation filter regex to remove matching content.
    
    Args:
        content (str): The text content to filter.
        citation_regex (str): The regular expression pattern for legal citations.
        
    Returns:
        str: Filtered content with citations removed.
    """
    if not content or not citation_regex:
        return content
    
    try:
        # Apply the citation filter regex
        filtered_content = re.sub(citation_regex, "", content, flags=re.IGNORECASE)
        
        # Clean up any double spaces left by removals
        filtered_content = re.sub(r"\s+", " ", filtered_content)
        
        return filtered_content.strip()
        
    except re.error as e:
        logger.warning(f"QUALITY_VALIDATOR: Warning - Invalid regex pattern '{citation_regex}': {e}")
        return content


def _trim_content_to_limit(content: str, word_limit: int = 850) -> str:
    """
    Trim content to meet word limit by removing sentences from the end.
    
    Args:
        content (str): The text content to trim.
        word_limit (int): The maximum number of words allowed.
        
    Returns:
        str: Trimmed content that meets the word limit.
    """
    if not content:
        return content
    
    plain_text = _extract_plain_text(content)
    current_word_count = _count_words(plain_text)
    
    if current_word_count <= word_limit:
        return content
    
    logger.info(f'QUALITY_VALIDATOR: Content exceeds {word_limit} words ({current_word_count}), trimming...')
    
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
    logger.info(f'QUALITY_VALIDATOR: Content trimmed to {_count_words(_extract_plain_text(trimmed_content))} words')
    
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
        logger.info(f'QUALITY_VALIDATOR: Content within word limit ({current_word_count}/{max_word_count})')
        return html_content
    
    logger.info(f'QUALITY_VALIDATOR: Enforcing word count limit - truncating from {current_word_count} to {max_word_count} words')
    
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
    logger.info(f'QUALITY_VALIDATOR: ✅ Word count enforced - final count: {final_word_count}/{max_word_count}')
    
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
    
    logger.info('QUALITY_VALIDATOR: Applying hedging language replacement...')
    
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
        logger.info(f'QUALITY_VALIDATOR: ✅ Replaced {replacements_made} instances of hedging language')
    else:
        logger.info('QUALITY_VALIDATOR: No hedging language found to replace')
    
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
        logger.warning('QUALITY_VALIDATOR: No OpenAI client provided, skipping polishing step')
        return content
    
    if not golden_sample:
        logger.warning('QUALITY_VALIDATOR: No golden sample available, skipping polishing step')
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
            logger.info('QUALITY_VALIDATOR: Content successfully polished with AI')
            return polished_content.strip()
        logger.info('QUALITY_VALIDATOR: AI polishing returned empty content, using original')
        return content
            
    except (OSError, ValueError, AttributeError, KeyError) as e:
        logger.error(f'QUALITY_VALIDATOR: AI polishing failed: {e}, using original content')
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
    
    logger.debug(f"QUALITY_VALIDATOR: Processing section '{section_name}'...")
    
    try:
        # Load configuration to get section-specific word limits
        config = _load_config()
        word_counts = config.get("word_counts", {})
        section_word_limit = word_counts.get(section_name, 150)  # Default to 150 if not specified
        
        processed_content = content
        
        # Step 1: Apply hedging language replacement
        logger.info(f"QUALITY_VALIDATOR: Applying hedging language replacement for '{section_name}'...")
        processed_content = replace_hedging_language(processed_content)
        
        # Step 2: Apply polishing (optional)
        if apply_polishing and client:
            golden_sample = config.get("golden_sample", "")
            logger.info(f"QUALITY_VALIDATOR: Applying AI polishing for '{section_name}'...")
            processed_content = _polish_with_ai(processed_content, golden_sample, client)
        
        # Step 3: Apply citation filtering
        citation_filter_regex = config.get("citation_filter_regex", "")
        if citation_filter_regex:
            logger.info(f"QUALITY_VALIDATOR: Applying citation filter for '{section_name}'...")
            processed_content = _apply_citation_filter(processed_content, citation_filter_regex)
        
        # Step 4: Apply deadline bolding for Next Steps section
        if section_name == "next_steps":
            logger.info(f"QUALITY_VALIDATOR: Applying deadline bolding for '{section_name}'...")
            processed_content = bold_deadlines_in_next_steps(processed_content)
        
        # Step 5: Enforce word count truncation
        logger.info(f"QUALITY_VALIDATOR: Enforcing word count limit for '{section_name}' ({section_word_limit} words)...")
        processed_content = enforce_word_count_truncation(processed_content, section_word_limit)
        
        return processed_content
        
    except Exception as e:
        error_msg = f"Section processing failed for '{section_name}': {e}"
        logger.error(f'QUALITY_VALIDATOR: ❌ {error_msg}')
        raise ContentValidationError(error_msg) from e