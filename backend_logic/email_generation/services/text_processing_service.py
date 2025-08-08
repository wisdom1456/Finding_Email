"""
Text Processing Service

Handles basic text processing and cleanup operations for email generation.
This service has been simplified to remove the complex text simplification pipeline,
as the original AI prompts should handle simplification adequately.

This service is responsible for:
- Basic AI response cleanup
- HTML formatting and prettification
- Essential text formatting operations

Note: Complex text simplification methods have been removed per user requirements.
"""

import re
import html
from typing import Optional
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class TextProcessingService:
    """
    Handles basic text processing and cleanup operations.
    
    This service provides essential text processing functionality while eliminating
    the complex text simplification pipeline that was causing issues.
    """
    
    def __init__(self):
        """Initialize the text processing service."""
        pass
    
    def clean_ai_response(self, response: str) -> str:
        """
        Clean and normalize AI response text.
        
        Performs basic cleanup operations on AI-generated text including:
        - Removing extra whitespace
        - Fixing common formatting issues
        - Normalizing quotes and apostrophes
        - Basic HTML entity cleanup
        
        Args:
            response: Raw AI response text
            
        Returns:
            Cleaned text
        """
        if not response:
            return ""
        
        try:
            # Remove excessive whitespace and normalize line breaks
            text = re.sub(r'\n\s*\n\s*\n+', '\n\n', response)
            text = re.sub(r'[ \t]+', ' ', text)
            text = text.strip()
            
            # Normalize quotes and apostrophes
            text = re.sub(r'["""]', '"', text)
            text = re.sub(r"[''']", "'", text)
            
            # Fix spacing around punctuation
            text = re.sub(r'\s+([.!?])', r'\1', text)
            text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)
            
            # Remove HTML entities if present
            text = html.unescape(text)
            
            # Fix common AI response artifacts
            text = re.sub(r'^\s*[\-\*\+]\s*', '', text, flags=re.MULTILINE)
            text = re.sub(r'\s*\[.*?\]\s*', ' ', text)  # Remove reference markers
            
            return text.strip()
            
        except Exception as e:
            logger.warning(f"Error cleaning AI response: {e}")
            return response
    
    def prettify_html_output(self, html_content: str, indent_size: int = 2) -> str:
        """
        Format and prettify HTML content for better readability.
        
        Args:
            html_content: Raw HTML content
            indent_size: Number of spaces for indentation
            
        Returns:
            Formatted HTML content
        """
        if not html_content:
            return ""
        
        try:
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Prettify with specified indentation
            pretty_html = soup.prettify(formatter="html")
            
            # Adjust indentation if different from default
            if indent_size != 1:
                lines = pretty_html.split('\n')
                adjusted_lines = []
                
                for line in lines:
                    # Count leading spaces
                    leading_spaces = len(line) - len(line.lstrip())
                    if leading_spaces > 0:
                        # Adjust indentation
                        new_indent = ' ' * (leading_spaces * indent_size)
                        adjusted_lines.append(new_indent + line.lstrip())
                    else:
                        adjusted_lines.append(line)
                
                pretty_html = '\n'.join(adjusted_lines)
            
            return pretty_html
            
        except Exception as e:
            logger.warning(f"Error prettifying HTML: {e}")
            return html_content
    
    def normalize_whitespace(self, text: str) -> str:
        """
        Normalize whitespace in text content.
        
        Args:
            text: Input text
            
        Returns:
            Text with normalized whitespace
        """
        if not text:
            return ""
        
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        
        # Replace multiple line breaks with double line break
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove trailing whitespace from lines
        text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def remove_html_tags(self, text: str, preserve_formatting: bool = True) -> str:
        """
        Remove HTML tags from text while optionally preserving basic formatting.
        
        Args:
            text: Input text with HTML tags
            preserve_formatting: Whether to preserve line breaks and basic formatting
            
        Returns:
            Plain text without HTML tags
        """
        if not text:
            return ""
        
        try:
            if preserve_formatting:
                # Convert common formatting tags to text equivalents
                text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
                text = re.sub(r'<p[^>]*>', '', text, flags=re.IGNORECASE)
            
            # Remove all HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            
            # Decode HTML entities
            text = html.unescape(text)
            
            # Clean up whitespace
            return self.normalize_whitespace(text)
            
        except Exception as e:
            logger.warning(f"Error removing HTML tags: {e}")
            return text
    
    def format_legal_content(self, content: str) -> str:
        """
        Apply basic formatting to legal content.
        
        Args:
            content: Legal content text
            
        Returns:
            Formatted legal content
        """
        if not content:
            return ""
        
        try:
            # Clean the content first
            content = self.clean_ai_response(content)
            
            # Ensure proper paragraph spacing
            content = re.sub(r'\n\n+', '\n\n', content)
            
            # Format section headers (simple detection)
            content = re.sub(r'^([A-Z][A-Z\s]{10,}):?\s*$', r'\1:', content, flags=re.MULTILINE)
            
            # Ensure consistent bullet point formatting
            content = re.sub(r'^\s*[-•]\s*', '• ', content, flags=re.MULTILINE)
            
            return content.strip()
            
        except Exception as e:
            logger.warning(f"Error formatting legal content: {e}")
            return content