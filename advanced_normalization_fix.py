#!/usr/bin/env python3
"""
Advanced Normalization Fix for Email Generator V2
Addresses HTML corruption and implements effective sentence breaking
"""
from __future__ import annotations

import json
import re
from typing import List, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag


class AdvancedNormalizationProcessor:
    """Advanced processor to fix HTML corruption and normalize content."""
    
    def __init__(self):
        # HTML corruption patterns to fix
        self.corruption_patterns = [
            # Fix malformed font-family declarations
            (r"'[^']*times[^']*'[^']*'[^']*times[^']*'[^']*", "'Times New Roman', serif"),
            (r"'[^']*nimbus[^']*roman[^']*'[^']*", "'Nimbus Roman No9 L', serif"),
            (r"'[^']*liberation[^']*serif[^']*'[^']*", "'Liberation Serif', serif"),
            (r"'[^']*freeserif[^']*'[^']*", "'FreeSerif', serif"),
            
            # Fix malformed HTML entities
            (r"&gt;\s*&lt;", "><"),
            (r"&lt;([^&]+)&gt;", r"<\1>"),
            
            # Fix broken style attributes
            (r'style="[^"]*[^;]"[^>]*>', lambda m: self._fix_style_attribute(m.group(0))),
            
            # Remove orphaned closing tags
            (r"&lt;/[^&]+&gt;", ""),
            
            # Fix font-family corruption in style attributes
            (r"font-family:\s*'[^']*times[^']*'[^']*serif[^']*;", "font-family: 'Times New Roman', serif;"),
        ]
        
        # Sentence breaking improvements
        self.sentence_splitters = [
            # Legal enumeration patterns
            (r"(\d+\))\s+([A-Z][^.!?]*[.!?])", r"\1 \2"),
            
            # Long procedural sentences - break after colons
            (r":\s*([A-Z][^.!?]{30,}[.!?])", r": \1"),
            
            # Break compound sentences with "and" if over 20 words
            (r"\band\s+([A-Z][^.!?]{25,}[.!?])", r". \1"),
            
            # Break after "The evidence" in long sentences
            (r"The evidence demonstrates ([^.!?]{25,}[.!?])", r"The evidence demonstrates \1"),
            
            # Break long "Application Analysis" sentences
            (r"Application Analysis:\s*([^.!?]{30,}[.!?])", r"Application Analysis: \1"),
        ]

    def _fix_style_attribute(self, style_attr: str) -> str:
        """Fix corrupted style attributes."""
        # Extract the style content
        match = re.search(r'style="([^"]*)"', style_attr)
        if not match:
            return style_attr
        
        style_content = match.group(1)
        
        # Fix common style corruptions
        fixed_style = re.sub(r"font-family:\s*[^;]*times[^;]*;", 'font-family: "Times New Roman", serif;', style_content)
        fixed_style = re.sub(r"[^;]*\d+px[^;]*;", "", fixed_style)  # Remove malformed px declarations
        
        return f'style="{fixed_style}"'

    def process_html_content(self, html_content: str) -> str:
        """Process HTML content to fix corruption and normalize sentences."""
        print("🔧 ADVANCED NORMALIZATION: Starting HTML processing...")
        
        # Step 1: Fix HTML corruption
        content = self._fix_html_corruption(html_content)
        
        # Step 2: Parse with BeautifulSoup for safe manipulation
        soup = BeautifulSoup(content, "html.parser")
        
        # Step 3: Process text nodes for sentence normalization
        self._normalize_text_nodes(soup)
        
        # Step 4: Clean up any remaining issues
        final_content = str(soup)
        final_content = self._final_cleanup(final_content)
        
        print("✅ ADVANCED NORMALIZATION: Processing complete")
        return final_content

    def _fix_html_corruption(self, content: str) -> str:
        """Fix HTML corruption patterns."""
        print("🔧 Fixing HTML corruption...")
        
        for pattern, replacement in self.corruption_patterns:
            if callable(replacement):
                content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
            else:
                content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        
        return content

    def _normalize_text_nodes(self, soup: BeautifulSoup) -> None:
        """Normalize sentence length in text nodes."""
        print("📝 Normalizing sentence length...")
        
        # Find all text nodes that contain sentences
        for element in soup.find_all(text=True):
            if isinstance(element, NavigableString) and element.strip():
                original_text = str(element).strip()
                
                # Skip if it's very short or doesn't contain sentences
                if len(original_text) < 20 or "." not in original_text:
                    continue
                
                normalized_text = self._break_long_sentences(original_text)
                
                if normalized_text != original_text:
                    element.replace_with(normalized_text)

    def _break_long_sentences(self, text: str) -> str:
        """Break long sentences using intelligent patterns."""
        # Apply sentence splitters
        for pattern, replacement in self.sentence_splitters:
            text = re.sub(pattern, replacement, text)
        
        # Split into sentences and process each
        sentences = re.split(r"[.!?]+", text)
        processed_sentences = []
        
        for original_sentence in sentences:
            sentence = original_sentence.strip()
            if not sentence:
                continue
                
            # Count words
            word_count = len(sentence.split())
            
            if word_count > 15:
                # Try to break at natural points
                broken_sentence = self._break_at_natural_points(sentence)
                processed_sentences.extend(broken_sentence)
            else:
                processed_sentences.append(sentence)
        
        # Rejoin with proper punctuation
        result = ". ".join(processed_sentences)
        if result and not result.endswith("."):
            result += "."
            
        return result

    def _break_at_natural_points(self, sentence: str) -> List[str]:
        """Break a long sentence at natural points."""
        words = sentence.split()
        
        if len(words) <= 15:
            return [sentence]
        
        # Look for natural break points
        break_points = []
        
        # Find conjunctions that could be break points
        for i, word in enumerate(words):
            if (word.lower() in ["and", "but", "however", "moreover", "furthermore", "additionally"] and
                i > 5 and i < len(words) - 5):  # Not too close to beginning or end
                break_points.append(i)
        
        # Find commas that could be break points
        for i, word in enumerate(words):
            if word.endswith(",") and i > 7 and i < len(words) - 7:
                break_points.append(i)
        
        if break_points:
            # Use the break point closest to the middle
            middle = len(words) // 2
            best_break = min(break_points, key=lambda x: abs(x - middle))
            
            first_part = " ".join(words[:best_break]).strip()
            second_part = " ".join(words[best_break:]).strip()
            
            # Recursively process if still too long
            result = []
            for part in [first_part, second_part]:
                if len(part.split()) > 15:
                    result.extend(self._break_at_natural_points(part))
                else:
                    result.append(part)
            
            return result
        
        # If no natural break points, break in half
        mid_point = len(words) // 2
        first_half = " ".join(words[:mid_point])
        second_half = " ".join(words[mid_point:])
        
        return [first_half, second_half]

    def _final_cleanup(self, content: str) -> str:
        """Final cleanup of the content."""
        # Remove extra whitespace
        content = re.sub(r"\s+", " ", content)
        
        # Fix sentence spacing
        content = re.sub(r"\.\s+([a-z])", r". \1", content)
        content = re.sub(r"([.!?])\s*([A-Z])", r"\1 \2", content)
        
        # Remove empty elements
        content = re.sub(r"<([^>]+)>\s*</\1>", "", content)
        
        return content

def main():
    """Test the advanced normalization processor."""
    # Test with a sample of problematic content
    test_content = """
    <p>Legal Claims Analysis: 1) civil rights Legal Elements: State actor requirement is satisfied Constitutional deprivation component is established Causation element links actions to harm Damages component supports monetary relief Application Analysis: The legal framework applies directly to your situation based on the available evidence and our analysis shows Video and witness evidence The evidence demonstrates clear liability under established legal standards.</p>
    """
    
    processor = AdvancedNormalizationProcessor()
    result = processor.process_html_content(test_content)
    
    print("Original:")
    print(test_content)
    print("\nProcessed:")
    print(result)

if __name__ == "__main__":
    main()
